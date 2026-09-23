"""tests/test_d12_1_ledger_integrity.py — G16 ledger integrity + concurrency.

Stdlib-only, threads-based. Covers:

    1. N threads concurrent append -> N dense unique sequences, no corruption.
    2. N threads concurrent transition on distinct findings -> consistent
       final state + ledger order.
    3. N threads concurrent replay registration of the SAME id -> exactly
       one succeeds (existing FindingStore.register guard under the lock).
    4. Tampered stored record -> read-back / seal verification fails.
    5. Read-back invariant: stored evidence + stored digest -> get()
       reproduces the same authenticated content (no reconstruction).

NOTE on scope: `C1AReplayGuard` (c1a_replay.py) is intentionally NOT
covered here — it is outside G16 file ownership and documents
process-local single-threaded use. The replay-registration race test
targets the ledger-backed `FindingStore.register` guard.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from typing import List

from raphael_ibm_bob.contracts import EvidenceReceipt, Finding, FindingState
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, verify_record
from raphael_ibm_bob.finding import FindingStore


def _make_run_dir(testcase: unittest.TestCase) -> Path:
    tmp = tempfile.mkdtemp(prefix="raphael_g16_run_")
    testcase.addCleanup(shutil.rmtree, tmp, True)
    return Path(tmp)


def _finding(fid: str) -> Finding:
    return Finding(
        finding_id=fid,
        state=FindingState.UNVERIFIED,
        summary=f"summary-{fid}",
        target=f"target-{fid}",
        evidence_ids=[],
    )


# -----------------------------------------------------------------------------
# 1. Concurrent append -> dense unique sequences, no corruption
# -----------------------------------------------------------------------------

class ConcurrentAppendDenseUnique(unittest.TestCase):
    def test_n_threads_concurrent_append(self):
        run_dir = _make_run_dir(self)
        ledger = EvidenceLedger(run_dir)
        self.addCleanup(ledger.close)
        n_threads, per_thread = 8, 25
        total = n_threads * per_thread
        barrier = threading.Barrier(n_threads)
        seqs: List[int] = []
        seqs_lock = threading.Lock()
        errors: List[BaseException] = []

        def worker(t: int):
            try:
                barrier.wait(timeout=30)
                for i in range(per_thread):
                    payload = {"thread": t, "i": i, "data": f"ev-{t}-{i}"}
                    seq = ledger.append_evidence(
                        evidence_id=f"E-{t}-{i}",
                        producer="g16",
                        request_seq=0,
                        decision_seq=0,
                        result_seq=None,
                        payload=payload,
                    )
                    with seqs_lock:
                        seqs.append(seq)
            except BaseException as exc:  # noqa: BLE001
                with seqs_lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        self.assertFalse(any(t.is_alive() for t in threads), msg="worker thread hung")
        self.assertEqual(errors, [], msg=f"workers raised: {errors!r}")
        # Dense + unique: exactly 1..N with no gaps or duplicates.
        self.assertEqual(len(seqs), total)
        self.assertEqual(sorted(seqs), list(range(1, total + 1)))
        # No corruption: every line parses and every seal verifies.
        records = ledger.all_records()
        self.assertEqual(len(records), total)
        for rec in records:
            self.assertTrue(verify_record(rec), msg=f"seal failed at seq {rec.get('seq')}")
        # Stored payload survives a full read-back.
        for rec in records:
            back = ledger.get(rec["evidence_id"])
            assert back is not None
            self.assertEqual(back.payload, rec["payload"])


# -----------------------------------------------------------------------------
# 2. Concurrent transition on distinct findings
# -----------------------------------------------------------------------------

class ConcurrentTransitionDistinctFindings(unittest.TestCase):
    def test_n_threads_transition_distinct_findings(self):
        run_dir = _make_run_dir(self)
        ledger = EvidenceLedger(run_dir)
        self.addCleanup(ledger.close)
        store = FindingStore(ledger)
        n = 8
        fids = [f"G16-F{i}" for i in range(n)]
        for fid in fids:
            store.register(_finding(fid))
        barrier = threading.Barrier(n)
        errors: List[BaseException] = []

        def worker(fid: str):
            try:
                barrier.wait(timeout=30)
                store.transition(fid, FindingState.VERIFIED, evidence_seqs=(1,))
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(fid,)) for fid in fids]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        self.assertFalse(any(t.is_alive() for t in threads), msg="worker thread hung")
        self.assertEqual(errors, [], msg=f"workers raised: {errors!r}")
        # Consistent final state: every finding VERIFIED in memory.
        for fid in fids:
            got = store.get(fid)
            self.assertIsNotNone(got)
            assert got is not None
            self.assertEqual(got.state, FindingState.VERIFIED)
        # Consistent ledger order: dense seqs; each finding has exactly
        # [initial(UNVERIFIED), transition(VERIFIED)] in seq order, and the
        # in-memory state matches the latest ledger row (no interleave of
        # ledger order vs memory order).
        records = ledger.all_records()
        self.assertEqual([r["seq"] for r in records], list(range(1, len(records) + 1)))
        for fid in fids:
            rows = store.evidence_for(fid)
            self.assertEqual(len(rows), 2, msg=f"expected 2 rows for {fid}")
            self.assertLess(rows[0]["seq"], rows[1]["seq"])
            self.assertEqual(rows[0]["state"], FindingState.UNVERIFIED.value)
            self.assertIsNone(rows[0]["prev_state"])
            self.assertEqual(rows[1]["state"], FindingState.VERIFIED.value)
            self.assertEqual(rows[1]["prev_state"], FindingState.UNVERIFIED.value)
            mem = store.get(fid)
            assert mem is not None
            self.assertEqual(mem.state.value, rows[-1]["state"])


# -----------------------------------------------------------------------------
# 3. Concurrent replay registration of the SAME id -> exactly one wins
# -----------------------------------------------------------------------------

class ConcurrentReplayRegistrationSameId(unittest.TestCase):
    def test_n_threads_register_same_id_exactly_one_succeeds(self):
        run_dir = _make_run_dir(self)
        ledger = EvidenceLedger(run_dir)
        self.addCleanup(ledger.close)
        store = FindingStore(ledger)
        n = 16
        barrier = threading.Barrier(n)
        won_lock = threading.Lock()
        won: List[str] = []
        rejected = 0
        rejected_lock = threading.Lock()
        errors: List[BaseException] = []

        def worker(t: int):
            nonlocal rejected
            try:
                barrier.wait(timeout=30)
                store.register(_finding("G16-REPLAY"))
                with won_lock:
                    won.append(f"thread-{t}")
            except ValueError:
                with rejected_lock:
                    rejected += 1
            except BaseException as exc:  # noqa: BLE001
                with won_lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        self.assertFalse(any(t.is_alive() for t in threads), msg="worker thread hung")
        self.assertEqual(errors, [], msg=f"unexpected errors: {errors!r}")
        self.assertEqual(len(won), 1, msg=f"expected exactly one winner, got {won!r}")
        self.assertEqual(rejected, n - 1)
        # The single winner is the stored finding; ledger holds one row.
        got = store.get("G16-REPLAY")
        self.assertIsNotNone(got)
        rows = store.evidence_for("G16-REPLAY")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["state"], FindingState.UNVERIFIED.value)

    def test_sequential_double_register_rejected(self):
        run_dir = _make_run_dir(self)
        ledger = EvidenceLedger(run_dir)
        self.addCleanup(ledger.close)
        store = FindingStore(ledger)
        store.register(_finding("G16-DUP"))
        with self.assertRaises(ValueError):
            store.register(_finding("G16-DUP"))


# -----------------------------------------------------------------------------
# 4. Tampered stored record -> read-back / seal verification fails
# -----------------------------------------------------------------------------

class TamperedRecordFailsVerification(unittest.TestCase):
    def _append_one(self, ledger: EvidenceLedger) -> str:
        payload = {"request_seq": 1, "decision_seq": 2, "result": "ok"}
        ledger.append_evidence(
            evidence_id="E-G16-TAMPER",
            producer="g16",
            request_seq=1,
            decision_seq=2,
            result_seq=None,
            payload=payload,
        )
        return "E-G16-TAMPER"

    def _tamper_payload(self, run_dir: Path, evidence_id: str) -> None:
        path = run_dir / "evidence.jsonl"
        lines = path.read_bytes().split(b"\n")
        out = []
        for ln in lines:
            if not ln.strip():
                continue
            obj = json.loads(ln.decode("utf-8"))
            if obj.get("evidence_id") == evidence_id:
                obj["payload"]["result"] = "FORGED"
                # Digest deliberately left stale -> seal must fail.
            out.append(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        path.write_bytes(b"\n".join(out) + b"\n")

    def test_tamper_fails_seal_and_readback(self):
        run_dir = _make_run_dir(self)
        ledger = EvidenceLedger(run_dir)
        self.addCleanup(ledger.close)
        ev_id = self._append_one(ledger)
        # Control: untampered record verifies and reads back.
        raw_before = ledger.reader().by_evidence_id(ev_id)
        self.assertEqual(len(raw_before), 1)
        self.assertTrue(verify_record(raw_before[0]))
        self.assertTrue(ledger.verify(ev_id))
        # Tamper the stored payload bytes on disk.
        self._tamper_payload(run_dir, ev_id)
        raw_after = ledger.reader().by_evidence_id(ev_id)
        self.assertEqual(len(raw_after), 1)
        self.assertEqual(raw_after[0]["payload"]["result"], "FORGED")
        # Seal verification fails (both non-raising paths).
        self.assertFalse(verify_record(raw_after[0]))
        self.assertFalse(ledger.verify(ev_id))
        # Fail-closed read-back: get / by_sequence / all raise, never
        # return the forged content.
        with self.assertRaises(ValueError):
            ledger.get(ev_id)
        with self.assertRaises(ValueError):
            ledger.by_sequence(raw_after[0]["seq"])
        with self.assertRaises(ValueError):
            ledger.all()

    def test_unknown_id_returns_none_and_verify_false(self):
        run_dir = _make_run_dir(self)
        ledger = EvidenceLedger(run_dir)
        self.addCleanup(ledger.close)
        self.assertIsNone(ledger.get("E-DOES-NOT-EXIST"))
        self.assertFalse(ledger.verify("E-DOES-NOT-EXIST"))


# -----------------------------------------------------------------------------
# 5. Read-back invariant: stored evidence + stored digest -> same content
# -----------------------------------------------------------------------------

class ReadBackReproducesStoredContent(unittest.TestCase):
    def test_append_then_get_roundtrip(self):
        run_dir = _make_run_dir(self)
        ledger = EvidenceLedger(run_dir)
        self.addCleanup(ledger.close)
        payload = {"request_seq": 3, "decision_seq": 4, "nested": {"a": [1, 2, 3]}}
        receipt = EvidenceReceipt(
            evidence_id="E-G16-ROUNDTRIP",
            sequence=0,
            producer="g16",
            payload=payload,
        )
        ledger.append(receipt)
        back = ledger.get("E-G16-ROUNDTRIP")
        self.assertIsNotNone(back)
        assert back is not None
        self.assertEqual(back.payload, payload)
        self.assertEqual(back.evidence_id, "E-G16-ROUNDTRIP")
        self.assertEqual(back.producer, "g16")
        # by_sequence / all also return the stored payload (not {}).
        by_seq = ledger.by_sequence(back.sequence)
        self.assertEqual(len(by_seq), 1)
        self.assertEqual(by_seq[0].payload, payload)
        everything = ledger.all()
        self.assertEqual(len(everything), 1)
        self.assertEqual(everything[0].payload, payload)


if __name__ == "__main__":
    unittest.main()
