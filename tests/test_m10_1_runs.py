"""tests.test_m10_1_runs — M10.1 durable run evidence tests.

Stdlib-only, real evidence throughout (no mocks): run directories are
created through the production `create_run_dir` helper, ledgers write
real records, and the hero tests spawn the demo as a subprocess so the
reopen proofs cross a real process boundary and read from disk.
"""
from __future__ import annotations

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

from raphael_ibm_bob.contracts import ActionRequest, Capability, Mission
from raphael_ibm_bob.evidence_ledger import (
    EvidenceLedger,
    LedgerReader,
    create_run_dir,
    generate_run_id,
)


def _mission() -> Mission:
    return Mission(
        mission_id="M-m10-1",
        description="durable runs mission",
        scope="src/",
        criteria=["evidence persists"],
        problem={
            "symptom_target": "src/probe.txt",
            "capability": "read",
            "purpose": "m10:probe",
        },
    )


def _write_one_record(run_dir: Path) -> None:
    """Write a minimal but complete request/decision/result/evidence
    chain plus a gate record, then release the ledger (simulating
    process exit; every append is fsync-durable already)."""
    from raphael_ibm_bob.broker import BOBBroker
    from raphael_ibm_bob.finding import FindingStore
    from raphael_ibm_bob.policy import BOBPolicy
    from raphael_ibm_bob.quality_gate import BOBQualityGate, GateInputs
    from raphael_ibm_bob.runtime import BOBRuntime
    from raphael_ibm_bob.workspace import Workspace

    ws_root = run_dir.parent / "ws"
    (ws_root / "src").mkdir(parents=True, exist_ok=True)
    (ws_root / "src" / "probe.txt").write_text("OK\n", encoding="utf-8")
    workspace = Workspace(ws_root)
    ledger = EvidenceLedger(run_dir)
    policy = BOBPolicy(workspace)
    broker = BOBBroker(policy, workspace, ledger=ledger)
    runtime = BOBRuntime(broker)
    mission = _mission()
    runtime.submit(ActionRequest(
        sequence=0, requester="probe",
        capability=Capability.READ, target="src/probe.txt",
        purpose="m10:probe",
    ), mission)
    gate = BOBQualityGate(ledger)
    gate.evaluate(GateInputs(
        mission=mission, findings=[],
        regression_ok=False, behavior_probe_ok=False,
    ))
    ledger.close()
    del ledger


class RunDirectoryMechanism(unittest.TestCase):
    def test_run_id_is_filesystem_safe(self):
        for _ in range(100):
            rid = generate_run_id()
            self.assertRegex(rid, r"^[0-9A-Za-z_-]+$")
            self.assertNotIn("..", rid)
            self.assertNotIn("/", rid)

    def test_run_ids_are_unique(self):
        self.assertEqual(len({generate_run_id() for _ in range(100)}), 100)

    def test_run_directory_is_created(self):
        base = Path(tempfile.mkdtemp(prefix="m10_runs_"))
        self.addCleanup(shutil.rmtree, base, True)
        run_id, run_dir = create_run_dir(base)
        self.assertTrue(run_dir.is_dir())
        self.assertEqual(run_dir.parent, base)
        self.assertEqual(run_dir.name, run_id)

    def test_evidence_and_artifacts_exist(self):
        base = Path(tempfile.mkdtemp(prefix="m10_runs_"))
        self.addCleanup(shutil.rmtree, base, True)
        _, run_dir = create_run_dir(base)
        _write_one_record(run_dir)
        self.assertTrue((run_dir / "evidence.jsonl").is_file())
        self.assertTrue((run_dir / "artifacts").is_dir())

    def test_each_run_gets_independent_directory(self):
        base = Path(tempfile.mkdtemp(prefix="m10_runs_"))
        self.addCleanup(shutil.rmtree, base, True)
        id1, dir1 = create_run_dir(base)
        id2, dir2 = create_run_dir(base)
        self.assertNotEqual(id1, id2)
        self.assertNotEqual(dir1, dir2)
        _write_one_record(dir1)
        dir2_records = list(LedgerReader(dir2 / "evidence.jsonl").records())
        self.assertEqual(dir2_records, [])

    def test_sequence_numbering_is_per_run(self):
        base = Path(tempfile.mkdtemp(prefix="m10_runs_"))
        self.addCleanup(shutil.rmtree, base, True)
        _, dir1 = create_run_dir(base)
        _, dir2 = create_run_dir(base)
        _write_one_record(dir1)
        _write_one_record(dir2)
        seqs1 = [r.get("seq") for r in
                 LedgerReader(dir1 / "evidence.jsonl").records()]
        seqs2 = [r.get("seq") for r in
                 LedgerReader(dir2 / "evidence.jsonl").records()]
        self.assertEqual(seqs1[0], 1)
        self.assertEqual(seqs2[0], 1)
        self.assertEqual(seqs1, sorted(seqs1))
        self.assertEqual(seqs1, seqs2)

    def test_ledger_reopens_after_completion(self):
        base = Path(tempfile.mkdtemp(prefix="m10_runs_"))
        self.addCleanup(shutil.rmtree, base, True)
        _, run_dir = create_run_dir(base)
        _write_one_record(run_dir)
        # Fresh reader, as a new process would construct it.
        reader = LedgerReader(run_dir / "evidence.jsonl")
        kinds = [r.get("kind") for r in reader.records()]
        for expected in ("request", "decision", "result", "evidence",
                         "gate"):
            self.assertIn(expected, kinds)

    def test_gate_record_survives_reopening(self):
        base = Path(tempfile.mkdtemp(prefix="m10_runs_"))
        self.addCleanup(shutil.rmtree, base, True)
        _, run_dir = create_run_dir(base)
        _write_one_record(run_dir)
        reader = LedgerReader(run_dir / "evidence.jsonl")
        gates = reader.gate_decisions()
        self.assertEqual(len(gates), 1)
        self.assertEqual(gates[0].get("mission_id"), "M-m10-1")
        self.assertIn(gates[0].get("decision"), ("complete", "refuse"))


def _run_hero_subprocess() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "demos/authkit_hero.py"],
        cwd=str(ROOT), capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )


def _evidence_path_from_stdout(stdout: str) -> Path:
    match = re.search(r"^Evidence: (\S+)$", stdout, re.MULTILINE)
    self_assert = match is not None
    assert self_assert, f"no Evidence line in hero output:\n{stdout}"
    return ROOT / match.group(1)


class HeroDurableRuns(unittest.TestCase):
    def test_hero_persists_evidence_locally(self):
        proc = _run_hero_subprocess()
        self.assertEqual(proc.returncode, 0, msg=proc.stderr[-2000:])
        self.assertIn("Gate: COMPLETE", proc.stdout)
        ledger_path = _evidence_path_from_stdout(proc.stdout)
        self.assertTrue(str(ledger_path).startswith(str(ROOT / "runs")))
        self.assertTrue(ledger_path.is_file())
        self.assertGreater(ledger_path.stat().st_size, 0)
        run_dir = ledger_path.parent
        self.assertTrue((run_dir / "artifacts").is_dir())
        # The ledger's artifact references resolve inside the run dir.
        reader = LedgerReader(ledger_path)
        refs = [r.get("artifact_ref") for r in reader.records()
                if r.get("kind") == "result"]
        self.assertTrue(refs)
        for ref in refs:
            self.assertTrue(
                Path(ref).is_file(),
                msg=f"artifact missing from durable run: {ref}")
            self.assertTrue(
                str(Path(ref)).startswith(str(run_dir)),
                msg=f"artifact outside durable run: {ref}")

    def test_second_run_does_not_overwrite_first(self):
        proc1 = _run_hero_subprocess()
        proc2 = _run_hero_subprocess()
        self.assertEqual(proc1.returncode, 0, msg=proc1.stderr[-2000:])
        self.assertEqual(proc2.returncode, 0, msg=proc2.stderr[-2000:])
        id1 = re.search(r"^Run ID: (\S+)$",
                        proc1.stdout, re.MULTILINE).group(1)
        id2 = re.search(r"^Run ID: (\S+)$",
                        proc2.stdout, re.MULTILINE).group(1)
        self.assertNotEqual(id1, id2)
        ledger1 = _evidence_path_from_stdout(proc1.stdout)
        ledger2 = _evidence_path_from_stdout(proc2.stdout)
        self.assertNotEqual(ledger1, ledger2)
        for ledger_path in (ledger1, ledger2):
            reader = LedgerReader(ledger_path)
            gates = reader.gate_decisions()
            self.assertEqual(len(gates), 1)
            self.assertEqual(gates[0].get("decision"), "complete")
            self.assertEqual(gates[0].get("run_id"),
                             ledger_path.parent.name)

    def test_no_tmp_dependency(self):
        proc = _run_hero_subprocess()
        self.assertEqual(proc.returncode, 0, msg=proc.stderr[-2000:])
        ledger_path = _evidence_path_from_stdout(proc.stdout)
        text = ledger_path.read_text(encoding="utf-8")
        self.assertNotIn("authkit_hero_run", text)
        self.assertNotIn("/tmp/", text)


if __name__ == "__main__":
    unittest.main()
