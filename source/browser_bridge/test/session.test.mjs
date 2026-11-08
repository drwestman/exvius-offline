import test from 'node:test';
import assert from 'node:assert/strict';
import { SessionCommands, SessionQueries } from '../dist/session.js';
const sink = { metadata() {}, packet() {}, failed() {} };
function setup() {
  const input = []; let starts = 0, closes = 0;
  const commands = new SessionCommands({ async start() { starts++; return { async input(c) { input.push(c); }, async close() { closes++; } }; } });
  return { commands, queries: new SessionQueries(commands), input, counts: () => ({ starts, closes }) };
}
test('given idle capture when status is queried then no command or mutation occurs', () => {
  const s = setup(); const before = s.queries.status();
  assert.equal(Object.isFrozen(before), true); assert.deepEqual(s.queries.status(), before);
  assert.deepEqual(s.counts(), { starts: 0, closes: 0 });
});
test('given an active player when another joins then only the original controls the game', async () => {
  const s = setup(), owner = {}, second = {};
  const id = await s.commands.start(owner, sink);
  await assert.rejects(s.commands.start(second, sink), /Game in use/);
  await assert.rejects(s.commands.input(second, id, { type: 'key', code: 4, action: 'down' }), /Stale/);
  await s.commands.stop(second); assert.equal(s.queries.status().phase, 'streaming');
  await s.commands.stop(owner); assert.deepEqual(s.counts(), { starts: 1, closes: 1 });
});
test('given held touch and keys when disconnected then releases precede capture shutdown and old commands cannot replay', async () => {
  const s = setup(), owner = {}; const id = await s.commands.start(owner, sink);
  await s.commands.input(owner, id, { type: 'pointer', action: 'down', id: 3, x: .2, y: .8 });
  await s.commands.input(owner, id, { type: 'key', action: 'down', code: 4 });
  await s.commands.stop(owner); await s.commands.stop(owner);
  assert.equal(s.input[2].action, 'up'); assert.equal(s.input[2].x, .2); assert.equal(s.input[3].action, 'up');
  const next = await s.commands.start(owner, sink); assert.notEqual(id, next);
  await assert.rejects(s.commands.input(owner, id, { type: 'key', action: 'down', code: 4 }), /Stale/);
});
test('given malformed or privileged input then the adapter never receives it', async () => {
  const s = setup(), owner = {}; const id = await s.commands.start(owner, sink);
  for (const input of [{ type: 'shell', command: 'rm' }, { type: 'key', code: 26, action: 'down' },
    { type: 'pointer', action: 'down', id: 1, x: NaN, y: 0 }, { type: 'text', text: '\n' }]) {
    await assert.rejects(s.commands.input(owner, id, input), /Invalid/);
  }
  assert.equal(s.input.length, 0); await s.commands.stop();
});
test('given a capture failure when starting then the lease is available for recovery', async () => {
  const c = new SessionCommands({ async start() { throw new Error('Device lost'); } });
  await assert.rejects(c.start({}, sink), /Device lost/); assert.equal(c.snapshot.phase, 'error');
  await assert.rejects(c.start({}, sink), /Device lost/);
});
