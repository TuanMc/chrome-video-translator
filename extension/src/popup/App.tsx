import { useEffect, useState } from "react";
import { loadSettings, saveSettings } from "../services/settings-storage";
import { SUBTITLE_FONT_SIZE_MAX, SUBTITLE_FONT_SIZE_MIN } from "../types/settings";
import type { DisplayMode, SubtitlePosition, UserSettings } from "../types/settings";
import type { SourceLanguage } from "../types/protocol";
import type { AckResponse, CaptureStatus, RuntimeMessage } from "../types/messages";

const LANGUAGE_OPTIONS: { value: SourceLanguage; label: string }[] = [
  { value: "en", label: "English" },
  { value: "ja", label: "日本語" },
  { value: "zh", label: "中文" },
];

const STATUS_LABEL: Record<CaptureStatus["state"], string> = {
  idle: "Idle",
  connecting: "Connecting…",
  listening: "Listening",
  translating: "Translating…",
  stopping: "Stopping…",
  error: "Error",
};

export default function App() {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [status, setStatus] = useState<CaptureStatus>({ state: "idle" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    loadSettings().then(setSettings);
    chrome.runtime.sendMessage({ type: "POPUP_GET_STATUS" } satisfies RuntimeMessage).then((s: CaptureStatus) => {
      if (s) setStatus(s);
    });

    const listener = (message: RuntimeMessage) => {
      if (message.type === "STATUS_UPDATE") {
        setStatus(message.status);
      }
    };
    chrome.runtime.onMessage.addListener(listener);
    return () => chrome.runtime.onMessage.removeListener(listener);
  }, []);

  const isActive = status.state === "connecting" || status.state === "listening" || status.state === "translating";
  const controlsDisabled = isActive || status.state === "stopping";

  function updateSettings(patch: Partial<UserSettings>): void {
    if (!settings) return;
    const next = { ...settings, ...patch };
    setSettings(next);
    saveSettings(next);
  }

  const handleClick = async () => {
    if (!settings) return;
    setBusy(true);
    try {
      if (isActive) {
        const res = (await chrome.runtime.sendMessage({ type: "POPUP_STOP" } satisfies RuntimeMessage)) as AckResponse;
        if (!res.ok) setStatus({ state: "error", error: res.error });
      } else {
        const res = (await chrome.runtime.sendMessage({
          type: "POPUP_START",
          settings,
        } satisfies RuntimeMessage)) as AckResponse;
        if (!res.ok) setStatus({ state: "error", error: res.error });
      }
    } catch (err) {
      // The service worker didn't respond at all (e.g. it was killed mid-request) —
      // without this, the failure would be a silent unhandled rejection and the
      // popup would just sit there giving no feedback.
      setStatus({
        state: "error",
        error: err instanceof Error ? err.message : "Lost contact with the extension background.",
      });
    } finally {
      setBusy(false);
    }
  };

  if (!settings) return null;

  return (
    <div className="popup">
      <p className="title">VIDEO TRANSLATOR</p>
      <p className="subtitle">Real-time Vietnamese subtitles</p>

      <div className="section">
        <label className="section-label" htmlFor="source-language">
          SOURCE LANGUAGE
        </label>
        <select
          id="source-language"
          className="select"
          value={settings.sourceLanguage}
          disabled={controlsDisabled}
          onChange={(e) => updateSettings({ sourceLanguage: e.target.value as SourceLanguage })}
        >
          {LANGUAGE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div className="section">
        <p className="section-label">SUBTITLE</p>

        <p className="field-label">Display</p>
        <div className="radio-row">
          {(["vietnamese", "bilingual"] as DisplayMode[]).map((mode) => (
            <label key={mode} className="radio-option">
              <input
                type="radio"
                name="displayMode"
                checked={settings.displayMode === mode}
                disabled={controlsDisabled}
                onChange={() => updateSettings({ displayMode: mode })}
              />
              {mode === "vietnamese" ? "Vietnamese" : "Bilingual"}
            </label>
          ))}
        </div>

        <p className="field-label">Text size</p>
        <input
          type="range"
          className="slider"
          min={SUBTITLE_FONT_SIZE_MIN}
          max={SUBTITLE_FONT_SIZE_MAX}
          value={settings.subtitleFontSize}
          disabled={controlsDisabled}
          onChange={(e) => updateSettings({ subtitleFontSize: Number(e.target.value) })}
        />

        <p className="field-label">Position</p>
        <div className="radio-row">
          {(["top", "bottom"] as SubtitlePosition[]).map((pos) => (
            <label key={pos} className="radio-option">
              <input
                type="radio"
                name="position"
                checked={settings.subtitlePosition === pos}
                disabled={controlsDisabled}
                onChange={() => updateSettings({ subtitlePosition: pos })}
              />
              {pos === "top" ? "Top" : "Bottom"}
            </label>
          ))}
        </div>
      </div>

      <div className={`status-row ${status.state}`}>
        <span className={`status-dot ${status.state}`} />
        <span>{STATUS_LABEL[status.state]}</span>
      </div>

      {status.state === "error" && status.error && <p className="error-text">{status.error}</p>}

      <button
        className={`primary ${isActive ? "stop" : ""}`}
        disabled={busy || status.state === "stopping"}
        onClick={handleClick}
      >
        {status.state === "stopping" ? "Stopping…" : isActive ? "■ STOP TRANSLATION" : "START TRANSLATION"}
      </button>
    </div>
  );
}
