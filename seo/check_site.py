#!/usr/bin/env python3
"""Crawlability and AI-access check for a Cargo site. Standard library only.

    python3 seo/check_site.py https://arthurfouray.systems
    python3 seo/check_site.py --self-test    # verify the robots.txt parser

The robots.txt parser follows RFC 9309: consecutive User-agent lines share one
group, a bot's own group fully overrides the "*" group, and among matching
rules the longest path wins with Allow breaking ties.
"""
import re
import sys
import urllib.error
import urllib.request

# Retrieval bots decide whether you appear in AI answers. Training bots only
# affect model training. Blocking a retrieval bot removes you from that
# product's answers entirely.
AI_BOTS = [
    ("GPTBot", "training"),
    ("OAI-SearchBot", "retrieval"),
    ("ChatGPT-User", "retrieval"),
    ("ClaudeBot", "training"),
    ("Claude-SearchBot", "retrieval"),
    ("Claude-User", "retrieval"),
    ("anthropic-ai", "training"),
    ("PerplexityBot", "retrieval"),
    ("Perplexity-User", "retrieval"),
    ("Google-Extended", "training"),
    ("Applebot-Extended", "training"),
    ("CCBot", "training"),
    ("Bytespider", "training"),
    ("meta-externalagent", "training"),
]

TITLE_MAX = 60
DESC_MIN, DESC_MAX = 120, 155
THIN_WORDS = 80


# --------------------------------------------------------------------------
# robots.txt
# --------------------------------------------------------------------------
def parse_robots(text):
    """Return [(agents, [(kind, path), ...]), ...] preserving group structure."""
    groups, agents, rules, in_agents = [], [], [], False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field, value = field.strip().lower(), value.strip()
        if field == "user-agent":
            if not in_agents and agents:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
            in_agents = True
        elif field in ("allow", "disallow"):
            in_agents = False
            if agents:
                rules.append((field, value))
    if agents:
        groups.append((agents, rules))
    return groups


def _path_matches(pattern, path):
    """Prefix match with * wildcard and $ end-anchor, per RFC 9309."""
    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]
    regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in pattern)
    return re.match(regex + ("$" if anchored else ""), path) is not None


def rules_for(groups, bot):
    """Rules that apply to bot, and where they came from."""
    bot = bot.lower()
    own = [r for agents, rules in groups if bot in agents for r in rules]
    if any(bot in agents for agents, _ in groups):
        return own, "own group"
    wild = [r for agents, rules in groups if "*" in agents for r in rules]
    if any("*" in agents for agents, _ in groups):
        return wild, "wildcard group"
    return [], "no rule"


def is_allowed(rules, path="/"):
    """Longest matching rule wins; Allow breaks ties. Empty Disallow allows."""
    best = None
    for kind, value in rules:
        if not value or not _path_matches(value, path):
            continue
        n = len(value)
        if best is None or n > best[0] or (n == best[0] and kind == "allow"):
            best = (n, kind)
    return True if best is None else best[1] == "allow"


# --------------------------------------------------------------------------
# fetching
# --------------------------------------------------------------------------
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


def check_page(url, findings, descriptions):
    status, html = get(url)
    if status != 200:
        findings.append(f"{url} returned HTTP {status}")
        print(f"\n== {url}  [{status}]")
        return

    title = tag(html, r"<title[^>]*>(.*?)</title>")
    desc = tag(html, r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']')
    canonical = tag(html, r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\'](.*?)["\']')
    lang = tag(html, r'<html[^>]+lang=["\']([^"\']+)')
    robots_meta = tag(html, r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'](.*?)["\']')
    og_image = tag(html, r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](.*?)["\']')
    stripped = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    words = len(re.sub(r"<[^>]+>", " ", stripped).split())
    imgs = re.findall(r"<img[^>]*>", html, re.I)
    noalt = [i for i in imgs if not re.search(r'alt=["\'][^"\']+["\']', i, re.I)]
    has_jsonld = "application/ld+json" in html

    print(f"\n== {url}  [{status}]")
    print(f"  title:       {title}  ({len(title or '')} chars)")
    print(f"  description: {desc}  ({len(desc or '')} chars)")
    print(f"  canonical:   {canonical}")
    print(f"  lang:        {lang}")
    print(f"  robots meta: {robots_meta}")
    print(f"  og:image:    {og_image}")
    print(f"  json-ld:     {'yes' if has_jsonld else 'NO'}")
    print(f"  images: {len(imgs)}, without alt: {len(noalt)}")
    print(f"  words in raw HTML (no JS): {words}")

    if not title:
        findings.append(f"{url} has no <title>")
    elif len(title) > TITLE_MAX:
        findings.append(f"{url} title is {len(title)} chars (aim for under {TITLE_MAX})")
    if not desc:
        findings.append(f"{url} has no meta description")
    else:
        descriptions.setdefault(desc, []).append(url)
        if not DESC_MIN <= len(desc) <= DESC_MAX:
            findings.append(f"{url} description is {len(desc)} chars (aim for {DESC_MIN}-{DESC_MAX})")
    if not canonical:
        findings.append(f"{url} has no canonical link")
    if robots_meta and "noindex" in robots_meta.lower():
        findings.append(f"{url} is noindex: {robots_meta}")
    if noalt:
        findings.append(f"{url} has {len(noalt)} of {len(imgs)} images without alt text")
    if words < THIN_WORDS:
        findings.append(
            f"{url} has only {words} words in raw HTML; AI fetchers do not run JavaScript"
        )


# --------------------------------------------------------------------------
def self_test():
    cases = [
        # grouped agents share one Disallow
        ("User-agent: GPTBot\nUser-agent: CCBot\nDisallow: /", "GPTBot", False),
        ("User-agent: GPTBot\nUser-agent: CCBot\nDisallow: /", "CCBot", False),
        # Disallow: / not adjacent to the User-agent line
        ("User-agent: ClaudeBot\nDisallow: /private\nDisallow: /", "ClaudeBot", False),
        # Allow: / with a narrower Disallow leaves the root open
        ("User-agent: PerplexityBot\nAllow: /\nDisallow: /admin", "PerplexityBot", True),
        # a bot's own group overrides the wildcard group
        ("User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nAllow: /", "GPTBot", True),
        ("User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nAllow: /", "CCBot", False),
        # empty Disallow means allow everything
        ("User-agent: *\nDisallow:", "GPTBot", True),
        # comments and blank lines are ignored
        ("# note\nUser-agent: GPTBot  # inline\nDisallow: /", "GPTBot", False),
        # no rules at all
        ("", "GPTBot", True),
        # end-anchored rule does not block the root
        ("User-agent: GPTBot\nDisallow: /feed$", "GPTBot", True),
    ]
    failed = 0
    for text, bot, expected in cases:
        rules, _ = rules_for(parse_robots(text), bot)
        got = is_allowed(rules)
        ok = got == expected
        failed += not ok
        if not ok:
            print(f"FAIL {bot} expected allowed={expected} got {got}\n---\n{text}\n---")
    print(f"self-test: {len(cases) - failed} passed, {failed} failed")
    return 1 if failed else 0


def main():
    args = [a for a in sys.argv[1:] if a != "--self-test"]
    if "--self-test" in sys.argv:
        return self_test()

    base = (args[0] if args else "https://arthurfouray.systems").rstrip("/")
    findings, descriptions = [], {}

    status, robots = get(f"{base}/robots.txt")
    print(f"== robots.txt [{status}]")
    print(robots.strip() or "(empty)")
    if status != 200:
        findings.append(f"robots.txt returned HTTP {status}")
    groups = parse_robots(robots)
    print("\n  AI crawler access to /:")
    for bot, kind in AI_BOTS:
        rules, source = rules_for(groups, bot)
        allowed = is_allowed(rules)
        mark = "OK     " if allowed else "BLOCKED"
        print(f"    {mark} {bot:<22} {kind:<9} via {source}")
        if not allowed and kind == "retrieval":
            findings.append(
                f"{bot} is blocked by robots.txt; this removes the site from that product's AI answers"
            )
        elif not allowed:
            findings.append(f"{bot} is blocked by robots.txt (training crawler)")

    status, sitemap = get(f"{base}/sitemap.xml")
    urls = re.findall(r"<loc>\s*(.*?)\s*</loc>", sitemap)
    print(f"\n== sitemap.xml [{status}] {len(urls)} urls")
    for u in urls:
        print("  ", u)
    if status != 200:
        findings.append(f"sitemap.xml returned HTTP {status}")
    elif not urls:
        findings.append("sitemap.xml contains no <loc> entries")

    status, llms = get(f"{base}/llms.txt")
    present = status == 200 and llms.lstrip().startswith("#")
    print(f"\n== llms.txt [{status}] {'present' if present else 'missing'}")
    if not present:
        findings.append("llms.txt is missing; see seo/llms.txt in this repo")

    pages = [base + "/"] + [u for u in urls if u.rstrip("/") != base][:15]
    for u in pages:
        check_page(u, findings, descriptions)

    for desc, where in descriptions.items():
        if len(where) > 1:
            findings.append(
                f"{len(where)} pages share one description ({desc[:50]}...); "
                "give each page its own, per seo/page-descriptions.md"
            )

    # A different response to an AI user agent means the site treats it differently.
    _, human = get(base + "/")
    s_ai, ai = get(base + "/", ua="ClaudeBot/1.0 (+claudebot@anthropic.com)")
    print(f"\n== homepage as ClaudeBot: [{s_ai}] {len(ai)} bytes vs {len(human)} as a browser")
    if s_ai != 200:
        findings.append(f"homepage returns HTTP {s_ai} to ClaudeBot but 200 to a browser")
    elif human and abs(len(ai) - len(human)) > 0.1 * len(human):
        findings.append("homepage serves materially different content to ClaudeBot")

    print(f"\n{'=' * 60}\n{len(findings)} findings\n{'=' * 60}")
    for i, f in enumerate(findings, 1):
        print(f"{i:2}. {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
