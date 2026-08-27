import type { SourceLanguage, TranslationProvider } from "./protocol";

export type DisplayMode = "vietnamese" | "bilingual";
export type SubtitlePosition = "top" | "bottom";

export interface UserSettings {
  sourceLanguage: SourceLanguage;
  translationProvider: TranslationProvider;
  displayMode: DisplayMode;
  subtitlePosition: SubtitlePosition;
  subtitleFontSize: number;
}

export const DEFAULT_USER_SETTINGS: UserSettings = {
  sourceLanguage: "en",
  translationProvider: "nllb",
  displayMode: "vietnamese",
  subtitlePosition: "bottom",
  subtitleFontSize: 24,
};

export const SUBTITLE_FONT_SIZE_MIN = 16;
export const SUBTITLE_FONT_SIZE_MAX = 32;
