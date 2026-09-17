"""raphael_ibm_bob.b4_lifecycle — governed lifecycle record + attestation.

Phase 2C B4-LIFECYCLE. Connects RAPHAEL's existing B4 attestation semantics
(``AttestationStatus``/``AttestationCheck``/``AttestationResult``/``ProofSession``)
to the Phase 2C sandbox lifecycle WITHOUT executing any provider.

This module attests LIFECYCLE INTEGRITY ONLY. It deliberately cannot express:
- "lifecycle attested" == "provider executed successfully"
- "teardown observed" == "mission complete"
- "session exists" == "execution authorized"
Authority/authorization keys are rejected, not stored.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple

from raphael_ibm_bob.b4_attestation import (
    AttestationCheck,
    AttestationResult,
    AttestationStatus,
)

#: Ordered lifecycle states. Transitions advance by exactly one step.
class LifecycleState(IntEnum):
    CREATED = 0
    SANDBOX_BOUND = 1
    WORKLOAD_BOUND = 2
    RUNNING = 3
    TEARDOWN_INITIATED = 4
    TEARDOWN_OBSERVED = 5
    CLOSED = 6


#: States that require an evidence reference + sha256 to be recorded.
EVIDENCE_REQUIRED_STATES = frozenset({LifecycleState.TEARDOWN_OBSERVED})

#: Keys that must NEVER appear in a lifecycle record/evidence — they belong to
#: the authorization/quality-gate authority, not to lifecycle integrity.
FORBIDDEN_AUTHORITY_KEYS = frozenset({
    "authorized", "authorization", "execution_authorized", "live_proof",
    "live_proof_authorized", "provider_success", "provider_executed",
    "mission_complete", "quality_gate_complete", "gate_verdict", "complete",
    "tool_executed", "capability_executed", "arsenal_invoked",
    "binary_sink_scan_executed",
})


class LifecycleError(Exception):
    """Fail-closed lifecycle construction/progression error."""


def _is_hex64(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _canonical(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _reject_authority(payload: Any, where: str) -> None:
    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str) and k.strip().lower() in FORBIDDEN_AUTHORITY_KEYS:
                    raise LifecycleError(
                        f"authority key {k!r} is not valid in {where}")
                walk(v)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
    walk(payload)


@dataclass(frozen=True)
class LifecycleTransition:
    """One ordered lifecycle transition with provenance."""
    seq: int
    state: LifecycleState
    at: float
    evidence_ref: Optional[str] = None
    evidence_sha256: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"seq": self.seq, "state": self.state.name, "at": self.at,
                "evidence_ref": self.evidence_ref,
                "evidence_sha256": self.evidence_sha256}


@dataclass
class LifecycleRecord:
    """RAPHAEL-owned lifecycle record for one governed session."""
    lifecycle_id: str
    proof_session_id: str
    sandbox_id: Optional[str] = None
    pid: Optional[int] = None
    pid_starttime: Optional[str] = None
    cgroup: Optional[str] = None
    transitions: List[LifecycleTransition] = field(default_factory=list)

    # --- construction ---------------------------------------------------
    @staticmethod
    def create(lifecycle_id: str, proof_session_id: str) -> "LifecycleRecord":
        if not _valid_id(lifecycle_id):
            raise LifecycleError("missing lifecycle identity")
        if not _valid_id(proof_session_id):
            raise LifecycleError("missing proof-session identity")
        rec = LifecycleRecord(lifecycle_id=lifecycle_id,
                              proof_session_id=proof_session_id)
        rec._append(LifecycleState.CREATED)
        return rec

    def _append(self, state: LifecycleState, evidence_ref: Optional[str] = None,
                evidence_sha256: Optional[str] = None) -> None:
        if self.transitions:
            last = self.transitions[-1].state
            if state != LifecycleState(last + 1):
                raise LifecycleError(
                    f"impossible transition {last.name} -> {state.name}")
        elif state is not LifecycleState.CREATED:
            raise LifecycleError("lifecycle must start at CREATED")
        if state in EVIDENCE_REQUIRED_STATES:
            if not _valid_id(evidence_ref) or not _is_hex64(evidence_sha256):
                raise LifecycleError(
                    f"{state.name} requires evidence_ref + sha256")
        seq = len(self.transitions)
        self.transitions.append(LifecycleTransition(
            seq=seq, state=state, at=float(seq),
            evidence_ref=evidence_ref, evidence_sha256=evidence_sha256))

    @property
    def state(self) -> LifecycleState:
        return self.transitions[-1].state if self.transitions else LifecycleState(-1)

    # --- bindings -------------------------------------------------------
    def bind_sandbox(self, sandbox_id: str) -> None:
        if not _valid_id(sandbox_id):
            raise LifecycleError("missing sandbox identity")
        if self.sandbox_id is not None and self.sandbox_id != sandbox_id:
            raise LifecycleError("mismatched sandbox identity")
        self.sandbox_id = sandbox_id
        self._append(LifecycleState.SANDBOX_BOUND)

    def bind_workload(self, pid: int, pid_starttime: str, cgroup: str) -> None:
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise LifecycleError("invalid workload pid")
        if not _valid_id(pid_starttime):
            raise LifecycleError("missing workload starttime")
        if not _valid_id(cgroup):
            raise LifecycleError("missing cgroup identity")
        self.pid, self.pid_starttime, self.cgroup = pid, pid_starttime, cgroup
        self._append(LifecycleState.WORKLOAD_BOUND)

    def start(self) -> None:
        self._append(LifecycleState.RUNNING)

    def initiate_teardown(self) -> None:
        self._append(LifecycleState.TEARDOWN_INITIATED)

    def observe_teardown(self, evidence_ref: str, evidence_sha256: str) -> None:
        self._append(LifecycleState.TEARDOWN_OBSERVED,
                     evidence_ref=evidence_ref, evidence_sha256=evidence_sha256)

    def close(self) -> None:
        if LifecycleState.TEARDOWN_OBSERVED not in [t.state for t in self.transitions]:
            raise LifecycleError("cannot close without teardown evidence")
        self._append(LifecycleState.CLOSED)

    # --- serialization --------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        body = {"lifecycle_id": self.lifecycle_id,
                "proof_session_id": self.proof_session_id,
                "sandbox_id": self.sandbox_id, "pid": self.pid,
                "pid_starttime": self.pid_starttime, "cgroup": self.cgroup,
                "transitions": [t.to_dict() for t in self.transitions],
                "scope": "lifecycle_integrity_only"}
        _reject_authority(body, "lifecycle record")
        digest = hashlib.sha256(_canonical(body).encode()).hexdigest()
        return {**body, "lifecycle_sha256": digest}

    @staticmethod
    def from_dict(payload: Dict[str, Any]) -> "LifecycleRecord":
        _reject_authority(payload, "lifecycle record")
        rec = LifecycleRecord(lifecycle_id=payload["lifecycle_id"],
                              proof_session_id=payload["proof_session_id"],
                              sandbox_id=payload.get("sandbox_id"))
        for t in payload.get("transitions", []):
            rec.transitions.append(LifecycleTransition(
                seq=t["seq"], state=LifecycleState[t["state"]], at=t["at"],
                evidence_ref=t.get("evidence_ref"),
                evidence_sha256=t.get("evidence_sha256")))
        rec.pid = payload.get("pid"); rec.pid_starttime = payload.get("pid_starttime")
        rec.cgroup = payload.get("cgroup")
        got = payload.get("lifecycle_sha256")
        check = dict(payload); check.pop("lifecycle_sha256", None)
        if got != hashlib.sha256(_canonical(check).encode()).hexdigest():
            raise LifecycleError("lifecycle integrity hash mismatch")
        return rec


def bind_m5_teardown(rec: LifecycleRecord, m5_evidence: Dict[str, Any],
                     reference: str, sha256: str) -> None:
    """Bind accepted M5 teardown evidence into lifecycle closure.

    Fail-closed: requires the M5 artifact to show populated 1 -> 0, a
    terminated target, and an explicit no-provider-execution statement. It
    NEVER implies provider success.
    """
    teardown = m5_evidence.get("teardown", {})
    post = m5_evidence.get("post_kill", {})
    if "populated 1" not in str(teardown.get("events_before")):
        raise LifecycleError("M5 evidence lacks pre-teardown populated=1")
    if "populated 0" not in str(teardown.get("events_after")):
        raise LifecycleError("M5 evidence lacks post-teardown populated=0")
    if not post.get("target_terminated"):
        raise LifecycleError("M5 evidence does not confirm target termination")
    if not m5_evidence.get("no_provider_execution"):
        raise LifecycleError("M5 evidence does not assert no_provider_execution")
    tracked = m5_evidence.get("tracked", {})
    if rec.pid is not None and tracked.get("pid") != rec.pid:
        raise LifecycleError("mismatched workload identity vs M5 evidence")
    if (rec.pid_starttime is not None
            and str(tracked.get("starttime")) != str(rec.pid_starttime)):
        raise LifecycleError("mismatched starttime vs M5 evidence")
    rec.observe_teardown(reference, sha256)


def attest_lifecycle(rec: LifecycleRecord,
                     m5_evidence: Optional[Dict[str, Any]] = None,
                     m5_reference: Optional[str] = None) -> AttestationResult:
    """Attest LIFECYCLE INTEGRITY ONLY (never provider/quality-gate status)."""
    checks: List[AttestationCheck] = []
    failures: List[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append(AttestationCheck(name, ok, detail))
        if not ok:
            failures.append(name)

    check("lifecycle-identity", _valid_id(rec.lifecycle_id))
    check("proof-session-identity", _valid_id(rec.proof_session_id))
    check("sandbox-identity-bound", _valid_id(rec.sandbox_id))
    check("workload-identity-bound",
          isinstance(rec.pid, int) and not isinstance(rec.pid, bool)
          and rec.pid > 0 and _valid_id(rec.pid_starttime) and _valid_id(rec.cgroup))
    seq_ok = [t.seq for t in rec.transitions] == list(range(len(rec.transitions)))
    check("transition-ordering", seq_ok)
    states = [t.state for t in rec.transitions]
    check("transition-contiguity",
          states == [LifecycleState(i) for i in range(len(states))])
    tev = [t for t in rec.transitions if t.state is LifecycleState.TEARDOWN_OBSERVED]
    check("teardown-evidence-present", len(tev) == 1)
    check("teardown-evidence-hashed",
          bool(tev) and _is_hex64(tev[0].evidence_sha256))
    check("closure-after-teardown",
          LifecycleState.CLOSED in states and len(tev) == 1
          and states.index(LifecycleState.CLOSED) > states.index(LifecycleState.TEARDOWN_OBSERVED))
    try:
        _reject_authority(rec.to_dict(), "lifecycle attestation")
        authority_clean = True
    except LifecycleError:
        authority_clean = False
    check("no-authority-smuggling", authority_clean)
    if m5_evidence is not None:
        tracked = m5_evidence.get("tracked", {})
        check("m5-workload-identity-match",
              tracked.get("pid") == rec.pid
              and str(tracked.get("starttime")) == str(rec.pid_starttime))
        check("m5-no-provider-execution", bool(m5_evidence.get("no_provider_execution")))
        check("m5-populated-zero",
              "populated 0" in str(m5_evidence.get("teardown", {}).get("events_after")))
    status = AttestationStatus.ATTESTED if not failures else AttestationStatus.INVALID
    return AttestationResult(
        status=status, proof_session_id=rec.proof_session_id, checks=checks,
        failures=failures,
        reasons=["lifecycle integrity only; no provider or gate authority"],
        quarantined=False,
        evidence={"lifecycle_id": rec.lifecycle_id,
                  "lifecycle_sha256": rec.to_dict()["lifecycle_sha256"],
                  "scope": "lifecycle_integrity_only",
                  "provider_executed": False, "live_proof": False,
                  "m5_reference": m5_reference})


__all__ = [
    "EVIDENCE_REQUIRED_STATES", "FORBIDDEN_AUTHORITY_KEYS", "LifecycleError",
    "LifecycleRecord", "LifecycleState", "LifecycleTransition",
    "attest_lifecycle", "bind_m5_teardown",
]
