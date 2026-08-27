import { DEFAULT_USER_SETTINGS } from "../types/settings";
import type { UserSettings } from "../types/settings";

const STORAGE_KEY = "userSettings";

// chrome.storage.local (not .sync) — deliberate, matches this project's
// local-first/privacy-first stance (requirement.md section 29): nothing
// about this extension should depend on or flow through Google's account
// sync infrastructure, even something as low-stakes as UI preferences.
export async function loadSettings(): Promise<UserSettings> {
  const result = await chrome.storage.local.get(STORAGE_KEY);
  const stored = result[STORAGE_KEY] as Partial<UserSettings> | undefined;
  return { ...DEFAULT_USER_SETTINGS, ...stored };
}

export async function saveSettings(settings: UserSettings): Promise<void> {
  await chrome.storage.local.set({ [STORAGE_KEY]: settings });
}
