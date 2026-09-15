"""tests.test_t1_3_seal — T1-3 evidence seal + export verification.

A deterministic hash chain seals the ledger; any modification,
deletion, reordering, or corruption fails verification. Existing
aggregation behavior is asserted unchanged.
"""
from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_SPEC = importlib.util.spec_from_file_location(
    "audit_runs", str(ROOT / "scripts" / "audit_runs.py"))
audit_runs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit_runs)

from raphael_ibm_bob import (
    ActionRequest,
    BOBBroker,
    BOBPolicy,
    BOBRuntime,
    Capability,
    Mission,
    Workspace,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.seal import (
    SEAL_FILENAME,
    compute_seal,
    verify_seal,
    write_seal,
)


def _run_dir(testcase: unittest.TestCase) -> Path:
    base = Path(tempfile.mkdtemp(prefix="t1_3_runs_"))
    testcase.addCleanup(shutil.rmtree, base, True)
    run_dir = base / "run-sealed"
    ws = base / "ws"
    (ws / "src").mkdir(parents=True)
    (ws / "src" / "a.txt").write_text("OK\n", encoding="utf-8")
    workspace = Workspace(ws)
    ledger = EvidenceLedger(run_dir)
    broker = BOBBroker(BOBPolicy(workspace), workspace, ledger=ledger)
    runtime = BOBRuntime(broker)
    mission = Mission(mission_id="M-s", description="x", scope="src/",
                      criteria=["x"])
    runtime.submit(ActionRequest(
        sequence=0, requester="probe", capability=Capability.READ,
        target="src/a.txt", purpose="seal-fixture"), mission)
    ledger.append_gate(
        decision="refuse", run_id=run_dir.name, mission_id="M-s",
        checks=("A",), evidence_refs=(), finding_refs=(),
        reasons=("fixture",), payload={"decision": "refuse"})
    ledger.close()
    return run_dir


class SealCreated(unittest.TestCase):
    def test_seal_written_and_verifies(self):
        run_dir = _run_dir(self)
        seal_path = write_seal(run_dir)
        self.assertEqual(seal_path, run_dir / SEAL_FILENAME)
        self.assertTrue(seal_path.is_file())
        ok, reason = verify_seal(run_dir)
        self.assertTrue(ok, msg=reason)
        self.assertEqual(reason, "seal-ok")

    def test_reopen_verifies(self):
        run_dir = _run_dir(self)
        write_seal(run_dir)
        # Fresh reads from disk only, as a new process would do.
        manifest = compute_seal(run_dir)
        ok, _ = verify_seal(run_dir)
        self.assertTrue(ok)
        self.assertEqual(manifest["run_id"], run_dir.name)
        self.assertGreater(manifest["record_count"], 0)


class TamperDetection(unittest.TestCase):
    def _tampered(self, testcase: unittest.TestCase,
                  mutate) -> Path:
        run_dir = _run_dir(testcase)
        write_seal(run_dir)
        ledger_path = run_dir / "evidence.jsonl"
        lines = ledger_path.read_text(
            encoding="utf-8").splitlines(keepends=False)
        mutate(lines)
        ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return run_dir

    def test_modify_one_byte_fails(self):
        def flip(lines):
            lines[0] = lines[0].replace("probe", "prXbe", 1)
        run_dir = self._tampered(self, flip)
        ok, reason = verify_seal(run_dir)
        self.assertFalse(ok)
        self.assertIn("head-mismatch", reason)

    def test_delete_record_fails(self):
        run_dir = self._tampered(self, lambda lines: lines.pop())
        ok, reason = verify_seal(run_dir)
        self.assertFalse(ok)
        self.assertIn("record-count-mismatch", reason)

    def test_reorder_records_fails(self):
        def swap(lines):
            lines[0], lines[1] = lines[1], lines[0]
        run_dir = self._tampered(self, swap)
        ok, reason = verify_seal(run_dir)
        self.assertFalse(ok)
        self.assertIn("head-mismatch", reason)

    def test_malformed_record_fails(self):
        run_dir = self._tampered(
            self, lambda lines: lines.append("NOT-JSON{{{"))
        ok, reason = verify_seal(run_dir)
        self.assertFalse(ok)
        self.assertIn("malformed-ledger", reason)

    def test_missing_seal_fails(self):
        run_dir = _run_dir(self)
        ok, reason = verify_seal(run_dir)
        self.assertFalse(ok)
        self.assertEqual(reason, "missing-seal")


class Determinism(unittest.TestCase):
    def test_seal_is_byte_stable(self):
        run_dir = _run_dir(self)
        write_seal(run_dir)
        first = (run_dir / SEAL_FILENAME).read_bytes()
        write_seal(run_dir)
        second = (run_dir / SEAL_FILENAME).read_bytes()
        self.assertEqual(first, second)


class MetricsUnchanged(unittest.TestCase):
    def test_aggregation_ignores_seals(self):
        base = Path(tempfile.mkdtemp(prefix="t1_3_agg_"))
        self.addCleanup(shutil.rmtree, base, True)
        run_dir = _run_dir(self)
        target = base / run_dir.name
        shutil.copytree(run_dir, target)
        before = audit_runs.audit_runs(base)
        from raphael_ibm_bob.seal import write_seal as _seal
        _seal(target)
        after = audit_runs.audit_runs(base)
        self.assertEqual(before["metrics"], after["metrics"])
        self.assertEqual(before["validation"], after["validation"])

    def test_cli_verify_seal(self):
        run_dir = _run_dir(self)
        write_seal(run_dir)
        self.assertEqual(
            audit_runs.main(["--verify-seal", str(run_dir)]), 0)
        ledger_path = run_dir / "evidence.jsonl"
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
        lines[0] = lines[0].replace("probe", "prXbe", 1)
        ledger_path.write_text("\n".join(lines) + "\n",
                               encoding="utf-8")
        self.assertEqual(
            audit_runs.main(["--verify-seal", str(run_dir)]), 1)
        self.assertEqual(
            audit_runs.main(["--verify-seal",
                             str(run_dir / "missing")]), 2)


if __name__ == "__main__":
    unittest.main()
