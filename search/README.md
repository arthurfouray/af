# Search audit for arthurfouray.systems

The site runs on Cargo 3. Its search box is Cargo's hosted search, so there is
no search code to tune in this repository. What the search returns is decided
entirely by the content of each page: its title, its tags, its description and
the text Cargo can read from the page body. A "perfect" search is therefore a
content audit, entry by entry, plus a fixed set of test queries that is re-run
every time entries are added.

Nothing here is deployed by this repo. `audit_search_index.py` runs locally
against the live site; `queries.txt` is the regression list to test in the
Cargo search box after each round of edits.

## What Cargo search can and cannot see

- It matches on page title, tags and page text. It does not see text inside
  images, PDFs or embedded players.
- Matching is literal. "Cafe" and "café" are different words to it, as are
  "PPP+" and "PPP", "rt4a" and "RT4A" (case is folded, punctuation is not
  reliable).
- There is no synonym table, no weighting control and no ranking control.
  The only way to make an entry rank for a word is to put that word in the
  title, the tags or the first lines of the page.
- Pages with a password, or hidden from the index, do not appear.

## Audit checklist, entry by entry

Run the crawler first; it produces `search_index_audit.csv` with one row per
page and a `flags` column. Then work through the flags in this order.

1. **Coverage.** Every entry that should be findable is in `sitemap.xml`.
   Any page missing from the sitemap is invisible to search engines and is
   a candidate for being hidden from Cargo search too.
2. **Duplicate or near-duplicate titles.** Two pages titled "Untitled" or
   "Spectre" and "Spectre (2015)" compete for the same query and the wrong
   one can win. Give each entry a title that is unique on its own:
   `Work title, venue, city, year`.
3. **Thin pages.** A page whose raw HTML carries fewer than 80 words is
   matched only by its title. Add one plain-text paragraph at the top of
   the page stating what, when, where and who. This is the same paragraph
   the SEO kit asks for, so it pays twice.
4. **Accents and aliases.** For every word a visitor might type in more than
   one form, make sure both forms are on the page. Concretely: `café / cafe`,
   `Genève / Geneva`, `Zürich / Zurich`, `rt4a / RT4A`, `PPP+ / PPP plus /
   PPPplus`, `Scheherazade / Shéhérazade / Sheherazade`. Tags are the
   cheapest place to hold the alternate spelling.
5. **Years and venues as tags.** Add the year, the venue and the city as
   tags on every exhibition, release and publication entry. A query such as
   "2015 Geneva" then returns exactly the Spectre show instead of nothing.
6. **Series names on every member.** Every card in PPP+, every track in a
   release, every essay in Exhibition Making carries the series name as a
   tag, so searching the series returns the whole series, not the index page
   alone.
7. **Consistent category vocabulary.** Pick one word per category and tag
   with it everywhere: `exhibition`, `curated`, `publication`, `painting`,
   `music`, `card`. Mixed vocabularies (`show` on one page, `exhibition` on
   another) split results.
8. **Descriptions.** Fill the per-page description from
   `seo/page-descriptions.md`. Cargo search reads it, and it becomes the
   result snippet.

## Regression queries

`queries.txt` lists one query per line with the page that must come first.
After every batch of new entries, type each query into the site's search
box and check the first result. A query whose expected page has slipped is
the signal that a new entry has stolen its words, and that the new entry's
title or tags need to be made more specific.

Extend the list every time a visitor reports a search miss.

## Beyond Cargo's own search

If literal matching stays the ceiling, the two realistic upgrades are:

- **Monocle**: a hosted search built for Cargo sites, added via Custom HTML,
  with fuzzy matching and its own index of the page text.
- **A static index served from this repo**: run `audit_search_index.py` on a
  schedule, publish the CSV as JSON, and embed a small client-side search
  (Fuse.js or MiniSearch, a few kilobytes) in Cargo's Custom HTML. This
  gives accent folding, synonyms and field weighting under your control,
  and the audit CSV doubles as the index.

Do the content audit first in either case; both upgrades index the same
titles, tags and text, and neither fixes a missing year or a duplicate
title.
