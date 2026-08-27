# AGENTS.md

## Project

A Chrome extension that generates near-real-time Vietnamese subtitles from tab audio (EN/JA/ZH source). Everything runs locally — no paid cloud AI APIs, audio/transcripts never leave localhost in normal operation — with one explicit, opt-in exception (`soniox-server/`, see below). Full spec: `.aidlc/inputs/requirement.md`. Deep architecture/API/dependency reference: `aidlc-docs/inception/reverse-engineering/` — read that before making structural changes, don't re-derive it from scratch.

## Layout

Four independently runnable packages. None imports another; they only talk over localhost WebSocket/HTTP at runtime.

| Package | What | Port |
|---|---|---|
| `extension/` | Chrome MV3 extension (React + TypeScript + Vite) | n/a (browser) |
| `nllb-server/` | FastAPI: faster-whisper STT + in-process NLLB-200 translation (default) | 8000 |
| `libre-server/` | FastAPI: same STT, translates via a self-hosted LibreTranslate container | 8001 |
| `soniox-server/` | FastAPI: relays audio to Soniox's cloud API (STT+translation combined) — **not local, paid**, the one deliberate exception to this project's local-only design; needs `SONIOX_API_KEY` | 8002 |

## Setup & commands

### extension
```bash
cd extension
npm install
npm run build     # tsc -b && vite build -> dist/
npm run lint       # oxlint
npm run dev        # vite dev server (not for loading into Chrome — build+load dist/ for that)
```
Load into Chrome: `chrome://extensions` → Developer mode → Load unpacked → `extension/dist`. Reload the extension (not just rebuild) after any `manifest.json` change.

### nllb-server
```bash
cd nllb-server
python3 -m venv .venv
.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch   # CPU wheel — plain `pip install torch` pulls the much larger CUDA build
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Health check: `curl http://127.0.0.1:8000/health` → `translationModelLoaded: true` once ready. Docker alternative: `run-server.bat` (or the equivalent `docker build`/`docker run`, see `nllb-server/README.md`).

### libre-server
```bash
cd libre-server
docker run -d -p 5000:5000 -e LT_LOAD_ONLY=en,ja,zh,vi libretranslate/libretranslate:latest   # the translation engine itself
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
```
Health check: `curl http://127.0.0.1:8001/health` → `translationReady: true` (live reachability check, not a one-time load flag). Docker-Compose alternative (both containers at once): `docker compose up -d --build` from `libre-server/`.

### soniox-server
```bash
cd soniox-server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
SONIOX_API_KEY=your-key-here .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002
```
Needs a paid API key from https://soniox.com/ — see `soniox-server/README.md` for the local-only-exception caveat and what's verified vs. assumed about Soniox's protocol. Health check: `curl http://127.0.0.1:8002/health` → `apiKeyConfigured: true` (only confirms the key is set, not that it's valid or Soniox is reachable). Docker alternative: `run-server.bat`.

No test suite exists for any package — do not claim "tests pass"; verification is build/lint plus manual/live testing (see each package's README for the specific manual test steps used historically).

## Conventions

- **Comments explain why, not what.** This repo leans heavily on comments that record the specific bug/measurement/tradeoff behind a piece of logic (e.g. why a constant is `0.4` and not `1.0`). Match this style — don't add comments that just restate the code.
- **Provider abstraction**: STT and translation are both behind ABCs (`providers/speech_to_text/base.py`, `providers/translation/base.py`) in `nllb-server`/`libre-server`. Add new backends there as new provider classes, not by branching inside the WebSocket handler. `soniox-server` deliberately does **not** use these ABCs — Soniox does STT and translation together as one combined stream, so splitting it across two swappable-backend interfaces designed for independently-swappable STT/translation would be a false abstraction; see `soniox-server/app/providers/soniox_client.py`'s docstring.
- **`nllb-server` and `libre-server` intentionally duplicate pipeline code** (`faster_whisper.py`, `translation_socket.py`, `terminology.py`, `protocol.py`) rather than sharing a package — a deliberate tradeoff (manual-sync-on-change), not an oversight. If you change shared-shaped logic in one, check whether the other needs the same change. `soniox-server` only shares `protocol.py`'s shape with them (the extension-facing contract) — it has no `faster_whisper.py`/local buffering equivalent at all, since Soniox handles segmentation server-side.
- **Every tunable constant is env-var overridable** via `app/config/settings.py`, with a comment explaining the chosen default. Follow this pattern for new constants rather than hardcoding.
- **Measure, don't guess.** Fixes and tuning in this repo are grounded in reproduced failures and direct measurement (see git history / `aidlc-docs/.../code-quality-assessment.md`), not assumption. Don't ship a "should help" change without at least attempting to verify it.

## Boundaries

- Never touch git config (`git config` is off-limits regardless of scope).
- Never commit `.venv/`, `__pycache__/`, or `tmp_recordings/` — already gitignored per-package, keep it that way.
- Privacy requirement: do not add persistence of captured audio, transcripts, or translations unless explicitly asked — `SAVE_DEBUG_AUDIO` exists and defaults to `false` for exactly this reason.
- Don't merge `nllb-server`/`libre-server` into a shared package on your own judgment — that tradeoff was made deliberately; raise it as a question if it seems worth revisiting.
- `.aidlc/inputs/requirement.md` is the original spec and has known drift from the current implementation (documented in `aidlc-docs/.../code-quality-assessment.md`) — treat the actual code as the source of truth, not that file, when they disagree.

## AI-DLC workflow

This project has adopted [AWS AI-DLC](https://github.com/awslabs/aidlc-workflows) (v1.0.1, official public release) as its structured development workflow.

- **When the user invokes AI-DLC** (says "AI-DLC", "Mob Elaboration", or asks for the structured workflow), read and follow `.aidlc/aidlc-rules/aws-aidlc-rules/core-workflow.md` — that file is the entry point and pulls in whichever rule-detail files it needs from `.aidlc/aidlc-rules/aws-aidlc-rule-details/`. Do not summarize or reimplement it from memory; read it fresh, since the exact stage rules matter.
- **Before taking any AI-DLC action, read `aidlc-docs/` first** — specifically `aidlc-docs/aidlc-state.md` (workflow state, what's already been completed) and `aidlc-docs/inception/reverse-engineering/` (the existing project knowledge base: architecture, code structure, API surface, dependencies, code quality). This project is brownfield with reverse-engineering artifacts already generated — core-workflow.md's own Workspace Detection step should find and reuse them rather than redoing the analysis, but confirm that happened rather than assuming it.
- Do not rename, move, or edit files under `.aidlc/aidlc-rules/` — that directory is a vendored copy of AWS's distributable rules package, not project-specific content. Project-specific AI-DLC output belongs under `aidlc-docs/`.

## In-progress work

`.aidlc/inputs/segment-improvement.md` is an approved-but-not-yet-implemented spec for reworking the realtime segmentation/incremental-STT pipeline. Check it before touching `faster_whisper.py` or `translation_socket.py` in case work is mid-flight.
