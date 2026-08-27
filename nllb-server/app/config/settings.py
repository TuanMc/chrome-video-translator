import os

# Host/port aren't config here — they're passed directly as `uvicorn` CLI flags
# (see server/README.md) and must match extension/src/constants/index.ts's
# LOCAL_SERVER_ORIGIN and manifest.json's host_permissions if ever changed.

# Fixed audio contract with the extension (see requirement.md section 13/16).
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_SAMPLE_WIDTH_BYTES = 2  # PCM16

# Off by default — this project is local-first/privacy-friendly by design
# (requirement.md section 29: do not persist captured audio unless explicitly
# required). Opt in with SAVE_DEBUG_AUDIO=true only when you specifically want
# to verify the capture/transport pipeline by listening back to a session.
SAVE_DEBUG_AUDIO = os.environ.get("SAVE_DEBUG_AUDIO", "false").lower() == "true"
DEBUG_AUDIO_DIR = os.environ.get("DEBUG_AUDIO_DIR", "tmp_recordings")

# --- faster-whisper (see requirement.md section 8, 26) ---

# POC3 benchmark (CPU-only, 8-core i5-1135G7, synthetic TTS samples — see
# server/README.md "POC3 benchmark results" for the full numbers and caveats):
# tiny ~380-420ms/pass but noticeably mangles EN/JA/ZH technical terms; small
# ~1.5-2.6s/pass, best accuracy but that alone risks blowing the "near real-time"
# feel once translation (POC4) stacks on top; base ~550-650ms/pass with a good
# accuracy/latency balance. "base" is a POC3-informed default, not a final
# decision — real speech (not clean TTS) and real end-user hardware may differ.
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "base")

# auto | cpu | cuda — "auto" tries CUDA and falls back to CPU if unavailable/fails.
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "auto")

# Empty = auto-pick (int8 on CPU, float16 on CUDA).
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "")

# Sliding-window streaming tuning (see requirement.md section 14).
# Governs only the *incremental* (windowed, not-expected-to-finalize) pass
# cadence now — was previously also the only thing gating finalize checks,
# but that's now driven earlier/independently by the cheap VAD probe (see
# WHISPER_VAD_PROBE_WINDOW_SECONDS below and faster_whisper.py's
# _check_vad_probe). Lowered from 1.0 to 0.7 (segment-improvement.md's
# suggested 600-800ms) now that finalize-latency no longer rides on this same
# cadence, so tightening it further is lower-risk than it used to be.
WHISPER_TRIGGER_SECONDS = float(os.environ.get("WHISPER_TRIGGER_SECONDS", "0.7"))
# Was 0.7. Lowered for the "subtitle within 1s of speech ending" target — this
# wait is pure dead time added before a finalize-eligible pass even runs, so
# it's the cheapest thing to cut. Real risk: a brief natural pause *within* a
# sentence (a breath, a comma) could now get finalized as if it were the
# sentence's end, splitting translation context earlier than really wanted —
# same class of trade-off already accepted for chunking, just tuned further.
WHISPER_SILENCE_FINALIZE_SECONDS = float(os.environ.get("WHISPER_SILENCE_FINALIZE_SECONDS", "0.4"))
# Bound for passes not expected to finalize (segment-improvement.md's
# "bounded sliding window" ask) — caps re-transcription cost that used to
# grow toward the 5-8s finalize ceiling on every ~0.7-1s tick. Passes that
# *are* expected to finalize (force_final, the VAD-probe-triggered early
# check, final_flush) still see the full buffer — this only bounds the
# cheap, frequent, not-yet-finalizing checks in between. 4.0s comfortably
# contains WHISPER_SILENCE_FINALIZE_SECONDS (trailing-silence detection) and
# slides forward every ~0.7s, so a multi-segment "settled" clause boundary
# is always visible well before it could age out of the window.
WHISPER_INCREMENTAL_WINDOW_SECONDS = float(os.environ.get("WHISPER_INCREMENTAL_WINDOW_SECONDS", "4.0"))
# How much trailing buffer the cheap standalone VAD probe inspects each time
# (faster_whisper.vad.get_speech_timestamps — just the small Silero ONNX
# model, not a Whisper decode). Needs to comfortably exceed
# WHISPER_SILENCE_FINALIZE_SECONDS with margin for the probe to reliably see
# a full pause; kept small since this runs on ~every incoming audio chunk
# (~200ms) and must stay cheap. Measured directly on this CPU with real
# (gTTS-generated) speech, not synthetic noise: 3.5ms avg per probe call on
# a 2s tail vs. 534ms avg per full transcribe() pass on a ~7s real-speech
# clip — a 152x difference, confirming this is safe to run far more
# often than a full pass.
WHISPER_VAD_PROBE_WINDOW_SECONDS = float(os.environ.get("WHISPER_VAD_PROBE_WINDOW_SECONDS", "2.0"))
# Was 15.0, then lowered to 4.0 to prioritize speed. Verified Whisper does NOT
# naturally split a continuous, pause-free sentence into multiple segments at
# any intermediate buffer size — it reports one growing segment the whole way.
# So for speech with no natural pause, this max-buffer cutoff is the *only*
# thing that finalizes (and therefore triggers translation for) a chunk
# before the sentence fully ends — trading translation naturalness (a chunk
# cut before its sentence completes reads a little less fluent in Vietnamese)
# for lower latency. Nudged back up to 5.0 after NLLB quantization (see
# NLLB_QUANTIZE_CPU) freed up real latency budget (translation dropped ~2.5x)
# — reinvesting some of that into fuller, more natural chunks while still
# staying far below the original 15s. This is the balance knob if you want to
# lean further either way: lower for more speed, higher for more complete
# sentences.
WHISPER_MAX_BUFFER_SECONDS = float(os.environ.get("WHISPER_MAX_BUFFER_SECONDS", "5.0"))
# When force-finalizing continuous speech with no natural pause, only trust a
# word as "finished" if it ended at least this long before the buffer's raw
# edge — otherwise a word Whisper hasn't fully heard yet can get cut mid-word
# and silently dropped by translation. Verified directly: without this, a 4s
# cutoff landed inside "React" and the word was lost entirely, not just split.
WHISPER_WORD_SAFETY_MARGIN_SECONDS = float(os.environ.get("WHISPER_WORD_SAFETY_MARGIN_SECONDS", "0.3"))
# Hard ceiling, found necessary from a user report of translation never
# starting at all: the word-safety check above holds off finalizing until a
# word has a safe trailing margin — fine for speech with brief natural gaps,
# but real fast/continuous talking (much more common in real video content
# than the clean single-sentence test that validated the soft cutoff) can
# keep the last recognized word suspiciously close to the buffer edge on
# every single pass, since the buffer edge itself keeps growing right along
# with the audio. Without a hard ceiling that never resolves — the buffer
# grows forever, STT never finalizes anything, translation never triggers.
# At this point, accept the mid-word-cut risk and force-clear everything.
WHISPER_HARD_MAX_BUFFER_SECONDS = float(os.environ.get("WHISPER_HARD_MAX_BUFFER_SECONDS", "8.0"))
# Biases recognition toward this vocabulary — attacks a real root cause of
# meaning loss found in testing: Whisper transliterating "TypeScript"/"Docker"
# into JA/ZH phonetic renderings that NLLB then can't recognize as the terms
# they are. Measured directly (JA): fixed "TypeScript"/"Docker" to stay in
# Latin script; "React" specifically stayed transliterated regardless of
# prompt wording tried (a strong learned loanword pattern, apparently
# resistant to prompt biasing). Measured (ZH): meaningfully improved both
# terms. Checked for the obvious risk — hallucinating these words into
# unrelated non-technical speech — and found none on synthetic non-technical
# EN/JA test sentences. Latency cost: negligible (within measurement noise).
# Extend this list with your own domain vocabulary if relevant.
WHISPER_INITIAL_PROMPT = os.environ.get(
    "WHISPER_INITIAL_PROMPT",
    "React, TypeScript, JavaScript, API, AWS, Docker, Kubernetes, Python, FastAPI, GitHub, Node.js, npm",
)
# Found from testing the prompt above in the real streaming pipeline (not just
# isolated one-shot calls): on a near-silent trailing fragment, the model
# hallucinated by echoing the prompt vocabulary back verbatim ("React,
# TypeScript, Docker, ..."). This is a known characteristic of prompted
# generation on ambiguous/empty input, and it's worse than the pre-prompt
# hallucinations (unrelated words) since it looks deceptively like genuine
# recognized speech. Can't safely filter by matching against the prompt text
# itself — a real video genuinely discussing these exact technologies would
# look identical. Instead calibrated directly against faster-whisper's
# no_speech_prob: measured 0.0012 for confirmed real speech vs 0.5143 for the
# reproduced hallucination — a >400x difference. Threshold set well below the
# hallucination value for margin. Based on one direct reproduction, not a
# large sample — tune if you see either real speech getting dropped (raise
# it) or hallucinations still leaking through (lower it).
WHISPER_NO_SPEECH_PROB_THRESHOLD = float(os.environ.get("WHISPER_NO_SPEECH_PROB_THRESHOLD", "0.4"))

# Repetition-loop guard. Found from a user report + screenshot showing the
# model getting stuck mid-utterance repeating "the React, the API, the API,
# the API, ..." — a known failure mode of greedy decoding (beam_size=1, used
# here for speed): nothing penalizes re-emitting the same token, so once it
# starts repeating, repeating again can stay the most likely next token
# indefinitely. WHISPER_INITIAL_PROMPT makes it worse by biasing toward
# exactly the words that get looped. This is a different failure than the
# no_speech_prob hallucination above — it happens on real, confidently-
# recognized speech, so no_speech_prob stays low the whole time and doesn't
# catch it.
#
# Reproduced directly: heavy background noise + this prompt reliably drove
# the model into repeating a prompt word 5x in a row ("AWS, AWS, AWS, AWS,
# AWS") — the same failure shape as the reported bug. `no_repeat_ngram_size=3`
# (hard-blocks repeating the same 3-token sequence) eliminated that exact
# loop in the same reproduction, with no measurable quality change on clean
# audio containing legitimate repeats (a 24s clip naturally repeating "the
# API"/"the React" 3x each transcribed identically with the guard on vs off).
#
# `repetition_penalty` was tried too (the other standard knob for this) but
# rejected: even a mild value (1.15) visibly fragmented and garbled otherwise-
# correct transcription of that same legitimate-repeats clip ("In ATI Layer
# itself depends On how To Reacts Framework") — a real regression, not a
# hypothetical one. Left out entirely rather than shipped at a "safer" value,
# since no value was tested clean.
WHISPER_NO_REPEAT_NGRAM_SIZE = int(os.environ.get("WHISPER_NO_REPEAT_NGRAM_SIZE", "3"))

# --- NLLB translation (POC4, see requirement.md section 9/10) ---
NLLB_DEVICE = os.environ.get("NLLB_DEVICE", "auto")  # auto | cpu | cuda
# Dynamic int8 quantization on CPU. Measured directly: 2.5x faster (1298ms ->
# 518ms avg per translate() call on this CPU) with no meaningful quality loss
# on spot-checked output. Toggle off only if you notice a real quality
# regression on your own content.
NLLB_QUANTIZE_CPU = os.environ.get("NLLB_QUANTIZE_CPU", "true").lower() == "true"
