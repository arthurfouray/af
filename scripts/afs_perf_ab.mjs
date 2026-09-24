// Lighthouse 12 A/B for arthurfouray.systems: A = the published site, B = the same
// site with the afs-img-dedupe guard installed before any page script
// (Page.addScriptToEvaluateOnNewDocument; the proposed custom_html places it
// ahead of every other custom_html script and of Cargo's module, so the effect is
// the same). Chrome flags match the PR #13 / #14 runner. Variants alternate
// (A B A B ...) so network and CDN drift hit both equally.
//
// usage: node afs_perf_ab.mjs OUTDIR [runs=5] [url=https://arthurfouray.systems/]
import fs from "node:fs";
import path from "node:path";
import lighthouse from "lighthouse";
import desktopConfig from "lighthouse/core/config/desktop-config.js";
import * as chromeLauncher from "chrome-launcher";
import puppeteer from "puppeteer-core";

const [outdir, runsArg, urlArg] = process.argv.slice(2);
const RUNS = +(runsArg || 5);
const URL_ = urlArg || "https://arthurfouray.systems/";
const GUARD = fs.readFileSync(new URL("./afs-img-dedupe.min.js", import.meta.url), "utf8");
const FLAGS = ["--headless=new", "--no-sandbox", "--disable-dev-shm-usage"];
fs.mkdirSync(outdir, { recursive: true });

const IMG = /freight\.cargo\.site\/.*\.(gif|png|jpe?g|webp|avif|svg)(\?|$)/i;
function imageStats(lhr) {
  const items = (lhr.audits["network-requests"]?.details?.items || []).filter(r => IMG.test(r.url));
  const byHash = {};
  for (const r of items) {
    const m = /\/i\/([^/]+)\//.exec(r.url) || /\/m\/([^/]+)\//.exec(r.url);
    (byHash[m ? m[1] : r.url] ||= []).push(r.transferSize || 0);
  }
  const groups = Object.values(byHash);
  const bytes = items.reduce((a, r) => a + (r.transferSize || 0), 0);
  const once = groups.reduce((a, v) => a + Math.min(...v), 0);
  return {
    imgRequests: items.length, uniqueImages: groups.length, imgBytes: bytes, dupWaste: bytes - once,
    w300h300: items.filter(r => /\/w\/300\/h\/300\//.test(r.url)).length,
    requests: items.map(r => [r.url.replace("https://freight.cargo.site", ""), r.transferSize || 0]),
  };
}

async function once(variant, form, i) {
  const chrome = await chromeLauncher.launch({ chromeFlags: FLAGS });
  try {
    const browser = await puppeteer.connect({ browserURL: `http://127.0.0.1:${chrome.port}`, defaultViewport: null });
    const page = await browser.newPage();
    if (variant === "B") await page.evaluateOnNewDocument(GUARD);
    const flags = { port: chrome.port, output: "json", logLevel: "error", onlyCategories: ["performance"], maxWaitForLoad: 60000 };
    const res = await lighthouse(URL_, flags, form === "desktop" ? desktopConfig : undefined, page);
    const lhr = res.lhr;
    const tag = `${form}-${variant}-${i}`;
    fs.writeFileSync(path.join(outdir, `lh-${tag}.json`), res.report);
    const a = lhr.audits;
    const row = {
      tag, form, variant, run: i, score: Math.round((lhr.categories.performance.score ?? NaN) * 100),
      fcp: a["first-contentful-paint"].numericValue, lcp: a["largest-contentful-paint"].numericValue,
      tbt: a["total-blocking-time"].numericValue, cls: a["cumulative-layout-shift"].numericValue,
      si: a["speed-index"].numericValue, mainThread: a["mainthread-work-breakdown"]?.numericValue,
      bootup: a["bootup-time"]?.numericValue, totalBytes: a["total-byte-weight"].numericValue,
      runtimeError: lhr.runtimeError?.code || null, benchmarkIndex: lhr.environment?.benchmarkIndex,
      lighthouse: lhr.lighthouseVersion, userAgent: lhr.environment?.hostUserAgent,
      ...imageStats(lhr),
    };
    await browser.disconnect();
    return row;
  } finally {
    await chrome.kill();
  }
}

const rows = [];
for (let i = 1; i <= RUNS; i++)
  for (const form of ["mobile", "desktop"])
    for (const variant of i % 2 ? ["A", "B"] : ["B", "A"]) {
      try {
        const r = await once(variant, form, i);
        const { requests, ...short } = r;
        console.log(JSON.stringify(short));
        rows.push(r);
      } catch (e) {
        console.log(JSON.stringify({ tag: `${form}-${variant}-${i}`, error: String(e).slice(0, 300) }));
        rows.push({ tag: `${form}-${variant}-${i}`, form, variant, run: i, error: String(e).slice(0, 300) });
      }
    }
fs.writeFileSync(path.join(outdir, "rows.json"), JSON.stringify(rows, null, 1));

const med = xs => { const s = xs.filter(Number.isFinite).sort((a, b) => a - b); return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : null; };
const keys = ["score", "fcp", "lcp", "tbt", "cls", "si", "mainThread", "bootup", "totalBytes", "imgRequests", "imgBytes", "dupWaste", "w300h300"];
const summary = {};
for (const form of ["mobile", "desktop"])
  for (const variant of ["A", "B"]) {
    const rs = rows.filter(r => r.form === form && r.variant === variant && !r.error && !r.runtimeError);
    summary[`${form}-${variant}`] = { n: rs.length, ...Object.fromEntries(keys.map(k => [k, med(rs.map(r => r[k]))])) };
  }
fs.writeFileSync(path.join(outdir, "summary.json"), JSON.stringify(summary, null, 1));
console.table(summary);
