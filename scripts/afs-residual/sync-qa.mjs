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
const newBundleName='afs-custom-html.f348acaf25672458.js';
const newRuntimeName='afs-site-runtime-v6.0.8-164a55f93430de03.txt';
const guardBundleName='afs-custom-html.da37965d685647a9.js';
const syncMatrix=true;
const syncBundleName="afs-custom-html.6b1c760cb96688bd.js",metaBundleName="afs-custom-html.ca9faab3e1846ac0.js",metaRuntimeName="afs-site-runtime-v6.0.8-c045315aef77410f.txt";
const syncBundle=fs.readFileSync(path.join(here,syncBundleName)),metaBundle=fs.readFileSync(path.join(here,metaBundleName)),metaRuntime=fs.readFileSync(path.join(here,metaRuntimeName));
const syncStub=fs.readFileSync(path.join(here,'Custom-HTML.gif-synchronous.stub.PLACEHOLDER.html'),'utf8'),metaStub=fs.readFileSync(path.join(here,'Custom-HTML.runtime-metadata.stub.PLACEHOLDER.html'),'utf8');
const gifMap=JSON.parse(fs.readFileSync(path.join(here,'canonical-gif-map.json'),'utf8'));
const gifUrls=new Set(Object.values(gifMap).flatMap(x=>[x.thumbnailUrl,x.canonicalUrl]));let gifProof=null;
if(sha(syncBundle)!=="6b1c760cb96688bdc240c9fc3df51cbf3c23706985e20893a8e2870a8ce187f4"||sha(metaBundle)!=="ca9faab3e1846ac0bb422df88c367a10fdf080f15b556778c62a73d49bb07df0"||sha(metaRuntime)!=="c045315aef77410ffa72e5a668c5ee9928d588889c1be5bef1e364289a3658ad")throw Error('Synchronous candidate pin mismatch');
const noopMatrix=process.env.AFS_QA_MATRIX==='paint-control';
const lateGuardName="afs-custom-html.b1dfc4e68282f59d.js";
const lateGuardBundle=fs.readFileSync(path.join(here,lateGuardName));
const lateGuardStub=fs.readFileSync(path.join(here,'Custom-HTML.late-guard.stub.PLACEHOLDER.html'),'utf8');
if(sha(lateGuardBundle)!=="b1dfc4e68282f59dc092a0ed9b8cae46384bcedc0eec6bc76fa8c0b608b972b7")throw Error('Late guard source mismatch');
const runtimeMatrix=process.env.AFS_QA_MATRIX==='runtime'||noopMatrix;
const noopBundle=fs.readFileSync(path.join(here,oldBundle));
const runtimeOnlyName='afs-custom-html.aea5e9cf36008686.js';
const runtimeOnlyBundle=fs.readFileSync(path.join(here,runtimeOnlyName));
const noopStub=fs.readFileSync(path.join(here,'Custom-HTML.noop.stub.PLACEHOLDER.html'),'utf8');
const runtimeOnlyStub=fs.readFileSync(path.join(here,'Custom-HTML.runtime-only.stub.PLACEHOLDER.html'),'utf8');
if(sha(noopBundle)!=='7eb327015e626fd36e1b5ed824faec6e5dbe6bb9fefe5fd5b9f2a10608845d18'||sha(runtimeOnlyBundle)!=='aea5e9cf360086863ebac714add32a1100d764e18c966b31143f8a6e911f04ef')throw Error('No-op/runtime-only base mismatch');
const paintDiagnostic=process.env.AFS_QA_PAINT_DIAGNOSTIC==='1';
const newBundle=fs.readFileSync(path.join(here,newBundleName));
const newStub=fs.readFileSync(path.join(here,'Custom-HTML.stub.PLACEHOLDER.html'),'utf8');
const guardBundle=runtimeMatrix?fs.readFileSync(path.join(here,guardBundleName)):null;
const guardStub=runtimeMatrix?fs.readFileSync(path.join(here,'Custom-HTML.guard-only.stub.PLACEHOLDER.html'),'utf8'):null;
const tagPattern=/<script id="afs-custom-html-bundle"[^>]*><\/script>/g;
const tagHits=[...newStub.matchAll(tagPattern)];
if(tagHits.length!==1||sha(newBundle)!=='f348acaf256724583b39e118e5f76ad379bb845e49e848712e0f68164465556c')throw Error('candidate bundle/stub pin mismatch');
const newTag=tagHits[0][0];
if(!newTag.includes(newBundleName)||!newTag.includes(placeholder))throw Error('candidate tag does not match placeholder bundle');
const guardTags=runtimeMatrix?[...guardStub.matchAll(tagPattern)]:[];
if(runtimeMatrix&&(guardTags.length!==1||sha(guardBundle)!=='da37965d685647a935ef7ad255fcddff53b432b004d5e5485146ee54b4ad5594'))throw Error('guard-only bundle/stub pin mismatch');
const guardTag=runtimeMatrix?guardTags[0][0]:null;
const cases=syncMatrix?[['desktop-home','desktop','/'],['mobile-home','mobile','/']]:noopMatrix?[['mobile-home','mobile','/']]:runtimeMatrix?[
  ['desktop-home','desktop','/'],['mobile-home','mobile','/']
]:[
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


// A production field exists both in SSR and Cargo's hydration state. Change both,
// or this is not a simulation of a real Cargo field release.
function substituteCustomHtml(documentHtml, oldTag, newTag){
  const fields=[...documentHtml.matchAll(/<customhtml\b[^>]*>([\s\S]*?)<\/customhtml>/gi)];
  const slots=[...documentHtml.matchAll(/"custom_html"\s*:\s*("(?:\\.|[^"\\])*")/g)];
  if(fields.length!==1||slots.length!==1)throw Error('SSR/preloaded Custom HTML field count changed');
  const field=fields[0][1];
  if(JSON.parse(slots[0][1])!==field)throw Error('SSR and preloaded Custom HTML differ before substitution');
  if(field.split(oldTag).length!==2)throw Error('Expected exactly one source bundle tag');
  const updatedField=field.replace(oldTag,newTag);
  const encoded=JSON.stringify(updatedField).replace(/</g,'\\u003c').replace(/\u2028/g,'\\u2028').replace(/\u2029/g,'\\u2029');
  let updated=documentHtml.replace(slots[0][1],()=>encoded).replace(oldTag,()=>newTag);
  const afterField=[...updated.matchAll(/<customhtml\b[^>]*>([\s\S]*?)<\/customhtml>/gi)][0][1];
  const afterSlot=[...updated.matchAll(/"custom_html"\s*:\s*("(?:\\.|[^"\\])*")/g)][0][1];
  if(afterField!==updatedField||JSON.parse(afterSlot)!==updatedField)throw Error('SSR/preloaded substitution did not round-trip');
  return updated;
}

function sanitizeHeaders(response){
  const h={...response.headers()};
  delete h['content-encoding'];delete h['content-length'];delete h['transfer-encoding'];
  return h;
}

async function visit(name,form,route,variant){
  const combined=variant==='B'||variant==='B2';
  const runtimeOnly=variant==='D';
  const noop=variant==='E'||variant==='F';
  const runtimeNoop=variant==='F';
  const lateGuard=variant==='L';
  const gifSync=variant==='G',metadata=variant==='R';
  if(gifSync&&!gifProof?.accepted)throw Error('Live GIF transform identity proof not accepted; synchronous alias test held');
  const gifReplies=[];
  const guardOnly=variant==='C'||variant==='C2';
  const ctx=await browser.newContext(profiles[form]);
  await ctx.addInitScript(()=>{
    const old=window.MutationObserver;
    const count=window.__afsMutationCensus={callbacks:0,attributeRecords:0,totalRecords:0};
    window.MutationObserver=class extends old{constructor(cb){super((records,observer)=>{count.callbacks++;count.totalRecords+=records.length;count.attributeRecords+=records.filter(r=>r.type==='attributes').length;return cb(records,observer)})}};
  });
  let documentPin=null,documentFieldSha=null,frontendBuild=null,bundleLoaded=false,runtimeLoaded=false;
  const errors=[],failed=[];
  await ctx.route('https://arthurfouray.systems/**',async r=>{
    if(r.request().resourceType()!=='document')return r.continue();
    const resp=await r.fetch();let body=await resp.text();
    const tags=[...body.matchAll(tagPattern)];
    const fields=[...body.matchAll(/<customhtml\b[^>]*>([\s\S]*?)<\/customhtml>/gi)];
    if(fields.length!==1)throw Error('customhtml count changed');
    documentFieldSha=sha(Buffer.from(fields[0][1]));
    if(documentFieldSha!=='d3ce518f02ef39cc56a8ccf6de78a871fc657fa622a302ac2058dc7024f72aef')throw Error('public Custom HTML field changed');
    const builds=[...body.matchAll(/https:\/\/build\.cargo\.site\/frontend\/([^/]+)\/index\.(?:js|css)/g)].map(x=>x[1]);
    if(builds.length!==2||builds.some(x=>x!=='b8c0c2'))throw Error('Cargo frontend changed during the test');
    frontendBuild=builds[0];
    if(tags.length!==1||!tags[0][0].includes(oldBundle))throw Error('live document bundle tag changed');
    if(new URL(r.request().url()).pathname==='/'&&new URL(r.request().url()).search===''){
      documentPin=sha(Buffer.from(body));
      if(documentPin!=='a89eba0a92e595af75183f9e1768c27e453c8d99f1dbeaa048b991f75dfe5d6f')throw Error('public homepage changed');
    }
    if(combined)body=substituteCustomHtml(body,tags[0][0],newTag);
    if(guardOnly)body=substituteCustomHtml(body,tags[0][0],guardTag);
    if(runtimeOnly)body=substituteCustomHtml(body,tags[0][0],[...runtimeOnlyStub.matchAll(tagPattern)][0][0]);
    if(noop)body=substituteCustomHtml(body,tags[0][0],[...noopStub.matchAll(tagPattern)][0][0]);
    if(lateGuard)body=substituteCustomHtml(body,tags[0][0],[...lateGuardStub.matchAll(tagPattern)][0][0]);
    if(gifSync)body=substituteCustomHtml(body,tags[0][0],[...syncStub.matchAll(tagPattern)][0][0]);
    if(metadata)body=substituteCustomHtml(body,tags[0][0],[...metaStub.matchAll(tagPattern)][0][0]);
    await r.fulfill({status:resp.status(),headers:sanitizeHeaders(resp),body});
  });
  if(gifSync||metadata){
    const file=gifSync?syncBundleName:metaBundleName,buf=gifSync?syncBundle:metaBundle;
    await ctx.route(u=>u.hostname==='freight.cargo.site'&&u.pathname.endsWith('/'+file),async r=>{bundleLoaded=true;await r.fulfill({status:200,body:buf,headers:{'content-type':'application/javascript; charset=utf-8','access-control-allow-origin':'*','cache-control':'no-store'}})});
  }
  if(metadata){
    await ctx.route(u=>u.hostname==='freight.cargo.site'&&u.pathname.endsWith('/'+metaRuntimeName),async r=>{runtimeLoaded=true;await r.fulfill({status:200,body:metaRuntime,headers:{'content-type':'text/plain; charset=utf-8','access-control-allow-origin':'*','cache-control':'no-store'}})});
  }
  if(lateGuard){
    await ctx.route(u=>u.hostname==='freight.cargo.site'&&u.pathname.endsWith('/'+lateGuardName),async r=>{bundleLoaded=true;await r.fulfill({status:200,body:lateGuardBundle,headers:{'content-type':'application/javascript; charset=utf-8','access-control-allow-origin':'*','cache-control':'no-store'}})});
  }
  if(runtimeNoop){
    await ctx.route(u=>u.hostname==='freight.cargo.site'&&u.pathname.endsWith('/'+oldRuntime),async r=>{if(!runtimeA)throw Error('Runtime no-op base missing');runtimeLoaded=true;await r.fulfill({status:200,body:runtimeA,headers:{'content-type':'text/plain; charset=utf-8','access-control-allow-origin':'*','cache-control':'no-store'}})});
  }
  if(noop||runtimeOnly){
    const file=noop?oldBundle:runtimeOnlyName,buf=noop?noopBundle:runtimeOnlyBundle;
    await ctx.route(u=>u.hostname==='freight.cargo.site'&&u.pathname.endsWith('/'+file),async r=>{bundleLoaded=true;await r.fulfill({status:200,body:buf,headers:{'content-type':'application/javascript; charset=utf-8','access-control-allow-origin':'*','cache-control':'no-store'}})});
  }
  if(runtimeOnly){
    await ctx.route(u=>u.hostname==='freight.cargo.site'&&u.pathname.endsWith('/'+newRuntimeName),async r=>{if(!runtimeB)throw Error('runtime B missing');runtimeLoaded=true;await r.fulfill({status:200,body:runtimeB,headers:{'content-type':'text/plain; charset=utf-8','access-control-allow-origin':'*','cache-control':'no-store'}})});
  }
  if(combined){
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
  if(guardOnly){
    await ctx.route(u=>u.hostname==='freight.cargo.site'&&u.pathname.endsWith('/'+guardBundleName),async r=>{
      bundleLoaded=true;
      await r.fulfill({status:200,body:guardBundle,headers:{'content-type':'application/javascript; charset=utf-8','access-control-allow-origin':'*','cache-control':'no-store'}});
    });
  }
  const page=await ctx.newPage();
  if(variant==='A'&&!gifProof)page.on('response',r=>{if(gifUrls.has(r.url()))gifReplies.push(r.body().then(buf=>({url:r.url(),status:r.status(),contentType:r.headers()['content-type'],bytes:buf.length,sha256:sha(buf),header:buf.subarray(0,6).toString('ascii'),width:buf.length>=10?buf.readUInt16LE(6):null,height:buf.length>=10?buf.readUInt16LE(8):null})).catch(e=>({url:r.url(),status:r.status(),error:String(e)})))});
  const cdp=await ctx.newCDPSession(page);
  await cdp.send('Network.enable');
  const requests=new Map();
  cdp.on('Network.requestWillBeSent',e=>requests.set(e.requestId,{url:e.request.url,type:e.type}));
  cdp.on('Network.responseReceived',e=>{const x=requests.get(e.requestId);if(x)x.status=e.response.status});
  cdp.on('Network.loadingFinished',e=>{const x=requests.get(e.requestId);if(x)x.bytes=e.encodedDataLength});
  cdp.on('Network.loadingFailed',e=>{const x=requests.get(e.requestId);if(x)x.failed=e.errorText});
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
    const browserProbe=await page.evaluate(async url=>{
      const root=document.documentElement;
      const loader={state:root.dataset.afsRuntimeLoader,error:root.dataset.afsRuntimeLoaderError,resourceState:root.dataset.afsRuntimeResourceState,resourceError:root.dataset.afsRuntimeResourceError};
      try{
        const response=await fetch(url,{credentials:'omit',cache:'force-cache',redirect:'error'});
        const bytes=new Uint8Array(await response.arrayBuffer());
        const chunks=[];for(let i=0;i<bytes.length;i+=8192)chunks.push(String.fromCharCode(...bytes.slice(i,i+8192)));
        return {status:response.status,contentType:response.headers.get('content-type'),bytes:bytes.length,base64:btoa(chunks.join('')),loader};
      }catch(e){return {error:String(e),loader}}
    },good.url);
    const browserBody=browserProbe.base64?Buffer.from(browserProbe.base64,'base64'):null;
    fs.writeFileSync(path.join(out,'runtime-source-observation.json'),JSON.stringify({status:good.status,url:good.url,contentType:good.contentType,playwrightBytes:good.body.length,playwrightSha256:sha(good.body),browserStatus:browserProbe.status,browserContentType:browserProbe.contentType,browserBytes:browserBody?.length,browserSha256:browserBody&&sha(browserBody),browserError:browserProbe.error,loader:browserProbe.loader},null,2));
    fs.writeFileSync(path.join(out,'runtime-served-for-diff.txt'),good.body);
    if(!browserBody)throw Error('in-page runtime fetch failed: '+browserProbe.error);
    runtimeA=browserBody;runtimeB=await buildRuntime(runtimeA);
    fs.writeFileSync(path.join(out,'runtime-pins.json'),JSON.stringify({sourceBytes:runtimeA.length,sourceSha256:sha(runtimeA),patchedBytes:runtimeB.length,patchedSha256:sha(runtimeB),sourceUrl:good.url},null,2));
  }
  const before=await page.evaluate(()=>({mode:document.documentElement.dataset.mode,title:document.title,bodyText:document.body?.innerText||'',pages:document.querySelectorAll('.page').length,mediaItems:document.querySelectorAll('media-item').length,navLayers:document.querySelectorAll('.nav-layer').length,srcSetterSource:String(Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src').set).slice(0,2000),guardActive:!/\[native code\]/.test(String(Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src').set)),guardMarker:String(Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src').set).includes('q.get(this)!=o'),scrollHeight:document.scrollingElement.scrollHeight}));
  fs.writeFileSync(path.join(out,`${name}-${variant}-text.txt`),before.bodyText);
  before.bodyTextSha256=sha(Buffer.from(before.bodyText));before.bodyTextBytes=Buffer.byteLength(before.bodyText);delete before.bodyText;
  await page.screenshot({path:path.join(out,`${name}-${variant}-top.png`),animations:'allow',timeout:60000}).catch(e=>errors.push('screenshot: '+String(e).slice(0,200)));
  let paintDiagnostics=null;
  {
    async function paintState(){return page.evaluate(()=>{
      const styleOf=n=>{const s=getComputedStyle(n),b=n.getBoundingClientRect();return {tag:n.tagName,id:n.id,classes:typeof n.className==='string'?n.className:'',attrs:Object.fromEntries([...n.attributes].map(x=>[x.name,x.value])),rect:{x:b.x,y:b.y,width:b.width,height:b.height},style:Object.fromEntries(['display','visibility','opacity','color','backgroundColor','filter','transform','mixBlendMode','overflow','clipPath','zIndex','pointerEvents','fontFamily','animationName','animationPlayState','transitionProperty'].map(k=>[k,s[k]]))}};
      const nodes=[...document.querySelectorAll('#tools,.nav-layer,[data-set-mode]')].slice(0,100).map(styleOf);
      const media=[...document.querySelectorAll('media-item')].map(n=>{const b=n.getBoundingClientRect();return {node:n,b}}).filter((x,i)=>i<12||x.b.y<innerHeight&&x.b.y+x.b.height>0).map(({node:n})=>({...styleOf(n),parents:[n.parentElement,n.parentElement?.parentElement].filter(Boolean).map(styleOf),image:n.shadowRoot?.querySelector('img')?(()=>{const i=n.shadowRoot.querySelector('img');return {...styleOf(i),src:i.currentSrc||i.src,complete:i.complete,naturalWidth:i.naturalWidth,naturalHeight:i.naturalHeight}})():null}));
      return {scrollX,scrollY,dpr:devicePixelRatio,innerWidth,innerHeight,rootAttrs:Object.fromEntries([...document.documentElement.attributes].map(x=>[x.name,x.value])),bodyAttrs:Object.fromEntries([...document.body.attributes].map(x=>[x.name,x.value])),fontStatus:document.fonts.status,fonts:[...document.fonts].map(f=>({family:f.family,status:f.status})),bundle:window.__afsCustomHtmlV1?Object.fromEntries(['version','sha256','state','t0','t1','ready','error'].filter(k=>window.__afsCustomHtmlV1[k]!==undefined).map(k=>[k,window.__afsCustomHtmlV1[k]])):null,nodes,media};
    })}
    paintDiagnostics={afterOriginalCapture:await paintState()};
    if(paintDiagnostic){
    paintDiagnostics.settle=await page.evaluate(async()=>{
      const fonts=await Promise.race([document.fonts.ready.then(()=>true),new Promise(r=>setTimeout(()=>r(false),3000))]);
      const raf=await Promise.race([new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(true)))),new Promise(r=>setTimeout(()=>r(false),3000))]);
      return {fonts,raf};
    });
    await page.screenshot({path:path.join(out,`${name}-${variant}-top-settled-allow.png`),animations:'allow',timeout:60000});
    paintDiagnostics.afterSettledAllow=await paintState();
    await page.screenshot({path:path.join(out,`${name}-${variant}-top-settled-disabled.png`),animations:'disabled',timeout:60000});
    paintDiagnostics.afterSettledDisabled=await paintState();
    }
    fs.writeFileSync(path.join(out,`${name}-${variant}-paint.json`),JSON.stringify(paintDiagnostics,null,2));
  }

  await page.evaluate(()=>{window.__afsMutationCensus.callbacks=0;window.__afsMutationCensus.attributeRecords=0;window.__afsMutationCensus.totalRecords=0});
  await page.evaluate(()=>scrollTo({top:Math.round((document.scrollingElement.scrollHeight-innerHeight)*0.55),behavior:'instant'}));
  await page.waitForTimeout(6000);
  const after=await page.evaluate(()=>({mode:document.documentElement.dataset.mode,scrollY,scrollHeight:document.scrollingElement.scrollHeight,navLayers:document.querySelectorAll('.nav-layer').length,mediaItems:document.querySelectorAll('media-item').length,htmlTone:document.documentElement.getAttribute('data-nav-tone'),mutationCensus:{...window.__afsMutationCensus}}));
  await page.screenshot({path:path.join(out,`${name}-${variant}-mid.png`),animations:'allow',timeout:60000}).catch(e=>errors.push('screenshot: '+String(e).slice(0,200)));
  const images=[...requests.values()].filter(x=>/freight\.cargo\.site\/.*\.(gif|png|jpe?g|webp|avif|svg)(\?|$)/i.test(x.url));
  const network={imageRequests:images.length,imageBytes:images.reduce((n,x)=>n+(x.bytes||0),0),w300h300:images.filter(x=>/\/w\/300\/h\/300\//.test(x.url)).length,failedImages:images.filter(x=>x.failed).length,images:images.map(x=>({url:x.url.replace('https://freight.cargo.site',''),bytes:x.bytes||0,status:x.status,failed:x.failed}))};
  const row={name,form,route,variant,documentPin,documentFieldSha,frontendBuild,navigation,bundleLoaded,runtimeLoaded,before,after,network,errors,failed};
  if(variant==='A'&&!gifProof){
    // Source-identity probes happen after the measured screenshot/network/scroll
    // snapshots. They are not added to any byte-delta or work-count scenario.
    const initial=await Promise.all(gifReplies);
    const denied=initial.filter(x=>[401,403,429].includes(x.status));
    const missing=[...gifUrls].filter(url=>!initial.some(x=>x.url===url));
    let probes=[];
    if(!denied.length&&missing.length)probes=await page.evaluate(async urls=>Promise.all(urls.map(url=>new Promise(resolve=>{const image=new Image;let done=false;const end=state=>{if(done)return;done=true;resolve({url,state})};image.onload=()=>end('loaded');image.onerror=()=>end('error');image.src=url;setTimeout(()=>end('timeout'),15000)}))),missing);
    const responses=await Promise.all(gifReplies);
    const assets=Object.entries(gifMap).map(([hash,item])=>{const a=responses.find(x=>x.url===item.thumbnailUrl&&x.status===200&&!x.error),b=responses.find(x=>x.url===item.canonicalUrl&&x.status===200&&!x.error);return {hash,...item,thumbnail:a,canonical:b,exactBodyIdentity:!!a&&!!b&&a.sha256===b.sha256&&a.sha256===item.originalSha256&&a.bytes===item.originalBytes&&b.bytes===item.originalBytes&&a.header.startsWith('GIF')&&b.header.startsWith('GIF')}});
    gifProof={sourceHomePin:documentPin,sourceFieldSha:documentFieldSha,cargoFrontend:frontendBuild,scope:'Outside measured window; normal browser GIF responses, no denial retry; current transform/source byte identity',accepted:assets.length===9&&assets.every(x=>x.exactBodyIdentity)&&!denied.length,assets,denied,probes,responses};
    fs.writeFileSync(path.join(out,'gif-transform-identity.json'),JSON.stringify(gifProof,null,2));
  }
  await ctx.close();
  return row;
}

try{
  outer: for(const [name,form,route] of cases){
    const variants=syncMatrix?['A','F','D','R','G']:noopMatrix?['A','E','F','D','L','C','B']:runtimeMatrix?(paintDiagnostic?['A','C','B']:['A','C','B','A2','C2','B2']):['A','B',...(['desktop-home','desktop-html'].includes(name)?['A2']:[])];
    for(const variant of variants){
      if((variant==='B'||variant==='B2')&&!runtimeB){rows.push({name,form,route,variant,error:'skipped: source runtime did not match pin'});break outer}
      try{const row=await visit(name,form,route,variant);rows.push(row);console.log(JSON.stringify({name,variant,mode:row.before.mode,guardMarker:row.before.guardMarker,bundle:row.bundleLoaded,runtime:row.runtimeLoaded,mutations:row.after.mutationCensus,images:row.network.imageRequests,imageBytes:row.network.imageBytes,w300h300:row.network.w300h300,errors:row.errors.length,failed:row.failed.length}))}
      catch(e){rows.push({name,form,route,variant,error:String(e)});console.error(JSON.stringify({name,variant,error:String(e)}))}
      fs.writeFileSync(path.join(out,'rows.json'),JSON.stringify(rows,null,2));
    }
  }
}finally{await browser.close()}
const pairs=cases.map(([name])=>({name,A:rows.find(r=>r.name===name&&r.variant==='A'),B:rows.find(r=>r.name===name&&r.variant===(syncMatrix?'R':'B'))}));
const failures=[];
for(const p of pairs){
  if(!p.A||!p.B||p.A.error||p.B.error){failures.push(`${p.name}: missing or failed case`);continue}
  if(!p.B.bundleLoaded||!p.B.runtimeLoaded)failures.push(`${p.name}: candidate bundle/runtime not active`);
  if(!runtimeMatrix){
    for(const k of ['mode','title','bodyTextSha256','pages','mediaItems','navLayers'])if(p.A.before[k]!==p.B.before[k])failures.push(`${p.name}: ${k} differs`);
    for(const k of ['mode','navLayers','mediaItems','htmlTone'])if(p.A.after[k]!==p.B.after[k])failures.push(`${p.name}: mid ${k} differs`);
  }else{
    const c=rows.find(r=>r.name===p.name&&r.variant===(syncMatrix?'G':'C'));
    if(!c||c.error||!c.bundleLoaded)failures.push(`${p.name}: guard-only control did not load`);
  }
  const extra=p.B.errors.filter(x=>!p.A.errors.includes(x));if(extra.length)failures.push(`${p.name}: candidate-only page errors ${extra.length}`);
}
const summary={matrix:syncMatrix?'synchronous':runtimeMatrix?'runtime':'parity',cases:cases.length,rows:rows.length,runtimeA:runtimeA&&{bytes:runtimeA.length,sha256:sha(runtimeA)},runtimeB:runtimeB&&{bytes:runtimeB.length,sha256:sha(runtimeB)},failures,pairedMutations:cases.map(([name])=>({name,...Object.fromEntries((runtimeMatrix?['A','C','B','A2','C2','B2']:['A','B','A2']).map(v=>[v,rows.find(r=>r.name===name&&r.variant===v)?.after?.mutationCensus]))})),controls:['desktop-home','desktop-html'].map(name=>({name,A:rows.find(r=>r.name===name&&r.variant==='A')?.before,A2:rows.find(r=>r.name===name&&r.variant==='A2')?.before,B:rows.find(r=>r.name===name&&r.variant==='B')?.before}))};
fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify(summary,null,2));
console.log(JSON.stringify(summary));
if(failures.length||rows.length!==(syncMatrix?cases.length*5:noopMatrix?7:runtimeMatrix?cases.length*(paintDiagnostic?3:6):cases.length*2+2))process.exitCode=1;
