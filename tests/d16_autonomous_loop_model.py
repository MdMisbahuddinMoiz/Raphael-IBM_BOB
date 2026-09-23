"""State-driven synthetic planning primitives for the D16 acceptance matrix."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Final

from raphael_ibm_bob.capability_bootstrap import InertAdapter, network_descriptors
from raphael_ibm_bob.capability_registry import CapabilityDescriptor, CapabilityRegistry
from raphael_ibm_bob.capability_selector import ExecutionPlan
from raphael_ibm_bob.target_service_model import TargetFacts


MISSION_ID: Final = "M-D16-wave1"
TARGET_HOST: Final = "synthetic.invalid"
CANDIDATE_TARGET: Final = "candidate.txt"
RECOVERY_TARGET: Final = "recovery.txt"
MISSION_TYPE: Final = "d16_acceptance"
SESSION_ID: Final = "session-d16-acceptance"


@unique
class ObservationRoute(StrEnum):
    """Facts exposed by the synthetic observation adapter."""

    STAGE_B = "stage_b"
    STATE_CHANGED = "state_changed"
    VERIFICATION_SUCCESS = "verification_success"
    VERIFICATION_FAILURE = "verification_failure"
    TERMINAL_REFUSAL = "terminal_refusal"


@unique
class VerificationStatus(StrEnum):
    """Factual result of a deterministic hypothesis check."""

    CONFIRMED = "confirmed"
    FALSIFIED = "falsified"


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """A bounded check over the payload returned by a governed action."""

    status: VerificationStatus
    expected_marker: str
    observed_payload: str


@dataclass(frozen=True, slots=True)
class ObservationSpec:
    """Immutable input for one synthetic observation receipt."""

    observation_id: str
    route: ObservationRoute | None = None
    observation_session: str = SESSION_ID
    source_seq: int | None = None


class StateDrivenSelector:
    """Build plans solely from normalized service facts.

    ``plan_calls`` is an intentional diagnostic counter: terminal-success tests
    use it to prove the coordinator did not ask the planner for an unnecessary
    replacement action. It is mutable because it measures calls, not state.
    """

    def __init__(self, candidate_target: str) -> None:
        self._candidate_target = candidate_target
        self.plan_calls = 0

    def select_and_compose(
        self,
        mission_type: str,
        mission_params: dict[str, str],
        facts: TargetFacts,
        *,
        credential_refs: list[str] | None = None,
    ) -> ExecutionPlan:
        """Compose the next proposal from facts, never from a scenario name."""
        del credential_refs
        self.plan_calls += 1
        protocols = frozenset(
            service.protocol.casefold()
            for service in facts.services
            if service.state == "open"
        )
        identity = json.dumps(
            {
                "mission_id": mission_params.get("mission_id", ""),
                "target_id": facts.target_id,
                "protocols": sorted(protocols),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        plan = ExecutionPlan(
            plan_id=f"DP-D16-{hashlib.sha256(identity.encode()).hexdigest()[:12]}",
            mission_id=mission_params.get("mission_id", ""),
            target_id=facts.target_id,
            mission_type=mission_type,
        )
        if "stage_a" in protocols:
            plan.add_step(
                "READ",
                {"target": self._candidate_target},
                purpose="d16:read-candidate",
            )
        if "stage_b" in protocols:
            plan.add_step(
                "LIST",
                {"target": "."},
                purpose="d16:list-workspace",
            )
        if "state_changed" in protocols or "verification_success" in protocols:
            plan.add_step(
                "SEARCH",
                {"target": "."},
                purpose="d16-search-marker",
            )
        if "verification_failure" in protocols:
            plan.add_step(
                "WRITE",
                {"target": RECOVERY_TARGET},
                purpose="content=d16-recovery",
            )
        if "terminal_refusal" in protocols:
            plan.add_step(
                "NETWORK_TELNET_SESSION",
                {"target": f"telnet://{TARGET_HOST}:23"},
                purpose="d16-terminal-refusal",
            )
        return plan


def _descriptor(capability_id: str, protocol: str) -> CapabilityDescriptor:
    """Declare a synthetic fact-to-capability mapping for the selector."""
    return CapabilityDescriptor(
        capability_id=capability_id,
        protocol=protocol,
        description=f"D16 synthetic {capability_id}",
        prerequisites=frozenset(),
        authorization_scope="synthetic",
        evidence_schema="d16_v1",
        execution_adapter="raphael_ibm_bob.capabilities",
        verifier_binding=None,
        falsifier_binding=None,
        mission_types=frozenset({MISSION_TYPE}),
    )


def registry() -> CapabilityRegistry:
    """Return a fresh registry with only existing governed capabilities."""
    result = CapabilityRegistry()
    for capability_id, protocol in (
        ("READ", "stage_a"),
        ("LIST", "stage_b"),
        ("SEARCH", "state_changed"),
        ("WRITE", "verification_failure"),
    ):
        result.register(_descriptor(capability_id, protocol), InertAdapter())
    for descriptor in network_descriptors():
        result.register(descriptor, InertAdapter())
    return result


__all__ = [
    "CANDIDATE_TARGET",
    "MISSION_ID",
    "MISSION_TYPE",
    "ObservationRoute",
    "RECOVERY_TARGET",
    "SESSION_ID",
    "TARGET_HOST",
    "ObservationSpec",
    "StateDrivenSelector",
    "VerificationResult",
    "VerificationStatus",
    "registry",
]
