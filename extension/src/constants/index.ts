import type { TranslationProvider } from "../types/protocol";

export const OFFSCREEN_DOCUMENT_PATH = "src/offscreen/offscreen.html";
export const CONTENT_SCRIPT_PATH = "assets/content-script.js";
export const CAPTURE_STATUS_STORAGE_KEY = "captureStatus";

// Three independent local servers, one per translation backend (see
// nllb-server/, libre-server/, soniox-server/) — each runs standalone on its
// own port so any combination can run at once and the popup can pick
// per-session which to use.
export const SERVER_CONFIG: Record<TranslationProvider, { origin: string; healthUrl: string; wsUrl: string }> = {
  nllb: {
    origin: "http://127.0.0.1:8000",
    healthUrl: "http://127.0.0.1:8000/health",
    wsUrl: "ws://127.0.0.1:8000/ws/translate",
  },
  libretranslate: {
    origin: "http://127.0.0.1:8001",
    healthUrl: "http://127.0.0.1:8001/health",
    wsUrl: "ws://127.0.0.1:8001/ws/translate",
  },
  // Cloud-based (Soniox), unlike the other two — see soniox-server/README.md.
  soniox: {
    origin: "http://127.0.0.1:8002",
    healthUrl: "http://127.0.0.1:8002/health",
    wsUrl: "ws://127.0.0.1:8002/ws/translate",
  },
};

export const UNSUPPORTED_URL_PREFIXES = [
  "chrome://",
  "chrome-extension://",
  "edge://",
  "about:",
  "https://chrome.google.com/webstore",
];
