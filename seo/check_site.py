#!/usr/bin/env python3
"""Quick crawlability check for a Cargo site. Standard library only.

Usage: python3 seo/check_site.py https://arthurfouray.systems
"""
import re
import sys
import urllib.error
import urllib.request

AI_BOTS = [
    "GPTBot", "OAI-SearchBot", "ChatGPT-User",
    "ClaudeBot", "Claude-SearchBot", "Claude-User", "anthropic-ai",
    "PerplexityBot", "Perplexity-User", "Google-Extended", "Applebot-Extended",
    "CCBot", "Bytespider", "meta-externalagent",
]


def get(url, ua="Mozilla/5.0 (compatible; seo-check/1.0)"):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def tag(html, pattern):
    m = re.search(pattern, html, re.I | re.S)
    return m.group(1).strip() if m else None


def check_page(url):
    status, html = get(url)
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    words = len(re.sub(r"<[^>]+>", " ", text).split())
    print(f"\n== {url}  [{status}]")
    print("  title:      ", tag(html, r"<title[^>]*>(.*?)</title>"))
    print("  description:", tag(html, r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']'))
    print("  canonical:  ", tag(html, r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\'](.*?)["\']'))
    print("  lang:       ", tag(html, r'<html[^>]+lang=["\']([^"\']+)'))
    print("  robots meta:", tag(html, r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'](.*?)["\']'))
    print("  og:image:   ", tag(html, r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](.*?)["\']'))
    print("  json-ld:    ", "yes" if "application/ld+json" in html else "NO")
    imgs = re.findall(r"<img[^>]*>", html, re.I)
    noalt = [i for i in imgs if not re.search(r'alt=["\'][^"\']+["\']', i, re.I)]
    print(f"  images: {len(imgs)}, without alt: {len(noalt)}")
    print(f"  words in raw HTML (no JS): {words}", "<- thin for AI fetchers" if words < 80 else "")


def main():
    base = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "https://arthurfouray.systems"

    status, robots = get(f"{base}/robots.txt")
    print(f"== robots.txt [{status}]")
    print(robots or "(empty)")
    blocked = [b for b in AI_BOTS if re.search(rf"user-agent:\s*{re.escape(b)}\s*\n\s*disallow:\s*/\s*$", robots, re.I | re.M)]
    print("AI bots blocked:", blocked or "none")
    if "*" in robots and re.search(r"user-agent:\s*\*\s*\n\s*disallow:\s*/\s*$", robots, re.I | re.M):
        print("WARNING: everything is disallowed for all bots")

    status, sitemap = get(f"{base}/sitemap.xml")
    urls = re.findall(r"<loc>(.*?)</loc>", sitemap)
    print(f"\n== sitemap.xml [{status}] {len(urls)} urls")
    for u in urls:
        print("  ", u)

    status, llms = get(f"{base}/llms.txt")
    print(f"\n== llms.txt [{status}] {'present' if status == 200 and llms.strip().startswith('#') else 'missing'}")

    for u in [base + "/"] + [u for u in urls if u.rstrip("/") != base][:15]:
        check_page(u)

    # Does the site answer differently to an AI user agent?
    s_ai, html_ai = get(base + "/", ua="ClaudeBot/1.0 (+claudebot@anthropic.com)")
    print(f"\n== homepage fetched as ClaudeBot: [{s_ai}] {len(html_ai)} bytes")


if __name__ == "__main__":
    main()
