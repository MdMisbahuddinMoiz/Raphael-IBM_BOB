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
event stream is required.

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
    """A provider-recorded execution (``getExecutions()``) — SECONDARY."""
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
    expected_execution_count: int = 1


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


def _valid_fixture_literal(path: str) -> bool:
    return bool(path) and os.path.isabs(path) and canonical_path(path) == path


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

    # 2. exactly one expected capability / declared tool.
    col.check("single-capability",
              bool(proof.capability_id) and "\n" not in proof.capability_id,
              f"capability_id={proof.capability_id!r}")
    col.check("expected-tool-is-binary-sink-scan",
              proof.expected_tool == EXPECTED_TOOL,
              f"expected_tool={proof.expected_tool!r}")
    # Canonical absolute fixture path.
    col.check("fixture-path-canonical-absolute",
              _valid_fixture_literal(proof.fixture_path),
              f"fixture_path={proof.fixture_path!r}")

    # 1. exactly one proof session + 9/17 dedicated-instance binding.
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

    # 5. boundary tool_call observed.
    col.check("boundary-tool-call-observed", bool(calls),
              f"calls={len(calls)}")

    # 3/13. tool-name equality; unknown-name attempts invalidate.
    bad_tools = sorted({c.tool for c in calls if c.tool != proof.expected_tool})
    bad_exec_tools = sorted({
        e.tool for e in executions if e.tool != proof.expected_tool})
    col.check("tool-name-equality", not bad_tools and not bad_exec_tools,
              f"unknown_calls={bad_tools} unknown_executions={bad_exec_tools}")

    # 4/16. exact params.path == fixture literal (calls and executions).
    call_paths = {c.call_id: (c.params or {}).get("path") for c in calls}
    bad_call_paths = sorted(
        c.call_id for c in calls
        if (c.params or {}).get("path") != proof.fixture_path)
    bad_exec_paths = sorted(
        e.execution_id for e in executions
        if e.path is not None and e.path != proof.fixture_path)
    col.check("exact-path-literal", not bad_call_paths and not bad_exec_paths,
              f"bad_call_paths={bad_call_paths} "
              f"bad_exec_paths={bad_exec_paths}")

    # 11. result correlation: every call has a matching tool_result.
    result_by_call = {r.call_id: r for r in results}
    missing_results = sorted(
        c.call_id for c in calls if c.call_id not in result_by_call)
    col.check("tool-result-observed", bool(results) and not missing_results,
              f"missing_results={missing_results}")
    col.check("tool-results-ok",
              all(r.ok for r in results),
              "one or more tool_result events report failure")

    # 7/8/14/15. provider execution observed, count == expected.
    col.check("execution-observed", bool(executions),
              f"executions={len(executions)}")
    col.check("execution-count",
              len(executions) == proof.expected_execution_count,
              f"observed={len(executions)} "
              f"expected={proof.expected_execution_count}")

    # 10. event/execution correlation + divergence (boundary PRIMARY).
    call_ids = {c.call_id for c in calls}
    exec_call_ids = [e.call_id for e in executions]
    uncorrelated = sorted(
        e.execution_id for e in executions if e.call_id not in call_ids)
    col.check("event-execution-correlation",
              bool(executions) and not uncorrelated,
              f"uncorrelated_executions={uncorrelated}")

    # 11. duplicate/replay execution or call.
    dup_exec = len(exec_call_ids) != len(set(exec_call_ids))
    dup_exec_ids = len({e.execution_id for e in executions}) != len(executions)
    col.check("no-duplicate-execution",
              not dup_exec and not dup_exec_ids,
              "duplicate execution id or call_id (replay)")

    # 12. result hash correlation where the model supports it.
    hash_status = "not-available"
    hash_ok = True
    for e in executions:
        res = result_by_call.get(e.call_id) if e.call_id else None
        if res is None:
            continue
        if e.result_hash is not None and res.result_hash is not None:
            if e.result_hash != res.result_hash:
                hash_ok = False
                hash_status = f"mismatch:{e.execution_id}"
        elif e.result_hash is not None or res.result_hash is not None:
            hash_ok = False
            hash_status = f"one-sided:{e.execution_id}"
        elif hash_status == "not-available":
            hash_status = "not-available"
    col.check("result-hash-correlation", hash_ok, f"hash={hash_status}")

    status = (AttestationStatus.ATTESTED if not col.failures
              else AttestationStatus.INVALID)
    evidence = {
        "scope": ATTESTATION_SCOPE,
        "boundary_primary": [c.call_id for c in calls],
        "provider_secondary": [e.execution_id for e in executions],
        "fixture_path": proof.fixture_path,
        "expected_tool": proof.expected_tool,
        "expected_execution_count": proof.expected_execution_count,
        "observed_execution_count": len(executions),
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
    "FORBIDDEN_CLAIM",
    "ProofSession",
    "ProviderExecution",
    "attest",
    "canonical_path",
]
