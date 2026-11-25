import https from 'node:https';
import http from 'node:http';
import { readFile, unlink, chmod } from 'node:fs/promises';
import { randomBytes, randomInt, timingSafeEqual } from 'node:crypto';
import { WebSocketServer, WebSocket } from 'ws';
import { SessionCommands, SessionQueries, type CapturePort } from './session.js';

export interface Config {
  hosts: string[]; names: string[]; port: number; cert: string; key: string;
  ipc: string; serial: string; serverFile: string; adb: string; sdk: string;
}
export async function serve(config: Config, port: CapturePort) {
  const commands = new SessionCommands(port), queries = new SessionQueries(commands);
  const code = String(randomInt(10_000_000, 100_000_000));
  const sessions = new Set<string>(), attempts = new Map<string, { count: number; until: number }>();
  const origins = new Set(config.names.map(h => 'https://' + h + ':' + config.port));
  const cookies = (req: http.IncomingMessage) => /(?:^|; )exvius=([a-f0-9]{64})(?:;|$)/.exec(req.headers.cookie ?? '')?.[1];
  const authenticated = (req: http.IncomingMessage) => sessions.has(cookies(req) ?? '');
  const validHost = (req: http.IncomingMessage) => config.names.some(h => req.headers.host === h + ':' + config.port);
  let chain: Promise<unknown> = Promise.resolve();
  const enqueue = <T>(job: () => Promise<T>): Promise<T> => {
    const result = chain.then(job); chain = result.catch(() => {}); return result;
  };
  const wss = new WebSocketServer({ noServer: true, maxPayload: 2048, perMessageDeflate: false });
  const clients = new Set<WebSocket>();
  let shuttingDown = false;
  let ipcListening = false;
  let markClosed!: () => void;
  const closed = new Promise<void>(resolve => { markClosed = resolve; });
  function reply(res: http.ServerResponse, status: number, value: unknown) {
    res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify(value));
  }
  const assets = new Map<string, { data: Buffer; type: string }>();
  for (const [url, file, type] of [
    ['/', 'index.html', 'text/html'], ['/app.js', 'app.js', 'text/javascript'],
    ['/style.css', 'style.css', 'text/css'], ['/audio-worklet.js', 'audio-worklet.js', 'text/javascript'],
  ]) assets.set(url, { data: await readFile(new URL('./web/' + file, import.meta.url)), type });
  const handler: http.RequestListener = (req, res) => {
    res.setHeader('Content-Security-Policy', "default-src 'self'; connect-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; object-src 'none'; frame-ancestors 'none'");
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    if (!validHost(req)) { reply(res, 403, { error: 'Unknown host' }); return; }
    if (req.method === 'POST' && req.url === '/api/commands/login') {
      if (!origins.has(req.headers.origin ?? '')) { reply(res, 403, { error: 'Invalid origin' }); return; }
      const address = req.socket.remoteAddress ?? '';
      const now = Date.now();
      // Bound memory even when clients continually acquire new addresses.
      for (const [ip, v] of attempts) if (v.until <= now) attempts.delete(ip);
      const attempt = attempts.get(address) ?? { count: 0, until: now + 60_000 };
      if (attempt.count >= 5 || attempts.size >= 1024) { reply(res, 429, { error: 'Wait a minute before trying again' }); return; }
      attempt.count++; attempts.set(address, attempt);
      let body = ''; let oversized = false;
      req.on('data', chunk => { body += chunk; if (body.length > 256) { oversized = true; req.destroy(); } });
      req.on('end', () => {
        if (oversized) return;
        let supplied: string;
        try { supplied = JSON.parse(body).code; } catch { reply(res, 400, { error: 'Invalid code' }); return; }
        if (typeof supplied !== 'string' || !/^[0-9]{8}$/.test(supplied) || !timingSafeEqual(Buffer.from(supplied), Buffer.from(code))) {
          reply(res, 401, { error: 'Incorrect access code' }); return;
        }
        if (sessions.size >= 32) { reply(res, 429, { error: 'Restart browser mode to pair more devices' }); return; }
        const token = randomBytes(32).toString('hex'); sessions.add(token);
        res.setHeader('Set-Cookie', 'exvius=' + token + '; Secure; HttpOnly; SameSite=Strict; Path=/');
        reply(res, 200, { ok: true });
      }); return;
    }
    if (req.url === '/api/queries/status' && req.method === 'GET') {
      reply(res, authenticated(req) ? 200 : 401, authenticated(req) ? queries.status() : { error: 'Enter the access code shown on the Mac' }); return;
    }
    const asset = assets.get(req.url ?? '');
    if (req.method === 'GET' && asset) { res.writeHead(200, { 'Content-Type': asset.type, 'Cache-Control': 'no-store' }); res.end(asset.data); }
    else reply(res, 404, { error: 'Not found' });
  };
  const tls = { cert: await readFile(config.cert), key: await readFile(config.key), minVersion: 'TLSv1.2' as const };
  const servers = config.hosts.map(() => https.createServer(tls, handler));
  for (const server of servers) {
    server.requestTimeout = 10_000; server.headersTimeout = 10_000;
    server.on('upgrade', (req, socket, head) => {
      if (req.url !== '/api/session' || !validHost(req) || !origins.has(req.headers.origin ?? '') || !authenticated(req) || clients.size >= 8) { socket.destroy(); return; }
      wss.handleUpgrade(req, socket, head, ws => wss.emit('connection', ws));
    });
  }
  wss.on('connection', ws => {
    clients.add(ws); let id = ''; let pending = 0; let alive = true; let count = 0;
    const tell = (value: object) => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(value)); };
    const sink = {
      metadata: (value: object) => tell({ type: 'metadata', ...value }),
      packet: (channel: number, flags: number, pts: bigint, data: Uint8Array) => {
        if (ws.readyState !== WebSocket.OPEN) return;
        if (ws.bufferedAmount > 1_048_576) { ws.close(1013, 'Connection too slow; reconnect'); return; }
        const header = Buffer.alloc(10); header[0] = channel; header[1] = flags; header.writeBigUint64BE(pts, 2);
        ws.send(Buffer.concat([header, data]));
      },
      failed: (error: Error) => {
        tell({ type: 'error', error: error.message });
        ws.close(1011, 'Capture ended');
        void enqueue(() => commands.stop(ws));
      },
    };
    const heartbeat = setInterval(() => {
      count = 0;
      if (!alive) { ws.terminate(); return; }
      alive = false; ws.ping();
    }, 10_000);
    ws.on('pong', () => { alive = true; });
    ws.on('message', (data, binary) => {
      if (binary || ++pending > 64 || ++count > 5000) { ws.close(1008, 'Too many commands'); return; }
      void enqueue(async () => {
        if (ws.readyState !== WebSocket.OPEN) return;
        try {
          const c = JSON.parse(data.toString());
          if (c.type === 'start') { id = await commands.start(ws, sink); tell({ type: 'started', sessionId: id }); }
          else if (c.type === 'stop') { await commands.stop(ws); id = ''; tell({ type: 'stopped' }); }
          else await commands.input(ws, c.sessionId, c);
        } catch (error) { tell({ type: 'error', error: (error as Error).message }); }
      }).finally(() => { pending--; });
    });
    ws.on('error', () => {});
    ws.on('close', () => { clearInterval(heartbeat); clients.delete(ws); void enqueue(() => commands.stop(ws)); });
  });
  const ipc = http.createServer((req, res) => {
    if (req.method === 'GET' && req.url === '/status') reply(res, 200, { ...queries.status(), code, urls: [...origins], serial: config.serial, sdk: config.sdk });
    else if (req.method === 'POST' && req.url === '/stop') { reply(res, 200, { ok: true }); void shutdown(); }
    else reply(res, 404, {});
  });
  async function shutdown() {
    if (shuttingDown) return;
    shuttingDown = true;
    for (const ws of clients) ws.terminate();
    await enqueue(() => commands.stop()).catch(() => {});
    await Promise.all(servers.map(s => new Promise<void>(resolve => { s.close(() => resolve()); s.closeAllConnections(); })));
    await new Promise<void>(resolve => ipc.close(() => resolve()));
    if (ipcListening) await unlink(config.ipc).catch(() => {});
    markClosed();
  }
  try {
    for (let i = 0; i < servers.length; i++) {
      await new Promise<void>((resolve, reject) => { servers[i].once('error', reject); servers[i].listen(config.port, config.hosts[i], () => resolve()); });
    }
    await new Promise<void>((resolve, reject) => { ipc.once('error', reject); ipc.listen(config.ipc, () => resolve()); });
    ipcListening = true;
    await chmod(config.ipc, 0o600);
  } catch (e) { await shutdown(); throw e; }
  return { shutdown, closed, status: queries.status.bind(queries) };
}
