import type { RuntimeMessage } from "../types/messages";

// Injected via chrome.scripting.executeScript as a classic (non-module) script,
// so this file must be fully self-contained — no runtime imports. See
// extension/README.md for why this is plain DOM manipulation, not React.
//
// Deliberately platform-independent: no dependency on the page's <video>
// structure (requirement.md section 9/17) — this just overlays a fixed-position
// element via Shadow DOM, isolated from the host page's CSS.

const HOST_ID = "video-translator-root";

// executeScript() re-runs this file's top-level code on every START click in
// the same tab. Without this guard, clicking Start twice without a navigation
// in between would create a duplicate shadow host and a duplicate listener.
if (!document.getElementById(HOST_ID)) {
  const host = document.createElement("div");
  host.id = HOST_ID;
  const shadow = host.attachShadow({ mode: "open" });

  const style = document.createElement("style");
  style.textContent = `
    .subtitle-container {
      position: fixed;
      left: 50%;
      bottom: 10%;
      transform: translateX(-50%);
      max-width: 80%;
      padding: 10px 16px;
      background: rgba(0, 0, 0, 0.75);
      border-radius: 6px;
      backdrop-filter: blur(4px);
      text-align: center;
      z-index: 2147483647;
      pointer-events: none;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: none;
    }
    .subtitle-container.visible {
      display: block;
    }
    .subtitle-container.top {
      top: 10%;
      bottom: auto;
    }
    .original {
      color: rgba(255, 255, 255, 0.65);
      margin: 0 0 4px;
    }
    .original.hidden {
      display: none;
    }
    .translation {
      color: #ffffff;
      font-weight: 600;
      margin: 0;
    }
  `;

  const container = document.createElement("div");
  container.className = "subtitle-container";

  const originalEl = document.createElement("p");
  originalEl.className = "original";
  const translationEl = document.createElement("p");
  translationEl.className = "translation";
  container.appendChild(originalEl);
  container.appendChild(translationEl);

  shadow.appendChild(style);
  shadow.appendChild(container);
  (document.body ?? document.documentElement).appendChild(host);

  // Fullscreen video (YouTube's fullscreen button, etc.) renders only the
  // fullscreened element's subtree in the browser's top layer — everything
  // else in the document, including this overlay under <body>, stops being
  // drawn even though it's still in the DOM. Re-parent into whatever just
  // became the fullscreen element (or back to <body> on exit) so the overlay
  // stays visible either way. `position: fixed` still resolves against the
  // viewport inside the top layer, so no positioning changes are needed.
  function keepOverlayInFullscreenSubtree(): void {
    const target = document.fullscreenElement ?? document.body ?? document.documentElement;
    if (host.parentElement !== target) {
      target.appendChild(host);
    }
  }
  document.addEventListener("fullscreenchange", keepOverlayInFullscreenSubtree);

  // Sensible defaults (mirrors types/settings.ts DEFAULT_USER_SETTINGS) in case
  // CONTENT_INIT is somehow delayed past the first subtitle — shouldn't happen in
  // practice since STT+translation latency (~1.6-1.9s, see server/README.md) is
  // far longer than the message round-trip, but better than an unstyled overlay.
  let displayMode: "vietnamese" | "bilingual" = "vietnamese";
  let position: "top" | "bottom" = "bottom";

  function applySettings(newDisplayMode: "vietnamese" | "bilingual", newPosition: "top" | "bottom", fontSize: number): void {
    displayMode = newDisplayMode;
    position = newPosition;
    originalEl.classList.toggle("hidden", displayMode === "vietnamese");
    container.classList.toggle("top", position === "top");
    translationEl.style.fontSize = `${fontSize}px`;
    // Keep the doc's example ratio (24px translation / 18px original = -6px).
    originalEl.style.fontSize = `${Math.max(12, fontSize - 6)}px`;
  }
  applySettings(displayMode, position, 24);

  function showSubtitle(original: string, translated: string): void {
    originalEl.textContent = original;
    translationEl.textContent = translated;
    container.classList.add("visible");
  }

  function clearSubtitle(): void {
    container.classList.remove("visible");
    originalEl.textContent = "";
    translationEl.textContent = "";
  }

  chrome.runtime.onMessage.addListener((message: RuntimeMessage) => {
    if (message.type === "SUBTITLE_UPDATE") {
      showSubtitle(message.original, message.translated);
    } else if (message.type === "SUBTITLE_CLEAR") {
      clearSubtitle();
    } else if (message.type === "CONTENT_INIT") {
      applySettings(message.displayMode, message.position, message.fontSize);
    }
  });
}
