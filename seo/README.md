# SEO and AI-crawl kit for arthurfouray.systems

Paste-ready assets for the Cargo 3 site. Nothing here is deployed by this repo;
each file states where it goes in the Cargo admin.

| File | Where it goes |
| --- | --- |
| `person.jsonld.html` | Cargo: Settings > Site Details > Additional meta tags (site-wide) |
| `page-descriptions.md` | Cargo: per-page settings, Title and Description fields |
| `llms.txt` | Root of the domain at `/llms.txt` if Cargo allows a root file; otherwise a plain text page at `/llms` |
| `check_site.py` | Run locally to verify raw HTML, robots.txt, sitemap and AI-bot access |
| `cloudflare-worker.js` | Optional, and only if the check shows AI bots blocked or `/llms.txt` unreachable. Read its caveats first. |

## Verifying the checker

Cargo does not let you edit `robots.txt`, so the checker's reading of it is the
only evidence you get about AI crawler access. Confirm the parser is sound
before trusting its verdict:

    python3 seo/check_site.py --self-test

Ten cases covering grouped `User-agent` lines, non-adjacent `Disallow`, `Allow`
overrides, wildcard fallback and end-anchored paths. All ten must pass. The
checker distinguishes retrieval bots, which decide whether you appear in AI
answers, from training bots, which do not.

## Order of work

1. Fill the `TODO` fields in `person.jsonld.html` (sameAs links, image URL), then paste it.
2. Apply the titles and descriptions from `page-descriptions.md` page by page.
3. Add alt text to every image on the project pages. Cargo exposes this per image.
4. Add a short plain-text paragraph at the top of each project page. This is what
   AI fetchers read; they do not run JavaScript.
5. Run `python3 seo/check_site.py https://arthurfouray.systems` and fix what it flags.
   If any bot shows BLOCKED, or `/llms.txt` cannot be served, consider
   `cloudflare-worker.js`.
6. Submit `sitemap.xml` in Google Search Console and Bing Webmaster Tools.
7. Create or update a Wikidata item for Arthur Fouray with the site as official website,
   and make sure Artsy, Les presses du réel, Motto and Bandcamp link back to the site.

## Facts used

Taken from the public CV PDF, Les presses du réel, Artsy and search snippets.
Correct anything wrong before publishing.

- Arthur Fouray, born 9 May 1990, Paris. Artist and curator.
- Curator at DOC, Paris. Co-founded Silicon Malley, Lausanne, 2015.
- First solo show "Spectre" at Espace Quark, Geneva, 2015. "2080" at ZQM, Berlin.
- Book "Screen" published by Les presses du réel (Tombolo Presses).
- Music released as rt4a, including Scheherazade Op. 35 versions and 2025 singles.
- PPP+: 620 playing cards, online, physical and NFT, 2023 to 2025.
