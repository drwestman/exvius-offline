class PcmSink extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = []; this.offset = 0; this.samples = 0; this.primed = false;
    this.port.onmessage = ({ data }) => {
      const pcm = new Int16Array(data);
      this.queue.push(pcm); this.samples += pcm.length;
      // At most 200 ms; discard old whole packets before latency can accumulate.
      while (this.samples > 19200 && this.queue.length > 1) {
        this.samples -= this.queue[0].length - this.offset; this.queue.shift(); this.offset = 0;
      }
    };
  }
  process(_inputs, outputs) {
    const output = outputs[0];
    if (!this.primed) { if (this.samples < 3840) return true; this.primed = true; }
    for (let i = 0; i < output[0].length; i++) {
      if (!this.queue.length) { this.primed = false; break; }
      const packet = this.queue[0];
      output[0][i] = packet[this.offset++] / 32768;
      output[1][i] = packet[this.offset++] / 32768;
      this.samples -= 2;
      if (this.offset >= packet.length) { this.queue.shift(); this.offset = 0; }
    }
    return true;
  }
}
registerProcessor('exvius-pcm', PcmSink);
