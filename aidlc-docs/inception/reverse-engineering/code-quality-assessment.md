# Code Quality Assessment

## Test Coverage

- **Overall**: None — no automated test suite exists for any of the three packages.
- **Unit Tests**: Not present.
- **Integration Tests**: Not present as checked-in, re-runnable tests. Equivalent verification *was* done throughout development, but as one-off scripts (direct provider calls, WebSocket handshake smoke tests, synthetic-TTS-generated audio through the real pipeline) run manually and documented in prose in `nllb-server/README.md` / `libre-server/README.md`, not preserved as a test suite anyone can re-run with one command.
- **This is real, honest technical debt**, not an oversight to gloss over — a project at this stage (rapid POC-by-POC iteration, per `requirement.md`'s own build order) reasonably deferred it, but it means every regression check currently depends on a human re-running things by hand.

## Code Quality Indicators

- **Linting**: Configured for the extension only (`oxlint`, `npm run lint`). Neither Python server has a linter or formatter configured (no ruff/black/flake8/mypy).
- **Code Style**: Consistent within each language. Notably heavy, deliberate use of comments explaining **why** a piece of logic exists (a specific bug it fixes, a tradeoff it accepts, a measurement that justified a constant's value) rather than what the code does — this is a strong, consistent project convention, not incidental.
- **Documentation**: Good at the "why" level (per-file/per-constant rationale comments, thorough per-server READMEs with real measured data) but there is no docstring/API-reference-style documentation, and — until this document set — no single place describing the system as a whole.

## Technical Debt

- **File-level duplication between nllb-server and libre-server** (`faster_whisper.py`, `translation_socket.py`, `terminology.py`, `protocol.py`) — an explicit, accepted tradeoff (see `dependencies.md`), but real debt: any pipeline-level change must be manually applied twice, already demonstrated once (a repetition-loop fix) and about to be exercised again by the `segment-improvement.md` refactor.
- **No automated tests** (see above).
- **`requirement.md` (the original product spec) has drifted from the implementation** in several places — e.g. it mandates a strict black/white/gray-only popup design (§19-20), while the popup now uses a dark/amber theme; it describes a single server, while there are now two; its `UserSettings` model is missing `translationProvider`. None of this is a "bug" — the drift is from explicit, approved changes made after the spec was written — but the spec document itself was never updated to match, so it's no longer a reliable source of truth for current behavior. This document set is intended to be the up-to-date replacement for that purpose.
- **Whisper's transcription window is unbounded until finalization** rather than a fixed sliding window — functions correctly today but re-transcribes a growing (up to 5-8s) buffer on every pass near the finalization cap, flagged as the primary target of the pending `segment-improvement.md` refactor.
- **No CI pipeline** — nothing runs lint/build/tests automatically on push; everything described above is invoked manually by a developer.

## Patterns and Anti-patterns

- **Good Patterns**:
  - Provider abstraction (`SpeechToTextProvider`/`TranslationProvider`) — proven out by a real second implementation (LibreTranslate), not just theoretical.
  - Shadow DOM isolation for the page-injected overlay.
  - Deliberate try/catch resource-cleanup boundaries in the extension (offscreen document, audio capture) — several were added specifically after tracing real failure paths (see `extension/README.md`'s "Bugs found and fixed" section).
  - Fixes grounded in reproduced, measured behavior rather than guesses — e.g. the `no_repeat_ngram_size` repetition-loop fix was validated by actually reproducing the failure with synthetic noisy audio before and after the change, and a candidate fix (`repetition_penalty`) was rejected specifically because it was shown to regress quality, not merely assumed safe.
- **Anti-patterns**:
  - Duplicated pipeline files across the two servers (see Technical Debt above).
  - No regression safety net beyond manual testing — a refactor as large as `segment-improvement.md` proposes has no automated tests to catch a regression before a human notices it live.
