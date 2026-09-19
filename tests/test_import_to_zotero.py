#!/usr/bin/env python3
"""Isolated entry-point tests for scripts/import-to-zotero.sh (no Docker/GROBID/Zotero)."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "import-to-zotero.sh"


def _run_script(*args: str, env: dict[str, str] | None = None, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=merged,
        cwd=str(ROOT),
    )


class ImportToZoteroScriptTests(unittest.TestCase):
    def test_script_is_executable_and_exits_before_docker(self):
        self.assertTrue(SCRIPT.is_file(), f"missing {SCRIPT}")
        mode = SCRIPT.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR, "import-to-zotero.sh must be executable")
        text = SCRIPT.read_text(encoding="utf-8")
        install_at = text.find('if [ "${1:-}" = "--install" ]')
        usage_at = text.find('if [ "$#" -eq 0 ]')
        docker_at = text.find("docker info")
        grobid_at = text.find("8070/api/isalive")
        zotero_at = text.find("open -a Zotero")
        self.assertGreater(install_at, 0)
        self.assertGreater(usage_at, install_at)
        self.assertGreater(docker_at, usage_at)
        self.assertGreater(grobid_at, docker_at)
        self.assertGreater(zotero_at, grobid_at)
        self.assertIn("--install", text)
        self.assertIn("Användning:", text)

    def test_no_args_exits_nonzero_with_usage_twice(self):
        first = _run_script()
        second = _run_script()
        self.assertNotEqual(first.returncode, 0)
        self.assertEqual(first.returncode, second.returncode)
        for result in (first, second):
            combined = result.stdout + result.stderr
            self.assertIn("Ingen PDF-fil angiven", combined)
            self.assertIn("Användning:", combined)
            self.assertIn("--install", combined)
            self.assertNotIn("Kontrollerar Docker", combined)
            self.assertNotIn("Kontrollerar GROBID", combined)

    def test_install_writes_workflow_under_sandbox_home(self):
        real_service = (
            Path.home() / "Library" / "Services" / "Importera till Zotero.workflow"
        )
        before_mtime = real_service.stat().st_mtime if real_service.exists() else None

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            result = _run_script("--install", env={"HOME": str(home)})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            combined = result.stdout + result.stderr
            self.assertIn("Installerar", combined)
            self.assertNotIn("Kontrollerar Docker", combined)

            workflow = home / "Library" / "Services" / "Importera till Zotero.workflow"
            info = workflow / "Contents" / "Info.plist"
            wflow = workflow / "Contents" / "document.wflow"
            copied = workflow / "Contents" / "Resources" / "document.wflow"
            self.assertTrue(info.is_file())
            self.assertTrue(wflow.is_file())
            self.assertTrue(copied.is_file())
            plist = info.read_text(encoding="utf-8")
            self.assertIn("se.makeitso.pdf2zotero.importService", plist)
            self.assertIn("Importera till Zotero", plist)
            self.assertIn("com.adobe.pdf", plist)
            body = wflow.read_text(encoding="utf-8")
            self.assertIn(str(SCRIPT), body)
            self.assertIn("com.apple.finder", body)

        if before_mtime is None:
            self.assertFalse(real_service.exists())
        else:
            self.assertEqual(real_service.stat().st_mtime, before_mtime)
