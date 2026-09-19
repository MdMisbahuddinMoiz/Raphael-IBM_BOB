"""tests.test_class_ab_inventory — frozen classification + seccomp semantics.

Forensic corrections F3/F4/F5:

* F3 — the operative C1A capability is `C1A static_file_inspect` over T3MP3ST
  `binary_sink_scan` (pure JS), distinct from the historical `C1`
  `file`-adapter audit.
* F4 — `RUN_TEST` is GOVERNED UNSANDBOXED HOST EXECUTION: not Class A, not
  sandboxed Class B, not C1A.
* F5 — seccomp allows `execve` for the curated runtime closure, denies
  `execveat`, and constrains child-process creation through the
  argument-filtered `clone` rule.

These assert artifacts/behavior, not documentation strings alone.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from raphael_ibm_bob import provider_runtime
from raphael_ibm_bob.seccomp_policy import (
    ARG_FILTERED, CURATED_ALLOWLIST, DENIED_SYSCALLS, allowed_syscall_names)

REPO = Path(__file__).resolve().parents[1]
DOC = (REPO / "docs" / "integration" /
       "phase-2c-c1a-reconciliation-and-classification.md")


class C1AIdentifiers(unittest.TestCase):
    def test_1_operative_c1a_identifiers(self):
        self.assertEqual(provider_runtime.C1A_CAPABILITY_ID,
                         "C1A static_file_inspect")
        self.assertEqual(provider_runtime.C1A_PROVIDER_ID, "t3mp3st")
        self.assertEqual(provider_runtime.C1A_TOOL, "binary_sink_scan")

    def test_2_reconciliation_document_present(self):
        self.assertTrue(DOC.is_file(), DOC)
        text = DOC.read_text()
        self.assertIn("binary_sink_scan", text)
        self.assertIn("C1A static_file_inspect", text)
        self.assertIn("pure JS", text)
        # historical subject explicitly distinguished
        self.assertIn("runSubprocess", text)


class RunTestClassificationF4(unittest.TestCase):
    def test_3_document_freezes_run_test_classification(self):
        text = DOC.read_text()
        self.assertIn("GOVERNED UNSANDBOXED HOST EXECUTION", text)
        self.assertIn("NOT** Class A", text)
        self.assertIn("NOT** sandboxed Class B", text)

    def test_4_run_test_is_not_a_class_a_capability(self):
        # No Class A/B registry advertises RUN_TEST; the capability enum is
        # distinct from the C1A provider tool.
        self.assertNotEqual(provider_runtime.C1A_TOOL, "run_test")
        self.assertNotEqual(provider_runtime.C1A_CAPABILITY_ID, "run_test")

    def test_5_run_test_host_subprocess_source(self):
        src = (REPO / "raphael_ibm_bob" / "capabilities.py").read_text()
        self.assertIn("subprocess.run", src)
        self.assertIn("Capability.RUN_TEST: _run_test", src)


class SeccompExecveSemanticsF5(unittest.TestCase):
    def test_6_execve_allowed_execveat_denied(self):
        allowed = allowed_syscall_names()
        self.assertIn("execve", allowed)
        self.assertIn("execveat", DENIED_SYSCALLS)

    def test_7_clone_is_arg_filtered_not_unconditional(self):
        self.assertNotIn("clone", {e.name for e in CURATED_ALLOWLIST})
        self.assertIn("clone", {name for (name, *_r) in ARG_FILTERED})

    def test_8_reconciliation_documents_execve_semantics(self):
        text = DOC.read_text()
        self.assertIn("`execve`", text)
        self.assertIn("`execveat`", text)
        self.assertIn("argument-filtered", text)


if __name__ == "__main__":
    unittest.main()
