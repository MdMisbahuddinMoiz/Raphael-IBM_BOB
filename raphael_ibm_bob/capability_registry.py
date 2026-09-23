"""raphael_ibm_bob.capability_registry — D13 registry-driven capability fabric.

The SINGLE declaration index for what capabilities exist, what they
require, and which adapter *would* execute them. Adding a capability is
a registration (descriptor + adapter reference); nothing else changes.

AUTHORITY BOUNDARY (non-negotiable, same rule as `capability_fabric`):

    DECLARATION            != AUTHORIZATION
    PROVIDER RESOLUTION    != AUTHORIZATION
    CAPABILITY RESOLUTION  != EXECUTION

This module is imported by the planner-adjacent selection layer, the UI,
and the bootstrap. It MUST NOT import `broker`, `policy`, `runtime`,
`quality_gate`, `capabilities.execute_capability`, or any process/network
primitive. Execution still travels the existing single path:

    ActionRequest -> Runtime -> Broker -> Policy -> Execution -> Evidence
      -> Verification -> Falsification -> Replan -> Quality Gate

The registry is a *declaration index*, not a dispatcher. `get_adapter`
returns an object that is itself responsible for going through the
governed boundary (see `capability_bootstrap.MediatedAdapter`); the
registry never calls `execute` on anything.

Thread-safety: all mutating/reading operations take an internal lock.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable

from raphael_ibm_bob.contracts import (
    ActionRequest,
    ExecutionResult,
    Mission,
    PolicyDecision,
)


class CapabilityState(Enum):
    """Lifecycle of a capability relative to a target."""
    DISCOVERED = "discovered"      # target has a matching service
    AUTHORIZED = "authorized"      # Policy has issued an ALLOW
    READY = "ready"                # prerequisites satisfied
    EXECUTING = "executing"
    COMPLETE = "complete"
    FAILED = "failed"
    REFUSED = "refused"            # Policy DENY


@dataclass(frozen=True)
class PrerequisiteSpec:
    """Declarative prerequisite, evaluated against TargetFacts at selection."""
    kind: str          # service|credential|authorization|artifact|platform|observation
    predicate: str     # e.g. "telnet:23", "credential:ssh_valid", "platform:linux"
    description: str = ""


@dataclass(frozen=True)
class CapabilityDescriptor:
    """Immutable description of one capability.

    `capability_id` for bridged BOB capabilities equals the
    `contracts.Capability` enum *name* (e.g. "NETWORK_HTTP_REQUEST"),
    which is what lets the bootstrap map it back to the governed enum.
    """
    capability_id: str
    protocol: str
    description: str
    prerequisites: frozenset
    authorization_scope: str
    evidence_schema: str
    execution_adapter: str
    verifier_binding: Optional[str]
    falsifier_binding: Optional[str]
    mission_types: frozenset
    schema_version: str = "1.0"

    def prerequisite_specs(self) -> "tuple[PrerequisiteSpec, ...]":
        return tuple(sorted(self.prerequisites, key=lambda p: (p.kind, p.predicate)))


@runtime_checkable
class ExecutionAdapter(Protocol):
    """Contract every capability adapter must satisfy.

    `execute` MUST return a normalized observation dict (the shape
    `observation_model.ObservationBuilder` produces) and MUST itself
    route through the governed boundary. It never receives authority
    from the registry.
    """

    def execute(self, target_facts: dict, credentials: list,
                mission_params: dict) -> dict:
        ...


@runtime_checkable
class GovernedExecutionAdapter(Protocol):
    def execute_governed(
        self, request: ActionRequest, mission: Mission,
        decision: PolicyDecision,
    ) -> ExecutionResult | Any:
        ...


class AdapterNotBoundError(RuntimeError):
    """Raised when a declared capability has no governed adapter bound.

    Fail closed: a declared capability is not an executable capability.
    """


class CapabilityRegistry:
    """Sole authority for capability *registration and discovery*.

    Broker, Policy, Selector, and UI consume discovery from here. No
    capability exists outside this index; registration happens at system
    init, never mid-mission.
    """

    def __init__(self) -> None:
        self._descriptors: dict[str, CapabilityDescriptor] = {}
        self._adapters: dict[str, ExecutionAdapter] = {}
        self._registration_log: list[dict] = []
        self._lock = threading.Lock()

    def register(self, descriptor: CapabilityDescriptor,
                 adapter: ExecutionAdapter) -> None:
        """Register a capability. Duplicate ids are a governance violation."""
        if not isinstance(descriptor, CapabilityDescriptor):
            raise TypeError("descriptor must be a CapabilityDescriptor")
        if not descriptor.capability_id:
            raise ValueError("capability_id is required")
        if not isinstance(descriptor.prerequisites, frozenset):
            raise TypeError("prerequisites must be frozenset (immutability)")
        if not isinstance(descriptor.mission_types, frozenset):
            raise TypeError("mission_types must be frozenset (immutability)")
        if adapter is None:
            raise TypeError("adapter is required (use an inert adapter to "
                            "declare a not-yet-executable capability)")
        with self._lock:
            if descriptor.capability_id in self._descriptors:
                raise ValueError(
                    f"capability already registered: "
                    f"{descriptor.capability_id}. Re-registration is a "
                    f"governance violation.")
            self._descriptors[descriptor.capability_id] = descriptor
            self._adapters[descriptor.capability_id] = adapter
            self._registration_log.append({
                "capability_id": descriptor.capability_id,
                "protocol": descriptor.protocol,
                "evidence_schema": descriptor.evidence_schema,
                "registered_at": time.time(),
            })

    def bind_adapter(self, capability_id: str,
                     adapter: ExecutionAdapter) -> None:
        """Bind (or replace) the execution adapter for a registered capability.

        Binding is a system-init step, separate from registration, so a
        capability may be *declared* before its governed adapter exists
        (fail-closed `InertAdapter`), then bound explicitly.
        """
        if adapter is None:
            raise TypeError("adapter is required")
        with self._lock:
            if capability_id not in self._descriptors:
                raise KeyError(f"unknown capability: {capability_id}")
            self._adapters[capability_id] = adapter

    def get(self, capability_id: str) -> CapabilityDescriptor:
        with self._lock:
            try:
                return self._descriptors[capability_id]
            except KeyError:
                raise KeyError(f"unknown capability: {capability_id}") from None

    def has(self, capability_id: str) -> bool:
        with self._lock:
            return capability_id in self._descriptors

    def get_adapter(self, capability_id: str) -> ExecutionAdapter:
        with self._lock:
            try:
                return self._adapters[capability_id]
            except KeyError:
                matching_id = next(
                    (registered_id for registered_id in self._descriptors
                     if registered_id.lower() == capability_id.lower()),
                    None,
                )
                if matching_id is not None:
                    return self._adapters[matching_id]
                raise KeyError(f"no adapter for: {capability_id}") from None

    def discover_for_target(self,
                            target_facts: dict) -> list[CapabilityDescriptor]:
        """Capabilities whose protocol matches an *open* target service.

        Target-agnostic: no `if target == X`. Facts drive discovery.
        """
        services = target_facts.get("services", []) or []
        available_protocols = {
            str(s.get("protocol", "")).lower()
            for s in services
            if s.get("protocol") and s.get("state", "open") == "open"
        }
        if not available_protocols:
            return []
        with self._lock:
            descriptors = list(self._descriptors.values())
        return [d for d in descriptors
                if d.protocol.lower() in available_protocols]

    def all_capabilities(self) -> list[CapabilityDescriptor]:
        with self._lock:
            return [self._descriptors[k] for k in sorted(self._descriptors)]

    def capabilities_for_mission(self,
                                 mission_type: str) -> list[CapabilityDescriptor]:
        with self._lock:
            descriptors = list(self._descriptors.values())
        return [d for d in descriptors if mission_type in d.mission_types]

    def registration_log(self) -> list[dict]:
        """Audit trail for registration — append to EvidenceLedger at init."""
        with self._lock:
            return list(self._registration_log)


# ---------------------------------------------------------------------------
# Process-wide registry (initialized at boot; replaceable for tests)
# ---------------------------------------------------------------------------

_registry: Optional[CapabilityRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> CapabilityRegistry:
    """Return the process-wide registry, creating an empty one if needed."""
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = CapabilityRegistry()
        return _registry


def set_registry(registry: Optional[CapabilityRegistry]) -> None:
    """Install a registry explicitly (dependency injection / tests)."""
    global _registry
    with _registry_lock:
        _registry = registry


def initialize_registry() -> CapabilityRegistry:
    """Fresh, empty registry for testing. Never call during a live mission."""
    registry = CapabilityRegistry()
    set_registry(registry)
    return registry


__all__ = [
    "AdapterNotBoundError",
    "CapabilityDescriptor",
    "CapabilityRegistry",
    "CapabilityState",
    "ExecutionAdapter",
    "GovernedExecutionAdapter",
    "PrerequisiteSpec",
    "get_registry",
    "initialize_registry",
    "set_registry",
]
