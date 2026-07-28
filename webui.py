#!/usr/bin/env python3
"""
pdf2zotero web UI — local drag-and-drop front end for the conversion pipeline.

Stdlib only. Reuses pdf2zotero.convert_one. Bind to localhost by default.
Requires a running GROBID server (same as the CLI).
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
import threading
import traceback
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import pdf2zotero


STATIC_DIR = Path(__file__).resolve().parent / "webui_static"
DEFAULT_OUTPUT = Path.home() / "Downloads" / "pdf2zotero"
MAX_UPLOAD_BYTES = 80 * 1024 * 1024
CSP_SELF = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; base-uri 'self'; form-action 'self'"


class AppState:
    def __init__(
        self,
        grobid_url: str,
        timeout: int,
        output_dir: Path,
        no_doi_lookup: bool,
    ) -> None:
        self.grobid_url = grobid_url
        self.timeout = timeout
        self.output_dir = output_dir
        self.no_doi_lookup = no_doi_lookup
        self.lock = threading.Lock()


STATE: AppState | None = None


def grobid_alive(grobid_url: str, timeout: int = 3) -> bool:
    url = grobid_url.rstrip("/") + "/api/isalive"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace").strip().lower()
            return body == "true" or "true" in body
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def safe_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^\w.\- ()\[\]]+", "_", name, flags=re.UNICODE)
    name = name.strip(" ._") or "upload.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


def unique_path(directory: Path, filename: str) -> Path:
    """Allocate a free path under directory. Caller must hold STATE.lock when racing."""
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for i in range(2, 1000):
        alt = directory / f"{stem}-{i}{suffix}"
        if not alt.exists():
            return alt
    raise RuntimeError("Could not allocate a unique output filename.")


def parse_bool_token(raw: str) -> bool | None:
    """Parse form bool; return None if empty/unknown."""
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def looks_like_pdf(data: bytes) -> bool:
    return b"%PDF" in data[:1024]


def origin_matches_host(origin: str, host: str) -> bool:
    """True when browser Origin host:port matches the request Host header."""
    try:
        parsed = urlparse(origin)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    origin_host = (parsed.netloc or "").lower()
    req_host = (host or "").lower()
    if not origin_host or not req_host:
        return False
    return origin_host == req_host


def convert_upload(
    pdf_bytes: bytes,
    original_name: str,
    *,
    no_doi_lookup: bool | None = None,
) -> dict:
    assert STATE is not None
    filename = safe_filename(original_name)
    STATE.output_dir.mkdir(parents=True, exist_ok=True)

    effective_no_doi = (
        STATE.no_doi_lookup if no_doi_lookup is None else no_doi_lookup
    )

    # Allocate unique paths under the lock; convert outside so uploads can proceed
    # concurrently once names are reserved.
    with STATE.lock:
        pdf_path = unique_path(STATE.output_dir, filename)
        # Reserve the name so concurrent uploads cannot pick the same path.
        pdf_path.write_bytes(pdf_bytes)
        bib_path = pdf_path.with_suffix(".bib")

    try:
        source = pdf2zotero.convert_one(
            pdf_path=pdf_path,
            output_path=bib_path,
            grobid_url=STATE.grobid_url,
            timeout=STATE.timeout,
            no_doi_lookup=effective_no_doi,
            save_tei=False,
        )
    except Exception:
        # Leave PDF for inspection; remove any partial/failed .bib.
        if bib_path.exists():
            bib_path.unlink(missing_ok=True)
        raise

    bibtex = bib_path.read_text(encoding="utf-8")
    return {
        "ok": True,
        "source": source,
        "bibtex": bibtex,
        "bib_filename": bib_path.name,
        "pdf_filename": pdf_path.name,
        "bib_path": str(bib_path.resolve()),
        "pdf_path": str(pdf_path.resolve()),
        "output_dir": str(STATE.output_dir.resolve()),
        "no_doi_lookup": effective_no_doi,
    }


def parse_multipart(body: bytes, content_type: str) -> dict[str, tuple[str | None, bytes]]:
    """
    Minimal multipart/form-data parser.
    Returns {field_name: (filename_or_None, raw_bytes)}.
    """
    match = re.search(r"boundary=([^;]+)", content_type, flags=re.I)
    if not match:
        raise ValueError("multipart boundary missing")
    boundary = match.group(1).strip().strip('"').encode("ascii", errors="ignore")
    if not boundary:
        raise ValueError("empty multipart boundary")

    delimiter = b"--" + boundary
    parts = body.split(delimiter)
    fields: dict[str, tuple[str | None, bytes]] = {}

    for part in parts:
        if not part or part in (b"--", b"--\r\n", b"\r\n"):
            continue
        if part.startswith(b"--"):
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]

        header_blob, sep, data = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        headers = header_blob.decode("utf-8", errors="replace")
        name_m = re.search(r'name="([^"]+)"', headers, flags=re.I)
        if not name_m:
            continue
        name = name_m.group(1)
        file_m = re.search(r'filename="([^"]*)"', headers, flags=re.I)
        filename = file_m.group(1) if file_m else None
        fields[name] = (filename, data)

    return fields


class Handler(BaseHTTPRequestHandler):
    server_version = "pdf2zotero-webui/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _security_headers(self, content_type: str) -> dict[str, str]:
        headers = {
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        }
        if content_type.startswith("text/html"):
            headers["Content-Security-Policy"] = CSP_SELF
        return headers

    def _send(self, code: int, body: bytes, content_type: str, headers: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        merged = self._security_headers(content_type)
        if headers:
            merged.update(headers)
        for key, value in merged.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._send(code, data, "application/json; charset=utf-8")

    def _serve_static(self, rel: str) -> None:
        if rel in {"", "/"}:
            rel = "/index.html"
        # Prevent path traversal with Path.relative_to.
        try:
            candidate = (STATIC_DIR / rel.lstrip("/")).resolve()
            candidate.relative_to(STATIC_DIR.resolve())
        except (OSError, ValueError):
            self._send(403, b"Forbidden", "text/plain; charset=utf-8")
            return
        if not candidate.is_file():
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type.endswith("javascript"):
            content_type += "; charset=utf-8"
        self._send(200, candidate.read_bytes(), content_type)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/api/health":
            assert STATE is not None
            alive = grobid_alive(STATE.grobid_url)
            self._send_json(
                200,
                {
                    "ok": True,
                    "grobid_url": STATE.grobid_url,
                    "grobid_alive": alive,
                    "output_dir": str(STATE.output_dir.resolve()),
                    "no_doi_lookup": STATE.no_doi_lookup,
                    "timeout": STATE.timeout,
                },
            )
            return

        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path != "/api/convert":
            self._send_json(404, {"ok": False, "error": "Not found"})
            return

        # Browser cross-origin POSTs must match Host; tools without Origin are allowed.
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and not origin_matches_host(origin, host):
            self._send_json(403, {"ok": False, "error": "Cross-origin request rejected"})
            return

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json(400, {"ok": False, "error": "Expected multipart/form-data"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_UPLOAD_BYTES + 1024 * 1024:
            self._send_json(400, {"ok": False, "error": "Invalid or too large upload"})
            return

        body = self.rfile.read(length)
        if len(body) != length:
            self._send_json(400, {"ok": False, "error": "Incomplete request body"})
            return

        try:
            form = parse_multipart(body, content_type)
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": f"Could not parse upload: {exc}"})
            return

        if "file" not in form:
            self._send_json(400, {"ok": False, "error": "Missing form field 'file'"})
            return

        filename, pdf_bytes = form["file"]
        filename = filename or "upload.pdf"
        if not str(filename).lower().endswith(".pdf"):
            self._send_json(400, {"ok": False, "error": "Only PDF files are accepted"})
            return
        if not pdf_bytes:
            self._send_json(400, {"ok": False, "error": "Empty file"})
            return
        if len(pdf_bytes) > MAX_UPLOAD_BYTES:
            self._send_json(400, {"ok": False, "error": "File too large (max 80 MB)"})
            return
        if not looks_like_pdf(pdf_bytes):
            self._send_json(
                400,
                {"ok": False, "error": "File does not look like a PDF (%PDF signature missing)"},
            )
            return

        # Missing field → server default; explicit true/false → form override.
        no_doi: bool | None = None
        if "no_doi_lookup" in form:
            raw = form["no_doi_lookup"][1].decode("utf-8", errors="replace")
            parsed_bool = parse_bool_token(raw)
            if parsed_bool is None:
                self._send_json(
                    400,
                    {"ok": False, "error": "Invalid no_doi_lookup value (use true/false)"},
                )
                return
            no_doi = parsed_bool

        try:
            result = convert_upload(pdf_bytes, str(filename), no_doi_lookup=no_doi)
            self._send_json(200, result)
        except Exception as exc:
            traceback.print_exc()
            self._send_json(
                500,
                {
                    "ok": False,
                    "error": str(exc),
                    "hint": (
                        "Is GROBID running? Try: curl -s http://localhost:8070/api/isalive"
                    ),
                },
            )


def main() -> int:
    global STATE

    parser = argparse.ArgumentParser(
        description="Local web UI for pdf2zotero (drag-and-drop PDF → BibTeX)."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    parser.add_argument(
        "--grobid-url",
        default="http://localhost:8070",
        help="GROBID base URL (default: http://localhost:8070)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Network timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Where to save PDF + .bib (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--no-doi-lookup",
        action="store_true",
        help="Do not contact doi.org/Crossref by default",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser tab on start",
    )
    args = parser.parse_args()

    if not STATIC_DIR.is_dir():
        print(f"Error: missing static UI directory: {STATIC_DIR}", file=sys.stderr)
        return 1

    STATE = AppState(
        grobid_url=args.grobid_url,
        timeout=args.timeout,
        output_dir=args.output_dir.expanduser(),
        no_doi_lookup=args.no_doi_lookup,
    )
    STATE.output_dir.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"pdf2zotero web UI → {url}")
    print(f"GROBID           → {args.grobid_url}")
    print(f"Output directory → {STATE.output_dir.resolve()}")
    if STATE.no_doi_lookup:
        print("DOI lookup      → off by default (form can override)")
    if not grobid_alive(args.grobid_url):
        print(
            "Warning: GROBID does not appear to be alive. "
            "Start it before converting PDFs.",
            file=sys.stderr,
        )

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
