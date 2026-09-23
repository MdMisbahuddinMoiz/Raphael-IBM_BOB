"""raphael_ibm_bob.capability_prerequisites — D13 prerequisite evaluation.

Answers: "given these TargetFacts, can this capability run?" Purely
declarative; no authority, no I/O. Unknown prerequisite kinds FAIL
CLOSED (return False), so a typo in a descriptor silently disables a
capability rather than enabling it.

Prerequisite kinds and predicate grammar:

    service        "protocol" or "protocol:port"
    authorization  "protocol"
    credential     "credential_type_or_token"
    platform       "linux" | "windows" | "any"
    observation    "observation_type"
    artifact       "artifact_type"
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from raphael_ibm_bob.capability_registry import CapabilityDescriptor, PrerequisiteSpec
from raphael_ibm_bob.target_service_model import TargetFacts


@dataclass
class PrerequisiteResult:
    """Outcome of evaluating a capability's prerequisites against a target."""
    capability_id: str
    satisfied: bool
    missing: list
    evaluated: dict


def _credential_token(item: Any) -> str:
    """Accept either a credential ref id (str) or a CredentialReference."""
    if isinstance(item, str):
        return item
    cred_type = getattr(item, "credential_type", "")
    cred_id = getattr(item, "credential_id", "")
    return f"{cred_type} {cred_id}".strip()


class PrerequisiteEngine:
    """Evaluates PrerequisiteSpec objects against TargetFacts."""

    def evaluate(self, descriptor: CapabilityDescriptor, facts: TargetFacts,
                 credential_refs: Optional[list] = None) -> PrerequisiteResult:
        credential_refs = credential_refs or []
        evaluated: dict = {}
        missing: list = []
        for prereq in descriptor.prerequisite_specs():
            ok = self._check_single(prereq, facts, credential_refs)
            evaluated[prereq.predicate] = ok
            if not ok:
                missing.append(
                    f"{prereq.kind}: {prereq.predicate} — {prereq.description}")
        return PrerequisiteResult(
            capability_id=descriptor.capability_id,
            satisfied=len(missing) == 0,
            missing=missing,
            evaluated=evaluated,
        )

    def _check_single(self, prereq: PrerequisiteSpec, facts: TargetFacts,
                      credential_refs: list) -> bool:
        kind = prereq.kind
        predicate = prereq.predicate

        if kind == "service":
            if ":" in predicate:
                protocol, _, port_str = predicate.partition(":")
                try:
                    port = int(port_str)
                except ValueError:
                    return False
                service = facts.get_service(protocol)
                return service is not None and service.port == port
            return facts.get_service(predicate) is not None

        if kind == "authorization":
            if facts.authorization is None:
                return False
            return predicate.lower() in {
                p.lower() for p in facts.authorization.authorized_protocols}

        if kind == "credential":
            tokens = [_credential_token(c) for c in credential_refs]
            return any(predicate in token for token in tokens)

        if kind == "platform":
            if predicate == "any":
                return True
            return facts.platform == predicate

        if kind == "observation":
            return any(o.get("type") == predicate for o in facts.observations)

        if kind == "artifact":
            return any(o.get("artifact_type") == predicate
                       for o in facts.observations)

        # Unknown prerequisite kind — fail closed.
        return False

    def batch_evaluate(self, descriptors: list, facts: TargetFacts,
                       credential_refs: Optional[list] = None) -> list:
        return [self.evaluate(d, facts, credential_refs) for d in descriptors]


__all__ = ["PrerequisiteEngine", "PrerequisiteResult"]
