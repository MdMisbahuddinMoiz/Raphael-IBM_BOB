"""tests.test_m10_3_benchmark — M10.3 benchmark modes + provenance tests.

Stdlib-only. Unit fixtures use the real M3 EvidenceLedger APIs plus
the production `append_run_provenance` helper; the end-to-end class
spawns the real demo in both modes as subprocesses and audits what
landed on disk. No synthetic benchmark data, no copied evidence.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SPEC = importlib.util.spec_from_file_location(
    "audit_runs", str(ROOT / "scripts" / "audit_runs.py"))
audit_runs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit_runs)

from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
    ExecutionResult,
    PolicyDecision,
)
from raphael_ibm_bob.evidence_ledger import (
    EvidenceLedger,
    append_run_provenance,
    create_run_dir,
)


def _base(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.mkdtemp(prefix="m10_3_runs_")
    testcase.addCleanup(shutil.rmtree, Path(tmp), True)
    return Path(tmp)


def _write_labeled_run(base: Path, name: str, mode: str | None,
                       verdict: str = "complete",
                       with_replan: bool = False,
                       with_deny: bool = False) -> Path:
    """Genuine ledger via real APIs; optional mode provenance record."""
    run_dir = base / name
    run_dir.mkdir(parents=True)
    ledger = EvidenceLedger(run_dir)
    if mode is not None:
        append_run_provenance(ledger, mode=mode, mission_id="M-authkit",
                              scenario="authkit")
    req = ledger.append_request(ActionRequest(
        sequence=0, requester="probe", capability=Capability.READ,
        target="src/a.txt", purpose="m10:test"))
    dec = ledger.append_decision(req, PolicyDecision(
        sequence=0, decision=Decision.ALLOW, reason="ok",
        capability=Capability.READ, target="src/a.txt"))
    res = ledger.append_result(
        req, dec, ExecutionResult(sequence=0, success=True, output="ok",
                                  error=None, evidence={"k": "v"}))
    if with_deny:
        req2 = ledger.append_request(ActionRequest(
            sequence=0, requester="probe", capability=Capability.RUN_TEST,
            target="src/a.txt", purpose="m10:test"))
        ledger.append_decision(req2, PolicyDecision(
            sequence=0, decision=Decision.DENY, reason="denied",
            capability=Capability.RUN_TEST, target="src/a.txt"))
    if with_replan:
        ledger.append_evidence(
            evidence_id="R-replan-1", producer="replanner",
            request_seq=req, decision_seq=dec, result_seq=res,
            payload={"parent_plan_id": "P-a", "plan_b_id": "P-b",
                     "refuted_finding_id": "F-1"},
            finding_id="F-1")
    ledger.append_finding(
        finding_id="F-1", state="verified", prev_state="unverified",
        summary="s", target="src/a.txt", evidence_seqs=(req, dec),
        payload={"kind": "transition"})
    ledger.append_gate(
        decision=verdict, run_id=run_dir.name, mission_id="M-authkit",
        checks=("A",), evidence_refs=(), finding_refs=("F-1",),
        reasons=(), payload={"decision": verdict})
    ledger.close()
    return run_dir


def _audit(base: Path) -> dict:
    return audit_runs.audit_runs(base)


class ModeProvenance(unittest.TestCase):
    def test_mode_is_persisted(self):
        base = _base(self)
        run_dir = _write_labeled_run(base, "m-1", mode="raphael")
        text = (run_dir / "evidence.jsonl").read_text(encoding="utf-8")
        self.assertIn('"producer":"benchmark"', text)
        self.assertIn('"mode":"raphael"', text)
        report = _audit(base)
        (entry,) = report["runs"]
        self.assertEqual(entry["mode"], "raphael")

    def test_unlabeled_runs_stay_unknown(self):
        base = _base(self)
        _write_labeled_run(base, "u-1", mode=None)
        report = _audit(base)
        (entry,) = report["runs"]
        self.assertEqual(entry["mode"], "unknown")
        self.assertEqual(report["metrics"]["by_mode"], {})

    def test_modes_are_distinguishable(self):
        base = _base(self)
        _write_labeled_run(base, "b-1", mode="baseline",
                           verdict="refuse")
        _write_labeled_run(base, "r-1", mode="raphael",
                           verdict="complete")
        report = _audit(base)
        self.assertEqual(sorted(report["metrics"]["by_mode"]),
                         ["baseline", "raphael"])
        self.assertEqual(
            report["metrics"]["by_mode"]["baseline"]["refused_runs"], 1)
        self.assertEqual(
            report["metrics"]["by_mode"]["raphael"]["complete_runs"], 1)


class UniqueRunIds(unittest.TestCase):
    def test_each_creation_is_unique(self):
        base = _base(self)
        ids = {create_run_dir(base)[0] for _ in range(10)}
        self.assertEqual(len(ids), 10)


class InvalidExcludedFromModes(unittest.TestCase):
    def test_broken_labeled_run_excluded(self):
        base = _base(self)
        _write_labeled_run(base, "good-1", mode="raphael")
        bad = base / "bad-1"
        bad.mkdir()
        (bad / "evidence.jsonl").write_text(
            '{"kind": "evidence", "seq": 1, "producer": "benchmark", '
            '"payload": {"mode": "raphael"}}\nTRUNCATED',
            encoding="utf-8")
        report = _audit(base)
        self.assertEqual(report["invalid_run_count"], 1)
        by_mode = report["metrics"]["by_mode"]
        self.assertEqual(by_mode["raphael"]["valid_runs"], 1)
        self.assertEqual(
            [r["run_id"] for r in report["runs"]], ["good-1"])


class ModeMetricsFromEvidence(unittest.TestCase):
    def test_by_mode_numbers_match_ledger(self):
        base = _base(self)
        _write_labeled_run(base, "b-1", mode="baseline",
                           verdict="refuse", with_deny=True)
        _write_labeled_run(base, "b-2", mode="baseline",
                           verdict="refuse")
        _write_labeled_run(base, "r-1", mode="raphael",
                           verdict="complete", with_replan=True)
        report = _audit(base)
        baseline = report["metrics"]["by_mode"]["baseline"]
        raphael = report["metrics"]["by_mode"]["raphael"]
        self.assertEqual(baseline["valid_runs"], 2)
        self.assertEqual(baseline["refused_runs"], 2)
        self.assertEqual(baseline["refusal_rate"], 1.0)
        self.assertEqual(baseline["policy_denies"], 1)
        self.assertEqual(raphael["valid_runs"], 1)
        self.assertEqual(raphael["complete_runs"], 1)
        self.assertEqual(raphael["completion_rate"], 1.0)
        self.assertEqual(raphael["average_replans"], 1.0)
        self.assertEqual(raphael["successful_run_test_executions"], 0)
        # Overall totals still cover every valid run.
        self.assertEqual(report["metrics"]["valid_runs"], 3)


class AggregationDeterminism(unittest.TestCase):
    def test_repeated_aggregation_stable(self):
        base = _base(self)
        _write_labeled_run(base, "d-1", mode="baseline",
                           verdict="refuse")
        _write_labeled_run(base, "d-2", mode="raphael",
                           verdict="complete", with_replan=True)
        first = _audit(base)
        second = _audit(base)
        for doc in (first, second):
            doc.pop("generated_at", None)
        self.assertEqual(first, second)


def _run_demo_subprocess(mode_args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "demos/authkit_hero.py", *mode_args],
        cwd=str(ROOT), capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )


def _parse_run(stdout: str) -> tuple:
    run_id = re.search(r"^Run ID: (\S+)$", stdout,
                       re.MULTILINE).group(1)
    evidence = re.search(r"^Evidence: (\S+)$", stdout,
                         re.MULTILINE).group(1)
    return run_id, ROOT / evidence


class BenchmarkModesEndToEnd(unittest.TestCase):
    """One real baseline + one real raphael execution, audited on disk."""

    @classmethod
    def setUpClass(cls):
        cls.baseline_proc = _run_demo_subprocess(["--mode", "baseline"])
        cls.raphael_proc = _run_demo_subprocess([])
        cls.base_id, cls.base_ledger = _parse_run(
            cls.baseline_proc.stdout)
        cls.raph_id, cls.raph_ledger = _parse_run(
            cls.raphael_proc.stdout)

    def test_benchmark_command_creates_durable_runs(self):
        for ledger_path in (self.base_ledger, self.raph_ledger):
            self.assertTrue(ledger_path.is_file())
            self.assertTrue((ledger_path.parent / "artifacts").is_dir())

    def test_run_ids_unique_across_modes(self):
        self.assertNotEqual(self.base_id, self.raph_id)
        self.assertNotEqual(self.base_ledger, self.raph_ledger)

    def test_baseline_refuses_raphael_completes(self):
        self.assertNotEqual(self.baseline_proc.returncode, 0)
        self.assertEqual(self.raphael_proc.returncode, 0)
        self.assertIn("Gate: REFUSE", self.baseline_proc.stdout)
        self.assertIn("Gate: COMPLETE", self.raphael_proc.stdout)

    def test_modes_use_equivalent_setup(self):
        from raphael_ibm_bob.evidence_ledger import LedgerReader
        base_gates = LedgerReader(self.base_ledger).gate_decisions()
        raph_gates = LedgerReader(self.raph_ledger).gate_decisions()
        self.assertEqual(len(base_gates), 1)
        self.assertEqual(len(raph_gates), 1)
        # Same mission...
        self.assertEqual(base_gates[0]["mission_id"], "M-authkit")
        self.assertEqual(raph_gates[0]["mission_id"], "M-authkit")
        # ...same initial Plan A target...
        base_reqs = [r for r in LedgerReader(self.base_ledger).records()
                     if r.get("kind") == "request"]
        raph_reqs = [r for r in LedgerReader(self.raph_ledger).records()
                     if r.get("kind") == "request"]
        self.assertEqual(base_reqs[0]["target"],
                         raph_reqs[0]["target"])
        self.assertEqual(base_reqs[0]["target"],
                         "fixtures/authkit/login.py")
        # ...opposite honest verdicts.
        self.assertEqual(base_gates[0]["decision"], "refuse")
        self.assertEqual(raph_gates[0]["decision"], "complete")

    def test_mode_provenance_on_disk(self):
        from raphael_ibm_bob.evidence_ledger import LedgerReader
        for ledger_path, expected in (
                (self.base_ledger, "baseline"),
                (self.raph_ledger, "raphael")):
            modes = [
                r["payload"]["mode"]
                for r in LedgerReader(ledger_path).records()
                if r.get("kind") == "evidence"
                and r.get("producer") == "benchmark"
                and isinstance(r.get("payload"), dict)
                and "mode" in r["payload"]]
            self.assertEqual(modes, [expected])

    def test_fixtures_restored_after_both_modes(self):
        session_text = (ROOT / "fixtures" / "authkit" / "session.py"
                        ).read_text(encoding="utf-8")
        self.assertIn("BUGGY", session_text)


if __name__ == "__main__":
    unittest.main()
