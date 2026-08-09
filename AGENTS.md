# AGENTS.md — conventions for AI coding agents

This file is for automated assistants (and humans) working in this repository.

## Project intent

pdf2zotero is a **thin integration layer**. It must not grow into a PDF parser, a metadata database, or a Zotero plugin.

**Product goal:** get the PDF **into the user’s Zotero library** (item + attachment), not merely extract metadata. BibTeX is the carrier because Zotero imports it via File → Import ([supported formats](https://www.zotero.org/support/kb/importing_standardized_formats)).

When documenting Zotero UI steps, **link Zotero’s official support pages** (`https://www.zotero.org/support/…`) — do not invent menu names. Canonical set: import formats, adding items, attaching files, retrieve PDF metadata (see GETTING_STARTED / README tables).

Core split of responsibility:

1. **GROBID** — understand the PDF (TEI XML).  
2. **doi.org / Crossref** — authoritative bibliographic record when a DOI exists.  
3. **BibTeX + `file` field** — Zotero-importable package (metadata + path to PDF).  
4. **Zotero** — library destination (user runs File → Import…).  

Install stack (Python, Docker/Colima, GROBID, Zotero): [`PREREQUISITES.md`](PREREQUISITES.md).  
User walkthrough (convert → Zotero import → PDF attachment): [`GETTING_STARTED.md`](GETTING_STARTED.md).  
Design rationale and diagrams: [`GUIDE.md`](GUIDE.md).  
Overview / flags: [`README.md`](README.md).

## Prerequisites agents must respect

When running or documenting the tool, assume and verify:

| Need | How to check |
|------|----------------|
| Python ≥ 3.9 (recommend 3.11/3.12) | `python3 --version` — shebang uses `env python3` |
| Script executable bit | `chmod +x pdf2zotero.py` when documenting install |
| GROBID up | `curl -s http://localhost:8070/api/isalive` (or configured `--grobid-url`) |
| Optional doi.org | Network; skip with `--no-doi-lookup` in offline tests |
| No pip deps | `requirements.txt` is intentionally empty (stdlib only). Do not add runtime PyPI packages unless the user explicitly accepts that trade-off |
| GitHub repo name | **`pdf2zotero`** under `jensabrahamsson` — not `zotero` |

Do not claim the project “installs with pip” or bundles GROBID. Document external services as **prerequisites**, not as optional nice-to-haves, except Zotero (optional for generation) and doi.org (optional with `--no-doi-lookup`).

## Non-negotiables

- **Stdlib only** for the main script (`pdf2zotero.py`). No new runtime pip dependencies unless the user explicitly asks and accepts that trade-off.  
- Prefer **DOI BibTeX** over hand-built fields when a DOI is available.  
- When GROBID is thin: merge **PDF Info** and light **filename** cues, then **Crossref** title/author search (author must match when both sides have person-authors; prefer book/monograph for books and report types for reports — never pick a review of the work).  
- Fallback BibTeX types: **`@article`** / **`@book`** / **`@techreport`** from `entry_type` (`article` | `book` | `report`).  
- Always attach the local PDF with a Zotero-compatible `file` field:  
  `:{absolute_path}:application/pdf`  
  including after a successful DOI lookup.  
- Keep the public CLI stable unless the change is intentional and documented in `README.md`.  
- License is **MIT** — do not switch license without an explicit user request.

## Layout

```
pdf2zotero.py      # CLI + conversion library
webui.py           # local drag-and-drop HTTP UI (stdlib)
webui_static/      # index.html, styles.css, app.js
scripts/           # setup-grobid.sh / setup-grobid.ps1 (Docker GROBID)
tests/             # stdlib unittest (pdf2zotero + webui)
e2e/               # live OA harness + harness unit tests
requirements.txt   # intentionally empty (stdlib-only runtime)
.github/           # workflows + dependabot.yml
PREREQUISITES.md   # Python, Docker/Colima, GROBID, Zotero install
GETTING_STARTED.md # convert + how material enters Zotero
README.md          # overview + flag reference
GUIDE.md           # architecture and design
AGENTS.md          # this file
LICENSE            # MIT
.gitignore
```

When changing install requirements, update **PREREQUISITES.md** first.  
When changing convert/import workflow, update **GETTING_STARTED.md** first, then README/GUIDE pointers.

Keep the web UI **stdlib-only** and bound to localhost by default. Reuse `pdf2zotero.convert_one`;
do not reimplement metadata logic in JS. Do not add Flask/FastAPI/React unless the user asks.

## Code style

- Python 3.9+ type hints (`list[str]`, `X | None`, etc.).  
- `from __future__ import annotations` at top of modules.  
- Prefer clear functions over classes, except small dataclasses (`Metadata`).  
- No silent failure of network steps: surface warnings to stderr and fall back when appropriate (DOI fail → GROBID BibTeX).  
- User-visible CLI strings and README may be English; keep error messages consistent with existing tone.

## When changing behaviour

| Change | Also update |
|--------|-------------|
| CLI flags / defaults | `README.md`, module docstring if needed |
| Pipeline / architecture | `GUIDE.md` |
| Agent/process rules | `AGENTS.md` |
| License | `LICENSE`, `README.md` license section |

## Safe experiments

- Prefer pure helpers (`parse_grobid_tei`, `clean_doi`, `attach_file_to_bibtex`, …) that can be exercised with synthetic TEI/XML without a live GROBID.  
- Do not commit generated `*.bib`, `*.tei.xml`, or `__pycache__` (see `.gitignore`).  
- Do not hardcode machine-specific paths in tests or docs.

## What not to do

- Reimplement full bibliographic resolution (Crossref search by title, fuzzy matching, etc.) inside this repo unless requested — that expands scope.  
- Replace GROBID with a second PDF stack without an explicit design decision.  
- Embed API keys or private tokens.  
- Force-push or rewrite published history on `main` without the user asking.  
- Add telemetry or upload PDFs anywhere except the configured GROBID URL and (optional) doi.org GET for BibTeX.

## Verification checklist

Before finishing a change:

1. `python3 -m py_compile pdf2zotero.py webui.py e2e/harness.py`  
2. `python3 -m unittest discover -s tests -v` and `python3 -m unittest e2e.test_harness_unit -v`  
3. Smoke-test pure functions with small TEI fixtures when parse/date/DOI/file logic changes.  
4. Confirm DOI path still runs `attach_file_to_bibtex` (brace and quote forms).  
5. Confirm published-date preference still beats unrelated `@when` on other `<date>` nodes (`imprint_date`).  
6. Confirm output collision refuses to overwrite the source PDF; offline mode makes no doi.org/Crossref calls.  
7. Update docs if user-facing behaviour changed (no default GROBID **0.8.x** recipes).

## Git / GitHub

- Default public identity for this project: **jensabrahamsson**.  
- Prefer small, focused commits with complete-sentence messages.  
- Do not create or push remotes without the user wanting that step (tokens may lack `createRepository`).
