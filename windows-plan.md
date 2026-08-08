# Windows support plan — pdf2zotero

**Status:** ready to execute  
**Goal-compatible:** yes — thin stdlib layer; product success = Zotero parent item + PDF child via BibTeX import  
**Constraint:** no live Windows machine available for end-to-end Zotero testing; verification relies on synthetic path tests + existing Mac/Linux checklist  

This document is the design + **PR Plan** for making pdf2zotero usable on Windows without regressing macOS/Linux.

---

## Product goal (unchanged)

| Done | Not done |
|------|----------|
| Parent item in Zotero (title, authors, year, DOI if any) | Only a `.bib` on disk |
| PDF as **child attachment** under that item | Metadata-only entry |

Stack remains:

1. **GROBID** — understand the PDF (TEI)  
2. **doi.org / Crossref** — authoritative record when DOI exists (optional with `--no-doi-lookup`)  
3. **BibTeX + `file` field** — Zotero-importable package  
4. **Zotero** — user runs **File → Import… → A file**  

pdf2zotero must **not** grow into a PDF parser, metadata DB, or Zotero plugin. No new runtime pip deps. MIT license unchanged.

---

## Problem statement

Today the repo is **macOS/Linux-first**:

| Gap | Evidence |
|-----|----------|
| Install docs assume Homebrew, Colima, bash, `chmod +x`, `~/bin` | `PREREQUISITES.md`, `GETTING_STARTED.md`, `README.md` |
| GROBID helper is bash-only | `scripts/setup-grobid.sh` (`pipefail`, arrays, Colima auto-start) |
| No Windows section / PowerShell helper | Layout lists only `setup-grobid.sh` |
| Windows PDF paths break `file` field | `zotero_file_field` uses `Path.resolve()` raw; `bib_escape` turns `\` into `\textbackslash{}` |
| Tests only use POSIX paths | `tests/test_pdf2zotero.py`, webui fixtures use `/tmp/…` |

Without path normalization, a Windows absolute path like  
`C:\Users\Ada\paper.pdf` becomes unusable after `bib_escape` (backslashes rewritten). That undermines the product goal on Windows even if GROBID and CLI otherwise work.

---

## Non-negotiables (from AGENTS.md)

- Stdlib only for `pdf2zotero.py` / `webui.py`.  
- Prefer DOI BibTeX; always attach local PDF via Zotero-compatible `file` field **including after DOI lookup**.  
- Public CLI stable unless intentional + documented.  
- Mac recipes stay intact — **branch by platform in docs**, do not replace Homebrew/Colima.  
- Do not claim pip install or bundled GROBID.  
- Verification before merge:  
  1. `python3 -m py_compile pdf2zotero.py webui.py e2e/harness.py`  
  2. `python3 -m unittest discover -s tests -v`  
  3. `python3 -m unittest e2e.test_harness_unit -v`  
- No hardcoding machine-specific paths in tests/docs.

---

## Key decisions

### K1 — Path form in `file` field

**Decision:** Normalize absolute PDF paths to **POSIX-style separators** (forward slash) **before** `bib_escape`, and keep the existing shape:

```text
:{absolute_path}:application/pdf
```

Examples (synthetic):

| Platform | After normalization |
|----------|---------------------|
| macOS/Linux | `:/Users/ada/paper.pdf:application/pdf` (unchanged behavior) |
| Windows | `:C:/Users/Ada/paper.pdf:application/pdf` |

**Rationale:**

- Stops `bib_escape` from destroying Windows paths (`\` → `\textbackslash{}`).  
- Forward slashes are accepted by most Windows APIs and by JabRef/Zotero-style file fields.  
- Drive-letter colon stays inside the path segment; importers that split on `:` typically treat first empty field as description, last as mimetype, middle (rejoined) as path.  
- **Uncertainty:** live Zotero Windows import of this shape was **not** verified here. Docs must keep the existing fallback: if import does not attach the PDF, **drag PDF onto the parent item** (always works).

**Implementation sketch** (stdlib only):

```python
def zotero_file_field(pdf_path: Path) -> str:
    """JabRef/Zotero file attachment value: :/abs/path:application/pdf"""
    # resolve() for absolute, real path; as_posix() so Windows \ never hits bib_escape
    abs_posix = pdf_path.resolve().as_posix()
    return f":{abs_posix}:application/pdf"
```

On POSIX, `as_posix()` is a no-op for separators → **no Mac/Linux behavioral change**.

### K2 — Do not over-escape the path for drive letters

**Decision:** Do **not** invent backslash-escaping of the drive colon (e.g. `C\:`) unless unit tests + documented Zotero behavior later require it. Prefer simple `C:/…` form.

**Rationale:** Minimal change; matches common BibTeX practice; drag-and-drop remains the guaranteed attachment path.

### K3 — Windows install path: Docker Desktop only (not Colima)

**Decision:** Document **Docker Desktop for Windows** as the supported container runtime. Do not document Colima as a Windows path.

**Rationale:** Colima is macOS/Linux; repo already documents Docker Desktop as path A. Same pinned image: `grobid/grobid:0.9.0-crf` (optional `--full`).

### K4 — Python on Windows: document `python` and `py -3`

**Decision:** Docs standardize examples as:

```powershell
python pdf2zotero.py paper.pdf
# or, if the launcher is preferred:
py -3 pdf2zotero.py paper.pdf
```

Note that `python3` may be missing on stock Windows installs; prefer `python` / `py -3` after python.org installer with “Add python.exe to PATH”.

**Rationale:** Repo shebangs stay `#!/usr/bin/env python3` (Unix). Windows users invoke the interpreter explicitly — no shebang dependency.

### K5 — PowerShell GROBID helper (parity, not rewrite of bash)

**Decision:** Add `scripts/setup-grobid.ps1` with the same commands: `up`, `status`, `down`, `purge`, optional `-Full`.

- Same image tags and container name defaults as the bash script.  
- Same port 8070 / isalive check.  
- **No Colima auto-start** on Windows — fail with a clear message if Docker daemon is down.  
- Prefer `curl.exe` (ships with modern Windows) for isalive; fall back to `Invoke-WebRequest` if needed.

**Rationale:** Native Windows UX without forcing WSL/Git Bash. Keep `setup-grobid.sh` unchanged for Mac/Linux.

### K6 — Documentation strategy: additive sections

**Decision:** Add **Windows** subsections / columns to existing docs; do not fork the entire install guide into a separate tree that diverges.

| File | Windows work |
|------|----------------|
| `PREREQUISITES.md` | New section: Windows install order (Python, Docker Desktop, GROBID, Zotero, Git) |
| `GETTING_STARTED.md` | Note PowerShell; CLI/webui invoke; Finder → Explorer wording; link official Zotero pages |
| `README.md` | One “Windows” bullet in prerequisites / quick start pointer |
| `GUIDE.md` | Optional one-liner that `file` uses POSIX separators for cross-platform BibTeX |

Update **PREREQUISITES first**, then GETTING_STARTED, then README pointers (per AGENTS.md).

### K7 — Verification without a Windows machine

**Decision:** Merge criteria = Mac/Linux compile + unittest **plus** synthetic Windows-path unit tests that do not require `os.name == "nt"`.

Optional later (not blocking): GitHub Actions `windows-latest` job for `py_compile` + unittest only (no Docker GROBID e2e on CI unless someone volunteers maintainership).

### K8 — Out of scope

- WSL-as-primary path (may work for bash script; optional note only, not required).  
- Chocolatey/Scoop/winget package recipes beyond “optional if you already use them”.  
- Zotero Web API push (still File → Import).  
- New pip dependencies, Flask/FastAPI/React.  
- Changing public CLI flags unless needed (prefer none).  
- Replacing Mac Homebrew/Colima docs.

---

## Current code risk (detail)

```python
# pdf2zotero.py today
def bib_escape(value: str) -> str:
    return value.replace("\\", r"\textbackslash{}")  # destroys Windows paths
    # ... braces, &, %, #

def zotero_file_field(pdf_path: Path) -> str:
    return f":{pdf_path.resolve()}:application/pdf"  # backslashes on Windows
```

Both DOI path (`attach_file_to_bibtex`) and local fallback (`fallback_bibtex`) use this. Fixing `zotero_file_field` alone is sufficient if it never emits `\`.

---

## Target Windows user journey

### One-time install

1. **Python 3.9+** from [python.org](https://www.python.org/downloads/)  
   - Check “Add python.exe to PATH”  
   - Verify: `python --version` or `py -3 --version`  
2. **Docker Desktop for Windows**  
   - Install, start, wait until engine is running  
   - Verify: `docker version` / `docker run --rm hello-world`  
3. **Git** (if cloning) — [git-scm.com](https://git-scm.com/) or GitHub Desktop  
4. Clone repo:

   ```powershell
   git clone https://github.com/jensabrahamsson/pdf2zotero.git
   cd pdf2zotero
   ```

5. **GROBID:**

   ```powershell
   .\scripts\setup-grobid.ps1 up
   # or manual:
   docker run -d --name grobid --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-crf
   curl.exe -s http://127.0.0.1:8070/api/isalive
   ```

6. **Zotero desktop** — [zotero.org/download](https://www.zotero.org/download/)

### Everyday use

```powershell
# Terminal 1: GROBID up (if not already)
.\scripts\setup-grobid.ps1 up

# Terminal 2: convert
python pdf2zotero.py "C:\Users\Ada\Documents\paper.pdf"
# → paper.bib next to the PDF

# or web UI
python webui.py
# → http://127.0.0.1:8765/
```

### Into Zotero

Same as Mac (official Zotero docs):

1. **File → Import… → A file** → select `.bib`  
2. If no PDF child → drag PDF onto parent item (Explorer → Zotero)  
3. Success = parent + PDF attachment  

Official links (already in GETTING_STARTED):

- [Importing standardized formats](https://www.zotero.org/support/kb/importing_standardized_formats)  
- [Attaching files](https://www.zotero.org/support/attaching_files)  

---

## Testing strategy (no Windows host)

### Required unit tests (run on Mac/Linux CI)

Add pure tests that **construct** Windows-like path strings without needing a real NT filesystem where possible:

1. **`zotero_file_field` uses forward slashes**  
   - On any platform: after `resolve()`, field must not contain `\`.  
   - Optionally mock/patch `Path.resolve` to return a path with Windows-style string, or use a helper that accepts a string path for testing.

2. **`bib_escape` does not mangle normalized file fields**  
   - Input path with backslashes **before** normalization would break; assert the public API (`zotero_file_field` → `attach_file_to_bibtex`) never writes `\textbackslash{}` into `file = {…}` for a path that had only path separators as backslashes.

3. **Drive-letter shape**  
   - Expected: starts with `:`, contains `C:/` (or similar), ends with `:application/pdf`.  
   - Use synthetic string helper if `Path` on POSIX cannot represent drive letters cleanly.

Recommended helper (test-only or production-small):

```python
def format_zotero_file_value(absolute_posix_path: str) -> str:
    return f":{absolute_posix_path}:application/pdf"
```

Keep production API as `zotero_file_field(Path)`; tests can also call an internal normalizer if extracted.

4. **Existing attach tests** still pass for brace and quote DOI forms.

5. **No regression:** `file` field still present after DOI attach and local fallback.

### Existing checklist (must stay green)

```bash
python3 -m py_compile pdf2zotero.py webui.py e2e/harness.py
python3 -m unittest discover -s tests -v
python3 -m unittest e2e.test_harness_unit -v
```

### Manual Windows checklist (human with a PC later)

Document in PREREQUISITES or GETTING_STARTED as “Windows smoke checklist (manual)”:

| # | Check |
|---|--------|
| 1 | `python --version` ≥ 3.9 |
| 2 | `docker info` OK |
| 3 | isalive → true |
| 4 | Convert one PDF → `.bib` with `file = {:C:/…:application/pdf}` (forward slashes) |
| 5 | Zotero File → Import `.bib` |
| 6 | PDF child present or drag-and-drop works |
| 7 | Web UI loads, converts, writes under `%USERPROFILE%\Downloads\pdf2zotero\` |

---

## Documentation outline (content to add)

### PREREQUISITES.md — “Windows”

Ordered install:

0. Optional: winget/choco notes (one line each, not required)  
1. Python from python.org (+ PATH + `py` launcher)  
2. Docker Desktop for Windows (WSL2 backend note if Docker docs require it)  
3. GROBID via `setup-grobid.ps1` or `docker run …`  
4. Zotero desktop  
5. Network / offline flag  
6. Clone repo  

Done-when checks mirrored from Mac table.

### GETTING_STARTED.md

- Intro: “Terminal (macOS), shell (Linux), **PowerShell or Windows Terminal (Windows)**”  
- Everyday CLI/webui with `python` examples  
- Zotero steps: Finder → **File Explorer** where relevant  
- Keep official Zotero menu names linked  

### README.md

- Prerequisites table row or note for Windows  
- Quick start: “Windows users: see PREREQUISITES (Windows) + `setup-grobid.ps1`”  

### AGENTS.md layout

- Add `scripts/setup-grobid.ps1` and `windows-plan.md` to the layout tree if still relevant after implementation (or drop plan from layout once done).

---

## Risk register

| Risk | Mitigation |
|------|------------|
| Zotero Windows ignores `file` with `C:/…` | Document drag-and-drop as guaranteed path (already true on all platforms) |
| Zotero splits on drive colon incorrectly | Prefer `as_posix()`; if reports come in, consider empty-description + quoted field research; unit tests lock current contract |
| `python3` missing on Windows | Document `python` / `py -3` |
| PowerShell execution policy blocks `.ps1` | Document `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` or `powershell -File …` |
| Docker Desktop not running | Clear error from ps1 (no Colima fallback) |
| Mac regression on `as_posix()` | Identical separators on POSIX; full unittest suite |
| Scope creep (WSL packaging, installers) | Explicit out of scope |

---

## Success criteria

1. On Mac/Linux: all existing tests pass; `file` fields unchanged in shape for POSIX paths.  
2. Synthetic Windows path tests pass without a Windows host.  
3. Windows user can follow PREREQUISITES + GETTING_STARTED in PowerShell and produce a `.bib` with a forward-slash absolute `file` field.  
4. PowerShell GROBID helper supports up/status/down/purge with pinned 0.9.0 images.  
5. No pip deps; CLI flags stable; Mac docs still valid.  

---

## Open questions (resolved for this plan)

| Question | Resolution |
|----------|------------|
| Require live Windows CI now? | **No** — optional follow-up PR. |
| Support Colima on Windows? | **No**. |
| Change `bib_escape` globally to skip path separators? | **No** — normalize paths before escape instead. |
| WSL primary? | **Optional note only**; native Windows path is Docker Desktop + PowerShell. |

---

## PR Plan

Executable by `/execute-plan windows-plan.md`. Each PR is independently reviewable. Merge gates: AGENTS verification checklist on Mac/Linux.

### PR 1: Normalize PDF paths for Zotero `file` field

- **Files/components affected:** `pdf2zotero.py`, `tests/test_pdf2zotero.py`, optionally `e2e/test_harness_unit.py` if assertions assume separator form  
- **Dependencies:** None  
- **Description:**  
  - Change `zotero_file_field` to use `pdf_path.resolve().as_posix()` (or equivalent) so the `file` value never contains backslashes.  
  - Keep format `:{abs}:application/pdf`.  
  - Ensure DOI path (`attach_file_to_bibtex`) and local fallback both benefit (they already call this helper).  
  - Add unit tests: no `\` in field; no `\textbackslash{}` in emitted `file = {…}` for Windows-like absolute paths (synthetic); POSIX path tests still pass; brace/quote attach still works.  
  - Do not change public CLI.  
  - Verify: `py_compile` + `unittest discover -s tests` + `e2e.test_harness_unit`.

### PR 2: PowerShell GROBID helper

- **Files/components affected:** `scripts/setup-grobid.ps1`, `scripts/setup-grobid.sh` (only if shared constants need a one-line comment cross-ref — prefer **no** bash changes)  
- **Dependencies:** None (can land in parallel with PR 1; docs PR depends on both)  
- **Description:**  
  - Implement `up` / `status` / `down` / `purge` parity with bash script:  
    - default image `grobid/grobid:0.9.0-crf`  
    - `-Full` → `grobid/grobid:0.9.0-full`  
    - container name `grobid` (or env override if bash has `GROBID_NAME`)  
    - port 8070  
    - `docker run -d --name … --init --ulimit core=0 -p 8070:8070`  
    - wait loop until isalive contains `true`  
  - If Docker daemon unreachable: print clear error (start Docker Desktop); **do not** attempt Colima.  
  - Use `curl.exe` when available for health checks.  
  - Script header comment with usage examples for PowerShell.  
  - No change to Python runtime.  
  - Verify: script is valid PowerShell syntax review; cannot run Docker on Mac CI for this script — document manual check; ensure bash script still works unchanged.

### PR 3: Windows documentation

- **Files/components affected:** `PREREQUISITES.md`, `GETTING_STARTED.md`, `README.md`, optionally `GUIDE.md`, `AGENTS.md` (layout line for `.ps1`)  
- **Dependencies:** PR 1, PR 2 (so docs describe real path format and real `setup-grobid.ps1`)  
- **Description:**  
  - **PREREQUISITES.md first:** full Windows install order (Python, Docker Desktop, GROBID via ps1 or docker run, Zotero, Git, network/offline). Done-when checks. Execution policy note for `.ps1`.  
  - **GETTING_STARTED.md:** PowerShell everyday CLI/webui; Explorer wording for drag-and-drop; keep official Zotero links; mention forward-slash `file` field example for Windows.  
  - **README.md:** short Windows pointer; do not remove Mac quick start.  
  - **GUIDE.md (optional):** note `as_posix()` / cross-platform `file` field.  
  - **AGENTS.md:** layout entry for `scripts/setup-grobid.ps1`; optional mention that Windows path normalization is required for `file` field.  
  - Link only real Zotero support URLs (do not invent menu names).  
  - No machine-specific absolute paths in docs (use `C:\Users\…` placeholders carefully; prefer generic examples).  
  - Verify: doc-only PR; still run compile+unittest to ensure tree is clean.

### PR 4: Optional CI on `windows-latest` (non-blocking follow-up)

- **Files/components affected:** `.github/workflows/ci.yml`  
- **Dependencies:** PR 1 (path tests should run on Windows runner too)  
- **Description:**  
  - Add a job (or matrix OS) for `windows-latest` with Python 3.12 (or same matrix subset): `py_compile` + `unittest discover -s tests` + harness unit tests.  
  - **Do not** require Docker/GROBID on the Windows runner.  
  - Keep existing `ubuntu-latest` jobs.  
  - Mark optional: can be deferred if CI minutes or flake risk is a concern; not required for “Windows docs + path fix” ship.  

---

## Suggested merge order

```text
PR1 (path fix + tests) ──┐
                         ├──► PR3 (docs)
PR2 (setup-grobid.ps1) ──┘
                              └──► PR4 (optional CI)
```

PR1 and PR2 are independent (level 0). PR3 depends on both. PR4 depends on PR1 only (or PR1+PR3 if docs mention CI).

---

## Implementation notes for agents

1. Prefer pure helpers and synthetic path tests — no live GROBID required for PR1.  
2. Do not add `requirements.txt` for the main app.  
3. Do not force-push `main`.  
4. When documenting Zotero UI, link `https://www.zotero.org/support/…` only.  
5. After PR1, confirm DOI path still calls `attach_file_to_bibtex` and still emits `file`.  
6. After docs, Mac install path must still be the primary happy path in PREREQUISITES.  

---

## Manual validation script (for a Windows volunteer)

```powershell
# After PR1–PR3 merged / branch checked out
python -m py_compile pdf2zotero.py webui.py e2e/harness.py
python -m unittest discover -s tests -v
python -m unittest e2e.test_harness_unit -v

docker info
.\scripts\setup-grobid.ps1 up
curl.exe -s http://127.0.0.1:8070/api/isalive

python pdf2zotero.py .\some-open-access.pdf
# Open the .bib: file = {:C:/.../some-open-access.pdf:application/pdf}
# Zotero: File → Import → A file → .bib; attach PDF if needed
```

---

## Summary

Windows support is **feasible and goal-compatible** without expanding product scope: fix path emission for the `file` field, add a PowerShell GROBID helper, and document Docker Desktop + python.org + Zotero import. Mac/Linux behavior and docs remain first-class. Live Zotero-on-Windows attachment of the `file` field is treated as best-effort; drag-and-drop remains the guaranteed PDF step on every platform.
