import { SERVER_CONFIG } from "../constants";
import { TranslationSocket } from "../services/websocket";
import type { AckResponse, RuntimeMessage } from "../types/messages";
import type { SourceLanguage, TranslationProvider } from "../types/protocol";

// Chrome's tab-capture constraints aren't part of the standard MediaTrackConstraints
// lib types, so they're declared locally and cast at the getUserMedia call site.
interface ChromeTabCaptureConstraints {
  audio: {
    mandatory: {
      chromeMediaSource: "tab";
      chromeMediaSourceId: string;
    };
  };
}

let stream: MediaStream | null = null;
let audioContext: AudioContext | null = null;
let sourceNode: MediaStreamAudioSourceNode | null = null;
let workletNode: AudioWorkletNode | null = null;
let silentGainNode: GainNode | null = null;
let socket: TranslationSocket | null = null;
let chunksSent = 0;
// Distinguishes "we called stop()" from "the connection died on its own" —
// only the latter should be reported up as an error (requirement.md section 27:
// "WebSocket disconnected").
let intentionalStop = false;
// Most recent `{type: "error"}` protocol message from the server (see
// app/models/protocol.py's ServerError on any of the three servers). Per-
// segment STT/translation failures are documented as non-fatal — "the next
// scheduled pass retries... session continues" — so receiving one must NOT
// by itself end the session. But a server can also send an error right
// before closing the connection for a genuinely fatal reason (e.g.
// soniox-server closing on a bad/invalid API key) — in that case the
// WebSocket's own onclose handler below already ends the session; this just
// lets it use the server's specific, actionable message instead of the
// generic "Connection to the local server was lost." fallback.
let lastServerErrorMessage: string | null = null;

function setStatusText(text: string): void {
  const el = document.getElementById("status");
  if (el) el.textContent = text;
  console.log(`[offscreen] ${text}`);
}

async function startCapture(
  streamId: string,
  sourceLanguage: SourceLanguage,
  translationProvider: TranslationProvider,
): Promise<void> {
  if (stream) {
    throw new Error("Capture already in progress.");
  }
  intentionalStop = false;
  lastServerErrorMessage = null;

  // Everything here can fail partway through (worklet module missing, WS
  // connect failing, etc.) after stream/audioContext are already live. Without
  // this boundary, a failure would leave those module-level vars non-null,
  // and the guard above would then permanently block any retry with "Capture
  // already in progress" until the extension is reloaded.
  try {
    const constraints: ChromeTabCaptureConstraints = {
      audio: {
        mandatory: {
          chromeMediaSource: "tab",
          chromeMediaSourceId: streamId,
        },
      },
    };

    stream = await navigator.mediaDevices.getUserMedia(constraints as unknown as MediaStreamConstraints);

    audioContext = new AudioContext();
    sourceNode = audioContext.createMediaStreamSource(stream);
    // Route the captured audio straight back out so the user keeps hearing the tab —
    // capturing a tab's MediaStream silences its normal output unless we do this.
    sourceNode.connect(audioContext.destination);

    await audioContext.audioWorklet.addModule(chrome.runtime.getURL("assets/pcm-processor.js"));
    workletNode = new AudioWorkletNode(audioContext, "pcm-processor");
    sourceNode.connect(workletNode);
    // The worklet's own output carries no audio (it only posts PCM chunks over its
    // port) — but it still needs a path to destination to stay in the render graph.
    silentGainNode = audioContext.createGain();
    silentGainNode.gain.value = 0;
    workletNode.connect(silentGainNode);
    silentGainNode.connect(audioContext.destination);

    chunksSent = 0;
    socket = new TranslationSocket(SERVER_CONFIG[translationProvider].wsUrl, {
      onServerMessage: (message) => {
        console.log("[offscreen] server:", message);
        if (message.type === "subtitle") {
          chrome.runtime
            .sendMessage({
              type: "OFFSCREEN_SUBTITLE",
              original: message.original,
              translated: message.translated,
            } satisfies RuntimeMessage)
            .catch(() => {});
        } else if (message.type === "status" && (message.status === "listening" || message.status === "translating")) {
          chrome.runtime
            .sendMessage({ type: "OFFSCREEN_STATUS", status: message.status } satisfies RuntimeMessage)
            .catch(() => {});
        } else if (message.type === "error") {
          // Non-fatal by itself (see lastServerErrorMessage's comment above) —
          // just remembered here and surfaced in the debug status line. If
          // it turns out to have been fatal, the server closes the
          // connection right after, and onClose below uses this message.
          console.warn("[offscreen] server error:", message.code, message.message);
          lastServerErrorMessage = message.message;
          setStatusText(`server reported an error: ${message.message}`);
        }
      },
      onError: () => {
        setStatusText("error: could not reach local server");
        handleUnexpectedDisconnect("Could not reach the local server.").catch(() => {});
      },
      onClose: () => {
        console.log("[offscreen] websocket closed");
        if (!intentionalStop) {
          handleUnexpectedDisconnect(lastServerErrorMessage ?? "Connection to the local server was lost.").catch(() => {});
        }
      },
    });
    await socket.connect({ type: "start", sourceLanguage });

    workletNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      socket?.sendAudio(event.data);
      chunksSent += 1;
      setStatusText(`capturing — ${chunksSent} chunks sent`);
    };

    // If the tab stops sharing (e.g. the tab was closed) the track ends on its own;
    // treat that the same as an explicit stop so we don't leak resources. Marked
    // intentional so the WebSocket's resulting close doesn't also get reported as
    // an unexpected-disconnect error — the tab closing is already handled
    // separately (service-worker.ts's chrome.tabs.onRemoved).
    stream.getAudioTracks()[0]?.addEventListener("ended", () => {
      intentionalStop = true;
      stopCapture().catch(() => {});
    });

    setStatusText("capturing (audio routed back to speakers)");
  } catch (err) {
    // Guarded so a failure during cleanup can't mask the original, more useful error.
    await stopCapture().catch(() => {});
    throw err;
  }
}

let stopping = false;

async function stopCapture(): Promise<void> {
  // Re-entrancy guard: without it, two near-simultaneous triggers (e.g. an
  // explicit Stop racing an external track-ended event) could both reach
  // `audioContext.close()` on the same context while the first call is still
  // awaiting it.
  if (stopping) return;
  stopping = true;
  try {
    socket?.stop();
    socket?.close();
    socket = null;

    workletNode?.disconnect();
    workletNode = null;
    silentGainNode?.disconnect();
    silentGainNode = null;

    sourceNode?.disconnect();
    sourceNode = null;

    stream?.getTracks().forEach((track) => track.stop());
    stream = null;

    if (audioContext) {
      await audioContext.close();
      audioContext = null;
    }

    setStatusText("idle");
  } finally {
    stopping = false;
  }
}

// The connection died on its own (server crashed, network dropped) rather than
// via an explicit Stop click. Clean up locally — capturing into a dead socket
// forever, with no subtitles and no visible error, is exactly the "indefinitely
// stuck" failure mode requirement.md warns against — then tell the service
// worker so it can update the popup and close the offscreen document.
async function handleUnexpectedDisconnect(message: string): Promise<void> {
  if (!stream) return; // already stopped/cleaned up — avoid a duplicate report
  await stopCapture();
  chrome.runtime.sendMessage({ type: "OFFSCREEN_ERROR", message } satisfies RuntimeMessage).catch(() => {});
}

chrome.runtime.onMessage.addListener((message: RuntimeMessage, _sender, sendResponse) => {
  if (message.type === "OFFSCREEN_START") {
    startCapture(message.streamId, message.sourceLanguage, message.translationProvider)
      .then(() => sendResponse({ ok: true } satisfies AckResponse))
      .catch((err: Error) => {
        setStatusText(`error: ${err.message}`);
        sendResponse({ ok: false, error: err.message } satisfies AckResponse);
      });
    return true;
  }

  if (message.type === "OFFSCREEN_STOP") {
    intentionalStop = true;
    stopCapture()
      .then(() => sendResponse({ ok: true } satisfies AckResponse))
      .catch((err: Error) => sendResponse({ ok: false, error: err.message } satisfies AckResponse));
    return true;
  }

  return false;
});
