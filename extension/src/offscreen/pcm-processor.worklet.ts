// Runs on the audio rendering thread. Downsamples the tab's native-rate audio
// (mono-summed) to 16kHz PCM16 and posts ~200ms batches back to the main thread.
//
// NOTE (POC2): resampling is plain linear interpolation, not a proper
// anti-aliased resample. Good enough to validate the transport; STT accuracy
// impact needs checking in POC3 per requirement.md section 5.

const TARGET_SAMPLE_RATE = 16000;
const CHUNK_DURATION_MS = 200;

class PCMProcessor extends AudioWorkletProcessor {
  private readonly resampleRatio: number;
  private readonly chunkSizeSamples: number;
  private fractionalIndex = 0;
  private pending: number[] = [];

  constructor() {
    super();
    this.resampleRatio = sampleRate / TARGET_SAMPLE_RATE;
    this.chunkSizeSamples = Math.round((TARGET_SAMPLE_RATE * CHUNK_DURATION_MS) / 1000);
  }

  process(inputs: Float32Array[][]): boolean {
    const input = inputs[0];
    const frameLength = input?.[0]?.length ?? 0;
    if (frameLength === 0) return true;

    const numChannels = input.length;
    let i = this.fractionalIndex;
    while (i < frameLength) {
      const idx = Math.floor(i);
      const frac = i - idx;

      const sampleAt = (n: number): number => {
        if (n >= frameLength) n = frameLength - 1;
        let sum = 0;
        for (let c = 0; c < numChannels; c++) sum += input[c][n];
        return sum / numChannels;
      };

      const s0 = sampleAt(idx);
      const s1 = sampleAt(idx + 1);
      const sample = s0 + (s1 - s0) * frac;
      const clamped = Math.max(-1, Math.min(1, sample));
      this.pending.push(Math.round(clamped * 32767));

      i += this.resampleRatio;
    }
    this.fractionalIndex = i - frameLength;

    if (this.pending.length >= this.chunkSizeSamples) {
      this.flush();
    }

    return true;
  }

  private flush(): void {
    const samples = this.pending;
    this.pending = [];

    const buffer = new ArrayBuffer(samples.length * 2);
    const view = new DataView(buffer);
    for (let n = 0; n < samples.length; n++) {
      view.setInt16(n * 2, samples[n], true); // little-endian
    }
    this.port.postMessage(buffer, [buffer]);
  }
}

registerProcessor("pcm-processor", PCMProcessor);
