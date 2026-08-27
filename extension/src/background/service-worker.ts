import {
  OFFSCREEN_DOCUMENT_PATH,
  CONTENT_SCRIPT_PATH,
  CAPTURE_STATUS_STORAGE_KEY,
  UNSUPPORTED_URL_PREFIXES,
  SERVER_CONFIG,
} from "../constants";
import type { AckResponse, CaptureStatus, RuntimeMessage } from "../types/messages";
import type { TranslationProvider } from "../types/protocol";
import type { UserSettings } from "../types/settings";
import { withTimeout } from "../utils/timeout";

async function setStatus(status: CaptureStatus): Promise<void> {
  await chrome.storage.session.set({ [CAPTURE_STATUS_STORAGE_KEY]: status });
  // Best-effort broadcast to an open popup. Throws if nobody is listening — ignore.
  chrome.runtime.sendMessage({ type: "STATUS_UPDATE", status } satisfies RuntimeMessage).catch(() => {});
}

async function getStatus(): Promise<CaptureStatus> {
  const result = await chrome.storage.session.get(CAPTURE_STATUS_STORAGE_KEY);
  return (result[CAPTURE_STATUS_STORAGE_KEY] as CaptureStatus | undefined) ?? { state: "idle" };
}

async function hasOffscreenDocument(): Promise<boolean> {
  const contexts = await chrome.runtime.getContexts({
    contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT],
    documentUrls: [chrome.runtime.getURL(OFFSCREEN_DOCUMENT_PATH)],
  });
  return contexts.length > 0;
}

async function ensureOffscreenDocument(): Promise<void> {
  if (await hasOffscreenDocument()) return;
  await chrome.offscreen.createDocument({
    url: OFFSCREEN_DOCUMENT_PATH,
    reasons: [chrome.offscreen.Reason.USER_MEDIA],
    justification:
      "Capture current tab audio for speech-to-text streaming while routing it back to the speakers.",
  });
}

async function closeOffscreenDocument(): Promise<void> {
  if (await hasOffscreenDocument()) {
    await chrome.offscreen.closeDocument();
  }
}

async function getActiveTab(): Promise<chrome.tabs.Tab> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || tab.id === undefined) {
    throw new Error("No active tab found.");
  }
  if (!tab.url || UNSUPPORTED_URL_PREFIXES.some((prefix) => tab.url!.startsWith(prefix))) {
    throw new Error("This page is not supported (browser/extension pages cannot be captured).");
  }
  return tab;
}

const SERVER_FOLDER: Record<TranslationProvider, string> = {
  nllb: "nllb-server",
  libretranslate: "libre-server",
};

// requirement.md section 24: check the local server before attempting to start,
// rather than discovering it's down partway through tabCapture/offscreen setup.
// nllb-server and libre-server are independent processes (see SERVER_CONFIG) —
// only the one for the selected engine needs to be up.
async function checkLocalServer(translationProvider: TranslationProvider): Promise<void> {
  const { healthUrl, origin } = SERVER_CONFIG[translationProvider];
  let response: Response;
  try {
    response = await fetch(healthUrl, { signal: AbortSignal.timeout(3000) });
  } catch {
    throw new Error(
      `${SERVER_FOLDER[translationProvider]} is not running at ${origin}. Start it with: ` +
        `cd ${SERVER_FOLDER[translationProvider]} && .venv/bin/uvicorn app.main:app --port ${new URL(origin).port}`,
    );
  }
  if (!response.ok) {
    throw new Error(`${SERVER_FOLDER[translationProvider]} returned an error (HTTP ${response.status}).`);
  }
  const health = (await response.json()) as {
    sttModelLoaded?: boolean;
    translationModelLoaded?: boolean; // nllb-server
    translationReady?: boolean; // libre-server
  };
  const translationOk = translationProvider === "nllb" ? health.translationModelLoaded : health.translationReady;
  if (!health.sttModelLoaded || !translationOk) {
    throw new Error(`${SERVER_FOLDER[translationProvider]} is still loading/reachable — wait a moment and try again.`);
  }
}

async function startCapture(settings: UserSettings): Promise<void> {
  await setStatus({ state: "connecting" });

  await checkLocalServer(settings.translationProvider);
  const tab = await getActiveTab();

  await ensureOffscreenDocument();
  // Everything below can fail in ways that would otherwise leave the offscreen
  // document (and its idle audio-capture context) dangling until the next
  // start attempt — one boundary that closes it on any failure, rather than a
  // `closeOffscreenDocument()` scattered into every individual catch.
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id! }, files: [CONTENT_SCRIPT_PATH] });
    await chrome.tabs
      .sendMessage(tab.id!, {
        type: "CONTENT_INIT",
        displayMode: settings.displayMode,
        position: settings.subtitlePosition,
        fontSize: settings.subtitleFontSize,
      } satisfies RuntimeMessage)
      .catch(() => {});

    let streamId: string;
    try {
      streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });
    } catch (err) {
      throw new Error(
        `Could not capture this tab's audio (${err instanceof Error ? err.message : "unknown reason"}). ` +
          "This can happen on protected/DRM content or if the capture permission was denied.",
      );
    }

    const response = (await withTimeout(
      chrome.runtime.sendMessage({
        type: "OFFSCREEN_START",
        streamId,
        tabId: tab.id!,
        sourceLanguage: settings.sourceLanguage,
        translationProvider: settings.translationProvider,
      } satisfies RuntimeMessage),
      10000,
      "Audio capture setup did not respond in time.",
    ).catch((err: Error) => ({ ok: false, error: err.message }) as AckResponse)) as AckResponse | undefined;

    if (!response?.ok) {
      throw new Error(response?.error ?? "Offscreen document failed to start capture.");
    }
  } catch (err) {
    await closeOffscreenDocument();
    throw err;
  }

  await setStatus({ state: "listening", tabId: tab.id });
}

// Tears down the offscreen document and clears the on-page overlay, without
// touching status — callers decide the final status (idle vs error) so a
// forced stop doesn't flash "idle" for a moment before "error" replaces it.
async function cleanupSession(tabId: number | undefined): Promise<void> {
  if (await hasOffscreenDocument()) {
    await chrome.runtime.sendMessage({ type: "OFFSCREEN_STOP" } satisfies RuntimeMessage).catch(() => {});
    await closeOffscreenDocument();
  }
  if (tabId !== undefined) {
    chrome.tabs.sendMessage(tabId, { type: "SUBTITLE_CLEAR" } satisfies RuntimeMessage).catch(() => {});
  }
}

async function stopCapture(): Promise<void> {
  const previous = await getStatus();
  await setStatus({ state: "stopping", tabId: previous.tabId });
  await cleanupSession(previous.tabId);
  await setStatus({ state: "idle" });
}

function isActive(state: CaptureStatus["state"]): boolean {
  return state === "connecting" || state === "listening" || state === "translating";
}

chrome.runtime.onMessage.addListener((message: RuntimeMessage, _sender, sendResponse) => {
  if (message.type === "POPUP_START") {
    startCapture(message.settings)
      .then(() => sendResponse({ ok: true } satisfies AckResponse))
      .catch((err: Error) => {
        setStatus({ state: "error", error: err.message });
        sendResponse({ ok: false, error: err.message } satisfies AckResponse);
      });
    return true;
  }

  if (message.type === "POPUP_STOP") {
    stopCapture()
      .then(() => sendResponse({ ok: true } satisfies AckResponse))
      .catch((err: Error) => sendResponse({ ok: false, error: err.message } satisfies AckResponse));
    return true;
  }

  if (message.type === "POPUP_GET_STATUS") {
    getStatus().then((status) => sendResponse(status));
    return true;
  }

  if (message.type === "OFFSCREEN_SUBTITLE") {
    getStatus().then((status) => {
      if (status.tabId !== undefined) {
        chrome.tabs
          .sendMessage(status.tabId, {
            type: "SUBTITLE_UPDATE",
            original: message.original,
            translated: message.translated,
          } satisfies RuntimeMessage)
          .catch(() => {});
      }
    });
    return false;
  }

  if (message.type === "OFFSCREEN_STATUS") {
    getStatus().then((status) => {
      if (isActive(status.state)) {
        setStatus({ state: message.status, tabId: status.tabId });
      }
    });
    return false;
  }

  if (message.type === "OFFSCREEN_ERROR") {
    // The offscreen document has already cleaned up its own local audio/WS
    // resources by the time this arrives (see handleUnexpectedDisconnect in
    // audio-capture.ts) — this still needs to close the offscreen document
    // itself and clear the on-page overlay.
    getStatus().then(async (status) => {
      if (!isActive(status.state)) return;
      await cleanupSession(status.tabId).catch(() => {});
      await setStatus({ state: "error", error: message.message, tabId: status.tabId });
    });
    return false;
  }

  return false;
});

// If Chrome kills the offscreen document unexpectedly (or the tab closes), don't leave
// the popup showing a stale "listening"/"translating" state.
chrome.tabs.onRemoved.addListener(async (tabId) => {
  const status = await getStatus();
  if (isActive(status.state) && status.tabId === tabId) {
    await stopCapture().catch(() => {});
  }
});

// The content script (and its Shadow DOM overlay) is destroyed on navigation —
// continuing to capture into a dead tab would just silently fail. Stop cleanly
// and surface it as an error instead (requirement.md section 27).
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo) => {
  const status = await getStatus();
  if (isActive(status.state) && status.tabId === tabId && changeInfo.status === "loading") {
    await cleanupSession(status.tabId).catch(() => {});
    await setStatus({ state: "error", error: "Tab navigated away; capture stopped.", tabId: status.tabId });
  }
});
