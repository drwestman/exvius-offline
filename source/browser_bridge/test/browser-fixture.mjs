import { serve } from '../dist/server.js';
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, rm, writeFile, unlink } from 'node:fs/promises';
const root = '/private/tmp/exvius-browser-playwright';
await mkdir(root,{recursive:true});
execFileSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-keyout',root+'/key.pem','-out',root+'/cert.pem','-subj','/CN=localhost','-days','1'],{stdio:'ignore'});
const video = await readFile(new URL('fixtures/blue.h264',import.meta.url));
const nals = [];
const starts = [];
for(let i=0;i<video.length-3;i++) {
  if(video[i]===0 && video[i+1]===0 && video[i+2]===1) { starts.push([i,i+3]);i+=2; }
  else if(video[i]===0 && video[i+1]===0 && video[i+2]===0 && video[i+3]===1) { starts.push([i,i+4]);i+=3; }
}
for(let i=0;i<starts.length;i++) nals.push({type:video[starts[i][1]]&31,data:video.subarray(starts[i][0],starts[i+1]?.[0]??video.length)});
const config = Buffer.concat(nals.filter(n=>n.type===7||n.type===8).map(n=>n.data));
const keyframe = Buffer.concat(nals.filter(n=>n.type!==7&&n.type!==8).map(n=>n.data));
await unlink(root+'/bridge.sock').catch(()=>{});
const app = await serve({hosts:['127.0.0.1'],names:['127.0.0.1'],port:18444,cert:root+'/cert.pem',key:root+'/key.pem',ipc:root+'/bridge.sock',serial:'emulator-test',sdk:'fixture'},{
  async start(sink) {
    const inputs=[];
    sink.metadata({width:360,height:640,codec:0x68323634});
    let frame=0;
    const timer=setInterval(()=>{
      if(frame===0) sink.packet(1,1,0n,config);
      sink.packet(1,2,BigInt(frame++*20000),keyframe);
      const pcm=Buffer.alloc(3840);
      for(let i=0;i<960;i++) { const v=Math.round(Math.sin(i*Math.PI*2*440/48000)*1000);pcm.writeInt16LE(v,i*4);pcm.writeInt16LE(v,i*4+2); }
      sink.packet(2,0,0n,pcm);
    },20);
    return { async input(c){inputs.push(c);await writeFile(root+'/inputs.json',JSON.stringify(inputs));},async close(){clearInterval(timer);} };
  }
});
process.on('SIGTERM',async()=>{await app.shutdown();await rm(root,{recursive:true,force:true});process.exit();});
