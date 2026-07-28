#!/usr/bin/env python3
"""Unit tests for webui helpers and HTTP handler behaviour (stdlib only)."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import webui  # noqa: E402


def _multipart(fields: dict[str, tuple[str | None, bytes]], boundary: str = "----bound") -> tuple[bytes, str]:
    parts: list[bytes] = []
    for name, (filename, data) in fields.items():
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"'
        )
        if filename is not None:
            header += f'; filename="{filename}"'
        header += "\r\n\r\n"
        parts.append(header.encode("utf-8") + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    return body, f"multipart/form-data; boundary={boundary}"


class HelperTests(unittest.TestCase):
    def test_parse_bool_token(self):
        self.assertTrue(webui.parse_bool_token("true"))
        self.assertFalse(webui.parse_bool_token("0"))
        self.assertIsNone(webui.parse_bool_token("maybe"))

    def test_looks_like_pdf(self):
        self.assertTrue(webui.looks_like_pdf(b"%PDF-1.4 rest"))
        self.assertTrue(webui.looks_like_pdf(b"\x00" * 10 + b"%PDF"))
        self.assertFalse(webui.looks_like_pdf(b"not a pdf"))

    def test_origin_matches_host(self):
        self.assertTrue(webui.origin_matches_host("http://127.0.0.1:8765", "127.0.0.1:8765"))
        self.assertFalse(webui.origin_matches_host("http://evil.example", "127.0.0.1:8765"))

    def test_parse_multipart(self):
        body, ctype = _multipart({"file": ("a.pdf", b"%PDF-1.4 data"), "no_doi_lookup": (None, b"true")})
        form = webui.parse_multipart(body, ctype)
        self.assertEqual(form["file"][0], "a.pdf")
        self.assertEqual(form["file"][1], b"%PDF-1.4 data")
        self.assertEqual(form["no_doi_lookup"][1], b"true")


class ConvertUploadTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.out = Path(self._td.name)
        webui.STATE = webui.AppState(
            grobid_url="http://localhost:8070",
            timeout=5,
            output_dir=self.out,
            no_doi_lookup=True,
        )

    def tearDown(self):
        webui.STATE = None
        self._td.cleanup()

    def test_server_default_when_field_missing(self):
        seen = {}

        def fake_convert_one(**kwargs):
            seen["no_doi"] = kwargs["no_doi_lookup"]
            path = kwargs["output_path"]
            path.write_text("@article{x,\n  file = {:/tmp/x.pdf:application/pdf}\n}\n", encoding="utf-8")
            return "GROBID/PDF fallback"

        with mock.patch.object(webui.pdf2zotero, "convert_one", side_effect=fake_convert_one):
            result = webui.convert_upload(b"%PDF-1.4", "paper.pdf", no_doi_lookup=None)
        self.assertTrue(seen["no_doi"])
        self.assertTrue(result["no_doi_lookup"])
        self.assertTrue(result["ok"])

    def test_explicit_false_overrides_server_offline(self):
        seen = {}

        def fake_convert_one(**kwargs):
            seen["no_doi"] = kwargs["no_doi_lookup"]
            kwargs["output_path"].write_text(
                "@article{x,\n  file = {:/tmp/x.pdf:application/pdf}\n}\n",
                encoding="utf-8",
            )
            return "DOI metadata (10.1/x)"

        with mock.patch.object(webui.pdf2zotero, "convert_one", side_effect=fake_convert_one):
            result = webui.convert_upload(b"%PDF-1.4", "paper.pdf", no_doi_lookup=False)
        self.assertFalse(seen["no_doi"])
        self.assertFalse(result["no_doi_lookup"])

    def test_partial_bib_cleanup_on_failure(self):
        def boom(**kwargs):
            kwargs["output_path"].write_text("partial", encoding="utf-8")
            raise RuntimeError("GROBID down")

        with mock.patch.object(webui.pdf2zotero, "convert_one", side_effect=boom):
            with self.assertRaises(RuntimeError):
                webui.convert_upload(b"%PDF-1.4", "paper.pdf")
        bibs = list(self.out.glob("*.bib"))
        self.assertEqual(bibs, [])
        pdfs = list(self.out.glob("*.pdf"))
        self.assertEqual(len(pdfs), 1)

    def test_concurrent_unique_names(self):
        barrier = threading.Barrier(2)
        paths: list[str] = []
        lock = threading.Lock()

        def fake_convert_one(**kwargs):
            barrier.wait(timeout=5)
            kwargs["output_path"].write_text(
                "@article{x,\n  file = {:/tmp/x.pdf:application/pdf}\n}\n",
                encoding="utf-8",
            )
            with lock:
                paths.append(str(kwargs["pdf_path"]))
            return "GROBID/PDF fallback"

        with mock.patch.object(webui.pdf2zotero, "convert_one", side_effect=fake_convert_one):
            errors: list[BaseException] = []

            def worker():
                try:
                    webui.convert_upload(b"%PDF-1.4 concurrent", "same.pdf")
                except BaseException as exc:  # noqa: BLE001
                    errors.append(exc)

            t1 = threading.Thread(target=worker)
            t2 = threading.Thread(target=worker)
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)
        self.assertEqual(errors, [])
        self.assertEqual(len(set(paths)), 2)


class HttpHandlerTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.out = Path(self._td.name)
        webui.STATE = webui.AppState(
            grobid_url="http://localhost:8070",
            timeout=5,
            output_dir=self.out,
            no_doi_lookup=True,
        )
        self.server = webui.ThreadingHTTPServer(("127.0.0.1", 0), webui.Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        webui.STATE = None
        self._td.cleanup()

    def _conn(self) -> HTTPConnection:
        return HTTPConnection("127.0.0.1", self.port, timeout=5)

    def test_health(self):
        conn = self._conn()
        conn.request("GET", "/api/health")
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertTrue(data["no_doi_lookup"])

    def test_static_csp_and_path_traversal(self):
        conn = self._conn()
        conn.request("GET", "/")
        resp = conn.getresponse()
        body = resp.read()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertIn("content-security-policy", headers)
        self.assertIn("default-src 'self'", headers["content-security-policy"])
        self.assertNotIn(b"fonts.googleapis.com", body)

        conn = self._conn()
        conn.request("GET", "/../pdf2zotero.py")
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertIn(resp.status, {403, 404})

    def test_reject_non_pdf_signature(self):
        body, ctype = _multipart({"file": ("x.pdf", b"not-a-pdf")})
        conn = self._conn()
        conn.request("POST", "/api/convert", body=body, headers={"Content-Type": ctype})
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        self.assertEqual(resp.status, 400)
        self.assertIn("PDF", data["error"])

    def test_reject_cross_origin(self):
        body, ctype = _multipart({"file": ("x.pdf", b"%PDF-1.4")})
        conn = self._conn()
        conn.request(
            "POST",
            "/api/convert",
            body=body,
            headers={
                "Content-Type": ctype,
                "Origin": "http://evil.example",
                "Host": f"127.0.0.1:{self.port}",
            },
        )
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        self.assertEqual(resp.status, 403)
        self.assertIn("Cross-origin", data["error"])

    def test_missing_no_doi_uses_server_default(self):
        seen = {}

        def fake_convert_one(**kwargs):
            seen["no_doi"] = kwargs["no_doi_lookup"]
            kwargs["output_path"].write_text(
                "@article{x,\n  file = {:/tmp/x.pdf:application/pdf}\n}\n",
                encoding="utf-8",
            )
            return "GROBID/PDF fallback"

        body, ctype = _multipart({"file": ("x.pdf", b"%PDF-1.4 data")})
        with mock.patch.object(webui.pdf2zotero, "convert_one", side_effect=fake_convert_one):
            conn = self._conn()
            conn.request(
                "POST",
                "/api/convert",
                body=body,
                headers={"Content-Type": ctype, "Host": f"127.0.0.1:{self.port}"},
            )
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            conn.close()
        self.assertEqual(resp.status, 200)
        self.assertTrue(seen["no_doi"])
        self.assertTrue(data["no_doi_lookup"])


if __name__ == "__main__":
    unittest.main()
