"""tests.test_reproducibility — M15.11 hygiene/reproducibility checks.

Verifies the documented module invocation, the governed-package
import, and that package discovery matches the physical repository
layout. Live server serving via the module invocation is exercised in
the milestone's runtime verification (not here) to avoid brittle
free-port tests.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

import raphael_ibm_bob

ROOT = Path(raphael_ibm_bob.__file__).resolve().parents[1]


class ModuleEntrypoint(unittest.TestCase):
    def test_A_module_help_succeeds(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT)
        proc = subprocess.run(
            [sys.executable, "-m", "raphael_ibm_bob.http", "--help"],
            cwd=str(ROOT), env=env, capture_output=True, text=True,
            timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("usage: raphael-http", proc.stdout)
        self.assertIn("--port", proc.stdout)

    def test_B_delegates_to_existing_app_main(self):
        import raphael_ibm_bob.http.__main__ as entry
        from raphael_ibm_bob.http import app
        self.assertIs(entry.main, app.main)
        self.assertTrue((ROOT / "raphael_ibm_bob" / "http" /
                         "__main__.py").is_file())

    def test_D_operator_routes_still_render(self):
        from raphael_ibm_bob.http.app import (
            RaphaelHTTPConfig, Request, dispatch)
        cfg = RaphaelHTTPConfig(runs_root=ROOT / "runs",
                                sessions_root=ROOT / "sessions")
        for path in ("/health", "/operations", "/operations/findings",
                     "/operations/evidence", "/operations/gate",
                     "/operations/capabilities", "/operations/graph"):
            response = dispatch(Request(method="GET", path=path), cfg)
            self.assertEqual(response.status, 200, path)


class ImportAndLayout(unittest.TestCase):
    def test_E_governed_package_imports(self):
        self.assertTrue(hasattr(raphael_ibm_bob, "__file__"))
        self.assertTrue((ROOT / "raphael_ibm_bob" / "__init__.py").is_file())

    def test_F_packaging_matches_repository_layout(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
        find = data["tool"]["setuptools"]["packages"]["find"]
        self.assertIn(".", find["where"])
        self.assertIs(find.get("namespaces"), False)
        self.assertEqual(find.get("include"), ["raphael_ibm_bob*"])
        package_dir = data["tool"]["setuptools"]["package-dir"]
        self.assertEqual(package_dir.get("raphael_ibm_bob"),
                         "raphael_ibm_bob")
        from setuptools import find_packages
        discovered = set(find_packages(where=".", include=["raphael_ibm_bob*"]))
        self.assertIn("raphael_ibm_bob", discovered)
        self.assertIn("raphael_ibm_bob.http", discovered)
        # The legacy offensive substrate must NOT be part of the distribution.
        self.assertNotIn("orchestrator", discovered)
        self.assertNotIn("agent", discovered)
        self.assertNotIn("arena", discovered)


if __name__ == "__main__":
    unittest.main()
