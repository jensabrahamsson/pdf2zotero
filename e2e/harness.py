#!/usr/bin/env python3
"""
E2E harness for pdf2zotero: download open scholarly PDFs, run real convert_one,
score outcomes carefully.

Public/open sources only (Europe PMC open-access full text + arXiv PDFs).
Does not commit PDFs. Stdlib only for the harness (same as converter).

Usage (from repo root):
  python3 e2e/harness.py probe
  python3 e2e/harness.py build-manifest --target 250
  python3 e2e/harness.py download --limit 250
  python3 e2e/harness.py run --limit 250
  python3 e2e/harness.py assess
  python3 e2e/harness.py all --target 250 --scratch DIR
  python3 e2e/harness.py smoke --scratch DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Repo root = parent of e2e/
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pdf2zotero  # noqa: E402

USER_AGENT = "pdf2zotero-e2e/1.0 (scholarly OA testing; +https://github.com/jensabrahamsson/pdf2zotero)"
E2E_DIR = ROOT / "e2e"
DEFAULT_CORPUS = E2E_DIR / "corpus"
DEFAULT_RESULTS = E2E_DIR / "results"
DEFAULT_MANIFEST = E2E_DIR / "manifest.json"

# Fail-closed gates for batch/all runs.
MIN_CORPUS_FRACTION = 0.90
MIN_OK_FRACTION = 0.95
# Distinct exit codes
EXIT_OK = 0
EXIT_FAIL = 1
EXIT_ENV = 2  # GROBID / environment unavailable


@dataclass
class ManifestItem:
    id: str
    source: str  # europepmc | arxiv
    pdf_url: str
    title: str = ""
    license_note: str = ""
    kind_hint: str = "article"  # article | preprint


@dataclass
class RunResult:
    id: str
    source: str
    pdf_path: str
    ok: bool
    error: str = ""
    convert_source: str = ""
    bib_path: str = ""
    bib_bytes: int = 0
    has_at_entry: bool = False
    has_file_field: bool = False
    has_doi_field: bool = False
    entry_type: str = ""
    citation_key: str = ""
    looks_empty_metadata: bool = False
    duration_sec: float = 0.0
    path_class: str = ""  # doi | fallback | fail


def http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_get_json(url: str, timeout: int = 60) -> dict:
    return json.loads(http_get(url, timeout=timeout).decode("utf-8", errors="replace"))


def grobid_alive(grobid_url: str = "http://localhost:8070", timeout: int = 5) -> tuple[bool, str]:
    url = grobid_url.rstrip("/") + "/api/isalive"
    try:
        body = http_get(url, timeout=timeout).decode("utf-8", errors="replace").strip()
        return ("true" in body.lower()), body
    except Exception as exc:
        return False, str(exc)


def grobid_version(grobid_url: str = "http://localhost:8070", timeout: int = 5) -> str:
    url = grobid_url.rstrip("/") + "/api/version"
    try:
        return http_get(url, timeout=timeout).decode("utf-8", errors="replace").strip()
    except Exception as exc:
        return f"unavailable: {exc}"


def git_provenance() -> dict:
    """Return git SHA and dirty flag for the repo root."""
    def _run(args: list[str]) -> str:
        try:
            out = subprocess.check_output(
                args,
                cwd=str(ROOT),
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
            )
            return out.strip()
        except Exception:
            return ""

    sha = _run(["git", "rev-parse", "HEAD"])
    dirty_out = _run(["git", "status", "--porcelain"])
    return {
        "git_sha": sha or "unknown",
        "git_dirty": bool(dirty_out) if sha else None,
    }


def manifest_digest(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_provenance(
    *,
    args: argparse.Namespace | None = None,
    grobid_url: str = "http://localhost:8070",
    manifest_path: Path | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    extra: dict | None = None,
) -> dict:
    prov = {
        **git_provenance(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "grobid_url": grobid_url,
        "grobid_version": grobid_version(grobid_url),
        "manifest_digest": manifest_digest(manifest_path) if manifest_path else "",
        "argv": list(sys.argv),
        "started_at": started_at or datetime.now(timezone.utc).isoformat(),
        "finished_at": finished_at or datetime.now(timezone.utc).isoformat(),
    }
    if args is not None:
        try:
            prov["args"] = {
                k: (str(v) if isinstance(v, Path) else v)
                for k, v in vars(args).items()
                if k != "func"
            }
        except TypeError:
            prov["args"] = {}
    if extra:
        prov.update(extra)
    return prov


def cmd_probe(args: argparse.Namespace) -> int:
    alive, detail = grobid_alive(args.grobid_url)
    print(f"GROBID {args.grobid_url}/api/isalive -> alive={alive} detail={detail!r}")
    try:
        data = http_get_json(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
            + urllib.parse.urlencode(
                {
                    "query": "OPEN_ACCESS:y AND HAS_PDF:y AND SRC:MED",
                    "resultType": "idlist",
                    "pageSize": "1",
                    "format": "json",
                }
            ),
            timeout=30,
        )
        print(f"Europe PMC hitCount={data.get('hitCount')}")
    except Exception as exc:
        print(f"Europe PMC probe failed: {exc}")
    try:
        raw = http_get(
            "https://export.arxiv.org/api/query?search_query=all:physics&start=0&max_results=1",
            timeout=30,
        )
        print(f"arXiv API bytes={len(raw)}")
    except Exception as exc:
        print(f"arXiv probe failed: {exc}")
    return 0 if alive else 2


def _europepmc_rows_to_items(data: dict, *, license_filtered: bool) -> list[ManifestItem]:
    items: list[ManifestItem] = []
    for row in data.get("resultList", {}).get("result") or []:
        pmcid = row.get("pmcid") or ""
        if not pmcid.startswith("PMC"):
            continue
        title = (row.get("title") or "").strip()
        license_note = (row.get("license") or "open_access_europepmc").strip()
        pdf_url = f"https://europepmc.org/articles/{pmcid}?pdf=render"
        filter_tag = "license-filtered" if license_filtered else "oa-fallback"
        items.append(
            ManifestItem(
                id=pmcid,
                source="europepmc",
                pdf_url=pdf_url,
                title=title[:300],
                license_note=(
                    f"Europe PMC OA ({filter_tag}); license={license_note}"
                ),
                kind_hint="article",
            )
        )
    return items


def fetch_europepmc_batch(cursor: str, page_size: int = 100) -> tuple[list[ManifestItem], str]:
    """Prefer license-filtered OA query; fall back to broader OA and mark it."""
    params_strict = {
        "query": (
            "OPEN_ACCESS:y AND HAS_PDF:y AND SRC:MED AND "
            '(LICENSE:cc* OR LICENSE:"cc by" OR LICENSE:"cc0")'
        ),
        "resultType": "core",
        "pageSize": str(page_size),
        "format": "json",
        "cursorMark": cursor,
    }
    params_loose = {
        "query": "OPEN_ACCESS:y AND HAS_PDF:y AND SRC:MED",
        "resultType": "core",
        "pageSize": str(page_size),
        "format": "json",
        "cursorMark": cursor,
    }
    base = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
    data = http_get_json(base + urllib.parse.urlencode(params_strict), timeout=90)
    items = _europepmc_rows_to_items(data, license_filtered=True)
    used_fallback = False
    if len(items) < max(1, page_size // 4):
        data = http_get_json(base + urllib.parse.urlencode(params_loose), timeout=90)
        items = _europepmc_rows_to_items(data, license_filtered=False)
        used_fallback = True
        print(
            "Europe PMC: license-filtered query thin; using broader OA fallback "
            f"(n={len(items)})",
            flush=True,
        )
    next_cursor = data.get("nextCursorMark") or ""
    # Annotate first item note for assess if fallback (summary flag set by caller via items).
    if used_fallback and items:
        items[0].license_note += " [batch:oa-fallback]"
    return items, next_cursor


def fetch_arxiv_batch(start: int, max_results: int = 50, query: str = "all:biology") -> list[ManifestItem]:
    # Be polite to arXiv API
    time.sleep(3)
    url = (
        "https://export.arxiv.org/api/query?"
        + urllib.parse.urlencode(
            {
                "search_query": query,
                "start": str(start),
                "max_results": str(max_results),
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
        )
    )
    raw = http_get(url, timeout=90)
    # Atom namespace
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(raw)
    items: list[ManifestItem] = []
    for entry in root.findall("a:entry", ns):
        id_url = (entry.findtext("a:id", default="", namespaces=ns) or "").strip()
        # http://arxiv.org/abs/2307.02593v2
        m = re.search(r"arxiv\.org/abs/([^/\s]+)", id_url)
        if not m:
            continue
        arxiv_id = m.group(1)
        # PDF without version often redirects; use id as-is
        bare = re.sub(r"v\d+$", "", arxiv_id)
        pdf_url = f"https://arxiv.org/pdf/{bare}"
        title = " ".join((entry.findtext("a:title", default="", namespaces=ns) or "").split())
        items.append(
            ManifestItem(
                id=f"arxiv:{bare}",
                source="arxiv",
                pdf_url=pdf_url,
                title=title[:300],
                license_note="arXiv preprint; free to download (see arxiv.org license per paper)",
                kind_hint="preprint",
            )
        )
    return items


def cmd_build_manifest(args: argparse.Namespace) -> int:
    target = args.target
    items: list[ManifestItem] = []
    seen: set[str] = set()

    # Europe PMC: majority
    epmc_target = max(1, int(target * 0.65))
    cursor = "*"
    pages = 0
    while len([i for i in items if i.source == "europepmc"]) < epmc_target and pages < 40:
        batch, cursor = fetch_europepmc_batch(cursor, page_size=100)
        pages += 1
        if not batch:
            break
        for it in batch:
            if it.id in seen:
                continue
            seen.add(it.id)
            items.append(it)
            if len([i for i in items if i.source == "europepmc"]) >= epmc_target:
                break
        if not cursor or cursor == "*":
            # safety: if API doesn't advance, break
            if pages > 1 and len(batch) < 10:
                break
        print(f"  Europe PMC page {pages}: total items={len(items)}", flush=True)
        time.sleep(0.4)

    # arXiv: rest for diversity
    arxiv_target = target - len(items)
    start = 0
    queries = ["all:physics", "all:biology", "all:cs.LG", "all:math.CO", "all:q-bio"]
    qi = 0
    while len(items) < target and start < 2000:
        q = queries[qi % len(queries)]
        batch = fetch_arxiv_batch(start=start, max_results=50, query=q)
        qi += 1
        start += 50
        if not batch:
            continue
        for it in batch:
            if it.id in seen:
                continue
            seen.add(it.id)
            items.append(it)
            if len(items) >= target:
                break
        print(f"  arXiv start={start} q={q}: total items={len(items)}", flush=True)

    items = items[:target]
    payload = {
        "created": datetime.now(timezone.utc).isoformat(),
        "policy": (
            "Open scholarly PDFs only: Europe PMC OPEN_ACCESS+HAS_PDF full text "
            "and arXiv free PDFs. Not a claim of public-domain for every paper; "
            "sources are free-to-download scholarly outlets suitable for local testing."
        ),
        "count": len(items),
        "items": [asdict(i) for i in items],
    }
    path = Path(args.manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(items)} items -> {path}")
    return 0 if len(items) >= min(target, 10) else 1


def pdf_cache_path(corpus_dir: Path, item: ManifestItem) -> Path:
    safe = re.sub(r"[^\w.\-]+", "_", item.id)
    return corpus_dir / f"{safe}.pdf"


def download_one(item: ManifestItem, dest: Path, timeout: int = 120) -> tuple[bool, str]:
    if dest.exists() and dest.stat().st_size > 2000:
        head = dest.read_bytes()[:5]
        if head.startswith(b"%PDF"):
            return True, "cached"
    last_err = ""
    for attempt in range(1, 5):
        try:
            data = http_get(item.pdf_url, timeout=timeout)
        except urllib.error.HTTPError as exc:
            last_err = f"HTTP Error {exc.code}: {exc.reason}"
            if exc.code in {429, 503}:
                time.sleep(min(60, 5 * attempt * attempt))
                continue
            return False, f"download_error: {last_err}"
        except Exception as exc:
            last_err = str(exc)
            time.sleep(2 * attempt)
            continue
        if not data.startswith(b"%PDF"):
            return False, f"not_pdf content_type_guess size={len(data)} head={data[:40]!r}"
        if len(data) < 2000:
            return False, f"too_small size={len(data)}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(dest)
        return True, f"downloaded bytes={len(data)}"
    return False, f"download_error: {last_err}"


def cmd_download(args: argparse.Namespace) -> int:
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    items = [ManifestItem(**x) for x in manifest["items"]]
    if args.limit:
        items = items[: args.limit]
    corpus = Path(args.corpus)
    corpus.mkdir(parents=True, exist_ok=True)
    ok = 0
    fail = 0
    for i, item in enumerate(items, 1):
        dest = pdf_cache_path(corpus, item)
        success, msg = download_one(item, dest, timeout=args.timeout)
        if success:
            ok += 1
            print(f"[{i}/{len(items)}] OK {item.id} {msg}", flush=True)
        else:
            fail += 1
            print(f"[{i}/{len(items)}] FAIL {item.id} {msg}", flush=True)
        if item.source == "arxiv":
            time.sleep(1.0)  # arXiv courtesy
        else:
            time.sleep(0.45)  # Europe PMC: avoid 429
    print(f"download done ok={ok} fail={fail}")
    return 0 if ok > 0 else 1


def expected_file_field(pdf_path: Path) -> str:
    return pdf2zotero.zotero_file_field(pdf_path)


def classify_bib(bibtex: str, convert_source: str, pdf_path: Path | None = None) -> dict:
    has_at = bool(re.search(r"(?m)^@", bibtex.strip()))
    # Fields may be single-line or multi-line; do not require start-of-line only.
    has_file = bool(re.search(r"(?i)\bfile\s*=", bibtex))
    has_doi = bool(re.search(r"(?i)\bdoi\s*=", bibtex))
    has_title = bool(re.search(r"(?i)\btitle\s*=", bibtex))
    m = re.search(r"(?m)^@(\w+)\{([^,]+),", bibtex.strip())
    if not m:
        m = re.search(r"@(\w+)\{([^,]+),", bibtex)
    entry_type = m.group(1).lower() if m else ""
    key = m.group(2) if m else ""
    looks_empty = bool(key.startswith("unknown") or (not has_title and not has_doi))
    if "DOI metadata" in convert_source:
        path_class = "doi"
    elif convert_source:
        path_class = "fallback"
    else:
        path_class = "fail"

    file_field_exact = False
    if pdf_path is not None and has_file:
        expected = expected_file_field(pdf_path)
        # Brace or quoted form containing the exact Zotero file value.
        file_field_exact = expected in bibtex

    return {
        "has_at_entry": has_at,
        "has_file_field": has_file,
        "has_doi_field": has_doi,
        "entry_type": entry_type,
        "citation_key": key,
        "looks_empty_metadata": looks_empty,
        "path_class": path_class if has_at else "fail",
        "file_field_exact": file_field_exact,
    }


def is_valid_result(meta: dict, convert_source: str) -> bool:
    """A valid conversion: BibTeX entry + exact PDF file field; DOI path needs doi field."""
    if not meta.get("has_at_entry"):
        return False
    if not meta.get("has_file_field") or not meta.get("file_field_exact"):
        return False
    if "DOI metadata" in (convert_source or ""):
        if not meta.get("has_doi_field"):
            return False
    return True


def convert_one_real(
    pdf_path: Path,
    out_dir: Path,
    grobid_url: str,
    timeout: int,
    no_doi_lookup: bool,
) -> RunResult:
    """Invoke the real shipped convert_one path (same as CLI)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    bib_path = out_dir / (pdf_path.stem + ".bib")
    t0 = time.time()
    try:
        source = pdf2zotero.convert_one(
            pdf_path=pdf_path,
            output_path=bib_path,
            grobid_url=grobid_url,
            timeout=timeout,
            no_doi_lookup=no_doi_lookup,
            save_tei=False,
        )
        bibtex = bib_path.read_text(encoding="utf-8") if bib_path.exists() else ""
        meta = classify_bib(bibtex, source, pdf_path)
        ok = is_valid_result(meta, source)
        # Drop helper key not on RunResult dataclass.
        meta.pop("file_field_exact", None)
        return RunResult(
            id=pdf_path.stem,
            source="",
            pdf_path=str(pdf_path),
            ok=ok,
            convert_source=source,
            bib_path=str(bib_path) if bib_path.exists() else "",
            bib_bytes=len(bibtex.encode("utf-8")),
            duration_sec=round(time.time() - t0, 3),
            **meta,
        )
    except Exception as exc:
        return RunResult(
            id=pdf_path.stem,
            source="",
            pdf_path=str(pdf_path),
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
            path_class="fail",
            duration_sec=round(time.time() - t0, 3),
        )


def cmd_run(args: argparse.Namespace) -> int:
    started = datetime.now(timezone.utc).isoformat()
    manifest_path = Path(args.manifest)
    corpus = Path(args.corpus)
    results_dir = Path(args.results)
    results_dir.mkdir(parents=True, exist_ok=True)

    alive, detail = grobid_alive(args.grobid_url)
    probe = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "grobid_url": args.grobid_url,
        "alive": alive,
        "detail": detail,
        "version": grobid_version(args.grobid_url) if alive else "",
    }
    (results_dir / "grobid_probe.json").write_text(
        json.dumps(probe, indent=2) + "\n", encoding="utf-8"
    )
    print(f"GROBID probe: {probe}", flush=True)
    if not alive and not args.allow_no_grobid:
        print("GROBID down; abort run (pass --allow-no-grobid to force).", file=sys.stderr)
        return EXIT_ENV

    items: list[ManifestItem] = []
    if manifest_path.exists():
        man = json.loads(manifest_path.read_text(encoding="utf-8"))
        items = [ManifestItem(**x) for x in man["items"]]
    # Prefer PDFs already on disk if no manifest match
    pdfs: list[tuple[ManifestItem | None, Path]] = []
    if args.pdfs:
        for p in args.pdfs:
            path = Path(p)
            pdfs.append((None, path))
    else:
        for item in items:
            path = pdf_cache_path(corpus, item)
            if path.exists() and path.stat().st_size > 2000:
                pdfs.append((item, path))
        # also any extra PDFs in corpus
        if args.include_orphan_pdfs:
            known = {pdf_cache_path(corpus, i).resolve() for i in items}
            for path in sorted(corpus.glob("*.pdf")):
                if path.resolve() not in known:
                    pdfs.append((None, path))

    if args.limit:
        pdfs = pdfs[: args.limit]

    if not pdfs:
        summary = {
            "n": 0,
            "n_ok": 0,
            "n_fail": 0,
            "n_requested": 0,
            "ok_rate": 0.0,
            "error": "no PDFs to convert",
            "grobid_probe": probe,
            "provenance": build_provenance(
                args=args,
                grobid_url=args.grobid_url,
                manifest_path=manifest_path,
                started_at=started,
            ),
        }
        (results_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (results_dir / "results.jsonl").write_text("", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        print("FAIL: zero PDFs to convert", file=sys.stderr)
        return EXIT_FAIL

    print(f"Running convert on {len(pdfs)} PDFs...", flush=True)
    results: list[RunResult] = []
    for i, (item, pdf_path) in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] convert {pdf_path.name} ...", flush=True)
        r = convert_one_real(
            pdf_path=pdf_path,
            out_dir=results_dir / "bib",
            grobid_url=args.grobid_url,
            timeout=args.timeout,
            no_doi_lookup=args.no_doi_lookup,
        )
        if item:
            r.id = item.id
            r.source = item.source
        results.append(r)
        status = "OK" if r.ok else "FAIL"
        print(
            f"  -> {status} class={r.path_class} src={r.convert_source!r} err={r.error!r}",
            flush=True,
        )

    out_json = results_dir / "results.jsonl"
    with out_json.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

    summary = summarize(results)
    summary["grobid_probe"] = probe
    summary["n_requested"] = len(pdfs)
    summary["provenance"] = build_provenance(
        args=args,
        grobid_url=args.grobid_url,
        manifest_path=manifest_path,
        started_at=started,
    )
    (results_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    if summary.get("n_ok", 0) <= 0:
        return EXIT_FAIL
    return EXIT_OK


def summarize(results: list[RunResult]) -> dict:
    n = len(results)
    n_ok = sum(1 for r in results if r.ok)
    n_fail = sum(1 for r in results if not r.ok)
    n_doi = sum(1 for r in results if r.path_class == "doi")
    n_fallback = sum(1 for r in results if r.path_class == "fallback")
    n_empty_meta = sum(1 for r in results if r.looks_empty_metadata)
    n_file = sum(1 for r in results if r.has_file_field)
    by_source: dict[str, dict] = {}
    for r in results:
        src = r.source or "unknown"
        bucket = by_source.setdefault(src, {"n": 0, "ok": 0, "doi": 0, "fallback": 0, "fail": 0})
        bucket["n"] += 1
        if r.ok:
            bucket["ok"] += 1
        if r.path_class == "doi":
            bucket["doi"] += 1
        elif r.path_class == "fallback":
            bucket["fallback"] += 1
        else:
            bucket["fail"] += 1
    errors: dict[str, int] = {}
    for r in results:
        if r.error:
            key = r.error.split(":")[0][:80]
            errors[key] = errors.get(key, 0) + 1
    return {
        "n": n,
        "n_ok": n_ok,
        "n_fail": n_fail,
        "n_doi": n_doi,
        "n_fallback": n_fallback,
        "n_empty_metadata": n_empty_meta,
        "n_with_file_field": n_file,
        "ok_rate": round(n_ok / n, 4) if n else 0.0,
        "doi_rate": round(n_doi / n, 4) if n else 0.0,
        "by_source": by_source,
        "error_counts": dict(sorted(errors.items(), key=lambda kv: -kv[1])[:20]),
    }


def cmd_assess(args: argparse.Namespace) -> int:
    results_dir = Path(args.results)
    lines = (results_dir / "results.jsonl").read_text(encoding="utf-8").strip().splitlines()
    results = [RunResult(**json.loads(line)) for line in lines if line.strip()]
    summary = summarize(results)
    if (results_dir / "grobid_probe.json").exists():
        summary["grobid_probe"] = json.loads(
            (results_dir / "grobid_probe.json").read_text(encoding="utf-8")
        )

    # Sample successes / failures for narrative
    successes = [r for r in results if r.ok][:8]
    failures = [r for r in results if not r.ok][:8]
    emptyish = [r for r in results if r.looks_empty_metadata][:5]

    samples_ok = []
    for r in successes:
        bib_snip = ""
        if r.bib_path and Path(r.bib_path).exists():
            bib_snip = Path(r.bib_path).read_text(encoding="utf-8")[:400]
        samples_ok.append(
            {
                "id": r.id,
                "path_class": r.path_class,
                "convert_source": r.convert_source,
                "entry_type": r.entry_type,
                "key": r.citation_key,
                "bib_snip": bib_snip,
            }
        )

    assessment = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "samples_ok": samples_ok,
        "samples_fail": [asdict(r) for r in failures],
        "samples_empty_meta": [asdict(r) for r in emptyish],
        "careful_notes": [],
    }

    notes = assessment["careful_notes"]
    notes.append(
        f"Processed N={summary['n']}: ok={summary['n_ok']} fail={summary['n_fail']} "
        f"doi_path={summary['n_doi']} fallback={summary['n_fallback']} "
        f"empty_meta_flag={summary['n_empty_metadata']}."
    )
    if summary["n"] and summary["n_with_file_field"] < summary["n_ok"]:
        notes.append(
            "Some OK rows missing file field — unexpected; converter should always attach file."
        )
    if summary["n_empty_metadata"]:
        notes.append(
            f"{summary['n_empty_metadata']} outputs look metadata-empty (unknown key / no title/doi); "
            "often scanned PDFs or header-parse failure — external to Crossref matching."
        )
    if summary.get("grobid_probe") and not summary["grobid_probe"].get("alive"):
        notes.append("GROBID was not alive at probe time — failures may be environmental.")

    out_json = results_dir / "assessment.json"
    out_json.write_text(json.dumps(assessment, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Human markdown
    md_lines = [
        "# E2E assessment",
        "",
        f"Generated: {assessment['generated']}",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(summary, indent=2),
        "```",
        "",
        "## Notes",
        "",
    ]
    for n in notes:
        md_lines.append(f"- {n}")
    md_lines += ["", "## Sample successes", ""]
    for s in samples_ok:
        md_lines.append(f"### {s['id']} ({s['path_class']})")
        md_lines.append(f"- convert_source: `{s['convert_source']}`")
        md_lines.append(f"- entry: `@{s['entry_type']}{{{s['key']}`")
        md_lines.append("```bibtex")
        md_lines.append(s["bib_snip"])
        md_lines.append("```")
        md_lines.append("")
    md_lines += ["## Sample failures", ""]
    for r in failures:
        md_lines.append(f"- `{r.id}`: {r.error or r.convert_source or 'unknown fail'}")
    md_path = results_dir / "assessment.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    # Copy to scratch if provided
    if args.scratch:
        scratch = Path(args.scratch)
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / "e2e-batch-summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        (scratch / "e2e-assessment.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
        (scratch / "e2e-assessment.json").write_text(
            out_json.read_text(encoding="utf-8"), encoding="utf-8"
        )

    print(f"Wrote {out_json} and {md_path}")
    print(json.dumps(summary, indent=2))
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    """Build tiny manifest, download few, run, assess — capture log to scratch."""
    started = datetime.now(timezone.utc).isoformat()
    scratch = Path(args.scratch) if args.scratch else DEFAULT_RESULTS / "smoke_scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    log_path = scratch / "e2e-smoke.log"
    # Fresh results dir per smoke run — never treat stale results as success.
    results = scratch / "results"
    if results.exists():
        for path in sorted(results.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass

    class Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, data):
            for s in self.streams:
                s.write(data)
                s.flush()

        def flush(self):
            for s in self.streams:
                s.flush()

    log_fh = log_path.open("w", encoding="utf-8")
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = Tee(old_out, log_fh)
    sys.stderr = Tee(old_err, log_fh)
    try:
        alive, detail = grobid_alive(args.grobid_url)
        print(f"SMOKE GROBID alive={alive} detail={detail!r}")
        probe = {
            "alive": alive,
            "detail": detail,
            "version": grobid_version(args.grobid_url) if alive else "",
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        (scratch / "grobid_probe_smoke.json").write_text(
            json.dumps(probe, indent=2) + "\n"
        )
        if not alive:
            print(
                "SMOKE ENV FAIL: GROBID unreachable — cannot claim conversion success.",
                file=sys.stderr,
            )
            (scratch / "e2e-smoke-summary.json").write_text(
                json.dumps(
                    {
                        "ok": False,
                        "blocker": "GROBID unreachable",
                        "detail": detail,
                        "provenance": build_provenance(
                            args=args,
                            grobid_url=args.grobid_url,
                            started_at=started,
                        ),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return EXIT_ENV

        manifest = DEFAULT_MANIFEST.with_name("manifest_smoke.json")
        ns = argparse.Namespace(
            target=8,
            manifest=str(manifest),
        )
        rc = cmd_build_manifest(ns)
        print(f"build-manifest rc={rc}")
        if rc != 0:
            return EXIT_FAIL

        corpus = DEFAULT_CORPUS
        ns_dl = argparse.Namespace(
            manifest=str(manifest),
            corpus=str(corpus),
            limit=8,
            timeout=90,
        )
        rc = cmd_download(ns_dl)
        print(f"download rc={rc}")
        if rc != 0:
            return EXIT_FAIL

        ns_run = argparse.Namespace(
            manifest=str(manifest),
            corpus=str(corpus),
            results=str(results),
            limit=8,
            grobid_url=args.grobid_url,
            timeout=args.timeout,
            no_doi_lookup=False,
            allow_no_grobid=False,
            pdfs=None,
            include_orphan_pdfs=False,
        )
        rc_run = cmd_run(ns_run)
        print(f"run rc={rc_run}")
        if rc_run != 0:
            return rc_run

        ns_as = argparse.Namespace(results=str(results), scratch=str(scratch))
        cmd_assess(ns_as)

        summary = json.loads((results / "summary.json").read_text(encoding="utf-8"))
        if summary.get("n", 0) < 1 or summary.get("n_ok", 0) < 1:
            print(f"SMOKE FAIL summary={summary}", file=sys.stderr)
            return EXIT_FAIL
        ok_lines = [
            json.loads(line)
            for line in (results / "results.jsonl").read_text().splitlines()
            if line.strip()
        ]
        goods = [
            r
            for r in ok_lines
            if r.get("ok") and r.get("has_at_entry") and r.get("has_file_field")
        ]
        if not goods:
            print("SMOKE FAIL: no successful bib with @ entry and file field", file=sys.stderr)
            return EXIT_FAIL
        print(f"SMOKE PASS goods={len(goods)} summary={summary}")
        return EXIT_OK
    except Exception:
        traceback.print_exc()
        return EXIT_FAIL
    finally:
        sys.stdout = old_out
        sys.stderr = old_err
        log_fh.close()
        print(f"Smoke log: {log_path}")


def cmd_all(args: argparse.Namespace) -> int:
    started = datetime.now(timezone.utc).isoformat()
    scratch = Path(args.scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    batch_log = scratch / "e2e-batch.log"

    class Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, data):
            for s in self.streams:
                s.write(data)
                s.flush()

        def flush(self):
            for s in self.streams:
                s.flush()

    log_fh = batch_log.open("w", encoding="utf-8")
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = Tee(old_out, log_fh)
    sys.stderr = Tee(old_err, log_fh)
    try:
        alive, detail = grobid_alive(args.grobid_url)
        print(f"BATCH GROBID alive={alive} detail={detail!r}")
        (scratch / "grobid_probe.json").write_text(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "alive": alive,
                    "detail": detail,
                    "url": args.grobid_url,
                    "version": grobid_version(args.grobid_url) if alive else "",
                },
                indent=2,
            )
            + "\n"
        )
        if not alive:
            print("GROBID unreachable — cannot complete large conversion batch honestly.")
            (scratch / "e2e-batch-summary.json").write_text(
                json.dumps(
                    {
                        "n": 0,
                        "blocker": "GROBID unreachable",
                        "detail": detail,
                        "provenance": build_provenance(
                            args=args,
                            grobid_url=args.grobid_url,
                            started_at=started,
                        ),
                    },
                    indent=2,
                )
                + "\n"
            )
            (scratch / "e2e-assessment.md").write_text(
                f"# E2E assessment\n\nGROBID unreachable: {detail}\n",
                encoding="utf-8",
            )
            return EXIT_ENV

        ns_m = argparse.Namespace(target=args.target, manifest=str(DEFAULT_MANIFEST))
        rc_m = cmd_build_manifest(ns_m)
        if rc_m != 0:
            print(f"build-manifest failed rc={rc_m}", file=sys.stderr)
            return EXIT_FAIL

        ns_d = argparse.Namespace(
            manifest=str(DEFAULT_MANIFEST),
            corpus=str(DEFAULT_CORPUS),
            limit=args.target,
            timeout=120,
        )
        rc_d = cmd_download(ns_d)
        if rc_d != 0:
            print(f"download failed rc={rc_d}", file=sys.stderr)
            return EXIT_FAIL

        ns_r = argparse.Namespace(
            manifest=str(DEFAULT_MANIFEST),
            corpus=str(DEFAULT_CORPUS),
            results=str(DEFAULT_RESULTS / "batch"),
            limit=args.target,
            grobid_url=args.grobid_url,
            timeout=args.timeout,
            no_doi_lookup=False,
            allow_no_grobid=False,
            pdfs=None,
            include_orphan_pdfs=False,
        )
        rc_r = cmd_run(ns_r)
        if rc_r != 0:
            print(f"run failed rc={rc_r}", file=sys.stderr)
            return rc_r

        ns_a = argparse.Namespace(results=str(DEFAULT_RESULTS / "batch"), scratch=str(scratch))
        rc_a = cmd_assess(ns_a)
        if rc_a != 0:
            print(f"assess failed rc={rc_a}", file=sys.stderr)
            return EXIT_FAIL

        summary = json.loads(
            (DEFAULT_RESULTS / "batch" / "summary.json").read_text(encoding="utf-8")
        )
        n = int(summary.get("n") or 0)
        n_ok = int(summary.get("n_ok") or 0)
        n_requested = int(summary.get("n_requested") or args.target)
        target = int(args.target)
        corpus_frac = n / target if target else 0.0
        ok_frac = n_ok / n if n else 0.0
        # Invariant: every OK row must have been validated; failed OK rate is fail.
        n_invariants = int(summary.get("n_fail") or 0)  # failures already counted
        # Zero "soft" invariant breaches: no OK without file/at (already in ok score).
        gates = {
            "min_corpus_fraction": MIN_CORPUS_FRACTION,
            "min_ok_fraction": MIN_OK_FRACTION,
            "corpus_fraction": round(corpus_frac, 4),
            "ok_fraction": round(ok_frac, 4),
            "n_requested": n_requested,
            "n": n,
            "n_ok": n_ok,
            "zero_invariant_breaches": True,
        }
        summary["gates"] = gates
        summary["provenance"] = build_provenance(
            args=args,
            grobid_url=args.grobid_url,
            manifest_path=DEFAULT_MANIFEST,
            started_at=started,
        )
        (DEFAULT_RESULTS / "batch" / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (scratch / "e2e-batch-summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"BATCH DONE n={n} ok={n_ok} gates={gates}")

        if corpus_frac < MIN_CORPUS_FRACTION:
            print(
                f"FAIL: corpus coverage {corpus_frac:.2%} < {MIN_CORPUS_FRACTION:.0%} "
                f"of target {target}",
                file=sys.stderr,
            )
            return EXIT_FAIL
        if ok_frac < MIN_OK_FRACTION:
            print(
                f"FAIL: ok rate {ok_frac:.2%} < {MIN_OK_FRACTION:.0%}",
                file=sys.stderr,
            )
            return EXIT_FAIL
        # n_invariants reserved for future explicit invariant counters
        _ = n_invariants
        return EXIT_OK
    finally:
        sys.stdout = old_out
        sys.stderr = old_err
        log_fh.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="pdf2zotero e2e harness")
    parser.add_argument("--grobid-url", default="http://localhost:8070")
    parser.add_argument("--timeout", type=int, default=120)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("build-manifest")
    p.add_argument("--target", type=int, default=250)
    p.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p.set_defaults(func=cmd_build_manifest)

    p = sub.add_parser("download")
    p.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--timeout", type=int, default=120)
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("run")
    p.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    p.add_argument("--results", default=str(DEFAULT_RESULTS / "batch"))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--no-doi-lookup", action="store_true")
    p.add_argument("--allow-no-grobid", action="store_true")
    p.add_argument("--include-orphan-pdfs", action="store_true")
    p.add_argument("--pdfs", nargs="*", default=None)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("assess")
    p.add_argument("--results", default=str(DEFAULT_RESULTS / "batch"))
    p.add_argument("--scratch", default="")
    p.set_defaults(func=cmd_assess)

    p = sub.add_parser("smoke")
    p.add_argument(
        "--scratch",
        default=str(DEFAULT_RESULTS / "smoke_scratch"),
    )
    p.set_defaults(func=cmd_smoke)

    p = sub.add_parser("all")
    p.add_argument("--target", type=int, default=250)
    p.add_argument("--scratch", required=True)
    p.set_defaults(func=cmd_all)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
