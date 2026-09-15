"""raphael_ibm_bob.falsifier — M4 Falsifier with broker-mediated challenge
(M5: counter-example payload carries the challenge target so the
Replanner can derive the new action target).

The Falsifier's job is to actively search for a behavioral
counter-example to an apparently-successful Finding.

`challenge(finding)` produces:
    - a challenge ActionRequest (e.g. a SEARCH for known-bad patterns,
      or a READ of a file that should NOT contain a fix), submitted
      through the runtime.
    - if the challenge observes a real counter-example (e.g. the file
      still contains the buggy pattern, or a known behavioral test fails
      outside the named test set), the finding transitions to REFUTED.
    - if the challenge observes no counter-example, the finding remains
      VERIFIED.

The counter-example must come from actual evidence, not hard-coded.

Legacy reference (ADAPT):
    src/orchestrator/brain/contradiction.py:134 ContradictionManager
        - DETECTED -> UNDER_INVESTIGATION -> RESOLVED_TRUE/FALSE lifecycle.
    The lifecycle pattern is reusable; the semantic binding is to a
    counter-example observed through the broker, not to an offensive
    contradiction. NOT imported.

Limitations at M4/M5:
    - Challenge strategies are simple (SEARCH target for a forbidden
      pattern, or READ target expecting a substring and observing it).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from raphael_ibm_bob.broker import BOBBroker, BrokerResult
from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
    Finding,
    FindingState,
    Mission,
    PolicyDecision,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, digest_id
from raphael_ibm_bob.finding import FindingStore, InvalidTransitionError
from raphael_ibm_bob.runtime import BOBRuntime, RuntimeResult


@dataclass(frozen=True)
class ChallengeSpec:
    """Specification of a falsifier challenge.

    capability: which capability to invoke (SEARCH or READ).
    target:     the target argument passed to the capability.
    purpose:    free-text purpose line for provenance.
    forbidden_substring: substring that, if OBSERVED in the result payload,
                        constitutes a real counter-example.
                        If None, the falsifier relies on `predicate`.
    predicate:  optional callable (payload_dict) -> bool that returns True
                when the payload contains a real counter-example. Takes
                precedence over `forbidden_substring` if both provided.
    """
    capability: Capability
    target: str
    purpose: str = "falsifier-challenge"
    forbidden_substring: Optional[str] = None
    predicate: Optional[Callable[[Dict[str, Any]], bool]] = None


@dataclass(frozen=True)
class ChallengeOutcome:
    """Public outcome of a Falsifier.challenge() call."""
    finding: Finding
    challenge_runtime: RuntimeResult
    counter_example_observed: bool
    counter_example_detail: str
    transition_applied: bool
    transition_reason: str


class Falsifier:
    """Broker-mediated active-challenge engine for Findings."""

    def __init__(
        self,
        runtime: BOBRuntime,
        ledger: EvidenceLedger,
        store: FindingStore,
    ):
        self._runtime = runtime
        self._ledger = ledger
        self._store = store
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

    def challenge(
        self,
        finding: Finding,
        spec: ChallengeSpec,
        mission: Mission,
        requester: str = "falsifier",
    ) -> ChallengeOutcome:
        """Actively challenge an apparently-successful Finding."""
        if finding.state is not FindingState.VERIFIED:
            return ChallengeOutcome(
                finding=finding,
                challenge_runtime=RuntimeResult(
                    broker_result=self._deny_broker_result(finding, reason="not-verified"),
                    execution=None,
                    sequence=0,
                    request_seq=0,
                    decision_seq=0,
                    result_seq=None,
                    evidence_ids=(),
                ),
                counter_example_observed=False,
                counter_example_detail="",
                transition_applied=False,
                transition_reason=f"finding-not-verified:{finding.state.value}",
            )

        request = ActionRequest(
            sequence=0,
            requester=requester,
            capability=spec.capability,
            target=spec.target,
            purpose=spec.purpose,
            finding_id=finding.finding_id,
        )
        rt_result = self._runtime.submit(request, mission)

        challenge_ev_id = digest_id({
            "finding_id": finding.finding_id,
            "request_seq": rt_result.request_seq,
            "decision_seq": rt_result.decision_seq,
            "result_seq": rt_result.result_seq,
            "kind": "challenge",
        }, prefix="F")
        self._ledger.append_evidence(
            evidence_id=challenge_ev_id,
            producer="falsifier",
            request_seq=rt_result.request_seq,
            decision_seq=rt_result.decision_seq,
            result_seq=rt_result.result_seq,
            payload={
                "kind": "challenge",
                "finding_id": finding.finding_id,
                "capability": spec.capability.value,
                "target": spec.target,
                "allowed": rt_result.broker_result.decision.decision is Decision.ALLOW,
            },
            finding_id=finding.finding_id,
        )

        decision = rt_result.broker_result.decision
        if decision.decision is Decision.DENY:
            return ChallengeOutcome(
                finding=finding,
                challenge_runtime=rt_result,
                counter_example_observed=False,
                counter_example_detail="",
                transition_applied=False,
                transition_reason=f"challenge-denied:{decision.reason}",
            )

        execution = rt_result.execution
        if execution is None or not execution.success:
            return ChallengeOutcome(
                finding=finding,
                challenge_runtime=rt_result,
                counter_example_observed=False,
                counter_example_detail="",
                transition_applied=False,
                transition_reason="challenge-execution-failed",
            )

        payload = execution.evidence or {}
        observed, detail = self._detect_counter_example(payload, spec)

        if not observed:
            return ChallengeOutcome(
                finding=finding,
                challenge_runtime=rt_result,
                counter_example_observed=False,
                counter_example_detail=detail,
                transition_applied=False,
                transition_reason="no-counter-example",
            )

        counter_ev_id = digest_id({
            "finding_id": finding.finding_id,
            "request_seq": rt_result.request_seq,
            "decision_seq": rt_result.decision_seq,
            "result_seq": rt_result.result_seq,
            "kind": "counter-example",
            "detail": detail,
        }, prefix="C")
        self._ledger.append_evidence(
            evidence_id=counter_ev_id,
            producer="falsifier",
            request_seq=rt_result.request_seq,
            decision_seq=rt_result.decision_seq,
            result_seq=rt_result.result_seq,
            payload={
                "kind": "counter-example",
                "finding_id": finding.finding_id,
                "detail": detail,
                # M5: feed the Replanner's derive_target with the
                # challenge target so Plan B can target the actual
                # refuted defect rather than the prior wrong target.
                "target": spec.target,
                "capability": spec.capability.value,
            },
            finding_id=finding.finding_id,
        )

        evidence_seqs = (
            rt_result.request_seq,
            rt_result.decision_seq,
        ) + ((rt_result.result_seq,) if rt_result.result_seq else ())
        try:
            self._store.transition(
                finding.finding_id,
                FindingState.REFUTED,
                evidence_seqs=evidence_seqs,
                additional_evidence_ids=[challenge_ev_id, counter_ev_id],
            )
        except InvalidTransitionError as e:
            return ChallengeOutcome(
                finding=finding,
                challenge_runtime=rt_result,
                counter_example_observed=True,
                counter_example_detail=detail,
                transition_applied=False,
                transition_reason=f"transition-invalid:{e}",
            )

        updated = self._store.get(finding.finding_id) or finding
        return ChallengeOutcome(
            finding=updated,
            challenge_runtime=rt_result,
            counter_example_observed=True,
            counter_example_detail=detail,
            transition_applied=True,
            transition_reason="counter-example-observed",
        )

    @staticmethod
    def _detect_counter_example(
        payload: Dict[str, Any], spec: ChallengeSpec
    ) -> Tuple[bool, str]:
        if spec.predicate is not None:
            try:
                obs = bool(spec.predicate(payload))
            except Exception as e:
                return False, f"predicate-raised:{type(e).__name__}"
            if obs:
                return True, "predicate-matched"
            return False, "predicate-not-matched"
        if spec.forbidden_substring is not None:
            blob = " ".join(str(v) for v in payload.values())
            if spec.forbidden_substring in blob:
                return True, f"forbidden-substring-found:{spec.forbidden_substring[:40]}"
            return False, "forbidden-substring-absent"
        return False, "no-spec"

    @staticmethod
    def _deny_broker_result(finding: Finding, *, reason: str) -> BrokerResult:
        return BrokerResult(
            decision=PolicyDecision(
                sequence=0,
                decision=Decision.DENY,
                reason=reason,
                capability=Capability.READ,
                target=finding.target,
                evidence_id=None,
            ),
            execution=None,
            capability_invoked=False,
            request_seq=0,
            decision_seq=0,
            result_seq=None,
            evidence_ids=(),
        )


__all__ = ["Falsifier", "ChallengeSpec", "ChallengeOutcome"]