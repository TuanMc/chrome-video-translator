import { useEffect, useState } from "react";
import { SERVER_CONFIG } from "../constants";
import { loadSettings, saveSettings } from "../services/settings-storage";
import { SUBTITLE_FONT_SIZE_MAX, SUBTITLE_FONT_SIZE_MIN } from "../types/settings";
import type { DisplayMode, SubtitlePosition, UserSettings } from "../types/settings";
import type { SourceLanguage, TranslationProvider } from "../types/protocol";
import type { AckResponse, CaptureStatus, RuntimeMessage } from "../types/messages";

const LANGUAGE_OPTIONS: { value: SourceLanguage; label: string }[] = [
  { value: "en", label: "English" },
  { value: "ja", label: "日本語" },
  { value: "zh", label: "中文" },
];

// Measured directly by testing both backends on the same sentences — not a
// generic claim. See server/README.md for the full comparison.
const PROVIDER_OPTIONS: { value: TranslationProvider; label: string }[] = [
  { value: "nllb", label: "NLLB" },
  { value: "libretranslate", label: "LibreTranslate" },
];

interface ProviderAvailability {
  nllb: boolean;
  libretranslate: boolean;
}

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
  // Defaults to nllb-only-available until the health check resolves — matches
  // the common case (no LibreTranslate container running) and avoids a flash
  // of an enabled option that then gets disabled a moment later.
  const [providerAvailability, setProviderAvailability] = useState<ProviderAvailability>({
    nllb: true,
    libretranslate: false,
  });

  useEffect(() => {
    loadSettings().then(setSettings);
    chrome.runtime.sendMessage({ type: "POPUP_GET_STATUS" } satisfies RuntimeMessage).then((s: CaptureStatus) => {
      if (s) setStatus(s);
    });
    // nllb-server and libre-server are independent processes on different
    // ports (see SERVER_CONFIG) — each is checked separately since either can
    // be up without the other. Each reports readiness under its own field
    // name (nllb-server: translationModelLoaded, libre-server: translationReady).
    fetch(SERVER_CONFIG.nllb.healthUrl, { signal: AbortSignal.timeout(3000) })
      .then((res) => res.json())
      .then((health: { sttModelLoaded?: boolean; translationModelLoaded?: boolean }) => {
        setProviderAvailability((prev) => ({
          ...prev,
          nllb: Boolean(health.sttModelLoaded && health.translationModelLoaded),
        }));
      })
      .catch(() => setProviderAvailability((prev) => ({ ...prev, nllb: false })));

    fetch(SERVER_CONFIG.libretranslate.healthUrl, { signal: AbortSignal.timeout(3000) })
      .then((res) => res.json())
      .then((health: { sttModelLoaded?: boolean; translationReady?: boolean }) => {
        setProviderAvailability((prev) => ({
          ...prev,
          libretranslate: Boolean(health.sttModelLoaded && health.translationReady),
        }));
      })
      .catch(() => {
        // Most common case — libre-server is an opt-in second server most
        // users won't have running. startCapture()'s own health check
        // surfaces a real error if the user tries to start a session anyway.
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
        <p className="section-label">Source language</p>
        <div className="segmented" role="radiogroup" aria-label="Source language">
          {LANGUAGE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={settings.sourceLanguage === opt.value ? "active" : ""}
              aria-pressed={settings.sourceLanguage === opt.value}
              disabled={controlsDisabled}
              onClick={() => updateSettings({ sourceLanguage: opt.value })}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="section">
        <p className="section-label">Translation engine</p>
        <div className="segmented" role="radiogroup" aria-label="Translation engine">
          {PROVIDER_OPTIONS.map((opt) => {
            const available = providerAvailability[opt.value];
            return (
              <button
                key={opt.value}
                type="button"
                className={settings.translationProvider === opt.value ? "active" : ""}
                aria-pressed={settings.translationProvider === opt.value}
                disabled={controlsDisabled || !available}
                onClick={() => updateSettings({ translationProvider: opt.value })}
              >
                {opt.label}
                {!available ? " (off)" : ""}
              </button>
            );
          })}
        </div>
        <p className="hint-text">
          NLLB: more accurate on technical terms and Japanese. LibreTranslate: more natural on casual English
          slang/register.
        </p>
      </div>

      <div className="section">
        <p className="section-label">Subtitle</p>

        <p className="field-label">Display</p>
        <div className="segmented" role="radiogroup" aria-label="Display mode">
          {(["vietnamese", "bilingual"] as DisplayMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              className={settings.displayMode === mode ? "active" : ""}
              aria-pressed={settings.displayMode === mode}
              disabled={controlsDisabled}
              onClick={() => updateSettings({ displayMode: mode })}
            >
              {mode === "vietnamese" ? "Vietnamese" : "Bilingual"}
            </button>
          ))}
        </div>

        <p className="field-label">Text size</p>
        <div className="size-row">
          <input
            type="range"
            className="slider"
            min={SUBTITLE_FONT_SIZE_MIN}
            max={SUBTITLE_FONT_SIZE_MAX}
            value={settings.subtitleFontSize}
            disabled={controlsDisabled}
            onChange={(e) => updateSettings({ subtitleFontSize: Number(e.target.value) })}
          />
          <span className="size-value">{settings.subtitleFontSize}px</span>
        </div>

        <p className="field-label">Position</p>
        <div className="segmented" role="radiogroup" aria-label="Subtitle position">
          {(["top", "bottom"] as SubtitlePosition[]).map((pos) => (
            <button
              key={pos}
              type="button"
              className={settings.subtitlePosition === pos ? "active" : ""}
              aria-pressed={settings.subtitlePosition === pos}
              disabled={controlsDisabled}
              onClick={() => updateSettings({ subtitlePosition: pos })}
            >
              {pos === "top" ? "Top" : "Bottom"}
            </button>
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
