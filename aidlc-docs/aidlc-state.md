# AI-DLC State

## Workspace Type

**Brownfield** — existing, working codebase (Chrome extension + two local translation-backend servers).

## Scope Note

The **Reverse Engineering** documentation stage was run first (before the workflow rules themselves were installed), producing the artifacts below. The official AI-DLC workflow rules package (`awslabs/aidlc-workflows` v1.0.1, verified against the public GitHub release) was installed afterward at `.aidlc/aidlc-rules/` — see `AGENTS.md`'s "AI-DLC workflow" section for the invocation entry point.

**Not yet set up**: `.aidlc/aidlc-agents/` (project specialist agents for Mob Elaboration) and `aidlc-docs/audit.md` (the mandatory session-log the full workflow expects once actively running). Mob Elaboration is skipped by core-workflow.md until agent files exist or the user explicitly requests it. Add these if/when a full Inception session (not just Reverse Engineering) is actually run.

## Reverse Engineering Status

- [x] Reverse Engineering — Completed on 2026-08-27T11:32:59Z
- **Artifacts Location**: `aidlc-docs/inception/reverse-engineering/`
- **Rerun trigger**: Artifacts should be regenerated/updated if the two-server architecture changes again (e.g. the `segment-improvement.md` refactor lands, or the file-duplication tradeoff between `nllb-server`/`libre-server` is revisited).
