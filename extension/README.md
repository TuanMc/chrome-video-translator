# Video Translator — Extension

Chrome MV3 extension: captures current-tab audio, streams it to a local
FastAPI server (STT + translation), and overlays the Vietnamese subtitle on
the page. Two interchangeable backend servers exist — `../nllb-server/README.md`
(default, port 8000) and `../libre-server/README.md` (LibreTranslate-backed,
port 8001) — the popup's "Translation Engine" setting picks which one a
session talks to; either or both can be running.

Built incrementally as 5 POCs (tab capture → transport → STT → translation →
on-page overlay), each proven working before the next was built — see git-less
history in the conversation, or just the shape of the code below. This README
now describes the finished MVP, not the POC log.

## Architecture

```
Popup (React)                     — settings UI + start/stop control
  │ POPUP_START { settings }
  ▼
Service worker                    — orchestration only, no audio/binary data
  │ health-checks the local server, validates the tab, injects the content
  │ script, creates the offscreen document, relays subtitle/status messages
  ├──────────────┐
  ▼              ▼
Offscreen doc    Content script
(audio capture,  (Shadow DOM
 WebSocket,       subtitle
 AudioWorklet)    overlay)
  │
  ▼
Local server, either nllb-server (FastAPI + faster-whisper + NLLB) or
libre-server (FastAPI + faster-whisper + LibreTranslate) — see their READMEs
```

**Deviation from the originally-approved folder structure worth flagging**:
`content/subtitle-overlay.tsx` was specified as React; it's plain
TypeScript/DOM instead. Reason: `chrome.scripting.executeScript({files:[...]})`
runs the file as a classic (non-module) script, so it must be fully
self-contained with zero runtime `import` statements — verified this
concretely (hit and fixed the same failure mode with the AudioWorklet file
earlier). The overlay is a handful of DOM operations, so plain TS sidesteps
the whole problem for free. React stays in the popup, where it's genuinely
useful for the settings UI.

## Build

```bash
npm install
npm run build
```

This produces `dist/`, which is what you load into Chrome (not the dev server).

## Load into Chrome

1. Go to `chrome://extensions`
2. Enable **Developer mode** (top right)
3. **Load unpacked** → select the `extension/dist` folder
4. Pin the extension so its icon is visible in the toolbar
5. If you're reloading after a permission change (e.g. `scripting`,
   `host_permissions`), click the reload icon on the extension's card — a
   plain rebuild isn't picked up automatically, and Chrome may prompt to
   accept the new permission.

## Before testing: start a local server

Start whichever server matches your intended **Translation Engine** popup
setting — `../nllb-server/README.md` (port 8000) or `../libre-server/README.md`
(port 8001). Both can run at once. The popup now checks `GET /health` on the
selected server before starting and will show a clear error (not hang) if it
isn't up or hasn't finished loading/reaching its models yet.

## Popup settings

- **Source language**: English / 日本語 / 中文 — sent as `sourceLanguage` in
  the WebSocket `start` message.
- **Translation engine**: NLLB or LibreTranslate — determines which local
  server (port 8000 or 8001) this session connects to. LibreTranslate is
  disabled in the popup unless `libre-server`'s `/health` reports it reachable
  (most users won't have it running — it's an opt-in second server).
- **Display**: Vietnamese-only or Bilingual (original + translated) — applied
  by the content script (hides/shows the original-language line).
- **Text size**: 16-32px, applied to the translated line (original line is
  6px smaller, floor 12px, matching the doc's example ratio).
- **Position**: Top or Bottom.

Settings persist via `chrome.storage.local` (deliberately *not* `.sync` — see
comment in `src/services/settings-storage.ts` — this project is local-first,
nothing should route through Google's account sync for something this
low-stakes). Controls are disabled while a session is active — change
settings, then start; no live-editing mid-session yet.

## Manual test steps

1. Start nllb-server, confirm `curl http://127.0.0.1:8000/health` shows both
   `sttModelLoaded` and `translationModelLoaded` as `true`. (For libre-server:
   `curl http://127.0.0.1:8001/health`, looking for `sttModelLoaded` and
   `translationReady`.)
2. Open the popup with the server **stopped** first — click **START
   TRANSLATION** — should show a clear "Local server is not running" error, not
   hang or silently fail. Then start the server and confirm the same click
   now proceeds normally.
3. Pick a source language, display mode, text size, and position in the popup.
4. Open a tab playing audio/video in that language (a talking-head YouTube
   video works well). Click **START TRANSLATION**.
5. **Listen**: audio should keep playing normally, no mute/gap/glitch.
6. Popup status should move `Idle → Connecting… → Listening`, with a
   green dot once listening. Watch for it to flip to `Translating…` (blue
   dot) briefly after each pause in speech, then back to `Listening`.
7. After a pause, a subtitle box should appear on the page matching your
   chosen position/display-mode/text-size settings. Compare it against what's
   actually being said. Try 2-3 different sites to check nothing clips it.
8. Click **■ STOP TRANSLATION** — audio unaffected, status back to `Idle`,
   overlay disappears, server logs the session summary.
9. Repeat start/stop a few times — no stuck capture indicator, no duplicate
   overlays, settings controls re-enable correctly each time.
10. Try **START TRANSLATION** on an unsupported page (`chrome://extensions`,
    a blank new tab) — clear error, not a hang.
11. Close the tab while active — capture stops cleanly (check the service
    worker console for errors).
12. Navigate the tab to a different URL while active — should stop cleanly
    with an error status rather than silently continuing into a dead page.
    Implemented but not yet tested by me in a real browser.
13. **Server-crash test**: start a session normally, then kill the server
    process (`Ctrl+C` in its terminal) while status is `Listening`. Within a
    few seconds the popup should flip to `Error` with "Connection to the
    local server was lost" (not keep showing `Listening` forever with audio
    playing and nothing happening). The offscreen document and overlay should
    both clean up — check `chrome://extensions` doesn't still show a capture
    indicator, and the on-page subtitle box should disappear.

## Debugging

- Service worker logs/errors: `chrome://extensions` → this extension →
  **service worker** link.
- Offscreen document logs: same page → **Inspect views: offscreen.html**
  (only appears while active). Shows `[offscreen] server: {...}` for every
  message from the local server.

## Error handling (requirement.md section 27)

| Case | Behavior |
|---|---|
| No active tab | Clear error, shown immediately |
| Unsupported/`chrome://` page | Clear error, shown immediately |
| Local server not running / still loading models | Caught by the pre-start health check, clear error, doesn't attempt capture |
| Tab audio capture fails / permission denied | Wrapped with a friendlier message than the raw Chrome error |
| WebSocket disconnects mid-session (server crash, network drop) | Detected via the socket's close/error events, distinguished from an intentional Stop; auto-cleans up audio/offscreen resources and surfaces a clear `Error` status |
| Offscreen audio setup hangs | 10s timeout on that round-trip, so the popup can't get stuck on `Connecting…` forever |
| Service worker unresponsive when popup sends a command | Caught in the popup, shown as an error instead of a silent failure |
| STT pass fails for one segment | Non-fatal (the next scheduled pass retries), but now sent to the client as a visible `error` message instead of only appearing in server logs |
| Translation fails for one segment | Already sent as a visible `error` message; session continues |
| Tab closes / navigates away during capture | Detected, capture stops cleanly, error status shown |

Tab-navigation and server-crash-mid-session are implemented but I haven't
personally verified them in a real browser — see test steps 12-13 above.

### Bugs found and fixed in a later review pass (worth knowing about)

- **Resource leak on partial-startup failure**: if `chrome.scripting.executeScript`
  (or anything after the offscreen document was created) failed, the offscreen
  document was never closed — it would sit around idle until the next start
  attempt. Fixed by consolidating all of `startCapture`'s post-offscreen-creation
  steps under one try/catch that always closes it on failure.
- **Retry-blocking bug in the offscreen document**: if audio setup failed
  partway through (worklet module missing, WebSocket connect failing, etc.)
  *after* `stream`/`audioContext` were already created, those module-level
  variables were never reset. Since `startCapture` guards with `if (stream)
  throw "Capture already in progress"`, this would have permanently blocked
  any retry until the extension was reloaded. Fixed with a try/catch that
  guarantees cleanup on any failure.
- **Redundant status flicker**: the tab-navigation-away handler called the
  full `stopCapture()` (which ends in `idle`) and then immediately overwrote
  it to `error` — a wasted extra status broadcast, and the `error` status was
  missing `tabId`. Refactored into a shared `cleanupSession()` helper that
  doesn't touch status, so each caller sets its own final state directly.
- **Re-entrancy guard added to the offscreen document's `stopCapture()`** —
  closes a narrow (and previously untested) race where two near-simultaneous
  triggers could both reach `audioContext.close()` on the same context.

None of these were caught by type-checking or linting — they're the kind of
bug that only shows up by tracing through failure paths by hand, which is
exactly what this pass was for. All verified via build/lint/type-check plus
a Node-based simulation of the actual compiled content-script bundle; the
underlying browser-specific behaviors (CORS bypass via `host_permissions`,
actual `chrome.scripting.executeScript` failures) still need real-browser
confirmation.

## Known limitations

- Settings can't be changed mid-session (must stop first).
- No auto-detect language (matches current requirement.md scope — manual
  selection only).
- Resampling to 16kHz uses plain linear interpolation, not a proper
  anti-aliased resample — testing suggests it's good enough for Whisper in
  practice, not rigorously isolated from other quality factors.
- "No audio detected" isn't actively detected — reliably distinguishing
  "no audio in the tab" from "silence/pause in normal speech" without false
  positives would need real tuning against real content; not attempted.
- DRM-protected streams and `chrome://`-style pages are expected to fail;
  that's by design.
- `host_permissions` is scoped to exactly `http://127.0.0.1:8000/*` and
  `http://127.0.0.1:8001/*` (needed so the service worker's health-check
  `fetch()` isn't blocked by CORS) — if you change either server's port,
  update this in `manifest.json` and `src/constants/index.ts`'s
  `SERVER_CONFIG` too.
