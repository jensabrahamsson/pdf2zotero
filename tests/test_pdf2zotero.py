#!/usr/bin/env python3
"""Deterministic unit tests for pdf2zotero (stdlib only, no live network)."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pdf2zotero  # noqa: E402


TEI_ARTICLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title level="a" type="main">A Sample Article Title</title>
      </titleStmt>
      <sourceDesc>
        <biblStruct>
          <analytic>
            <title level="a" type="main">A Sample Article Title</title>
            <author>
              <persName><forename>Ada</forename><surname>Lovelace</surname></persName>
            </author>
            <idno type="DOI">10.1234/sample.article</idno>
          </analytic>
          <monogr>
            <title level="j">Journal of Samples</title>
            <imprint>
              <biblScope unit="volume">12</biblScope>
              <biblScope unit="issue">3</biblScope>
              <biblScope unit="page" from="10" to="20"/>
              <date type="published" when="2020-05-01"/>
              <date when="1999-01-01"/>
            </imprint>
          </monogr>
        </biblStruct>
      </sourceDesc>
    </fileDesc>
  </teiHeader>
</TEI>
"""

TEI_BOOK = b"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt><title/></titleStmt>
      <sourceDesc>
        <biblStruct>
          <monogr>
            <title level="m" type="main">Meeting the Universe Halfway</title>
            <author>
              <persName><forename>Karen</forename><surname>Barad</surname></persName>
            </author>
            <imprint>
              <publisher>Duke University Press</publisher>
              <date type="published" when="2007"/>
            </imprint>
          </monogr>
        </biblStruct>
      </sourceDesc>
    </fileDesc>
  </teiHeader>
</TEI>
"""

TEI_REPORT = b"""<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title type="main">Technical Report on Widgets TR-42</title>
      </titleStmt>
      <sourceDesc>
        <biblStruct>
          <monogr>
            <title level="m">Technical Report on Widgets TR-42</title>
            <imprint>
              <publisher>National Labs</publisher>
              <date type="published" when="2019"/>
              <biblScope unit="report">TR-42</biblScope>
            </imprint>
          </monogr>
        </biblStruct>
      </sourceDesc>
    </fileDesc>
  </teiHeader>
</TEI>
"""


class CopyrightLicenseTests(unittest.TestCase):
    def test_notice_constants(self):
        self.assertIn("2026", pdf2zotero.COPYRIGHT)
        self.assertIn("Jens Abrahamsson", pdf2zotero.COPYRIGHT)
        self.assertIn("MIT", pdf2zotero.LICENSE_NOTICE)
        self.assertIn(pdf2zotero.COPYRIGHT, pdf2zotero.CLI_EPILOG)

    def test_cli_help_includes_license(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr

        buf_out, buf_err = io.StringIO(), io.StringIO()
        old_argv = sys.argv
        try:
            with self.assertRaises(SystemExit) as ctx:
                with redirect_stdout(buf_out), redirect_stderr(buf_err):
                    sys.argv = ["pdf2zotero.py", "--help"]
                    pdf2zotero.main()
            self.assertEqual(ctx.exception.code, 0)
        finally:
            sys.argv = old_argv
        help_text = buf_out.getvalue() + buf_err.getvalue()
        self.assertIn("Copyright (c) 2026 Jens Abrahamsson", help_text)
        self.assertIn("MIT License", help_text)


class CleanDoiTests(unittest.TestCase):
    def test_strips_url_and_prefix(self):
        self.assertEqual(
            pdf2zotero.clean_doi("https://doi.org/10.1000/xyz123"),
            "10.1000/xyz123",
        )
        self.assertEqual(pdf2zotero.clean_doi("doi:10.1000/xyz123"), "10.1000/xyz123")

    def test_keeps_punctuation_rich_suffix(self):
        doi = "10.1000/abc(def).ghi:jkl;mn"
        self.assertEqual(pdf2zotero.clean_doi(doi), doi)
        self.assertEqual(pdf2zotero.clean_doi(doi + "."), doi)
        self.assertEqual(pdf2zotero.clean_doi("(" + doi + ")"), doi)

    def test_balanced_parens_in_suffix(self):
        doi = "10.1016/S0140-6736(12)60071-1"
        self.assertEqual(pdf2zotero.clean_doi(doi), doi)
        self.assertEqual(pdf2zotero.clean_doi(doi + ")"), doi)


class NormalizeTitleAndNamesTests(unittest.TestCase):
    def test_unicode_title_preserved(self):
        a = pdf2zotero.normalize_title("Äpple och Päron")
        b = pdf2zotero.normalize_title("äpple och päron")
        self.assertEqual(a, b)
        self.assertIn("p", a)
        # Non-Latin scripts should not be wiped.
        self.assertTrue(pdf2zotero.normalize_title("量子力学导论"))
        self.assertGreater(
            pdf2zotero.title_similarity("量子力学导论", "量子力学导论 第二版"),
            0.5,
        )

    def test_surname_orders(self):
        self.assertEqual(pdf2zotero.person_surname("Ada Lovelace"), "lovelace")
        self.assertEqual(pdf2zotero.person_surname("Lovelace, Ada"), "lovelace")
        self.assertEqual(
            pdf2zotero.author_surnames(["Barad, Karen", "Niels Bohr"]),
            {"barad", "bohr"},
        )


class AttachFileTests(unittest.TestCase):
    def test_replace_brace_and_quote_forms(self):
        pdf = Path("/tmp/example.pdf")
        field = pdf2zotero.zotero_file_field(pdf)
        brace = "@article{x,\n  file = {:/old.pdf:application/pdf}\n}\n"
        quote = '@article{x,\n  file = ":/old.pdf:application/pdf"\n}\n'
        out_b = pdf2zotero.attach_file_to_bibtex(brace, pdf)
        out_q = pdf2zotero.attach_file_to_bibtex(quote, pdf)
        self.assertIn(field, out_b)
        self.assertNotIn("/old.pdf", out_b)
        self.assertIn(field, out_q)
        self.assertNotIn("/old.pdf", out_q)

    def test_insert_when_missing(self):
        pdf = Path("/tmp/example.pdf")
        bib = "@article{x,\n  title = {Hello}\n}\n"
        out = pdf2zotero.attach_file_to_bibtex(bib, pdf)
        self.assertIn("file = {", out)
        self.assertIn(pdf2zotero.zotero_file_field(pdf), out)


class ParseTeiTests(unittest.TestCase):
    def test_article_prefers_published_date(self):
        meta = pdf2zotero.parse_grobid_tei(TEI_ARTICLE)
        self.assertEqual(meta.entry_type, "article")
        self.assertEqual(meta.year, "2020")
        self.assertEqual(meta.doi, "10.1234/sample.article")
        self.assertEqual(meta.journal, "Journal of Samples")
        self.assertIn("Lovelace", meta.authors[0])

    def test_book_monograph(self):
        meta = pdf2zotero.parse_grobid_tei(TEI_BOOK)
        self.assertEqual(meta.entry_type, "book")
        self.assertIn("Universe", meta.title)
        self.assertEqual(meta.year, "2007")

    def test_report(self):
        meta = pdf2zotero.parse_grobid_tei(TEI_REPORT)
        self.assertEqual(meta.entry_type, "report")
        self.assertIn("Technical Report", meta.title)


class MergeAndFallbackTests(unittest.TestCase):
    def test_merge_fills_empty(self):
        base = pdf2zotero.Metadata(title="", authors=[])
        extra = pdf2zotero.Metadata(title="T", authors=["A B"], year="2021")
        out = pdf2zotero.merge_metadata(base, extra)
        self.assertEqual(out.title, "T")
        self.assertEqual(out.authors, ["A B"])
        self.assertEqual(out.year, "2021")

    def test_fallback_bibtex_shape(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "doc.pdf"
            pdf.write_bytes(b"%PDF-1.4 minimal")
            meta = pdf2zotero.Metadata(
                title="Hello World Paper",
                authors=["Lovelace, Ada"],
                year="2020",
                entry_type="article",
            )
            bib = pdf2zotero.fallback_bibtex(meta, pdf)
            self.assertTrue(bib.startswith("@article{"))
            self.assertIn("title = {Hello World Paper}", bib)
            self.assertIn(f"file = {{{pdf2zotero.zotero_file_field(pdf)}}}", bib)
            self.assertIn("lovelace", bib.lower())


class OutputSafetyTests(unittest.TestCase):
    def test_refuse_same_path(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "x.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            with self.assertRaises(RuntimeError):
                pdf2zotero.ensure_safe_output_path(pdf, pdf)

    def test_atomic_write_and_collision_leaves_pdf(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "x.pdf"
            original = b"%PDF-1.4 original-bytes"
            pdf.write_bytes(original)
            out = Path(td) / "x.bib"
            pdf2zotero.write_text_atomic(out, "@article{a,\n}\n")
            self.assertTrue(out.is_file())
            self.assertEqual(pdf.read_bytes(), original)
            with self.assertRaises(RuntimeError):
                pdf2zotero.ensure_safe_output_path(pdf, pdf)
            self.assertEqual(pdf.read_bytes(), original)


class LooksLikeBibtexTests(unittest.TestCase):
    def test_valid_and_invalid(self):
        self.assertTrue(pdf2zotero.looks_like_bibtex("@article{key,\n  title={T}\n}\n"))
        self.assertFalse(pdf2zotero.looks_like_bibtex("not bibtex"))
        self.assertFalse(pdf2zotero.looks_like_bibtex("@article{incomplete"))


class OfflineAndNetworkMockTests(unittest.TestCase):
    def _minimal_pdf(self, path: Path) -> None:
        # Minimal PDF with optional Info dict is fine; GROBID is mocked.
        path.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n")

    def test_no_doi_lookup_skips_network(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "a.pdf"
            out = Path(td) / "a.bib"
            self._minimal_pdf(pdf)
            tei = TEI_ARTICLE.replace(
                b"10.1234/sample.article",
                b"",
            )
            # Remove DOI idno entirely for this path.
            tei = TEI_ARTICLE.replace(
                b'<idno type="DOI">10.1234/sample.article</idno>',
                b"",
            )

            calls: list[str] = []

            def fake_urlopen(req, timeout=None):  # noqa: ANN001
                calls.append(getattr(req, "full_url", str(req)))
                raise AssertionError(f"unexpected network: {req}")

            with mock.patch.object(pdf2zotero, "call_grobid", return_value=tei):
                with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                    source = pdf2zotero.convert_one(
                        pdf_path=pdf,
                        output_path=out,
                        grobid_url="http://localhost:8070",
                        timeout=5,
                        no_doi_lookup=True,
                        save_tei=False,
                    )
            self.assertEqual(source, "GROBID/PDF fallback")
            self.assertEqual(calls, [])
            text = out.read_text(encoding="utf-8")
            self.assertIn("@", text)
            self.assertIn("file = {", text)

    def test_invalid_doi_bibtex_falls_back(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "a.pdf"
            out = Path(td) / "a.bib"
            self._minimal_pdf(pdf)
            with mock.patch.object(pdf2zotero, "call_grobid", return_value=TEI_ARTICLE):
                with mock.patch.object(
                    pdf2zotero,
                    "fetch_bibtex_for_doi",
                    side_effect=RuntimeError("DOI resolver did not return valid BibTeX"),
                ):
                    source = pdf2zotero.convert_one(
                        pdf_path=pdf,
                        output_path=out,
                        grobid_url="http://localhost:8070",
                        timeout=5,
                        no_doi_lookup=False,
                        save_tei=False,
                    )
            self.assertEqual(source, "GROBID/PDF fallback")
            self.assertTrue(out.read_text(encoding="utf-8").startswith("@"))

    def test_crossref_uses_v1_and_retries(self):
        meta = pdf2zotero.Metadata(
            title="A Unique Unlikely Title For Testing Crossref 99991",
            authors=["Zebra, Zed"],
            entry_type="article",
        )
        payload = {
            "message": {
                "items": [
                    {
                        "DOI": "10.9999/retry-test",
                        "title": ["A Unique Unlikely Title For Testing Crossref 99991"],
                        "author": [{"family": "Zebra", "given": "Zed"}],
                        "type": "journal-article",
                        "score": 80.0,
                    }
                ]
            }
        }
        attempts = {"n": 0}

        class FakeResp:
            def __init__(self, data: bytes):
                self._data = data

            def read(self):
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(req, timeout=None):  # noqa: ANN001
            attempts["n"] += 1
            url = getattr(req, "full_url", "")
            self.assertIn("/v1/works", url)
            if attempts["n"] == 1:
                raise urllib.error.HTTPError(
                    url, 503, "Service Unavailable", hdrs=None, fp=None
                )
            return FakeResp(json.dumps(payload).encode("utf-8"))

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with mock.patch.object(pdf2zotero.time, "sleep", return_value=None):
                doi, work_type = pdf2zotero.crossref_find_doi(meta, timeout=30)
        self.assertEqual(doi, "10.9999/retry-test")
        self.assertEqual(work_type, "journal-article")
        self.assertGreaterEqual(attempts["n"], 2)

    def test_output_collision_before_write(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "same.pdf"
            original = b"%PDF-1.4 keep-me"
            pdf.write_bytes(original)
            with mock.patch.object(pdf2zotero, "call_grobid", return_value=TEI_ARTICLE):
                with self.assertRaises(RuntimeError):
                    pdf2zotero.convert_one(
                        pdf_path=pdf,
                        output_path=pdf,
                        grobid_url="http://localhost:8070",
                        timeout=5,
                        no_doi_lookup=True,
                        save_tei=False,
                    )
            self.assertEqual(pdf.read_bytes(), original)


class GrobidErrorMessageTests(unittest.TestCase):
    def test_http_error_message(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "a.pdf"
            pdf.write_bytes(b"%PDF-1.4")

            def boom(req, timeout=None):  # noqa: ANN001
                raise urllib.error.HTTPError(
                    req.full_url, 500, "Internal", hdrs=None, fp=None
                )

            with mock.patch("urllib.request.urlopen", side_effect=boom):
                with self.assertRaises(RuntimeError) as ctx:
                    pdf2zotero.call_grobid(pdf, "http://localhost:8070", 5)
            self.assertIn("HTTP 500", str(ctx.exception))

    def test_timeout_message(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "a.pdf"
            pdf.write_bytes(b"%PDF-1.4")

            def boom(req, timeout=None):  # noqa: ANN001
                raise TimeoutError("timed out")

            with mock.patch("urllib.request.urlopen", side_effect=boom):
                with self.assertRaises(RuntimeError) as ctx:
                    pdf2zotero.call_grobid(pdf, "http://localhost:8070", 5)
            self.assertIn("timed out", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
