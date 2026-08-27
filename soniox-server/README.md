# Local Server — Soniox variant

Sibling of `../nllb-server` and `../libre-server`, but architecturally
different from both: it doesn't run `faster-whisper` or any local/self-hosted
translation model. Instead it relays tab audio to
[Soniox](https://soniox.com/)'s real-time cloud API, which does speech-to-text
**and** translation together over a single WebSocket connection.

**This server is not fully local.** Every other package in this repo keeps
audio and transcripts on localhost (see the top-level `AGENTS.md`); this one
is a deliberate, explicit exception — it sends captured tab audio to Soniox's
servers, and Soniox is a paid API (see [pricing](https://soniox.com/pricing)).
Only use it if you're fine with that tradeoff. `nllb-server`/`libre-server`
remain the fully-local default.

Runs on **port 8002**, so it can run alongside `nllb-server` (8000) and
`libre-server` (8001) — the extension popup lets you pick per-session which
backend to use.

## Why this exists

Soniox's `stt-rt-v5` model streams transcription tokens immediately, then
translation tokens progressively, on the same connection — and does its own
server-side pause/endpoint detection, emitting a sentinel `"<end>"` token to
mark a finished utterance. That collapses what's normally two separate
pipeline stages (STT, then a translate call) plus a chunk of
sliding-window/VAD bookkeeping (see `faster_whisper.py` in the other two
servers) into "relay audio in, re-shape the token stream out." See
`app/providers/soniox_client.py` for the client and
`app/websocket/translation_socket.py` for how its token stream maps onto
this project's `transcript`/`subtitle` WebSocket protocol (unchanged from
the other two servers — the extension needs no protocol-level changes).

Built against Soniox's public docs: [WebSocket API](https://soniox.com/docs/api-reference/stt/websocket-api),
[real-time transcription](https://soniox.com/docs/stt/rt/real-time-transcription),
[real-time translation](https://soniox.com/docs/translation/stt-translation/rt-translation),
[endpoint detection](https://soniox.com/docs/stt/rt/endpoint-detection).

## What's verified vs. assumed

**Not yet verified against live Soniox traffic** (I don't have a Soniox API
key, so this was built from docs alone — the docs don't show a full
multi-turn transcript+translation example):

- Whether the `"<end>"` sentinel applies to *both* the original-language and
  translated streams for a turn, or only the original one.
- Whether translation tokens reliably finish catching up to their source
  tokens before `"<end>"` fires, or whether a translated segment can still be
  incomplete at that point.

`translation_socket.py` currently assumes both (flushes whatever's
accumulated in both buffers the moment `"<end>"` arrives). If real testing
shows translated text getting cut off short at segment boundaries, that
assumption is the first thing to revisit — it would mean waiting briefly
after `"<end>"` for trailing translation tokens rather than finalizing
immediately.

If you test this against a real Soniox key, please report back what you see
(any of: translations look complete vs. truncated at each subtitle; segment
boundaries feel natural vs. too frequent/infrequent) — that's the fastest
path to confirming or fixing the assumption above.

## Setup

Needs a Soniox API key: sign up at [soniox.com](https://soniox.com/) and
create one in their console, then make it available as the `SONIOX_API_KEY`
environment variable. Never commit a real key — `.env` is gitignored
specifically for this.

**Recommended: a `.env` file**, like a Node project's `.env`/dotenv
convention. Copy `.env.example` to `.env` in this folder and fill in your
key:
```
SONIOX_API_KEY=your-key-here
```
`run-server.bat` auto-detects `.env` and passes it to Docker via
`--env-file .env`. For a local Python venv, pass `--env-file .env` to
`uvicorn` directly (it already depends on `python-dotenv` via
`uvicorn[standard]`, so this works with no extra install):
```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002 --env-file .env
```
If you'd rather not use a file, setting the variable directly in your shell
(`set SONIOX_API_KEY=...` on Windows, `export SONIOX_API_KEY=...` on
Mac/Linux) works everywhere below too — `run-server.bat` falls back to that
if no `.env` is present.

### Option A: Docker

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   and make sure it's running.
2. Set up your key (`.env` file, or the `SONIOX_API_KEY` shell variable —
   see above).
3. From this folder, run `run-server.bat` (Windows), or directly:
   ```bash
   docker build -t chrome-video-translator-soniox-server:local .
   docker run -d --name chrome-video-translator-soniox-server -p 8002:8002 --env-file .env chrome-video-translator-soniox-server:local
   ```

Unlike the other two servers, there's no model to download — the image
builds in well under a minute and starts immediately.

### Option B: local Python venv

```bash
cd soniox-server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002 --env-file .env
```

Verify it's up:

```bash
curl http://127.0.0.1:8002/health
# {"status":"ok","apiKeyConfigured":true,"sttModelLoaded":true,"translationReady":true}
```

`apiKeyConfigured` (and the two fields mirroring it, kept for parity with
the other servers' `/health` shape) is a **configuration** check — it only
confirms `SONIOX_API_KEY` is set, not that the key is valid or that Soniox
is reachable. A bad or expired key will only surface once a session actually
starts, as an `STT_ERROR` message.

### Configuration (env vars)

| Var | Default | Notes |
|---|---|---|
| `SONIOX_API_KEY` | *(required)* | from the Soniox console — set via `.env` (recommended) or your shell |
| `SONIOX_WS_URL` | `wss://stt-rt.soniox.com/transcribe-websocket` | override only for testing against a different endpoint |
| `SONIOX_MODEL` | `stt-rt-v5` | Soniox's real-time model id |
| `SONIOX_TARGET_LANGUAGE` | `vi` | this project always translates to Vietnamese |
| `SONIOX_ENABLE_ENDPOINT_DETECTION` | `true` | lets Soniox decide segment/pause boundaries server-side |
| `SONIOX_FINISH_TIMEOUT_SECONDS` | `5.0` | how long `stop()` waits for Soniox's `finished: true` before giving up |
| `SAVE_DEBUG_AUDIO` | `false` | opt-in `.wav` capture for verifying the transport pipeline by ear — note audio is sent to Soniox regardless of this setting |

## What to check when testing

Same shape as the other two servers' manual-test workflow: watch this
server's terminal, start a capture session from the extension, and confirm:

- `{type: 'transcript', final: false}` messages arrive quickly as speech is
  recognized, text roughly tracking what's actually being said.
- On a natural pause, a `final: true` transcript, then a `subtitle` message
  with both `original` and `translated` text, then the status returns to
  `listening`.
- Read the Vietnamese `translated` text against what was actually said (not
  just the `original` transcript) to judge translation quality
  independently of STT quality — same as the other servers' README guidance.
- Whether segment boundaries (where a new subtitle starts) feel natural —
  this is entirely Soniox's endpoint detection now, not any local tuning
  knob in this repo.
