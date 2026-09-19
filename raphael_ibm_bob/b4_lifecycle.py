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

Semantics (R1-R7 + B4-1..B4-7 corrective closure):

R1 teardown provenance
    Every ``TEARDOWN_OBSERVED`` transition carries an explicit, serialized
    ``provenance``: ``"direct"`` (an unbound local observation) or
    ``"m5-bound"`` (bound to an authenticated M5 artifact). Provenance and the
    M5 reference/digest are serialized and covered by ``lifecycle_sha256``.

R2 fail-closed closure
    ``close()`` requires an ``M5-bound`` teardown transition with a non-None,
    authenticated M5 reference. A direct observation can never close.

R3 strict booleans
    ``target_terminated`` and ``no_provider_execution`` must be the boolean
    ``True`` (``1``/``"true"``/etc. rejected, never coerced).

R4 atomic rebind
    Identity mismatches are validated BEFORE any mutation; failed rebinds are
    side-effect-free; identity-preserving rebinds are no-ops.

R5 semantics documentation
    * ``at`` is an ORDINAL counter (0,1,2,...), NOT wall-clock time.
    * Authority-key rejection is a STRUCTURAL key-name check only.
    * ``lifecycle_sha256`` is TAMPER EVIDENCE ONLY, not authentication.

R6 file digest helper
    :func:`sha256_file` / :func:`verify_file_sha256` hash ACTUAL bytes and
    fail closed.

B4-1 fake M5-bound provenance eliminated
    ``observe_teardown()`` is DIRECT observation only and rejects
    ``provenance="m5-bound"``. ONLY :func:`bind_m5_teardown` can create an
    M5-bound transition. DECLARATION != AUTHORIZATION.

B4-2 M5 evidence authenticated
    ``bind_m5_teardown`` does NOT treat a 64-hex string as proof. It resolves
    the reference to a filesystem artifact, hashes its ACTUAL bytes with
    :func:`sha256_file`, compares to the expected digest, parses the artifact,
    and requires the caller-supplied evidence dict to equal the authenticated
    artifact. Missing file / malformed digest / mismatch all fail closed.
    :func:`attest_lifecycle`, :meth:`LifecycleRecord.to_dict`, and
    :meth:`LifecycleRecord.from_dict` RE-AUTHENTICATE the referenced artifact,
    so a forged M5-bound transition cannot become attestable or serializable
    even if ``lifecycle_sha256`` is recomputed.

B4-3 cgroup.events parsing
    ``populated`` is parsed as a FIELD (see :func:`cgroup_populated`), never by
    substring. Missing / malformed / duplicate / non-integer / out-of-range
    values fail closed; ``"unpopulated 1"`` and ``"populated 10"`` are
    rejected.

B4-4/B4-5 deserialization revalidates append invariants
    ``from_dict`` reapplies the same ordinal/type/provenance/ordering/evidence
    and M5 invariants as the live API (plus B4-2 authentication); a valid
    object round-trips, a forged dictionary does not become valid by
    recomputing ``lifecycle_sha256``.

B4-6 construction / mutability hardening
    ``transitions`` is exposed read-only; :meth:`LifecycleRecord.__post_init__`
    rejects structurally impossible initial records (e.g. a CLOSED record
    without an M5-bound teardown). A caller cannot ``.append`` onto the
    transition tuple; a directly-populated forged M5-bound record is rejected
    by authentication at ``to_dict``/attestation.

B4-7 attestation field taxonomy
    Attestation evidence avoids names that collide with
    :data:`FORBIDDEN_AUTHORITY_KEYS`: it emits ``provider_execution_observed``
    and ``live_proof_claimed`` (both False), never ``provider_executed`` /
    ``live_proof``.
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
    """Return the SHA-256 of the ACTUAL bytes of ``path`` (fail closed)."""
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
    """True iff ``path`` exists and its ACTUAL SHA-256 equals ``expected``."""
    if not _is_hex64(expected):
        return False
    try:
        return sha256_file(path) == expected
    except LifecycleError:
        return False


# ---------------------------------------------------------------------------
# B4-3 — cgroup.events field parser (never substring matching)
# ---------------------------------------------------------------------------

def cgroup_populated(events_text: Any) -> Optional[int]:
    """Parse ``cgroup.events`` and return the ``populated`` field value.

    Field-based (line/whitespace), never substring. Returns ``None`` when no
    ``populated`` field is present. Raises ``LifecycleError`` on a malformed
    line, a non-integer value, or a duplicate ``populated`` field.
    """
    if not isinstance(events_text, str):
        raise LifecycleError("cgroup.events must be a string")
    values: List[int] = []
    for raw in events_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if parts[0] != "populated":
            continue  # e.g. "frozen 0", "unpopulated 1"
        if len(parts) != 2:
            raise LifecycleError(f"malformed populated line: {line!r}")
        try:
            values.append(int(parts[1]))
        except ValueError:
            raise LifecycleError(
                f"non-integer populated value: {parts[1]!r}") from None
    if not values:
        return None
    if len(values) > 1:
        raise LifecycleError("duplicate populated fields in cgroup.events")
    return values[0]


# ---------------------------------------------------------------------------
# B4-2 — M5 artifact authentication (actual bytes, fail-closed)
# ---------------------------------------------------------------------------

def resolve_reference_path(reference: str) -> str:
    """Strip an optional ``#fragment`` from an M5 reference."""
    if not isinstance(reference, str) or not reference.strip():
        raise LifecycleError("missing M5 reference")
    return reference.split("#", 1)[0]


def authenticate_m5_artifact(reference: str, sha256: Any) -> Dict[str, Any]:
    """Resolve, hash, parse, and return the referenced M5 artifact.

    Fail-closed: missing/blank reference, non-64-hex expected digest, missing
    or unreadable file, digest mismatch, non-JSON, or non-object all raise.
    A caller-supplied digest alone is never accepted as proof.
    """
    if not _is_hex64(sha256):
        raise LifecycleError("M5 digest must be 64 lowercase hex")
    path = resolve_reference_path(reference)
    if not os.path.isfile(path):
        raise LifecycleError(
            f"M5 reference is not a readable artifact: {path!r}")
    actual = sha256_file(path)
    if actual != sha256:
        raise LifecycleError(
            f"M5 digest mismatch for {path!r}: expected {sha256} got {actual}")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.loads(handle.read())
    except (OSError, ValueError) as exc:
        raise LifecycleError(
            f"M5 artifact not parseable JSON: {type(exc).__name__}") from None
    if not isinstance(data, dict):
        raise LifecycleError("M5 artifact must be a JSON object")
    return data


# ---------------------------------------------------------------------------
# Transition + record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LifecycleTransition:
    """One ordered lifecycle transition with provenance.

    ``at`` is an ORDINAL counter (see R5), not wall-clock time.
    ``provenance`` / ``m5_reference`` / ``m5_sha256`` are meaningful on the
    ``TEARDOWN_OBSERVED`` transition and must be ``None`` elsewhere.
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


def _record_body(rec: "LifecycleRecord") -> Dict[str, Any]:
    return {"lifecycle_id": rec.lifecycle_id,
            "proof_session_id": rec.proof_session_id,
            "sandbox_id": rec.sandbox_id, "pid": rec.pid,
            "pid_starttime": rec.pid_starttime, "cgroup": rec.cgroup,
            "transitions": [t.to_dict() for t in rec._transitions],
            "scope": "lifecycle_integrity_only"}


def _validate_structure(rec: "LifecycleRecord", *, authenticate: bool) -> None:
    """Reapply every append-time invariant (B4-4/B4-5).

    Used by ``__post_init__`` (authenticate=False), ``to_dict`` and
    ``from_dict`` (authenticate=True).
    """
    if not _valid_id(rec.lifecycle_id):
        raise LifecycleError("missing lifecycle identity")
    if not _valid_id(rec.proof_session_id):
        raise LifecycleError("missing proof-session identity")
    if rec.sandbox_id is not None and not _valid_id(rec.sandbox_id):
        raise LifecycleError("invalid sandbox identity")
    if rec.pid is not None:
        if isinstance(rec.pid, bool) or not isinstance(rec.pid, int) or rec.pid <= 0:
            raise LifecycleError("invalid workload pid")
    if rec.pid_starttime is not None and not _valid_id(rec.pid_starttime):
        raise LifecycleError("invalid workload starttime")
    if rec.cgroup is not None and not _valid_id(rec.cgroup):
        raise LifecycleError("invalid cgroup identity")

    ts = list(rec._transitions)
    if [t.seq for t in ts] != list(range(len(ts))):
        raise LifecycleError("non-contiguous transition sequence")
    if [t.state for t in ts] != [LifecycleState(i) for i in range(len(ts))]:
        raise LifecycleError("non-contiguous lifecycle states")
    for t in ts:
        if isinstance(t.at, bool) or not isinstance(t.at, (int, float)) \
                or float(t.at) != float(t.seq):
            raise LifecycleError("transition 'at' must equal the ordinal seq")
        if t.state is LifecycleState.TEARDOWN_OBSERVED:
            if not _valid_id(t.evidence_ref) or not _is_hex64(t.evidence_sha256):
                raise LifecycleError("teardown transition lacks evidence")
            if t.provenance not in _VALID_TEARDOWN_PROVENANCE:
                raise LifecycleError("invalid teardown provenance")
            if t.provenance == TEARDOWN_PROVENANCE_M5_BOUND:
                if not _valid_id(t.m5_reference) or not _is_hex64(t.m5_sha256):
                    raise LifecycleError("m5-bound teardown lacks reference/digest")
                if authenticate:
                    # B4-2: independently verify the referenced artifact bytes.
                    authenticate_m5_artifact(t.m5_reference, t.m5_sha256)
            else:  # direct
                if t.m5_reference is not None or t.m5_sha256 is not None:
                    raise LifecycleError(
                        "direct teardown must not carry M5 reference/digest")
        else:
            if (t.provenance is not None or t.m5_reference is not None
                    or t.m5_sha256 is not None):
                raise LifecycleError(
                    "non-teardown transition must not carry provenance/M5")
    states = [t.state for t in ts]
    if LifecycleState.CLOSED in states:
        tv = next((t for t in ts
                   if t.state is LifecycleState.TEARDOWN_OBSERVED), None)
        if (tv is None or tv.provenance != TEARDOWN_PROVENANCE_M5_BOUND
                or not _valid_id(tv.m5_reference)):
            raise LifecycleError(
                "CLOSED requires M5-bound teardown provenance")


@dataclass
class LifecycleRecord:
    """RAPHAEL-owned lifecycle record for one governed session.

    ``transitions`` is exposed read-only (a tuple); use the bind/observe/close
    API. Direct field population is structurally validated by
    ``__post_init__`` and, for M5-bound transitions, re-authenticated by
    ``to_dict``/``from_dict``/attestation.
    """
    lifecycle_id: str
    proof_session_id: str
    sandbox_id: Optional[str] = None
    pid: Optional[int] = None
    pid_starttime: Optional[str] = None
    cgroup: Optional[str] = None
    _transitions: List[LifecycleTransition] = field(default_factory=list)

    def __post_init__(self) -> None:
        # B4-6: reject structurally impossible initial records (e.g. a direct
        # CLOSED record). Authentication of M5-bound transitions is deferred
        # to to_dict/from_dict/attestation (it requires filesystem access).
        _validate_structure(self, authenticate=False)

    @property
    def transitions(self) -> Tuple[LifecycleTransition, ...]:
        """Read-only view; prevents silent public mutation (B4-6)."""
        return tuple(self._transitions)

    # --- construction ---------------------------------------------------
    @staticmethod
    def create(lifecycle_id: str, proof_session_id: str) -> "LifecycleRecord":
        rec = LifecycleRecord(lifecycle_id=lifecycle_id,
                              proof_session_id=proof_session_id)
        rec._append(LifecycleState.CREATED)
        return rec

    def _expected_next(self) -> Optional[LifecycleState]:
        if not self._transitions:
            return LifecycleState.CREATED
        last = self._transitions[-1].state
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
                provenance: Optional[str] = None) -> None:
        """Append a NON-M5 transition (CREATED..TEARDOWN_OBSERVED direct)."""
        if provenance == TEARDOWN_PROVENANCE_M5_BOUND:
            raise LifecycleError(
                "m5-bound provenance may only be established by "
                "bind_m5_teardown() (B4-1)")
        self._require_next(state)
        if provenance is not None and provenance != TEARDOWN_PROVENANCE_DIRECT:
            raise LifecycleError(f"unknown teardown provenance {provenance!r}")
        if state in EVIDENCE_REQUIRED_STATES:
            if not _valid_id(evidence_ref) or not _is_hex64(evidence_sha256):
                raise LifecycleError(
                    f"{state.name} requires evidence_ref + sha256")
        seq = len(self._transitions)
        self._transitions.append(LifecycleTransition(
            seq=seq, state=state, at=float(seq),
            evidence_ref=evidence_ref, evidence_sha256=evidence_sha256,
            provenance=provenance))

    def _append_m5_bound(self, reference: str, sha256: str) -> None:
        """PRIVATE: the only path that creates an M5-bound transition (B4-1).

        Callable only by :func:`bind_m5_teardown` after authentication.
        """
        if self._expected_next() is not LifecycleState.TEARDOWN_OBSERVED:
            raise LifecycleError("impossible transition to TEARDOWN_OBSERVED")
        seq = len(self._transitions)
        self._transitions.append(LifecycleTransition(
            seq=seq, state=LifecycleState.TEARDOWN_OBSERVED, at=float(seq),
            evidence_ref=reference, evidence_sha256=sha256,
            provenance=TEARDOWN_PROVENANCE_M5_BOUND,
            m5_reference=reference, m5_sha256=sha256))

    @property
    def state(self) -> LifecycleState:
        return self._transitions[-1].state if self._transitions else LifecycleState(-1)

    @property
    def teardown_transition(self) -> Optional[LifecycleTransition]:
        for t in self._transitions:
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
        """Record a DIRECT teardown observation (B4-1).

        This method is DIRECT-ONLY. ``provenance="m5-bound"`` is explicitly
        rejected: M5-bound provenance may only be established by
        :func:`bind_m5_teardown` (which authenticates the artifact). Supplying
        an M5 reference/digest here is likewise rejected.
        """
        if provenance == TEARDOWN_PROVENANCE_M5_BOUND:
            raise LifecycleError(
                "m5-bound provenance may only be established by "
                "bind_m5_teardown() (B4-1)")
        if provenance != TEARDOWN_PROVENANCE_DIRECT:
            raise LifecycleError(f"unknown teardown provenance {provenance!r}")
        if m5_reference is not None or m5_sha256 is not None:
            raise LifecycleError(
                "M5 reference/digest may only be supplied via "
                "bind_m5_teardown() (B4-1)")
        if self.teardown_transition is not None:
            raise LifecycleError("teardown already observed (no rebind)")
        self._append(
            LifecycleState.TEARDOWN_OBSERVED,
            evidence_ref=evidence_ref, evidence_sha256=evidence_sha256,
            provenance=TEARDOWN_PROVENANCE_DIRECT)

    def close(self) -> None:
        """Close ONLY after an authenticated M5-bound teardown (R2/B4-2)."""
        tev = self.teardown_transition
        if tev is None:
            raise LifecycleError("cannot close without teardown evidence")
        if tev.provenance != TEARDOWN_PROVENANCE_M5_BOUND:
            raise LifecycleError(
                "cannot close without M5-bound teardown provenance")
        if not _valid_id(tev.m5_reference):
            raise LifecycleError(
                "cannot close without a non-None M5 reference")
        # B4-2: a forged M5-bound transition cannot close, even in memory.
        authenticate_m5_artifact(tev.m5_reference, tev.m5_sha256)
        self._append(LifecycleState.CLOSED)

    # --- serialization --------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        _validate_structure(self, authenticate=True)
        body = _record_body(self)
        _reject_authority(body, "lifecycle record")
        digest = hashlib.sha256(_canonical(body).encode()).hexdigest()
        return {**body, "lifecycle_sha256": digest}

    @staticmethod
    def from_dict(payload: Dict[str, Any]) -> "LifecycleRecord":
        if not isinstance(payload, dict):
            raise LifecycleError("lifecycle payload must be a dict")
        _reject_authority(payload, "lifecycle record")
        transitions: List[LifecycleTransition] = []
        for t in payload.get("transitions", []):
            if not isinstance(t, dict):
                raise LifecycleError("transition must be an object")
            try:
                transitions.append(LifecycleTransition(
                    seq=t["seq"], state=LifecycleState[t["state"]], at=t["at"],
                    evidence_ref=t.get("evidence_ref"),
                    evidence_sha256=t.get("evidence_sha256"),
                    provenance=t.get("provenance"),
                    m5_reference=t.get("m5_reference"),
                    m5_sha256=t.get("m5_sha256")))
            except (KeyError, TypeError, ValueError) as exc:
                raise LifecycleError(
                    f"malformed transition: {type(exc).__name__}") from None
        rec = LifecycleRecord(
            lifecycle_id=payload["lifecycle_id"],
            proof_session_id=payload["proof_session_id"],
            sandbox_id=payload.get("sandbox_id"),
            pid=payload.get("pid"),
            pid_starttime=payload.get("pid_starttime"),
            cgroup=payload.get("cgroup"),
            _transitions=transitions)
        got = payload.get("lifecycle_sha256")
        check = dict(payload); check.pop("lifecycle_sha256", None)
        if got != hashlib.sha256(_canonical(check).encode()).hexdigest():
            raise LifecycleError("lifecycle integrity hash mismatch")
        # B4-4/B4-5 (+B4-2): reapply append invariants AND authenticate M5.
        _validate_structure(rec, authenticate=True)
        return rec


def bind_m5_teardown(rec: LifecycleRecord, m5_evidence: Dict[str, Any],
                     reference: str, sha256: str) -> None:
    """Authenticate + bind M5 teardown evidence; the ONLY M5-bound path.

    Fail-closed and atomic (B4-1/B4-2/R3/R4): (1) the referenced artifact is
    resolved and its ACTUAL bytes are hashed; (2) the digest must match; (3)
    the artifact must parse to a JSON object equal to ``m5_evidence``; (4) all
    content checks run; only then is the transition appended. Any failure
    leaves the record untouched, and the binding never implies provider
    success.
    """
    if rec.teardown_transition is not None:
        raise LifecycleError("teardown already observed (no rebind)")
    if not _valid_id(reference):
        raise LifecycleError("missing M5 reference")
    if not _is_hex64(sha256):
        raise LifecycleError("M5 digest must be 64 lowercase hex")
    # B4-2: authenticate the artifact BEFORE trusting caller-supplied content.
    authenticated = authenticate_m5_artifact(reference, sha256)
    if not isinstance(m5_evidence, dict) or authenticated != m5_evidence:
        raise LifecycleError(
            "caller-supplied M5 evidence does not match the authenticated "
            "artifact")

    teardown = authenticated.get("teardown", {})
    post = authenticated.get("post_kill", {})
    if not isinstance(teardown, dict) or not isinstance(post, dict):
        raise LifecycleError("M5 evidence has malformed teardown/post_kill")
    # B4-3: field parsing (no substring matching).
    before = cgroup_populated(teardown.get("events_before"))
    after = cgroup_populated(teardown.get("events_after"))
    if before != 1:
        raise LifecycleError(
            "M5 evidence requires pre-teardown populated == 1")
    if after != 0:
        raise LifecycleError(
            "M5 evidence requires post-teardown populated == 0")
    # R3 — strict boolean, no coercion.
    if post.get("target_terminated") is not True:
        raise LifecycleError(
            "M5 evidence target_terminated must be boolean True")
    if authenticated.get("no_provider_execution") is not True:
        raise LifecycleError(
            "M5 evidence no_provider_execution must be boolean True")
    tracked = authenticated.get("tracked", {})
    if not isinstance(tracked, dict):
        raise LifecycleError("M5 evidence has malformed tracked block")
    if rec.pid is not None and tracked.get("pid") != rec.pid:
        raise LifecycleError("mismatched workload identity vs M5 evidence")
    if (rec.pid_starttime is not None
            and str(tracked.get("starttime")) != str(rec.pid_starttime)):
        raise LifecycleError("mismatched starttime vs M5 evidence")
    rec._append_m5_bound(reference, sha256)


def _m5_authentication_status(rec: LifecycleRecord) -> Tuple[bool, str]:
    tev = rec.teardown_transition
    if tev is None:
        return False, "no teardown transition"
    if tev.provenance != TEARDOWN_PROVENANCE_M5_BOUND:
        return False, "teardown is not m5-bound"
    try:
        authenticate_m5_artifact(tev.m5_reference, tev.m5_sha256)
        return True, ""
    except LifecycleError as exc:
        return False, str(exc)


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

    ts = list(rec._transitions)
    check("lifecycle-identity", _valid_id(rec.lifecycle_id))
    check("proof-session-identity", _valid_id(rec.proof_session_id))
    check("sandbox-identity-bound", _valid_id(rec.sandbox_id))
    check("workload-identity-bound",
          isinstance(rec.pid, int) and not isinstance(rec.pid, bool)
          and rec.pid > 0 and _valid_id(rec.pid_starttime) and _valid_id(rec.cgroup))
    check("transition-ordering",
          [t.seq for t in ts] == list(range(len(ts))))
    states = [t.state for t in ts]
    check("transition-contiguity",
          states == [LifecycleState(i) for i in range(len(states))])
    tev = [t for t in ts if t.state is LifecycleState.TEARDOWN_OBSERVED]
    check("teardown-evidence-present", len(tev) == 1)
    check("teardown-evidence-hashed",
          bool(tev) and _is_hex64(tev[0].evidence_sha256))
    check("teardown-provenance-m5-bound",
          bool(tev) and tev[0].provenance == TEARDOWN_PROVENANCE_M5_BOUND)
    check("m5-reference-present",
          bool(tev) and _valid_id(tev[0].m5_reference))
    # B4-2: independent artifact authentication is part of attestation.
    auth_ok, auth_detail = _m5_authentication_status(rec)
    check("m5-reference-authenticated", auth_ok, auth_detail)
    check("closure-after-teardown",
          LifecycleState.CLOSED in states and len(tev) == 1
          and states.index(LifecycleState.CLOSED) > states.index(LifecycleState.TEARDOWN_OBSERVED))
    try:
        _reject_authority(_record_body(rec), "lifecycle attestation")
        authority_clean = True
    except LifecycleError:
        authority_clean = False
    check("no-authority-smuggling", authority_clean)

    authenticated: Optional[Dict[str, Any]] = None
    if auth_ok:
        try:
            authenticated = authenticate_m5_artifact(
                tev[0].m5_reference, tev[0].m5_sha256)
        except LifecycleError:
            authenticated = None
    if m5_evidence is not None:
        if authenticated is not None:
            check("m5-evidence-matches-artifact", authenticated == m5_evidence)
            source = authenticated
        else:
            check("m5-evidence-matches-artifact", False)
            source = m5_evidence
        tracked = source.get("tracked", {}) if isinstance(source, dict) else {}
        check("m5-workload-identity-match",
              isinstance(tracked, dict) and tracked.get("pid") == rec.pid
              and str(tracked.get("starttime")) == str(rec.pid_starttime))
        check("m5-no-provider-execution",
              isinstance(source, dict)
              and source.get("no_provider_execution") is True)
        populated_after = None
        if isinstance(source, dict):
            try:
                populated_after = cgroup_populated(
                    source.get("teardown", {}).get("events_after"))
            except LifecycleError:
                populated_after = None
        check("m5-populated-zero", populated_after == 0)

    status = AttestationStatus.ATTESTED if not failures else AttestationStatus.INVALID
    tev0 = tev[0] if tev else None
    try:
        lifecycle_sha = hashlib.sha256(
            _canonical(_record_body(rec)).encode()).hexdigest()
    except (AttributeError, TypeError):
        lifecycle_sha = None
    # B4-7: evidence field names must not collide with FORBIDDEN_AUTHORITY_KEYS.
    evidence = {
        "lifecycle_id": rec.lifecycle_id,
        "lifecycle_sha256": lifecycle_sha,
        "scope": "lifecycle_integrity_only",
        "teardown_provenance": tev0.provenance if tev0 is not None else None,
        "m5_reference": tev0.m5_reference if tev0 is not None else None,
        "provider_execution_observed": False,
        "live_proof_claimed": False,
        "m5_reference_arg": m5_reference,
    }
    return AttestationResult(
        status=status, proof_session_id=rec.proof_session_id, checks=checks,
        failures=failures,
        reasons=["lifecycle integrity only; no provider or gate authority"],
        quarantined=False,
        evidence=evidence)


__all__ = [
    "EVIDENCE_REQUIRED_STATES", "FORBIDDEN_AUTHORITY_KEYS", "LifecycleError",
    "LifecycleRecord", "LifecycleState", "LifecycleTransition",
    "TEARDOWN_PROVENANCE_DIRECT", "TEARDOWN_PROVENANCE_M5_BOUND",
    "attest_lifecycle", "authenticate_m5_artifact", "bind_m5_teardown",
    "cgroup_populated", "resolve_reference_path", "sha256_file",
    "verify_file_sha256",
]
