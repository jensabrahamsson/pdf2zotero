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
| 2a | **Docker Desktop** | One of 2a/2b | Common GUI on macOS | [Docker Desktop](https://www.docker.com/products/docker-desktop/) · [Homebrew cask](https://formulae.brew.sh/cask/docker-desktop) |
| 2b | **Colima + Docker CLI** | One of 2a/2b | Lighter alternative | [Colima](https://github.com/abiosoft/colima) · [Homebrew `colima`](https://formulae.brew.sh/formula/colima) · [Homebrew `docker`](https://formulae.brew.sh/formula/docker) |
| 3 | **GROBID** | Yes | Reads scholarly PDFs (HTTP :8070) | [GROBID project](https://github.com/kermitt2/grobid) · [GROBID Docker guide](https://grobid.readthedocs.io/en/latest/Grobid-docker/) · [Docker Hub `grobid/grobid`](https://hub.docker.com/r/grobid/grobid) |
| 4 | **Zotero desktop** | For the end goal | Your library | [Download](https://www.zotero.org/download/) · [Support](https://www.zotero.org/support) |
| 5 | **Network (HTTPS)** | Usual case | Best metadata | [doi.org](https://www.doi.org/) · [Crossref API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) |

pdf2zotero itself needs **no [`pip`](https://pip.pypa.io/) install**. Only the [Python standard library](https://docs.python.org/3/library/).

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

### Done when

```bash
python3 -c "import sys; assert sys.version_info >= (3, 9); print('OK', sys.version)"
```

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

### 3.1 Official pinned images (preferred)

Follow [GROBID Docker](https://grobid.readthedocs.io/en/latest/Grobid-docker/).  
Hub: [grobid/grobid](https://hub.docker.com/r/grobid/grobid).

| Tag | When to use |
|-----|-------------|
| `grobid/grobid:0.9.0-crf` | Default / lighter (CRF models) |
| `grobid/grobid:0.9.0-full` | Full deep-learning models (heavier) |

Dedicated terminal (leave it open). `--init` and `core=0` match the upstream guide:

```bash
docker run --rm --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-crf
```

Full models:

```bash
docker run --rm --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.0-full
```

First pull is large. Prefer an **explicit tag**; `latest` is not always published.  
(Older third-party tags such as `lfoppiano/grobid:0.8.x` may still work but are **not** the documented default.)

### 3.2 Check alive

New terminal:

```bash
curl -s http://localhost:8070/api/isalive
```

Expect a body containing `true`.

### 3.3 Apple Silicon / Colima issues

| Symptom | Likely cause | Try |
|---------|--------------|-----|
| `PR_SET_CHILD_SUBREAPER` / tini fatal | Default entrypoint under some VMs | Ensure Docker/Colima is current; try `--init` as above |
| TensorFlow / AVX, never alive | Full DL image under amd64 emulation | Prefer **`0.9.0-crf`** (lighter) |

Named container example:

```bash
docker rm -f grobid 2>/dev/null

docker pull grobid/grobid:0.9.0-crf

docker run -d --name grobid --init --ulimit core=0 -p 8070:8070 \
  grobid/grobid:0.9.0-crf
```

```bash
for i in 1 2 3 4 5 6 7 8 9 10; do
  curl -sf http://localhost:8070/api/isalive && break
  sleep 5
done
curl -s http://localhost:8070/api/isalive
docker logs grobid   # if still failing
```

Stop named container:

```bash
docker rm -f grobid
```

### 3.4 Done when

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

## Quick verify (all prerequisites)

```bash
brew --version          # macOS path
python3 --version
docker info >/dev/null && echo "docker OK"
curl -s http://localhost:8070/api/isalive
ls pdf2zotero.py webui.py
```

---

## Minimal “start of day” checklist

1. **Homebrew tools available** (`brew`, `python3`, `docker` on `PATH`)  
2. **Runtime up:** Docker Desktop **or** `colima start`  
3. **GROBID up:** `curl -s http://localhost:8070/api/isalive`  
4. **Convert:** [GETTING_STARTED.md](GETTING_STARTED.md)  
5. **Zotero import + PDF attach:** same guide + [Zotero docs](https://www.zotero.org/support)  

---

## Troubleshooting prerequisites

| Problem | Fix | Link |
|---------|-----|------|
| `brew: command not found` | Install Homebrew; fix PATH | [brew.sh](https://brew.sh/) · [Installation](https://docs.brew.sh/Installation) |
| `python3: command not found` | `brew install python@3.12` | [python@3.12](https://formulae.brew.sh/formula/python@3.12) |
| `docker: command not found` | Desktop cask **or** `brew install docker colima` | [docker-desktop](https://formulae.brew.sh/cask/docker-desktop) · [docker](https://formulae.brew.sh/formula/docker) |
| Cannot connect to Docker daemon | Start Desktop / `colima start` + `docker context use colima` | [Colima](https://github.com/abiosoft/colima) · [Desktop](https://docs.docker.com/desktop/) |
| `docker-credential-desktop` errors | Edit `~/.docker/config.json`, drop `credsStore: desktop` | [Docker config](https://docs.docker.com/reference/cli/docker/#configuration-files) |
| `grobid:latest` not found | Use pinned tag `0.9.0-crf` or `0.9.0-full` | [grobid/grobid tags](https://hub.docker.com/r/grobid/grobid/tags) · [Docker guide](https://grobid.readthedocs.io/en/latest/Grobid-docker/) |
| tini / AVX / never alive | Prefer CRF image; update Docker/Colima (§3.3) | [GROBID Docker](https://grobid.readthedocs.io/en/latest/Grobid-docker/) |
| Port 8070 busy | `docker ps` → `docker rm -f <id>` | [docker ps](https://docs.docker.com/reference/cli/docker/container/ls/) |
| Zotero missing | Install desktop app | [download](https://www.zotero.org/download/) · [cask](https://formulae.brew.sh/cask/zotero) |

---

## Related docs in this repo

| File | Role |
|------|------|
| **[PREREQUISITES.md](PREREQUISITES.md)** (this file) | Homebrew, Python, Docker/Colima, GROBID, Zotero |
| **[GETTING_STARTED.md](GETTING_STARTED.md)** | Convert + import into Zotero |
| **[README.md](README.md)** | Overview and CLI/web flags |
| **[GUIDE.md](GUIDE.md)** | Architecture and design |
