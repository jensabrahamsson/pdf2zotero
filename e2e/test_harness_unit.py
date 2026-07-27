#!/usr/bin/env python3
"""Unit checks for e2e scoring helpers — exercise real classify_bib + convert path when GROBID up."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "e2e"))

import harness  # noqa: E402
import pdf2zotero  # noqa: E402


class ClassifyBibTests(unittest.TestCase):
    def test_doi_path_bib(self):
        bib = """@article{Smith_2020,
  title = {Hello},
  doi = {10.1234/foo},
  file = {:/tmp/x.pdf:application/pdf}
}
"""
        m = harness.classify_bib(bib, "DOI metadata (10.1234/foo)")
        self.assertTrue(m["has_at_entry"])
        self.assertTrue(m["has_file_field"])
        self.assertTrue(m["has_doi_field"])
        self.assertEqual(m["path_class"], "doi")
        self.assertEqual(m["entry_type"], "article")

    def test_empty_unknown(self):
        bib = """@article{unknownndabc,
  file = {:/tmp/x.pdf:application/pdf}
}
"""
        m = harness.classify_bib(bib, "GROBID/PDF fallback")
        self.assertTrue(m["looks_empty_metadata"])
        self.assertEqual(m["path_class"], "fallback")


class ConvertPathSmoke(unittest.TestCase):
    """Calls real convert_one when GROBID is alive — skips otherwise."""

    def test_convert_one_minimal_pdf_or_skip(self):
        alive, _ = harness.grobid_alive()
        if not alive:
            self.skipTest("GROBID not alive")
        # Use a tiny real PDF if corpus has one; else skip
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


if __name__ == "__main__":
    unittest.main()
