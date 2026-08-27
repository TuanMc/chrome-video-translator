import type { SourceLanguage, TranslationProvider } from "./protocol";
import type { DisplayMode, SubtitlePosition, UserSettings } from "./settings";

// Matches requirement.md section 23, minus "transcribing" — the server never
// actually emits a discrete signal for that (STT runs continuously as part of
// "listening"), so it's not included rather than faked.
export type CaptureState = "idle" | "connecting" | "listening" | "translating" | "stopping" | "error";

export interface CaptureStatus {
  state: CaptureState;
  tabId?: number;
  error?: string;
}

export type RuntimeMessage =
  // tabId is captured by the popup itself, as close as possible to the user's
  // icon-click that granted activeTab (see App.tsx) — NOT re-derived later in
  // the background script via a fresh "active tab" query. activeTab is tied
  // to the specific tab that was active at the moment of that click; if the
  // background script re-queries "the active tab" after an async gap (a
  // message round-trip plus whatever else runs before tabCapture), a page
  // that opens its own new tab/window in that window (common on ad-heavy
  // sites) can make a *different* tab "active" by then — one activeTab was
  // never granted for — producing tabCapture's cryptic "Extension has not
  // been invoked for the current page" error on an otherwise-supported page.
  | { type: "POPUP_START"; settings: UserSettings; tabId: number }
  | { type: "POPUP_STOP" }
  | { type: "POPUP_GET_STATUS" }
  | {
      type: "OFFSCREEN_START";
      streamId: string;
      tabId: number;
      sourceLanguage: SourceLanguage;
      translationProvider: TranslationProvider;
    }
  | { type: "OFFSCREEN_STOP" }
  | { type: "OFFSCREEN_SUBTITLE"; original: string; translated: string }
  | { type: "OFFSCREEN_STATUS"; status: "listening" | "translating" }
  | { type: "OFFSCREEN_ERROR"; message: string }
  | { type: "STATUS_UPDATE"; status: CaptureStatus }
  | { type: "CONTENT_INIT"; displayMode: DisplayMode; position: SubtitlePosition; fontSize: number }
  | { type: "SUBTITLE_UPDATE"; original: string; translated: string }
  | { type: "SUBTITLE_CLEAR" };

export interface AckResponse {
  ok: boolean;
  error?: string;
}
