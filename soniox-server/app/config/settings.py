import os

# Host/port aren't config here — passed directly as `uvicorn` CLI flags (see
# README.md). This server runs on port 8002 (nllb-server takes 8000,
# libre-server takes 8001) — must match extension/src/constants/index.ts's
# SERVER_CONFIG.soniox if ever changed (manifest.json's host_permissions is
# now <all_urls>, so it doesn't need updating for a port change — see
# extension/README.md's "Known limitations" for why).

# Fixed audio contract with the extension (see requirement.md section 13/16) —
# also happens to be exactly what Soniox's raw-PCM input wants, so no
# transcoding is needed anywhere in this server.
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_SAMPLE_WIDTH_BYTES = 2  # PCM16

# Off by default — this project is local-first/privacy-friendly by design
# (requirement.md section 29). Opt in with SAVE_DEBUG_AUDIO=true only when
# you specifically want to verify the capture/transport pipeline by
# listening back to a session. Note this server already sends that same
# audio to Soniox's cloud API regardless of this setting — see README.md's
# "not fully local" caveat.
SAVE_DEBUG_AUDIO = os.environ.get("SAVE_DEBUG_AUDIO", "false").lower() == "true"
DEBUG_AUDIO_DIR = os.environ.get("DEBUG_AUDIO_DIR", "tmp_recordings")

# --- Soniox (cloud STT + translation, one combined WebSocket session) ---
# No local model here at all: unlike nllb-server/libre-server, this server
# doesn't run faster-whisper or any in-process/self-hosted translation
# engine — Soniox's stt-rt-v5 model does STT and translation together over
# one upstream WebSocket. See README.md for the protocol this is built
# against and what's been verified vs. assumed from docs alone.

# Required — no default. main.py's lifespan refuses to start meaningfully
# without this (see /health's apiKeyConfigured). Get one at
# https://soniox.com/ (paid; see README.md's cloud-cost caveat).
SONIOX_API_KEY = os.environ.get("SONIOX_API_KEY", "")

SONIOX_WS_URL = os.environ.get("SONIOX_WS_URL", "wss://stt-rt.soniox.com/transcribe-websocket")
SONIOX_MODEL = os.environ.get("SONIOX_MODEL", "stt-rt-v5")

# Fixed at "vi" — this project's whole purpose is Vietnamese subtitles, same
# as nllb-server/libre-server's translation targets. Not exposed as an
# extension setting, so not worth making configurable beyond an env var
# escape hatch for local experimentation.
SONIOX_TARGET_LANGUAGE = os.environ.get("SONIOX_TARGET_LANGUAGE", "vi")

# Lets Soniox's own server-side VAD/pause detection decide segment
# boundaries (emits the "<end>" sentinel token — see
# app/websocket/translation_socket.py) instead of this server re-implementing
# the sliding-window/silence-finalize logic faster_whisper.py has to.
SONIOX_ENABLE_ENDPOINT_DETECTION = (
    os.environ.get("SONIOX_ENABLE_ENDPOINT_DETECTION", "true").lower() == "true"
)

# Bound for how long stop() waits for Soniox's "finished: true" after sending
# the empty-string end-of-audio frame, before giving up and closing anyway —
# mirrors this project's general pattern of never blocking session teardown
# indefinitely on an external signal that might not arrive.
SONIOX_FINISH_TIMEOUT_SECONDS = float(os.environ.get("SONIOX_FINISH_TIMEOUT_SECONDS", "5.0"))
