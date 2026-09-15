"""raphael_bob.evidence_ledger — M3 append-only JSONL evidence ledger.

This module implements the M1 `EvidenceLedger` Protocol as a durable,
append-only JSONL store. The ledger is the M3 spine:

    ActionRequest
       ↓
    PolicyDecision
       ↓
    ExecutionResult (ALLOW only)
       ↓
    EvidenceReceipt
       ↓
    durable JSONL records under runs/<run_id>/evidence.jsonl

Sequence semantics:
    Each ledger maintains a per-run dense sequence counter. Sequence
    numbers are the canonical ordering key. Wall-clock timestamps are
    attached as additional metadata but MUST NOT be used as the primary
    ordering mechanism (per the M3 determinism rule).

Append-only invariant:
    The public API has only `append_*` methods. There is no public
    `update`, `delete`, `rewrite`, or `truncate` method. The underlying
    file handle is opened with mode `'ab'` for append; the reader is a
    separate object that reconstructs records without mutating the file.

Legacy notes:
    src/orchestrator/brain/evidence.py is the M0/M1 ADAPT candidate.
    The frozen-dataclass + SHA-256 digest pattern is reusable at the
    concept level. The legacy in-memory `EvidenceGraph` with semantic
    `derived_from / supports / contradicts` relations is NOT imported
    here; the BOB MVP uses flat causal links (request_seq, decision_seq,
    result_seq) inside each record, and JSONL records as the source of
    truth. Legacy behavior remains ISOLATE in
    `raphael_bob/adapters/legacy.py`.

M4 additions:
    - `finding_id: Optional[str]` on EvidenceRecord.
    - `RecordKind.FINDING = "finding"` + FindingRecord for transitions.

M6 additions:
    - `RecordKind.GATE = "gate"` + GateRecord for the QualityGate
      decision (COMPLETE / REFUSE + checks + reasons + evidence refs).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from raphael_bob.contracts import (
    ActionRequest,
    EvidenceReceipt,
    ExecutionResult,
    PolicyDecision,
)


# -----------------------------------------------------------------------------
# Clock abstraction (for determinism)
# -----------------------------------------------------------------------------

class _Clock:
    """Default clock returns wall-clock ns. Tests may inject a deterministic clock."""

    def __init__(self) -> None:
        self._fn = self._wall

    def __call__(self) -> int:
        return self._fn()

    def _wall(self) -> int:
        return time.time_ns()

    def set(self, fn) -> None:
        self._fn = fn


DEFAULT_CLOCK = _Clock()
DEFAULT_CLOCK_FN = DEFAULT_CLOCK


# -----------------------------------------------------------------------------
# Record types
# -----------------------------------------------------------------------------

class RecordKind(str, Enum):
    """Kinds of records the ledger can store."""
    REQUEST = "request"
    DECISION = "decision"
    RESULT = "result"
    EVIDENCE = "evidence"
    FINDING = "finding"        # M4: Finding lifecycle transitions
    GATE = "gate"              # M6: QualityGate decision record


def _canonical(payload: Dict[str, Any]) -> str:
    """Deterministic JSON encoding for digest computation."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_id(payload: Dict[str, Any], prefix: str = "E") -> str:
    """Compute a deterministic SHA-256 digest identifier over a canonical payload."""
    h = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return f"{prefix}-{h[:16]}"


# -----------------------------------------------------------------------------
# Durable run directories (M10.1)
# -----------------------------------------------------------------------------

def generate_run_id(stamp: Optional[str] = None) -> str:
    """Build a collision-resistant, filesystem-safe run identifier.

    Shape: `<UTC-timestamp>_<6-hex>`, e.g. `20260915T083012_9f3ac2`.
    The timestamp orders runs; the random suffix prevents collisions
    between runs started in the same second. Run IDs are infrastructure
    labels, not evidence content: never compare them for determinism.
    """
    if stamp is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}_{uuid.uuid4().hex[:6]}"


def create_run_dir(base_dir: Union[str, Path]) -> Tuple[str, Path]:
    """Create an isolated run directory `<base>/<run_id>/` and return both.

    The base is created when missing. Creation uses mkdir-without-exist
    so a colliding run_id is retried, never appended to: two runs never
    share a ledger. The caller hands the path to `EvidenceLedger`,
    which owns `evidence.jsonl` and `artifacts/` inside it.
    """
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    while True:
        run_id = generate_run_id()
        run_dir = base / run_id
        try:
            run_dir.mkdir(parents=False, exist_ok=False)
            return run_id, run_dir
        except FileExistsError:
            continue


def append_run_provenance(ledger: "EvidenceLedger", *, mode: str,
                          mission_id: str, scenario: str) -> int:
    """Record benchmark-mode provenance as ordinary ledger evidence.

    M10.3: harness-owned metadata (`producer="benchmark"`), so the
    core control loop stays untouched. The audit layer reads the
    FIRST such record in a run; runs without one keep `mode=unknown`
    and are excluded from by-mode statistics (never relabeled).
    """
    payload = {
        "kind": "benchmark",
        "mode": mode,
        "mission_id": mission_id,
        "scenario": scenario,
    }
    evidence_id = digest_id(payload, prefix="M")
    return ledger.append_evidence(
        evidence_id=evidence_id,
        producer="benchmark",
        request_seq=0,
        decision_seq=0,
        result_seq=None,
        payload=payload,
    )


@dataclass(frozen=True)
class RequestRecord:
    """A durable ActionRequest record."""
    kind: str
    seq: int
    ts: int
    requester: str
    capability: str
    target: str
    purpose: str
    plan_id: Optional[str]
    finding_id: Optional[str]

    @classmethod
    def build(cls, request: ActionRequest, seq: int, ts: int) -> "RequestRecord":
        return cls(
            kind=RecordKind.REQUEST.value,
            seq=seq,
            ts=ts,
            requester=request.requester,
            capability=request.capability.value if hasattr(request.capability, "value") else str(request.capability),
            target=request.target,
            purpose=request.purpose,
            plan_id=request.plan_id,
            finding_id=request.finding_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionRecord:
    """A durable PolicyDecision record."""
    kind: str
    seq: int
    ts: int
    request_seq: int
    decision: str
    reason: str
    capability: str
    target: str

    @classmethod
    def build(cls, request_seq: int, decision: PolicyDecision, seq: int, ts: int) -> "DecisionRecord":
        return cls(
            kind=RecordKind.DECISION.value,
            seq=seq,
            ts=ts,
            request_seq=request_seq,
            decision=decision.decision.value,
            reason=decision.reason,
            capability=decision.capability.value,
            target=decision.target,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResultRecord:
    """A durable ExecutionResult record. Persisted only on ALLOW."""
    kind: str
    seq: int
    ts: int
    request_seq: int
    decision_seq: int
    success: bool
    output: str
    error: Optional[str]
    artifact_ref: str

    @classmethod
    def build(
        cls,
        request_seq: int,
        decision_seq: int,
        result: ExecutionResult,
        artifact_ref: str,
        seq: int,
        ts: int,
    ) -> "ResultRecord":
        return cls(
            kind=RecordKind.RESULT.value,
            seq=seq,
            ts=ts,
            request_seq=request_seq,
            decision_seq=decision_seq,
            success=result.success,
            output=result.output,
            error=result.error,
            artifact_ref=artifact_ref,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRecord:
    """A durable EvidenceReceipt record."""
    kind: str
    seq: int
    ts: int
    evidence_id: str
    producer: str
    request_seq: int
    decision_seq: int
    result_seq: Optional[int]
    payload: Dict[str, Any]
    digest: str
    finding_id: Optional[str] = None

    @classmethod
    def build(
        cls,
        evidence_id: str,
        producer: str,
        request_seq: int,
        decision_seq: int,
        result_seq: Optional[int],
        seq: int,
        ts: int,
        payload: Dict[str, Any],
        finding_id: Optional[str] = None,
    ) -> "EvidenceRecord":
        return cls(
            kind=RecordKind.EVIDENCE.value,
            seq=seq,
            ts=ts,
            evidence_id=evidence_id,
            producer=producer,
            request_seq=request_seq,
            decision_seq=decision_seq,
            result_seq=result_seq,
            payload=dict(payload),
            digest=hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
            finding_id=finding_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FindingRecord:
    """A durable Finding lifecycle record. Persisted on every transition."""
    kind: str
    seq: int
    ts: int
    finding_id: str
    state: str
    prev_state: Optional[str]
    summary: str
    target: str
    evidence_seqs: Tuple[int, ...]
    digest: str

    @classmethod
    def build(
        cls,
        finding_id: str,
        state: str,
        prev_state: Optional[str],
        summary: str,
        target: str,
        evidence_seqs: Tuple[int, ...],
        seq: int,
        ts: int,
        payload: Dict[str, Any],
    ) -> "FindingRecord":
        return cls(
            kind=RecordKind.FINDING.value,
            seq=seq,
            ts=ts,
            finding_id=finding_id,
            state=state,
            prev_state=prev_state,
            summary=summary,
            target=target,
            evidence_seqs=tuple(int(s) for s in evidence_seqs),
            digest=hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GateRecord:
    """A durable QualityGate decision record (M6).

    Carries the final decision, the checks performed, the evidence
    references that informed the decision, the finding references, and
    the reason(s) for REFUSE.
    """
    kind: str               # RecordKind.GATE.value
    seq: int
    ts: int
    decision: str          # GateVerdict.value
    run_id: str            # ledger run directory name
    mission_id: str
    checks: Tuple[str, ...] # names of conditions that passed/failed
    evidence_refs: Tuple[str, ...]  # evidence_ids
    finding_refs: Tuple[str, ...]   # finding_ids
    reasons: Tuple[str, ...]        # human-readable reasons
    digest: str           # SHA-256 of canonical payload

    @classmethod
    def build(
        cls,
        decision: str,
        run_id: str,
        mission_id: str,
        checks: Tuple[str, ...],
        evidence_refs: Tuple[str, ...],
        finding_refs: Tuple[str, ...],
        reasons: Tuple[str, ...],
        seq: int,
        ts: int,
        payload: Dict[str, Any],
    ) -> "GateRecord":
        return cls(
            kind=RecordKind.GATE.value,
            seq=seq,
            ts=ts,
            decision=decision,
            run_id=run_id,
            mission_id=mission_id,
            checks=tuple(checks),
            evidence_refs=tuple(evidence_refs),
            finding_refs=tuple(finding_refs),
            reasons=tuple(reasons),
            digest=hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest(),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


Record = Union[
    RequestRecord, DecisionRecord, ResultRecord, EvidenceRecord, FindingRecord, GateRecord,
]


# -----------------------------------------------------------------------------
# Artifact sink
# -----------------------------------------------------------------------------

class ArtifactSink:
    """Persists result payloads as JSON files under `runs/<run_id>/artifacts/`.

    The JSONL ledger stores `artifact_ref` (the relative path) rather than the
    payload itself, so the ledger remains a thin index and large payloads do
    not bloat the spine.
    """

    def __init__(self, run_dir: Path):
        self._run_dir = Path(run_dir)
        self._artifacts_dir = self._run_dir / "artifacts"
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, evidence_id: str, payload: Dict[str, Any]) -> Path:
        with self._lock:
            ref = self._artifacts_dir / f"{evidence_id}.json"
            ref.write_text(_canonical(payload), encoding="utf-8")
            return ref

    def path_for(self, evidence_id: str) -> Path:
        return self._artifacts_dir / f"{evidence_id}.json"


# -----------------------------------------------------------------------------
# Append-only writer
# -----------------------------------------------------------------------------

class LedgerWriter:
    """Append-only JSONL writer.

    Public API is append-only. The writer holds a single file handle opened
    in `'ab'` mode so every record is durably persisted to disk before the
    caller observes the return value.
    """

    def __init__(self, path: Path, clock=None):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self._path, "ab", buffering=0)
        self._lock = threading.Lock()
        self._seq = 0
        self._clock = clock if clock is not None else DEFAULT_CLOCK_FN

    def __del__(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass

    def close(self) -> None:
        with self._lock:
            try:
                self._fh.close()
            except Exception:
                pass

    @property
    def path(self) -> Path:
        return self._path

    @property
    def next_seq(self) -> int:
        with self._lock:
            return self._seq + 1

    def _append_line(self, payload: Dict[str, Any]) -> int:
        with self._lock:
            self._seq += 1
            record = dict(payload)
            record["seq"] = self._seq
            line = (_canonical(record) + "\n").encode("utf-8")
            self._fh.write(line)
            self._fh.flush()
            os.fsync(self._fh.fileno())
            return self._seq

    def append_request(self, request: ActionRequest) -> int:
        return self._append_line(
            RequestRecord.build(request, seq=0, ts=self._clock()).to_dict()
        )

    def append_decision(self, request_seq: int, decision: PolicyDecision) -> int:
        return self._append_line(
            DecisionRecord.build(request_seq, decision, seq=0, ts=self._clock()).to_dict()
        )

    def append_result(
        self,
        request_seq: int,
        decision_seq: int,
        result: ExecutionResult,
        artifact_ref: str,
    ) -> int:
        return self._append_line(
            ResultRecord.build(
                request_seq, decision_seq, result, artifact_ref, seq=0, ts=self._clock()
            ).to_dict()
        )

    def append_evidence(
        self,
        evidence_id: str,
        producer: str,
        request_seq: int,
        decision_seq: int,
        result_seq: Optional[int],
        payload: Dict[str, Any],
        finding_id: Optional[str] = None,
    ) -> int:
        rec = EvidenceRecord.build(
            evidence_id=evidence_id,
            producer=producer,
            request_seq=request_seq,
            decision_seq=decision_seq,
            result_seq=result_seq,
            seq=0,
            ts=self._clock(),
            payload=payload,
            finding_id=finding_id,
        )
        return self._append_line(rec.to_dict())

    def append_finding(
        self,
        finding_id: str,
        state: str,
        prev_state: Optional[str],
        summary: str,
        target: str,
        evidence_seqs: Tuple[int, ...],
        payload: Dict[str, Any],
    ) -> int:
        rec = FindingRecord.build(
            finding_id=finding_id,
            state=state,
            prev_state=prev_state,
            summary=summary,
            target=target,
            evidence_seqs=evidence_seqs,
            seq=0,
            ts=self._clock(),
            payload=payload,
        )
        return self._append_line(rec.to_dict())

    def append_gate(
        self,
        decision: str,
        run_id: str,
        mission_id: str,
        checks: Tuple[str, ...],
        evidence_refs: Tuple[str, ...],
        finding_refs: Tuple[str, ...],
        reasons: Tuple[str, ...],
        payload: Dict[str, Any],
    ) -> int:
        rec = GateRecord.build(
            decision=decision,
            run_id=run_id,
            mission_id=mission_id,
            checks=checks,
            evidence_refs=evidence_refs,
            finding_refs=finding_refs,
            reasons=reasons,
            seq=0,
            ts=self._clock(),
            payload=payload,
        )
        return self._append_line(rec.to_dict())


# -----------------------------------------------------------------------------
# Reader
# -----------------------------------------------------------------------------

class LedgerReader:
    """Reads JSONL records from a ledger file. Stateless and non-mutating."""

    def __init__(self, path: Path):
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def records(self) -> Iterator[Dict[str, Any]]:
        """Yield every parsed record. Raises ValueError on corrupt lines."""
        if not self._path.exists():
            return
        with open(self._path, "rb") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"corrupt ledger record at {self._path}: {e}"
                    ) from e
                yield obj

    def all(self) -> List[Dict[str, Any]]:
        return list(self.records())

    def by_kind(self, kind: str) -> List[Dict[str, Any]]:
        return [r for r in self.records() if r.get("kind") == kind]

    def by_request_seq(self, request_seq: int) -> List[Dict[str, Any]]:
        return [r for r in self.records() if r.get("request_seq") == request_seq]

    def by_evidence_id(self, evidence_id: str) -> List[Dict[str, Any]]:
        return [r for r in self.records() if r.get("evidence_id") == evidence_id]

    def by_finding_id(self, finding_id: str) -> List[Dict[str, Any]]:
        return [r for r in self.records() if r.get("finding_id") == finding_id]

    def gate_decisions(self) -> List[Dict[str, Any]]:
        return [r for r in self.records() if r.get("kind") == RecordKind.GATE.value]


# -----------------------------------------------------------------------------
# M1 EvidenceLedger Protocol implementation
# -----------------------------------------------------------------------------

class EvidenceLedger:
    """JSONL-backed EvidenceLedger that satisfies the M1 Protocol.

    The instance composes a `LedgerWriter` (for append) and an `ArtifactSink`
    (for result payloads). Reads are delegated to a fresh `LedgerReader`
    constructed on demand so reopening the file is straightforward.
    """

    def __init__(self, run_dir: Path, clock=None):
        self._run_dir = Path(run_dir)
        self._run_dir.mkdir(parents=True, exist_ok=True)
        ledger_path = self._run_dir / "evidence.jsonl"
        self._writer = LedgerWriter(ledger_path, clock=clock)
        self._artifacts = ArtifactSink(self._run_dir)
        self._reader = LedgerReader(ledger_path)

    # --- M1 EvidenceLedger Protocol ----------------------------------------

    def append(self, receipt: EvidenceReceipt) -> str:
        """Persist an `EvidenceReceipt` (the contract type) and return its id."""
        payload = receipt.payload
        ev_id = receipt.evidence_id or digest_id(
            {"producer": receipt.producer, "payload": payload}, prefix="E"
        )
        self._writer.append_evidence(
            evidence_id=ev_id,
            producer=receipt.producer,
            request_seq=int(payload.get("request_seq", -1)),
            decision_seq=int(payload.get("decision_seq", -1)),
            result_seq=payload.get("result_seq"),
            payload=payload,
        )
        return ev_id

    def get(self, evidence_id: str) -> Optional[EvidenceReceipt]:
        for rec in self._reader.by_evidence_id(evidence_id):
            return EvidenceReceipt(
                evidence_id=evidence_id,
                sequence=rec.get("seq", 0),
                producer=rec.get("producer", ""),
                payload={k: v for k, v in rec.items() if k not in {
                    "kind", "seq", "ts", "evidence_id", "producer",
                    "request_seq", "decision_seq", "result_seq", "digest",
                }},
            )
        return None

    def by_sequence(self, sequence: int) -> List[EvidenceReceipt]:
        out: List[EvidenceReceipt] = []
        for rec in self._reader.by_kind(RecordKind.EVIDENCE.value):
            if rec.get("seq") == sequence:
                out.append(EvidenceReceipt(
                    evidence_id=rec.get("evidence_id", ""),
                    sequence=rec.get("seq", 0),
                    producer=rec.get("producer", ""),
                    payload={},
                ))
        return out

    def all(self) -> List[EvidenceReceipt]:
        return [
            EvidenceReceipt(
                evidence_id=rec.get("evidence_id", ""),
                sequence=rec.get("seq", 0),
                producer=rec.get("producer", ""),
                payload={},
            )
            for rec in self._reader.by_kind(RecordKind.EVIDENCE.value)
        ]

    # --- M3 record append helpers -----------------------------------------

    def append_request(self, request: ActionRequest) -> int:
        return self._writer.append_request(request)

    def append_decision(self, request_seq: int, decision: PolicyDecision) -> int:
        return self._writer.append_decision(request_seq, decision)

    def append_result(
        self,
        request_seq: int,
        decision_seq: int,
        result: ExecutionResult,
    ) -> int:
        evidence_id = digest_id({
            "request_seq": request_seq,
            "decision_seq": decision_seq,
            "result": result.to_dict(),
        }, prefix="R")
        artifact_ref = str(self._artifacts.write(evidence_id, result.to_dict()))
        return self._writer.append_result(
            request_seq, decision_seq, result, artifact_ref
        )

    def append_evidence(
        self,
        evidence_id: str,
        producer: str,
        request_seq: int,
        decision_seq: int,
        result_seq: Optional[int],
        payload: Dict[str, Any],
        finding_id: Optional[str] = None,
    ) -> int:
        return self._writer.append_evidence(
            evidence_id, producer, request_seq, decision_seq, result_seq, payload,
            finding_id=finding_id,
        )

    def append_finding(
        self,
        finding_id: str,
        state: str,
        prev_state: Optional[str],
        summary: str,
        target: str,
        evidence_seqs: Tuple[int, ...],
        payload: Dict[str, Any],
    ) -> int:
        return self._writer.append_finding(
            finding_id, state, prev_state, summary, target, evidence_seqs, payload
        )

    def append_gate(
        self,
        decision: str,
        run_id: str,
        mission_id: str,
        checks: Tuple[str, ...],
        evidence_refs: Tuple[str, ...],
        finding_refs: Tuple[str, ...],
        reasons: Tuple[str, ...],
        payload: Dict[str, Any],
    ) -> int:
        return self._writer.append_gate(
            decision, run_id, mission_id, checks,
            evidence_refs, finding_refs, reasons, payload,
        )

    def records_for_finding(self, finding_id: str) -> List[Dict[str, Any]]:
        """Return every ledger record linked to the given finding_id.

        Combines FindingRecord rows + EvidenceRecord rows that carry the
        same `finding_id` field. Sorted by ledger seq. Returns [] if no match.
        """
        out: List[Dict[str, Any]] = []
        for rec in self._reader.all():
            if rec.get("finding_id") == finding_id:
                out.append(rec)
        out.sort(key=lambda r: r.get("seq", 0))
        return out

    def gate_decisions(self) -> List[Dict[str, Any]]:
        return self._reader.gate_decisions()

    # --- Convenience getters -----------------------------------------------

    def run_dir(self) -> Path:
        return self._run_dir

    def ledger_path(self) -> Path:
        return self._writer.path

    def close(self) -> None:
        """Flush and release the ledger file handle.

        Every append is already fsync-durable before it returns, so
        close is lifecycle hygiene, not a durability requirement: a
        reopened `LedgerReader` sees all records even if the writer was
        never explicitly closed.
        """
        self._writer.close()

    def reader(self) -> LedgerReader:
        return LedgerReader(self._writer.path)

    def all_records(self) -> List[Dict[str, Any]]:
        return self._reader.all()

    def records_by_kind(self, kind: str) -> List[Dict[str, Any]]:
        return self._reader.by_kind(kind)


__all__ = [
    "RecordKind",
    "RequestRecord",
    "DecisionRecord",
    "ResultRecord",
    "EvidenceRecord",
    "FindingRecord",
    "GateRecord",
    "Record",
    "digest_id",
    "generate_run_id",
    "create_run_dir",
    "append_run_provenance",
    "LedgerWriter",
    "LedgerReader",
    "EvidenceLedger",
    "ArtifactSink",
    "DEFAULT_CLOCK",
    "DEFAULT_CLOCK_FN",
]