"""POC3 scope: audio -> faster-whisper -> transcript, streamed back over WS.

Still no translation (POC4) — transcript messages carry the original-language
text. Audio is still optionally saved to .wav for debugging (see
app.config.settings.SAVE_DEBUG_AUDIO).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
import wave
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config.settings import (
    AUDIO_CHANNELS,
    AUDIO_SAMPLE_RATE,
    AUDIO_SAMPLE_WIDTH_BYTES,
    DEBUG_AUDIO_DIR,
    SAVE_DEBUG_AUDIO,
)
from app.models.protocol import ClientStart, parse_client_message
from app.providers.speech_to_text.faster_whisper import FasterWhisperProvider
from app.providers.speech_to_text.base import TranscriptResult
from app.providers.translation.nllb import NLLBTranslationProvider

logger = logging.getLogger("translation_socket")

router = APIRouter()


class AudioSessionStats:
    def __init__(self, session_id: str, source_language: str):
        self.session_id = session_id
        self.source_language = source_language
        self.started_at = time.monotonic()
        self.last_chunk_at = self.started_at
        self.chunk_count = 0
        self.total_bytes = 0
        self.stalls = 0

    def record_chunk(self, size: int) -> None:
        now = time.monotonic()
        if self.chunk_count > 0:
            gap_ms = (now - self.last_chunk_at) * 1000
            if gap_ms > 500:
                self.stalls += 1
                logger.warning("[%s] gap of %.0fms between audio chunks", self.session_id, gap_ms)
        self.last_chunk_at = now
        self.chunk_count += 1
        self.total_bytes += size

    def summary(self) -> str:
        elapsed = time.monotonic() - self.started_at
        bytes_per_second = AUDIO_SAMPLE_RATE * AUDIO_CHANNELS * AUDIO_SAMPLE_WIDTH_BYTES
        audio_seconds = self.total_bytes / bytes_per_second if bytes_per_second else 0
        return (
            f"session={self.session_id} lang={self.source_language} "
            f"chunks={self.chunk_count} bytes={self.total_bytes} "
            f"audio_duration={audio_seconds:.2f}s wall_duration={elapsed:.2f}s stalls={self.stalls}"
        )


@router.websocket("/ws/translate")
async def translate_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    session_id = uuid.uuid4().hex[:8]
    stats: AudioSessionStats | None = None
    wav_writer: wave.Wave_write | None = None
    provider: FasterWhisperProvider | None = None
    send_lock = asyncio.Lock()

    async def safe_send(payload: dict) -> None:
        async with send_lock:
            try:
                await websocket.send_json(payload)
            except Exception:
                pass  # connection may already be closing

    translator = NLLBTranslationProvider(
        websocket.app.state.nllb_model,
        websocket.app.state.nllb_tokenizer,
        websocket.app.state.nllb_device,
        websocket.app.state.nllb_executor,
    )

    async def handle_stt_error(message: str) -> None:
        # Non-fatal — see SpeechToTextProvider.on_error docstring. Just visibility.
        await safe_send({"type": "error", "code": "STT_ERROR", "message": message})

    async def handle_transcript(result: TranscriptResult) -> None:
        await safe_send(
            {
                "type": "transcript",
                "segmentId": result.segment_id,
                "text": result.text,
                "language": result.language,
                "final": result.is_final,
                "ts": time.time(),
            }
        )

        if not result.is_final:
            return

        # Only finalized segments are translated — partials are about to be
        # replaced anyway, so translating them would just waste CPU (section 6/8).
        await safe_send({"type": "status", "status": "translating"})
        translate_started_at = time.monotonic()
        try:
            translated = await translator.translate(result.text, result.language)
        except Exception:
            logger.exception("[%s] translation failed", result.segment_id)
            await safe_send(
                {"type": "error", "code": "TRANSLATION_ERROR", "message": "Translation failed for this segment."}
            )
            return
        translate_latency_ms = (time.monotonic() - translate_started_at) * 1000
        logger.info("[%s] translate_latency=%.0fms translated=%r", result.segment_id, translate_latency_ms, translated)

        await safe_send(
            {
                "type": "subtitle",
                "segmentId": result.segment_id,
                "original": result.text,
                "translated": translated,
                "final": True,
                "ts": time.time(),
            }
        )
        await safe_send({"type": "status", "status": "listening"})

    try:
        first_message = await websocket.receive_json()
        start = parse_client_message(first_message)
        if not isinstance(start, ClientStart):
            await safe_send({"type": "error", "code": "PROTOCOL_ERROR", "message": "Expected 'start' as the first message."})
            await websocket.close(code=1002)
            return

        stats = AudioSessionStats(session_id, start.sourceLanguage)
        logger.info("[%s] start sourceLanguage=%s", session_id, start.sourceLanguage)

        if SAVE_DEBUG_AUDIO:
            Path(DEBUG_AUDIO_DIR).mkdir(parents=True, exist_ok=True)
            wav_path = Path(DEBUG_AUDIO_DIR) / f"{session_id}.wav"
            wav_writer = wave.open(str(wav_path), "wb")
            wav_writer.setnchannels(AUDIO_CHANNELS)
            wav_writer.setsampwidth(AUDIO_SAMPLE_WIDTH_BYTES)
            wav_writer.setframerate(AUDIO_SAMPLE_RATE)
            logger.info("[%s] saving debug audio to %s", session_id, wav_path)

        provider = FasterWhisperProvider(
            websocket.app.state.whisper_model,
            websocket.app.state.whisper_executor,
            websocket.app.state.vad_executor,
        )
        provider.on_transcript(handle_transcript)
        provider.on_error(handle_stt_error)
        await provider.start(start.sourceLanguage)

        await safe_send({"type": "ready"})
        await safe_send({"type": "status", "status": "listening"})

        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            if message.get("bytes") is not None:
                chunk: bytes = message["bytes"]
                stats.record_chunk(len(chunk))
                if wav_writer is not None:
                    wav_writer.writeframes(chunk)
                provider.send_audio(chunk)
                continue

            if message.get("text") is not None:
                payload = json.loads(message["text"])
                control = parse_client_message(payload)
                if control.type == "stop":
                    logger.info("[%s] stop received: %s", session_id, stats.summary())
                    break

    except WebSocketDisconnect:
        logger.info("[%s] client disconnected", session_id)
    except Exception as exc:  # noqa: BLE001 — POC-level catch-all so one bad frame doesn't kill the server
        logger.exception("[%s] error", session_id)
        await safe_send({"type": "error", "code": "SERVER_ERROR", "message": str(exc)})
    finally:
        # Guarded individually so a failure in one cleanup step (e.g. a final
        # transcribe pass erroring inside provider.stop()) can't skip the rest —
        # closing the wav file and logging the session summary should still
        # happen regardless.
        if provider is not None:
            try:
                await provider.stop()
            except Exception:
                logger.exception("[%s] error while stopping provider", session_id)
        if wav_writer is not None:
            wav_writer.close()
        if stats is not None:
            logger.info("[%s] session summary: %s", session_id, stats.summary())
