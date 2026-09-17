# AF research runners

Temporary reproducible research workflows used to generate auditable datasets. Generated outputs are downloaded as workflow artifacts; no output dataset is committed to the default branch.

## Layout

- `scripts/` — the Python runners, committed as plain source so they can be reviewed and diffed:
  - `newyorker_tables_for_two_audit.py` — live crawl and verification (audit workflow).
  - `prepare_final_candidates.py` — builds the source-corrected candidate list from the crawl artifact.
  - `nytft_final_verify.py` — constrained final verification of those candidates.
- `payload/repair_v6.py.gz.b64` — the OCR/source repair helper imported by `prepare_final_candidates.py`. This is the only copy and it currently fails gzip's CRC check; the verification workflow stops with a clear error until it is re-encoded from a known-good `repair_v6.py`.
- `.github/actions/setup-nytft/` — shared Python setup used by both workflows.
- `.github/workflows/` — `newyorker_tables_for_two_audit.yml`, `nytft_final_verify.yml`, `cancel-stale-nytft.yml`.

The verification workflow needs the artifact of a recent successful run of the full-audit workflow (`nytft-full-audit.yml`, which lives on branch `nytft-full-audit-20260807`). It uses the latest successful run, or the run ID passed as the `upstream_run_id` dispatch input. Artifacts expire after 7 days.

Scripts read their input and output locations from environment variables (`NYTFT_WORK_ROOT`, `NYTFT_EXHAUSTIVE_ROOT`, `UPSTREAM_ROOT`, `INPUT_B64`, `OUTPUT_DIR`); the workflows show the values used in CI.
