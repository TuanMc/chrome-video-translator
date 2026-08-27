"""audio -> Soniox (STT+translation combined) -> transcript/subtitle, streamed
back over WS.

Unlike nllb-server/libre-server, there's no local sliding-window buffering
or a separate translate-HTTP-call step here: Soniox's own server-side pause
detection ("endpoint detection") decides segment boundaries and emits a
sentinel "<end>" token (see app/providers/soniox_client.py), and translation
tokens stream in alongside transcription tokens on the same connection. This
handler's job is just relaying audio in, and re-shaping Soniox's token
stream into this project's existing transcript/subtitle protocol.

Audio is still optionally saved to .wav for debugging (see
app.config.settings.SAVE_DEBUG_AUDIO) — note it's also sent to Soniox's
cloud API regardless of this setting; see README.md.
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
    SONIOX_FINISH_TIMEOUT_SECONDS,
)
from app.models.protocol import ClientStart, parse_client_message
from app.providers.soniox_client import SonioxClient

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
    client: SonioxClient | None = None
    receive_task: asyncio.Task | None = None
    send_lock = asyncio.Lock()

    source_language = "en"
    # Per-segment accumulators. A "segment" here is bounded by Soniox's own
    # endpoint detection (the "<end>" sentinel token), not by any local
    # buffering logic — see soniox_client.py.
    segment_id = uuid.uuid4().hex[:8]
    original_final = ""
    original_draft = ""
    translated_final = ""
    translated_draft = ""

    async def safe_send(payload: dict) -> None:
        async with send_lock:
            try:
                await websocket.send_json(payload)
            except Exception:
                pass  # connection may already be closing

    async def emit_partial_transcript() -> None:
        await safe_send(
            {
                "type": "transcript",
                "segmentId": segment_id,
                "text": original_final + original_draft,
                "language": source_language,
                "final": False,
                "ts": time.time(),
            }
        )

    async def finalize_segment() -> None:
        nonlocal segment_id, original_final, original_draft, translated_final, translated_draft
        if not original_final and not translated_final:
            # Nothing accumulated (e.g. an "<end>" on an already-empty
            # buffer, or cleanup running after a normal finalize already
            # reset everything) — just mint a fresh segment id and return.
            segment_id = uuid.uuid4().hex[:8]
            original_draft = ""
            translated_draft = ""
            return

        await safe_send(
            {
                "type": "transcript",
                "segmentId": segment_id,
                "text": original_final,
                "language": source_language,
                "final": True,
                "ts": time.time(),
            }
        )
        await safe_send(
            {
                "type": "subtitle",
                "segmentId": segment_id,
                "original": original_final,
                "translated": translated_final,
                "final": True,
                "ts": time.time(),
            }
        )

        segment_id = uuid.uuid4().hex[:8]
        original_final = ""
        original_draft = ""
        translated_final = ""
        translated_draft = ""

    async def consume_soniox_events() -> None:
        nonlocal original_final, original_draft, translated_final, translated_draft
        assert client is not None
        try:
            async for event in client.receive():
                if event.error:
                    logger.warning("[%s] soniox error: %s", session_id, event.error)
                    await safe_send({"type": "error", "code": "STT_ERROR", "message": event.error})
                    # 401/403 (verified directly: 401 for a bad api_key) is a
                    # configuration problem that will never resolve itself —
                    # unlike a single failed STT pass (see the on_error
                    # docstring in libre-server's base.py, "the next
                    # scheduled pass retries"), there is no next pass here to
                    # retry: Soniox has already closed its side. Close
                    # proactively instead of leaving the client waiting on a
                    # session that can only ever error again on its next
                    # audio chunk.
                    if event.error_code in (401, 403):
                        logger.error("[%s] fatal Soniox auth error (code=%s) — closing session", session_id, event.error_code)
                        try:
                            await websocket.close(code=1011)
                        except Exception:
                            pass
                        break
                    continue

                changed = False
                if event.original_final_delta:
                    original_final += event.original_final_delta
                    changed = True
                if event.translated_final_delta:
                    translated_final += event.translated_final_delta
                if event.original_draft != original_draft:
                    original_draft = event.original_draft
                    changed = True
                translated_draft = event.translated_draft

                if changed:
                    await emit_partial_transcript()

                if event.is_end:
                    await safe_send({"type": "status", "status": "translating"})
                    await finalize_segment()
                    await safe_send({"type": "status", "status": "listening"})

                if event.finished:
                    break
        except Exception:
            logger.exception("[%s] error consuming soniox events", session_id)

    try:
        first_message = await websocket.receive_json()
        start = parse_client_message(first_message)
        if not isinstance(start, ClientStart):
            await safe_send({"type": "error", "code": "PROTOCOL_ERROR", "message": "Expected 'start' as the first message."})
            await websocket.close(code=1002)
            return

        source_language = start.sourceLanguage
        stats = AudioSessionStats(session_id, source_language)
        logger.info("[%s] start sourceLanguage=%s", session_id, source_language)

        if SAVE_DEBUG_AUDIO:
            Path(DEBUG_AUDIO_DIR).mkdir(parents=True, exist_ok=True)
            wav_path = Path(DEBUG_AUDIO_DIR) / f"{session_id}.wav"
            wav_writer = wave.open(str(wav_path), "wb")
            wav_writer.setnchannels(AUDIO_CHANNELS)
            wav_writer.setsampwidth(AUDIO_SAMPLE_WIDTH_BYTES)
            wav_writer.setframerate(AUDIO_SAMPLE_RATE)
            logger.info("[%s] saving debug audio to %s", session_id, wav_path)

        client = SonioxClient(source_language)
        try:
            await client.connect()
        except Exception as exc:
            logger.exception("[%s] failed to connect to Soniox", session_id)
            await safe_send({"type": "error", "code": "STT_ERROR", "message": f"Could not connect to Soniox: {exc}"})
            await websocket.close(code=1011)
            return

        receive_task = asyncio.create_task(consume_soniox_events())

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
                await client.send_audio(chunk)
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
        # Guarded individually so a failure in one cleanup step can't skip
        # the rest — signaling end-of-audio, waiting for Soniox to wrap up,
        # flushing any trailing unfinalized segment, closing the wav file,
        # and logging the session summary should all still happen.
        if client is not None:
            try:
                await client.end_audio()
            except Exception:
                logger.exception("[%s] error signaling end-of-audio to soniox", session_id)
            if receive_task is not None:
                try:
                    await asyncio.wait_for(receive_task, timeout=SONIOX_FINISH_TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    logger.warning("[%s] timed out waiting for soniox to finish", session_id)
                    receive_task.cancel()
                except Exception:
                    logger.exception("[%s] error while waiting for soniox receive task", session_id)
            try:
                # Flushes anything left over if the session ended before
                # Soniox's own endpoint detection fired for the last segment.
                await finalize_segment()
            except Exception:
                logger.exception("[%s] error flushing final segment", session_id)
            try:
                await client.close()
            except Exception:
                logger.exception("[%s] error closing soniox connection", session_id)
        if wav_writer is not None:
            wav_writer.close()
        if stats is not None:
            logger.info("[%s] session summary: %s", session_id, stats.summary())
