/**
 * OPTIONAL. Only needed if Cargo's own /robots.txt blocks AI retrieval bots,
 * or if Cargo will not serve /llms.txt from the domain root. Run
 * `python3 seo/check_site.py https://arthurfouray.systems` first: if no bot
 * shows BLOCKED and llms.txt is present, this file is unnecessary.
 *
 * What it does: serves /robots.txt and /llms.txt itself and passes every other
 * request through to Cargo untouched.
 *
 * Prerequisites, and the honest cost of them:
 *   - arthurfouray.systems must use Cloudflare nameservers with the record
 *     pointing at Cargo and proxying ON (orange cloud).
 *   - SSL/TLS mode must be Full or Full (strict); Flexible will loop.
 *   - Putting a proxy in front of Cargo means Cargo support can no longer see
 *     the full request path when diagnosing issues. Do not do this casually.
 *
 * Deploy: Cloudflare dashboard > Workers & Pages > Create Worker, paste this,
 * then add a route for arthurfouray.systems/* on the zone.
 */

const ROBOTS = `User-agent: *
Allow: /

# AI retrieval bots: these decide whether the site appears in AI answers.
User-agent: OAI-SearchBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: Claude-SearchBot
Allow: /

User-agent: Claude-User
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Perplexity-User
Allow: /

# Training bots. Allowed here; change Allow to Disallow to opt out of training
# without losing AI search visibility, which the retrieval groups above keep.
User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: Applebot-Extended
Allow: /

Sitemap: https://arthurfouray.systems/sitemap.xml
`;

// Keep this in sync with seo/llms.txt. Paste that file's contents here.
const LLMS = `# Arthur Fouray Systems

> Official website and active archive of Arthur Fouray (born 9 May 1990, Paris),
> French artist and curator.

See https://arthurfouray.systems/curriculum-vitae for the full CV.
`;

export default {
  async fetch(request) {
    const { pathname } = new URL(request.url);
    const headers = {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": "public, max-age=3600",
    };
    if (pathname === "/robots.txt") return new Response(ROBOTS, { headers });
    if (pathname === "/llms.txt") return new Response(LLMS, { headers });
    return fetch(request);
  },
};
