// A/B for moving the arthurfouray.systems Custom HTML into one Freight file (read-only, nothing uploaded).
//   A     the published homepage, untouched.
//   B0    the same response routed through Playwright and served unchanged (control: routing disables
//         the HTTP cache and can reorder late requests, so B is compared with B0 as well as with A).
//   B@ms  the Custom HTML replaced by the stub, in <customhtml> and in __PRELOADED_STATE__.custom_html
//         (Cargo escapes it as JSON with < written <). The bundle is served from its would-be
//         Freight URL after `ms` of delay, with CORS and the SRI the stub pins.
//   B404  (systems only) the bundle request fails: what a visitor sees if Freight does not answer.
// Then A, B0 and B@0 on direct loads of other routes (ROUTES) and after an in-site navigation from the
// homepage (NAV: click the link, Cargo's router swaps the page without reloading), in systems and html.
// usage: BUILD=DIR node run.cjs chromium|webkit desktop|mobile OUTDIR
//   DIR holds live-custom-html.html (the <customhtml> body of the page as served now) and what
//   externalize.py built from it: Custom-HTML.stub.html and afs-custom-html.<sha16>.js.
// env: MODES (default systems,clean,clean-dark,html,img,card), DELAYS (0,300,1500), SETTLE_MS (10000),
//      REPS (4: timing repetitions of B0 and B@0 in systems and html), ROUTES (before-arts,curriculum-vitae,chronology),
//      NAV (before-arts: the homepage link to click; empty to skip)
const pw = require('playwright');
const fs = require('fs'), path = require('path'), zlib = require('zlib'), crypto = require('crypto');
const { PNG } = require('pngjs');
const pixelmatch = require('pixelmatch');
const [browserName, profile, outdir] = process.argv.slice(2);
const here = process.env.BUILD || __dirname;
const liveCh = fs.readFileSync(path.join(here, 'live-custom-html.html'), 'utf8');
const stub = fs.readFileSync(path.join(here, 'Custom-HTML.stub.html'), 'utf8');
const bundleName = fs.readdirSync(here).find(f => /^afs-custom-html\.[0-9a-f]{16}\.js$/.test(f));
const bundle = fs.readFileSync(path.join(here, bundleName));
const bundleUrl = /id="afs-custom-html-bundle" src="([^"]+)"/.exec(stub)[1];
const esc = s => JSON.stringify(s).slice(1, -1).replace(/</g, '\\u003c');
const liveEsc = esc(liveCh), stubEsc = esc(stub);
const count = (h, n) => h.split(n).length - 1;
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const MODES = (process.env.MODES || 'systems,clean,clean-dark,html,img,card').split(',');
const DELAYS = (process.env.DELAYS || '0,300,1500').split(',').map(Number);
const SETTLE = +(process.env.SETTLE_MS || 10000), REPS = +(process.env.REPS || 4);
const ROUTES = (process.env.ROUTES ?? 'before-arts,curriculum-vitae,chronology').split(',').filter(Boolean);
const NAV = process.env.NAV ?? 'before-arts';
const IDS7 = ['afs-mode-root-initializer', 'afs-mode-css-controller-loader', 'afs-runtime-loader', 'afs-heavy-page-loader',
  'afs-persisted-mode-replay', 'afs-html-footer-index', 'afs-section-menu-js'];
const UA = { chromium: 'Mozilla/5.0 (Linux; Android 11; moto g power (2022)) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36',
  webkit: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1' };
const profiles = { desktop: { viewport: { width: 1350, height: 940 }, deviceScaleFactor: 1 },
  mobile: { viewport: { width: 412, height: 823 }, deviceScaleFactor: 1.75, isMobile: true, hasTouch: true, userAgent: UA[browserName] } };

// Timing marks, installed before any page script: first time each root attribute value appears,
// body opacity cleared, first paint entries.
const MARKS = () => {
  const m = window.__afsAB = { attrs: {}, bodyVisible: null };
  const root = document.documentElement;
  const log = () => { for (const a of ['data-afs-mode', 'data-afs-css-state', 'data-afs-html-v1-preparse', 'data-afs-tk']) {
    const v = root.getAttribute(a), k = a + '=' + v; if (v !== null && !(k in m.attrs)) m.attrs[k] = Math.round(performance.now()); } };
  new MutationObserver(log).observe(root, { attributes: true }); log();
  // Cargo serves <body style="opacity: 0;"> and clears it once its module has booted.
  const tick = () => { const b = document.body; if (b && b.style.opacity !== '0') { m.bodyVisible = Math.round(performance.now()); return; } requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
};

const STATE = IDS7 => {
  const root = document.documentElement, ch = document.querySelector('customhtml');
  const sid = [...document.querySelectorAll('script[id]')].map(s => s.id);
  const dup = [...new Set(sid.filter((x, i) => sid.indexOf(x) !== i))];
  const tags = {}; for (const e of document.body ? document.body.querySelectorAll('*') : []) tags[e.localName] = (tags[e.localName] || 0) + 1;
  const api = globalThis.__afsCustomHtmlV1;
  const nav = performance.getEntriesByType('navigation')[0] || {};
  const paint = Object.fromEntries(performance.getEntriesByType('paint').map(p => [p.name, Math.round(p.startTime)]));
  return {
    data: { ...root.dataset }, bodyClass: document.body && document.body.className,
    ids7: Object.fromEntries(IDS7.map(id => [id, document.querySelectorAll(`script[id="${id}"]`).length])),
    duplicateScriptIds: dup,
    order: ch ? [...ch.children].map(e => e.localName + (e.id ? '#' + e.id : '')) : null,
    jsonld: document.querySelectorAll('script[type="application/ld+json"]').length,
    sheets: [...document.querySelectorAll('link[rel=stylesheet]')].map(l => (l.href || '').split('/').pop()),
    styleIds: [...document.querySelectorAll('style[id]')].map(s => s.id),
    tags, nodes: document.querySelectorAll('*').length,
    text: document.body ? document.body.innerText : '',
    api: api ? { anchored: api.anchored, patch: api.patch || null, stoppedAfter: api.stoppedAfter || null, restored: api.restored || 0,
      ms: Math.round(api.t1 - api.t0), at: Math.round(api.t0) } : null,
    marks: window.__afsAB || null, paint,
    nav: { dcl: Math.round(nav.domContentLoadedEventEnd || 0), load: Math.round(nav.loadEventEnd || 0) },
  };
};

async function run(browser, mode, variant, delay, group, opts = {}) {
  const tag = `${group}-${variant}${variant === 'B' ? '@' + delay : ''}${opts.rep === undefined ? '' : '-' + opts.rep}`;
  const dir = path.join(outdir, tag); fs.mkdirSync(dir, { recursive: true });
  const ctx = await browser.newContext({ ...profiles[profile], colorScheme: 'light' });
  if (mode === 'clean-dark') await ctx.addInitScript(() => { try { localStorage.setItem('afs-clean-theme-v1', 'dark'); } catch {} });
  await ctx.addInitScript(MARKS);
  const rec = { browser: browserName, profile, mode, variant, delay, group, tag, route: opts.route || "", navTo: opts.nav || null,
    html: [], bundleRequests: 0, routeError: null };
  if (variant !== 'A') {
    await ctx.route(/^https:\/\/arthurfouray\.systems\/[a-z0-9-]*(\?.*)?$/, async route => {
      let r, lastErr;
      for (let i = 0; i < 4 && !r; i++) r = await route.fetch().catch(e => { lastErr = e; return null; });
      if (!r) { rec.routeError = 'route.fetch failed 4x: ' + String(lastErr).slice(0, 120); return route.abort().catch(() => {}); }
      let h = await r.text();
      const n1 = count(h, liveCh), n2 = count(h, liveEsc);
      const before = Buffer.byteLength(h);
      if (n1 !== 1 || n2 !== 1) rec.routeError = `published Custom HTML found ${n1}x in <customhtml> and ${n2}x in the state; the site changed since the build`;
      else if (variant !== 'B0') h = h.replace(liveCh, () => stub).replace(liveEsc, () => stubEsc);
      const b = Buffer.from(h);
      rec.html.push({ url: route.request().url(), before, after: b.length,
        gzip6: zlib.gzipSync(b, { level: 6 }).length, br5: zlib.brotliCompressSync(b, { params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 5 } }).length });
      const headers = { ...r.headers() }; delete headers['content-encoding']; delete headers['content-length'];
      await route.fulfill({ status: r.status(), headers, body: b });
    });
    await ctx.route(u => u.href === bundleUrl, async route => {
      rec.bundleRequests++;
      if (variant === 'B404') return route.fulfill({ status: 404, body: 'not found', headers: { 'access-control-allow-origin': '*' } });
      if (delay) await new Promise(r => setTimeout(r, delay));
      await route.fulfill({ status: 200, body: bundle, headers: { 'content-type': 'text/javascript; charset=utf-8',
        'access-control-allow-origin': '*', 'cache-control': 'max-age=31536000, immutable' } });
    });
  }
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text().slice(0, 300)); });
  page.on('pageerror', e => errors.push('pageerror ' + String(e).slice(0, 300)));
  page.on('requestfailed', q => { const f = q.failure() && q.failure().errorText || ''; if (!/aborted|cancel/i.test(f)) errors.push(`requestfailed ${f} ${q.url().slice(0, 160)}`); });
  const m = mode === 'clean-dark' ? 'clean' : mode;
  const url = 'https://arthurfouray.systems/' + (opts.route || '') + (m === 'systems' ? '' : '?mode=' + m);
  const t = Date.now();
  await page.goto(url, { waitUntil: 'load', timeout: 120000 }).catch(e => errors.push('goto ' + e.message));
  rec.loadWallMs = Date.now() - t;
  await page.waitForTimeout(SETTLE);
  if (opts.nav) {
    const ok = await page.evaluate(h => { const a = document.querySelector(`a[href="${h}"]`); if (!a) return false; a.click(); return true; }, opts.nav)
      .catch(e => { errors.push('nav ' + e.message); return false; });
    if (!ok) errors.push(`nav: no a[href="${opts.nav}"]`);
    else await page.waitForFunction(h => location.pathname === '/' + h, opts.nav, { timeout: 30000 }).catch(e => errors.push('nav wait ' + e.message.slice(0, 120)));
    await page.waitForTimeout(SETTLE);
    rec.navPath = await page.evaluate(() => location.pathname).catch(() => null);
  }
  const st = await page.evaluate(STATE, IDS7).catch(e => ({ evalError: String(e) }));
  const text = st.text || ''; delete st.text;
  Object.assign(rec, st, { textSha: sha(text), textLen: text.length, errors });
  await page.screenshot({ path: path.join(dir, 'shot.png') }).catch(e => errors.push('shot ' + e.message));
  fs.writeFileSync(path.join(dir, 'state.json'), JSON.stringify(rec, null, 1));
  await ctx.close();
  console.log(JSON.stringify({ tag, errors: errors.length, mode: rec.data && rec.data.afsMode, css: rec.data && rec.data.afsCssState,
    preparse: rec.data && rec.data.afsHtmlV1Preparse, api: rec.api, routeError: rec.routeError }));
  return rec;
}

function pxdiff(a, b) {
  try {
    const A = PNG.sync.read(fs.readFileSync(a)), B = PNG.sync.read(fs.readFileSync(b));
    if (A.width !== B.width || A.height !== B.height) return null;
    return +(100 * pixelmatch(A.data, B.data, null, A.width, A.height, { threshold: 0.1 }) / (A.width * A.height)).toFixed(3);
  } catch { return null; }
}

(async () => {
  fs.mkdirSync(outdir, { recursive: true });
  const browser = await pw[browserName].launch(browserName === 'chromium' ? { args: ['--autoplay-policy=no-user-gesture-required'] } : {});
  const out = [];
  for (const mode of MODES) {
    const variants = [['A', 0], ['B0', 0], ...DELAYS.map(d => ['B', d]), ...(mode === 'systems' ? [['B404', 0]] : [])];
    for (const [v, d] of variants) out.push(await run(browser, mode, v, d, mode));
  }
  const V3 = [['A', 0], ['B0', 0], ['B', 0]];
  for (const route of ROUTES) for (const mode of ['systems', 'html']) for (const [v, d] of V3)
    out.push(await run(browser, mode, v, d, `route-${route}-${mode}`, { route }));
  if (NAV) for (const mode of ['systems', 'html']) for (const [v, d] of V3)
    out.push(await run(browser, mode, v, d, `nav-${NAV}-${mode}`, { nav: NAV }));
  const timing = [];
  for (const mode of ['systems', 'html']) for (let i = 0; i < REPS; i++) for (const [v, d] of [['B0', 0], ['B', 0]])
    timing.push(await run(browser, mode, v, d, `timing/${mode}`, { rep: i }));
  await browser.close();

  // Compare every run with A and B0 of the same group (mode, route or navigation).
  const rows = [];
  const strip = o => (o || []).filter(x => x !== 'script#afs-custom-html-bundle');
  for (const group of [...new Set(out.map(r => r.group))]) {
    const A = out.find(r => r.group === group && r.variant === 'A');
    for (const r of out.filter(r => r.group === group)) {
      const tag = r.tag;
      const sheetsEq = JSON.stringify(r.sheets) === JSON.stringify(A.sheets);
      const orderEq = JSON.stringify(strip(r.order)) === JSON.stringify(strip(A.order));
      const dataKeys = ['afsMode', 'afsCssState', 'afsManifestSource', 'afsHtmlV1Preparse', 'afsHtmlV1Projected', 'afsTk'];
      const dataDiff = dataKeys.filter(k => (r.data || {})[k] !== (A.data || {})[k]).map(k => `${k}:${(A.data || {})[k]}→${(r.data || {})[k]}`);
      const tagDiff = Object.keys({ ...A.tags, ...r.tags }).filter(k => (A.tags || {})[k] !== (r.tags || {})[k] && k !== 'script')
        .map(k => `${k}:${(A.tags || {})[k] || 0}→${(r.tags || {})[k] || 0}`);
      rows.push({ tag, variant: r.variant, errors: r.errors.length, errorSample: r.errors.slice(0, 3), routeError: r.routeError,
        ids7ok: IDS7.every(id => (r.ids7 || {})[id] === 1), duplicateScriptIds: r.duplicateScriptIds, api: r.api, bundleRequests: r.bundleRequests,
        dataDiff, sheetsEq, orderEq, orderB: r.variant === 'A' ? undefined : (orderEq ? undefined : strip(r.order)), jsonld: r.jsonld,
        textEqA: r.textSha === A.textSha, textLen: r.textLen, tagDiff: tagDiff.slice(0, 12), nodes: r.nodes, nodesA: A.nodes,
        navPath: r.navPath, pxVsA: r.variant === 'A' ? 0 : pxdiff(path.join(outdir, `${group}-A`, 'shot.png'), path.join(outdir, tag, 'shot.png')),
        pxVsB0: r.variant.startsWith('B') && r.variant !== 'B0' ? pxdiff(path.join(outdir, `${group}-B0`, 'shot.png'), path.join(outdir, tag, 'shot.png')) : undefined,
        html: r.html, fcp: r.paint && r.paint['first-contentful-paint'], marks: r.marks, nav: r.nav });
    }
  }
  const med = a => { const s = a.filter(x => typeof x === 'number').sort((x, y) => x - y); return s.length ? s[s.length >> 1] : null; };
  const tsum = [];
  for (const mode of ['systems', 'html']) for (const v of ['B0', 'B']) {
    const rs = timing.filter(r => r.mode === mode && r.variant === v);
    const first = (r, pre) => { const e = Object.entries((r.marks || {}).attrs || {}).find(([k]) => k.startsWith(pre)); return e ? e[1] : null; };
    tsum.push({ mode, variant: v, n: rs.length, errors: rs.reduce((s, r) => s + r.errors.length, 0),
      fcp: med(rs.map(r => r.paint && r.paint['first-contentful-paint'])), bodyVisible: med(rs.map(r => r.marks && r.marks.bodyVisible)),
      modeSet: med(rs.map(r => first(r, 'data-afs-mode='))), cssReady: med(rs.map(r => (r.marks && r.marks.attrs || {})['data-afs-css-state=ready'])),
      preparseReady: med(rs.map(r => (r.marks && r.marks.attrs || {})['data-afs-html-v1-preparse=ready'])),
      dcl: med(rs.map(r => r.nav && r.nav.dcl)), load: med(rs.map(r => r.nav && r.nav.load)), bundleMs: med(rs.map(r => r.api && r.api.ms)),
      htmlAfter: med(rs.map(r => r.html[0] && r.html[0].after)), htmlBr5: med(rs.map(r => r.html[0] && r.html[0].br5)) });
  }
  const summary = { browser: browserName, profile, bundle: { name: bundleName, bytes: bundle.length, url: bundleUrl }, stubBytes: Buffer.byteLength(stub), rows, timing: tsum };
  fs.writeFileSync(path.join(outdir, 'summary.json'), JSON.stringify(summary, null, 1));
  const bad = rows.filter(r => r.variant.startsWith('B') && r.variant !== 'B404' && (r.errors || r.routeError || !r.ids7ok || r.duplicateScriptIds.length || r.dataDiff.length || !r.sheetsEq || !r.orderEq));
  console.log(`rows ${rows.length}, flagged ${bad.length}: ${bad.map(r => r.tag).join(' ')}`);
  console.table(tsum);
})();
