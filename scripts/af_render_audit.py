#!/usr/bin/env python3
"""Render-path audit for arthurfouray.systems.

Collects the evidence needed to decide how the site can paint faster through
code changes alone, without re-encoding or downsizing any image asset.
Reads a Lighthouse JSON report plus the raw HTML of each audited page and
prints a compact, log-readable summary.
"""
from __future__ import annotations
import json, os, re, sys, urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path(os.environ.get('OUTPUT_DIR', 'af_render_audit')).resolve()
OUT.mkdir(parents=True, exist_ok=True)


def rule(title: str) -> None:
    print('\n' + '=' * 78)
    print(title)
    print('=' * 78)


def kb(n) -> str:
    try:
        return f'{float(n)/1024:.1f} KiB'
    except (TypeError, ValueError):
        return 'n/a'


def ms(n) -> str:
    try:
        return f'{float(n):.0f} ms'
    except (TypeError, ValueError):
        return 'n/a'


# --------------------------------------------------------------------------
# Raw markup analysis
# --------------------------------------------------------------------------
TAG = re.compile(r'<(img|script|link|style|iframe|video|source)\b([^>]*)>', re.I | re.S)
ATTR = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"|([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*\'([^\']*)\'|([a-zA-Z_:][-a-zA-Z0-9_:.]*)', re.S)


def attrs(blob: str) -> dict:
    out = {}
    for m in ATTR.finditer(blob):
        if m.group(1):
            out[m.group(1).lower()] = m.group(2)
        elif m.group(3):
            out[m.group(3).lower()] = m.group(4)
        elif m.group(5):
            out[m.group(5).lower()] = ''
    return out


def analyse_markup(url: str, html: str) -> dict:
    head = html[:html.lower().find('</head>')] if '</head>' in html.lower() else html
    tags = [(m.group(1).lower(), attrs(m.group(2))) for m in TAG.finditer(html)]

    imgs = [a for t, a in tags if t == 'img']
    scripts = [a for t, a in tags if t == 'script']
    links = [a for t, a in tags if t == 'link']

    rels = defaultdict(list)
    for a in links:
        for r in a.get('rel', '').lower().split():
            rels[r].append(a.get('href', ''))

    blocking_css = [h for h in rels.get('stylesheet', []) if h]
    blocking_js = [a.get('src', '') for a in scripts
                   if a.get('src') and 'async' not in a and 'defer' not in a
                   and a.get('type', '').lower() not in ('module',)]
    module_js = [a.get('src', '') for a in scripts
                 if a.get('src') and a.get('type', '').lower() == 'module']
    inline_js_bytes = 0
    for m in re.finditer(r'<script\b([^>]*)>(.*?)</script>', html, re.I | re.S):
        if 'src=' not in m.group(1).lower():
            inline_js_bytes += len(m.group(2).encode('utf-8'))
    inline_css_bytes = sum(len(m.group(1).encode('utf-8'))
                           for m in re.finditer(r'<style\b[^>]*>(.*?)</style>', html, re.I | re.S))

    origins = Counter()
    for t, a in tags:
        for key in ('src', 'href'):
            v = a.get(key, '')
            if v.startswith('//'):
                v = 'https:' + v
            if v.startswith('http'):
                net = urllib.parse.urlparse(v).netloc
                if net:
                    origins[net] += 1

    def count(pred):
        return sum(1 for a in imgs if pred(a))

    info = {
        'url': url,
        'html_bytes': len(html.encode('utf-8')),
        'head_bytes': len(head.encode('utf-8')),
        'img_total': len(imgs),
        'img_lazy': count(lambda a: a.get('loading', '').lower() == 'lazy'),
        'img_eager': count(lambda a: a.get('loading', '').lower() == 'eager'),
        'img_no_loading_attr': count(lambda a: 'loading' not in a),
        'img_decoding_async': count(lambda a: a.get('decoding', '').lower() == 'async'),
        'img_fetchpriority': count(lambda a: 'fetchpriority' in a),
        'img_with_dimensions': count(lambda a: 'width' in a and 'height' in a),
        'img_with_srcset': count(lambda a: 'srcset' in a),
        'img_with_sizes': count(lambda a: 'sizes' in a),
        'img_data_src_only': count(lambda a: 'src' not in a and any(k.startswith('data-') for k in a)),
        'script_total': len(scripts),
        'script_external': len([a for a in scripts if a.get('src')]),
        'script_render_blocking': blocking_js,
        'script_module': module_js,
        'inline_js_bytes': inline_js_bytes,
        'inline_css_bytes': inline_css_bytes,
        'stylesheets_blocking': blocking_css,
        'preload': rels.get('preload', []),
        'preconnect': rels.get('preconnect', []),
        'dns_prefetch': rels.get('dns-prefetch', []),
        'prefetch': rels.get('prefetch', []),
        'origins': origins.most_common(15),
        'has_content_visibility': 'content-visibility' in html.lower(),
        'has_font_display': 'font-display' in html.lower(),
        'font_face_blocks': len(re.findall(r'@font-face', html, re.I)),
        'picture_elements': len(re.findall(r'<picture\b', html, re.I)),
        'noscript_blocks': len(re.findall(r'<noscript\b', html, re.I)),
    }
    return info


def print_markup(info: dict) -> None:
    rule(f'MARKUP  {info["url"]}')
    print(f'  HTML document          : {kb(info["html_bytes"])}  (head {kb(info["head_bytes"])})')
    print(f'  <img> in initial HTML  : {info["img_total"]}')
    if info['img_total']:
        print(f'    loading="lazy"       : {info["img_lazy"]}')
        print(f'    loading="eager"      : {info["img_eager"]}')
        print(f'    no loading attribute : {info["img_no_loading_attr"]}')
        print(f'    decoding="async"     : {info["img_decoding_async"]}')
        print(f'    fetchpriority set    : {info["img_fetchpriority"]}')
        print(f'    width+height set     : {info["img_with_dimensions"]}')
        print(f'    srcset / sizes       : {info["img_with_srcset"]} / {info["img_with_sizes"]}')
        print(f'    JS-deferred (data-*) : {info["img_data_src_only"]}')
    print(f'  <picture> elements     : {info["picture_elements"]}')
    print(f'  <noscript> blocks      : {info["noscript_blocks"]}')
    print(f'  Scripts total/external : {info["script_total"]} / {info["script_external"]}')
    print(f'  Render-blocking JS     : {len(info["script_render_blocking"])}')
    for s in info['script_render_blocking'][:12]:
        print(f'      - {s[:110]}')
    print(f'  Module scripts         : {len(info["script_module"])}')
    print(f'  Blocking stylesheets   : {len(info["stylesheets_blocking"])}')
    for s in info['stylesheets_blocking'][:12]:
        print(f'      - {s[:110]}')
    print(f'  Inline JS / inline CSS : {kb(info["inline_js_bytes"])} / {kb(info["inline_css_bytes"])}')
    print(f'  @font-face blocks      : {info["font_face_blocks"]}   font-display present: {info["has_font_display"]}')
    print(f'  content-visibility used: {info["has_content_visibility"]}')
    print(f'  preload                : {info["preload"][:8] or "NONE"}')
    print(f'  preconnect             : {info["preconnect"] or "NONE"}')
    print(f'  dns-prefetch           : {info["dns_prefetch"] or "NONE"}')
    print('  Referenced origins     :')
    for host, n in info['origins']:
        print(f'      {n:>4}x  {host}')


# --------------------------------------------------------------------------
# Lighthouse report analysis
# --------------------------------------------------------------------------
def print_lighthouse(path: Path) -> None:
    try:
        lr = json.loads(path.read_text())
    except Exception as e:
        print(f'  ! could not read {path}: {e}')
        return
    if 'lighthouseResult' in lr:
        lr = lr['lighthouseResult']
    audits = lr.get('audits', {})
    rule(f'LIGHTHOUSE  {lr.get("finalDisplayedUrl") or lr.get("finalUrl")}  '
         f'[{lr.get("configSettings", {}).get("formFactor", "?")}]')
    score = lr.get('categories', {}).get('performance', {}).get('score')
    print(f'  Performance score      : {round(score*100) if score is not None else "n/a"}')
    for key, label in [
        ('first-contentful-paint', 'First Contentful Paint'),
        ('largest-contentful-paint', 'Largest Contentful Paint'),
        ('speed-index', 'Speed Index'),
        ('total-blocking-time', 'Total Blocking Time'),
        ('cumulative-layout-shift', 'Cumulative Layout Shift'),
        ('interactive', 'Time to Interactive'),
        ('server-response-time', 'Server response time'),
    ]:
        a = audits.get(key, {})
        print(f'  {label:<23}: {a.get("displayValue", "n/a")}')

    # Byte weight by resource type
    rs = audits.get('resource-summary', {}).get('details', {}).get('items', [])
    if rs:
        print('\n  Transfer by resource type (requests / bytes):')
        for it in rs:
            print(f'      {it.get("label", it.get("resourceType","?")):<16} '
                  f'{it.get("requestCount", 0):>4}  {kb(it.get("transferSize", 0))}')

    # Opportunities and diagnostics that matter for a code-only fix
    interesting = [
        'render-blocking-resources', 'unused-css-rules', 'unused-javascript',
        'unminified-css', 'unminified-javascript', 'uses-text-compression',
        'uses-long-cache-ttl', 'uses-rel-preconnect', 'uses-rel-preload',
        'font-display', 'critical-request-chains', 'dom-size',
        'offscreen-images', 'lcp-lazy-loaded', 'prioritize-lcp-image',
        'unsized-images', 'layout-shift-elements', 'third-party-summary',
        'bootup-time', 'mainthread-work-breakdown', 'duplicated-javascript',
        'legacy-javascript', 'redirects', 'uses-passive-event-listeners',
        'non-composited-animations', 'total-byte-weight', 'network-server-latency',
    ]
    print('\n  Audit findings relevant to a code-only fix:')
    for key in interesting:
        a = audits.get(key)
        if not a:
            continue
        sc = a.get('score')
        dv = a.get('displayValue', '')
        overall = a.get('details', {}).get('overallSavingsMs')
        flag = 'OK  ' if sc == 1 else ('FAIL' if sc is not None and sc < 0.9 else 'INFO')
        extra = f'  (est. saving {ms(overall)})' if overall else ''
        print(f'      [{flag}] {a.get("title", key)[:62]:<62} {dv}{extra}')

    # LCP element
    lcp_el = audits.get('largest-contentful-paint-element', {}).get('details', {}).get('items', [])
    if lcp_el:
        print('\n  LCP element:')
        for it in lcp_el:
            for sub in it.get('items', [it]):
                node = sub.get('node', {})
                if node:
                    print(f'      selector : {node.get("selector","")[:100]}')
                    print(f'      snippet  : {node.get("snippet","")[:160]}')
                for ph in (sub.get('items') or []):
                    if 'phase' in ph:
                        print(f'      {ph["phase"]:<22} {ms(ph.get("timing"))}  {kb(ph.get("percent"))if False else ""}')

    # Render blocking detail
    rb = audits.get('render-blocking-resources', {}).get('details', {}).get('items', [])
    if rb:
        print('\n  Render-blocking resources:')
        for it in rb:
            print(f'      {ms(it.get("wastedMs"))}  {kb(it.get("totalBytes"))}  {str(it.get("url",""))[:96]}')

    # Critical chain depth
    cc = audits.get('critical-request-chains', {}).get('displayValue')
    if cc:
        print(f'\n  Critical request chains: {cc}')

    # Third parties
    tp = audits.get('third-party-summary', {}).get('details', {}).get('items', [])
    if tp:
        print('\n  Third-party cost:')
        for it in tp[:10]:
            ent = it.get('entity')
            name = ent.get('text') if isinstance(ent, dict) else ent
            print(f'      {str(name)[:34]:<34} blocking {ms(it.get("blockingTime"))}  '
                  f'transfer {kb(it.get("transferSize"))}')

    # Network requests: image + font + cache posture
    nr = audits.get('network-requests', {}).get('details', {}).get('items', [])
    if nr:
        by_type = Counter()
        bytes_by_type = Counter()
        img_mimes = Counter()
        for it in nr:
            rt = it.get('resourceType') or 'Other'
            by_type[rt] += 1
            bytes_by_type[rt] += it.get('transferSize') or 0
            if rt == 'Image':
                img_mimes[it.get('mimeType', '?')] += 1
        print('\n  Network requests by type:')
        for rt, n in by_type.most_common():
            print(f'      {rt:<14} {n:>4} requests  {kb(bytes_by_type[rt])}')
        if img_mimes:
            print('  Image formats actually served:')
            for mt, n in img_mimes.most_common():
                print(f'      {mt:<24} {n}')
        imgs = sorted([i for i in nr if i.get('resourceType') == 'Image'],
                      key=lambda i: -(i.get('transferSize') or 0))[:15]
        if imgs:
            print('  Heaviest image responses (NOT to be re-encoded; listed for '
                  'priority/lazy decisions):')
            for i in imgs:
                print(f'      {kb(i.get("transferSize")):>11}  '
                      f'start {ms(i.get("networkRequestTime")):>9}  '
                      f'{str(i.get("url","")).split("/")[-1][:64]}')
    print()


def main() -> int:
    pages = json.loads(os.environ.get('PAGES_JSON', '[]'))
    rule('AUDIT SCOPE')
    for p in pages:
        print(f'  {p}')

    summary = []
    for idx, url in enumerate(pages):
        html_path = OUT / f'page_{idx:02d}.html'
        if html_path.exists():
            html = html_path.read_text(errors='replace')
            info = analyse_markup(url, html)
            print_markup(info)
            summary.append(info)

    (OUT / 'markup_summary.json').write_text(json.dumps(summary, indent=2))

    for lh in sorted(OUT.glob('lighthouse_*.json')):
        print_lighthouse(lh)

    hdr = OUT / 'headers.txt'
    if hdr.exists():
        rule('RESPONSE HEADERS (compression, caching, image formats)')
        print(hdr.read_text()[:20000])
    return 0


if __name__ == '__main__':
    sys.exit(main())
