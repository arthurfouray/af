"""Content, SEO and accessibility audit of arthurfouray.systems.

Crawls every page in the sitemap and reports what a visitor, a search engine
and an AI fetcher each get from the raw HTML: titles, descriptions, social
cards, structured data, headings, alt text, readable text, outbound links,
site-level files and security headers. Lighthouse results for accessibility,
SEO and best practices are summarised when present in OUTPUT_DIR.

Standard library only. Read-only: it fetches public pages and prints a report.
"""

import collections
import concurrent.futures
import hashlib
import html.parser
import json
import os
import re
import subprocess
import tempfile
import urllib.parse

SITE = os.environ.get('SITE', 'https://arthurfouray.systems').rstrip('/')
OUT = os.environ.get('OUTPUT_DIR', 'af_content_audit')
UA = os.environ.get('UA', 'Mozilla/5.0 (compatible; af-content-audit)')
HOST = urllib.parse.urlparse(SITE).netloc

os.makedirs(OUT, exist_ok=True)


def fetch(url, follow=True):
    """Return (status, headers_text, body) using curl, like the other runners."""
    with tempfile.NamedTemporaryFile(mode='r', suffix='.hdr') as hdr:
        args = ['curl', '-sS', '--compressed', '--max-time', '60', '-A', UA,
                '-D', hdr.name, '-o', '-']
        if follow:
            args.append('-L')
        r = subprocess.run(args + [url], capture_output=True)
        # With -L every hop writes a header block; keep the final one.
        blocks = [b for b in re.split(r'\r?\n\r?\n', hdr.read()) if b.startswith('HTTP/')]
    headers = blocks[-1] if blocks else ''
    m = re.match(r'HTTP/\S+\s+(\d+)', headers)
    return (int(m.group(1)) if m else 0), headers, r.stdout.decode('utf-8', errors='replace')


def header(headers, name):
    m = re.search(r'^' + re.escape(name) + r':\s*(.*)$', headers, re.I | re.M)
    return m.group(1).strip() if m else None


class Page(html.parser.HTMLParser):
    SKIP = {'script', 'style', 'noscript', 'template', 'svg'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.title = ''
        self.in_title = False
        self.meta = {}
        self.canonical = None
        self.hreflang = []
        self.jsonld = []
        self.in_jsonld = False
        self.jsonld_buf = ''
        self.headings = []
        self.in_heading = None
        self.heading_buf = ''
        self.images = []
        self.links = []
        self.iframes = []
        self.media = []
        self.skip_depth = 0
        self.text = []
        self.inline_scripts = []
        self.inline_styles = []
        self.in_script = False
        self.in_style = False
        self.script_buf = ''
        self.style_buf = ''
        self.forms = 0
        self.icons = []
        self.feeds = []
        self.manifest = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'html':
            self.lang = a.get('lang')
        elif tag == 'title':
            self.in_title = True
        elif tag == 'meta':
            key = (a.get('name') or a.get('property') or '').lower()
            if key and 'content' in a:
                self.meta.setdefault(key, a['content'])
        elif tag == 'link':
            rel = (a.get('rel') or '').lower()
            if 'canonical' in rel:
                self.canonical = a.get('href')
            if 'alternate' in rel and a.get('hreflang'):
                self.hreflang.append(a['hreflang'])
            if 'alternate' in rel and re.search(r'rss|atom', a.get('type') or ''):
                self.feeds.append(a.get('href'))
            if 'icon' in rel:
                self.icons.append(rel)
            if 'manifest' in rel:
                self.manifest = a.get('href')
        elif tag == 'script':
            if (a.get('type') or '').lower() == 'application/ld+json':
                self.in_jsonld = True
                self.jsonld_buf = ''
            elif 'src' not in a:
                self.in_script = True
                self.script_buf = ''
        elif tag == 'style':
            self.in_style = True
            self.style_buf = ''
        elif tag in ('h1', 'h2', 'h3'):
            self.in_heading = tag
            self.heading_buf = ''
        elif tag in ('img', 'media-item'):
            src = a.get('src') or a.get('contenturl') or a.get('data-src') or ''
            self.images.append({'tag': tag, 'alt': a.get('alt'), 'src': src})
        elif tag == 'a':
            self.links.append({'href': a.get('href') or '',
                               'label': a.get('aria-label'),
                               'rel': a.get('rel')})
        elif tag == 'iframe':
            self.iframes.append(a.get('src') or '')
        elif tag in ('audio', 'video'):
            self.media.append(tag)
        elif tag == 'form':
            self.forms += 1
        if tag in self.SKIP:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        elif tag == 'script':
            if self.in_jsonld:
                self.jsonld.append(self.jsonld_buf)
                self.in_jsonld = False
            if self.in_script:
                self.inline_scripts.append(self.script_buf)
                self.in_script = False
        elif tag == 'style' and self.in_style:
            self.inline_styles.append(self.style_buf)
            self.in_style = False
        elif tag == self.in_heading:
            self.headings.append((tag, re.sub(r'\s+', ' ', self.heading_buf).strip()))
            self.in_heading = None
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_jsonld:
            self.jsonld_buf += data
        if self.in_script:
            self.script_buf += data
        if self.in_style:
            self.style_buf += data
        if self.in_heading:
            self.heading_buf += data
        if not self.skip_depth and not self.in_title:
            self.text.append(data)


def jsonld_types(blocks):
    types = []
    for b in blocks:
        try:
            data = json.loads(b)
        except ValueError:
            types.append('INVALID')
            continue
        stack = [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
            elif isinstance(d, dict):
                t = d.get('@type')
                if t:
                    types.extend(t if isinstance(t, list) else [t])
                stack.extend(v for v in d.values() if isinstance(v, (dict, list)))
    return types


def analyse(url):
    status, headers, body = fetch(url)
    p = Page()
    try:
        p.feed(body)
    except Exception as exc:  # malformed markup should not stop the crawl
        print('parse error', url, exc)
    text = re.sub(r'\s+', ' ', ' '.join(p.text)).strip()
    words = len(re.findall(r'\w+', text))
    ext_domains = collections.Counter()
    internal = 0
    mailto = 0
    unlabeled = 0
    for ln in p.links:
        href = ln['href']
        if href.startswith('mailto:'):
            mailto += 1
            continue
        u = urllib.parse.urlparse(urllib.parse.urljoin(url, href))
        if u.scheme in ('http', 'https') and u.netloc and u.netloc != HOST:
            ext_domains[u.netloc.lower().removeprefix('www.')] += 1
        elif href and not href.startswith('#') and not href.startswith('javascript'):
            internal += 1
    imgs = p.images
    alt_missing = sum(1 for i in imgs if i['alt'] is None)
    alt_empty = sum(1 for i in imgs if i['alt'] is not None and not i['alt'].strip())
    alt_filename = sum(1 for i in imgs if i['alt'] and re.search(
        r'\.(jpe?g|png|gif|svg|webp)$|^IMG[_-]?\d|^DSC', i['alt'].strip(), re.I))
    return {
        'url': url,
        'status': status,
        'bytes': len(body.encode('utf-8', errors='replace')),
        'x_robots': header(headers, 'x-robots-tag'),
        'lang': p.lang,
        'title': re.sub(r'\s+', ' ', p.title).strip(),
        'description': p.meta.get('description'),
        'robots': p.meta.get('robots'),
        'og_title': p.meta.get('og:title'),
        'og_description': p.meta.get('og:description'),
        'og_image': p.meta.get('og:image'),
        'og_type': p.meta.get('og:type'),
        'twitter_card': p.meta.get('twitter:card'),
        'canonical': p.canonical,
        'hreflang': p.hreflang,
        'jsonld_types': jsonld_types(p.jsonld),
        'h1': [h for t, h in p.headings if t == 'h1'],
        'h2_count': sum(1 for t, _ in p.headings if t == 'h2'),
        'images': len(imgs),
        'alt_missing': alt_missing,
        'alt_empty': alt_empty,
        'alt_filename_like': alt_filename,
        'alt_samples': [i['alt'] for i in imgs if i['alt']][:4],
        'words': words,
        'text_hash': hashlib.sha1(text.encode()).hexdigest()[:12],
        'text_start': text[:220],
        'internal_links': internal,
        'external_domains': dict(ext_domains),
        'mailto': mailto,
        'iframes': p.iframes,
        'media_tags': p.media,
        'forms': p.forms,
        'inline_js_bytes': sum(len(s) for s in p.inline_scripts),
        'inline_css_bytes': sum(len(s) for s in p.inline_styles),
        'inline_scripts_top': sorted(
            ((len(s), re.sub(r'\s+', ' ', s.strip())[:110]) for s in p.inline_scripts),
            reverse=True)[:6],
        'icons': p.icons,
        'feeds': p.feeds,
        'manifest': p.manifest,
        'gtm': bool(re.search(r'googletagmanager\.com|GTM-[A-Z0-9]+|gtag\(', body)),
        'consent_words': bool(re.search(r'cookie\s*(consent|banner|policy|settings)|consent\s*mode|tarteaucitron|axeptio|didomi|cookiebot|onetrust', body, re.I)),
        'privacy_words': bool(re.search(r'privacy|confidentialit|mentions l[ée]gales|imprint|impressum', text, re.I)),
    }


def section(title):
    print()
    print('=' * 78)
    print(title)
    print('=' * 78)


def site_files():
    section('SITE-LEVEL FILES AND REDIRECTS')
    checks = [
        ('/robots.txt', True), ('/sitemap.xml', True), ('/llms.txt', True),
        ('/favicon.ico', True), ('/apple-touch-icon.png', True),
        ('/manifest.json', True), ('/site.webmanifest', True),
        ('/feed', True), ('/rss', True), ('/humans.txt', True),
        ('/.well-known/security.txt', True),
        ('/this-page-should-not-exist-af-audit', True),
    ]
    for path, follow in checks:
        status, headers, body = fetch(SITE + path, follow=follow)
        ctype = header(headers, 'content-type') or ''
        print(f'  {status:>3}  {path:<42} {ctype[:40]:<40} {len(body):>8} bytes')
        if path == '/robots.txt' and status == 200:
            print('       --- robots.txt ---')
            for ln in body.splitlines()[:60]:
                print('       ' + ln)
        if path == '/this-page-should-not-exist-af-audit':
            p = Page()
            p.feed(body)
            print(f'       404 page title: {p.title.strip()!r}  (a soft 404 returns 200)')
    for variant in ('http://' + HOST + '/', 'https://www.' + HOST + '/', 'http://www.' + HOST + '/'):
        r = subprocess.run(['curl', '-sS', '-o', '/dev/null', '-A', UA, '--max-time', '30',
                            '-w', '%{http_code} -> %{redirect_url}', variant],
                           capture_output=True, text=True)
        print(f'  {variant:<45} {r.stdout.strip() or r.stderr.strip()[:80]}')

    section('SECURITY AND PRIVACY HEADERS ON THE HOME DOCUMENT')
    status, headers, _ = fetch(SITE + '/')
    for name in ('strict-transport-security', 'content-security-policy',
                 'x-content-type-options', 'x-frame-options', 'referrer-policy',
                 'permissions-policy', 'cross-origin-opener-policy', 'server',
                 'cache-control', 'content-encoding', 'x-robots-tag', 'link'):
        print(f'  {name:<30} {header(headers, name) or "(absent)"}')


def sitemap_urls():
    status, _, body = fetch(SITE + '/sitemap.xml')
    urls = [u.strip() for u in re.findall(r'<loc>\s*(.*?)\s*</loc>', body)] if status == 200 else []
    lastmods = re.findall(r'<lastmod>\s*(.*?)\s*</lastmod>', body)
    section(f'SITEMAP  {len(urls)} URLs, {len(lastmods)} with <lastmod>')
    if SITE + '/' not in urls and SITE not in urls:
        urls.insert(0, SITE + '/')
    odd = [u for u in urls if re.search(r"[,()'’–—\s]|%[0-9A-F]{2}", urllib.parse.urlparse(u).path)]
    fragments = [u for u in urls if re.search(
        r'/(menu|footer|header)$|-(overlay|stack|header|menu|background|holographic)(-\d+)?$', u)]
    print(f'  URLs with commas, parentheses, dashes or encoded characters: {len(odd)}')
    for u in odd[:40]:
        print('     ', u)
    print(f'  URLs that look like layout fragments (menu, footer, overlay, stack, header): {len(fragments)}')
    for u in fragments:
        print('     ', u)
    norm = collections.Counter(u.rstrip('/') for u in urls)
    dups = [u for u, n in norm.items() if n > 1]
    print(f'  Same page listed twice (trailing-slash variants): {dups}')
    return list(dict.fromkeys(urls))


def report(rows):
    ok = [r for r in rows if r['status'] == 200]
    section(f'PAGE INVENTORY  {len(ok)}/{len(rows)} pages returned 200')
    for r in rows:
        if r['status'] != 200:
            print('  NON-200', r['status'], r['url'])

    def dist(key):
        return collections.Counter((r[key] or '(none)') for r in ok)

    section('TITLES')
    titles = dist('title')
    print(f'  distinct titles: {len(titles)} across {len(ok)} pages')
    for t, n in titles.most_common(12):
        print(f'    {n:>4}x  {t[:100]}')

    section('META DESCRIPTIONS')
    descs = dist('description')
    print(f'  distinct descriptions: {len(descs)} across {len(ok)} pages')
    for t, n in descs.most_common(6):
        print(f'    {n:>4}x  {t[:160]}')

    section('SOCIAL CARDS (Open Graph / Twitter)')
    for key in ('og_title', 'og_description', 'og_image', 'og_type', 'twitter_card'):
        d = dist(key)
        print(f'  {key:<15} distinct={len(d):<4} missing={d.get("(none)", 0):<4} top: {d.most_common(1)[0][0][:90]}')

    section('INDEXING SIGNALS')
    for key in ('lang', 'canonical', 'robots', 'x_robots'):
        d = dist(key)
        print(f'  {key:<10} distinct={len(d):<4} missing={d.get("(none)", 0):<4} examples: {[k[:60] for k, _ in d.most_common(3)]}')
    self_canon = sum(1 for r in ok if r['canonical'] and r['canonical'].rstrip('/') == r['url'].rstrip('/'))
    print(f'  self-referencing canonical: {self_canon}/{len(ok)}')
    print(f'  pages with hreflang alternates: {sum(1 for r in ok if r["hreflang"])}')
    jt = collections.Counter(t for r in ok for t in r['jsonld_types'])
    print(f'  JSON-LD types across the site: {dict(jt) or "none"}')
    print(f'  RSS/Atom feed links: {sum(1 for r in ok if r["feeds"])} pages; manifest link: {ok[0]["manifest"] if ok else None}')
    print(f'  icon rels on home: {ok[0]["icons"] if ok else None}')

    section('HEADINGS')
    h1 = collections.Counter(len(r['h1']) for r in ok)
    print(f'  pages by number of <h1>: {dict(sorted(h1.items()))}')
    h1text = collections.Counter(h for r in ok for h in r['h1'])
    for t, n in h1text.most_common(8):
        print(f'    {n:>4}x  h1 = {t[:90]!r}')

    section('IMAGES AND ALT TEXT (img + Cargo media-item)')
    total = sum(r['images'] for r in ok)
    miss = sum(r['alt_missing'] for r in ok)
    empty = sum(r['alt_empty'] for r in ok)
    fname = sum(r['alt_filename_like'] for r in ok)
    print(f'  images: {total}  alt missing: {miss}  alt empty: {empty}  alt looks like a filename: {fname}')
    worst = sorted(ok, key=lambda r: r['alt_missing'] + r['alt_empty'], reverse=True)[:8]
    for r in worst:
        print(f'    {r["alt_missing"] + r["alt_empty"]:>4} without alt / {r["images"]:<4} {r["url"]}')
    samples = [a for r in ok for a in r['alt_samples']]
    print('  sample alt texts:')
    for a in list(dict.fromkeys(samples))[:12]:
        print(f'    {a[:110]!r}')

    section('READABLE TEXT IN RAW HTML (what search engines and AI fetchers read)')
    ws = sorted(r['words'] for r in ok)
    if ws:
        print(f'  words per page: min {ws[0]}  median {ws[len(ws)//2]}  max {ws[-1]}')
    thin = [r for r in ok if r['words'] < 150]
    print(f'  pages under 150 words: {len(thin)}')
    for r in sorted(thin, key=lambda r: r['words'])[:25]:
        print(f'    {r["words"]:>5}  {r["url"]}')
    hashes = collections.Counter(r['text_hash'] for r in ok)
    dup_groups = [h for h, n in hashes.items() if n > 1]
    print(f'  groups of pages with identical visible text: {len(dup_groups)}')
    for h in dup_groups[:8]:
        members = [r['url'] for r in ok if r['text_hash'] == h]
        print(f'    {len(members)} pages, e.g. {members[:3]}')
    print('  opening text of key pages:')
    for r in ok:
        if urllib.parse.urlparse(r['url']).path.strip('/') in ('', 'arthur-fouray', 'biography', 'music', 'exhibition-making', 'ppplus', 'screen', 'rt4a'):
            print(f'    [{r["url"]}]')
            print(f'      {r["text_start"]!r}')

    section('LINKS, EMBEDS AND CONTACT')
    ext = collections.Counter()
    for r in ok:
        ext.update(r['external_domains'].keys())
    print('  external domains (number of pages linking to each):')
    for d, n in ext.most_common(30):
        print(f'    {n:>4}  {d}')
    print(f'  pages with a mailto link: {sum(1 for r in ok if r["mailto"])}')
    print(f'  pages with a <form>: {sum(1 for r in ok if r["forms"])}')
    iframes = collections.Counter(urllib.parse.urlparse(s).netloc for r in ok for s in r['iframes'] if s)
    print(f'  iframe embeds by host: {dict(iframes) or "none"}')
    media = collections.Counter(t for r in ok for t in r['media_tags'])
    print(f'  <audio>/<video> tags: {dict(media) or "none"}')
    print(f'  internal links per page (median): {sorted(r["internal_links"] for r in ok)[len(ok)//2] if ok else 0}')

    section('ANALYTICS, CONSENT AND LEGAL')
    print(f'  pages loading Google Tag Manager / gtag: {sum(1 for r in ok if r["gtm"])}')
    print(f'  pages with any cookie-consent tooling or wording: {sum(1 for r in ok if r["consent_words"])}')
    print(f'  pages whose text mentions privacy / legal notice: {sum(1 for r in ok if r["privacy_words"])}')

    section('PAGE WEIGHT (raw HTML)')
    by_size = sorted(ok, key=lambda r: r['bytes'], reverse=True)
    for r in by_size[:10]:
        print(f'  {r["bytes"]/1024:>8.1f} KiB  inline JS {r["inline_js_bytes"]/1024:>7.1f} KiB  inline CSS {r["inline_css_bytes"]/1024:>6.1f} KiB  {r["url"]}')
    home = next((r for r in ok if r['url'].rstrip('/') == SITE), ok[0] if ok else None)
    if home:
        print('  largest inline scripts on the home page (bytes, first characters):')
        for size, start in home['inline_scripts_top']:
            print(f'    {size:>8}  {start!r}')


def lighthouse_summary():
    files = sorted(f for f in os.listdir(OUT) if f.startswith('lh_') and f.endswith('.json'))
    for f in files:
        try:
            data = json.load(open(os.path.join(OUT, f)))
        except ValueError:
            print('unreadable', f)
            continue
        section(f'LIGHTHOUSE  {data.get("finalDisplayedUrl") or data.get("requestedUrl")}  [{f}]')
        cats = data.get('categories', {})
        print('  scores: ' + ', '.join(f'{k}={round((v.get("score") or 0) * 100)}' for k, v in cats.items()))
        audits = data.get('audits', {})
        for cat_key, cat in cats.items():
            fails = []
            for ref in cat.get('auditRefs', []):
                a = audits.get(ref['id'], {})
                if a.get('scoreDisplayMode') in ('notApplicable', 'manual', 'informative'):
                    continue
                if a.get('score') is not None and a['score'] < 0.9:
                    fails.append(a)
            if not fails or cat_key == 'performance':
                continue
            print(f'  [{cat_key}] failing audits:')
            for a in fails:
                items = (a.get('details') or {}).get('items') or []
                print(f'    - {a.get("title")}  ({len(items)} items)')
                for it in items[:4]:
                    node = it.get('node') or {}
                    snippet = node.get('snippet') or it.get('source') or it.get('url') or it.get('description') or ''
                    label = node.get('nodeLabel') or ''
                    if isinstance(snippet, dict):
                        snippet = snippet.get('url', '')
                    print(f'        {str(label)[:60]!r}  {str(snippet)[:120]}')
        if 'performance' in cats:
            for audit_id in ('bootup-time', 'mainthread-work-breakdown'):
                a = audits.get(audit_id, {})
                print(f'  {a.get("title")}: {a.get("displayValue")}')
                for it in ((a.get('details') or {}).get('items') or [])[:10]:
                    name = it.get('url') or it.get('groupLabel') or it.get('group')
                    total = it.get('total') or it.get('duration') or 0
                    script = it.get('scripting')
                    extra = f'  scripting {script:.0f} ms' if isinstance(script, (int, float)) else ''
                    print(f'      {total:>10.0f} ms{extra}  {str(name)[:110]}')
            a = audits.get('long-tasks', {})
            items = (a.get('details') or {}).get('items') or []
            print(f'  long tasks: {len(items)}')
            by_url = collections.Counter()
            for it in items:
                by_url[it.get('url', '?')] += it.get('duration', 0)
            for u, d in by_url.most_common(6):
                print(f'      {d:>10.0f} ms  {u[:110]}')


def main():
    site_files()
    urls = sitemap_urls()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(analyse, urls))
    json.dump(rows, open(os.path.join(OUT, 'pages.json'), 'w'), indent=1)
    report(rows)
    lighthouse_summary()


if __name__ == '__main__':
    main()
