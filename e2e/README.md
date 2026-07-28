# E2E harness

Automated end-to-end testing of the **shipped** conversion path (`pdf2zotero.convert_one`).

**Scope:** live corpus is **articles / preprints** (Europe PMC OA + arXiv). Book and report contracts are covered by deterministic unit fixtures in `tests/test_pdf2zotero.py`, not by expanding the OA harvest.

## Sources (open / free-to-download scholarly PDFs)

| Source | Policy note |
|--------|-------------|
| [Europe PMC](https://europepmc.org/) license-filtered OA first | Prefer `OPEN_ACCESS:y AND HAS_PDF:y` with CC-style license filter; broader OA fallback is **explicitly marked** on items |
| [arXiv](https://arxiv.org/) API PDFs (HTTPS) | Freely downloadable preprints (per-paper license on arXiv) |

PDFs are **not** committed to git. Cache: `e2e/corpus/` (gitignored).

## Commands (from repo root)

```bash
# GROBID must be up: curl -s http://localhost:8070/api/isalive

python3 e2e/harness.py probe
python3 e2e/harness.py smoke --scratch /path/to/scratch
python3 e2e/harness.py all --target 250 --scratch /path/to/scratch

# Or stepwise:
python3 e2e/harness.py build-manifest --target 250
python3 e2e/harness.py download --limit 250
python3 e2e/harness.py run --limit 250
python3 e2e/harness.py assess --scratch /path/to/scratch
```

## Exit codes (fail-closed)

| Code | Meaning |
|------|---------|
| `0` | Success / gates passed |
| `1` | Conversion or gate failure (including **zero PDFs**) |
| `2` | Environment failure (GROBID down, etc.) |

### Gates

| Command | Gate |
|---------|------|
| `run` | Nonzero PDF set required; `n_ok > 0` |
| `smoke` | Fresh results under scratch (never reuses stale summaries); GROBID down → exit `2`; ≥1 valid conversion |
| `all` | Propagates child exit codes; ≥**90%** of target corpus run; ≥**95%** valid conversions; zero invariant breaches |

### Valid result

A conversion counts as OK only if the `.bib` has:

- an `@…{…}` entry,
- the **exact** expected Zotero `file` field for that PDF (`:{abs}:application/pdf`),
- and, on the DOI path, a `doi` field.

## Provenance

Every `summary.json` includes a `provenance` object with:

- `git_sha` / `git_dirty`
- `python_version`
- `grobid_version` (from `/api/version` when reachable)
- `manifest_digest` (SHA-256 of the manifest file)
- `argv` / `args`
- `started_at` / `finished_at` (UTC ISO-8601)

## Outputs

| Path | Content |
|------|---------|
| `e2e/results/*/results.jsonl` | Per-document outcomes |
| `e2e/results/*/summary.json` | Aggregates + provenance (+ gates for `all`) |
| `e2e/results/*/assessment.md` | Human assessment |
| smoke: `{scratch}/results/` | Isolated per-run smoke results (not shared stale dir) |
| scratch `e2e-batch-summary.json` / `e2e-assessment.md` | Copied summary for verification |

Scoring uses real `.bib` content — not “process exited 0” alone.
