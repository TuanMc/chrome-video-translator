# Role

Act as a **Senior Chrome Extension Architect, React/TypeScript Engineer, and Python AI Engineer**.

Your task is to design and implement an MVP Chrome Extension that generates **near-real-time Vietnamese subtitles from audio playing in the current Chrome tab**.

The solution must be:

* Platform-independent
* Local-first
* Free of paid AI APIs
* Privacy-friendly
* Extensible
* Optimized for low subtitle latency

Do not build specifically for YouTube.

The extension should work with normal video/audio websites wherever Chrome allows tab audio capture.

---

# 1. Product Goal

Build a Chrome Extension that converts:

```text
Video/audio playing in current tab
              ↓
        Speech recognition
              ↓
       Original transcript
              ↓
    Vietnamese translation
              ↓
       Subtitle overlay
```

Primary use cases include:

* YouTube
* Udemy
* Coursera
* Vimeo
* Facebook
* News websites
* Training websites
* HTML5 video players
* Other websites playing audio/video

Do not depend on:

* YouTube APIs
* YouTube captions
* Website subtitle APIs
* Specific `<video>` DOM structures

The source of truth is the **audio captured from the current Chrome tab**.

---

# 2. MVP Languages

The user manually selects the source language.

Support:

```ts
type SourceLanguage =
  | "en"
  | "ja"
  | "zh";
```

UI labels:

```text
English
日本語
中文
```

Target language is always:

```text
Vietnamese
vi
```

Do NOT implement automatic language detection for the MVP.

---

# 3. Local-Only AI Requirement

The MVP must NOT use paid external AI APIs.

Do NOT use:

* OpenAI API
* Claude API
* Google Cloud Speech
* Azure Speech
* DeepL API
* Other paid AI APIs

Run AI models locally.

Use:

### Speech-to-Text

`faster-whisper`

### Translation

`facebook/nllb-200-distilled-600M`

### Backend

Python + FastAPI

### Realtime communication

WebSocket

The goal is:

```text
External AI API cost = $0
```

Internet access may be required initially to download models/dependencies, but normal translation/transcription should run locally afterward.

---

# 4. High-Level Architecture

Use this architecture:

```text
┌───────────────────────────────┐
│       Chrome Extension        │
│                               │
│ React + TypeScript            │
│ Manifest V3                   │
└───────────────┬───────────────┘
                │
         chrome.tabCapture
                │
                ▼
        Tab Audio Stream
                │
                ▼
      Audio Processing Layer
                │
                │ WebSocket
                ▼
┌───────────────────────────────┐
│      Local Python Server      │
│                               │
│ FastAPI                       │
│ WebSocket                     │
│                               │
│        audio stream           │
│             ↓                 │
│      faster-whisper           │
│             ↓                 │
│        transcript             │
│             ↓                 │
│          NLLB-200             │
│             ↓                 │
│      Vietnamese text          │
└───────────────┬───────────────┘
                │
              WS
                │
                ▼
┌───────────────────────────────┐
│       Content Script          │
│                               │
│     Shadow DOM Overlay        │
│                               │
│   Vietnamese Subtitle         │
└───────────────────────────────┘
```

---

# 5. Chrome Extension Stack

Use:

* Chrome Manifest V3
* React
* TypeScript
* Vite
* Chrome Extension APIs
* Shadow DOM

Recommended structure:

```text
extension/
├── src/
│   ├── background/
│   │   └── service-worker.ts
│   │
│   ├── offscreen/
│   │   ├── offscreen.html
│   │   └── audio-capture.ts
│   │
│   ├── content/
│   │   ├── content-script.ts
│   │   ├── create-shadow-root.ts
│   │   └── subtitle-overlay.tsx
│   │
│   ├── popup/
│   │   ├── App.tsx
│   │   └── components/
│   │
│   ├── services/
│   │   └── websocket.ts
│   │
│   ├── hooks/
│   ├── types/
│   ├── constants/
│   └── utils/
│
├── manifest.json
├── vite.config.ts
└── package.json
```

You may modify this structure when technically justified.

---

# 6. Local Backend Structure

Recommended structure:

```text
server/
├── app/
│   ├── main.py
│   │
│   ├── websocket/
│   │   └── translation_socket.py
│   │
│   ├── providers/
│   │   ├── speech_to_text/
│   │   │   ├── base.py
│   │   │   └── faster_whisper.py
│   │   │
│   │   └── translation/
│   │       ├── base.py
│   │       └── nllb.py
│   │
│   ├── services/
│   │   ├── transcription_service.py
│   │   └── translation_service.py
│   │
│   ├── models/
│   ├── config/
│   └── utils/
│
├── requirements.txt
└── README.md
```

Keep AI provider implementations separated from application logic.

---

# 7. Provider Abstraction

Even though the MVP uses local models, avoid tightly coupling the application to them.

Create an STT abstraction conceptually similar to:

```ts
interface SpeechToTextProvider {
  start(language: SourceLanguage): Promise<void>;

  sendAudio(chunk: ArrayBuffer): void;

  stop(): Promise<void>;
}
```

Initial implementation:

```text
SpeechToTextProvider
        │
        └── FasterWhisperProvider
```

Translation abstraction:

```ts
interface TranslationProvider {
  translate(
    text: string,
    sourceLanguage: SourceLanguage,
    context?: string[],
  ): Promise<string>;
}
```

Initial implementation:

```text
TranslationProvider
        │
        └── NLLBTranslationProvider
```

The architecture should allow future implementations such as:

```text
SpeechToTextProvider
├── FasterWhisperProvider
├── OpenAIProvider
├── AzureProvider
└── GoogleProvider

TranslationProvider
├── NLLBProvider
├── GPTProvider
├── ClaudeProvider
└── DeepLProvider
```

Do NOT implement the cloud providers now.

---

# 8. faster-whisper

Use `faster-whisper` for local speech recognition.

The language is already known because the user selects it.

Pass the selected language to Whisper rather than performing automatic language detection.

Example:

```text
User selected:
日本語

       ↓

language = "ja"

       ↓

faster-whisper
```

Support:

```text
en
ja
zh
```

Choose an appropriate Whisper model for MVP development.

Start with a model that provides a reasonable balance between:

* Latency
* Accuracy
* RAM/VRAM
* CPU performance
* GPU performance

Do NOT assume that every user has an NVIDIA GPU.

The application should be able to run on CPU.

If CUDA is available, allow faster-whisper to use it.

Make model/device configuration easy to change.

---

# 9. NLLB Translation

Use:

`facebook/nllb-200-distilled-600M`

for translation.

Language mapping:

```ts
const NLLB_LANGUAGE_MAP = {
  en: "eng_Latn",
  ja: "jpn_Jpan",
  zh: "zho_Hans",
  vi: "vie_Latn",
};
```

Pipeline:

```text
Whisper transcript

"We're going to create a component."

                ↓

NLLB

                ↓

"Chúng ta sẽ tạo một component."
```

Japanese:

```text
今日はReactについて勉強します。

              ↓

NLLB

              ↓

Hôm nay chúng ta sẽ học về React.
```

Chinese:

```text
今天我们来学习 React。

              ↓

NLLB

              ↓

Hôm nay chúng ta sẽ học về React.
```

---

# 10. Translation Context

Design the system so a small amount of previous context can be maintained.

For example:

```text
Segment N-2
Segment N-1
Segment N
```

However, NLLB is not an LLM.

Do NOT blindly concatenate large amounts of context if that degrades translation quality.

Investigate and propose the safest strategy for subtitle translation.

Prioritize:

1. Correct meaning
2. Natural Vietnamese
3. Technical terminology
4. Proper nouns
5. Short subtitle-friendly output
6. Low latency

Explain any limitations NLLB introduces compared with LLM-based translation.

---

# 11. Audio Capture

Use:

`chrome.tabCapture`

The user flow:

```text
Open video
    ↓
Click extension
    ↓
Select language
    ↓
START TRANSLATION
    ↓
capture current tab audio
```

Important requirement:

**The user must continue hearing the video's original audio while translation is running.**

Do not accidentally mute tab audio because its MediaStream is being captured.

Use Web Audio APIs where necessary:

```text
Captured MediaStream
       │
       ├── Local audio output
       │
       └── STT processing
```

---

# 12. Offscreen Document

Because this is Manifest V3, investigate the correct use of:

`chrome.offscreen`

for handling the captured audio stream.

Do not attempt to perform media processing directly inside the service worker if Chrome does not support it reliably.

Clearly define responsibilities between:

```text
Popup
Service Worker
Offscreen Document
Content Script
Local Backend
```

---

# 13. Audio Format

Determine an efficient format for transferring audio from Chrome to the Python server.

Investigate:

* PCM
* mono vs stereo
* sample rate
* chunk size
* WebSocket binary frames

Whisper should not receive unnecessary stereo/high-sample-rate audio if it can work efficiently with something such as:

```text
16 kHz
mono
PCM
```

Prefer WebSocket binary frames for audio rather than encoding audio into JSON/Base64.

Optimize for:

* low latency
* low CPU usage
* low memory usage
* simple backend decoding

---

# 14. Streaming Strategy

Do NOT implement:

```text
record 30 seconds
       ↓
upload
       ↓
transcribe
       ↓
translate
```

Subtitle latency would be unacceptable.

Design a streaming/chunking strategy.

Conceptually:

```text
audio
 │
 ├── chunk
 ├── chunk
 ├── chunk
 ├── chunk
 │
 ▼
buffer
 │
 ▼
faster-whisper
 │
 ▼
transcript segment
 │
 ▼
NLLB
 │
 ▼
subtitle
```

Investigate appropriate:

* Audio chunk size
* Whisper buffer duration
* Sliding window
* Voice activity detection
* Silence detection
* Segment finalization

The goal is near-real-time subtitles without repeatedly retranscribing huge amounts of audio.

---

# 15. Latency

Latency is a major MVP metric.

Measure:

```text
Speech occurs
     ↓
Audio captured
     ↓
STT
     ↓
Translation
     ↓
Subtitle received
     ↓
Subtitle rendered
```

Track timestamps so development builds can measure:

```text
STT latency
Translation latency
Total subtitle latency
```

Do not claim a guaranteed latency before benchmarking.

---

# 16. WebSocket Protocol

Use typed messages.

Client control messages:

```ts
type ClientControlMessage =
  | {
      type: "start";
      sourceLanguage: SourceLanguage;
    }
  | {
      type: "stop";
    };
```

Send audio using WebSocket binary frames.

Server messages:

```ts
type ServerMessage =
  | {
      type: "ready";
    }
  | {
      type: "transcript";
      text: string;
      language: SourceLanguage;
      final: boolean;
    }
  | {
      type: "subtitle";
      original: string;
      translated: string;
      final: boolean;
    }
  | {
      type: "status";
      status:
        | "listening"
        | "transcribing"
        | "translating";
    }
  | {
      type: "error";
      code: string;
      message: string;
    };
```

Avoid arbitrary untyped WebSocket payloads.

---

# 17. Subtitle Overlay

Do NOT rely on:

```js
document.querySelector("video")
```

The extension should inject a page-level overlay.

Use:

```text
document
   │
   └── extension host element
            │
            ▼
        Shadow Root
            │
            ▼
        React Root
            │
            ▼
     SubtitleOverlay
```

Shadow DOM is required to minimize CSS conflicts with host websites.

Use:

```css
pointer-events: none;
z-index: 2147483647;
```

The overlay should remain visible above normal page/video content where Chrome permits it.

---

# 18. Subtitle Modes

Support:

## Vietnamese

```text
Chúng ta sẽ tạo một React component mới.
```

## Bilingual

```text
We're going to create a new React component.

Chúng ta sẽ tạo một React component mới.
```

For Japanese:

```text
今日はReactについて勉強します。

Hôm nay chúng ta sẽ học về React.
```

For Chinese:

```text
今天我们来学习 React。

Hôm nay chúng ta sẽ học về React.
```

The Vietnamese translation should have stronger visual emphasis.

---

# 19. Popup Design

Use a minimalist dark design.

Primary requirements:

```text
Background: BLACK
Text: WHITE
```

Example:

```text
┌──────────────────────────────────────┐
│                                      │
│  VIDEO TRANSLATOR                    │
│  Real-time Vietnamese subtitles      │
│                                      │
│  SOURCE LANGUAGE                     │
│                                      │
│  ┌────────────────────────────────┐  │
│  │ English                      ▼ │  │
│  └────────────────────────────────┘  │
│                                      │
│  English    日本語    中文             │
│                                      │
│  SUBTITLE                            │
│                                      │
│  Display                             │
│  ● Vietnamese     ○ Bilingual        │
│                                      │
│  Text size                           │
│  ─────────────●────────              │
│                                      │
│  Position                            │
│  ○ Top            ● Bottom           │
│                                      │
│  ┌────────────────────────────────┐  │
│  │       START TRANSLATION        │  │
│  └────────────────────────────────┘  │
│                                      │
└──────────────────────────────────────┘
```

---

# 20. Design Tokens

Use approximately:

```css
:root {
  --background: #000000;

  --surface: #121212;
  --surface-hover: #1c1c1c;

  --text-primary: #ffffff;
  --text-secondary: #a1a1aa;
  --text-disabled: #666666;

  --border: #27272a;

  --button-primary-background: #ffffff;
  --button-primary-text: #000000;
}
```

Avoid:

* gradients
* excessive colors
* decorative animations
* unnecessary shadows
* complex visual effects

Keep the UI primarily:

```text
Black
White
Gray
```

Semantic colors may be used sparingly for errors/status.

---

# 21. Subtitle Design

Default:

```css
.subtitle-container {
  position: fixed;

  left: 50%;
  bottom: 10%;

  transform: translateX(-50%);

  max-width: 80%;

  padding: 10px 16px;

  background: rgba(0, 0, 0, 0.75);
  color: #ffffff;

  border-radius: 6px;

  backdrop-filter: blur(4px);

  text-align: center;

  z-index: 2147483647;

  pointer-events: none;
}
```

Original text:

```css
.original {
  color: rgba(255, 255, 255, 0.65);
  font-size: 18px;
}
```

Vietnamese:

```css
.translation {
  color: #ffffff;
  font-size: 24px;
  font-weight: 600;
}
```

---

# 22. User Settings

Persist settings with:

`chrome.storage`

Model:

```ts
interface UserSettings {
  sourceLanguage:
    | "en"
    | "ja"
    | "zh";

  displayMode:
    | "vietnamese"
    | "bilingual";

  subtitlePosition:
    | "top"
    | "bottom";

  subtitleFontSize: number;
}
```

Default:

```ts
{
  sourceLanguage: "en",
  displayMode: "vietnamese",
  subtitlePosition: "bottom",
  subtitleFontSize: 24
}
```

---

# 23. Runtime State

Support:

```text
Idle
Connecting
Listening
Transcribing
Translating
Error
```

When idle:

```text
START TRANSLATION
```

When running:

```text
■ STOP TRANSLATION
```

Display useful status information without cluttering the UI.

---

# 24. Local Server Detection

The extension depends on the local AI server.

Before starting translation:

```text
Extension
    ↓
localhost health check
    ↓
Server running?
   /        \
 YES         NO
 │            │
Start       Show setup
```

Provide an endpoint such as:

```text
GET /health
```

Return useful information:

```json
{
  "status": "ok",
  "sttModelLoaded": true,
  "translationModelLoaded": true,
  "device": "cuda"
}
```

If the server is unavailable, show a clear message rather than failing silently.

---

# 25. Model Loading

Local AI models can take time to load.

Do NOT reload:

```text
Whisper
NLLB
```

for every subtitle segment.

Models should be initialized once and reused.

Consider:

```text
Server startup
      ↓
Load models
      ↓
Ready
      ↓
Multiple translation segments
```

Also consider lazy loading if startup time becomes problematic.

Explain the chosen strategy.

---

# 26. CPU/GPU Support

Support CPU as the baseline.

Detect/use CUDA when available.

Configuration should allow something conceptually similar to:

```text
DEVICE=auto

auto
cpu
cuda
```

Potential future support may include additional acceleration backends.

Do not make CUDA mandatory.

---

# 27. Error Handling

Handle:

* Local server unavailable
* Model download missing
* Model loading failure
* No active tab
* Unsupported Chrome page
* Tab capture failure
* No audio
* WebSocket disconnect
* STT failure
* Translation failure
* Invalid language
* User stops translation
* Tab closes
* Tab navigates away

Never leave capture/resources running after failure.

---

# 28. Resource Cleanup

When translation stops:

```text
Stop MediaStream tracks
        ↓
Close AudioContext
        ↓
Stop AudioWorklet/processor
        ↓
Close WebSocket
        ↓
Clear buffers
        ↓
Remove unnecessary listeners
        ↓
Hide/remove subtitle overlay
```

Avoid memory leaks.

---

# 29. Privacy

This is a local-first application.

Normal operation should be:

```text
Video audio
     ↓
localhost
     ↓
Local Whisper
     ↓
Local NLLB
```

Audio and transcript should NOT leave the user's machine.

Do not persist:

* captured audio
* transcripts
* translations

unless a future feature explicitly requires it.

Avoid unnecessary logging of transcript content.

---

# 30. MVP Scope

Implement:

* Chrome Manifest V3
* React + TypeScript + Vite
* Black/white popup UI
* Manual EN / JA / ZH selection
* `chrome.tabCapture`
* Original audio remains audible
* Offscreen audio processing
* WebSocket binary audio streaming
* Local FastAPI server
* faster-whisper STT
* NLLB-200 distilled 600M translation
* Vietnamese subtitle overlay
* Shadow DOM isolation
* Vietnamese-only mode
* Bilingual mode
* Subtitle font-size setting
* Top/bottom position
* Settings persistence
* Start/Stop
* Local server health check
* CPU support
* CUDA acceleration when available
* Error handling
* Resource cleanup
* Basic latency measurement

---

# 31. NOT MVP

Do NOT implement yet:

* Auto language detection
* Voice dubbing
* User accounts
* Cloud storage
* Translation history
* Subtitle export
* Speaker identification
* Mobile support
* Cloud AI providers
* Website-specific caption extraction
* Korean/French/Thai/etc.
* Complex settings UI

Do not over-engineer these future features.

---

# 32. P0 Implementation Order

Do NOT build everything simultaneously.

## POC 1 — Tab Audio

Prove:

```text
Chrome tab
    ↓
tabCapture
    ↓
audio available
    ↓
user can still hear audio
```

Do not continue until this works reliably.

---

## POC 2 — Chrome → Python

Prove:

```text
Tab audio
    ↓
WebSocket
    ↓
FastAPI
```

Verify audio format and realtime delivery.

---

## POC 3 — Speech Recognition

Add:

```text
Audio
  ↓
faster-whisper
  ↓
Original transcript
```

Test separately with:

```text
English
Japanese
Chinese
```

Measure latency.

---

## POC 4 — Translation

Add:

```text
Transcript
    ↓
NLLB-200
    ↓
Vietnamese
```

Test:

```text
EN → VI
JA → VI
ZH → VI
```

Evaluate both latency and translation quality.

---

## POC 5 — Subtitle

Complete:

```text
Audio
 ↓
Whisper
 ↓
Transcript
 ↓
NLLB
 ↓
Vietnamese
 ↓
WebSocket
 ↓
Chrome
 ↓
Overlay
```

Only after this pipeline works should you spend significant time polishing the popup/settings UI.

---

# 33. Performance Testing

For each language, benchmark:

```text
EN → VI
JA → VI
ZH → VI
```

Measure:

```text
STT latency
Translation latency
Total subtitle latency
CPU usage
RAM usage
GPU usage
VRAM usage
```

Test at least:

```text
Whisper tiny
Whisper base
Whisper small
```

Then recommend the best default model for the MVP based on actual results rather than assumptions.

---

# 34. Translation Quality Testing

Prepare representative test cases for:

### English

* Normal conversation
* Software/technical video
* Fast speech

### Japanese

* Normal conversation
* Anime/drama-style dialogue
* Technical explanation
* English technical terms embedded in Japanese

### Chinese

* Mandarin conversation
* Technical explanation
* English technical terms embedded in Chinese

Evaluate whether NLLB preserves terms such as:

```text
React
TypeScript
API
component
AWS
Docker
Kubernetes
```

Avoid translating technical product/library names incorrectly.

---

# 35. Important Engineering Principles

Follow:

* KISS
* Separation of concerns
* Provider abstraction
* Type safety
* Minimal Chrome permissions
* Local-first privacy
* Resource cleanup
* Low latency over premature feature richness
* Measure before optimizing

Do not introduce unnecessary frameworks or infrastructure.

---

# 36. First Response Required

Do NOT start generating the entire codebase immediately.

Your first response must contain:

1. Your understanding of the product.
2. Architecture review.
3. Any Chrome Manifest V3 limitations or risks.
4. How `chrome.tabCapture` + offscreen document should work.
5. Proposed audio format and streaming strategy.
6. Proposed faster-whisper configuration.
7. Proposed NLLB configuration.
8. Expected CPU/GPU requirements.
9. Major latency risks.
10. Project structure.
11. WebSocket protocol.
12. POC implementation plan.
13. Technical risks that should be validated before full implementation.
14. Any changes you recommend to these requirements.

Clearly separate:

**Confirmed approach**

from:

**Needs proof-of-concept / benchmarking**

Do not present estimated performance as guaranteed performance.

After presenting the architecture and POC plan:

**STOP and wait for my approval before implementing the code.**

---

# Final Goal

The final MVP should provide this experience:

```text
User opens any supported video website
              ↓
Opens Chrome Extension
              ↓
Selects

English
日本語
or
中文

              ↓
Clicks START TRANSLATION
              ↓
Extension captures tab audio
              ↓
Local faster-whisper
              ↓
Local NLLB-200
              ↓
Vietnamese translation
              ↓
Subtitle appears over webpage

┌───────────────────────────────────────────────┐
│                                               │
│                  VIDEO                        │
│                                               │
│                                               │
│        Hôm nay chúng ta sẽ học React.         │
│                                               │
└───────────────────────────────────────────────┘
```

The most important product requirements are:

> **Platform-independent, EN/JA/ZH → Vietnamese, near-real-time subtitles, black/white UI, local AI processing, privacy-friendly, and no paid AI API required for normal operation.**
