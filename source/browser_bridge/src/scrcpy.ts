import { AdbServerClient } from '@yume-chan/adb';
import { AdbServerNodeTcpConnector } from '@yume-chan/adb-server-node-tcp';
import { AdbScrcpyClient, AdbScrcpyOptions3_3_3 } from '@yume-chan/adb-scrcpy';
import { ReadableStream, WritableStream } from '@yume-chan/stream-extra';
import { readFileSync } from 'node:fs';
import type { AndroidKeyCode } from '@yume-chan/scrcpy';
import { readFile } from 'node:fs/promises';
import type { CapturePort, Capture, MediaSink, Input } from './session.js';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createHash } from 'node:crypto';

export const SERVER = JSON.parse(readFileSync(new URL('../server-manifest.json', import.meta.url), 'utf8'));
export class ScrcpyAdapter implements CapturePort {
  constructor(private readonly serial: string, private readonly serverFile: string, private readonly adbPath: string) {
    if (!/^emulator-\d+$/.test(serial)) throw new Error('Only an emulator can be streamed');
  }
  async start(sink: MediaSink): Promise<Capture> {
    const server = await readFile(this.serverFile);
    if (createHash('sha256').update(server).digest('hex') !== SERVER.sha256) throw new Error('Scrcpy checksum mismatch; run setup-browser');
    const adb = await new AdbServerClient(new AdbServerNodeTcpConnector({ host: '127.0.0.1', port: 5037 })).createAdb({ serial: this.serial });
    let client: Awaited<ReturnType<typeof AdbScrcpyClient.start>> | undefined;
    let closed = false;
    const timeout = setTimeout(() => { void adb.close(); }, 20000);
    try {
      // Verify identity again at the adapter boundary; never trust a browser-selected serial.
      const identity = await promisify(execFile)(this.adbPath, ['-s', this.serial, 'emu', 'avd', 'name'], { timeout: 10000 });
      if (identity.stdout.split('\n')[0].trim() !== 'Exvius_Offline_API_33') throw new Error('Emulator identity changed');
      await AdbScrcpyClient.pushServer(adb, new ReadableStream({ start(c) { c.enqueue(server); c.close(); } }));
      const options = new AdbScrcpyOptions3_3_3({
        video: true, audio: true, control: true, audioCodec: 'raw', audioSource: 'output',
        maxSize: 1280, maxFps: 30, videoBitRate: 4_000_000, stayAwake: true,
        clipboardAutosync: false, tunnelForward: true,
      });
      client = await AdbScrcpyClient.start(adb, '/data/local/tmp/scrcpy-server.jar', options);
      const active = client;
      // Drain server output so its subprocess cannot deadlock on a full pipe.
      void active.output.pipeTo(new WritableStream({ write() {} })).catch(() => {});
      const [video, audio] = await Promise.all([active.videoStream, active.audioStream]);
      if (!video || audio?.type !== 'success') throw new Error('Android video/audio capture unavailable');
      let width = video.metadata.width!, height = video.metadata.height!;
      video.sizeChanged(({ width: w, height: h }) => { width = w; height = h; sink.metadata({ width, height }); });
      sink.metadata({ width, height, codec: video.metadata.codec, audio: 'pcm-s16le', sampleRate: 48000, channels: 2 });
      const pump = async (stream: typeof video.stream, channel: number) => {
        const reader = stream.getReader();
        try {
          while (!closed) {
            const { done, value } = await reader.read();
            if (done) break;
            sink.packet(channel, value.type === 'configuration' ? 1 : value.keyframe ? 2 : 0,
              value.type === 'data' ? value.pts ?? 0n : 0n, value.data);
          }
          if (!closed) sink.failed(new Error('Android stream ended'));
        } catch (e) { if (!closed) sink.failed(e as Error); }
        finally { reader.releaseLock(); }
      };
      void pump(video.stream, 1); void pump(audio.stream, 2);
      void active.exited.then(() => { if (!closed) sink.failed(new Error('Android capture exited')); });
      clearTimeout(timeout);
      return {
        async input(c: Input) {
          if (closed || !active.controller) throw new Error('Capture closed');
          if (c.type === 'pointer') await active.controller.injectTouch({
            action: c.action === 'down' ? 0 : c.action === 'up' ? 1 : 2,
            pointerId: BigInt(c.id), pointerX: Math.min(width - 1, Math.round(c.x * width)),
            pointerY: Math.min(height - 1, Math.round(c.y * height)), videoWidth: width, videoHeight: height,
            pressure: c.action === 'up' ? 0 : 1, actionButton: 0, buttons: 0,
          });
          else if (c.type === 'key') await active.controller.injectKeyCode({ action: c.action === 'down' ? 0 : 1, keyCode: c.code as AndroidKeyCode, repeat: 0, metaState: 0 });
          else await active.controller.injectText(c.text);
        },
        async close() { closed = true; try { await active.close(); } finally { await adb.close(); } },
      };
    } catch (e) { clearTimeout(timeout); closed = true; try { await client?.close(); } finally { await adb.close(); } throw e; }
  }
}
