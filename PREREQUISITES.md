# Prerequisites

Everything you need **before** running `pdf2zotero.py` or `webui.py`.  
After this, continue with **[GETTING_STARTED.md](GETTING_STARTED.md)** (convert → import into Zotero).

---

## Overview

| # | Prerequisite | Required? | Role | Links |
|---|--------------|-----------|------|--------|
| 0 | **[Homebrew](https://brew.sh/)** (macOS recommended) | Strongly recommended on Mac | Installs Python, Docker/Colima, Git, … | [brew.sh](https://brew.sh/) · [docs](https://docs.brew.sh/) |
| 1 | **Python 3.9+** | Yes | Runs pdf2zotero and the web UI | [python.org](https://www.python.org/downloads/) · [status of Python versions](https://devguide.python.org/versions/) · [Homebrew `python@3.12`](https://formulae.brew.sh/formula/python@3.12) |
| 2 | **Container runtime** | Yes* | Runs GROBID | *or host GROBID another way |
| 2a | **Docker Desktop** | One of 2a/2b (required path on **Windows**) | Common GUI on macOS / Windows | [Docker Desktop](https://www.docker.com/products/docker-desktop/) · [Homebrew cask](https://formulae.brew.sh/cask/docker-desktop) · [Windows install](https://docs.docker.com/desktop/setup/install/windows-install/) |
| 2b | **Colima + Docker CLI** | One of 2a/2b (macOS/Linux) | Lighter alternative | [Colima](https://github.com/abiosoft/colima) · [Homebrew `colima`](https://formulae.brew.sh/formula/colima) · [Homebrew `docker`](https://formulae.brew.sh/formula/docker) |
| 3 | **GROBID** | Yes | Reads scholarly PDFs (HTTP :8070) | [GROBID project](https://github.com/kermitt2/grobid) · [GROBID Docker guide](https://grobid.readthedocs.io/en/latest/Grobid-docker/) · [Docker Hub `grobid/grobid`](https://hub.docker.com/r/grobid/grobid) |
| 4 | **Zotero desktop** | For the end goal | Your library | [Download](https://www.zotero.org/download/) · [Support](https://www.zotero.org/support) |
| 5 | **Network (HTTPS)** | Usual case | Best metadata | [doi.org](https://www.doi.org/) · [Crossref API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) |

pdf2zotero itself needs **no [`pip`](https://pip.pypa.io/) install**. Only the [Python standard library](https://docs.python.org/3/library/).

**Platform paths in this file:**

| OS | Install path |
|----|----------------|
| **macOS / Linux** | Sections 0–6 below (Homebrew / Colima or Docker Desktop) — primary happy path |
| **Windows** | [Windows install order](#windows-install-order) — Docker Desktop + PowerShell helper |

---

## 0. Homebrew (macOS)

[Homebrew](https://brew.sh/) is the usual package manager on Mac. Most install commands below use `brew`.

### 0.1 Check

```bash
brew --version
which brew
```

Typical path on Apple Silicon: `/opt/homebrew/bin/brew`  
On Intel Macs often: `/usr/local/bin/brew`

### 0.2 Install Homebrew (if missing)

Official one-liner from [https://brew.sh/](https://brew.sh/):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow the script’s on-screen notes (especially **“Next steps”** to put `brew` on your `PATH`).

Docs:

- [Homebrew homepage](https://brew.sh/)  
- [Homebrew documentation](https://docs.brew.sh/)  
- [Installation](https://docs.brew.sh/Installation)  
- [FAQ](https://docs.brew.sh/FAQ)  

### 0.3 After install (Apple Silicon)

If `brew` is not found in a new terminal:

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
brew --version
```

### 0.4 Useful Homebrew commands

```bash
brew update                 # refresh package index
brew search python          # find formulae
brew info python@3.12       # details / caveats
brew install <formula>      # install a formula
brew install --cask <app>   # install a GUI app (cask)
```

- Formulae catalogue: [formulae.brew.sh](https://formulae.brew.sh/)  
- Casks (GUI apps): [formulae.brew.sh/cask](https://formulae.brew.sh/cask/)  

### 0.5 Done when

```bash
brew --version
# e.g. Homebrew 4.x / 5.x / 6.x
```

---

## 1. Python 3.9+

### What you need

| | Version | Link |
|--|---------|------|
| Minimum (compat floor) | **3.9** (EOL — still supported here until a breaking bump) | [What’s new in 3.9](https://docs.python.org/3/whatsnew/3.9.html) · [version status](https://devguide.python.org/versions/) |
| Recommended | **3.11–3.14** | [python.org downloads](https://www.python.org/downloads/) |
| Homebrew formula | `python@3.12` (or newer) | [formulae.brew.sh/formula/python@3.12](https://formulae.brew.sh/formula/python@3.12) |

### Check

```bash
python3 --version
which python3
```

Use **`python3`**, not bare `python` ([PEP 394](https://peps.python.org/pep-0394/)).

### Install with Homebrew (macOS)

```bash
brew update
brew install python@3.12
python3 --version
```

If `python3` is still old, follow `brew info python@3.12` “Caveats” (PATH), or:

```bash
$(brew --prefix python@3.12)/bin/python3 --version
```

### Install without Homebrew

- macOS/Windows/Linux installers: [python.org/downloads](https://www.python.org/downloads/)  
- Linux (Debian/Ubuntu example): `sudo apt update && sudo apt install python3` (ensure ≥ 3.9)  
- Docs: [Using Python on Unix](https://docs.python.org/3/using/unix.html)  
- **Windows:** see [Windows install order → Python](#w1-python-39-from-pythonorg) (`python` / `py -3`; `python3` may be missing)

### Done when

```bash
python3 -c "import sys; assert sys.version_info >= (3, 9); print('OK', sys.version)"
```

On Windows (PowerShell), use `python` or `py -3` instead of `python3` if needed.

---

## 2. Container runtime (Docker **or** Colima)

GROBID ships as a **container image**. You need a runtime that can `docker pull` / `docker run`.

Pick **one** path:

| Path | Best if… | Links |
|------|----------|--------|
| **A. Docker Desktop** | Official GUI, simple setup | [Product page](https://www.docker.com/products/docker-desktop/) · [Docs](https://docs.docker.com/desktop/) · [Homebrew cask](https://formulae.brew.sh/cask/docker-desktop) |
| **B. Colima + Docker CLI** | No Desktop app; lighter VM | [Colima GitHub](https://github.com/abiosoft/colima) · [Homebrew colima](https://formulae.brew.sh/formula/colima) · [Homebrew docker CLI](https://formulae.brew.sh/formula/docker) · [Docker Engine docs](https://docs.docker.com/engine/) |

---

### Path A — Docker Desktop

#### A1. Install with Homebrew

Cask: [docker-desktop](https://formulae.brew.sh/cask/docker-desktop)

```bash
brew update
brew install --cask docker-desktop
# older docs may say: brew install --cask docker
```

Or install the `.dmg` from [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/).

#### A2. Start Docker Desktop

1. Open **Docker** from Applications.  
2. Wait until it reports **running** (menu bar icon).  
3. Accept first-run prompts / login if asked (login is optional for local images).

Official: [Docker Desktop manual](https://docs.docker.com/desktop/).

#### A3. Verify

```bash
docker version
docker info
```

You need a **Server** section. Client-only errors → Desktop not running.

Engine reference: [docker CLI](https://docs.docker.com/reference/cli/docker/).

#### A4. Done when

```bash
docker run --rm hello-world
```

([hello-world image](https://hub.docker.com/_/hello-world))

---

### Path B — Colima + Docker CLI (no Desktop)

[Colima](https://github.com/abiosoft/colima) runs a Linux VM with Docker (or other runtimes) on macOS/Linux.

#### B1. Install with Homebrew

```bash
brew update
brew install colima docker
```

- [formulae.brew.sh/formula/colima](https://formulae.brew.sh/formula/colima)  
- [formulae.brew.sh/formula/docker](https://formulae.brew.sh/formula/docker) (CLI client only)  
- Optional QEMU extras are handled by Colima/Lima as needed — see [Colima README](https://github.com/abiosoft/colima#readme)

#### B2. Fix credential helper (if pulls fail)

If Docker Desktop was installed before, `~/.docker/config.json` may contain `"credsStore": "desktop"`, which breaks pulls without Desktop.

```bash
# inspect
cat ~/.docker/config.json
```

Remove the `credsStore` / `credHelpers` entries that point at `desktop`, e.g.:

```json
{
  "auths": {}
}
```

Docker config docs: [config.json](https://docs.docker.com/reference/cli/docker/#configuration-files).

#### B3. Start Colima

GROBID needs RAM. Example:

```bash
colima start --cpu 4 --memory 6 --disk 40
```

- [Colima: start options](https://github.com/abiosoft/colima#customizing-the-vm)  
- Lima (under the hood): [lima-vm/lima](https://github.com/lima-vm/lima)

#### B4. Point the Docker CLI at Colima

```bash
docker context use colima
docker info
```

[docker context](https://docs.docker.com/engine/context/working-with-contexts/)

#### B5. Done when

```bash
docker run --rm hello-world
```

#### B6. Daily stop / start

```bash
colima stop
colima start          # reuses previous VM settings
colima status
```

---

## 3. GROBID

**GROBID** ([GitHub: kermitt2/grobid](https://github.com/kermitt2/grobid)) turns scholarly PDFs into structured TEI XML.

Project site / docs:

- [GROBID documentation](https://grobid.readthedocs.io/)  
- [GROBID GitHub](https://github.com/kermitt2/grobid)  
- Training / models overview in the same docs  

pdf2zotero calls (default base `http://localhost:8070`):

| Endpoint | Purpose |
|----------|---------|
| `GET /api/isalive` | Health check |
| `POST /api/processHeaderDocument` | Header/metadata extraction |

Service API (overview): [GROBID service](https://grobid.readthedocs.io/en/latest/Grobid-service/).

You do **not** install GROBID via pip for this project. You run a **container**.

### 3.1 Setup script (recommended)

From the repo root, with Docker Desktop **or** Colima available:

**macOS / Linux** (`scripts/setup-grobid.sh`):

```bash
chmod +x scripts/setup-grobid.sh   # once
./scripts/setup-grobid.sh up       # pull + start + wait until alive
./scripts/setup-grobid.sh status
./scripts/setup-grobid.sh down     # stop container only
./scripts/setup-grobid.sh purge    # stop container + delete GROBID images (frees disk)
```

- Default image: `grobid/grobid:0.9.0-crf` (lighter).  
- Full models: `./scripts/setup-grobid.sh up --full` → `grobid/grobid:0.9.0-full`.  
- Starts Colima automatically if `docker info` fails and `colima` is installed.

**Windows** (`scripts/setup-grobid.ps1`) — Docker Desktop must already be running (no Colima auto-start); run from a local clone of this repo:

```powershell
.\scripts\setup-grobid.ps1 up
.\scripts\setup-grobid.ps1 status
.\scripts\setup-grobid.ps1 down
.\scripts\setup-grobid.ps1 purge
```

- Default image: `grobid/grobid:0.9.0-crf` (lighter).  
- Full models: `.\scripts\setup-grobid.ps1 up -Full` → `grobid/grobid:0.9.0-full`.

If PowerShell blocks script execution:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-grobid.ps1 up
```

Or once per user: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.  
Full Windows install order: [Windows install order](#windows-install-order).

Follow [GROBID Docker](https://grobid.readthedocs.io/en/latest/Grobid-docker/).  
Hub: [grobid/grobid](https://hub.docker.com/r/grobid/grobid).

| Tag | When to use |
|-----|-------------|
| `grobid/grobid:0.9.0-crf` | Default / lighter (CRF models) |
| `grobid/grobid:0.9.0-full` | Full deep-learning models (heavier) |

### 3.2 Manual `docker run` (optional)

Dedicated terminal (leave it open). `--init` and `core=0` match the upstream guide:

```bash
docker run --rm --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-crf
```

On Windows (detached container, same flags as the PowerShell helper):

```powershell
docker run -d --name grobid --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-crf
```

First pull is large. Prefer an **explicit tag**; `latest` is not always published.

### 3.3 Check alive

```bash
curl -s http://localhost:8070/api/isalive
# or: ./scripts/setup-grobid.sh status
```

On Windows PowerShell, prefer `curl.exe` (not the `curl` alias for `Invoke-WebRequest`):

```powershell
curl.exe -s http://127.0.0.1:8070/api/isalive
# or: .\scripts\setup-grobid.ps1 status
```

Expect a body containing `true`.

### 3.4 Apple Silicon / Colima issues

| Symptom | Likely cause | Try |
|---------|--------------|-----|
| `PR_SET_CHILD_SUBREAPER` / tini fatal | Default entrypoint under some VMs | Ensure Docker/Colima is current; script uses `--init` |
| TensorFlow / AVX, never alive | Full DL image under amd64 emulation | Prefer **`0.9.0-crf`** / omit `--full` |

### 3.5 Done when

```bash
curl -s http://localhost:8070/api/isalive
```

---

## 4. Zotero (desktop)

Required for the product goal (library item + PDF). Not required only to *generate* `.bib` files.

| Resource | URL |
|----------|-----|
| Download | [zotero.org/download](https://www.zotero.org/download/) |
| Documentation home | [zotero.org/support](https://www.zotero.org/support) |
| Import BibTeX / formats | [Importing standardized formats](https://www.zotero.org/support/kb/importing_standardized_formats) |
| Add items | [Adding items to Zotero](https://www.zotero.org/support/adding_items_to_zotero) |
| Attach PDFs | [Adding files](https://www.zotero.org/support/attaching_files) |
| Optional: Homebrew cask | [formulae.brew.sh/cask/zotero](https://formulae.brew.sh/cask/zotero) |

Install with Homebrew (optional):

```bash
brew install --cask zotero
```

Or use the official installer from the download page.

---

## 5. Network (usual case)

| Host | Why | Link |
|------|-----|------|
| `https://doi.org/…` | Authoritative BibTeX for a DOI | [doi.org](https://www.doi.org/) · [Content negotiation](https://citation.crosscite.org/docs.html) |
| `https://api.crossref.org/…` | Title/author → DOI search | [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) · [api.crossref.org](https://api.crossref.org/) |

Offline:

```bash
python3 pdf2zotero.py paper.pdf --no-doi-lookup
```

Windows:

```powershell
python pdf2zotero.py paper.pdf --no-doi-lookup
```

(or web UI “Offline mode”).

---

## 6. This repository + Git

| Resource | URL |
|----------|-----|
| GitHub repo | [github.com/jensabrahamsson/pdf2zotero](https://github.com/jensabrahamsson/pdf2zotero) |
| Git (if needed) | [git-scm.com](https://git-scm.com/) · [Homebrew `git`](https://formulae.brew.sh/formula/git) |

```bash
# if git is missing on macOS:
brew install git

git clone https://github.com/jensabrahamsson/pdf2zotero.git
cd pdf2zotero
chmod +x pdf2zotero.py webui.py
```

On Windows (PowerShell; no `chmod` required for `python script.py`):

```powershell
git clone https://github.com/jensabrahamsson/pdf2zotero.git
cd pdf2zotero
```

**No runtime pip dependencies** (stdlib only). A local `.venv` is fine for development and verification; you do not need `pip install -r requirements.txt` for the app itself.

---

## macOS “all via Homebrew” summary

After [Homebrew](https://brew.sh/) is installed:

```bash
brew update

# Python
brew install python@3.12

# Pick ONE container stack:
#   A) Docker Desktop
brew install --cask docker-desktop
#   then open Docker.app from Applications

#   B) Colima + CLI
# brew install colima docker
# colima start --cpu 4 --memory 6 --disk 40
# docker context use colima

# Optional: Zotero + Git
brew install --cask zotero
brew install git

# Then GROBID (needs working docker):
docker run --rm --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-crf
```

Formula / cask index: [formulae.brew.sh](https://formulae.brew.sh/).

---

## Windows install order

Additive path for **Windows**. The macOS/Linux sections above remain the primary happy path; this section does not replace them.

Supported container runtime on Windows: **Docker Desktop** only (not Colima).  
Shell: **PowerShell** or [Windows Terminal](https://learn.microsoft.com/en-us/windows/terminal/).

Optional package managers (not required; use only if you already prefer them):

| Tool | Example |
|------|---------|
| [winget](https://learn.microsoft.com/en-us/windows/package-manager/winget/) | `winget install Python.Python.3.12` · `winget install Docker.DockerDesktop` |
| [Chocolatey](https://chocolatey.org/) | `choco install python docker-desktop` |

### W1. Python 3.9+ from python.org

1. Download the Windows installer from [python.org/downloads](https://www.python.org/downloads/).  
2. During setup, enable **“Add python.exe to PATH”**.  
3. Prefer **3.11–3.14** (3.9 is the compatibility floor).  
4. Docs: [Using Python on Windows](https://docs.python.org/3/using/windows.html).

**Check** (PowerShell):

```powershell
python --version
# or the Windows py launcher:
py -3 --version
```

On many Windows installs **`python3` is missing**; use `python` or `py -3`. The repo shebang (`#!/usr/bin/env python3`) is for Unix — on Windows always invoke the interpreter explicitly:

```powershell
python pdf2zotero.py paper.pdf
py -3 pdf2zotero.py paper.pdf
```

**Done when:**

```powershell
python -c "import sys; assert sys.version_info >= (3, 9); print('OK', sys.version)"
```

### W2. Docker Desktop for Windows

1. Install from [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)  
   (product page: [Docker Desktop](https://www.docker.com/products/docker-desktop/)).  
2. Start **Docker Desktop** and wait until the engine reports **running**.  
3. If the installer requires **WSL 2**, follow Docker’s Windows install docs for the WSL 2 backend.  
4. Login is optional for pulling public images such as `grobid/grobid`.

**Check:**

```powershell
docker version
docker info
docker run --rm hello-world
```

You need a **Server** section from `docker version`. Client-only errors → Desktop not running.

### W3. Git + this repository

Clone before starting GROBID via the helper script (the script lives in `scripts\` inside the repo).

| Resource | URL |
|----------|-----|
| Git for Windows | [git-scm.com](https://git-scm.com/) |
| GitHub repo | [github.com/jensabrahamsson/pdf2zotero](https://github.com/jensabrahamsson/pdf2zotero) |

```powershell
git clone https://github.com/jensabrahamsson/pdf2zotero.git
cd pdf2zotero
```

No `chmod` and no `pip install` for the app (stdlib only).

### W4. GROBID

From the **repo root** (after [W3](#w3-git--this-repository)), with Docker Desktop running:

```powershell
.\scripts\setup-grobid.ps1 up
.\scripts\setup-grobid.ps1 status
```

- Default image: `grobid/grobid:0.9.0-crf` (lighter).  
- Full models: `.\scripts\setup-grobid.ps1 up -Full` → `grobid/grobid:0.9.0-full`.  
- Stop container only: `.\scripts\setup-grobid.ps1 down`  
- Stop + delete images: `.\scripts\setup-grobid.ps1 purge`  

If execution policy blocks `.ps1` scripts:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-grobid.ps1 up
```

Or once for your user account:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**Manual alternative** (does not require the helper script; same image and flags):

```powershell
docker run -d --name grobid --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-crf
```

**Alive check** (use `curl.exe` so PowerShell does not rewrite `curl`):

```powershell
curl.exe -s http://127.0.0.1:8070/api/isalive
# expect a body containing true
```

The PowerShell helper does **not** auto-start Colima or Docker Desktop — start Docker Desktop first.

Follow [GROBID Docker](https://grobid.readthedocs.io/en/latest/Grobid-docker/).  
Hub: [grobid/grobid](https://hub.docker.com/r/grobid/grobid).

### W5. Zotero desktop

| Resource | URL |
|----------|-----|
| Download | [zotero.org/download](https://www.zotero.org/download/) |
| Documentation home | [zotero.org/support](https://www.zotero.org/support) |
| Import BibTeX / formats | [Importing standardized formats](https://www.zotero.org/support/kb/importing_standardized_formats) |
| Attach PDFs | [Adding files](https://www.zotero.org/support/attaching_files) |

Install the desktop app from the download page. Required for the product goal (library item + PDF); not required only to *generate* `.bib` files.

### W6. Network (usual case) / offline

Same hosts as on macOS: [doi.org](https://www.doi.org/) and [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/).

Offline conversion (skips doi.org / Crossref only; does not stop a configured remote GROBID):

```powershell
python pdf2zotero.py paper.pdf --no-doi-lookup
```

### Windows “done when” checks

Mirror of the macOS quick verify:

```powershell
python --version
# or: py -3 --version
docker info | Out-Null; if ($?) { "docker OK" }
curl.exe -s http://127.0.0.1:8070/api/isalive
Get-Item pdf2zotero.py, webui.py, scripts\setup-grobid.ps1
```

| # | Check |
|---|--------|
| 1 | `python --version` (or `py -3 --version`) ≥ 3.9 |
| 2 | `docker info` OK (Docker Desktop running) |
| 3 | isalive body contains `true` |
| 4 | Repo files present (`pdf2zotero.py`, `webui.py`, `scripts\setup-grobid.ps1`) |
| 5 | Zotero desktop installed for import ([download](https://www.zotero.org/download/)) |

Continue with **[GETTING_STARTED.md](GETTING_STARTED.md)** (convert → Zotero **File → Import…** → attach PDF if needed).

---

## Quick verify (all prerequisites)

**macOS / Linux:**

```bash
brew --version          # macOS path
python3 --version
docker info >/dev/null && echo "docker OK"
curl -s http://localhost:8070/api/isalive
ls pdf2zotero.py webui.py
```

**Windows** (PowerShell): see [Windows “done when” checks](#windows-done-when-checks) above.

---

## Minimal “start of day” checklist

**macOS / Linux:**

1. **Homebrew tools available** (`brew`, `python3`, `docker` on `PATH`)  
2. **Runtime up:** Docker Desktop **or** `colima start`  
3. **GROBID up:** `curl -s http://localhost:8070/api/isalive`  
4. **Convert:** [GETTING_STARTED.md](GETTING_STARTED.md)  
5. **Zotero import + PDF attach:** same guide + [Zotero docs](https://www.zotero.org/support)  

**Windows:**

1. **Python on PATH** (`python` or `py -3`)  
2. **Docker Desktop running** (`docker info`)  
3. **GROBID up:** `.\scripts\setup-grobid.ps1 up` then `curl.exe -s http://127.0.0.1:8070/api/isalive`  
4. **Convert:** [GETTING_STARTED.md](GETTING_STARTED.md) (`python pdf2zotero.py …` or `python webui.py`)  
5. **Zotero import + PDF attach:** same guide + [Zotero docs](https://www.zotero.org/support)  

---

## Troubleshooting prerequisites

| Problem | Fix | Link |
|---------|-----|------|
| `brew: command not found` | Install Homebrew; fix PATH | [brew.sh](https://brew.sh/) · [Installation](https://docs.brew.sh/Installation) |
| `python3: command not found` | macOS: `brew install python@3.12`. Windows: use `python` / `py -3` from python.org (+ PATH) | [python@3.12](https://formulae.brew.sh/formula/python@3.12) · [python.org](https://www.python.org/downloads/) |
| `docker: command not found` | Desktop cask **or** `brew install docker colima` (Mac/Linux). Windows: install Docker Desktop | [docker-desktop](https://formulae.brew.sh/cask/docker-desktop) · [Windows install](https://docs.docker.com/desktop/setup/install/windows-install/) |
| Cannot connect to Docker daemon | Start Desktop / `colima start` + `docker context use colima` | [Colima](https://github.com/abiosoft/colima) · [Desktop](https://docs.docker.com/desktop/) |
| `docker-credential-desktop` errors | Edit `~/.docker/config.json`, drop `credsStore: desktop` | [Docker config](https://docs.docker.com/reference/cli/docker/#configuration-files) |
| `grobid:latest` not found | Use pinned tag `0.9.0-crf` or `0.9.0-full` | [grobid/grobid tags](https://hub.docker.com/r/grobid/grobid/tags) · [Docker guide](https://grobid.readthedocs.io/en/latest/Grobid-docker/) |
| tini / AVX / never alive | Prefer CRF image; update Docker/Colima (§3.3) | [GROBID Docker](https://grobid.readthedocs.io/en/latest/Grobid-docker/) |
| Port 8070 busy | `docker ps` → `docker rm -f <id>` | [docker ps](https://docs.docker.com/reference/cli/docker/container/ls/) |
| Zotero missing | Install desktop app | [download](https://www.zotero.org/download/) · [cask](https://formulae.brew.sh/cask/zotero) |
| PowerShell: cannot run `setup-grobid.ps1` | Bypass once, or `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` | [about_Execution_Policies](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies) |
| Windows: `curl` returns unexpected HTML/object | Use `curl.exe` (not the `Invoke-WebRequest` alias) | — |
| Windows: Docker daemon down | Start Docker Desktop; script does not start Colima | [Windows install](https://docs.docker.com/desktop/setup/install/windows-install/) |

---

## Related docs in this repo

| File | Role |
|------|------|
| **[PREREQUISITES.md](PREREQUISITES.md)** (this file) | Homebrew / Windows, Python, Docker/Colima, GROBID, Zotero |
| **[GETTING_STARTED.md](GETTING_STARTED.md)** | Convert + import into Zotero |
| **[README.md](README.md)** | Overview and CLI/web flags |
| **[GUIDE.md](GUIDE.md)** | Architecture and design |
