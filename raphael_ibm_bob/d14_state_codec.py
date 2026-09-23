from __future__ import annotations

# noqa: SIZE_OK — canonical state serialization remains one deterministic codec boundary.

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from raphael_ibm_bob._d15_observation_types import (
    AuthoritativeSessionBinding,
    GovernedRuntimeSession,
)
from raphael_ibm_bob.contracts import (
    Decision,
    ExecutionResult,
    PolicyDecision,
    capability_id,
)
from raphael_ibm_bob.observation_model import ObservationRecord
from raphael_ibm_bob.target_service_model import ServiceRecord, TargetFacts

if TYPE_CHECKING:
    from raphael_ibm_bob.d14_world_state import Hypothesis


JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class EvidenceBinding:
    """Read-only authorization and result facts for one evidence receipt."""

    evidence_id: str
    request_seq: int
    policy_decision: str
    result_success: bool
    session_id: str | None
    decision_seq: int | None = None
    result_seq: int | None = None


class _GovernedBrokerResult(Protocol):
    decision: PolicyDecision


class GovernedRuntimeResult(Protocol):
    """Runtime result shape accepted by the D16 execution binder."""

    broker_result: _GovernedBrokerResult
    execution: ExecutionResult | None
    request_seq: int
    decision_seq: int
    result_seq: int | None
    evidence_ids: tuple[str, ...]


class ExecutionBindingError(ValueError):
    """Raised when a normalized observation cannot bind to execution."""


@dataclass(frozen=True, slots=True)
class ExecutionBinding:
    """Immutable link from a normalized observation to one ALLOWed result."""

    observation_evidence_id: str
    execution_evidence_id: str
    request_seq: int
    decision_seq: int
    result_seq: int
    capability_id: str
    session_binding: AuthoritativeSessionBinding

    @classmethod
    def from_runtime_result(
        cls,
        runtime_result: GovernedRuntimeResult,
        runtime_session: GovernedRuntimeSession,
        observation_evidence_id: str,
    ) -> "ExecutionBinding":
        """Bind one observation receipt to a successful governed execution."""
        if not isinstance(observation_evidence_id, str) or not observation_evidence_id.strip():
            raise ExecutionBindingError("observation evidence_id is required")
        if runtime_result.broker_result.decision.decision is not Decision.ALLOW:
            raise ExecutionBindingError("execution binding requires Policy ALLOW")
        execution = runtime_result.execution
        if execution is None or not execution.success:
            raise ExecutionBindingError("execution binding requires a successful result")
        if (
            not isinstance(runtime_result.result_seq, int)
            or isinstance(runtime_result.result_seq, bool)
            or runtime_result.result_seq <= 0
        ):
            raise ExecutionBindingError("execution binding requires a result sequence")
        if (
            not isinstance(runtime_result.request_seq, int)
            or isinstance(runtime_result.request_seq, bool)
            or not isinstance(runtime_result.decision_seq, int)
            or isinstance(runtime_result.decision_seq, bool)
            or runtime_result.request_seq <= 0
            or runtime_result.decision_seq <= 0
        ):
            raise ExecutionBindingError("execution binding requires request and decision sequences")
        if not runtime_result.evidence_ids:
            raise ExecutionBindingError("execution binding requires execution evidence")
        execution_evidence_id = runtime_result.evidence_ids[-1]
        if (
            not isinstance(execution_evidence_id, str)
            or not execution_evidence_id.strip()
        ):
            raise ExecutionBindingError("execution evidence_id is required")
        session_binding = AuthoritativeSessionBinding.from_governed_runtime(
            runtime_session,
        )
        if not session_binding.session_id.strip():
            raise ExecutionBindingError("runtime session binding is empty")
        return cls(
            observation_evidence_id=observation_evidence_id,
            execution_evidence_id=execution_evidence_id,
            request_seq=runtime_result.request_seq,
            decision_seq=runtime_result.decision_seq,
            result_seq=runtime_result.result_seq,
            capability_id=capability_id(
                runtime_result.broker_result.decision.capability,
            ),
            session_binding=session_binding,
        )

    @property
    def evidence_id(self) -> str:
        """Return the evidence receipt used by D16 ingestion."""
        return self.observation_evidence_id

    def to_provenance(self) -> dict[str, JsonValue]:
        """Return the canonical, non-secret association payload."""
        return {
            "observation_evidence_id": self.observation_evidence_id,
            "execution_evidence_id": self.execution_evidence_id,
            "request_seq": self.request_seq,
            "decision_seq": self.decision_seq,
            "result_seq": self.result_seq,
            "capability_id": self.capability_id,
            "session_id": self.session_binding.session_id,
        }


class ReadOnlyLedgerView(Protocol):
    """Minimum read-only ledger capability required by D14 ingestion."""

    def resolve_evidence(self, evidence_id: str) -> EvidenceBinding | None:
        """Resolve an evidence id to its immutable execution binding."""


class _ValueEnum(Protocol):
    value: str


_OBSERVATION_PROTOCOLS = {
    "http_get": "http",
    "http_response": "http",
    "network_response": "http",
    "ssh_service": "ssh",
    "smb_service": "smb",
    "tls_metadata": "tls",
    "dns_metadata": "dns",
}


def _protocol_from_observation(observation: ObservationRecord) -> str | None:
    observation_type = observation.observation_type.strip().casefold()
    protocol = _OBSERVATION_PROTOCOLS.get(observation_type)
    if protocol is not None:
        return protocol
    if observation_type != "service_banner":
        return None

    normalized = observation.provenance.get("normalized")
    sources = (normalized, observation.provenance)
    for source in sources:
        if not isinstance(source, dict):
            continue
        for field in ("protocol", "family"):
            value = source.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip().casefold()
    return None


def next_band(current_band: _ValueEnum, kind: str) -> str:
    current = current_band.value
    if kind in {"reachable", "http_response"}:
        if current in {"unknown", "candidate"}:
            return "candidate" if kind == "reachable" else "confirmed"
        if current == "confirmed":
            return "confirmed"
        return "conflicted"
    if kind == "failure":
        if current in {"unknown", "refuted"}:
            return "refuted"
        return "conflicted"
    return current


def endpoint_key(host: str, port: int | None) -> str:
    return host if port is None else f"{host}:{port}"


def service_from_observation(
    observation: ObservationRecord,
) -> ServiceRecord | None:
    port = observation.target_port
    if port is None:
        return None
    provenance = observation.provenance
    protocol = _protocol_from_observation(observation)
    if protocol is None:
        return None
    version = provenance.get("version")
    banner = provenance.get("banner")
    return ServiceRecord(
        host=observation.target_host,
        port=port,
        protocol=protocol,
        version=version if isinstance(version, str) else None,
        state="open",
        banner=banner if isinstance(banner, str) else None,
        discovered_at=0.0,
        source="prior_observation",
    )


def canonical_state_payload(
    *,
    mission_id: str,
    target_id: str,
    revision: int,
    facts: TargetFacts,
    endpoints: dict[str, _ValueEnum],
    hypotheses: dict[str, Hypothesis],
    observations: tuple[ObservationRecord, ...],
    applied_observation_ids: frozenset[str],
    last_source_seq: int,
    step_count: int,
    replan_count: int,
    failure_count: int,
) -> dict[str, JsonValue]:
    return {
        "mission_id": mission_id,
        "target_id": target_id,
        "revision": revision,
        "facts": facts_payload(facts),
        "endpoints": {key: endpoints[key].value for key in sorted(endpoints)},
        "hypotheses": {
            key: hypothesis_payload(hypotheses[key])
            for key in sorted(hypotheses)
        },
        "observations": [
            observation_payload(observation) for observation in observations
        ],
        "applied_observation_ids": sorted(applied_observation_ids),
        "last_source_seq": last_source_seq,
        "step_count": step_count,
        "replan_count": replan_count,
        "failure_count": failure_count,
    }


def facts_payload(facts: TargetFacts) -> dict[str, JsonValue]:
    authorization = facts.authorization
    return {
        "target_id": facts.target_id,
        "host": facts.host,
        "services": [
            {
                "host": service.host,
                "port": service.port,
                "protocol": service.protocol,
                "version": service.version,
                "state": service.state,
                "banner": service.banner,
                "source": service.source,
            }
            for service in sorted(facts.services, key=lambda item: item.key())
        ],
        "authorization": None if authorization is None else {
            "target_host": authorization.target_host,
            "authorized_protocols": sorted(authorization.authorized_protocols),
            "authorized_ports": sorted(authorization.authorized_ports),
            "engagement_id": authorization.engagement_id,
            "scope_document_ref": authorization.scope_document_ref,
        },
        "platform": facts.platform,
        "credential_refs": sorted(facts.credential_refs),
        "mission_id": facts.mission_id,
    }


def hypothesis_payload(hypothesis: Hypothesis) -> dict[str, JsonValue]:
    return {
        "hypothesis_id": hypothesis.hypothesis_id,
        "statement": hypothesis.statement,
        "status": hypothesis.status,
        "observation_ids": list(hypothesis.observation_ids),
    }


def observation_payload(observation: ObservationRecord) -> dict[str, JsonValue]:
    return {
        "observation_id": observation.observation_id,
        "capability_id": observation.capability_id,
        "observation_type": observation.observation_type,
        "target_host": observation.target_host,
        "target_port": observation.target_port,
        "content_hash": observation.content_hash,
        "raw_output_ref": observation.raw_output_ref,
        "provenance": canonical_value(observation.provenance),
    }


def canonical_value(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {
            str(key): canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key).lower() not in {"timestamp", "discovered_at"}
        }
    if isinstance(value, (list, tuple)):
        return [canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(canonical_value(item) for item in value)
    return value
