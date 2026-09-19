"""raphael_ibm_bob.b4_lifecycle — governed lifecycle record + attestation.

Phase 2C B4-LIFECYCLE. Connects RAPHAEL's existing B4 attestation semantics to
the Phase 2C sandbox lifecycle WITHOUT executing any provider.

This module attests LIFECYCLE INTEGRITY ONLY. It cannot express provider
success, mission completion, or authorization. Authority/authorization keys
are rejected, not stored.

Three properties are kept STRICTLY separate (B4-2 authenticity correction):

  A. ARTIFACT INTEGRITY   — "these exact bytes hash to this digest."
  B. ARTIFACT AUTHENTICITY— "these bytes were produced by the trusted M5
                             observation authority for THIS lifecycle."
  C. LIFECYCLE INTEGRITY  — "this record has not been modified since recorded."

``sha256_file`` solves A. It does NOT solve B. An M5-bound lifecycle transition
is therefore only created by :func:`bind_m5_teardown` when supplied an
``M5Observation`` minted by a live :class:`M5TrustAuthority` — a process-local
authority whose final trust decision is an injected verifier. Both the
authority and its verifier default to FAIL CLOSED: without a configured
verifier the authority refuses to mint, so a caller cannot turn a
self-authored, schema-valid, correctly-hashed JSON file into M5-bound
provenance.

Design reconnaissance (PART 0):
  * trusted M5 producer ....... ``scripts/m5_teardown_probe.py`` (live cgroup
                                ``cgroup.kill`` -> ``populated 1->0``, PID +
                                ``/proc/<pid>/stat`` starttime anti-reuse).
  * what makes it trusted ..... it performs the live OS observation; it does
                                not merely read a caller-supplied file.
  * persistent trust root .... NONE. :mod:`raphael_ibm_bob.seal` is unkeyed by
                                design (integrity, not authenticity). There is
                                no committed secret and no signing root.
  * trust primitive chosen ... an explicit in-process ``M5TrustAuthority`` that
                                mints a sealed (HMAC-SHA256 with a per-process
                                secret) observation, bound to the lifecycle
                                identity and the artifact digest. The module
                                fails closed when no authority/verifier is
                                available, and a per-process seal does not
                                survive serialization into another process.
  * why an attacker caller cannot manufacture it ... the public file-path API
                                no longer grants M5-bound provenance; a token
                                must be minted by a live authority whose
                                verifier is the trusted producer. A sealed
                                observation cannot be forged without the
                                process secret, and it is not exportable.
  * serialization ............ ``to_dict`` may serialize (integrity); but
                                ``from_dict`` REQUIRES a live authority to
                                re-establish authenticity and FAILS CLOSED
                                without it. A serialized record cannot regain
                                ATTESTED merely because its JSON/digest/record
                                hash are valid.

Honesty note (recorded, not hidden): an in-process authority is a capability
boundary, not a cryptographic boundary — code already executing inside the
RAPHAEL process could call the authority. The verifier is the trust anchor and
defaults to fail-closed; a persistent, cross-process cryptographic root is a
FUTURE requirement, not something this module fakes.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Tuple

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

#: Per-process secret. Never persisted, never committed, never logged.
_AUTHORITY_SECRET = secrets.token_bytes(32)


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
# R6 — file digest helpers (artifact INTEGRITY)
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
# B4-3 / PART 11 — canonical cgroup.events parser
# ---------------------------------------------------------------------------

def cgroup_populated(events_text: Any) -> Optional[int]:
    """Return the canonical ``populated`` value (0 or 1), else fail closed.

    Field-based (never substring). Accepts ONLY the kernel's canonical grammar
    ``populated 0`` / ``populated 1``; malformed-but-integer forms such as
    ``01``, ``-0``, ``-1``, ``10`` are rejected (PART 11).
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
            continue
        if len(parts) != 2:
            raise LifecycleError(f"malformed populated line: {line!r}")
        token = parts[1]
        if token not in ("0", "1"):
            raise LifecycleError(
                f"non-canonical populated value: {token!r}")
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
# B4-2 — M5 trust authority (artifact AUTHENTICITY)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class M5Observation:
    """A sealed observation minted by :class:`M5TrustAuthority`.

    The seal is HMAC-SHA256 over the canonical observation payload using the
    per-process authority secret. It is not exportable/forgeable without the
    secret, and it does not survive into another process.
    """
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


def _seal_payload(payload: Dict[str, Any]) -> str:
    return hmac.new(
        _AUTHORITY_SECRET, _canonical(payload).encode("utf-8"),
        hashlib.sha256).hexdigest()


def _seal_valid(observation: M5Observation) -> bool:
    if not isinstance(observation, M5Observation):
        return False
    return hmac.compare_digest(observation.seal,
                               _seal_payload(observation.payload()))


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
    """Process-local authority that mints authenticated M5 observations.

    The final trust decision is the injected ``verifier``. With no verifier the
    authority FAILS CLOSED (refuses to mint). The verifier is the trusted M5
    producer boundary; in production the M5 teardown probe is the caller.
    """

    def __init__(self, verifier: Optional[Callable[[Dict[str, Any]], bool]] = None,
                 *, authority_id: Optional[str] = None) -> None:
        self._verifier = verifier
        self._authority_id = authority_id or ("m5-authority-" + secrets.token_hex(6))

    @property
    def authority_id(self) -> str:
        return self._authority_id

    @property
    def available(self) -> bool:
        return self._verifier is not None

    def verify(self, observation: M5Observation) -> bool:
        return _seal_valid(observation) and \
            observation.authority_id == self._authority_id

    def mint(self, *, lifecycle_id: str, proof_session_id: str, sandbox_id: str,
             pid: int, pid_starttime: str, cgroup: str,
             reference: str, sha256: str) -> M5Observation:
        """Authenticate the artifact AND its identity, then seal an observation.

        Fail-closed steps: authority must have a verifier; artifact bytes must
        hash to ``sha256``; identity fields must be present; the artifact's
        recorded PID/starttime/cgroup must match the claimed identity; the
        teardown content must be canonical (populated 1->0, strict booleans);
        and finally the injected trusted verifier must accept.
        """
        if self._verifier is None:
            raise M5AuthorityError(
                "M5 trust authority has no verifier configured (fail closed); "
                "a trusted M5 producer must supply one")
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
            raise M5AuthorityError(
                f"M5 digest mismatch for {path!r}: expected {sha256} got {actual}")
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
            raise M5AuthorityError("M5 artifact has malformed teardown/post/tracked")
        before = cgroup_populated(teardown.get("events_before"))
        after = cgroup_populated(teardown.get("events_after"))
        if before != 1:
            raise M5AuthorityError("M5 evidence requires pre-teardown populated == 1")
        if after != 0:
            raise M5AuthorityError("M5 evidence requires post-teardown populated == 0")
        if post.get("target_terminated") is not True:
            raise M5AuthorityError("target_terminated must be boolean True")
        if evidence.get("no_provider_execution") is not True:
            raise M5AuthorityError("no_provider_execution must be boolean True")

        # PART 3 — artifact identity must match the claimed lifecycle identity.
        if tracked.get("pid") != pid:
            raise M5AuthorityError("artifact target PID != lifecycle target PID")
        if str(tracked.get("starttime")) != str(pid_starttime):
            raise M5AuthorityError("artifact starttime != lifecycle starttime")
        artifact_cgroup = evidence.get("delegation_context", {}).get("child_cgroup")
        if not _valid_id(artifact_cgroup) or artifact_cgroup != cgroup:
            raise M5AuthorityError("artifact cgroup != lifecycle cgroup")

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
        # Final trusted-producer gate (the trust anchor).
        if not bool(self._verifier(payload)):
            raise M5AuthorityError("trusted verifier rejected the observation")
        return M5Observation(**payload, seal=_seal_payload(payload))


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


def _validate_structure(rec: "LifecycleRecord", *, require_authority: bool = False,
                        authority: Optional["M5TrustAuthority"] = None) -> None:
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
                obs = observation_from_dict(t.m5_observation)
                if not _seal_valid(obs):
                    raise LifecycleError("m5 observation seal invalid/foreign-process")
                # PART 3 — the observation must bind the record identity.
                if (obs.lifecycle_id != rec.lifecycle_id
                        or obs.proof_session_id != rec.proof_session_id
                        or obs.sandbox_id != rec.sandbox_id
                        or obs.pid != rec.pid
                        or str(obs.pid_starttime) != str(rec.pid_starttime)
                        or obs.cgroup != rec.cgroup
                        or obs.evidence_reference != t.m5_reference
                        or obs.evidence_sha256 != t.m5_sha256):
                    raise LifecycleError("m5 observation does not bind this lifecycle")
                if require_authority:
                    if authority is None:
                        raise LifecycleError(
                            "M5-bound record requires a live trust authority "
                            "(fail closed)")
                    if not authority.verify(obs):
                        raise LifecycleError(
                            "M5 observation not authenticated by this authority")
            else:  # direct
                if t.m5_reference is not None or t.m5_sha256 is not None \
                        or t.m5_observation is not None:
                    raise LifecycleError(
                        "direct teardown must not carry M5 observation")
        else:
            if (t.provenance is not None or t.m5_reference is not None
                    or t.m5_sha256 is not None or t.m5_observation is not None):
                raise LifecycleError(
                    "non-teardown transition must not carry provenance/M5")
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

    def __post_init__(self) -> None:
        _validate_structure(self, require_authority=False)

    @property
    def transitions(self) -> Tuple[LifecycleTransition, ...]:
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
            raise LifecycleError(
                "m5-bound provenance may only be established by "
                "bind_m5_teardown()")
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
            raise LifecycleError(
                "m5-bound provenance may only be established by bind_m5_teardown()")
        if provenance != TEARDOWN_PROVENANCE_DIRECT:
            raise LifecycleError(f"unknown teardown provenance {provenance!r}")
        if m5_reference is not None or m5_sha256 is not None:
            raise LifecycleError(
                "M5 reference/digest may only be supplied via bind_m5_teardown()")
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
            raise LifecycleError("cannot close without M5-bound teardown provenance")
        if not _valid_id(tev.m5_reference):
            raise LifecycleError("cannot close without a non-None M5 reference")
        # Authenticity re-check in-process (seal validity).
        _validate_structure(self, require_authority=False)
        self._append(LifecycleState.CLOSED)

    # --- serialization --------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        _validate_structure(self, require_authority=False)
        body = _record_body(self)
        _reject_authority(body, "lifecycle record")
        digest = hashlib.sha256(_canonical(body).encode()).hexdigest()
        return {**body, "lifecycle_sha256": digest}

    @staticmethod
    def from_dict(payload: Dict[str, Any], *,
                  authority: Optional["M5TrustAuthority"] = None) -> "LifecycleRecord":
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
        got = payload.get("lifecycle_sha256")
        check = dict(payload); check.pop("lifecycle_sha256", None)
        if got != hashlib.sha256(_canonical(check).encode()).hexdigest():
            raise LifecycleError("lifecycle integrity hash mismatch")
        # PART 6/7 — authenticity must be re-established by a LIVE authority;
        # a serialized record cannot regain ATTESTED from JSON alone.
        _validate_structure(rec, require_authority=True, authority=authority)
        return rec


def bind_m5_teardown(rec: LifecycleRecord, m5_evidence: Dict[str, Any],
                     reference: str, sha256: str, *,
                     observation: "M5Observation") -> None:
    """Bind an AUTHORITY-AUTHENTICATED M5 observation into lifecycle closure.

    The ONLY path to M5-bound provenance. Requires an ``M5Observation`` minted
    by a live :class:`M5TrustAuthority`. A caller-authored file + digest (even
    with correct schema and hash) CANNOT satisfy this without such an
    observation, and the observation is bound to THIS lifecycle's identity.
    """
    if rec.teardown_transition is not None:
        raise LifecycleError("teardown already observed (no rebind)")
    if not isinstance(observation, M5Observation) or not _seal_valid(observation):
        raise LifecycleError("missing or invalid M5 observation (fail closed)")
    # Identity binding: the observation must be for this lifecycle.
    if (observation.lifecycle_id != rec.lifecycle_id
            or observation.proof_session_id != rec.proof_session_id
            or observation.sandbox_id != rec.sandbox_id
            or observation.pid != rec.pid
            or str(observation.pid_starttime) != str(rec.pid_starttime)
            or observation.cgroup != rec.cgroup
            or observation.evidence_reference != reference
            or observation.evidence_sha256 != sha256):
        raise LifecycleError("M5 observation does not bind this lifecycle")
    # Re-verify artifact integrity + equality with the supplied evidence.
    if not _is_hex64(sha256):
        raise LifecycleError("M5 digest must be 64 lowercase hex")
    actual = sha256_file(resolve_reference_path(reference))
    if actual != sha256:
        raise LifecycleError("M5 artifact changed after authentication")
    if not isinstance(m5_evidence, dict):
        raise LifecycleError("M5 evidence must be a dict")
    if sha256_file(reference.split("#", 1)[0]) != sha256 or \
            not _evidence_equals(reference, m5_evidence):
        raise LifecycleError(
            "caller-supplied M5 evidence does not match the authenticated artifact")
    rec._append_m5_bound(observation)


def _evidence_equals(reference: str, evidence: Dict[str, Any]) -> bool:
    path = reference.split("#", 1)[0]
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.loads(handle.read()) == evidence
    except (OSError, ValueError):
        return False


def _m5_observation_status(rec: LifecycleRecord,
                           authority: Optional["M5TrustAuthority"]
                           ) -> Tuple[bool, str]:
    tev = rec.teardown_transition
    if tev is None:
        return False, "no teardown transition"
    if tev.provenance != TEARDOWN_PROVENANCE_M5_BOUND:
        return False, "teardown is not m5-bound"
    if not isinstance(tev.m5_observation, dict):
        return False, "missing observation"
    try:
        obs = observation_from_dict(tev.m5_observation)
    except LifecycleError as exc:
        return False, str(exc)
    if not _seal_valid(obs):
        return False, "observation seal invalid or from another process"
    if authority is None:
        return False, "no live M5 trust authority available (fail closed)"
    if not authority.verify(obs):
        return False, "observation not authenticated by this authority"
    return True, ""


def attest_lifecycle(rec: LifecycleRecord,
                     m5_evidence: Optional[Dict[str, Any]] = None,
                     m5_reference: Optional[str] = None,
                     *,
                     authority: Optional["M5TrustAuthority"] = None,
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
    # PART 6/7 — authenticity (not just integrity) is required to attest.
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
    "verify_file_sha256",
]
