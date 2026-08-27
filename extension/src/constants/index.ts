export const OFFSCREEN_DOCUMENT_PATH = "src/offscreen/offscreen.html";
export const CONTENT_SCRIPT_PATH = "assets/content-script.js";
export const CAPTURE_STATUS_STORAGE_KEY = "captureStatus";

export const LOCAL_SERVER_ORIGIN = "http://127.0.0.1:8000";
export const LOCAL_SERVER_HEALTH_URL = `${LOCAL_SERVER_ORIGIN}/health`;
export const TRANSLATION_WS_URL = "ws://127.0.0.1:8000/ws/translate";

export const UNSUPPORTED_URL_PREFIXES = [
  "chrome://",
  "chrome-extension://",
  "edge://",
  "about:",
  "https://chrome.google.com/webstore",
];
