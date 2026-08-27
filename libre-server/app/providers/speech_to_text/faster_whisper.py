"""faster-whisper implementation of SpeechToTextProvider.

Whisper isn't a streaming model — it transcribes whatever buffer you hand it.
The streaming behaviour here is a sliding-window scheme (requirement.md
section 14): accumulate audio, periodically re-transcribe the buffer with
Whisper's built-in Silero VAD, and treat trailing silence as a cue to
"finalize" everything up to the last detected speech and start a fresh
buffer. If speech runs on for too long without a pause, the buffer is
force-finalized instead of growing unbounded (bounds both re-transcription
cost and worst-case latency).

Two additions on top of that base scheme (segment-improvement.md, "frame-level
VAD + bounded window" pass):

1. A cheap standalone VAD probe (`faster_whisper.vad.get_speech_timestamps`,
   just the small Silero ONNX model — not the Whisper encoder/decoder) runs on
   every incoming audio chunk, decoupled from the expensive transcribe cadence
   below. When it detects trailing silence, it triggers an early full-buffer
   check immediately instead of waiting for the next scheduled tick — this is
   the main latency win, since finalize-detection used to be bottlenecked on
   the same cadence as everything else. Guarded to fire at most once per
   detected-silence episode (`_silence_check_fired`) so a false-positive probe
   reading can't retry every ~200ms — the same class of runaway-retry bug
   already fixed once below for `force_final`.
2. Passes that aren't expected to finalize (no VAD-detected silence, buffer
   still well under the max) are windowed to the last
   WHISPER_INCREMENTAL_WINDOW_SECONDS of the buffer instead of the whole
   growing buffer — caps the worst-case re-transcription cost that used to
   grow toward the 5-8s finalize ceiling. Passes expected to finalize
   (`force_final`, the VAD-probe-triggered early check, and `final_flush`)
   still see the full buffer, unwindowed, preserving the existing word-safety-
   margin/hard-ceiling logic exactly and keeping single-pass coherence for
   whatever text actually gets shown as final.

This is a POC implementation, not the section-33 benchmarking result — window/
trigger constants live in app.config.settings and are meant to be tuned once
real latency numbers are in.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import numpy as np
from faster_whisper import WhisperModel
from faster_whisper.vad import VadOptions, get_speech_timestamps

from app.config.settings import (
    AUDIO_SAMPLE_RATE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_HARD_MAX_BUFFER_SECONDS,
    WHISPER_INCREMENTAL_WINDOW_SECONDS,
    WHISPER_INITIAL_PROMPT,
    WHISPER_MAX_BUFFER_SECONDS,
    WHISPER_MODEL_SIZE,
    WHISPER_NO_REPEAT_NGRAM_SIZE,
    WHISPER_NO_SPEECH_PROB_THRESHOLD,
    WHISPER_SILENCE_FINALIZE_SECONDS,
    WHISPER_TRIGGER_SECONDS,
    WHISPER_VAD_PROBE_WINDOW_SECONDS,
    WHISPER_WORD_SAFETY_MARGIN_SECONDS,
)
from app.providers.speech_to_text.base import ErrorCallback, SpeechToTextProvider, TranscriptCallback, TranscriptResult

logger = logging.getLogger("faster_whisper_provider")

BYTES_PER_SAMPLE = 2
TRIGGER_BYTES = int(WHISPER_TRIGGER_SECONDS * AUDIO_SAMPLE_RATE) * BYTES_PER_SAMPLE
MAX_BUFFER_BYTES = int(WHISPER_MAX_BUFFER_SECONDS * AUDIO_SAMPLE_RATE) * BYTES_PER_SAMPLE
INCREMENTAL_WINDOW_BYTES = int(WHISPER_INCREMENTAL_WINDOW_SECONDS * AUDIO_SAMPLE_RATE) * BYTES_PER_SAMPLE
VAD_PROBE_WINDOW_BYTES = int(WHISPER_VAD_PROBE_WINDOW_SECONDS * AUDIO_SAMPLE_RATE) * BYTES_PER_SAMPLE

# Options for the cheap standalone probe — reuses WHISPER_SILENCE_FINALIZE_SECONDS
# as the min-silence-duration so there's one source of truth for "how much
# trailing silence means a pause," shared with _transcribe_sync's own
# (Whisper-internal-VAD-based) silence_final check below. The probe's job is
# only to decide *when to bother checking early*, not to make the actual
# finalize decision — that's still made by _transcribe_sync against the real
# model output, unchanged.
_PROBE_VAD_OPTIONS = VadOptions(min_silence_duration_ms=int(WHISPER_SILENCE_FINALIZE_SECONDS * 1000))

# Found via a reproduced hallucination on near-silent trailing audio: Whisper
# transcribed a 1.1s tail as ". ." (no actual words), and NLLB then hallucinated
# its own unrelated content ("I don't know... I don't know...") translating
# that degenerate input. \w is Unicode-aware in Python (matches CJK/Vietnamese
# too), so this is a language-agnostic "is there anything actually worth
# translating here" check.
_HAS_WORD_CHAR_RE = re.compile(r"\w", re.UNICODE)


def resolve_device_and_compute_type() -> tuple[str, str]:
    device = WHISPER_DEVICE
    if device == "auto":
        try:
            import ctranslate2

            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    compute_type = WHISPER_COMPUTE_TYPE or ("float16" if device == "cuda" else "int8")
    return device, compute_type


def load_model() -> tuple[WhisperModel, str, str]:
    """Loaded once at server startup and shared across all sessions (section 25)."""
    device, compute_type = resolve_device_and_compute_type()
    try:
        model = WhisperModel(WHISPER_MODEL_SIZE, device=device, compute_type=compute_type)
    except Exception:
        logger.exception("Failed to load Whisper on device=%s, falling back to CPU/int8", device)
        device, compute_type = "cpu", "int8"
        model = WhisperModel(WHISPER_MODEL_SIZE, device=device, compute_type=compute_type)
    logger.info("Loaded faster-whisper model=%s device=%s compute_type=%s", WHISPER_MODEL_SIZE, device, compute_type)
    return model, device, compute_type


def pcm16_bytes_to_float32(raw: bytes) -> np.ndarray:
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


class FasterWhisperProvider(SpeechToTextProvider):
    def __init__(self, model: WhisperModel, executor: ThreadPoolExecutor, vad_executor: ThreadPoolExecutor):
        self._model = model
        self._executor = executor
        # Separate, lightweight executor for the cheap VAD-only probe — must
        # not share a thread with `executor`, or a probe would just queue
        # behind an in-flight (expensive) transcribe pass and lose the point
        # of being cheap and frequent.
        self._vad_executor = vad_executor
        self._language: Optional[str] = None
        self._buffer = bytearray()
        self._bytes_since_last_run = 0
        self._lock = asyncio.Lock()
        self._segment_id = uuid.uuid4().hex[:8]
        self._callback: Optional[TranscriptCallback] = None
        self._error_callback: Optional[ErrorCallback] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._vad_probe_in_flight = False
        # True once an early VAD-triggered check has been fired for the
        # *current* stretch of detected trailing silence — reset back to
        # False as soon as the probe sees speech again (a new episode) or a
        # pass actually finalizes. Without this, a probe false-positive would
        # retry every ~200ms instead of falling back to the normal cadence.
        self._silence_check_fired = False

    def on_transcript(self, callback: TranscriptCallback) -> None:
        self._callback = callback

    def on_error(self, callback: ErrorCallback) -> None:
        self._error_callback = callback

    async def start(self, language: str) -> None:
        self._language = language
        self._buffer.clear()
        self._bytes_since_last_run = 0
        self._segment_id = uuid.uuid4().hex[:8]
        self._loop = asyncio.get_running_loop()
        self._vad_probe_in_flight = False
        self._silence_check_fired = False

    def send_audio(self, chunk: bytes) -> None:
        self._buffer.extend(chunk)
        self._bytes_since_last_run += len(chunk)

        if not self._loop:
            return

        # Cheap, frequent check (runs on ~every incoming chunk, ~200ms) —
        # decoupled from the expensive cadence below, so a natural pause can
        # trigger a finalize check immediately instead of waiting up to
        # WHISPER_TRIGGER_SECONDS for the next scheduled tick.
        if not self._vad_probe_in_flight and not self._lock.locked():
            self._vad_probe_in_flight = True
            self._loop.create_task(self._check_vad_probe())

        # Bug found via user report of translation stalling: force_final can now
        # come back with is_final=False (no safe word boundary yet — see
        # _transcribe_sync), which leaves the buffer over MAX_BUFFER_BYTES
        # afterward. `over_max` used to also be a trigger condition on its own,
        # which meant every subsequent chunk (every ~200ms, not the normal ~1s
        # cadence) would immediately retry — fine when force_final always
        # cleared the buffer in one shot (the old behavior), but a runaway
        # re-transcription loop now that it doesn't always. Triggering is still
        # driven only by this normal cadence; force_final is still computed
        # fresh each time from the current buffer size. Passes that aren't
        # over_max are windowed (see _run_pass) instead of seeing the whole
        # growing buffer.
        if not self._lock.locked() and self._bytes_since_last_run >= TRIGGER_BYTES:
            self._bytes_since_last_run = 0
            over_max = len(self._buffer) >= MAX_BUFFER_BYTES
            self._loop.create_task(self._run_pass(force_final=over_max, windowed=not over_max))

    async def _check_vad_probe(self) -> None:
        try:
            tail = bytes(self._buffer[-VAD_PROBE_WINDOW_BYTES:])
            if not tail or self._lock.locked():
                return
            audio = pcm16_bytes_to_float32(tail)
            speeches = await self._loop.run_in_executor(self._vad_executor, self._vad_probe_sync, audio)

            if not speeches:
                # Nothing detected in the probe window at all — not a "speech
                # just ended" episode, just ongoing silence/nothing yet.
                self._silence_check_fired = False
                return

            audio_duration = len(audio) / AUDIO_SAMPLE_RATE
            trailing_silence = audio_duration - (speeches[-1]["end"] / AUDIO_SAMPLE_RATE)

            if trailing_silence < WHISPER_SILENCE_FINALIZE_SECONDS:
                # Still speaking (or not enough of a pause yet) — re-arm for
                # the next time trailing silence actually appears.
                self._silence_check_fired = False
                return

            if self._silence_check_fired or self._lock.locked():
                return

            self._silence_check_fired = True
            self._bytes_since_last_run = 0
            # force_final=False deliberately — the probe only decides *when*
            # to check early; the actual finalize decision is still made by
            # _transcribe_sync against the real (more accurate) Whisper VAD
            # output, unchanged from before this feature existed.
            self._loop.create_task(self._run_pass(force_final=False, windowed=False))
        finally:
            self._vad_probe_in_flight = False

    def _vad_probe_sync(self, audio: np.ndarray) -> List[dict]:
        return get_speech_timestamps(audio, _PROBE_VAD_OPTIONS)

    async def _run_pass(self, force_final: bool, windowed: bool, final_flush: bool = False) -> None:
        # A lock (not a plain busy flag) so stop() can wait for an in-flight pass to
        # finish instead of silently skipping the final flush if one is running.
        async with self._lock:
            if not self._buffer:
                return

            started_at = time.monotonic()
            # Passes not expected to finalize get windowed to the last
            # WHISPER_INCREMENTAL_WINDOW_SECONDS instead of the whole growing
            # buffer. Any sample offset _transcribe_sync returns is relative
            # to whatever audio it was given — window_offset_samples corrects
            # that back to a full-buffer-relative offset before trimming, so
            # a windowed pass that unexpectedly *does* finalize (the existing
            # multi-segment "settled" chunking can still do this) still trims
            # self._buffer at the right position instead of corrupting it.
            if windowed and len(self._buffer) > INCREMENTAL_WINDOW_BYTES:
                window_offset_bytes = len(self._buffer) - INCREMENTAL_WINDOW_BYTES
                audio_bytes = bytes(self._buffer[window_offset_bytes:])
            else:
                window_offset_bytes = 0
                audio_bytes = bytes(self._buffer)
            window_offset_samples = window_offset_bytes // BYTES_PER_SAMPLE

            audio = pcm16_bytes_to_float32(audio_bytes)
            try:
                text, is_final, finalize_at_samples_in_window = await self._loop.run_in_executor(
                    self._executor, self._transcribe_sync, audio, force_final, final_flush
                )
            except Exception as exc:
                logger.exception("[%s] transcription failed", self._segment_id)
                if self._error_callback:
                    await self._error_callback(f"Speech recognition failed for one segment: {exc}")
                return

            if window_offset_samples > 0 and is_final:
                # Found via direct testing: a windowed pass's own leading edge
                # can land mid-word (e.g. "itself" -> "self depends..."), the
                # same class of bug WHISPER_WORD_SAFETY_MARGIN_SECONDS already
                # guards against at the *trailing* edge — but nothing protects
                # the *leading* edge of a bounded window, and none of
                # _transcribe_sync's finalize paths (silence_final, the
                # multi-segment "settled" chunking) were written expecting to
                # see anything but a full-buffer-relative start. Rather than
                # add leading-edge word-safety logic too, simplest and safest:
                # a pass that actually cut off the front of the buffer (i.e.
                # genuinely windowed, not just "buffer happened to be shorter
                # than the window") never finalizes — only full-buffer passes
                # (force_final / the VAD-probe-triggered early check /
                # final_flush) commit a final result, exactly as before this
                # feature existed. Downgraded to a preview-only partial; the
                # next full-buffer pass will produce the correct complete text.
                is_final = False

            latency_ms = (time.monotonic() - started_at) * 1000
            logger.info(
                "[%s] stt_latency=%.0fms buffer=%.2fs windowed=%s final=%s text=%r",
                self._segment_id,
                latency_ms,
                len(audio) / AUDIO_SAMPLE_RATE,
                windowed and window_offset_samples > 0,
                is_final,
                text[:80],
            )

            if text and not _HAS_WORD_CHAR_RE.search(text):
                logger.info("[%s] dropping no-word-content result (likely hallucination): %r", self._segment_id, text)
                text = ""

            if text and self._callback:
                # Awaited directly (not fire-and-forget) so the send actually completes
                # before this returns — the caller may be about to close the connection
                # right after (e.g. stop()), which would otherwise race a scheduled-but-
                # not-yet-run send task and silently drop the message.
                await self._callback(
                    TranscriptResult(
                        text=text,
                        language=self._language or "en",
                        is_final=is_final,
                        segment_id=self._segment_id,
                    )
                )

            if is_final:
                finalize_at_samples = finalize_at_samples_in_window + window_offset_samples
                finalize_at_bytes = finalize_at_samples * BYTES_PER_SAMPLE
                del self._buffer[:finalize_at_bytes]
                self._segment_id = uuid.uuid4().hex[:8]
                self._silence_check_fired = False

    def _transcribe_sync(self, audio: np.ndarray, force_final: bool, final_flush: bool = False) -> tuple[str, bool, int]:
        segments_iter, _info = self._model.transcribe(
            audio,
            language=self._language,
            task="transcribe",
            vad_filter=True,
            beam_size=1,
            word_timestamps=True,
            initial_prompt=WHISPER_INITIAL_PROMPT or None,
            no_repeat_ngram_size=WHISPER_NO_REPEAT_NGRAM_SIZE,
        )
        segments = list(segments_iter)

        dropped = [s for s in segments if s.no_speech_prob >= WHISPER_NO_SPEECH_PROB_THRESHOLD]
        if dropped:
            logger.info(
                "[%s] dropping %d low-confidence segment(s) (no_speech_prob >= %.2f, likely hallucination): %r",
                self._segment_id,
                len(dropped),
                WHISPER_NO_SPEECH_PROB_THRESHOLD,
                [s.text for s in dropped],
            )
        segments = [s for s in segments if s.no_speech_prob < WHISPER_NO_SPEECH_PROB_THRESHOLD]

        text = " ".join(s.text.strip() for s in segments).strip()
        audio_duration = len(audio) / AUDIO_SAMPLE_RATE

        if final_flush:
            # Session ending (stop()) — no more audio is coming, so flush
            # everything regardless of word-safety. Keeping a possibly-
            # imperfect trailing word beats silently dropping the tail of
            # the session.
            return text, True, int(audio_duration * AUDIO_SAMPLE_RATE)

        if not segments:
            # No speech at all in this buffer (pure silence). Nothing worth
            # keeping — clear it all whenever we finalize at all.
            is_final = force_final or audio_duration >= WHISPER_SILENCE_FINALIZE_SECONDS
            return text, is_final, int(audio_duration * AUDIO_SAMPLE_RATE) if is_final else 0

        last_speech_end = segments[-1].end
        trailing_silence = audio_duration - last_speech_end
        silence_final = trailing_silence >= WHISPER_SILENCE_FINALIZE_SECONDS

        if silence_final:
            # A real pause was found — segment already stopped short of the
            # buffer edge, so this is an established, safe boundary.
            return text, True, int(last_speech_end * AUDIO_SAMPLE_RATE)

        if len(segments) >= 2:
            # Mid-utterance chunking: Whisper has already moved on to a new
            # segment, so everything before the last one is settled — it won't
            # be revised further by seeing more audio. Flush it now instead of
            # waiting for the whole utterance to go quiet, so a long sentence
            # with no pauses gets translated in pieces as it's spoken rather
            # than as one big chunk at the end. Trade-off: translating a
            # settled clause alone (without the sentence that follows it) can
            # read slightly less natural in Vietnamese — accepted deliberately
            # for lower latency.
            settled = segments[:-1]
            settled_text = " ".join(s.text.strip() for s in settled).strip()
            if settled_text:
                return settled_text, True, int(settled[-1].end * AUDIO_SAMPLE_RATE)

        if force_final:
            # One continuous segment, no natural break, and the max-buffer
            # timeout hit mid-session. Cutting at the raw buffer edge (or even
            # at the segment's own reported end) here is unsafe — verified
            # directly: for ongoing speech with no gap, Whisper's segment/word
            # end estimate for whatever it's currently hearing lands right at
            # the buffer edge, which can be mid-word (a 4.0s cutoff once
            # landed inside "React", produced a dangling "re-" fragment, and
            # translation silently dropped it — an actual word lost, not just
            # an awkward split). Only trust a word as finished if there's
            # already a safety margin of trailing audio after it that Whisper
            # chose not to attribute to a new word.
            words = [w for s in segments for w in (s.words or [])]
            safe_words = [w for w in words if (audio_duration - w.end) >= WHISPER_WORD_SAFETY_MARGIN_SECONDS]
            if safe_words:
                safe_text = "".join(w.word for w in safe_words).strip()
                if safe_text:
                    return safe_text, True, int(safe_words[-1].end * AUDIO_SAMPLE_RATE)

            if audio_duration >= WHISPER_HARD_MAX_BUFFER_SECONDS:
                # No safe word has appeared even after growing well past the
                # soft cutoff — found necessary from a real report of
                # translation never starting at all: fast/continuous real
                # speech (unlike the clean test sentence that validated the
                # soft cutoff) can keep the last word suspiciously close to
                # the buffer edge on every pass, since the edge keeps growing
                # right along with the audio, so waiting for a safe word can
                # never resolve. Accept the mid-word-cut risk here rather
                # than hang forever — this is the fallback of last resort,
                # not the common case.
                logger.warning(
                    "[%s] hit hard max buffer (%.1fs) with no safe word boundary — force-clearing",
                    self._segment_id,
                    audio_duration,
                )
                return text, True, int(audio_duration * AUDIO_SAMPLE_RATE)

            # No safe word yet — don't cut mid-word. send_audio's over_max
            # check keeps retrying force_final on subsequent passes with more
            # audio, typically resolving within one more trigger interval
            # once the in-progress word finishes.
            return text, False, 0

        return text, False, 0

    async def stop(self) -> None:
        if self._loop:
            # Waits for any in-flight pass (via the lock) before doing the final flush.
            await self._run_pass(force_final=True, windowed=False, final_flush=True)
        self._buffer.clear()
