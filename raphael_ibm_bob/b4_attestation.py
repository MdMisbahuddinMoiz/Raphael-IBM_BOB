"""raphael_ibm_bob.b4_attestation — B4 Option-B post-hoc attestation.

RAPHAEL-side validator for the C1A first-proof **execution contract**.
It consumes two observable sources and attests the invariant:

    "Every RAPHAEL-observed tool_call and every provider-recorded
     execution was binary_sink_scan, and params.path exactly equals the
     fixture literal."

Sources (per the accepted no-fork design, C5):

    PRIMARY   RAPHAEL-observed boundary events
              ``agent:tool_call`` / ``agent:tool_result``
    SECONDARY provider-recorded executions (``getExecutions()``)

A ``ToolExecution`` record lacks sufficient argument/session identity on
its own, so provider executions alone are never sufficient: the boundary
event stream is required. Correlation between a boundary call and a
provider execution uses the RAPHAEL-side ``call_id`` (observed on the
boundary event and carried onto the provider-execution record by the
RAPHAEL-side collector); no provider field is fabricated.

First-proof semantics (B4 corrective closure): exactly **one** boundary
call, **one** boundary result, and **one** provider execution, mutually
correlated 1:1. Cardinality is enforced per stream, not only by a total.

Semantic boundary (deliberate):

    validate, never authorize
    attest, never verify a finding
    quarantine a proof, never complete a mission

This module MUST NOT produce authorization, a VERIFIED/REFUTED finding,
COMPLETE, or any Quality Gate decision, and it MUST NOT execute a
provider. It returns structured attestation evidence only; persistence
and any consequence remain the caller's governed concern.

Accepted property (recorded, explicit): attestation is **post-hoc**. It
DETECTS an out-of-contract execution; it does NOT PREVENT one. The
result therefore never claims prevention and never uses the forbidden
claim below.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: Verbatim attestation scope (C5).
ATTESTATION_SCOPE = (
    "Every RAPHAEL-observed tool_call and every provider-recorded "
    "execution was binary_sink_scan, and params.path exactly equals the "
    "fixture literal.")

#: The stronger claim that exceeds the evidence model (C5, forbidden).
FORBIDDEN_CLAIM = "No subprocess ran in the provider process."

#: The one capability tool permitted for the first proof.
EXPECTED_TOOL = "binary_sink_scan"

#: First-proof cardinality (one call, one result, one execution).
FIRST_PROOF_CALLS = 1


class AttestationStatus(str, Enum):
    """Outcome of an attestation run (never a mission verdict)."""
    ATTESTED = "attested"
    INVALID = "invalid"


@dataclass(frozen=True)
class BoundaryToolCall:
    """A RAPHAEL-observed ``agent:tool_call`` boundary event."""
    seq: int
    session_id: str
    instance_id: str
    call_id: str
    tool: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BoundaryToolResult:
    """A RAPHAEL-observed ``agent:tool_result`` boundary event."""
    seq: int
    session_id: str
    instance_id: str
    call_id: str
    tool: str
    ok: bool = True
    result_hash: Optional[str] = None


@dataclass(frozen=True)
class ProviderExecution:
    """A provider-recorded execution (``getExecutions()``) — SECONDARY.

    ``call_id`` is the RAPHAEL-side correlation key, carried onto the
    record by the RAPHAEL-side collector; it is not invented from
    provider data.
    """
    execution_id: str
    session_id: str
    instance_id: str
    tool: str
    call_id: Optional[str] = None
    path: Optional[str] = None
    result_hash: Optional[str] = None


@dataclass(frozen=True)
class ProofSession:
    """Binds one proof session to one dedicated provider instance.

    The dedicated, single-session instance is a hard requirement: a
    shared Arsenal/execution history cannot support attribution.
    """
    proof_session_id: str
    instance_id: str
    capability_id: str
    fixture_path: str
    expected_tool: str = EXPECTED_TOOL
    expected_calls: int = FIRST_PROOF_CALLS


@dataclass(frozen=True)
class AttestationCheck:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class AttestationResult:
    status: AttestationStatus
    proof_session_id: str
    checks: List[AttestationCheck]
    failures: List[str]
    reasons: List[str]
    quarantined: bool
    post_hoc: bool = True
    prevented: bool = False
    evidence: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status is AttestationStatus.ATTESTED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "proof_session_id": self.proof_session_id,
            "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail}
                       for c in self.checks],
            "failures": list(self.failures),
            "reasons": list(self.reasons),
            "quarantined": self.quarantined,
            "post_hoc": self.post_hoc,
            "prevented": self.prevented,
            "evidence": dict(self.evidence),
        }


def canonical_path(path: str) -> str:
    """Canonical absolute path (normalised; no filesystem access)."""
    return os.path.normpath(os.path.abspath(path))


def _valid_id(value: Any) -> bool:
    """A present, non-empty, non-whitespace identifier (H4)."""
    return isinstance(value, str) and value.strip() != ""


def _valid_fixture_literal(path: Any) -> bool:
    return (_valid_id(path) and os.path.isabs(path)
            and canonical_path(path) == path)


def _exact_path(value: Any, literal: str) -> bool:
    """Exact literal match: present, a non-empty string, no normalisation."""
    return isinstance(value, str) and value != "" and value == literal


class _Collector:
    def __init__(self) -> None:
        self.checks: List[AttestationCheck] = []
        self.failures: List[str] = []
        self.reasons: List[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append(AttestationCheck(name, ok, detail))
        if not ok:
            self.failures.append(name)
            if detail:
                self.reasons.append(f"{name}: {detail}")
        return ok


def attest(proof: ProofSession,
           calls: Sequence[BoundaryToolCall],
           results: Sequence[BoundaryToolResult],
           executions: Sequence[ProviderExecution],
           ) -> AttestationResult:
    """Validate the C1A execution contract; return an attestation.

    Fails closed: any mismatch invalidates the proof and quarantines the
    candidate result. Never downgrades to a warning.
    """
    col = _Collector()
    calls = list(calls)
    results = list(results)
    executions = list(executions)
    expected = proof.expected_calls

    # H4 — non-empty proof/instance identifiers.
    col.check("proof-session-id-nonempty", _valid_id(proof.proof_session_id),
              f"proof_session_id={proof.proof_session_id!r}")
    col.check("instance-id-nonempty", _valid_id(proof.instance_id),
              f"instance_id={proof.instance_id!r}")

    # H5 — the proof DECLARES one expected capability and enforces it.
    col.check("capability-declared", _valid_id(proof.capability_id),
              f"capability_id={proof.capability_id!r}")
    col.check("expected-tool-is-binary-sink-scan",
              proof.expected_tool == EXPECTED_TOOL,
              f"expected_tool={proof.expected_tool!r}")
    # Canonical absolute fixture path (setup side).
    col.check("fixture-path-canonical-absolute",
              _valid_fixture_literal(proof.fixture_path),
              f"fixture_path={proof.fixture_path!r}")

    # Dedicated single-session / single-instance binding.
    all_records = (*calls, *results, *executions)
    foreign_sessions = sorted({
        r.session_id for r in all_records
        if r.session_id != proof.proof_session_id})
    col.check("single-proof-session", not foreign_sessions,
              f"foreign_sessions={foreign_sessions}")
    foreign_instances = sorted({
        r.instance_id for r in all_records
        if r.instance_id != proof.instance_id})
    col.check("dedicated-instance", not foreign_instances,
              f"foreign_instances={foreign_instances}")

    # H1/H2 — per-stream cardinality (exactly one call/result/execution).
    col.check("boundary-tool-call-observed", bool(calls),
              f"calls={len(calls)}")
    col.check("call-count", len(calls) == expected,
              f"observed={len(calls)} expected={expected}")
    col.check("result-count", len(results) == expected,
              f"observed={len(results)} expected={expected}")
    col.check("execution-observed", bool(executions),
              f"executions={len(executions)}")
    col.check("execution-count", len(executions) == expected,
              f"observed={len(executions)} expected={expected}")

    # Tool-name equality; unknown-name attempts invalidate.
    bad_tools = sorted({c.tool for c in calls if c.tool != proof.expected_tool})
    bad_exec_tools = sorted({
        e.tool for e in executions if e.tool != proof.expected_tool})
    col.check("tool-name-equality", not bad_tools and not bad_exec_tools,
              f"unknown_calls={bad_tools} unknown_executions={bad_exec_tools}")

    # H3 — exact params.path == fixture literal; missing/None/empty/non-str
    # and any alternate normalisation MUST fail (both streams).
    bad_call_paths = sorted(
        c.call_id for c in calls
        if not _exact_path((c.params or {}).get("path"), proof.fixture_path))
    bad_exec_paths = sorted(
        e.execution_id for e in executions
        if not _exact_path(e.path, proof.fixture_path))
    col.check("exact-path-literal", not bad_call_paths and not bad_exec_paths,
              f"bad_call_paths={bad_call_paths} "
              f"bad_exec_paths={bad_exec_paths}")

    # H2 — 1:1 call <-> result cardinality and correlation.
    result_by_call = {r.call_id: r for r in results}
    call_ids = [c.call_id for c in calls]
    result_call_ids = [r.call_id for r in results]
    missing_results = sorted(cid for cid in call_ids
                             if cid not in result_by_call)
    col.check("tool-result-observed", bool(results) and not missing_results
              and len(result_call_ids) == len(set(result_call_ids)),
              f"missing_results={missing_results} "
              f"duplicate_results={len(result_call_ids) - len(set(result_call_ids))}")
    col.check("tool-results-ok", all(r.ok for r in results),
              "one or more tool_result events report failure")
    col.check("call-result-correlation",
              len(set(call_ids)) == len(call_ids)
              and set(result_call_ids) == set(call_ids),
              f"calls={call_ids} results={result_call_ids}")

    # H1 — one call correlates to exactly one provider execution.
    exec_call_ids = [e.call_id for e in executions]
    col.check("call-execution-correlation",
              bool(executions)
              and len(exec_call_ids) == len(call_ids)
              and set(exec_call_ids) == set(call_ids)
              and all(cid in call_ids for cid in exec_call_ids),
              f"calls={call_ids} executions={exec_call_ids}")
    uncorrelated = sorted(
        e.execution_id for e in executions if e.call_id not in call_ids)
    col.check("event-execution-correlation",
              bool(executions) and not uncorrelated,
              f"uncorrelated_executions={uncorrelated}")

    # No duplicate call / execution identity (replay).
    dup_exec_calls = len(exec_call_ids) != len(set(exec_call_ids))
    dup_exec_ids = len({e.execution_id for e in executions}) != len(executions)
    dup_call_ids = len(call_ids) != len(set(call_ids))
    col.check("no-duplicate-execution",
              not dup_exec_calls and not dup_exec_ids and not dup_call_ids,
              "duplicate call_id or execution id (replay)")

    # Result-hash correlation; one-sided hashes are not verifiable.
    hash_ok = True
    hash_status = "not-available"
    for e in executions:
        res = result_by_call.get(e.call_id) if e.call_id else None
        if res is None:
            continue
        if e.result_hash is not None and res.result_hash is not None:
            if e.result_hash != res.result_hash:
                hash_ok = False
                hash_status = f"mismatch:{e.execution_id}"
        elif (e.result_hash is not None) != (res.result_hash is not None):
            hash_ok = False
            hash_status = f"one-sided:{e.execution_id}"
        elif hash_status == "not-available":
            hash_status = "both-absent"
    col.check("result-hash-correlation", hash_ok, f"hash={hash_status}")

    status = (AttestationStatus.ATTESTED if not col.failures
              else AttestationStatus.INVALID)
    evidence = {
        "scope": ATTESTATION_SCOPE,
        "boundary_primary": list(call_ids),
        "provider_secondary": [e.execution_id for e in executions],
        "fixture_path": proof.fixture_path,
        "expected_tool": proof.expected_tool,
        "expected_calls": expected,
        "observed_calls": len(calls),
        "observed_results": len(results),
        "observed_executions": len(executions),
        "post_hoc": True,
        "prevented": False,
        "honesty": ("post-hoc attestation DETECTS an out-of-contract "
                    "execution; it does NOT PREVENT one."),
        "forbidden_claim_not_made": FORBIDDEN_CLAIM,
    }
    return AttestationResult(
        status=status,
        proof_session_id=proof.proof_session_id,
        checks=col.checks,
        failures=col.failures,
        reasons=col.reasons,
        quarantined=status is AttestationStatus.INVALID,
        evidence=evidence)


__all__ = [
    "ATTESTATION_SCOPE",
    "AttestationCheck",
    "AttestationResult",
    "AttestationStatus",
    "BoundaryToolCall",
    "BoundaryToolResult",
    "EXPECTED_TOOL",
    "FIRST_PROOF_CALLS",
    "FORBIDDEN_CLAIM",
    "ProofSession",
    "ProviderExecution",
    "attest",
    "canonical_path",
]
