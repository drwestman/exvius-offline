// Opt-in: real Android capture through the complete HTTPS/WSS/browser pipeline.
// Uses temporary certificates, never installs trust, starts activities, or injects input.
import { serve } from '../dist/server.js';
import { ScrcpyAdapter } from '../dist/scrcpy.js';
import { chromium, webkit } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import http from 'node:http';
const root = await mkdtemp('/private/tmp/exvius-live-');
execFileSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-keyout',root+'/key.pem','-out',root+'/cert.pem','-subj','/CN=localhost','-days','1'],{stdio:'ignore'});
const adapter = new ScrcpyAdapter(process.argv[2],process.argv[3],process.argv[4]);
const stats={video:0,audio:0};
const bridge=await serve({hosts:['127.0.0.1'],names:['127.0.0.1'],port:18445,cert:root+'/cert.pem',key:root+'/key.pem',ipc:root+'/bridge.sock',sdk:'live',serial:process.argv[2]},{
  start(sink) { return adapter.start({...sink,packet(...args){stats[args[0]===1?'video':'audio']++;sink.packet(...args);}}); }
});
try {
  const info=await new Promise((resolve,reject)=>{
    http.get({socketPath:root+'/bridge.sock',path:'/status'},res=>{
      let body='';res.on('data',c=>body+=c);res.on('end',()=>resolve(JSON.parse(body)));
    }).on('error',reject);
  });
  for(const [name, engine] of [['chromium',chromium],['webkit',webkit]]) {
    const browser=await engine.launch();
    try {
      const page=await browser.newPage({ignoreHTTPSErrors:true});
      const errors=[];page.on('pageerror',e=>errors.push(e.message));
      await page.goto('https://127.0.0.1:18445');
      await page.getByLabel('Access code').fill(info.code);
      await page.getByRole('button',{name:'Connect',exact:true}).click();
      await page.getByRole('button',{name:'Play',exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('#connection').textContent==='Playing');
      await page.waitForFunction(()=>document.querySelector('canvas').getContext('2d').getImageData(10,10,1,1).data[3]===255);
      await page.screenshot({path:root+'/'+name+'.png'});
      if(errors.length) throw new Error(errors.join('\n'));
      console.log(name+': real Android frame rendered over HTTPS');
      await page.getByRole('button',{name:'Disconnect',exact:true}).click();
      await new Promise(resolve=>setTimeout(resolve,1000));
    } finally { await browser.close(); }
  }
  console.log(JSON.stringify(stats));
} finally { await bridge.shutdown(); await rm(root,{recursive:true,force:true}); }
