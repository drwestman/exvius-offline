import { build } from 'esbuild';
import { mkdir, copyFile } from 'node:fs/promises';
await mkdir('dist/web', { recursive: true });
await build({ entryPoints: ['web/app.ts'], bundle: true, format: 'esm', target: 'es2022', outfile: 'dist/web/app.js' });
await copyFile('web/index.html', 'dist/web/index.html');
await copyFile('web/style.css', 'dist/web/style.css');

await copyFile('web/audio-worklet.js', 'dist/web/audio-worklet.js');
