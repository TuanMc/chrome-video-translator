# Role

Act as a **Senior Realtime Audio Engineer, Chrome Extension Architect, and Python AI Backend Engineer**.

I already have a working Chrome Extension project for near-real-time Vietnamese subtitles.

The current system has:

* Chrome Extension
* `chrome.tabCapture`
* local audio streaming
* `faster-whisper` for speech-to-text
* two independent translation backends:

  * NLLB server
  * LibreTranslate server
* Vietnamese subtitle overlay

The current implementation works, but subtitle latency and transcript stability need improvement.

Your task is to **review and refactor the realtime audio/STT pipeline**, especially:

* audio buffering
* chunking
* VAD
* incremental transcription
* partial/final transcript handling
* translation debounce
* subtitle stability

The changes must work with **both translation servers**.

Do NOT redesign the entire application unless necessary.

---

# 1. Current Architecture

Conceptually, the system is:

```text
Chrome Extension
      ↓
chrome.tabCapture
      ↓
Audio Stream
      ↓
Local STT Backend
      ↓
faster-whisper
      ↓
Transcript
      ↓
      ├── NLLB Server
      │       ↓
      │   Vietnamese
      │
      └── LibreTranslate Server
              ↓
          Vietnamese
      ↓
Chrome Subtitle Overlay
```

There are two independent translation servers.

The user can choose which translation provider to use.

Conceptually:

```ts
type TranslationProvider =
  | "nllb"
  | "libretranslate";
```

Do not merge the two translation servers into one implementation unless there is a strong architectural reason.

The STT/audio pipeline should be shared.

---

# 2. Goal

Improve the realtime experience so that:

* subtitles appear earlier
* subtitles do not constantly rewrite unnecessarily
* sentence boundaries are more natural
* CPU usage remains reasonable
* Whisper does not repeatedly transcribe huge audio buffers
* translation is not triggered for every tiny transcript change
* the same realtime behavior works with both NLLB and LibreTranslate

Target experience:

```text
Speaker:
"We're going to create..."

~1–2 seconds

Subtitle:
"Chúng ta sẽ tạo..."

Speaker:
"We're going to create a React component."

Subtitle updates to:
"Chúng ta sẽ tạo một React component."
```

Do not promise fixed latency before benchmarking.

---

# 3. New Realtime Pipeline

Refactor toward this architecture:

```text
Chrome AudioWorklet
      ↓
small PCM frames
      ↓
WebSocket
      ↓
Backend Ring Buffer
      ↓
VAD
      ↓
Speech Segment Buffer
      ↓
Incremental faster-whisper
      ↓
Stable + Unstable Transcript
      ↓
Translation Scheduler
      ↓
      ├── NLLB
      └── LibreTranslate
      ↓
Vietnamese Partial/Final Subtitle
      ↓
Chrome Overlay
```

The important architectural separation should be:

```text
Audio processing
      ↓
STT
      ↓
Transcript stabilization
      ↓
Translation scheduling
      ↓
Translation provider
```

Do not let NLLB- or LibreTranslate-specific logic leak into VAD/STT logic.

---

# 4. Audio Format

Use a consistent audio format for STT:

```text
16 kHz
mono
PCM16
```

Prefer binary WebSocket frames.

Do NOT send audio as Base64 JSON unless the current implementation absolutely requires it.

The Chrome side should stream small audio frames.

Recommended baseline:

```text
20–40 ms per audio frame
```

For example:

```text
16 kHz × 20 ms
≈ 320 samples
```

The audio chunk size used for transport is NOT the same thing as the Whisper transcription window.

Keep them separate.

---

# 5. AudioWorklet

Prefer `AudioWorklet` over deprecated or high-latency audio processing APIs.

Responsibilities:

```text
Captured tab MediaStream
      ↓
AudioWorklet
      ↓
Downmix stereo → mono
      ↓
Resample if required
      ↓
PCM16
      ↓
20–40 ms frames
      ↓
WebSocket
```

The user must continue hearing original tab audio while translation runs.

Ensure capture does not mute normal playback.

---

# 6. Ring Buffer

Add or improve a server-side audio ring buffer.

The ring buffer should keep a small amount of audio before VAD detects speech.

Baseline:

```text
pre-roll:
~250 ms
```

Reason:

VAD may detect speech slightly after the first phoneme.

Without pre-roll:

```text
"We're going to..."
 ↑
first word may be clipped
```

With pre-roll:

```text
last ~250 ms
      +
detected speech
      ↓
complete speech segment
```

Make this configurable.

---

# 7. VAD

Use or evaluate **Silero VAD**.

Do not finalize a segment immediately on a single low speech probability frame.

Use hysteresis / timing rules.

Recommended starting values:

```text
Speech start:
speech probability > ~0.6
for ~100–200 ms

Speech end:
speech probability < ~0.35
for ~400–700 ms
```

Example:

```text
"Today we're going to"

200 ms pause

"build a React component"
```

This should usually remain one segment.

Do NOT split on very short pauses.

Make thresholds configurable.

---

# 8. VAD State Machine

Implement a clear state model such as:

```text
IDLE
 ↓
POSSIBLE_SPEECH
 ↓
SPEAKING
 ↓
POSSIBLE_SILENCE
 ↓
FINALIZE_SEGMENT
```

Avoid scattered boolean flags such as:

```text
isTalking
hasSpeech
waitForSilence
probablyDone
```

Prefer one explicit state machine.

Document transitions.

---

# 9. Incremental Transcription

Do NOT wait until VAD reports the end of a full sentence before running Whisper.

While the user is speaking, run incremental transcription periodically.

Recommended starting interval:

```text
~600–800 ms
```

Example:

```text
0.8 sec
"We're going to"
      ↓
Whisper

1.6 sec
"We're going to create a"
      ↓
Whisper

2.4 sec
"We're going to create a React component"
      ↓
Whisper
```

This enables partial subtitles.

---

# 10. Do Not Retranscribe Unlimited Audio

Avoid:

```text
0–1 sec
0–2 sec
0–3 sec
0–4 sec
0–5 sec
...
```

This becomes increasingly expensive.

Use a sliding transcription window.

Recommended starting configuration:

```text
Sliding audio window:
~4 seconds

Overlap:
~500 ms
```

Conceptually:

```text
stable transcript
      +
recent overlapping audio
      ↓
Whisper
```

Reuse stable text/context when useful.

Do not continuously re-run Whisper over 20–30 seconds of previous audio.

---

# 11. Stable Prefix Detection

Implement transcript stabilization.

Example:

```text
Result 1:
We're going to create

Result 2:
We're going to create a React

Result 3:
We're going to create a React component
```

Stable portion:

```text
We're going to create
```

Unstable portion:

```text
a React component
```

Use an approach such as:

* longest common prefix
* token-level prefix stability
* repeated agreement across consecutive Whisper results

Prefer token/word-level logic instead of raw character-level comparison where practical.

Maintain conceptually:

```ts
interface IncrementalTranscript {
  stableText: string;
  unstableText: string;
  fullText: string;
  final: boolean;
}
```

Do not append every partial result to transcript history.

---

# 12. Partial vs Final Transcript

Support two states.

Partial:

```json
{
  "type": "transcript",
  "text": "We're going to create...",
  "final": false
}
```

Final:

```json
{
  "type": "transcript",
  "text": "We're going to create a React component.",
  "final": true
}
```

A final segment may be triggered by:

```text
VAD silence > threshold

OR

clear sentence-ending punctuation

OR

maximum speech segment duration reached
```

Recommended maximum speech segment duration:

```text
~6–8 seconds
```

Do not allow indefinitely long segments.

---

# 13. Forced Segment Split

If a speaker talks continuously for a long time, force a split.

Example:

```text
speech
speech
speech
speech
speech
...
> 6–8 sec
```

Prefer to split near:

* punctuation
* word boundary
* short pause

rather than cutting arbitrarily mid-word.

---

# 14. Translation Scheduling

Do NOT translate every Whisper update.

For example, avoid:

```text
Whisper every 500 ms
      ↓
NLLB every 500 ms
```

or:

```text
Whisper every 500 ms
      ↓
LibreTranslate every 500 ms
```

This wastes CPU and causes subtitle flicker.

Add a translation scheduler/debounce layer.

Recommended baseline:

```text
Whisper update:
~600–800 ms

Partial translation:
~800–1200 ms

Final translation:
immediate
```

A partial translation should run if one of these is true:

```text
enough new content was added

OR

translation debounce interval elapsed

OR

segment became final
```

Example heuristic:

```text
Translate if:

new transcript has >= 3 meaningful new words

OR

> ~900 ms since last translation

OR

final == true
```

For Japanese and Chinese, do not rely only on whitespace-based word count.

Use a language-aware notion of meaningful text growth.

---

# 15. Provider-independent Translation Scheduler

Create a shared translation scheduling layer.

Conceptually:

```text
Incremental Transcript
       ↓
TranslationScheduler
       ↓
TranslationProvider
       ↓
Vietnamese subtitle
```

Do NOT duplicate scheduling logic inside:

```text
NLLB server

and

LibreTranslate server
```

The same decision rules should apply to both providers.

Only provider execution should differ.

---

# 16. Translation Provider Interface

Keep a provider abstraction.

Conceptually:

```ts
interface TranslationProvider {
  translate(request: {
    text: string;
    sourceLanguage: "en" | "ja" | "zh";
    targetLanguage: "vi";
    final: boolean;
  }): Promise<TranslationResult>;
}
```

Implementations:

```text
TranslationProvider
├── NLLBTranslationProvider
└── LibreTranslateProvider
```

If the two translation services remain separate HTTP servers, keep adapters such as:

```text
NLLBTranslationClient

LibreTranslateClient
```

Do not rewrite provider-independent logic twice.

---

# 17. NLLB Server Changes

Review the current NLLB translation server.

Apply the new realtime protocol and scheduling requirements.

NLLB-specific considerations:

* model should remain loaded in memory
* do not reload model per request
* avoid translating extremely small fragments
* minimize repeated translation of nearly identical text
* keep input length subtitle-friendly
* preserve technical names where possible

Examples:

```text
React
TypeScript
Docker
AWS
Kubernetes
API
```

Avoid unnecessary translation of product/library names.

---

# 18. LibreTranslate Server Changes

Apply equivalent realtime behavior to the LibreTranslate path.

Important:

The final Chrome UX should not behave differently simply because the user selected LibreTranslate instead of NLLB.

Both should receive equivalent stabilized transcript requests.

Conceptually:

```text
Stable transcript
       ↓
TranslationScheduler
       ↓
       ├── NLLB server
       └── LibreTranslate server
```

LibreTranslate-specific considerations:

* minimize repeated HTTP calls
* reuse HTTP sessions/connections
* avoid translating tiny fragments
* handle timeout/failure cleanly
* keep server local
* do not run language detection because user manually selects the source language

---

# 19. English/Japanese/Chinese Tuning

Support separate default timing policies.

Suggested starting point:

```text
English

Whisper incremental:
~600–700 ms

Translation debounce:
~800–900 ms
```

```text
Chinese

Whisper incremental:
~700–800 ms

Translation debounce:
~900–1000 ms
```

```text
Japanese

Whisper incremental:
~800–1000 ms

Translation debounce:
~1000–1200 ms
```

Japanese may require slightly more context because important grammatical information often appears near the end of the phrase.

Do not hard-code these values deeply.

Create configuration such as:

```ts
interface RealtimeLanguageConfig {
  transcriptionIntervalMs: number;
  translationDebounceMs: number;
  silenceFinalizeMs: number;
  maxSegmentDurationMs: number;
}
```

Keep language-specific tuning configurable.

---

# 20. Subtitle Updates

Avoid visual flickering.

If the current partial subtitle is:

```text
Chúng ta sẽ tạo...
```

and the next version is:

```text
Chúng ta sẽ tạo một React component.
```

replace the current subtitle.

Do NOT render:

```text
Chúng ta sẽ tạo...
Chúng ta sẽ tạo một...
Chúng ta sẽ tạo một React...
Chúng ta sẽ tạo một React component...
```

as separate subtitle entries.

Maintain one active partial subtitle per speech segment.

Final subtitles may then replace or finalize that active item.

---

# 21. Suggested Subtitle Event

Use something conceptually similar to:

```ts
interface SubtitleEvent {
  segmentId: string;

  original: string;

  translated: string;

  final: boolean;

  provider:
    | "nllb"
    | "libretranslate";

  timestamps?: {
    audioStartedAt?: number;
    transcriptionCompletedAt?: number;
    translationCompletedAt?: number;
  };
}
```

`segmentId` is important so the Chrome overlay knows whether to:

```text
replace existing partial

or

start a new subtitle segment
```

---

# 22. Segment IDs

Generate a stable ID per speech segment.

Example:

```text
segment-001

partial update 1
segment-001

partial update 2
segment-001

final update
segment-001

next speech
segment-002
```

Do not generate a new ID for every incremental update.

---

# 23. Latency Instrumentation

Add development metrics.

Track:

```text
audio capture time

speech detected time

STT started

STT completed

translation started

translation completed

subtitle rendered
```

Calculate:

```text
STT latency

translation latency

backend latency

total subtitle latency
```

Do this for both:

```text
NLLB

LibreTranslate
```

so we can compare them objectively.

---

# 24. Provider Benchmark

Add or propose a simple development benchmark.

For the same stabilized transcript:

```text
NLLB
vs
LibreTranslate
```

Measure:

```text
translation latency

output quality

CPU usage

RAM usage
```

Do not assume which provider is faster before testing.

---

# 25. Suggested Default Configuration

Start with approximately:

```text
Audio:
16 kHz
mono
PCM16
20–40 ms frames

VAD:
pre-roll: 250 ms
speech start confirmation: 150 ms
silence finalize: 500 ms

Whisper:
incremental interval: 700 ms
sliding window: 4 sec
overlap: 500 ms
max segment: 6 sec

Translation:
partial debounce: 900 ms
final translation: immediate
```

These are baseline values only.

Move them into configuration.

Do not scatter magic numbers through the codebase.

---

# 26. Config Structure

Prefer something like:

```ts
const realtimeConfig = {
  audio: {
    sampleRate: 16000,
    channels: 1,
    frameDurationMs: 20,
    preRollMs: 250,
  },

  vad: {
    speechStartThreshold: 0.6,
    speechEndThreshold: 0.35,
    speechStartConfirmationMs: 150,
    silenceFinalizeMs: 500,
  },

  transcription: {
    intervalMs: 700,
    slidingWindowMs: 4000,
    overlapMs: 500,
    maxSegmentMs: 6000,
  },

  translation: {
    partialDebounceMs: 900,
  },
};
```

Language-specific overrides may then apply.

---

# 27. Error Handling

Handle independently:

```text
STT failure

NLLB failure

LibreTranslate failure

WebSocket disconnect

VAD failure

translation timeout
```

Translation-provider failures must not corrupt STT state.

Example:

```text
Whisper still works

NLLB temporarily fails

→ show translation error
→ preserve current speech/transcript state
→ allow retry or next segment
```

Do not unnecessarily reset the entire audio pipeline for a translation error.

---

# 28. Resource Management

Ensure proper cleanup when Stop is clicked:

```text
stop MediaStream tracks

stop AudioWorklet

close AudioContext

close STT WebSocket

clear ring buffers

clear VAD state

cancel pending STT jobs

cancel translation debounce timers

cancel outstanding NLLB requests

cancel outstanding LibreTranslate requests where possible

clear active segment

remove/hide subtitle overlay
```

Do not leak timers/tasks across sessions.

---

# 29. Concurrency

Prevent stale async responses from overwriting newer subtitle state.

Example:

```text
Request A
partial:
"We're going to"

Request B
partial:
"We're going to build React"

B completes first

A completes afterward
```

A must NOT overwrite B.

Use:

```text
segmentId

sequence number

revision number

or timestamp
```

Example:

```ts
interface TranslationRequest {
  segmentId: string;
  revision: number;
}
```

Only display the newest valid revision.

This must work for both NLLB and LibreTranslate.

---

# 30. Backpressure

Consider what happens if:

```text
Whisper produces updates faster than translation can complete.
```

Do not build an unlimited translation queue.

Prefer:

```text
latest partial wins
```

For partial translations:

* cancel or ignore obsolete requests
* keep at most the newest relevant pending partial
* always prioritize final translations

Conceptually:

```text
partial 1
partial 2
partial 3

translator busy

→ discard/ignore 1 and 2
→ process latest 3
```

Final segments must not be dropped.

---

# 31. Important Japanese Consideration

Japanese partial transcription may frequently change before the end of a phrase.

Do not aggressively translate every Japanese partial.

Prefer:

```text
slightly longer debounce

more stable prefix

punctuation/silence-aware finalization
```

The UI should prioritize stable subtitles over maximum update frequency.

---

# 32. Expected Result

The final architecture should resemble:

```text
Chrome AudioWorklet
       ↓
20–40 ms PCM16 frames
       ↓
WebSocket
       ↓
Ring Buffer
       ↓
Silero VAD
       ↓
Speech Segment
       ↓
Incremental faster-whisper
       ↓
Stable Prefix Detection
       ↓
Transcript Revision
       ↓
Translation Scheduler
       ↓
       ├───────────────┐
       ▼               ▼
NLLB Client      LibreTranslate Client
       │               │
       └───────┬───────┘
               ↓
       Subtitle Event
               ↓
       Chrome Overlay
```

---

# 33. Required First Step

Do NOT immediately rewrite everything.

First inspect the existing implementation and respond with:

1. Current audio capture flow.
2. Current chunk size/audio format.
3. Current WebSocket protocol.
4. Current Whisper transcription strategy.
5. Whether VAD already exists.
6. Current segment finalization logic.
7. Current NLLB integration.
8. Current LibreTranslate integration.
9. Which logic is duplicated between NLLB and LibreTranslate.
10. Where translation scheduling currently occurs.
11. Current causes of latency.
12. Current causes of subtitle flickering/rewrite.
13. Risk of stale async translation responses.
14. Proposed refactor plan.
15. Files/modules that need modification.
16. New modules that should be introduced.
17. Configuration changes.
18. Migration plan that minimizes breakage.

Clearly separate:

## Existing behavior

## Problems identified

## Proposed architecture

## Files to modify

## New modules

## Risks

## Validation plan

Then STOP and wait for my approval.

---

# 34. Validation Plan

After implementation, verify the complete pipeline with:

### English → Vietnamese

* continuous speaking
* normal pauses
* fast speech
* technical video

### Japanese → Vietnamese

* normal conversation
* long Japanese sentence
* short pauses
* English technical terms mixed into Japanese

### Chinese → Vietnamese

* Mandarin speech
* continuous speaking
* technical terms

For each language test both:

```text
NLLB

LibreTranslate
```

Record:

```text
First partial subtitle latency

Final subtitle latency

STT latency

Translation latency

Subtitle stability

CPU usage

RAM usage
```

Compare NLLB and LibreTranslate using the exact same STT transcript whenever possible.

---

# 35. Success Criteria

The refactor is successful if:

```text
✓ short audio frames are streamed continuously

✓ VAD reliably detects speech boundaries

✓ short pauses do not unnecessarily split sentences

✓ Whisper produces incremental transcripts

✓ stable transcript portions are preserved

✓ Whisper does not repeatedly process unlimited audio history

✓ translation is debounced

✓ NLLB and LibreTranslate share the same scheduling logic

✓ both providers support partial and final subtitle updates

✓ stale translations cannot overwrite newer subtitles

✓ translation queues cannot grow without bounds

✓ final translations are prioritized

✓ subtitles visually replace partial text instead of duplicating it

✓ EN / JA / ZH can use different realtime tuning

✓ realtime timing values are configurable

✓ latency can be measured

✓ NLLB and LibreTranslate can be benchmarked fairly
```

---

# Final Engineering Principle

Optimize the system in this order:

```text
Audio segmentation
        ↓
VAD quality
        ↓
Incremental STT
        ↓
Transcript stability
        ↓
Translation scheduling
        ↓
Translation provider performance
        ↓
Subtitle rendering
```

Do not attempt to solve realtime latency only by switching translation providers.

The goal is to make the entire pipeline behave as a coherent realtime subtitle system while keeping **NLLB and LibreTranslate as two independent, interchangeable translation backends**.
