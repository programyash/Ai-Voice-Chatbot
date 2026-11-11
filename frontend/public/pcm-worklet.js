class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super(); this.acc = 0; this.samples = []; this.levelCount = 0;
  }
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    let energy = 0;
    for (let i = 0; i < channel.length; i++) {
      const sample = Math.max(-1, Math.min(1, channel[i]));
      energy += sample * sample;
      this.acc += 16000;
      if (this.acc >= sampleRate) {
        this.acc -= sampleRate;
        this.samples.push(sample < 0 ? Math.round(sample * 32768) : Math.round(sample * 32767));
        if (this.samples.length >= 320) {
          const pcm = new Int16Array(this.samples.splice(0, 320));
          this.port.postMessage({ type: 'pcm', buffer: pcm.buffer }, [pcm.buffer]);
        }
      }
    }
    if (++this.levelCount % 6 === 0) this.port.postMessage({ type: 'level', value: Math.min(1, Math.sqrt(energy / channel.length) * 5) });
    return true;
  }
}
registerProcessor('pcm-capture', PcmCapture);
