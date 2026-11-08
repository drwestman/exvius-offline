import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import https from 'node:https';
import { once } from 'node:events';
import { WebSocket } from 'ws';
import { serve } from '../dist/server.js';

test('given LAN HTTPS when pairing and connecting then auth, origins, status and exclusive control are enforced', async t => {
  const dir = await mkdtemp(join(tmpdir(), 'exvius-https-'));
  execFileSync('openssl', ['req','-x509','-newkey','rsa:2048','-nodes','-keyout',join(dir,'key.pem'),'-out',join(dir,'cert.pem'),'-subj','/CN=localhost','-days','1'], { stdio: 'ignore' });
  let starts = 0, closes = 0;
  const port = 18443;
  const app = await serve({ hosts:['127.0.0.1'],names:['127.0.0.1'],port, cert:join(dir,'cert.pem'),key:join(dir,'key.pem'),ipc:join(dir,'bridge.sock'),serial:'emulator-5554',sdk:'/sdk' }, {
    async start(sink) { starts++; sink.metadata({ width: 360, height: 640, codec: 0x68323634 }); return { async input() {}, async close() { closes++; } }; },
  });
  t.after(async () => { await app.shutdown(); await rm(dir,{recursive:true,force:true}); });
  const origin = 'https://127.0.0.1:' + port;
  const request = (path, method='GET', body, headers={}) => new Promise((resolve,reject) => {
    const req = https.request(origin+path,{method,rejectUnauthorized:false,headers}, res => {
      let data=''; res.on('data',c => data+=c); res.on('end',() => resolve({status:res.statusCode,body:JSON.parse(data),cookie:res.headers['set-cookie']?.[0].split(';')[0]}));
    });
    req.on('error',reject); req.end(body && JSON.stringify(body));
  });
  assert.equal((await request('/api/queries/status')).status,401);
  assert.equal((await request('/api/commands/login','POST',{code:'00000000'})).status,403);
  assert.equal((await request('/api/commands/login','POST',{code:'éééééééé'},{Origin:origin})).status,401);
  // Access code is exposed solely over a private local socket, never through LAN status.
  const http = await import('node:http');
  const info = await new Promise((resolve,reject) => {
    http.get({socketPath:join(dir,'bridge.sock'),path:'/status'},res => {
      let data='';res.on('data',c=>data+=c);res.on('end',()=>resolve(JSON.parse(data)));
    }).on('error',reject);
  });
  const login = await request('/api/commands/login','POST',{code:info.code},{Origin:origin});
  assert.equal(login.status,200);
  const status = await request('/api/queries/status','GET',null,{Cookie:login.cookie});
  assert.equal(status.body.phase,'idle'); assert.equal(status.body.code,undefined); assert.equal(starts,0);
  const connect = async () => {
    const ws=new WebSocket(origin.replace('https','wss')+'/api/session',{rejectUnauthorized:false,headers:{Origin:origin,Cookie:login.cookie}});
    await once(ws,'open'); return ws;
  };
  const denied = new WebSocket(origin.replace('https','wss')+'/api/session',{rejectUnauthorized:false,headers:{Origin:origin}});
  await assert.rejects(once(denied,'open'));
  const crossOrigin = new WebSocket(origin.replace('https','wss')+'/api/session',{rejectUnauthorized:false,headers:{Origin:'https://another-site.invalid',Cookie:login.cookie}});
  await assert.rejects(once(crossOrigin,'open'));
  const first=await connect(); const second=await connect();
  t.after(()=>{first.terminate();second.terminate();});
  const started = once(first,'message'); first.send(JSON.stringify({type:'start'}));
  await started;
  const rejected = once(second,'message'); second.send(JSON.stringify({type:'start'}));
  assert.match(JSON.parse((await rejected)[0]).error,/Game in use/);
  first.close(); await once(first,'close');
  for(let i=0;i<50 && closes===0;i++)await new Promise(r=>setTimeout(r,10));
  assert.equal(closes,1);
  const restarted=once(second,'message');second.send(JSON.stringify({type:'start'}));await restarted;
  assert.equal(starts,2);
});
