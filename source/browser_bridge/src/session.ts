import { randomUUID } from 'node:crypto';

export type Input = { type: 'pointer'; action: 'down' | 'move' | 'up'; id: number; x: number; y: number }
  | { type: 'key'; action: 'down' | 'up'; code: number } | { type: 'text'; text: string };
export interface Capture {
  input(command: Input): Promise<void>;
  close(): Promise<void>;
}
export interface MediaSink {
  metadata(value: object): void;
  packet(channel: number, flags: number, pts: bigint, data: Uint8Array): void;
  failed(error: Error): void;
}
export interface CapturePort { start(sink: MediaSink): Promise<Capture> }
export class SessionQueries {
  constructor(private readonly commands: SessionCommands) {}
  status() { return Object.freeze({ ...this.commands.snapshot }); }
}
// The only writer of session state. The transport serializes commands.
export class SessionCommands {
  snapshot = { phase: 'idle', sessionId: '', width: 0, height: 0, error: '' };
  private owner?: object;
  private capture?: Capture;
  private pointers = new Map<number, Input & { type: 'pointer' }>();
  private keys = new Set<number>();
  constructor(private readonly port: CapturePort) {}
  async start(owner: object, sink: MediaSink) {
    if (this.owner) throw new Error('Game in use');
    this.owner = owner;
    this.snapshot = { phase: 'connecting', sessionId: randomUUID(), width: 0, height: 0, error: '' };
    try {
      this.capture = await this.port.start({
        ...sink,
        metadata: value => {
          Object.assign(this.snapshot, value);
          sink.metadata({ ...value, sessionId: this.snapshot.sessionId });
        },
      });
      this.snapshot.phase = 'streaming';
      return this.snapshot.sessionId;
    } catch (error) {
      this.owner = undefined;
      this.snapshot = { phase: 'error', sessionId: '', width: 0, height: 0, error: String(error) };
      throw error;
    }
  }
  async input(owner: object, sessionId: string, value: unknown) {
    if (owner !== this.owner || sessionId !== this.snapshot.sessionId || !this.capture) throw new Error('Stale session');
    const c = validateInput(value);
    if (c.type === 'pointer') {
      if (c.action !== 'down' && !this.pointers.has(c.id)) return;
      if (c.action === 'down' && this.pointers.size >= 10) throw new Error('Too many pointers');
      if (c.action === 'up') this.pointers.delete(c.id); else this.pointers.set(c.id, c);
    } else if (c.type === 'key') {
      if (c.action === 'down') this.keys.add(c.code); else this.keys.delete(c.code);
    }
    await this.capture.input(c);
  }
  async stop(owner?: object) {
    if (owner && owner !== this.owner) return;
    const capture = this.capture;
    this.capture = undefined;
    try {
      if (capture) {
        for (const c of this.pointers.values()) await capture.input({ ...c, action: 'up' });
        for (const code of this.keys) await capture.input({ type: 'key', code, action: 'up' });
      }
    } finally {
      try { await capture?.close(); }
      finally {
        this.pointers.clear(); this.keys.clear(); this.owner = undefined;
        this.snapshot = { phase: 'idle', sessionId: '', width: 0, height: 0, error: '' };
      }
    }
  }
}
export function validateInput(value: unknown): Input {
  const c = value as Input;
  if (!c || typeof c !== 'object') throw new Error('Invalid input');
  if (c.type === 'pointer' && ['down', 'move', 'up'].includes(c.action)
      && Number.isSafeInteger(c.id) && c.id >= 0 && c.id <= 2147483647
      && Number.isFinite(c.x) && c.x >= 0 && c.x <= 1 && Number.isFinite(c.y) && c.y >= 0 && c.y <= 1) return c;
  if (c.type === 'key' && ['down', 'up'].includes(c.action) && [4, 19, 20, 21, 22, 61, 66, 67].includes(c.code)) return c;
  if (c.type === 'text' && typeof c.text === 'string' && c.text.length <= 256 && !/[\x00-\x1f]/.test(c.text)) return c;
  throw new Error('Invalid input');
}
