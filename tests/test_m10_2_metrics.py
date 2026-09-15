"""tests.test_m10_2_metrics — M10.2 metrics aggregation tests.

Stdlib-only. Valid-run fixtures are written through the real M3
EvidenceLedger APIs (request/decision/result/evidence/finding/gate),
so the aggregator is exercised against genuine record shapes.
Invalid-run fixtures are hand-crafted malformed JSONL. The audit
module itself is loaded from scripts/audit_runs.py and parses pure
JSON — it never imports raphael_ibm_bob.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

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
from raphael_ibm_bob.evidence_ledger import EvidenceLedger


def _base(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.mkdtemp(prefix="m10_2_runs_")
    testcase.addCleanup(shutil.rmtree, Path(tmp), True)
    return Path(tmp)


def _run_dir(base: Path, name: str) -> Path:
    d = base / name
    d.mkdir(parents=True)
    return d


def _request(capability: Capability = Capability.READ,
             target: str = "src/a.txt") -> ActionRequest:
    return ActionRequest(
        sequence=0, requester="probe", capability=capability,
        target=target, purpose="m10:test")


def _decision(allow: bool = True,
              capability: Capability = Capability.READ,
              target: str = "src/a.txt") -> PolicyDecision:
    return PolicyDecision(
        sequence=0,
        decision=Decision.ALLOW if allow else Decision.DENY,
        reason="ok" if allow else "denied",
        capability=capability, target=target)


def _result() -> ExecutionResult:
    return ExecutionResult(sequence=0, success=True, output="ok",
                           error=None, evidence={"k": "v"})


def _write_valid_run(run_dir: Path, verdict: str = "complete",
                     with_replan: bool = False,
                     with_deny: bool = False) -> None:
    """A genuine ledger: one ALLOWed READ chain, optional DENY chain,
    optional replanner record, finding lifecycle, and a gate record."""
    ledger = EvidenceLedger(run_dir)
    req = ledger.append_request(_request())
    dec = ledger.append_decision(req, _decision(allow=True))
    res = ledger.append_result(req, dec, _result())
    ledger.append_evidence(
        evidence_id="E-exec-1", producer="execution",
        request_seq=req, decision_seq=dec, result_seq=res,
        payload={"ok": True})
    if with_deny:
        req2 = ledger.append_request(
            _request(Capability.RUN_TEST, "src/a.txt"))
        ledger.append_decision(req2, _decision(
            allow=False, capability=Capability.RUN_TEST,
            target="src/a.txt"))
    if with_replan:
        ledger.append_evidence(
            evidence_id="R-replan-1", producer="replanner",
            request_seq=req, decision_seq=dec, result_seq=res,
            payload={"parent_plan_id": "P-a", "plan_b_id": "P-b",
                     "refuted_finding_id": "F-1"},
            finding_id="F-1")
    ledger.append_finding(
        finding_id="F-1", state="unverified", prev_state=None,
        summary="s", target="src/a.txt", evidence_seqs=(req,),
        payload={"kind": "initial"})
    ledger.append_finding(
        finding_id="F-1", state="verified", prev_state="unverified",
        summary="s", target="src/a.txt", evidence_seqs=(req, dec),
        payload={"kind": "transition"})
    ledger.append_gate(
        decision=verdict, run_id=run_dir.name, mission_id="M-t",
        checks=("A",), evidence_refs=("E-exec-1",),
        finding_refs=("F-1",), reasons=(),
        payload={"decision": verdict})
    ledger.close()


def _audit(base: Path) -> dict:
    return audit_runs.audit_runs(base)


class EmptyRoot(unittest.TestCase):
    def test_empty_runs_directory(self):
        base = _base(self)
        report = _audit(base)
        self.assertEqual(report["run_count"], 0)
        self.assertEqual(report["valid_run_count"], 0)
        self.assertEqual(report["invalid_run_count"], 0)
        self.assertIsNone(report["metrics"]["completion_rate"])


class SingleValidRun(unittest.TestCase):
    def test_one_valid_run(self):
        base = _base(self)
        _write_valid_run(_run_dir(base, "run-1"))
        report = _audit(base)
        self.assertEqual(report["run_count"], 1)
        self.assertEqual(report["valid_run_count"], 1)
        self.assertEqual(report["invalid_run_count"], 0)
        self.assertEqual(report["runs"][0]["verdict"], "complete")
        self.assertEqual(report["runs"][0]["record_count"], 7)


class MultipleValidRuns(unittest.TestCase):
    def test_two_runs_aggregate(self):
        base = _base(self)
        _write_valid_run(_run_dir(base, "run-1"), verdict="complete")
        _write_valid_run(_run_dir(base, "run-2"), verdict="refuse")
        report = _audit(base)
        self.assertEqual(report["metrics"]["complete_runs"], 1)
        self.assertEqual(report["metrics"]["refused_runs"], 1)
        self.assertEqual(report["metrics"]["completion_rate"], 0.5)
        self.assertEqual(
            [r["run_id"] for r in report["runs"]], ["run-1", "run-2"])


class InvalidJsonl(unittest.TestCase):
    def test_truncated_jsonl_is_invalid(self):
        base = _base(self)
        d = _run_dir(base, "bad-1")
        (d / "evidence.jsonl").write_text(
            '{"kind": "request", "seq": 1}\n{"kind": "decis',
            encoding="utf-8")
        report = _audit(base)
        self.assertEqual(report["invalid_run_count"], 1)
        self.assertEqual(report["valid_run_count"], 0)
        entry = report["validation"][0]
        self.assertFalse(entry["valid"])
        self.assertTrue(any("unparseable-line" in r
                            for r in entry["reasons"]))

    def test_missing_evidence_jsonl_is_invalid(self):
        base = _base(self)
        _run_dir(base, "empty-1")
        report = _audit(base)
        self.assertEqual(report["invalid_run_count"], 1)
        self.assertIn("missing-evidence-jsonl",
                      report["validation"][0]["reasons"])


class MissingGate(unittest.TestCase):
    def test_run_without_gate_is_invalid(self):
        base = _base(self)
        d = _run_dir(base, "nogate-1")
        ledger = EvidenceLedger(d)
        req = ledger.append_request(_request())
        ledger.append_decision(req, _decision())
        ledger.close()
        report = _audit(base)
        self.assertEqual(report["invalid_run_count"], 1)
        self.assertIn("missing-gate-record",
                      report["validation"][0]["reasons"])


class CorruptSequence(unittest.TestCase):
    def test_duplicate_sequence_is_invalid(self):
        base = _base(self)
        d = _run_dir(base, "dupseq-1")
        lines = [
            {"kind": "request", "seq": 1},
            {"kind": "decision", "seq": 1},
        ]
        (d / "evidence.jsonl").write_text(
            "\n".join(json.dumps(o) for o in lines) + "\n",
            encoding="utf-8")
        report = _audit(base)
        self.assertEqual(report["invalid_run_count"], 1)
        self.assertIn("non-dense-sequence",
                      report["validation"][0]["reasons"])

    def test_unknown_kind_is_invalid(self):
        base = _base(self)
        d = _run_dir(base, "badkind-1")
        (d / "evidence.jsonl").write_text(
            '{"kind": "telemetry", "seq": 1}\n', encoding="utf-8")
        report = _audit(base)
        self.assertEqual(report["invalid_run_count"], 1)


class CompleteVsRefuse(unittest.TestCase):
    def test_verdicts_come_from_gate_records(self):
        base = _base(self)
        _write_valid_run(_run_dir(base, "c-1"), verdict="complete")
        _write_valid_run(_run_dir(base, "r-1"), verdict="refuse")
        report = _audit(base)
        by_id = {r["run_id"]: r["verdict"] for r in report["runs"]}
        self.assertEqual(by_id, {"c-1": "complete", "r-1": "refuse"})
        self.assertEqual(report["metrics"]["gate_decisions"],
                         {"complete": 1, "refuse": 1})


class AllowVsDeny(unittest.TestCase):
    def test_deny_is_not_execution(self):
        base = _base(self)
        _write_valid_run(_run_dir(base, "d-1"), with_deny=True)
        (entry,) = [r for r in _audit(base)["runs"]]
        self.assertEqual(entry["allows"], 1)
        self.assertEqual(entry["denies"], 1)
        self.assertEqual(entry["requested"], 2)
        self.assertEqual(entry["executed"], 1)
        self.assertEqual(entry["requested_by_capability"],
                         {"read": 1, "run_test": 1})
        self.assertEqual(entry["executed_by_capability"], {"read": 1})


class FindingStates(unittest.TestCase):
    def test_terminal_vs_transitions(self):
        base = _base(self)
        _write_valid_run(_run_dir(base, "f-1"))
        (entry,) = [r for r in _audit(base)["runs"]]
        self.assertEqual(entry["findings"], 1)
        self.assertEqual(entry["finding_terminal_states"],
                         {"verified": 1})
        self.assertEqual(entry["finding_transitions"], 2)


class ReplanCounting(unittest.TestCase):
    def test_replans_from_replanner_records(self):
        base = _base(self)
        _write_valid_run(_run_dir(base, "p-1"), with_replan=True)
        _write_valid_run(_run_dir(base, "p-2"), with_replan=False)
        report = _audit(base)
        by_id = {r["run_id"]: r for r in report["runs"]}
        self.assertEqual(by_id["p-1"]["replans"], 1)
        self.assertEqual(by_id["p-1"]["plan_depth"], 2)
        self.assertEqual(by_id["p-2"]["replans"], 0)
        self.assertEqual(by_id["p-2"]["plan_depth"], 1)
        self.assertEqual(report["metrics"]["max_replans_observed"], 1)


class InvalidExcluded(unittest.TestCase):
    def test_invalid_runs_do_not_contaminate(self):
        base = _base(self)
        _write_valid_run(_run_dir(base, "good-1"), verdict="complete")
        bad = _run_dir(base, "bad-1")
        (bad / "evidence.jsonl").write_text("not json\n",
                                            encoding="utf-8")
        report = _audit(base)
        self.assertEqual(report["run_count"], 2)
        self.assertEqual(report["valid_run_count"], 1)
        self.assertEqual(report["invalid_run_count"], 1)
        self.assertEqual(report["metrics"]["complete_runs"], 1)
        self.assertEqual([r["run_id"] for r in report["runs"]],
                         ["good-1"])


class Determinism(unittest.TestCase):
    def test_same_evidence_same_metrics(self):
        base = _base(self)
        _write_valid_run(_run_dir(base, "a-1"), verdict="complete",
                         with_replan=True, with_deny=True)
        _write_valid_run(_run_dir(base, "a-2"), verdict="refuse")
        first = _audit(base)
        second = _audit(base)
        for doc in (first, second):
            doc.pop("generated_at", None)
        self.assertEqual(first, second)

    def test_cli_writes_deterministic_document(self):
        base = _base(self)
        _write_valid_run(_run_dir(base, "b-1"))
        out1 = base / "m1.json"
        out2 = base / "m2.json"
        self.assertEqual(
            audit_runs.main(["--runs-root", str(base),
                             "--output", str(out1)]), 0)
        self.assertEqual(
            audit_runs.main(["--runs-root", str(base),
                             "--output", str(out2)]), 0)
        doc1 = json.loads(out1.read_text(encoding="utf-8"))
        doc2 = json.loads(out2.read_text(encoding="utf-8"))
        doc1.pop("generated_at")
        doc2.pop("generated_at")
        self.assertEqual(doc1, doc2)

    def test_missing_root_is_fatal(self):
        base = _base(self)
        self.assertEqual(
            audit_runs.main(["--runs-root",
                             str(base / "nope"),
                             "--output", str(base / "m.json")]), 2)


if __name__ == "__main__":
    unittest.main()
