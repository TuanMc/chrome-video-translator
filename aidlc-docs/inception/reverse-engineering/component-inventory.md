# Component Inventory

## Application Packages

- **extension** — Chrome Manifest V3 extension (React + TypeScript + Vite). User-facing capture/UI/overlay.
- **nllb-server** — FastAPI application server, port 8000. STT + in-process NLLB translation.
- **libre-server** — FastAPI application server, port 8001. STT + HTTP-proxied LibreTranslate translation.

## Infrastructure Packages

- **libre-server/docker-compose.yml** — Docker Compose definition bundling `libre-server`'s app container with a `libretranslate/libretranslate` engine container. No CDK/Terraform/CloudFormation — this project has no cloud deployment target, everything is local.
- **nllb-server/Dockerfile**, **libre-server/Dockerfile** — standalone single-container builds for each server (the `nllb-server` one is fully self-sufficient; `libre-server`'s standalone Dockerfile still needs a separately-run LibreTranslate container to be useful, which is what the compose file is for).

## Shared Packages

**None** — by explicit decision, `nllb-server` and `libre-server` do not share a code package. `faster_whisper.py`, `translation_socket.py`, `terminology.py`, and `protocol.py` are duplicated file-for-file between the two server folders, kept in sync manually when the shared logic changes. See `dependencies.md` for the rationale.

## Test Packages

**None currently exist.** No automated unit, integration, or end-to-end test suite is checked into the repository for any of the three components. Verification throughout development was done via ad hoc scripts (direct provider calls, WebSocket smoke tests, synthetic TTS audio) documented in each server's `README.md`, plus manual testing in a real browser — not via a persisted, re-runnable test suite. See `code-quality-assessment.md`.

## Total Count

- **Total Packages**: 3
- **Application**: 3 (extension, nllb-server, libre-server)
- **Infrastructure**: 0 dedicated packages (Dockerfiles/compose live alongside their app code)
- **Shared**: 0
- **Test**: 0
