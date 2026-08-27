# Local Server — POC4

FastAPI WebSocket server. Accepts the typed `start` / binary-audio / `stop`
protocol, tracks basic timing stats, writes received audio to a `.wav` file
for debugging, runs the audio through `faster-whisper` using a sliding-window
streaming scheme (requirement.md section 14) sending `transcript` messages
(partial, then `final: true` on a pause), and now translates each finalized
segment with `facebook/nllb-200-distilled-600M`, sending a `subtitle` message
(`original` + `translated`) once translation completes.

## Setup

```bash
cd server
python3 -m venv .venv        # requires a Python with a working `venv`/ensurepip
.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch
.venv/bin/pip install -r requirements.txt
```

If `python3 -m venv` fails with an `ensurepip is not available` error, use a
Python installation that has pip built in (this repo's dev venv was created
with `pyenv`'s 3.9.25 build for exactly this reason — check `pyenv versions`).

Torch is installed separately from the CPU-only wheel index — a plain
`pip install torch` (or just listing it in requirements.txt) pulls the much
larger CUDA-bundled build. If you actually have a CUDA GPU and want it used,
install the matching CUDA build from pytorch.org instead of the command above.

## Run

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Model loading happens once at startup and can take anywhere from a few seconds
to ~1-2 minutes (first run downloads the model from Hugging Face; afterwards
it's cached locally, but even a cached load can occasionally take longer if
its metadata check to huggingface.co is slow — that's a network hiccup, not a
code issue). Watch the terminal for `Model ready.` before testing.

Tip: once you've downloaded a model at least once, set `HF_HUB_OFFLINE=1` to
skip Hugging Face's metadata check on every startup (it occasionally hangs for
a while even though the model itself is already cached locally):
```bash
HF_HUB_OFFLINE=1 .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Verify it's up:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","sttModelLoaded":true,"translationModelLoaded":true,"device":"cpu"}
```

NLLB is a larger download (~2.4GB) and slower to load than Whisper — first-run
setup for both models together can take a few minutes.

### Configuration (env vars)

| Var | Default | Notes |
|---|---|---|
| `WHISPER_MODEL_SIZE` | `base` | `tiny`/`base`/`small` (or any faster-whisper size) — see benchmark below |
| `WHISPER_DEVICE` | `auto` | `auto`/`cpu`/`cuda` — auto tries CUDA, falls back to CPU if unavailable |
| `WHISPER_COMPUTE_TYPE` | *(auto)* | int8 on CPU, float16 on CUDA, unless overridden |
| `WHISPER_TRIGGER_SECONDS` | `1.0` | how much new audio triggers a re-transcription pass |
| `WHISPER_SILENCE_FINALIZE_SECONDS` | `0.4` | trailing silence (via Whisper's VAD) needed to finalize a segment — the "1s target" dial, see below |
| `WHISPER_MAX_BUFFER_SECONDS` | `5.0` | force-finalize continuous speech (no pause found) after this long — the meaning-vs-speed dial, see below |
| `WHISPER_WORD_SAFETY_MARGIN_SECONDS` | `0.3` | how much trailing audio a word needs after it before force-finalize trusts it as complete |
| `WHISPER_HARD_MAX_BUFFER_SECONDS` | `8.0` | absolute ceiling — force-clears even without a safe word boundary, so continuous speech can never get stuck never finalizing |
| `WHISPER_INITIAL_PROMPT` | *(tech vocab list)* | biases recognition toward known terms — see "Meaning vs. speed" below |
| `WHISPER_NO_SPEECH_PROB_THRESHOLD` | `0.4` | drops segments Whisper itself flags as likely non-speech (hallucination mitigation) |
| `NLLB_DEVICE` | `auto` | `auto`/`cpu`/`cuda` |
| `NLLB_QUANTIZE_CPU` | `true` | dynamic int8 quantization on CPU — measured 2.5x faster translation with no meaningful quality loss, see below |
| `SAVE_DEBUG_AUDIO` | `false` | opt-in only — set `true` to save `.wav` files for verifying the capture pipeline by ear (see Privacy below) |

## POC3 benchmark results

Measured on this dev sandbox: 8-core Intel i5-1135G7, **CPU only** (no CUDA
available here), using synthetic TTS audio (clean, no background noise/accent
variation) for English/Japanese/Chinese, each with an embedded technical term
("React", "TypeScript", "Docker") per requirement.md section 34. Full sliding-
window streaming was exercised (not a single one-shot transcribe call) —
these are real per-pass latencies from the actual streaming code path, not a
synthetic estimate. **Real end-user hardware and real speech (accents,
background noise, music) will differ — this is a data point, not a
guarantee.**

| Model | Avg latency/pass | Max latency/pass | EN accuracy | JA accuracy | ZH accuracy |
|---|---|---|---|---|---|
| tiny | ~380-420ms | ~440ms | Perfect | Good, but mangled "TypeScript" → "タイプスクリープ" | Weak — "React" became unrelated text "热业"; "TypeScript"/"Docker" garbled |
| base | ~550-650ms | ~670ms | Perfect | Good — correct "タイプスクリプト" | Still weak — "React" mistranscribed as "学系列"; terms garbled |
| small | ~1.5-2.6s | ~2.6s | Perfect | Good, cleanly split into two segments via VAD | Notably better — kept "React"/"docker" correctly, "TypeScript" still off |

Consistent across all sizes: Whisper renders "React" as the *katakana
transliteration* リアクト in Japanese speech rather than the literal Latin
"React" — worth knowing for POC4's translation/terminology-protection work,
since NLLB will receive リアクト, not "React".

**Current default is `base`**: best latency/accuracy balance for EN/JA;
Chinese technical-term accuracy is the weakest spot Whisper itself has at any
tested size, and improves with `small` at a real latency cost. This isn't a
final recommendation — only tested on synthetic clean audio on one CPU.

## POC4: NLLB translation results

Tested with the actual real-time-streamed sliding-window pipeline (not
isolated one-shot calls), using the POC3 transcripts as input — same CPU-only
sandbox, same caveats about real hardware/speech differing.

**The terminology-protection trick (section 10) works, when Whisper preserves
the literal term.** Verified round-trip: `"...for a React component."` and
`"...React。 ...docker。"` (Chinese, `small`-model output) both came back with
"React"/"Docker" intact and correctly capitalized after translation —
confirmed by inspecting the actual placeholder substitution, not just eyeballing
output. When Whisper instead transliterates a term phonetically (e.g. "React"
→ リアクト in Japanese — see POC3 notes), there's no literal term to protect,
and NLLB translated リアクト as **"phản ứng"** (Vietnamese for "reaction/response")
— an actual mistranslation, not just a missed protection. This is a real,
now-confirmed limitation of the STT→NLLB chain for Japanese specifically; fixing
it would need a phonetic glossary, out of scope here.

**Found and fixed: NLLB silently drops trailing sentences on some multi-sentence
input.** Given the two-sentence Japanese segment `"今日はリアクトについて勉強します。
タイプスクリプトとドッカーも使います。"` as one translation call, NLLB returned only
a translation of the first sentence — the second was gone, not garbled, just
absent from the output. Confirmed this is **not** a greedy-decoding artifact
(`num_beams=4` produced the identical truncation). Since one finalized STT
segment can legitimately span multiple sentences (the sliding window splits on
pauses, not sentence boundaries), this wasn't a rare edge case. Fix: split each
segment into sentences before translating, batch them through NLLB together,
and join the outputs — confirmed this resolves the truncation with a modest
(sometimes negative) latency cost.

**Measured total latency** (final STT pass → subtitle ready, `base` Whisper +
NLLB-600M, this CPU): STT final pass ~400-500ms + NLLB translation ~1.2-1.4s ≈
**~1.6-1.9s** from a speech pause to the translated subtitle being ready. This
is the honest number — noticeably higher than the informal "0.5-1.5s" figure
from an earlier draft of this spec (which the current spec correctly doesn't
promise). Translation is the larger contributor, not STT.

Sample outputs (full pipeline, not cherry-picked):
```
EN: "This is a test of the English speech recognition pipeline for a React component."
VI: "Đây là một thử nghiệm của ống dẫn nhận dạng giọng nói tiếng Anh cho một thành phần React."

ZH: "今天我们来学习React。 我们也会用type group和docker。"
VI: "Hôm nay chúng ta sẽ học React. Chúng tôi cũng sẽ sử dụng nhóm type và Docker."
```
Both read as natural, correctly-meaning Vietnamese with "React"/"Docker" preserved.
"type group" (itself a Whisper mistranscription of "TypeScript") was translated
literally as "nhóm type" — expected, term protection can't fix an STT error that
already destroyed the source word.

## NLLB int8 quantization — biggest single latency win so far

Translation was the dominant per-chunk cost (more than STT), and it was
running in full FP32 on CPU — the same precision problem Whisper already
solved by defaulting to int8 on CPU. Applied the same fix to NLLB via
PyTorch's dynamic quantization (`torch.quantization.quantize_dynamic`,
CPU-only — the CUDA path is untouched, already fp16 via `.to(device)`).

**Measured directly**, not assumed: same two-sentence benchmark, same CPU —
**1298ms → 518ms average per `translate()` call, a 2.5x speedup.** Spot-checked
output quality stayed natural and correct at every step of this work
("React"/"TypeScript"/"Docker" still preserved); only trivial synonym
differences appeared (e.g. "ống dẫn" vs "đường ống", both mean "pipeline").
Re-verified in the full live pipeline afterward (not just the isolated
benchmark) — real `translate_latency` in server logs is now consistently in
the 150-660ms range across EN/JA/ZH, down from ~1.2-1.4s before.

Toggle off with `NLLB_QUANTIZE_CPU=false` only if you notice an actual
quality regression on your own content — nothing observed in testing here,
but it's one CPU, synthetic audio, and a handful of sentences, not a
comprehensive quality suite.

Note: `torch.quantization.quantize_dynamic` is deprecated as of torch 2.8
(removal slated for 2.10) in favor of the separate `torchao` package — not
migrated yet since it's still functional and migrating would mean adding a
new dependency for no functional gain right now; worth revisiting before
upgrading past torch 2.10.

## Chunking for lower latency

Original behavior: translation only fired once a segment was *fully*
finalized — either a real pause was detected, or the (then-15s) max-buffer
timeout hit. For a long sentence spoken with no pause at all, that meant
waiting for the *entire* sentence to finish before translation even started.

**Requested change**: translate smaller pieces as they become available,
rather than waiting for one long sentence.

Two mechanisms now do this, in order of preference:

1. **Mid-utterance chunking (free, no downside)** — Whisper's own transcribe
   call already breaks audio into phrase-level segments. Once there are 2+
   segments in a pass, everything except the newest one is "settled" (Whisper
   won't revise it by seeing more audio) and gets flushed immediately. This
   only helps speech that has *some* natural micro-pause (multiple clauses,
   hesitations) — **verified directly that it does NOT fire for genuinely
   continuous speech**: fed a pause-free test sentence through Whisper at
   every intermediate buffer size (1-6s) and it reported exactly one segment
   at every size, never splitting on its own.

2. **Max-buffer force-chunking (the mechanism that handles continuous
   speech)** — `WHISPER_MAX_BUFFER_SECONDS` lowered from 15.0s to 4.0s, so
   continuous speech with no natural pause gets cut into ~4s pieces instead
   of waiting up to 15s or until it ends.

**A real bug this surfaced and the fix**: naively cutting at the 4s mark (or
even at Whisper's own segment-end estimate) is unsafe for continuous speech —
verified directly that a 4.0s cutoff landed inside the word "React"
(word-level timestamps showed the last recognized token was a bare `" re"` +
`"-"` fragment ending at 3.94s, 0.06s before the buffer edge). The first
translated chunk became "...for a" and the second became just "Component" —
**"React" was silently dropped entirely**, not just awkwardly split. Fixed
with `word_timestamps=True` and a safety margin
(`WHISPER_WORD_SAFETY_MARGIN_SECONDS`, default 0.3s): a force-finalize now
only trusts a word as complete if it ended at least that long before the
buffer edge; otherwise it holds off and lets the buffer grow one more pass
(the in-progress word finishes almost immediately). Re-verified after the fix
with the same sentence: the cut now lands cleanly at "...pipeline for" |
"React component." — no dropped or fragmented words, confirmed through full
translation with "React" correctly preserved and capitalized in the output.

**Measured effect** (same EN test sentence, `base` Whisper): first subtitle
now arrives ~4s after speech starts instead of ~8-9s (waiting for the full
~5.7s sentence plus its translation). Confirmed working the same way for the
JA and ZH test cases too.

**Trade-off, stated plainly**: a chunk cut before its sentence naturally
completes reads slightly less fluent in Vietnamese than the whole sentence
translated at once (e.g. "Đây là một thử nghiệm... cho" reads as an
incomplete clause on its own). This is the deliberate choice being made here
— speed over per-chunk translation fluency — consistent with the explicit
request that led to this change.

### Critical bug found from a user report of translation stalling

Lowering `WHISPER_MAX_BUFFER_SECONDS` interacted badly with `send_audio`'s
trigger logic. `over_max` used to double as a trigger condition on its own —
harmless under the old behavior, where force-finalizing always cleared the
whole buffer in one shot (so `over_max` could only ever be true for one
pass). Now that force-finalize can come back with `is_final=False` (holding
off because no safe word boundary was found yet — see above), the buffer can
stay over the max for multiple passes, and `over_max` alone would retrigger a
pass on almost *every* incoming audio chunk (~200ms) instead of the normal
~1s cadence — a runaway re-transcription loop on real (noisier, less
clean-cut) audio where a safe word takes more than one attempt to appear.
This is the likely explanation for a report of translation appearing to stop
entirely. Fixed: triggering is now driven only by the normal ~1s cadence;
`force_final` is still computed fresh from the current buffer size each time.
Verified with a targeted test simulating a stuck buffer (force_final always
returns "not safe yet"): before the fix this would fire on every ~200ms
chunk, after the fix it's bounded to ~1s intervals.

### Second bug from the same report: no hard ceiling

After the fix above, a second report ("still no translation overlay") led to
another real gap: the word-safety check had no upper bound. It's fine for
speech with brief natural gaps between words, but genuinely continuous fast
talking (much more realistic for actual video/lecture content than the
single clean test sentence that validated the soft 4.0s cutoff) can keep the
last recognized word suspiciously close to the buffer's edge on *every*
pass — because the edge itself keeps growing right along with the incoming
audio. Without an upper bound, this genuinely never resolves: the buffer
grows forever, STT never finalizes anything, translation never triggers —
matching the reported symptom exactly (popup stuck on "Listening", audio
clearly flowing, nothing ever shown).

Fixed with `WHISPER_HARD_MAX_BUFFER_SECONDS` (default 8.0s): past this point,
force-clear everything regardless of word safety — accepting the mid-word-cut
risk as a last resort rather than hanging indefinitely. Verified with a
targeted test using a mock model that always reports its last word right at
the buffer edge (simulating the pathological case): before this fix nothing
would ever finalize; after it, finalization is forced once the hard ceiling
is hit, confirmed via the actual "hit hard max buffer" log line firing and a
final segment being emitted.

### Hallucination on trailing silence — partially mitigated

Testing surfaced Whisper hallucinating content on near-silent trailing audio
at session end (`stop()`'s unconditional final flush). Two reproductions,
both landing on a suspiciously identical 1.10s buffer (likely an artifact
specific to the synthetic gTTS/mp3 test files used here, not necessarily
representative of real browser-captured PCM audio — worth confirming with
real testing):
- `". ."` (no actual words) → NLLB then hallucinated *its own* unrelated
  Vietnamese text translating that degenerate input ("Tôi không biết..." —
  "I don't know...").
- `"And"` → `"Và"` — a hallucinated but real, grammatically-plausible word.

**Fixed the first case**: text with no actual word characters (checked with
Unicode-aware `\w`, so it works across EN/JA/ZH/VI) is now dropped before
ever reaching translation — cheap, unambiguous, no tuning required.

**The second case (hallucinated real words) is not fixed.** Checked
`no_speech_prob` directly against this exact failure and it's a weak signal
here — a hallucinating pass can report high confidence while inventing
content, so a threshold would be tuned off one data point (guessing, not
measuring). Left as a known residual risk rather than "fixed" with an
unverified filter. If it shows up often in real testing (not just this
specific test file's tail artifact), `avg_logprob`/`compression_ratio`
filtering would be the next thing to try, with real data this time.

## Meaning vs. speed

After the latency work above, asked to find a balance rather than just chase
more speed. Tested three levers with real measurements, not assumptions:

**`num_beams` for NLLB — tested, no benefit, not changed.** Compared
`num_beams=1` vs `num_beams=4` on the quantized model: identical output text
on both test sentences, 1.65x slower. No reason to use it; stayed on
`num_beams=1`.

**`WHISPER_MAX_BUFFER_SECONDS` raised 4.0 → 5.0.** Quantization freed up
real latency budget (translation dropped ~2.5x), so this reinvests some of
it into more complete chunks — still far below the original 15.0, still the
dial to turn either direction depending on preference.

**`WHISPER_INITIAL_PROMPT` — the real win, with a real caveat.** faster-whisper's
`initial_prompt` biases recognition toward a given vocabulary list. This
attacks an actual root cause of meaning loss found earlier: Whisper
transliterating "TypeScript"/"Docker" into JA/ZH phonetic renderings that
NLLB then can't translate as the technical terms they are.

- Measured (JA): "TypeScript"/"Docker" now stay in Latin script correctly.
  "React" specifically stayed transliterated regardless of prompt wording
  tried — a strong learned loanword pattern that prompt biasing didn't move.
- Measured (ZH): meaningfully improved recognition of the same two terms.
- Checked the obvious risk directly: does biasing toward tech vocabulary
  hallucinate those words into unrelated non-technical speech? Generated
  synthetic non-technical EN/JA sentences (weather, a walk in the park) and
  compared transcription with/without the prompt — identical, no
  hallucination into unrelated content.
- Latency cost: negligible (within measurement noise).

**The real caveat, found via full live pipeline testing (not just isolated
calls)**: on the same near-silent trailing-audio hallucination already noted
above (see "One rough edge found"), the prompt made things *worse* in one
way — instead of hallucinating an unrelated word, the model echoed prompt
vocabulary back verbatim ("React, TypeScript, Docker, ..."), which is a known
characteristic of prompted generation on ambiguous/empty input. Can't safely
filter this by matching the output against the prompt text — a real video
genuinely discussing these exact technologies would look identical.

Instead calibrated against faster-whisper's own `no_speech_prob`: measured
`0.0012` for confirmed real speech vs `0.5143` for the reproduced
hallucination — a >400x difference, a real signal this time (an earlier,
single-data-point check of this same metric had looked too weak to trust).
Added `WHISPER_NO_SPEECH_PROB_THRESHOLD` (default 0.4) to drop segments above
it before they ever reach translation.

**This is a partial fix, not a complete one — say so plainly**: re-testing
after adding the filter, it correctly dropped one hallucinated segment
(`'好客'`, `no_speech_prob` well above threshold) — but a second hallucinated
segment in the *same pass* survived, because the model was confidently wrong
about it (`no_speech_prob` low, despite the text — `'React,Script, Docker,'`
— clearly still being an echo of the prompt, not real speech). `no_speech_prob`
measures "is there speech here at all," not "is this specific text accurate,"
and a strongly-primed model can hallucinate content it's genuinely confident
about. If this shows up often in real testing, `avg_logprob`/`compression_ratio`
filtering (mentioned in the rough-edge section above) would be the next
thing to try — with two real data points to calibrate against now instead
of one.

**Also noticed, not root-caused**: a few STT passes during this test session
took 2.6s-11s for tiny (~1-2s) buffers — dramatically slower than the usual
~700-1000ms. Clustered around rapid session start/stop transitions in the
test script; plausibly the shared single-worker Whisper executor queuing a
new session's first pass behind a previous session's tail-flush, or general
load on this shared dev sandbox from a long test session — not confirmed
either way. Worth watching for in real testing; flagging honestly rather
than either fixing blind or staying silent about it.

## Target: subtitle within 1s of speech ending, meaning preserved

Built a dedicated latency test (`scripts` not committed — see method below)
that measures wall-clock time from "last audio byte sent" to "first subtitle
received," instead of relying on server log timestamps alone. Changed one
thing: `WHISPER_SILENCE_FINALIZE_SECONDS` 0.7 → 0.4 (the wait to *confirm* a
pause happened before even starting the finalize pass — the cheapest, most
direct thing to cut for this target).

**Result on speech with real natural pauses (the common case)**: genuinely
excellent. A two-sentence test ("Hello, how are you today? I hope you are
doing well.") now finalizes each sentence separately at its own natural
pause — both translated completely and coherently ("Chào, hôm nay anh khỏe
không?" / "Tôi hy vọng anh đang khỏe.", not fragments) — with the second
sentence's subtitle arriving *before* all audio even finished sending. This
also improved a longer continuous-sounding sentence: it's now found a
micro-pause partway through it that 0.7s wasn't sensitive enough to catch,
splitting it into a fast, complete first chunk in under 1s of STT+translate
combined.

**Two real caveats, not glossed over:**

1. **An unexplained intermittent slow-pass issue, now confirmed across
   multiple runs.** Several times during this testing, the *first* STT pass
   of a new session took 3-8s (once even 13s) for a tiny ~1s buffer — every
   other pass in the same session was normal (~500-900ms). Not reproducible
   on demand; happened on some runs, not others, with no code difference
   between them. Best guess: contention specific to this shared dev sandbox
   (many heavy model-loading processes run throughout this session) rather
   than an architectural bug — but this is a guess, not a diagnosis. If this
   shows up in real usage on real hardware, that would be a different, more
   concerning signal worth investigating further (possibly the shared
   single-worker `ThreadPoolExecutor` queuing across sessions). Flagging
   honestly rather than either hiding it or overclaiming a root cause.
2. **The lower threshold occasionally triggers on marginal content, not just
   real pauses**, which can interact with the `no_speech_prob` hallucination
   filter to drop a few genuine trailing words on continuous speech (verified
   one case: `' in pipeline for React.'` — real content — got dropped as
   "likely hallucination" on a small trailing fragment). This is a real,
   if fairly contained, quality cost of chasing lower latency this
   aggressively.

**Bottom line**: under normal conditions, the target is genuinely met for
speech with natural pauses, with translations that still read as complete,
correct sentences — not a forced trade of meaning for speed. But "always
under 1s, no exceptions" isn't a claim this data supports, given the
unexplained slow-pass cases. If you hit either issue in real testing, that's
useful signal — tell me what you see.

## Error-handling / robustness pass

A fresh review pass after the MVP settings/popup work turned up a few real
bugs, fixed and verified here (not just in the extension):

- **Silence-handling bug (found and fixed)**: during a buffer with *no speech
  at all* (pure silence), the finalize-boundary calculation defaulted to
  clearing "up to sample 0" — i.e. nothing. Every ~1s trigger during a long
  silence would re-transcribe an ever-growing dead buffer instead of clearing
  it, until the 15s max-buffer force-clear finally kicked in. Fixed to clear
  the whole buffer when no speech is found. Verified directly: fed the
  provider 6s of pure silence and confirmed the buffer now resets to 0 bytes
  after every pass instead of growing toward 192000 bytes.
- **STT pass failures are now visible to the client** — previously only
  logged server-side; now sent as a non-fatal `{"type":"error","code":"STT_ERROR",...}`
  message (the next scheduled pass retries regardless, so this doesn't end
  the session).
- Consolidated inconsistent direct `websocket.send_json()` calls (in the
  protocol-error and outer-exception paths) to go through the same
  lock-guarded `safe_send` as everything else, avoiding a theoretical
  interleaving with an in-flight background translation's sends.
- `finally: await provider.stop()` is now individually guarded so a failure
  there can't prevent the rest of cleanup (closing the wav file, logging the
  session summary) from running.

## What to check during POC3/4 testing

With the extension's offscreen document streaming audio (see `extension/README.md`),
watch this server's terminal output and the offscreen console. You should see,
per capture session:

```
[<session>] start sourceLanguage=en
[<session>] saving debug audio to tmp_recordings/<session>.wav   (only if SAVE_DEBUG_AUDIO=true)
[<session>] stt_latency=NNNms buffer=X.XXs final=False text='...'   (repeats as speech continues)
[<session>] stt_latency=NNNms buffer=X.XXs final=True text='...'    (on a pause, or forced at stop)
[<session>] translate_latency=NNNms translated='...'                (once per finalized segment)
[<session>] stop received: session=... chunks=N bytes=N audio_duration=X.XXs wall_duration=X.XXs stalls=0
```

- `stalls` counts gaps over 500ms between audio chunks — should be 0 during
  steady playback.
- `audio_duration` vs `wall_duration` should track closely (audio arriving
  roughly in realtime, not bursty/delayed).
- Watch the offscreen console (`chrome://extensions` → Inspect views) for
  `[offscreen] server: {type: 'transcript', ...}` — text should roughly track
  what's actually being said, growing with each partial and settling on a
  correct `final: true` once there's a pause. This is real spoken audio
  through a real browser, so it's a better test than my synthetic-TTS
  benchmark above — actual accents/background noise/talk pace will show
  where `base` holds up or doesn't.
- After each `final: true` transcript, expect `{type: 'status', status:
  'translating'}` then `{type: 'subtitle', original, translated, final: true}`
  then `{type: 'status', status: 'listening'}` — read the Vietnamese against
  what was actually said (not just against the transcript, which may itself be
  wrong) to judge translation quality independently of STT quality.
- If a `final: true` message never arrives for a segment that clearly should
  have finalized (e.g. after a long pause), that's worth flagging — my fix for
  a bug where the last message could be dropped on stop was validated with
  synthetic audio, not yet with a live browser session.
- If you want to double-check transport integrity by ear (the POC2 check),
  run with `SAVE_DEBUG_AUDIO=true .venv/bin/uvicorn ...` and open the saved
  `tmp_recordings/<session>.wav` afterward, comparing it to what was actually
  playing.

`SAVE_DEBUG_AUDIO` defaults to `false` — audio is not persisted to disk in
normal operation, per the privacy requirement (section 29). `tmp_recordings/`
is gitignored regardless, in case you do turn it on for a test session.
