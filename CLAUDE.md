# Working in this repo

Reproducible research runners. Logic lives in `payload/*.gz.b64` (gzip+base64 blobs that
`.github/workflows/*.yml` decodes with `base64 -d <file> | gzip -dc > work/<name>.py`).
Outputs are workflow artifacts; no dataset is committed to the default branch.

## Token hygiene (this repo burns context fast if you read it naively)

- **Never read `payload/**/*.b64` into context.** ~45 KB of base64 ≈ 15k tokens of noise, and
  base64 tokenizes badly. To inspect logic, decode to the scratchpad first, then `grep`/`sed -n`
  the decoded `.py`. To edit, change the source `.py` and re-encode — never hand-edit a blob.
- **`scripts/newyorker_tables_for_two_audit.py` is ~37 KB (~10k tokens).** Locate with `grep -n`,
  then read only the range you need with `sed -n 'A,Bp'`. Don't `cat` it.
- **Never paste workflow logs wholesale.** Pull the failing step with `grep -n -A5 -B5`.
- Reach for `git diff`/`git show` over re-reading whole files you already changed.

## Working rules

- Answer from the smallest slice of the repo that settles the question; don't pre-read
  "for context". Every file read is re-sent on every later turn in the session.
- One task per session. `/clear` between unrelated tasks — a long session re-bills its whole
  history each turn.
- Subagents and workflows each carry their own context. Use them only for genuine fan-out
  (many files, many independent checks), not to answer a single question.
- Report results plainly; skip restating the diff in prose.

Per-model cost tuning and the recommended user-level settings: `docs/claude-usage-tuning.md`
(not auto-loaded — read it only when tuning).
