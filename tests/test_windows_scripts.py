#!/usr/bin/env python3
"""Static checks for Windows PowerShell helpers (no Docker / Zotero required)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup-grobid.ps1"
IMPORT = ROOT / "scripts" / "import-to-zotero.ps1"


class SetupGrobidPs1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(SETUP.is_file(), f"missing {SETUP}")
        self.text = SETUP.read_text(encoding="utf-8")

    def test_pinned_images_and_commands(self):
        self.assertIn("grobid/grobid:0.9.0-crf", self.text)
        self.assertIn("grobid/grobid:0.9.0-full", self.text)
        self.assertIn("8070", self.text)
        self.assertIn("api/isalive", self.text)
        self.assertIn("curl.exe", self.text)
        self.assertIn("Invoke-WebRequest", self.text)
        for command in ("up", "status", "down", "purge"):
            self.assertIn(command, self.text)

    def test_no_colima_autostart(self):
        self.assertIn("Does not auto-start Colima", self.text)
        self.assertNotIn("colima start", self.text.lower())

    def test_docker_desktop_error_and_execution_policy(self):
        self.assertIn("Docker Desktop", self.text)
        self.assertIn("ExecutionPolicy Bypass", self.text)
        self.assertIn("--init", self.text)
        self.assertIn("core=0", self.text)


class ImportToZoteroPs1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(IMPORT.is_file(), f"missing {IMPORT}")
        self.text = IMPORT.read_text(encoding="utf-8")

    def test_usage_exits_before_docker(self):
        no_pdf = self.text.find("no PDF file given")
        docker = self.text.find("Checking Docker")
        grobid = self.text.find("Checking GROBID")
        zotero = self.text.find("Opening Zotero")
        convert = self.text.find("Converting and importing")
        self.assertGreater(no_pdf, 0)
        self.assertGreater(docker, no_pdf)
        self.assertGreater(grobid, docker)
        self.assertGreater(zotero, grobid)
        self.assertGreater(convert, zotero)
        self.assertIn("pdf2zotero.py", self.text)

    def test_python_and_zotero_windows_paths(self):
        self.assertIn("py -3", self.text)
        self.assertIn("python", self.text)
        self.assertIn("zotero.exe", self.text)
        self.assertIn("SendTo", self.text)
        self.assertIn("127.0.0.1:8070", self.text)
        self.assertIn("setup-grobid.ps1", self.text)
        self.assertIn("ExecutionPolicy Bypass", self.text)
        self.assertIn("-Install", self.text)


if __name__ == "__main__":
    unittest.main()
