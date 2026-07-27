# E2E harness

Automated end-to-end testing of the **shipped** conversion path (`pdf2zotero.convert_one`).

## Sources (open / free-to-download scholarly PDFs)

| Source | Policy note |
|--------|-------------|
| [Europe PMC](https://europepmc.org/) `OPEN_ACCESS:y AND HAS_PDF:y` | Open-access full text via Europe PMC PDF render |
| [arXiv](https://arxiv.org/) API PDFs | Freely downloadable preprints (per-paper license on arXiv) |

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

## Outputs

| Path | Content |
|------|---------|
| `e2e/results/*/results.jsonl` | Per-document outcomes |
| `e2e/results/*/summary.json` | Aggregates |
| `e2e/results/*/assessment.md` | Human assessment |
| scratch `e2e-batch-summary.json` / `e2e-assessment.md` | Copied summary for verification |

Scoring uses real `.bib` content: `@` entry, `file` field, DOI field, empty-metadata heuristics — not “process exited 0” alone.
