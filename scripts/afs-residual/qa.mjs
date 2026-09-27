// Read-only public-site A/B. B substitutes the prepared bundle and runtime only
// inside this browser context; it does not write Freight, Cargo, or production.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright-core';

const here=path.dirname(fileURLToPath(import.meta.url));
const out=process.argv[2]||path.join(process.cwd(),'afs-residual-qa');
fs.mkdirSync(out,{recursive:true});
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const oldBundle='afs-custom-html.7eb327015e626fd3.js';
const oldRuntime='afs-site-runtime-v6.0.8-4f0da0796acfc010.txt';
const placeholder='F0000000000000000000000000000000';
const newBundleName='afs-custom-html.cf4656f21e4f0660.js';
const newRuntimeName='afs-site-runtime-v6.0.8-164a55f93430de03.txt';
const newBundle=fs.readFileSync(path.join(here,newBundleName));
const newStub=fs.readFileSync(path.join(here,'Custom-HTML.stub.PLACEHOLDER.html'),'utf8');
const tagPattern=/<script id="afs-custom-html-bundle"[^>]*><\/script>/g;
const tagHits=[...newStub.matchAll(tagPattern)];
if(tagHits.length!==1||sha(newBundle)!=='cf4656f21e4f0660d0e1fb43338d648a9eefccd3ecdc139abda38ea0a131f248')throw Error('candidate bundle/stub pin mismatch');
const newTag=tagHits[0][0];
if(!newTag.includes(newBundleName)||!newTag.includes(placeholder))throw Error('candidate tag does not match placeholder bundle');
const cases=[
  ['desktop-home','desktop','/'],['mobile-home','mobile','/'],
  ['desktop-html','desktop','/?mode=html'],['desktop-clean','desktop','/?mode=clean'],
  ['desktop-before-arts','desktop','/before-arts'],['mobile-before-arts','mobile','/before-arts']
];
const profiles={desktop:{viewport:{width:1350,height:940},deviceScaleFactor:1},mobile:{viewport:{width:412,height:823},deviceScaleFactor:1.75,isMobile:true,hasTouch:true}};
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
const rows=[];let runtimeA=null,runtimeB=null;
const runtimeReplies=[];

async function buildRuntime(buf){
  if(buf.length!==407172||sha(buf)!=='4f0da0796acfc010018a9fcf7ea04fea314e707a00c24bf56100b43d10b9557e')throw Error(`live runtime changed; observed bytes=${buf.length} sha256=${sha(buf)}; cannot patch this base`);
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'afs-runtime-'));
  const a=path.join(dir,'runtime-a.txt'),b=path.join(dir,'runtime-b.txt');
  fs.writeFileSync(a,buf);
  const x=spawnSync('python3',[path.join(here,'make-idempotent.py'),a,b],{encoding:'utf8'});
  if(x.status!==0)throw Error('runtime patch failed: '+(x.stderr||x.stdout).slice(0,300));
  const patched=fs.readFileSync(b);
  if(patched.length!==407333||sha(patched)!=='164a55f93430de03dadecdecd03512460479c2044d893f4b5b8ed4b1eddeda0f')throw Error('patched runtime pin mismatch');
  return patched;
}

function sanitizeHeaders(response){
  const h={...response.headers()};
  delete h['content-encoding'];delete h['content-length'];delete h['transfer-encoding'];
  return h;
}

async function visit(name,form,route,variant){
  const ctx=await browser.newContext(profiles[form]);
  await ctx.addInitScript(()=>{
    const old=window.MutationObserver;
    const count=window.__afsMutationCensus={callbacks:0,attributeRecords:0,totalRecords:0};
    window.MutationObserver=class extends old{constructor(cb){super((records,observer)=>{count.callbacks++;count.totalRecords+=records.length;count.attributeRecords+=records.filter(r=>r.type==='attributes').length;return cb(records,observer)})}};
  });
  let documentPin=null,bundleLoaded=false,runtimeLoaded=false;
  const errors=[],failed=[];
  await ctx.route('https://arthurfouray.systems/**',async r=>{
    if(r.request().resourceType()!=='document')return r.continue();
    const resp=await r.fetch();let body=await resp.text();
    const tags=[...body.matchAll(tagPattern)];
    if(tags.length!==1||!tags[0][0].includes(oldBundle))throw Error('live document bundle tag changed');
    if(new URL(r.request().url()).pathname==='/'&&new URL(r.request().url()).search===''){
      documentPin=sha(Buffer.from(body));
      if(documentPin!=='8823ffd20a7bbad6523e7db616ff5a98c79e2b245288d6ab83e50d311c2555b0')throw Error('public homepage changed');
    }
    if(variant==='B')body=body.replace(tagPattern,newTag);
    await r.fulfill({status:resp.status(),headers:sanitizeHeaders(resp),body});
  });
  if(variant==='B'){
    await ctx.route(u=>u.hostname==='freight.cargo.site'&&u.pathname.endsWith('/'+newBundleName),async r=>{
      bundleLoaded=true;
      await r.fulfill({status:200,body:newBundle,headers:{'content-type':'application/javascript; charset=utf-8','access-control-allow-origin':'*','cache-control':'no-store'}});
    });
    await ctx.route(u=>u.hostname==='freight.cargo.site'&&u.pathname.endsWith('/'+newRuntimeName),async r=>{
      if(!runtimeB)throw Error('runtime B was not built from A');
      runtimeLoaded=true;
      await r.fulfill({status:200,body:runtimeB,headers:{'content-type':'text/plain; charset=utf-8','access-control-allow-origin':'*','cache-control':'no-store'}});
    });
  }
  const page=await ctx.newPage();
  page.on('pageerror',e=>errors.push(String(e).slice(0,300)));
  page.on('requestfailed',r=>failed.push({url:r.url().slice(0,180),failure:r.failure()?.errorText}));
  if(variant==='A'&&!runtimeA)page.on('response',r=>{
    if(r.url().includes('/'+oldRuntime))runtimeReplies.push(r.body().then(b=>({status:r.status(),body:b,url:r.url(),contentType:r.headers()['content-type']})).catch(e=>({error:String(e)})));
  });
  let navigation=null;
  try{await page.goto('https://arthurfouray.systems'+route,{waitUntil:'load',timeout:120000})}catch(e){navigation=String(e).slice(0,300)}
  await page.waitForTimeout(12000);
  if(variant==='A'&&!runtimeA){
    const replies=await Promise.all(runtimeReplies);
    const good=replies.find(r=>r.status===200&&r.body);
    if(!good)throw Error('published runtime response not captured: '+JSON.stringify(replies.map(r=>({status:r.status,error:r.error,url:r.url}))));
    fs.writeFileSync(path.join(out,'runtime-source-observation.json'),JSON.stringify({status:good.status,url:good.url,contentType:good.contentType,bytes:good.body.length,sha256:sha(good.body)},null,2));
    fs.writeFileSync(path.join(out,'runtime-served-for-diff.txt'),good.body);
    runtimeA=good.body;runtimeB=await buildRuntime(runtimeA);
    fs.writeFileSync(path.join(out,'runtime-pins.json'),JSON.stringify({sourceBytes:runtimeA.length,sourceSha256:sha(runtimeA),patchedBytes:runtimeB.length,patchedSha256:sha(runtimeB),sourceUrl:good.url},null,2));
  }
  const before=await page.evaluate(()=>({mode:document.documentElement.dataset.mode,title:document.title,bodyText:document.body?.innerText||'',pages:document.querySelectorAll('.page').length,mediaItems:document.querySelectorAll('media-item').length,navLayers:document.querySelectorAll('.nav-layer').length,guardActive:!/\[native code\]/.test(String(Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src').set)),scrollHeight:document.scrollingElement.scrollHeight}));
  before.bodyTextSha256=sha(Buffer.from(before.bodyText));before.bodyTextBytes=Buffer.byteLength(before.bodyText);delete before.bodyText;
  await page.screenshot({path:path.join(out,`${name}-${variant}-top.png`),animations:'disabled',timeout:60000}).catch(e=>errors.push('screenshot: '+String(e).slice(0,200)));
  await page.evaluate(()=>{window.__afsMutationCensus.callbacks=0;window.__afsMutationCensus.attributeRecords=0;window.__afsMutationCensus.totalRecords=0});
  await page.evaluate(()=>scrollTo({top:Math.round((document.scrollingElement.scrollHeight-innerHeight)*0.55),behavior:'instant'}));
  await page.waitForTimeout(6000);
  const after=await page.evaluate(()=>({mode:document.documentElement.dataset.mode,scrollY,scrollHeight:document.scrollingElement.scrollHeight,navLayers:document.querySelectorAll('.nav-layer').length,mediaItems:document.querySelectorAll('media-item').length,htmlTone:document.documentElement.getAttribute('data-nav-tone'),mutationCensus:{...window.__afsMutationCensus}}));
  await page.screenshot({path:path.join(out,`${name}-${variant}-mid.png`),animations:'disabled',timeout:60000}).catch(e=>errors.push('screenshot: '+String(e).slice(0,200)));
  const row={name,form,route,variant,documentPin,navigation,bundleLoaded,runtimeLoaded,before,after,errors,failed};
  await ctx.close();
  return row;
}

try{
  outer: for(const [name,form,route] of cases){
    for(const variant of ['A','B']){
      if(variant==='B'&&!runtimeB){rows.push({name,form,route,variant,error:'skipped: source runtime did not match pin'});break outer}
      try{const row=await visit(name,form,route,variant);rows.push(row);console.log(JSON.stringify({name,variant,mode:row.before.mode,guard:row.before.guardActive,bundle:row.bundleLoaded,runtime:row.runtimeLoaded,mutations:row.after.mutationCensus,errors:row.errors.length,failed:row.failed.length}))}
      catch(e){rows.push({name,form,route,variant,error:String(e)});console.error(JSON.stringify({name,variant,error:String(e)}))}
      fs.writeFileSync(path.join(out,'rows.json'),JSON.stringify(rows,null,2));
    }
  }
}finally{await browser.close()}
const pairs=cases.map(([name])=>({name,A:rows.find(r=>r.name===name&&r.variant==='A'),B:rows.find(r=>r.name===name&&r.variant==='B')}));
const failures=[];
for(const p of pairs){
  if(!p.A||!p.B||p.A.error||p.B.error){failures.push(`${p.name}: missing or failed case`);continue}
  if(!p.B.bundleLoaded||!p.B.runtimeLoaded||!p.B.before.guardActive)failures.push(`${p.name}: candidate bundle/runtime/guard not active`);
  for(const k of ['mode','title','bodyTextSha256','pages','mediaItems','navLayers'])if(p.A.before[k]!==p.B.before[k])failures.push(`${p.name}: ${k} differs`);
  for(const k of ['mode','navLayers','mediaItems','htmlTone'])if(p.A.after[k]!==p.B.after[k])failures.push(`${p.name}: mid ${k} differs`);
  const extra=p.B.errors.filter(x=>!p.A.errors.includes(x));if(extra.length)failures.push(`${p.name}: candidate-only page errors ${extra.length}`);
}
const summary={cases:cases.length,rows:rows.length,runtimeA:runtimeA&&{bytes:runtimeA.length,sha256:sha(runtimeA)},runtimeB:runtimeB&&{bytes:runtimeB.length,sha256:sha(runtimeB)},failures,pairedMutations:pairs.map(p=>({name:p.name,A:p.A?.after?.mutationCensus,B:p.B?.after?.mutationCensus}))};
fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify(summary,null,2));
console.log(JSON.stringify(summary));
if(failures.length||rows.length!==cases.length*2)process.exitCode=1;
