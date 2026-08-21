#!/usr/bin/env python3
"""Unit checks for e2e scoring helpers — exercise real classify_bib + convert path when GROBID up."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "e2e"))

import harness  # noqa: E402
import pdf2zotero  # noqa: E402


class ClassifyBibTests(unittest.TestCase):
    def test_doi_path_bib(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "x.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            field = pdf2zotero.zotero_file_field(pdf)
            bib = f"""@article{{Smith_2020,
  title = {{Hello}},
  doi = {{10.1234/foo}},
  file = {{{field}}}
}}
"""
            m = harness.classify_bib(bib, "DOI metadata (10.1234/foo)", pdf)
            self.assertTrue(m["has_at_entry"])
            self.assertTrue(m["has_file_field"])
            self.assertTrue(m["has_doi_field"])
            self.assertTrue(m["file_field_exact"])
            self.assertEqual(m["path_class"], "doi")
            self.assertEqual(m["entry_type"], "article")
            self.assertTrue(harness.is_valid_result(m, "DOI metadata (10.1234/foo)"))

    def test_empty_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "x.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            field = pdf2zotero.zotero_file_field(pdf)
            bib = f"""@article{{unknownndabc,
  file = {{{field}}}
}}
"""
            m = harness.classify_bib(bib, "GROBID/PDF fallback", pdf)
            self.assertTrue(m["looks_empty_metadata"])
            self.assertEqual(m["path_class"], "fallback")
            self.assertFalse(m["has_title"])
            self.assertFalse(harness.is_valid_result(m, "GROBID/PDF fallback"))

    def test_titled_fallback_with_file_is_valid(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "x.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            field = pdf2zotero.zotero_file_field(pdf)
            bib = f"""@article{{Lovelace_2020,
  title = {{Hello World}},
  file = {{{field}}}
}}
"""
            m = harness.classify_bib(bib, "GROBID/PDF fallback", pdf)
            self.assertTrue(m["has_title"])
            self.assertTrue(harness.is_valid_result(m, "GROBID/PDF fallback"))

    def test_doi_path_requires_doi_field(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "x.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            field = pdf2zotero.zotero_file_field(pdf)
            bib = f"@article{{k,\n  title = {{T}},\n  file = {{{field}}}\n}}\n"
            m = harness.classify_bib(bib, "DOI metadata (10.1/x)", pdf)
            self.assertFalse(harness.is_valid_result(m, "DOI metadata (10.1/x)"))

    def test_wrong_file_path_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "x.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            bib = "@article{k,\n  file = {:/wrong.pdf:application/pdf}\n}\n"
            m = harness.classify_bib(bib, "GROBID/PDF fallback", pdf)
            self.assertFalse(m["file_field_exact"])
            self.assertFalse(harness.is_valid_result(m, "GROBID/PDF fallback"))


class ProvenanceTests(unittest.TestCase):
    def test_build_provenance_keys(self):
        prov = harness.build_provenance(grobid_url="http://localhost:8070")
        for key in (
            "git_sha",
            "python_version",
            "grobid_version",
            "argv",
            "started_at",
            "finished_at",
        ):
            self.assertIn(key, prov)


class CmdRunFailClosedTests(unittest.TestCase):
    def test_zero_pdfs_fails(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            manifest = td_path / "manifest.json"
            manifest.write_text(json.dumps({"items": []}) + "\n", encoding="utf-8")
            results = td_path / "results"
            ns = argparse.Namespace(
                manifest=str(manifest),
                corpus=str(td_path / "corpus"),
                results=str(results),
                limit=0,
                grobid_url="http://localhost:8070",
                timeout=5,
                no_doi_lookup=True,
                allow_no_grobid=True,
                pdfs=None,
                include_orphan_pdfs=False,
            )
            with mock.patch.object(harness, "grobid_alive", return_value=(True, "true")):
                with mock.patch.object(harness, "grobid_version", return_value="test"):
                    rc = harness.cmd_run(ns)
            self.assertEqual(rc, harness.EXIT_FAIL)
            summary = json.loads((results / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["n"], 0)
            self.assertIn("provenance", summary)


class ConvertPathSmoke(unittest.TestCase):
    """Calls real convert_one when GROBID is alive — skips otherwise."""

    def test_convert_one_minimal_pdf_or_skip(self):
        alive, _ = harness.grobid_alive()
        if not alive:
            self.skipTest("GROBID not alive")
        corpus = ROOT / "e2e" / "corpus"
        pdfs = list(corpus.glob("*.pdf"))[:1]
        if not pdfs:
            self.skipTest("no corpus PDF yet")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.bib"
            source = pdf2zotero.convert_one(
                pdf_path=pdfs[0],
                output_path=out,
                grobid_url="http://localhost:8070",
                timeout=120,
                no_doi_lookup=False,
                save_tei=False,
            )
            text = out.read_text(encoding="utf-8")
            self.assertTrue(text.strip().startswith("@"))
            self.assertIn("file", text.lower())
            self.assertTrue(source)
            meta = harness.classify_bib(text, source, pdfs[0])
            self.assertTrue(harness.is_valid_result(meta, source))


if __name__ == "__main__":
    unittest.main()
