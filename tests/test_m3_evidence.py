"""tests/test_m3_evidence.py — M3 evidence ledger tests.

Stdlib-only. Real Runtime + Broker + Policy + EvidenceLedger path. NO mocks.

Coverage:
    1. allowed action creates durable ledger evidence
    2. denied action creates durable denial evidence
    3. request/result linkage is correct
    4. evidence IDs are populated
    5. sequence ordering is deterministic
    6. JSONL records are parseable
    7. append-only behavior is enforced
    8. prior records remain unchanged after new appends
    9. ledger can be reopened and read
   10. no execution record exists for a denied capability
   11. partial write / corrupt / collision / duplicate / update / delete paths
"""
from __future__ import annotations

import json
import os
import tempfile
import textwrap
import threading
import unittest
from pathlib import Path
from typing import List

from raphael_ibm_bob import (
    ActionRequest,
    Capability,
    Decision,
    Mission,
)
from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.evidence_ledger import (
    EvidenceLedger,
    LedgerReader,
    LedgerWriter,
    digest_id,
)
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.workspace import Workspace


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

def _make_workspace(testcase: unittest.TestCase) -> Path:
    """Create a temporary workspace with a known file structure."""
    tmp = tempfile.mkdtemp(prefix="raphael_ibm_bob_m3_ws_")
    root = Path(tmp)
    (root / "src").mkdir()
    (root / "src" / "hello.txt").write_text("hello-m3\n", encoding="utf-8")
    (root / "src" / "authkit").mkdir()
    (root / "src" / "authkit" / "store.py").write_text("STORE = {}\n", encoding="utf-8")
    (root / "src" / "authkit" / "session.py").write_text(
        "def session(): return {}\n", encoding="utf-8"
    )
    (root / "src" / "test_smoke.py").write_text(textwrap.dedent("""
        import unittest
        class T(unittest.TestCase):
            def test_true(self):
                self.assertTrue(True)
        if __name__ == "__main__":
            unittest.main()
    """).strip() + "\n", encoding="utf-8")
    testcase.addCleanup(_rm, root)
    return root


def _make_run_dir(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.mkdtemp(prefix="raphael_ibm_bob_m3_run_")
    testcase.addCleanup(_rm, Path(tmp))
    return Path(tmp)


def _rm(p: Path) -> None:
    import shutil
    shutil.rmtree(p, ignore_errors=True)


def _mission(scope: str = "src/") -> Mission:
    return Mission(
        mission_id="M-test", description="authkit fix", scope=scope,
        criteria=["all named tests pass", "behavior probe passes"],
    )


class _Harness:
    """Convenience bundle for M3 tests."""

    def __init__(self, workspace: Workspace, ledger: EvidenceLedger,
                 broker: BOBBroker, runtime: BOBRuntime, scope: str):
        self.workspace = workspace
        self.ledger = ledger
        self.broker = broker
        self.runtime = runtime
        self.mission = _mission(scope)

    def request(self, cap: Capability, target: str, purpose: str = "p",
                requester: str = "agent"):
        return ActionRequest(
            sequence=0,
            requester=requester,
            capability=cap,
            target=target,
            purpose=purpose,
        )


def _harness(testcase: unittest.TestCase, scope: str = "src/") -> _Harness:
    ws_root = _make_workspace(testcase)
    run_root = _make_run_dir(testcase)
    workspace = Workspace(ws_root)
    ledger = EvidenceLedger(run_root)
    policy = BOBPolicy(workspace)
    broker = BOBBroker(policy, workspace, ledger=ledger)
    runtime = BOBRuntime(broker)
    return _Harness(workspace, ledger, broker, runtime, scope)


# -----------------------------------------------------------------------------
# 1. Allowed action creates durable ledger evidence
# -----------------------------------------------------------------------------

class AllowedActionCreatesEvidence(unittest.TestCase):
    def test_allow_path_persists_request_decision_result_evidence(self):
        h = _harness(self)
        result = h.runtime.submit(
            h.request(Capability.READ, "src/hello.txt", purpose="read"),
            h.mission,
        )
        rec = h.ledger.all_records()
        kinds = [r.get("kind") for r in rec]
        self.assertIn("request", kinds)
        self.assertIn("decision", kinds)
        self.assertIn("result", kinds)
        self.assertIn("evidence", kinds)
        ev_records = [r for r in rec if r.get("kind") == "evidence"]
        producers = sorted({r.get("producer") for r in ev_records})
        self.assertIn("policy", producers)
        self.assertIn("execution", producers)
        self.assertGreaterEqual(len(result.evidence_ids), 2)


# -----------------------------------------------------------------------------
# 2. Denied action creates durable denial evidence
# -----------------------------------------------------------------------------

class DeniedActionCreatesEvidence(unittest.TestCase):
    def test_deny_path_persists_request_decision_evidence_only(self):
        h = _harness(self)
        result = h.runtime.submit(
            h.request(Capability.WRITE, "/tmp/escape.txt", purpose="content=x"),
            h.mission,
        )
        rec = h.ledger.all_records()
        kinds = [r.get("kind") for r in rec]
        self.assertIn("request", kinds)
        self.assertIn("decision", kinds)
        self.assertNotIn("result", kinds)
        ev_records = [r for r in rec if r.get("kind") == "evidence"]
        self.assertGreaterEqual(len(ev_records), 1)
        policy_ev = [r for r in ev_records if r.get("producer") == "policy"]
        self.assertEqual(len(policy_ev), 1)
        decision_rec = [r for r in rec if r.get("kind") == "decision"][-1]
        self.assertEqual(decision_rec.get("decision"), "deny")
        self.assertEqual(policy_ev[0].get("decision_seq"), decision_rec.get("seq"))
        self.assertFalse(result.broker_result.capability_invoked)
        self.assertIsNone(result.execution)
        self.assertIsNone(result.result_seq)


# -----------------------------------------------------------------------------
# 3. request/result linkage
# -----------------------------------------------------------------------------

class RequestResultLinkage(unittest.TestCase):
    def test_evidence_records_link_back_to_request_and_decision(self):
        h = _harness(self)
        h.runtime.submit(
            h.request(Capability.READ, "src/hello.txt"), h.mission,
        )
        rec = h.ledger.all_records()
        rq = [r for r in rec if r.get("kind") == "request"][-1]
        dec = [r for r in rec if r.get("kind") == "decision"][-1]
        res = [r for r in rec if r.get("kind") == "result"][-1]
        ev_pol = [r for r in rec if r.get("kind") == "evidence" and r.get("producer") == "policy"][-1]
        ev_exec = [r for r in rec if r.get("kind") == "evidence" and r.get("producer") == "execution"][-1]
        self.assertEqual(dec.get("request_seq"), rq.get("seq"))
        self.assertEqual(res.get("request_seq"), rq.get("seq"))
        self.assertEqual(res.get("decision_seq"), dec.get("seq"))
        self.assertEqual(ev_pol.get("request_seq"), rq.get("seq"))
        self.assertEqual(ev_pol.get("decision_seq"), dec.get("seq"))
        self.assertEqual(ev_exec.get("result_seq"), res.get("seq"))


# -----------------------------------------------------------------------------
# 4. evidence IDs are populated
# -----------------------------------------------------------------------------

class EvidenceIDsPopulated(unittest.TestCase):
    def test_every_evidence_record_has_a_nonzero_digest_id(self):
        h = _harness(self)
        h.runtime.submit(
            h.request(Capability.READ, "src/hello.txt"), h.mission,
        )
        rec = h.ledger.all_records()
        evs = [r for r in rec if r.get("kind") == "evidence"]
        self.assertGreater(len(evs), 0)
        for ev in evs:
            self.assertTrue(ev.get("evidence_id"))
            self.assertTrue(ev.get("digest"))
            self.assertEqual(len(ev["digest"]), 64)  # SHA-256 hex


# -----------------------------------------------------------------------------
# 5. sequence ordering is deterministic
# -----------------------------------------------------------------------------

class SequenceOrderingDeterministic(unittest.TestCase):
    def test_sequence_numbers_are_dense_and_strictly_increasing(self):
        h = _harness(self)
        for i in range(5):
            cap = Capability.READ if i % 2 == 0 else Capability.LIST
            target = "src/hello.txt" if cap is Capability.READ else "src/"
            h.runtime.submit(h.request(cap, target, purpose=f"p{i}"), h.mission)
        rec = h.ledger.all_records()
        seqs = [r.get("seq") for r in rec]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(seqs[0], 1)
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))

    def test_injected_clock_does_not_affect_seq(self):
        ws_root = _make_workspace(self)
        run_root = _make_run_dir(self)
        class FakeClock:
            def __call__(self):
                return 1000
        ledger = EvidenceLedger(run_root, clock=FakeClock())
        ws = Workspace(ws_root)
        b = BOBBroker(BOBPolicy(ws), ws, ledger=ledger)
        rt = BOBRuntime(b)
        m = _mission()
        for _ in range(3):
            rt.submit(ActionRequest(sequence=0, requester="a",
                                    capability=Capability.READ,
                                    target="hello.txt",
                                    purpose="p"), m)
        seqs = [r.get("seq") for r in ledger.all_records()]
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))


# -----------------------------------------------------------------------------
# 6. JSONL records are parseable
# -----------------------------------------------------------------------------

class JSONLParseable(unittest.TestCase):
    def test_ledger_file_is_line_delimited_valid_json(self):
        h = _harness(self)
        h.runtime.submit(
            h.request(Capability.READ, "src/hello.txt"), h.mission,
        )
        path = h.ledger.ledger_path()
        with open(path, "rb") as fh:
            lines = [ln for ln in fh.read().split(b"\n") if ln.strip()]
        self.assertGreater(len(lines), 0)
        for ln in lines:
            obj = json.loads(ln.decode("utf-8"))
            self.assertIsInstance(obj, dict)
            self.assertIn("seq", obj)
            self.assertIn("kind", obj)
            self.assertIn("ts", obj)


# -----------------------------------------------------------------------------
# 7. append-only behavior is enforced
# -----------------------------------------------------------------------------

class AppendOnlyEnforced(unittest.TestCase):
    def test_writer_public_api_has_no_update_delete_rewrite(self):
        public = [n for n in dir(LedgerWriter) if not n.startswith("_")]
        for forbidden in ("update", "delete", "rewrite", "truncate", "pop", "remove"):
            self.assertNotIn(forbidden, public, msg=f"LedgerWriter exposes {forbidden}()")

    def test_writing_a_record_does_not_rewrite_prior_records(self):
        h = _harness(self)
        h.runtime.submit(
            h.request(Capability.READ, "src/hello.txt"), h.mission,
        )
        path = h.ledger.ledger_path()
        before = path.read_bytes()
        h.runtime.submit(
            h.request(Capability.LIST, "src/"), h.mission,
        )
        after = path.read_bytes()
        self.assertTrue(after.startswith(before),
                        msg="ledger tail was rewritten; append-only invariant violated")
        self.assertGreater(len(after), len(before))

    def test_corrupt_tail_is_detected_by_reader(self):
        h = _harness(self)
        h.runtime.submit(
            h.request(Capability.READ, "src/hello.txt"), h.mission,
        )
        path = h.ledger.ledger_path()
        with open(path, "ab") as fh:
            fh.write(b"NOT-VALID-JSON\n")
        with self.assertRaises(ValueError):
            list(h.ledger.reader().records())


# -----------------------------------------------------------------------------
# 8. prior records remain unchanged
# -----------------------------------------------------------------------------

class PriorRecordsImmutable(unittest.TestCase):
    def test_record_digest_is_stable_across_subsequent_appends(self):
        h = _harness(self)
        h.runtime.submit(
            h.request(Capability.READ, "src/hello.txt"), h.mission,
        )
        first_ev = [r for r in h.ledger.all_records()
                    if r.get("kind") == "evidence"][0]
        digest_before = first_ev.get("digest")
        ev_id_before = first_ev.get("evidence_id")
        seq_before = first_ev.get("seq")
        for _ in range(3):
            h.runtime.submit(
                h.request(Capability.LIST, "src/"), h.mission,
            )
        rec = h.ledger.all_records()
        first_ev_after = [r for r in rec if r.get("kind") == "evidence"][0]
        self.assertEqual(first_ev_after.get("digest"), digest_before)
        self.assertEqual(first_ev_after.get("evidence_id"), ev_id_before)
        self.assertEqual(first_ev_after.get("seq"), seq_before)


# -----------------------------------------------------------------------------
# 9. ledger can be reopened and read
# -----------------------------------------------------------------------------

class ReopenAndRead(unittest.TestCase):
    def test_reopen_reader_sees_full_history(self):
        ws_root = _make_workspace(self)
        run_root = _make_run_dir(self)
        ledger = EvidenceLedger(run_root)
        ws = Workspace(ws_root)
        b = BOBBroker(BOBPolicy(ws), ws, ledger=ledger)
        rt = BOBRuntime(b)
        # Target must be inside the workspace; hello.txt is at src/hello.txt.
        m = Mission(mission_id="M-test", description="authkit fix", scope="src/")
        rt.submit(ActionRequest(sequence=0, requester="a",
                                capability=Capability.READ,
                                target="src/hello.txt",
                                purpose="p"), m)
        ledger._writer.close()
        reopened = EvidenceLedger(run_root)
        rec = reopened.all_records()
        self.assertGreater(len(rec), 0)
        kinds = [r.get("kind") for r in rec]
        self.assertIn("request", kinds)
        self.assertIn("decision", kinds)
        self.assertIn("result", kinds)
        self.assertIn("evidence", kinds)
# -----------------------------------------------------------------------------

class NoExecutionOnDeny(unittest.TestCase):
    def test_denied_request_has_no_result_record(self):
        h = _harness(self)
        h.runtime.submit(
            h.request(Capability.WRITE, "/tmp/escape.txt", purpose="content=x"),
            h.mission,
        )
        rec = h.ledger.all_records()
        result_records = [r for r in rec if r.get("kind") == "result"]
        self.assertEqual(len(result_records), 0)
        exec_ev = [r for r in rec if r.get("kind") == "evidence" and r.get("producer") == "execution"]
        self.assertEqual(len(exec_ev), 0)

    def test_denied_request_does_not_create_artifacts(self):
        h = _harness(self)
        before = set(p.name for p in h.ledger._artifacts._artifacts_dir.iterdir())
        h.runtime.submit(
            h.request(Capability.WRITE, "/tmp/escape.txt", purpose="content=x"),
            h.mission,
        )
        after = set(p.name for p in h.ledger._artifacts._artifacts_dir.iterdir())
        self.assertEqual(before, after)


# -----------------------------------------------------------------------------
# 11. Failure modes
# -----------------------------------------------------------------------------

class FailureModes(unittest.TestCase):
    def test_sequence_collision_is_handled_by_sequential_lock(self):
        run_root = _make_run_dir(self)
        writer = LedgerWriter(run_root / "evidence.jsonl")
        N = 100
        seqs: List[int] = []
        def worker():
            for _ in range(N):
                seqs.append(writer.append_evidence(
                    evidence_id=digest_id({"x": len(seqs)}, prefix="X"),
                    producer="test",
                    request_seq=0,
                    decision_seq=0,
                    result_seq=None,
                    payload={"x": len(seqs)},
                ))
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(set(seqs)), len(seqs))
        self.assertEqual(min(seqs), 1)
        self.assertEqual(max(seqs), 4 * N)

    def test_corrupt_record_raises_on_read(self):
        run_root = _make_run_dir(self)
        ledger_path = run_root / "evidence.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger_path, "wb") as fh:
            fh.write(b'{"kind":"request","seq":1,"ts":0}\n')
            fh.write(b"not-valid-json\n")
        reader = LedgerReader(ledger_path)
        with self.assertRaises(ValueError):
            list(reader.records())

    def test_partial_write_does_not_corrupt_prior_records(self):
        ws_root = _make_workspace(self)
        run_root = _make_run_dir(self)
        ledger = EvidenceLedger(run_root)
        ws = Workspace(ws_root)
        b = BOBBroker(BOBPolicy(ws), ws, ledger=ledger)
        rt = BOBRuntime(b)
        m = _mission()
        rt.submit(ActionRequest(sequence=0, requester="a",
                                capability=Capability.READ,
                                target="hello.txt",
                                purpose="p"), m)
        with open(ledger.ledger_path(), "ab") as fh:
            fh.write(b'{"kind":"request","seq":99,"ts":0}\nALMOST-')
        with self.assertRaises(ValueError):
            list(ledger.reader().records())

    def test_duplicate_append_yields_distinct_records(self):
        run_root = _make_run_dir(self)
        writer = LedgerWriter(run_root / "evidence.jsonl")
        payload = {"x": 1}
        eid = digest_id(payload, prefix="D")
        s1 = writer.append_evidence(eid, "test", 0, 0, None, payload)
        s2 = writer.append_evidence(eid, "test", 0, 0, None, payload)
        self.assertNotEqual(s1, s2)
        rec = LedgerReader(run_root / "evidence.jsonl").all()
        self.assertEqual(len(rec), 2)
        self.assertEqual(rec[0]["seq"], s1)
        self.assertEqual(rec[1]["seq"], s2)

    def test_public_api_has_no_update_or_delete(self):
        for cls in (LedgerWriter, EvidenceLedger):
            public = [n for n in dir(cls) if not n.startswith("_")]
            for forbidden in ("update", "delete", "rewrite", "truncate", "pop", "remove"):
                self.assertNotIn(
                    forbidden, public,
                    msg=f"{cls.__name__} exposes {forbidden}()",
                )


# -----------------------------------------------------------------------------
# 12. Digest determinism
# -----------------------------------------------------------------------------

class DigestDeterminism(unittest.TestCase):
    def test_same_payload_produces_same_evidence_id(self):
        payload = {"a": 1, "b": [2, 3]}
        self.assertEqual(digest_id(payload), digest_id(payload))

    def test_key_order_does_not_affect_digest(self):
        self.assertEqual(digest_id({"a": 1, "b": 2}), digest_id({"b": 2, "a": 1}))


# -----------------------------------------------------------------------------
# 13. No network
# -----------------------------------------------------------------------------

class NoNetwork(unittest.TestCase):
    def test_no_network_imports_in_evidence_ledger(self):
        from pathlib import Path
        target = Path(__file__).resolve().parent.parent / "raphael_ibm_bob" / "evidence_ledger.py"
        text = target.read_text(encoding="utf-8")
        forbidden = ["import socket", "import urllib", "import httpx",
                     "import requests", "import aiohttp", "import http.client"]
        for f in forbidden:
            self.assertNotIn(f, text, msg=f"evidence_ledger.py contains {f}")

if __name__ == "__main__":
    unittest.main()