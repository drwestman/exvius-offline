import readline from 'node:readline';
import { serve, type Config } from './server.js';
import { ScrcpyAdapter } from './scrcpy.js';
const lines = readline.createInterface({ input: process.stdin });
let running: Awaited<ReturnType<typeof serve>> | undefined;
let starting = false;
lines.on('line', line => {
  if (starting) return;
  starting = true;
  void (async () => {
    const config = JSON.parse(line) as Config;
    running = await serve(config, new ScrcpyAdapter(config.serial, config.serverFile, config.adb));
    console.log('Browser bridge ready');
    void running.closed.then(() => lines.close());
  })().catch(error => { console.error('Browser bridge: ' + error.message); process.exitCode = 1; lines.close(); });
});
const stop = async () => { await running?.shutdown(); process.exit(); };
lines.on('close', () => { void stop(); });
process.on('SIGTERM', () => { void stop(); });
process.on('SIGINT', () => { void stop(); });
