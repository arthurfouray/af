#!/usr/bin/env python3
"""Crawl a Cargo site through its sitemap and flag pages that will search badly.

Standard library only. Usage:

    python3 search/audit_search_index.py https://arthurfouray.systems

Writes search_index_audit.csv (one row per page) and prints a summary.
Flags per page:
  no-title        title missing or generic
  dup-title       another page has the same title after normalisation
  no-description  meta description missing
  thin            fewer than MIN_WORDS words in the raw HTML (no JS)
  no-year         no four-digit year anywhere in title, description or text
  accent-only     a word appears only in its accented form (add the plain form)
"""
import csv
import html
import re
import sys
import unicodedata
import urllib.error
import urllib.request

MIN_WORDS = 80
GENERIC_TITLES = {"", "untitled", "new page", "page", "home"}
# words visitors type without accents; add to taste
ACCENT_PAIRS = {
    "café": "cafe", "genève": "geneve", "zürich": "zurich", "réel": "reel",
    "shéhérazade": "sheherazade", "vitæ": "vitae", "galeries": "galeries",
}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (search-audit/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def tag(page, pattern):
    m = re.search(pattern, page, re.I | re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def fold(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def norm_title(t):
    t = re.sub(r"\s+[—–-]\s+arthur fouray systems$", "", fold(t))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def visible_text(page):
    t = re.sub(r"<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>", " ", page, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def audit(base):
    base = base.rstrip("/")
    status, sm = get(f"{base}/sitemap.xml")
    urls = re.findall(r"<loc>(.*?)</loc>", sm)
    if not urls:
        sys.exit(f"sitemap.xml returned {status} with no URLs")
    rows = []
    for u in urls:
        st, page = get(u)
        title = tag(page, r"<title[^>]*>(.*?)</title>")
        desc = tag(page, r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']')
        text = visible_text(page)
        words = text.split()
        blob = f"{title} {desc} {text}"
        flags = []
        if norm_title(title) in GENERIC_TITLES:
            flags.append("no-title")
        if not desc:
            flags.append("no-description")
        if len(words) < MIN_WORDS:
            flags.append("thin")
        if not re.search(r"\b(19|20)\d{2}\b", blob):
            flags.append("no-year")
        low = blob.lower()
        for acc, plain in ACCENT_PAIRS.items():
            if acc in low and plain not in fold(blob).replace(acc, ""):
                if plain not in low:
                    flags.append(f"accent-only:{acc}")
        rows.append({
            "url": u, "status": st, "title": title, "norm_title": norm_title(title),
            "description": desc, "words": len(words), "flags": flags,
        })
        print(f"[{st}] {u}  words={len(words)}  {' '.join(flags)}")
    seen = {}
    for r in rows:
        seen.setdefault(r["norm_title"], []).append(r)
    for group in seen.values():
        if len(group) > 1:
            for r in group:
                r["flags"].append("dup-title")
    with open("search_index_audit.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["url", "status", "title", "description", "words", "flags"], extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "flags": " ".join(r["flags"])})
    flagged = sum(1 for r in rows if r["flags"])
    print(f"\n{len(rows)} pages, {flagged} flagged. Written to search_index_audit.csv")


if __name__ == "__main__":
    audit(sys.argv[1] if len(sys.argv) > 1 else "https://arthurfouray.systems")
