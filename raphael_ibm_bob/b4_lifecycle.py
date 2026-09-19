"""raphael_ibm_bob.b4_lifecycle — governed lifecycle record + attestation.

Phase 2C B4-LIFECYCLE. Connects RAPHAEL's existing B4 attestation semantics
(``AttestationStatus``/``AttestationCheck``/``AttestationResult``/``ProofSession``)
to the Phase 2C sandbox lifecycle WITHOUT executing any provider.

This module attests LIFECYCLE INTEGRITY ONLY. It deliberately cannot express:

    "lifecycle attested"          == "provider executed successfully"
    "teardown observed"           == "mission complete"
    "session exists"              == "execution authorized"
    "lifecycle scope"             == "authorization"
    "lifecycle scope"             == "provider execution"
    "lifecycle scope"             == "mission completion"

Authority/authorization keys are rejected, not stored.

Semantics (R1-R7 corrective closure):

R1 teardown provenance
    Every ``TEARDOWN_OBSERVED`` transition carries an explicit, serialized
    ``provenance``: either ``"direct"`` (an unbound local observation) or
    ``"m5-bound"`` (the observation is bound to an accepted M5 teardown
    artifact). The provenance and the M5 reference/digest live on the
    transition, are serialized by :meth:`LifecycleRecord.to_dict`, and are
    therefore covered by ``lifecycle_sha256``. :func:`attest_lifecycle`
    exposes them.

R2 fail-closed closure
    ``close()`` requires an ``M5-bound`` teardown transition with a non-None
    M5 reference. A direct (M5-less) observation can never close the record,
    and an M5-less record can never produce a successful lifecycle
    attestation. The previously demonstrated
    ``observe_teardown -> close -> CLOSED`` false closure is eliminated.

R3 strict booleans
    :func:`bind_m5_teardown` accepts ``target_terminated`` and
    ``no_provider_execution`` only when they are the boolean ``True``.
    ``1``, ``"true"``, and any other truthy object are rejected; values are
    never coerced.

R4 atomic rebind
    Identity mismatches are validated BEFORE any state mutation. A failed
    ``bind_sandbox`` / ``bind_workload`` / :func:`bind_m5_teardown` leaves the
    record exactly as it was. An identity-preserving rebind is a no-op.

R5 semantics documentation
    * ``at`` is an ORDINAL ordering counter (0,1,2,...), NEVER wall-clock
      time. It is not comparable across runs.
    * The authority-key rejection is a STRUCTURAL key-name check only (exact
      lowercased names in :data:`FORBIDDEN_AUTHORITY_KEYS`); it is not a
      content classifier and does not inspect values.
    * ``lifecycle_sha256`` is TAMPER EVIDENCE ONLY, not authentication. It
      detects an accidental or inconsistent edit; it does not authenticate a
      writer and is unkeyed.

R6 file digest helper
    :func:`sha256_file` / :func:`verify_file_sha256` hash ACTUAL file bytes
    and fail closed on a missing/unreadable file. A caller-supplied SHA is
    recorded as provenance; it is never treated as proof of content unless
    independently verified with these helpers.

R7 regression tests
    ``tests/test_b4_lifecycle.py`` covers direct-vs-M5 closure, provenance
    serialization + hash coverage, strict booleans, atomic rebind, hash
    tampering, M5 reference tampering, and the historical false-closure
    attacks. Tests assert behavior/artifacts, never ``PASS`` strings.
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

#: R1 — explicit teardown provenance taxonomy.
TEARDOWN_PROVENANCE_DIRECT = "direct"
TEARDOWN_PROVENANCE_M5_BOUND = "m5-bound"
_VALID_TEARDOWN_PROVENANCE = frozenset({
    TEARDOWN_PROVENANCE_DIRECT, TEARDOWN_PROVENANCE_M5_BOUND})


class LifecycleError(Exception):
    """Fail-closed lifecycle construction/progression error."""


def _is_hex64(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip() != ""


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


# ---------------------------------------------------------------------------
# R6 — file digest helpers (content verification, fail-closed)
# ---------------------------------------------------------------------------

def sha256_file(path: str) -> str:
    """Return the SHA-256 of the ACTUAL bytes of ``path``.

    Fails closed (``LifecycleError``) on a missing/unreadable path. This is
    the only per-content proof the module offers; a caller-supplied digest is
    never substituted for it.
    """
    handle = None
    try:
        handle = open(path, "rb")
        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise LifecycleError(
            f"cannot hash file {path!r}: {type(exc).__name__}") from None
    finally:
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass


def verify_file_sha256(path: str, expected: Any) -> bool:
    """True iff ``path`` exists and its actual SHA-256 equals ``expected``.

    Fails closed (False) on an invalid expected digest or an unreadable file.
    Never treats a caller-supplied digest as proof by itself.
    """
    if not _is_hex64(expected):
        return False
    try:
        return sha256_file(path) == expected
    except LifecycleError:
        return False


# ---------------------------------------------------------------------------
# Transition + record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LifecycleTransition:
    """One ordered lifecycle transition with provenance.

    ``at`` is an ORDINAL counter (see R5), not wall-clock time.
    ``provenance`` / ``m5_reference`` / ``m5_sha256`` are meaningful on the
    ``TEARDOWN_OBSERVED`` transition and are ``None`` elsewhere.
    """
    seq: int
    state: LifecycleState
    at: float
    evidence_ref: Optional[str] = None
    evidence_sha256: Optional[str] = None
    provenance: Optional[str] = None
    m5_reference: Optional[str] = None
    m5_sha256: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"seq": self.seq, "state": self.state.name, "at": self.at,
                "evidence_ref": self.evidence_ref,
                "evidence_sha256": self.evidence_sha256,
                "provenance": self.provenance,
                "m5_reference": self.m5_reference,
                "m5_sha256": self.m5_sha256}


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

    def _expected_next(self) -> Optional[LifecycleState]:
        if not self.transitions:
            return LifecycleState.CREATED
        last = self.transitions[-1].state
        if last is LifecycleState.CLOSED:
            return None
        return LifecycleState(last + 1)

    def _require_next(self, state: LifecycleState) -> None:
        """Validate the transition BEFORE any state mutation (R4)."""
        expected = self._expected_next()
        if expected is None:
            raise LifecycleError("lifecycle already CLOSED")
        if state is not expected:
            raise LifecycleError(
                f"impossible transition {self.state.name} -> {state.name}")

    def _append(self, state: LifecycleState, evidence_ref: Optional[str] = None,
                evidence_sha256: Optional[str] = None,
                provenance: Optional[str] = None,
                m5_reference: Optional[str] = None,
                m5_sha256: Optional[str] = None) -> None:
        self._require_next(state)
        if provenance is not None and provenance not in _VALID_TEARDOWN_PROVENANCE:
            raise LifecycleError(f"unknown teardown provenance {provenance!r}")
        if state in EVIDENCE_REQUIRED_STATES:
            if not _valid_id(evidence_ref) or not _is_hex64(evidence_sha256):
                raise LifecycleError(
                    f"{state.name} requires evidence_ref + sha256")
            if provenance == TEARDOWN_PROVENANCE_M5_BOUND:
                if not _valid_id(m5_reference):
                    raise LifecycleError(
                        "m5-bound teardown requires a non-None M5 reference")
                if not _is_hex64(m5_sha256):
                    raise LifecycleError(
                        "m5-bound teardown requires a 64-hex M5 digest")
        seq = len(self.transitions)
        self.transitions.append(LifecycleTransition(
            seq=seq, state=state, at=float(seq),
            evidence_ref=evidence_ref, evidence_sha256=evidence_sha256,
            provenance=provenance, m5_reference=m5_reference,
            m5_sha256=m5_sha256))

    @property
    def state(self) -> LifecycleState:
        return self.transitions[-1].state if self.transitions else LifecycleState(-1)

    @property
    def teardown_transition(self) -> Optional[LifecycleTransition]:
        for t in self.transitions:
            if t.state is LifecycleState.TEARDOWN_OBSERVED:
                return t
        return None

    @property
    def teardown_provenance(self) -> Optional[str]:
        tev = self.teardown_transition
        return tev.provenance if tev is not None else None

    @property
    def m5_reference(self) -> Optional[str]:
        tev = self.teardown_transition
        return tev.m5_reference if tev is not None else None

    # --- bindings -------------------------------------------------------
    def bind_sandbox(self, sandbox_id: str) -> None:
        if not _valid_id(sandbox_id):
            raise LifecycleError("missing sandbox identity")
        if self.sandbox_id is not None:
            if self.sandbox_id != sandbox_id:
                raise LifecycleError("mismatched sandbox identity")
            return  # identity-preserving rebind: no-op, no mutation (R4)
        self._require_next(LifecycleState.SANDBOX_BOUND)
        self.sandbox_id = sandbox_id
        self._append(LifecycleState.SANDBOX_BOUND)

    def bind_workload(self, pid: int, pid_starttime: str, cgroup: str) -> None:
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise LifecycleError("invalid workload pid")
        if not _valid_id(pid_starttime):
            raise LifecycleError("missing workload starttime")
        if not _valid_id(cgroup):
            raise LifecycleError("missing cgroup identity")
        if self.pid is not None:
            if (self.pid, self.pid_starttime, self.cgroup) != \
                    (pid, pid_starttime, cgroup):
                raise LifecycleError("mismatched workload identity")
            return  # identity-preserving rebind: no-op, no mutation (R4)
        self._require_next(LifecycleState.WORKLOAD_BOUND)
        self.pid, self.pid_starttime, self.cgroup = pid, pid_starttime, cgroup
        self._append(LifecycleState.WORKLOAD_BOUND)

    def start(self) -> None:
        self._append(LifecycleState.RUNNING)

    def initiate_teardown(self) -> None:
        self._append(LifecycleState.TEARDOWN_INITIATED)

    def observe_teardown(self, evidence_ref: str, evidence_sha256: str, *,
                         provenance: str = TEARDOWN_PROVENANCE_DIRECT,
                         m5_reference: Optional[str] = None,
                         m5_sha256: Optional[str] = None) -> None:
        """Record a teardown observation with explicit provenance (R1).

        ``provenance="direct"`` records an unbound observation (which can
        never close the record). ``provenance="m5-bound"`` additionally
        requires a non-None M5 reference and a 64-hex M5 digest.
        """
        if provenance not in _VALID_TEARDOWN_PROVENANCE:
            raise LifecycleError(f"unknown teardown provenance {provenance!r}")
        if self.teardown_transition is not None:
            raise LifecycleError("teardown already observed (no rebind)")
        self._append(
            LifecycleState.TEARDOWN_OBSERVED,
            evidence_ref=evidence_ref, evidence_sha256=evidence_sha256,
            provenance=provenance, m5_reference=m5_reference,
            m5_sha256=m5_sha256)

    def close(self) -> None:
        """Close ONLY after an M5-bound teardown observation (R2)."""
        tev = self.teardown_transition
        if tev is None:
            raise LifecycleError("cannot close without teardown evidence")
        if tev.provenance != TEARDOWN_PROVENANCE_M5_BOUND:
            raise LifecycleError(
                "cannot close without M5-bound teardown provenance")
        if not _valid_id(tev.m5_reference):
            raise LifecycleError(
                "cannot close without a non-None M5 reference")
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
                evidence_sha256=t.get("evidence_sha256"),
                provenance=t.get("provenance"),
                m5_reference=t.get("m5_reference"),
                m5_sha256=t.get("m5_sha256")))
        rec.pid = payload.get("pid")
        rec.pid_starttime = payload.get("pid_starttime")
        rec.cgroup = payload.get("cgroup")
        got = payload.get("lifecycle_sha256")
        check = dict(payload); check.pop("lifecycle_sha256", None)
        if got != hashlib.sha256(_canonical(check).encode()).hexdigest():
            raise LifecycleError("lifecycle integrity hash mismatch")
        # Structural validation: a forged record must still be contiguous.
        states = [t.state for t in rec.transitions]
        if [t.seq for t in rec.transitions] != list(range(len(rec.transitions))):
            raise LifecycleError("non-contiguous transition sequence")
        if states != [LifecycleState(i) for i in range(len(states))]:
            raise LifecycleError("non-contiguous lifecycle states")
        for t in rec.transitions:
            if t.state in EVIDENCE_REQUIRED_STATES:
                if not _valid_id(t.evidence_ref) or not _is_hex64(t.evidence_sha256):
                    raise LifecycleError("teardown transition lacks evidence")
                if t.provenance is not None and \
                        t.provenance not in _VALID_TEARDOWN_PROVENANCE:
                    raise LifecycleError("invalid teardown provenance")
        # R2 — a deserialized CLOSED record must still be M5-bound.
        if LifecycleState.CLOSED in states:
            tv = rec.teardown_transition
            if (tv is None
                    or tv.provenance != TEARDOWN_PROVENANCE_M5_BOUND
                    or not _valid_id(tv.m5_reference)):
                raise LifecycleError(
                    "CLOSED requires M5-bound teardown provenance")
        return rec


def bind_m5_teardown(rec: LifecycleRecord, m5_evidence: Dict[str, Any],
                     reference: str, sha256: str) -> None:
    """Bind accepted M5 teardown evidence into lifecycle closure.

    Fail-closed and atomic (R3/R4): every check runs BEFORE any mutation, so
    a rejected binding leaves the record untouched. ``target_terminated`` and
    ``no_provider_execution`` must be the boolean ``True`` (strict), and the
    binding never implies provider success.
    """
    if rec.teardown_transition is not None:
        raise LifecycleError("teardown already observed (no rebind)")
    if not _valid_id(reference):
        raise LifecycleError("missing M5 reference")
    if not _is_hex64(sha256):
        raise LifecycleError("M5 digest must be 64 lowercase hex")
    teardown = m5_evidence.get("teardown", {})
    post = m5_evidence.get("post_kill", {})
    if "populated 1" not in str(teardown.get("events_before")):
        raise LifecycleError("M5 evidence lacks pre-teardown populated=1")
    if "populated 0" not in str(teardown.get("events_after")):
        raise LifecycleError("M5 evidence lacks post-teardown populated=0")
    # R3 — strict boolean, no coercion.
    if post.get("target_terminated") is not True:
        raise LifecycleError(
            "M5 evidence target_terminated must be boolean True")
    if m5_evidence.get("no_provider_execution") is not True:
        raise LifecycleError(
            "M5 evidence no_provider_execution must be boolean True")
    tracked = m5_evidence.get("tracked", {})
    if rec.pid is not None and tracked.get("pid") != rec.pid:
        raise LifecycleError("mismatched workload identity vs M5 evidence")
    if (rec.pid_starttime is not None
            and str(tracked.get("starttime")) != str(rec.pid_starttime)):
        raise LifecycleError("mismatched starttime vs M5 evidence")
    rec.observe_teardown(
        reference, sha256, provenance=TEARDOWN_PROVENANCE_M5_BOUND,
        m5_reference=reference, m5_sha256=sha256)


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
    # R1/R2 — provenance is load-bearing for closure and attestation.
    check("teardown-provenance-m5-bound",
          bool(tev) and tev[0].provenance == TEARDOWN_PROVENANCE_M5_BOUND)
    check("m5-reference-present",
          bool(tev) and _valid_id(tev[0].m5_reference))
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
        check("m5-no-provider-execution",
              m5_evidence.get("no_provider_execution") is True)
        check("m5-populated-zero",
              "populated 0" in str(m5_evidence.get("teardown", {}).get("events_after")))
    status = AttestationStatus.ATTESTED if not failures else AttestationStatus.INVALID
    tev0 = tev[0] if tev else None
    return AttestationResult(
        status=status, proof_session_id=rec.proof_session_id, checks=checks,
        failures=failures,
        reasons=["lifecycle integrity only; no provider or gate authority"],
        quarantined=False,
        evidence={"lifecycle_id": rec.lifecycle_id,
                  "lifecycle_sha256": rec.to_dict()["lifecycle_sha256"],
                  "scope": "lifecycle_integrity_only",
                  "teardown_provenance":
                      tev0.provenance if tev0 is not None else None,
                  "m5_reference": tev0.m5_reference if tev0 is not None else None,
                  "provider_executed": False, "live_proof": False,
                  "m5_reference_arg": m5_reference})


__all__ = [
    "EVIDENCE_REQUIRED_STATES", "FORBIDDEN_AUTHORITY_KEYS", "LifecycleError",
    "LifecycleRecord", "LifecycleState", "LifecycleTransition",
    "TEARDOWN_PROVENANCE_DIRECT", "TEARDOWN_PROVENANCE_M5_BOUND",
    "attest_lifecycle", "bind_m5_teardown", "sha256_file",
    "verify_file_sha256",
]
