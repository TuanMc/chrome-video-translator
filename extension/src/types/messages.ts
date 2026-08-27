import type { SourceLanguage } from "./protocol";
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
  | { type: "POPUP_START"; settings: UserSettings }
  | { type: "POPUP_STOP" }
  | { type: "POPUP_GET_STATUS" }
  | { type: "OFFSCREEN_START"; streamId: string; tabId: number; sourceLanguage: SourceLanguage }
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
