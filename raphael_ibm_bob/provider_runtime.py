"""raphael_ibm_bob.provider_runtime — Phase 2C ProviderRuntime boundary.

The MINIMUM out-of-process boundary for the single authorized C1A
capability (``static_file_inspect`` → T3MP3ST ``binary_sink_scan``).

    ActionRequest + ScopeHandoff
        -> ProviderRuntime.invoke(...)
        -> out-of-process adapter (HTTP/MCP)
        -> ProviderResult (closed schema)
        -> RAPHAEL normalization
        -> B4 option-B attestation

Hard boundaries (M1-M7 from the Phase 2B-delta hardening design):

    M3  capability class — only C1A is invocable; no generic dispatch
    M4  ProviderResult is a CLOSED allow-list; authority fields are
        REJECTED fail-closed, never ignored
    M5  cancellation.acknowledged only after externally observed teardown
    M6  provenance fails closed; provider IDs are never authoritative
    M7  exceeding a limit MUST NOT remain success (partial/failure)

This module NEVER executes a provider process, never imports the Broker/
Policy/QualityGate, and never produces VERIFIED / REFUTED / COMPLETE /
authorization / policy approval / gate state. It normalizes evidence.
"""
from __future__ import annotations

import json
import os
import time
import unicodedata
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from raphael_ibm_bob.b4_attestation import (
    AttestationResult,
    BoundaryToolCall,
    BoundaryToolResult,
    ProofSession,
    ProviderExecution,
    attest,
)
from raphael_ibm_bob.contracts import ActionRequest

#: The single Phase 2C capability and its provider implementation tool.
C1A_CAPABILITY_ID = "C1A static_file_inspect"
C1A_PROVIDER_ID = "t3mp3st"
C1A_TOOL = "binary_sink_scan"


class ProviderState(str, Enum):
    """Bounded ProviderResult states (closed vocabulary)."""
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


class ProviderRuntimeError(Exception):
    """Base error for the ProviderRuntime boundary."""


class ScopeViolation(ProviderRuntimeError):
    """The handoff/request failed RAPHAEL-owned scope enforcement."""


class ProviderSchemaError(ProviderRuntimeError):
    """The provider payload violated the closed schema (M4)."""


class ProvenanceError(ProviderRuntimeError):
    """Provenance was missing/malformed/mismatched (M6)."""


# ---------------------------------------------------------------------------
# M4 — closed allow-list / authority-field rejection
# ---------------------------------------------------------------------------

#: Fields the closed ProviderResult parser accepts (nothing else).
ALLOWED_PAYLOAD_KEYS = frozenset({
    "results", "artifacts", "provider_message", "operation_id",
    "result_hash", "truncated",
})

#: Authority categories that must be REJECTED on presence (normalized).
_DENIED_KEY_CATEGORIES: Dict[str, str] = {}
for _category, _keys in {
    "gate": ("verifyGate",),
    "verdict": ("verdict", "conclusion", "validated", "verified", "refuted"),
    "severity/risk": ("severity", "assertedSeverity", "risk", "priority",
                      "impact", "cvss"),
    "confidence": ("confidence", "confidence_score", "score", "probability",
                   "certainty", "trust"),
    "authority": ("authorized", "approved", "approval", "permission", "policy",
                  "gate_pass", "gatePass"),
    "completeness": ("complete", "COMPLETE", "done"),
    "direction": ("recommendation", "recommendations", "next_steps",
                  "directives"),
}.items():
    for _k in _keys:
        _DENIED_KEY_CATEGORIES[_k] = _category


def _normalize_key(key: str) -> str:
    """Case/separator/Unicode-fold a key for deny-matching (anti-evasion)."""
    folded = unicodedata.normalize("NFKC", key).casefold()
    return "".join(ch for ch in folded if ch.isalnum())


_DENIED_NORMALIZED = {
    _normalize_key(k): cat for k, cat in _DENIED_KEY_CATEGORIES.items()}


def _reject_duplicate_keys(pairs):
    seen: Dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ProviderSchemaError(f"duplicate JSON key: {key!r}")
        seen[key] = value
    return seen


def parse_closed_payload(raw: bytes, max_bytes: int) -> Dict[str, Any]:
    """Parse a provider payload against the CLOSED schema (M4).

    Rejects: oversized payload, non-object, duplicate keys, any authority
    field (by normalized name), and any key outside the allow-list.
    """
    if not isinstance(raw, (bytes, bytearray)):
        raise ProviderSchemaError("provider payload must be bytes")
    if len(raw) > max_bytes:
        raise ProviderSchemaError(
            f"payload exceeds byte cap: {len(raw)} > {max_bytes}")
    try:
        data = json.loads(raw.decode("utf-8"),
                          object_pairs_hook=_reject_duplicate_keys)
    except ProviderSchemaError:
        raise
    except (UnicodeDecodeError, ValueError) as exc:
        raise ProviderSchemaError(f"provider payload not JSON: {exc}") from None
    if not isinstance(data, dict):
        raise ProviderSchemaError("provider payload must be a JSON object")
    for key in data:
        normalized = _normalize_key(key)
        if normalized in _DENIED_NORMALIZED:
            raise ProviderSchemaError(
                f"authority field rejected (M4): {key!r} "
                f"({_DENIED_NORMALIZED[normalized]})")
        if key not in ALLOWED_PAYLOAD_KEYS:
            raise ProviderSchemaError(
                f"field outside closed allow-list: {key!r}")
    return data


# ---------------------------------------------------------------------------
# Scope (M1/M2/M3) — RAPHAEL-owned
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScopeHandoff:
    """RAPHAEL-owned scope bound before invocation."""
    run_id: str
    proof_session_id: str
    action_request_id: str
    invocation_id: str
    fixture_root: str
    fixture_path: str
    capability_id: str = C1A_CAPABILITY_ID
    provider_id: str = C1A_PROVIDER_ID
    network_denied: bool = True
    timeout_seconds: float = 10.0
    max_response_bytes: int = 65536
    max_results: int = 64
    max_artifacts: int = 8
    max_artifact_bytes: int = 1_048_576
    allow_directory: bool = False
    sandbox_digest: str = ""


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _canonical(path: str) -> str:
    return os.path.normpath(os.path.abspath(path))


def validate_scope(handoff: ScopeHandoff,
                   request: ActionRequest) -> None:
    """Enforce RAPHAEL-owned scope; raise ScopeViolation on any breach.

    Fails closed. Capability must be exactly C1A; the request target must
    equal the exact canonical fixture literal and live under the fixture
    root; directory mode, network, and unbounded parameters are refused.
    """
    for name, value in (("run_id", handoff.run_id),
                        ("proof_session_id", handoff.proof_session_id),
                        ("action_request_id", handoff.action_request_id),
                        ("invocation_id", handoff.invocation_id),
                        ("fixture_root", handoff.fixture_root),
                        ("fixture_path", handoff.fixture_path)):
        if not _valid_id(value):
            raise ScopeViolation(f"{name} missing/invalid")
    if handoff.capability_id != C1A_CAPABILITY_ID:
        raise ScopeViolation(
            f"capability not authorized for Phase 2C: "
            f"{handoff.capability_id!r}")
    if handoff.provider_id != C1A_PROVIDER_ID:
        raise ScopeViolation(f"unknown provider: {handoff.provider_id!r}")
    if handoff.allow_directory:
        raise ScopeViolation("directory mode is forbidden for this proof")
    if not handoff.network_denied:
        raise ScopeViolation("network egress must be denied")
    if handoff.timeout_seconds <= 0:
        raise ScopeViolation("timeout must be positive")
    if handoff.max_response_bytes <= 0 or handoff.max_results <= 0:
        raise ScopeViolation("output limits must be positive")
    for name in ("fixture_root", "fixture_path"):
        value = getattr(handoff, name)
        if not os.path.isabs(value) or _canonical(value) != value:
            raise ScopeViolation(f"{name} must be canonical absolute")
    if not (handoff.fixture_path == os.path.join(
            handoff.fixture_root,
            os.path.relpath(handoff.fixture_path, handoff.fixture_root))):
        raise ScopeViolation("fixture_path escapes fixture_root")
    if os.path.dirname(handoff.fixture_path) != handoff.fixture_root:
        raise ScopeViolation("single-file mode: fixture must be direct child "
                             "of the RAPHAEL-owned root")
    if request.capability.value != "read":
        # The C1A proof is expressed as a READ action over the fixture.
        raise ScopeViolation(
            f"C1A requires a read-class ActionRequest, got "
            f"{request.capability.value!r}")
    target = (request.target or "").replace("\\", "/")
    if not target or _canonical(target) != handoff.fixture_path:
        raise ScopeViolation(
            f"target must equal the exact fixture literal: {target!r} != "
            f"{handoff.fixture_path!r}")
    if request.timeout_seconds is not None and request.timeout_seconds <= 0:
        raise ScopeViolation("request timeout must be positive when set")


# ---------------------------------------------------------------------------
# ProviderResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderResult:
    """Normalized, bounded provider outcome (never an authority)."""
    state: ProviderState
    run_id: str
    action_request_id: str
    invocation_id: str
    proof_session_id: str
    capability_id: str
    provider_id: str
    results: Tuple[Dict[str, Any], ...] = ()
    artifacts: Tuple[str, ...] = ()
    result_hash: Optional[str] = None
    truncated: bool = False
    cancellation_acknowledged: bool = False
    provider_message: str = ""
    operation_id_untrusted: Optional[str] = None
    error: str = ""

    @property
    def success(self) -> bool:
        return self.state is ProviderState.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "run_id": self.run_id,
            "action_request_id": self.action_request_id,
            "invocation_id": self.invocation_id,
            "proof_session_id": self.proof_session_id,
            "capability_id": self.capability_id,
            "provider_id": self.provider_id,
            "results": [dict(r) for r in self.results],
            "artifacts": list(self.artifacts),
            "result_hash": self.result_hash,
            "truncated": self.truncated,
            "cancellation_acknowledged": self.cancellation_acknowledged,
            "provider_message": self.provider_message,
            "operation_id_untrusted": self.operation_id_untrusted,
            "error": self.error,
        }


_ALLOWED_RESULT_KEYS = frozenset({"path", "kind", "offset", "size", "hash"})


def normalize_result(handoff: ScopeHandoff, raw: bytes) -> ProviderResult:
    """M4/M6/M7 normalize a raw provider payload into a ProviderResult."""
    def _fail(state: ProviderState, msg: str) -> ProviderResult:
        return ProviderResult(
            state=state, run_id=handoff.run_id,
            action_request_id=handoff.action_request_id,
            invocation_id=handoff.invocation_id,
            proof_session_id=handoff.proof_session_id,
            capability_id=handoff.capability_id,
            provider_id=handoff.provider_id, error=msg[:512])

    try:
        data = parse_closed_payload(raw, handoff.max_response_bytes)
    except ProviderSchemaError as exc:
        return _fail(ProviderState.FAILURE, f"schema:{exc}")

    # M6 — provenance is fail-closed; provider IDs are untrusted metadata.
    operation_id = data.get("operation_id")
    if operation_id is not None and not isinstance(operation_id, str):
        return _fail(ProviderState.DENIED, "provenance: operation_id invalid")

    results_raw = data.get("results", [])
    if not isinstance(results_raw, list):
        return _fail(ProviderState.FAILURE, "results must be a list")
    if len(results_raw) > handoff.max_results:
        return ProviderResult(
            state=ProviderState.PARTIAL, run_id=handoff.run_id,
            action_request_id=handoff.action_request_id,
            invocation_id=handoff.invocation_id,
            proof_session_id=handoff.proof_session_id,
            capability_id=handoff.capability_id,
            provider_id=handoff.provider_id, truncated=True,
            error=f"results limit: {len(results_raw)}>"
                  f"{handoff.max_results}")

    results: List[Dict[str, Any]] = []
    for item in results_raw:
        if not isinstance(item, dict) or set(item) - _ALLOWED_RESULT_KEYS:
            return _fail(ProviderState.FAILURE, "result item outside schema")
        path = item.get("path")
        if not isinstance(path, str) or path == "":
            return _fail(ProviderState.DENIED, "provider result missing path")
        if path != handoff.fixture_path:
            return _fail(ProviderState.DENIED,
                         f"result path != fixture literal: {path!r}")
        results.append(dict(item))

    artifacts_raw = data.get("artifacts", [])
    if not isinstance(artifacts_raw, list):
        return _fail(ProviderState.FAILURE, "artifacts must be a list")
    if len(artifacts_raw) > handoff.max_artifacts:
        return _fail(ProviderState.FAILURE, "artifact count over limit")
    artifacts: List[str] = []
    for ref in artifacts_raw:
        if not isinstance(ref, str) or not ref:
            return _fail(ProviderState.FAILURE, "artifact ref must be a string")
        artifacts.append(ref)   # REFERENCES ONLY — never ingested

    message = data.get("provider_message", "")
    if not isinstance(message, str):
        return _fail(ProviderState.FAILURE, "provider_message must be a string")
    result_hash = data.get("result_hash")
    if result_hash is not None and not isinstance(result_hash, str):
        return _fail(ProviderState.FAILURE, "result_hash must be a string")
    truncated = bool(data.get("truncated", False))

    return ProviderResult(
        state=ProviderState.PARTIAL if truncated else ProviderState.SUCCESS,
        run_id=handoff.run_id,
        action_request_id=handoff.action_request_id,
        invocation_id=handoff.invocation_id,
        proof_session_id=handoff.proof_session_id,
        capability_id=handoff.capability_id,
        provider_id=handoff.provider_id,
        results=tuple(results), artifacts=tuple(artifacts),
        result_hash=result_hash, truncated=truncated,
        provider_message=message[:2000],
        operation_id_untrusted=operation_id)


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------

class ProviderRuntime(Protocol):
    """Out-of-process provider boundary (adapter implements this)."""

    provider_id: str

    def invoke(self, handoff: ScopeHandoff,
               request: ActionRequest) -> ProviderResult:
        """Invoke the provider out-of-process; returns a ProviderResult."""
        ...


def invoke_governed(runtime: ProviderRuntime, handoff: ScopeHandoff,
                    request: ActionRequest) -> ProviderResult:
    """Validate scope, invoke with a wall-clock bound, normalize.

    Fail-closed: a timeout never becomes success; a provider exception
    becomes UNAVAILABLE/FAILURE. Cancellation is only acknowledged when
    the adapter reports externally observed teardown.
    """
    validate_scope(handoff, request)
    start = time.monotonic()
    try:
        result = runtime.invoke(handoff, request)
    except ScopeViolation:
        raise
    except Exception as exc:  # noqa: BLE001 - fail closed at the boundary
        return ProviderResult(
            state=ProviderState.UNAVAILABLE,
            run_id=handoff.run_id,
            action_request_id=handoff.action_request_id,
            invocation_id=handoff.invocation_id,
            proof_session_id=handoff.proof_session_id,
            capability_id=handoff.capability_id,
            provider_id=handoff.provider_id,
            error=f"{type(exc).__name__}:{exc}"[:512])
    elapsed = time.monotonic() - start
    if elapsed > handoff.timeout_seconds and result.state is ProviderState.SUCCESS:
        return ProviderResult(
            state=ProviderState.TIMEOUT, run_id=handoff.run_id,
            action_request_id=handoff.action_request_id,
            invocation_id=handoff.invocation_id,
            proof_session_id=handoff.proof_session_id,
            capability_id=handoff.capability_id,
            provider_id=handoff.provider_id,
            cancellation_acknowledged=False,
            error=f"wall-clock exceeded: {elapsed:.3f}s > "
                  f"{handoff.timeout_seconds}s")
    return result


def fixture_digest(path: str) -> Dict[str, Any]:
    """Pre/post fixture fingerprint (size + sha256). Read-only."""
    data = b""
    if os.path.isfile(path):
        with open(path, "rb") as handle:
            data = handle.read()
    return {"path": path, "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def fixture_integrity_ok(pre: Dict[str, Any],
                         post: Dict[str, Any]) -> bool:
    """A proof is invalid if the fixture changed during the proof."""
    return pre == post


def attest_result(handoff: ScopeHandoff, result: ProviderResult,
                  calls: Sequence[BoundaryToolCall],
                  results: Sequence[BoundaryToolResult],
                  executions: Sequence[ProviderExecution],
                  ) -> AttestationResult:
    """Wire the B4 harness for the first proof (expected_calls = 1)."""
    proof = ProofSession(
        proof_session_id=handoff.proof_session_id,
        instance_id=handoff.invocation_id,
        capability_id=handoff.capability_id,
        fixture_path=handoff.fixture_path,
        expected_tool=C1A_TOOL,
        expected_calls=1)
    return attest(proof, calls, results, executions)


__all__ = [
    "ALLOWED_PAYLOAD_KEYS",
    "C1A_CAPABILITY_ID",
    "C1A_PROVIDER_ID",
    "C1A_TOOL",
    "ProviderResult",
    "ProviderRuntime",
    "ProviderRuntimeError",
    "ProviderSchemaError",
    "ProviderState",
    "ProvenanceError",
    "ScopeHandoff",
    "ScopeViolation",
    "attest_result",
    "fixture_digest",
    "fixture_integrity_ok",
    "invoke_governed",
    "normalize_result",
    "parse_closed_payload",
    "validate_scope",
]
