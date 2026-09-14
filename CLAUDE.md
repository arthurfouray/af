# AF research runners

GitHub Actions workflows that crawl and verify public New Yorker "Tables for Two"
listings. Outputs are uploaded as workflow artifacts and are never committed.

## Layout

- `scripts/newyorker_tables_for_two_audit.py` — live crawler (398 lines), run by
  the "New Yorker Tables for Two audit" workflow.
- `payload/*.py.gz.b64` — gzip+base64-encoded Python, decoded at workflow runtime.
  `payload/final_chunks/` holds a split copy of `prepare_final_candidates.py`.
- `.github/workflows/` — the audit, final-verification, and stale-run-cancel workflows.

## Working with the payloads

Decode once into a scratch dir, then read the decoded `.py`. Never read the
`.b64` files directly — they are unreadable and burn a lot of context.
Two `PreToolUse` hooks in `.claude/settings.json` enforce this; the block
message repeats the decode command.

```bash
mkdir -p /tmp/af-work
for f in payload/*.py.gz.b64; do
  base64 -d "$f" | gzip -dc > "/tmp/af-work/$(basename "$f" .gz.b64)"
done
```

To change payload behaviour, edit the decoded file and re-encode:

```bash
gzip -9 -n -c /tmp/af-work/NAME.py | base64 -w0 > payload/NAME.py.gz.b64
```

Known broken: `payload/repair_v6.py.gz.b64` has a damaged gzip stream. The base64
is clean, but it decodes to only 227 of its lines and then fails with CRC and
length errors, so the final-verification workflow's decode step cannot succeed
until the payload is regenerated from its original source. Don't re-diagnose it.

## Session cost

This repo's `.claude/settings.json` pins effort to `high` and caps the
auto-compact window at 200K tokens. See `docs/claude-code-usage.md` before
changing those. Two habits matter more than any setting:

- `/clear` between unrelated tasks — every request re-sends the whole
  conversation, so a stale session makes each later turn more expensive.
- Read narrowly. Prefer `grep`/`sed -n '100,160p'` over whole-file reads; a
  decoded payload is ~430 lines and rarely needs to be read end to end.

## Compact instructions

When compacting, keep the current diff, the decode/re-encode commands above, and
any workflow-run IDs in play. Drop decoded payload bodies — they can be
regenerated from `payload/` in one command.
