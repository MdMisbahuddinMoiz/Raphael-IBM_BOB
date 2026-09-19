"""raphael_ibm_bob.b4_lifecycle — governed lifecycle record + attestation.

Phase 2C B4-LIFECYCLE. Lifecycle-integrity attestation only; never provider
success, mission completion, or authorization.

TRUST MODEL (honest, PART 0/11)

    TRUSTED RAPHAEL CORE / TRUSTED M5 PRODUCER
        -> process-local capability authority
        -> authenticated M5 observation
        -> identity-bound lifecycle
        -> CLOSED / ATTESTED

The process-local :class:`M5TrustAuthority` is a CAPABILITY BOUNDARY INSIDE
THE TRUSTED CORE. It is **not** a process-isolation boundary, **not** a
defense against arbitrary code already executing inside the RAPHAEL process,
**not** a persistent cryptographic root, and **not** a cross-process/restart
authenticator. A fully compromised Python process can obtain and use the
capability (Q8 = yes, accepted and documented). What is removed are the
*accidental* and unnecessary weaknesses: there is no public constructor that
accepts a caller-supplied verifier, no caller-supplied HMAC secret, no
module-global signing secret, no overridable trust decision, and no
unattached lookalike authority that can satisfy the trust path.

Three properties stay separate:

  A. ARTIFACT INTEGRITY    — "these exact bytes hash to this digest."
  B. ARTIFACT AUTHENTICITY — "sealed by the trusted-core M5 authority for
                              THIS lifecycle identity."
  C. LIFECYCLE INTEGRITY   — "this record is unmodified since recorded"
                              (lifecycle_sha256 = tamper evidence only).

Caller-authored artifact bytes and caller-computed digests are INSUFFICIENT
to obtain M5-bound provenance: M5-bound provenance requires the trusted-core
M5 authority capability and a valid observation. Post-bind, the referenced
artifact is RE-READ and re-hashed at every trust boundary (close/to_dict/
attest/from_dict), so replacing or deleting it invalidates the record.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple

from raphael_ibm_bob.b4_attestation import (
    AttestationCheck,
    AttestationResult,
    AttestationStatus,
)


class LifecycleState(IntEnum):
    CREATED = 0
    SANDBOX_BOUND = 1
    WORKLOAD_BOUND = 2
    RUNNING = 3
    TEARDOWN_INITIATED = 4
    TEARDOWN_OBSERVED = 5
    CLOSED = 6


EVIDENCE_REQUIRED_STATES = frozenset({LifecycleState.TEARDOWN_OBSERVED})

FORBIDDEN_AUTHORITY_KEYS = frozenset({
    "authorized", "authorization", "execution_authorized", "live_proof",
    "live_proof_authorized", "provider_success", "provider_executed",
    "mission_complete", "quality_gate_complete", "gate_verdict", "complete",
    "tool_executed", "capability_executed", "arsenal_invoked",
    "binary_sink_scan_executed",
})

TEARDOWN_PROVENANCE_DIRECT = "direct"
TEARDOWN_PROVENANCE_M5_BOUND = "m5-bound"
_VALID_TEARDOWN_PROVENANCE = frozenset({
    TEARDOWN_PROVENANCE_DIRECT, TEARDOWN_PROVENANCE_M5_BOUND})


class LifecycleError(Exception):
    """Fail-closed lifecycle construction/progression error."""


class M5AuthorityError(LifecycleError):
    """The M5 trust authority refused (fail-closed)."""


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
# R6 / PART 6 — artifact byte integrity helpers
# ---------------------------------------------------------------------------

def sha256_file(path: str) -> str:
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
    if not _is_hex64(expected):
        return False
    try:
        return sha256_file(path) == expected
    except LifecycleError:
        return False


# ---------------------------------------------------------------------------
# B4-3 / PART 7 — canonical cgroup.events parser
# ---------------------------------------------------------------------------

def cgroup_populated(events_text: Any) -> Optional[int]:
    """Return canonical ``populated`` (0 or 1), else fail closed."""
    if not isinstance(events_text, str):
        raise LifecycleError("cgroup.events must be a string")
    values: List[int] = []
    for raw in events_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if parts[0] != "populated":
            continue
        if len(parts) != 2:
            raise LifecycleError(f"malformed populated line: {line!r}")
        token = parts[1]
        if token not in ("0", "1"):
            raise LifecycleError(f"non-canonical populated value: {token!r}")
        values.append(int(token))
    if not values:
        return None
    if len(values) > 1:
        raise LifecycleError("duplicate populated fields in cgroup.events")
    return values[0]


def resolve_reference_path(reference: str) -> str:
    if not isinstance(reference, str) or not reference.strip():
        raise LifecycleError("missing M5 reference")
    return reference.split("#", 1)[0]


# ---------------------------------------------------------------------------
# PART 1/3 — trusted-core M5 authority (capability, closure-held secret)
# ---------------------------------------------------------------------------

class _TrustCore:
    """Owns the sealing secret inside a closure; never a module attribute."""

    __slots__ = ("_seal_fn", "_verify_fn")

    def __init__(self) -> None:
        secret = secrets.token_bytes(32)  # closure-held; not module-global

        def _seal(payload: Dict[str, Any]) -> str:
            return hmac.new(secret, _canonical(payload).encode("utf-8"),
                            hashlib.sha256).hexdigest()

        def _verify(payload: Dict[str, Any], seal: Any) -> bool:
            return isinstance(seal, str) and hmac.compare_digest(seal, _seal(payload))

        self._seal_fn = _seal
        self._verify_fn = _verify

    def seal(self, payload: Dict[str, Any]) -> str:
        return self._seal_fn(payload)

    def verify(self, payload: Dict[str, Any], seal: Any) -> bool:
        return self._verify_fn(payload, seal)


#: Private construction token: only the trusted core holds this.
_M5_AUTHORITY_TOKEN = object()


@dataclass(frozen=True)
class M5Observation:
    """A sealed observation. Construction alone is NOT authenticity."""
    authority_id: str
    lifecycle_id: str
    proof_session_id: str
    sandbox_id: str
    pid: int
    pid_starttime: str
    cgroup: str
    evidence_reference: str
    evidence_sha256: str
    no_provider_execution: bool
    target_terminated: bool
    seal: str

    def payload(self) -> Dict[str, Any]:
        return {
            "authority_id": self.authority_id,
            "lifecycle_id": self.lifecycle_id,
            "proof_session_id": self.proof_session_id,
            "sandbox_id": self.sandbox_id,
            "pid": self.pid,
            "pid_starttime": self.pid_starttime,
            "cgroup": self.cgroup,
            "evidence_reference": self.evidence_reference,
            "evidence_sha256": self.evidence_sha256,
            "no_provider_execution": self.no_provider_execution,
            "target_terminated": self.target_terminated,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {**self.payload(), "seal": self.seal}


def observation_from_dict(payload: Dict[str, Any]) -> M5Observation:
    if not isinstance(payload, dict):
        raise LifecycleError("observation must be an object")
    try:
        return M5Observation(
            authority_id=payload["authority_id"],
            lifecycle_id=payload["lifecycle_id"],
            proof_session_id=payload["proof_session_id"],
            sandbox_id=payload["sandbox_id"],
            pid=payload["pid"],
            pid_starttime=payload["pid_starttime"],
            cgroup=payload["cgroup"],
            evidence_reference=payload["evidence_reference"],
            evidence_sha256=payload["evidence_sha256"],
            no_provider_execution=payload["no_provider_execution"],
            target_terminated=payload["target_terminated"],
            seal=payload["seal"])
    except (KeyError, TypeError) as exc:
        raise LifecycleError(
            f"malformed observation: {type(exc).__name__}") from None


class M5TrustAuthority:
    """Trusted-core capability that mints sealed M5 observations.

    There is NO public verifier parameter and NO module-global secret. The
    class cannot be subclassed (``__init_subclass__`` raises), and all trust
    decisions go through the module-level, non-polymorphic
    :func:`_verify_observation` which requires the EXACT authority type.
    Obtained only via :func:`trusted_m5_authority` (the trusted producer).
    """

    __slots__ = ("_core", "_authority_id")

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("M5TrustAuthority is a trusted-core capability and "
                        "cannot be subclassed")

    def __init__(self, *, _token: Any) -> None:
        if _token is not _M5_AUTHORITY_TOKEN:
            raise M5AuthorityError(
                "M5TrustAuthority is a trusted-core capability; construct via "
                "trusted_m5_authority()")
        self._core = _TrustCore()
        self._authority_id = "m5-authority-" + secrets.token_hex(6)

    @property
    def authority_id(self) -> str:
        return self._authority_id

    def mint(self, *, lifecycle_id: str, proof_session_id: str, sandbox_id: str,
             pid: int, pid_starttime: str, cgroup: str,
             reference: str, sha256: str) -> M5Observation:
        """Mint a sealed observation from the producer's observed values.

        Validates artifact integrity, teardown content, and identity binding.
        Only the trusted producer (M5 teardown probe) is expected to call this
        with kernel-observed values.
        """
        if not _valid_id(lifecycle_id) or not _valid_id(proof_session_id) \
                or not _valid_id(sandbox_id):
            raise M5AuthorityError("missing lifecycle/proof/sandbox identity")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise M5AuthorityError("invalid target pid")
        if not _valid_id(pid_starttime) or not _valid_id(cgroup):
            raise M5AuthorityError("missing target starttime/cgroup identity")
        if not _is_hex64(sha256):
            raise M5AuthorityError("M5 digest must be 64 lowercase hex")

        path = resolve_reference_path(reference)
        if not os.path.isfile(path):
            raise M5AuthorityError(f"M5 reference is not a readable artifact: {path!r}")
        actual = sha256_file(path)
        if actual != sha256:
            raise M5AuthorityError("M5 digest mismatch")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                evidence = json.loads(handle.read())
        except (OSError, ValueError) as exc:
            raise M5AuthorityError(
                f"M5 artifact not parseable JSON: {type(exc).__name__}") from None
        if not isinstance(evidence, dict):
            raise M5AuthorityError("M5 artifact must be a JSON object")

        teardown = evidence.get("teardown", {})
        post = evidence.get("post_kill", {})
        tracked = evidence.get("tracked", {})
        if not isinstance(teardown, dict) or not isinstance(post, dict) \
                or not isinstance(tracked, dict):
            raise M5AuthorityError("malformed teardown/post/tracked")
        if cgroup_populated(teardown.get("events_before")) != 1:
            raise M5AuthorityError("requires pre-teardown populated == 1")
        if cgroup_populated(teardown.get("events_after")) != 0:
            raise M5AuthorityError("requires post-teardown populated == 0")
        if post.get("target_terminated") is not True:
            raise M5AuthorityError("target_terminated must be boolean True")
        if evidence.get("no_provider_execution") is not True:
            raise M5AuthorityError("no_provider_execution must be boolean True")
        if tracked.get("pid") != pid:
            raise M5AuthorityError("artifact PID != claimed PID")
        if str(tracked.get("starttime")) != str(pid_starttime):
            raise M5AuthorityError("artifact starttime != claimed starttime")
        artifact_cgroup = evidence.get("delegation_context", {}).get("child_cgroup")
        if not _valid_id(artifact_cgroup) or artifact_cgroup != cgroup:
            raise M5AuthorityError("artifact cgroup != claimed cgroup")

        payload = {
            "authority_id": self._authority_id,
            "lifecycle_id": lifecycle_id,
            "proof_session_id": proof_session_id,
            "sandbox_id": sandbox_id,
            "pid": pid,
            "pid_starttime": pid_starttime,
            "cgroup": cgroup,
            "evidence_reference": reference,
            "evidence_sha256": sha256,
            "no_provider_execution": True,
            "target_terminated": True,
        }
        return M5Observation(**payload, seal=self._core.seal(payload))


def _verify_observation(authority: Any, observation: Any) -> bool:
    """Non-polymorphic trust decision: EXACT type + authority id + seal."""
    if type(authority) is not M5TrustAuthority:
        return False
    if not isinstance(observation, M5Observation):
        return False
    if authority._core is None:  # defensive
        return False
    if observation.authority_id != authority._authority_id:
        return False
    return authority._core.verify(observation.payload(), observation.seal)


#: The single process-local trusted-core authority (trusted producer capability).
_PROCESS_AUTHORITY = M5TrustAuthority(_token=_M5_AUTHORITY_TOKEN)


def trusted_m5_authority() -> M5TrustAuthority:
    """Return the trusted-core M5 authority capability.

    Intended caller: the trusted M5 producer (``scripts/m5_teardown_probe.py``).
    Possession of this capability is the trust anchor; it is NOT a boundary
    against arbitrary code already running in this process (documented).
    """
    return _PROCESS_AUTHORITY


# ---------------------------------------------------------------------------
# Transition + record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LifecycleTransition:
    seq: int
    state: LifecycleState
    at: float
    evidence_ref: Optional[str] = None
    evidence_sha256: Optional[str] = None
    provenance: Optional[str] = None
    m5_reference: Optional[str] = None
    m5_sha256: Optional[str] = None
    m5_observation: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"seq": self.seq, "state": self.state.name, "at": self.at,
                "evidence_ref": self.evidence_ref,
                "evidence_sha256": self.evidence_sha256,
                "provenance": self.provenance,
                "m5_reference": self.m5_reference,
                "m5_sha256": self.m5_sha256,
                "m5_observation": self.m5_observation}


def _record_body(rec: "LifecycleRecord") -> Dict[str, Any]:
    return {"lifecycle_id": rec.lifecycle_id,
            "proof_session_id": rec.proof_session_id,
            "sandbox_id": rec.sandbox_id, "pid": rec.pid,
            "pid_starttime": rec.pid_starttime, "cgroup": rec.cgroup,
            "transitions": [t.to_dict() for t in rec._transitions],
            "scope": "lifecycle_integrity_only"}


def _validate_structure(rec: "LifecycleRecord", *, authenticate: bool) -> None:
    if not _valid_id(rec.lifecycle_id):
        raise LifecycleError("missing lifecycle identity")
    if not _valid_id(rec.proof_session_id):
        raise LifecycleError("missing proof-session identity")
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
                if not isinstance(t.m5_observation, dict):
                    raise LifecycleError("m5-bound teardown lacks an observation")
                if not authenticate:
                    continue
                if type(rec._authority) is not M5TrustAuthority:
                    raise LifecycleError(
                        "M5-bound record requires the trusted-core authority "
                        "(fail closed)")
                obs = observation_from_dict(t.m5_observation)
                if not _verify_observation(rec._authority, obs):
                    raise LifecycleError("M5 observation seal invalid/unauthorized")
                if (obs.lifecycle_id != rec.lifecycle_id
                        or obs.proof_session_id != rec.proof_session_id
                        or obs.sandbox_id != rec.sandbox_id
                        or obs.pid != rec.pid
                        or str(obs.pid_starttime) != str(rec.pid_starttime)
                        or obs.cgroup != rec.cgroup
                        or obs.evidence_reference != t.m5_reference
                        or obs.evidence_sha256 != t.m5_sha256):
                    raise LifecycleError("M5 observation does not bind this lifecycle")
                # PART 6 — re-read and re-hash the artifact at every boundary.
                if sha256_file(resolve_reference_path(t.m5_reference)) != t.m5_sha256:
                    raise LifecycleError(
                        "M5 artifact replaced/tampered after binding")
            else:  # direct
                if t.m5_reference is not None or t.m5_sha256 is not None \
                        or t.m5_observation is not None:
                    raise LifecycleError("direct teardown must not carry M5")
        else:
            if (t.provenance is not None or t.m5_reference is not None
                    or t.m5_sha256 is not None or t.m5_observation is not None):
                raise LifecycleError("non-teardown transition must not carry M5")
    states = [t.state for t in ts]
    if LifecycleState.CLOSED in states:
        tv = next((t for t in ts
                   if t.state is LifecycleState.TEARDOWN_OBSERVED), None)
        if (tv is None or tv.provenance != TEARDOWN_PROVENANCE_M5_BOUND
                or not _valid_id(tv.m5_reference)):
            raise LifecycleError("CLOSED requires M5-bound teardown provenance")


@dataclass
class LifecycleRecord:
    lifecycle_id: str
    proof_session_id: str
    sandbox_id: Optional[str] = None
    pid: Optional[int] = None
    pid_starttime: Optional[str] = None
    cgroup: Optional[str] = None
    _transitions: List[LifecycleTransition] = field(default_factory=list)
    _authority: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_structure(self, authenticate=False)

    @property
    def transitions(self) -> Tuple[LifecycleTransition, ...]:
        return tuple(self._transitions)

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
        expected = self._expected_next()
        if expected is None:
            raise LifecycleError("lifecycle already CLOSED")
        if state is not expected:
            raise LifecycleError(
                f"impossible transition {self.state.name} -> {state.name}")

    def _append(self, state: LifecycleState, evidence_ref: Optional[str] = None,
                evidence_sha256: Optional[str] = None,
                provenance: Optional[str] = None) -> None:
        if provenance == TEARDOWN_PROVENANCE_M5_BOUND:
            raise LifecycleError("m5-bound provenance requires bind_m5_teardown()")
        self._require_next(state)
        if provenance is not None and provenance != TEARDOWN_PROVENANCE_DIRECT:
            raise LifecycleError(f"unknown teardown provenance {provenance!r}")
        if state in EVIDENCE_REQUIRED_STATES:
            if not _valid_id(evidence_ref) or not _is_hex64(evidence_sha256):
                raise LifecycleError(f"{state.name} requires evidence_ref + sha256")
        seq = len(self._transitions)
        self._transitions.append(LifecycleTransition(
            seq=seq, state=state, at=float(seq),
            evidence_ref=evidence_ref, evidence_sha256=evidence_sha256,
            provenance=provenance))

    def _append_m5_bound(self, observation: M5Observation) -> None:
        if self._expected_next() is not LifecycleState.TEARDOWN_OBSERVED:
            raise LifecycleError("impossible transition to TEARDOWN_OBSERVED")
        seq = len(self._transitions)
        self._transitions.append(LifecycleTransition(
            seq=seq, state=LifecycleState.TEARDOWN_OBSERVED, at=float(seq),
            evidence_ref=observation.evidence_reference,
            evidence_sha256=observation.evidence_sha256,
            provenance=TEARDOWN_PROVENANCE_M5_BOUND,
            m5_reference=observation.evidence_reference,
            m5_sha256=observation.evidence_sha256,
            m5_observation=observation.to_dict()))

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
            return
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
            return
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
        """Record a DIRECT teardown observation (B4-1). DIRECT-only."""
        if provenance == TEARDOWN_PROVENANCE_M5_BOUND:
            raise LifecycleError("m5-bound provenance requires bind_m5_teardown()")
        if provenance != TEARDOWN_PROVENANCE_DIRECT:
            raise LifecycleError(f"unknown teardown provenance {provenance!r}")
        if m5_reference is not None or m5_sha256 is not None:
            raise LifecycleError("M5 reference/digest requires bind_m5_teardown()")
        if self.teardown_transition is not None:
            raise LifecycleError("teardown already observed (no rebind)")
        self._append(LifecycleState.TEARDOWN_OBSERVED,
                     evidence_ref=evidence_ref, evidence_sha256=evidence_sha256,
                     provenance=TEARDOWN_PROVENANCE_DIRECT)

    def close(self) -> None:
        tev = self.teardown_transition
        if tev is None:
            raise LifecycleError("cannot close without teardown evidence")
        if tev.provenance != TEARDOWN_PROVENANCE_M5_BOUND:
            raise LifecycleError("cannot close without M5-bound provenance")
        if not _valid_id(tev.m5_reference):
            raise LifecycleError("cannot close without a non-None M5 reference")
        _validate_structure(self, authenticate=True)  # seal + identity + artifact
        self._append(LifecycleState.CLOSED)

    # --- serialization --------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        _validate_structure(self, authenticate=True)
        body = _record_body(self)
        _reject_authority(body, "lifecycle record")
        digest = hashlib.sha256(_canonical(body).encode()).hexdigest()
        return {**body, "lifecycle_sha256": digest}

    @staticmethod
    def from_dict(payload: Dict[str, Any], *,
                  authority: Optional[M5TrustAuthority] = None) -> "LifecycleRecord":
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
                    m5_sha256=t.get("m5_sha256"),
                    m5_observation=t.get("m5_observation")))
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
        rec._authority = authority if type(authority) is M5TrustAuthority else None
        got = payload.get("lifecycle_sha256")
        check = dict(payload); check.pop("lifecycle_sha256", None)
        if got != hashlib.sha256(_canonical(check).encode()).hexdigest():
            raise LifecycleError("lifecycle integrity hash mismatch")
        # PART 6/9 — authenticity + artifact integrity must be re-established;
        # serialized JSON + recomputed hash is NOT sufficient.
        _validate_structure(rec, authenticate=True)
        return rec


def bind_m5_teardown(rec: LifecycleRecord, m5_evidence: Dict[str, Any],
                     reference: str, sha256: str, *,
                     observation: M5Observation,
                     authority: M5TrustAuthority) -> None:
    """Bind an authority-authenticated observation. The ONLY M5-bound path."""
    if rec.teardown_transition is not None:
        raise LifecycleError("teardown already observed (no rebind)")
    if type(authority) is not M5TrustAuthority:
        raise LifecycleError("trusted-core authority required (fail closed)")
    if not _verify_observation(authority, observation):
        raise LifecycleError("missing/invalid M5 observation (fail closed)")
    if (observation.lifecycle_id != rec.lifecycle_id
            or observation.proof_session_id != rec.proof_session_id
            or observation.sandbox_id != rec.sandbox_id
            or observation.pid != rec.pid
            or str(observation.pid_starttime) != str(rec.pid_starttime)
            or observation.cgroup != rec.cgroup
            or observation.evidence_reference != reference
            or observation.evidence_sha256 != sha256):
        raise LifecycleError("M5 observation does not bind this lifecycle")
    if not _is_hex64(sha256):
        raise LifecycleError("M5 digest must be 64 lowercase hex")
    if sha256_file(resolve_reference_path(reference)) != sha256:
        raise LifecycleError("M5 artifact changed after authentication")
    if not isinstance(m5_evidence, dict) or \
            not _evidence_equals(reference, m5_evidence):
        raise LifecycleError("caller M5 evidence does not match the artifact")
    rec._authority = authority
    rec._append_m5_bound(observation)


def _evidence_equals(reference: str, evidence: Dict[str, Any]) -> bool:
    path = reference.split("#", 1)[0]
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.loads(handle.read()) == evidence
    except (OSError, ValueError):
        return False


def _m5_observation_status(rec: LifecycleRecord,
                           authority: Optional[M5TrustAuthority]
                           ) -> Tuple[bool, str]:
    tev = rec.teardown_transition
    if tev is None:
        return False, "no teardown transition"
    if tev.provenance != TEARDOWN_PROVENANCE_M5_BOUND:
        return False, "teardown is not m5-bound"
    if not isinstance(tev.m5_observation, dict):
        return False, "missing observation"
    # Attestation requires an EXPLICIT live authority (fail closed).
    auth = authority
    if type(auth) is not M5TrustAuthority:
        return False, "no trusted-core authority supplied (fail closed)"
    try:
        obs = observation_from_dict(tev.m5_observation)
    except LifecycleError as exc:
        return False, str(exc)
    if not _verify_observation(auth, obs):
        return False, "observation seal invalid/unauthorized"
    try:
        if sha256_file(resolve_reference_path(tev.m5_reference)) != tev.m5_sha256:
            return False, "artifact replaced/deleted after binding"
    except LifecycleError:
        return False, "artifact unavailable"
    return True, ""


def attest_lifecycle(rec: LifecycleRecord,
                     m5_evidence: Optional[Dict[str, Any]] = None,
                     m5_reference: Optional[str] = None,
                     *, authority: Optional[M5TrustAuthority] = None,
                     ) -> AttestationResult:
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
    check("transition-ordering", [t.seq for t in ts] == list(range(len(ts))))
    states = [t.state for t in ts]
    check("transition-contiguity",
          states == [LifecycleState(i) for i in range(len(states))])
    tev = [t for t in ts if t.state is LifecycleState.TEARDOWN_OBSERVED]
    check("teardown-evidence-present", len(tev) == 1)
    check("teardown-evidence-hashed",
          bool(tev) and _is_hex64(tev[0].evidence_sha256))
    check("teardown-provenance-m5-bound",
          bool(tev) and tev[0].provenance == TEARDOWN_PROVENANCE_M5_BOUND)
    check("m5-reference-present", bool(tev) and _valid_id(tev[0].m5_reference))
    auth_ok, auth_detail = _m5_observation_status(rec, authority)
    check("m5-observation-authenticated", auth_ok, auth_detail)
    check("closure-after-teardown",
          LifecycleState.CLOSED in states and len(tev) == 1
          and states.index(LifecycleState.CLOSED)
          > states.index(LifecycleState.TEARDOWN_OBSERVED))
    try:
        _reject_authority(_record_body(rec), "lifecycle attestation")
        authority_clean = True
    except LifecycleError:
        authority_clean = False
    check("no-authority-smuggling", authority_clean)

    if m5_evidence is not None and auth_ok:
        check("m5-evidence-matches-artifact",
              _evidence_equals(tev[0].m5_reference, m5_evidence))
        tracked = m5_evidence.get("tracked", {})
        check("m5-workload-identity-match",
              isinstance(tracked, dict) and tracked.get("pid") == rec.pid
              and str(tracked.get("starttime")) == str(rec.pid_starttime))
        check("m5-no-provider-execution",
              m5_evidence.get("no_provider_execution") is True)

    status = AttestationStatus.ATTESTED if not failures else AttestationStatus.INVALID
    tev0 = tev[0] if tev else None
    try:
        lifecycle_sha = hashlib.sha256(
            _canonical(_record_body(rec)).encode()).hexdigest()
    except (AttributeError, TypeError):
        lifecycle_sha = None
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
        quarantined=False, evidence=evidence)


__all__ = [
    "EVIDENCE_REQUIRED_STATES", "FORBIDDEN_AUTHORITY_KEYS", "LifecycleError",
    "M5AuthorityError", "LifecycleRecord", "LifecycleState", "LifecycleTransition",
    "M5Observation", "M5TrustAuthority",
    "TEARDOWN_PROVENANCE_DIRECT", "TEARDOWN_PROVENANCE_M5_BOUND",
    "attest_lifecycle", "bind_m5_teardown", "cgroup_populated",
    "observation_from_dict", "resolve_reference_path", "sha256_file",
    "trusted_m5_authority", "verify_file_sha256",
]
