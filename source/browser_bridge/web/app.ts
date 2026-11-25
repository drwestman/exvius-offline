import { WebCodecsVideoDecoder, CanvasVideoFrameRenderer } from '@yume-chan/scrcpy-decoder-webcodecs';
import { ScrcpyVideoCodecId } from '@yume-chan/scrcpy';
import { mapPoint } from './input';

class GameRenderer extends CanvasVideoFrameRenderer {
  private context = this.canvas.getContext('2d')!;
  async draw(frame: VideoFrame) { this.context.drawImage(frame, 0, 0); }
}
const get = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const canvas = get<HTMLCanvasElement>('screen'), play = get<HTMLButtonElement>('play');
const message = (text: string) => { get('message').textContent = text; };
let ws: WebSocket | undefined, sessionId = '', decoder: WebCodecsVideoDecoder | undefined;
let writer: WritableStreamDefaultWriter<any> | undefined, audio: AudioContext | undefined;
let sink: AudioWorkletNode | undefined, gain: GainNode | undefined, queuedFrames = 0, submittedFrames = 0;
const pointers = new Map<number, { x: number; y: number }>(), keys = new Set<number>();
function send(c: object) { if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ ...c, sessionId })); }
function release() {
  for (const [id, point] of pointers) send({ type: 'pointer', action: 'up', id, ...point });
  for (const code of keys) send({ type: 'key', action: 'up', code });
  pointers.clear(); keys.clear();
}
function clean() {
  release(); sessionId = ''; ws?.close(); ws = undefined;
  writer?.releaseLock(); writer = undefined; decoder?.dispose(); decoder = undefined;
  void audio?.close().catch(() => {}); audio = undefined; sink = undefined; gain = undefined; queuedFrames = 0; submittedFrames = 0;
  for (const id of ['disconnect', 'back', 'send-text']) get<HTMLButtonElement>(id).disabled = true;
  play.disabled = false; get('connection').textContent = 'Disconnected';
}
async function status() {
  const response = await fetch('/api/queries/status');
  if (response.ok) { get('login-panel').hidden = true; play.disabled = false; }
}
get<HTMLFormElement>('login').onsubmit = async e => {
  e.preventDefault();
  try {
    const response = await fetch('/api/commands/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: get<HTMLInputElement>('code').value }) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    get<HTMLInputElement>('code').value = ''; await status(); message('Connected. Press Play to start video and sound.');
  } catch (e) { message((e as Error).message); }
};
play.onclick = async () => {
  play.disabled = true;
  try {
    if (!isSecureContext || !WebCodecsVideoDecoder.isSupported) throw new Error('This browser needs HTTPS and WebCodecs video support. Trust the local certificate, then use current Chrome or Safari.');
    audio = new AudioContext({ sampleRate: 48000, latencyHint: 'interactive' });
    await audio.resume();
    await audio.audioWorklet.addModule('/audio-worklet.js');
    sink = new AudioWorkletNode(audio, 'exvius-pcm', { numberOfInputs: 0, numberOfOutputs: 1, outputChannelCount: [2] });
    gain = audio.createGain(); gain.gain.value = Number(get<HTMLInputElement>('volume').value);
    sink.connect(gain).connect(audio.destination);
    decoder = new WebCodecsVideoDecoder({ codec: ScrcpyVideoCodecId.H264, renderer: new GameRenderer(canvas) });
    writer = decoder.writable.getWriter();
    const socket = new WebSocket(location.origin.replace('https:', 'wss:') + '/api/session');
    ws = socket;
    ws.binaryType = 'arraybuffer';
    ws.onopen = () => send({ type: 'start' });
    ws.onerror = () => { message('Connection failed. Check the Mac launcher, Wi-Fi, and certificate trust.'); };
    ws.onclose = () => { if (ws !== socket) return; clean(); message('Disconnected. Press Play to reconnect to your game.'); };
    ws.onmessage = e => {
      if (ws !== socket) return;
      if (typeof e.data === 'string') {
        const c = JSON.parse(e.data);
        if (c.type === 'metadata') {
          sessionId = c.sessionId;
          if (c.width && c.height) { canvas.width = c.width; canvas.height = c.height; canvas.style.aspectRatio = c.width + '/' + c.height; }
        } else if (c.type === 'started') {
          sessionId = c.sessionId; message('Playing. Tap or drag the game screen.'); get('connection').textContent = 'Playing';
          for (const id of ['disconnect', 'back', 'send-text']) get<HTMLButtonElement>(id).disabled = false;
          canvas.focus();
        } else if (c.type === 'error') { message(c.error); clean(); message(c.error); }
        return;
      }
      const buffer = e.data as ArrayBuffer, data = new Uint8Array(buffer, 10), header = new DataView(buffer);
      if (header.getUint8(0) === 2) {
        if (data.byteLength % 4 === 0) { const pcm = buffer.slice(10); sink?.port.postMessage(pcm, [pcm]); }
        return;
      }
      const backlog = header.getUint8(1) !== 1 && ++submittedFrames - (decoder?.framesRendered ?? 0) - (decoder?.framesSkipped ?? 0) > 60;
      if (++queuedFrames > 60 || backlog) { message('Connection fell behind. Press Play to reconnect.'); clean(); return; }
      const packet = header.getUint8(1) === 1 ? { type: 'configuration', data } : { type: 'data', pts: header.getBigUint64(2), keyframe: header.getUint8(1) === 2, data };
      const current = writer;
      void current?.write(packet).catch(e => { if (writer === current) { clean(); message('Video: ' + e.message); } }).finally(() => { if (writer === current) queuedFrames--; });
    };
  } catch (e) { clean(); message((e as Error).message); }
};
get('disconnect').onclick = () => { release(); clean(); };
get('back').onclick = () => { send({ type: 'key', code: 4, action: 'down' }); send({ type: 'key', code: 4, action: 'up' }); };
get<HTMLInputElement>('volume').oninput = e => { if (gain) gain.gain.value = Number((e.target as HTMLInputElement).value); };
get('fullscreen').onclick = () => { void get('stage').requestFullscreen?.().catch(() => message('Full screen is unavailable on this browser.')); };
canvas.onpointerdown = e => {
  if (!sessionId || e.button !== 0) return;
  e.preventDefault(); canvas.focus(); canvas.setPointerCapture(e.pointerId); pointers.set(e.pointerId, mapPoint(canvas.getBoundingClientRect(), e.clientX, e.clientY));
  send({ type: 'pointer', action: 'down', id: e.pointerId, ...mapPoint(canvas.getBoundingClientRect(), e.clientX, e.clientY) });
};
for (const event of ['pointermove', 'pointerup', 'pointercancel', 'lostpointercapture']) canvas.addEventListener(event, (e: Event) => {
  const p = e as PointerEvent;
  if (!pointers.has(p.pointerId)) return;
  const action = event === 'pointermove' ? 'move' : 'up';
  send({ type: 'pointer', action, id: p.pointerId, ...mapPoint(canvas.getBoundingClientRect(), p.clientX, p.clientY) });
  if (action === 'up') pointers.delete(p.pointerId);
  else pointers.set(p.pointerId, mapPoint(canvas.getBoundingClientRect(), p.clientX, p.clientY));
});
const keyCodes: Record<string, number> = { Escape: 4, ArrowUp: 19, ArrowDown: 20, ArrowLeft: 21, ArrowRight: 22, Tab: 61, Enter: 66, Backspace: 67 };
canvas.onkeydown = e => {
  if (!sessionId || e.repeat) return;
  if (keyCodes[e.key]) { e.preventDefault(); keys.add(keyCodes[e.key]); send({ type: 'key', code: keyCodes[e.key], action: 'down' }); }
  else if (e.key.length === 1 && !e.metaKey && !e.ctrlKey) { e.preventDefault(); send({ type: 'text', text: e.key }); }
};
canvas.onkeyup = e => { const code = keyCodes[e.key]; if (keys.delete(code)) { e.preventDefault(); send({ type: 'key', code, action: 'up' }); } };
canvas.onblur = release;
get<HTMLFormElement>('text-entry').onsubmit = e => { e.preventDefault(); send({ type: 'text', text: get<HTMLInputElement>('text').value }); get<HTMLInputElement>('text').value = ''; canvas.focus(); };
addEventListener('pagehide', () => { release(); clean(); });
document.addEventListener('visibilitychange', () => { if (document.hidden && ws) { release(); clean(); message('Paused connection. Press Play when you return.'); } });
void status().catch(() => message('Could not reach the Mac. Check the browser launcher.'));
