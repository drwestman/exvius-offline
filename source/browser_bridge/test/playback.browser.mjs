import { test, expect } from '@playwright/test';
import http from 'node:http';
import { readFile } from 'node:fs/promises';
test.use({ hasTouch: true });
test('given a paired browser when Play is pressed then real H264 decodes and touch and keyboard commands reach the adapter',async({page})=>{
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  const info=await new Promise((resolve,reject)=>{
    http.get({socketPath:'/private/tmp/exvius-browser-playwright/bridge.sock',path:'/status'},res=>{
      let body='';res.on('data',c=>body+=c);res.on('end',()=>resolve(JSON.parse(body)));
    }).on('error',reject);
  });
  await page.addInitScript(() => {
    const Context = window.AudioContext;
    window.AudioContext = class extends Context {
      createGain() {
        const gain = super.createGain();
        const analyser = this.createAnalyser();
        gain.connect(analyser);
        window.testAnalyser = analyser;
        return gain;
      }
    };
  });
  await page.goto('/');
  await page.getByLabel('Access code').fill(info.code);
  await page.getByRole('button',{name:'Connect',exact:true}).click();
  await expect(page.getByRole('button',{name:'Play',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'Play',exact:true}).click();
  await expect(page.locator('#connection')).toHaveText('Playing');
  await expect.poll(()=>page.locator('canvas').evaluate(c=>{const p=c.getContext('2d').getImageData(10,10,1,1).data;return p[2]>200 && p[0]<30;})).toBe(true);
  await expect.poll(()=>page.evaluate(()=>{
    const a=window.testAnalyser; if(!a)return false;
    const samples=new Float32Array(a.fftSize);a.getFloatTimeDomainData(samples);
    return samples.some(v=>Math.abs(v)>.001);
  })).toBe(true);
  await page.locator('#volume').evaluate(el=>{el.value='0';el.dispatchEvent(new Event('input'));});
  await expect.poll(()=>page.evaluate(()=>{
    const a=window.testAnalyser; const samples=new Float32Array(a.fftSize);a.getFloatTimeDomainData(samples);
    return samples.every(v=>Math.abs(v)<.00001);
  })).toBe(true);
  const box=await page.locator('canvas').boundingBox();
  await page.mouse.click(box.x+box.width*.5,box.y+box.height*.5);
  await page.keyboard.press('Escape');
  await page.setViewportSize({width:390,height:844});
  const mobile=await page.locator('canvas').boundingBox();
  await page.touchscreen.tap(mobile.x+mobile.width*.5,mobile.y+mobile.height*.5);
  await expect.poll(async()=>JSON.parse(await readFile('/private/tmp/exvius-browser-playwright/inputs.json','utf8')).length).toBeGreaterThanOrEqual(6);
  const inputs=JSON.parse(await readFile('/private/tmp/exvius-browser-playwright/inputs.json','utf8'));
  expect(inputs.some(c=>c.type==='pointer'&&c.action==='down'&&Math.abs(c.x-.5)<.03&&Math.abs(c.y-.5)<.03)).toBe(true);
  await page.getByRole('button',{name:'Disconnect',exact:true}).click();
  await expect(page.getByRole('button',{name:'Play',exact:true})).toBeEnabled();
  // Reconnect starts a fresh capture; stale close callbacks cannot clear it.
  await page.getByRole('button',{name:'Play',exact:true}).click();
  await expect(page.locator('#connection')).toHaveText('Playing');
  await page.getByRole('button',{name:'Disconnect',exact:true}).click();
  expect(errors).toEqual([]);
});
