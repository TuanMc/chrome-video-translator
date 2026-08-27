# API Documentation

Both servers expose the identical surface — one WebSocket endpoint and one REST health-check endpoint. Message shapes are defined once in `app/models/protocol.py` (Python/Pydantic) and mirrored in `extension/src/types/protocol.ts` (TypeScript) — the two must be kept in sync by hand.

## WebSocket API

### `ws://127.0.0.1:{8000|8001}/ws/translate`

**Client → Server messages** (JSON text frames, except audio which is binary):

| Type | Shape | Notes |
|---|---|---|
| `start` | `{ type: "start", sourceLanguage: "en" \| "ja" \| "zh" }` | Must be the first message sent after connecting. |
| *(binary)* | raw PCM16 mono 16kHz bytes | No envelope — sent as WebSocket binary frames, one per ~200ms audio batch. |
| `stop` | `{ type: "stop" }` | Triggers a final flush of any buffered audio before the connection closes. |

**Server → Client messages**:

| Type | Shape | Notes |
|---|---|---|
| `ready` | `{ type: "ready" }` | Sent once, after `start` is accepted and the STT provider is initialized for this session. |
| `status` | `{ type: "status", status: "listening" \| "transcribing" \| "translating" }` | `"transcribing"` is defined in the protocol but never actually emitted (the server has no discrete signal for it). |
| `transcript` | `{ type: "transcript", segmentId, text, language, final, ts }` | Emitted on every STT pass. `final: false` = in-progress/partial (not translated); `final: true` = the segment is settled and translation will follow. |
| `subtitle` | `{ type: "subtitle", segmentId, original, translated, final, ts }` | Emitted once per finalized segment, after translation completes. |
| `error` | `{ type: "error", code, message }` | Non-fatal for `STT_ERROR`/`TRANSLATION_ERROR` (session continues); `SERVER_ERROR`/`PROTOCOL_ERROR` end the session. |

**Error codes seen in practice**: `PROTOCOL_ERROR` (first message wasn't `start`), `STT_ERROR`, `TRANSLATION_ERROR`, `SERVER_ERROR`, `TRANSLATION_PROVIDER_UNAVAILABLE` (requested engine unreachable — not currently applicable now that each server only ever uses its own single backend).

## REST API

### `GET /health`

Response shape **differs between the two servers** because they represent readiness differently:

**nllb-server** (in-process model — readiness is a one-time load flag):
```json
{
  "status": "ok",
  "sttModelLoaded": true,
  "translationModelLoaded": true,
  "device": "cpu"
}
```

**libre-server** (remote HTTP dependency — readiness is checked live on every call):
```json
{
  "status": "ok",
  "sttModelLoaded": true,
  "translationReady": true,
  "device": "cpu"
}
```

The extension's popup and service worker both know to check the field appropriate to the server they're querying (`translationModelLoaded` vs `translationReady`).

## Internal APIs (Python)

### `SpeechToTextProvider` (`providers/speech_to_text/base.py`)
```python
class SpeechToTextProvider(ABC):
    def on_transcript(self, callback: TranscriptCallback) -> None: ...
    def on_error(self, callback: ErrorCallback) -> None: ...
    async def start(self, language: str) -> None: ...
    def send_audio(self, chunk: bytes) -> None: ...
    async def stop(self) -> None: ...
```
- **Implementation**: `FasterWhisperProvider` (identical in both servers).

### `TranslationProvider` (`providers/translation/base.py`)
```python
class TranslationProvider(ABC):
    async def translate(self, text: str, source_language: str, context: Optional[List[str]] = None) -> str: ...
```
- **Implementations**: `NLLBTranslationProvider` (nllb-server), `LibreTranslateProvider` (libre-server, plus an `is_reachable()` helper used by `/health`).
- `context` is part of the interface for a possible future LLM-based provider but is intentionally unused by both current implementations — neither NLLB nor LibreTranslate is designed to consume multi-turn context.

## Internal APIs (TypeScript)

### `TranslationSocket` (`extension/src/services/websocket.ts`)
```ts
class TranslationSocket {
  connect(start: { type: "start"; sourceLanguage: SourceLanguage }): Promise<void>;
  sendAudio(chunk: ArrayBuffer): void;
  stop(): void;
  close(): void;
}
```

## Data Models

### `UserSettings` (`extension/src/types/settings.ts`)
- `sourceLanguage: "en" | "ja" | "zh"`
- `translationProvider: "nllb" | "libretranslate"`
- `displayMode: "vietnamese" | "bilingual"`
- `subtitlePosition: "top" | "bottom"`
- `subtitleFontSize: number` (16-32)
- Persisted via `chrome.storage.local` (deliberately not `.sync` — nothing should route through Google account sync, per the project's privacy stance).

### `CaptureStatus` (`extension/src/types/messages.ts`)
- `state: "idle" | "connecting" | "listening" | "translating" | "stopping" | "error"`
- `tabId?: number`, `error?: string`

### `TranscriptResult` (server, `providers/speech_to_text/base.py`)
- `text: str`, `language: str`, `is_final: bool`, `segment_id: str`
