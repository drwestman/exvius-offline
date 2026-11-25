// Explicit integration probe against the existing named AVD; never launches an activity.
import { ScrcpyAdapter } from '../dist/scrcpy.js';
const stats = { video: 0, audio: 0, audioBytes: 0 };
let failure;
const capture = await new ScrcpyAdapter(process.argv[2], process.argv[3], process.argv[4]).start({
  metadata(value) { console.log(JSON.stringify(value)); },
  packet(channel, flags, pts, data) { if(channel === 1) stats.video++; else { stats.audio++; stats.audioBytes += data.length; } },
  failed(error) { failure = error; },
});
await new Promise(resolve => setTimeout(resolve, 4000));
await capture.close();
console.log(JSON.stringify(stats));
if (failure || !stats.video || !stats.audio) throw failure ?? new Error('Missing media packets');
