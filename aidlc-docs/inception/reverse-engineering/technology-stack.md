# Technology Stack

## Programming Languages

- **TypeScript** (~6.0.2) — the entire `extension` package.
- **Python** (developed against 3.9.25 locally; Docker images use 3.11-slim) — both server packages.

## Frameworks & Libraries

### Extension
- **React** 19.2.8 — popup UI only (the content-script overlay is deliberately plain DOM/TS, not React, since `chrome.scripting.executeScript` requires a classic non-module script).
- **Vite** 8.2.2 — build tool.
- **@crxjs/vite-plugin** 2.7.1 — MV3-aware bundling (handles multi-entry-point extension builds Vite doesn't natively).

### nllb-server
- **FastAPI** (>=0.115,<0.116) + **uvicorn[standard]** (>=0.32,<0.33) — WebSocket/HTTP server.
- **faster-whisper** (>=1.2,<1.3) — CTranslate2-based Whisper STT, CPU-friendly (int8).
- **transformers** (>=4.57,<4.58) + **torch** (CPU-only wheel) — loads and runs `facebook/nllb-200-distilled-600M`, with dynamic int8 quantization on CPU.
- **numpy** (>=2.0,<3.0) — PCM16 ↔ float32 audio conversion.

### libre-server
- Same FastAPI/uvicorn/faster-whisper/numpy stack as nllb-server.
- **httpx** (>=0.27,<0.28) — async HTTP client to the LibreTranslate container. No torch/transformers dependency — translation isn't an in-process model here.

### External AI Models/Services (all self-hosted, no paid APIs)
- **faster-whisper `base` model** — speech recognition, EN/JA/ZH.
- **facebook/nllb-200-distilled-600M** — translation (nllb-server).
- **libretranslate/libretranslate** (Docker image, Argos-Translate-based) — translation (libre-server).

## Infrastructure

- **Docker / Docker Compose** — the only "infrastructure" in this project; used for zero-Python-install deployment and for bundling libre-server with its LibreTranslate engine container. No cloud provider, no managed services.

## Build Tools

- **npm** — extension package management/scripts.
- **pip + venv** — server dependency management (no lockfile/poetry — plain `requirements.txt` with version ranges).
- **Docker** — containerized builds for both servers.

## Linting / Formatting

- **oxlint** (^1.79.0) — extension linting, `npm run lint`, config at `extension/.oxlintrc.json`.
- **No Python linter or formatter is configured** for either server (no ruff/black/flake8/mypy config found in the repo).

## Testing Tools

**None configured.** No test runner (pytest, vitest, jest, etc.) is set up for any package. See `code-quality-assessment.md` for the implications and the verification approach actually used instead.
