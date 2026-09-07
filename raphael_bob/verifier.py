"""raphael_bob.verifier — M4 Verifier with broker-mediated retest.

The Verifier's job is to independently retest a candidate Finding
through the controlled execution boundary (Runtime -> Broker -> Policy).

`verify(finding)` produces:
    - a retest ActionRequest (e.g. READ the target file again, or RUN_TEST
      a specific test), submitted through the runtime.
    - on Policy ALLOW + observed evidence matching the retest expectation:
      transition the finding UNVERIFIED -> VERIFIED.
    - on Policy DENY, leave the finding UNVERIFIED; persist a denial
      evidence record (via the ledger) so the failure is durable.

The Verifier MUST itself go through the Broker. There is no direct
filesystem/process path.

Legacy reference (ADAPT):
    src/raphael/verifier/core.py:33 VerificationLoop has a preflight/observe/
    adapt lifecycle for *exploit canary* verification (TCP/HTTP/DNS
    callbacks). Lifecycle shape is reusable; semantics are wrong for the
    BOB MVP (which needs behavioral retest of source-code fixes, not
    exploit canary callbacks). NOT imported.

Limitations at M4:
    - Retest strategies are intentionally simple (READ target file, or
      RUN_TEST target file).
    - No streaming / partial retest.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Optional

from raphael_bob.broker import BOBBroker, BrokerResult
from raphael_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
    Finding,
    FindingState,
    Mission,
)
from raphael_bob.evidence_ledger import EvidenceLedger, digest_id
from raphael_bob.finding import FindingStore, InvalidTransitionError
from raphael_bob.runtime import BOBRuntime, RuntimeResult


@dataclass(frozen=True)
class RetestSpec:
    """Specification of a retest action.

    capability: which capability to invoke during retest.
    target:     the target argument passed to the capability.
    purpose:    free-text purpose line for provenance.
    expected_substring: optional substring that the result payload
                       must contain for the retest to count as success.
                       If None, any successful ALLOW is sufficient.
    """
    capability: Capability
    target: str
    purpose: str = "verifier-retest"
    expected_substring: Optional[str] = None


@dataclass(frozen=True)
class VerifyOutcome:
    """Public outcome of a Verifier.verify() call."""
    finding: Finding
    retest_runtime: RuntimeResult
    transition_applied: bool
    transition_reason: str


class Verifier:
    """Broker-mediated retest engine for candidate Findings."""

    def __init__(
        self,
        runtime: BOBRuntime,
        ledger: EvidenceLedger,
        store: FindingStore,
    ):
        self._runtime = runtime
        self._ledger = ledger
        self._store = store
        # Cache broker for tests that need direct denial probes.
        self._broker: BOBBroker = runtime.broker

    @property
    def broker(self) -> BOBBroker:
        return self._broker

    @property
    def ledger(self) -> EvidenceLedger:
        return self._ledger

    @property
    def store(self) -> FindingStore:
        return self._store

    def verify(
        self,
        finding: Finding,
        retest: RetestSpec,
        mission: Mission,
        requester: str = "verifier",
    ) -> VerifyOutcome:
        """Retest the candidate finding through the Broker.

        On ALLOW + matching observation: transition UNVERIFIED -> VERIFIED.
        On DENY or observation mismatch: leave UNVERIFIED.
        """
        if finding.state is not FindingState.UNVERIFIED:
            return VerifyOutcome(
                finding=finding,
                retest_runtime=RuntimeResult(
                    broker_result=BrokerResult(
                        decision=finding_state_to_decision(finding),
                        execution=None,
                        capability_invoked=False,
                        request_seq=0,
                        decision_seq=0,
                        result_seq=None,
                        evidence_ids=(),
                    ),
                    execution=None,
                    sequence=0,
                    request_seq=0,
                    decision_seq=0,
                    result_seq=None,
                    evidence_ids=(),
                ),
                transition_applied=False,
                transition_reason=f"finding-not-unverified:{finding.state.value}",
            )

        # Build a finding-tagged request and submit through the broker.
        request = ActionRequest(
            sequence=0,
            requester=requester,
            capability=retest.capability,
            target=retest.target,
            purpose=retest.purpose,
            finding_id=finding.finding_id,
        )
        runtime_result = self._runtime.submit(request, mission)

        # Persist a retest evidence record with finding_id linkage. We use
        # the ledger directly because the broker-mediated chain does not
        # carry finding_id into its policy / execution receipts.
        retest_ev_id = digest_id({
            "finding_id": finding.finding_id,
            "request_seq": runtime_result.request_seq,
            "decision_seq": runtime_result.decision_seq,
            "result_seq": runtime_result.result_seq,
            "kind": "retest",
        }, prefix="V")
        self._ledger.append_evidence(
            evidence_id=retest_ev_id,
            producer="verifier",
            request_seq=runtime_result.request_seq,
            decision_seq=runtime_result.decision_seq,
            result_seq=runtime_result.result_seq,
            payload={
                "kind": "retest",
                "finding_id": finding.finding_id,
                "capability": retest.capability.value,
                "target": retest.target,
                "allowed": runtime_result.broker_result.decision.decision is Decision.ALLOW,
            },
            finding_id=finding.finding_id,
        )

        decision = runtime_result.broker_result.decision
        if decision.decision is Decision.DENY:
            return VerifyOutcome(
                finding=finding,
                retest_runtime=runtime_result,
                transition_applied=False,
                transition_reason=f"retest-denied:{decision.reason}",
            )

        # ALLOW: check observation.
        execution = runtime_result.execution
        ok = execution is not None and execution.success
        if retest.expected_substring is not None and ok:
            payload = execution.evidence or {}
            observed = " ".join(str(v) for v in payload.values())
            ok = retest.expected_substring in observed

        if not ok:
            return VerifyOutcome(
                finding=finding,
                retest_runtime=runtime_result,
                transition_applied=False,
                transition_reason="retest-output-mismatch",
            )

        # Persist an observation evidence receipt.
        obs_ev_id = digest_id({
            "finding_id": finding.finding_id,
            "request_seq": runtime_result.request_seq,
            "decision_seq": runtime_result.decision_seq,
            "result_seq": runtime_result.result_seq,
            "kind": "observation",
        }, prefix="O")
        self._ledger.append_evidence(
            evidence_id=obs_ev_id,
            producer="verifier",
            request_seq=runtime_result.request_seq,
            decision_seq=runtime_result.decision_seq,
            result_seq=runtime_result.result_seq,
            payload={
                "kind": "observation",
                "finding_id": finding.finding_id,
                "success": bool(execution and execution.success),
                "evidence_keys": sorted((execution.evidence or {}).keys()) if execution else [],
            },
            finding_id=finding.finding_id,
        )

        # Transition UNVERIFIED -> VERIFIED.
        evidence_seqs = (
            runtime_result.request_seq,
            runtime_result.decision_seq,
        ) + ((runtime_result.result_seq,) if runtime_result.result_seq else ())
        try:
            self._store.transition(
                finding.finding_id,
                FindingState.VERIFIED,
                evidence_seqs=evidence_seqs,
                additional_evidence_ids=[retest_ev_id, obs_ev_id],
            )
        except InvalidTransitionError as e:
            return VerifyOutcome(
                finding=finding,
                retest_runtime=runtime_result,
                transition_applied=False,
                transition_reason=f"transition-invalid:{e}",
            )

        # Re-fetch the updated Finding.
        updated = self._store.get(finding.finding_id) or finding
        return VerifyOutcome(
            finding=updated,
            retest_runtime=runtime_result,
            transition_applied=True,
            transition_reason="retest-ok",
        )


def finding_state_to_decision(finding: Finding):
    """Helper: produce a synthetic PolicyDecision for non-retest paths
    (used only when the Verifier is asked about an already-transitioned
    Finding). Not a real decision; used to keep VerifyOutcome ergonomic."""
    from raphael_bob.contracts import PolicyDecision
    return PolicyDecision(
        sequence=0,
        decision=Decision.DENY,
        reason=f"non-retest:{finding.state.value}",
        capability=Capability.READ,
        target=finding.target,
        evidence_id=None,
    )


__all__ = ["Verifier", "RetestSpec", "VerifyOutcome"]