"""raphael_ibm_bob.capability_fabric — M16.1 Capability Fabric seam.

A *provider-resolution* seam over the existing native capabilities. It
answers "which provider can supply this capability?" and can PREPARE the
ordinary `ActionRequest` the existing execution path consumes. It is NOT
an executor, NOT an orchestrator, and NOT an authority.

Semantic boundaries (preserved deliberately):

    DECLARATION != AUTHORIZATION
    PROVIDER RESOLUTION != AUTHORIZATION
    CAPABILITY RESOLUTION != EXECUTION

Authority is unchanged and lives elsewhere:

    ActionRequest -> Runtime -> Broker -> Policy -> Execution -> Evidence
      -> Verification -> Falsification -> Replan -> Quality Gate

The Fabric MUST NOT: plan missions, choose replans, decide the Quality
Gate, bypass the Broker/Policy/Runtime, execute a capability, mutate
findings/evidence, or replace the existing skill/role declaration
registry. It imports only the declaration layer (`contracts`, `skills`)
— never `broker`, `policy`, `runtime`, `quality_gate`, or
`capabilities.execute_capability`.

Future providers (DESIGN ONLY, not implemented here):

    RAPHAEL NATIVE PROVIDER
              \
               -> Capability Fabric -> ActionRequest -> Runtime -> ...
              /
    future Decepticon adapter
    future T3MP3ST adapter
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Protocol, Tuple, runtime_checkable

from raphael_ibm_bob.contracts import ActionRequest, Capability
from raphael_ibm_bob.skills import (
    CapabilityDefinition,
    CapabilityRegistry,
    default_registry,
    register_default_skills,
)

#: The provider id of the first (and only) concrete provider.
NATIVE_PROVIDER_ID = "raphael-native"

#: The provider id of the C1A out-of-process provider.
C1A_PROVIDER_ID = "t3mp3st"


# ---------------------------------------------------------------------------
# explicit error taxonomy (deterministic, never silent)
# ---------------------------------------------------------------------------

class CapabilityFabricError(Exception):
    """Base class for Capability Fabric errors."""


class DuplicateProviderError(CapabilityFabricError):
    """A provider id was registered twice."""


class ProviderNotFoundError(CapabilityFabricError):
    """An explicit provider id is not registered."""


class CapabilityNotProvidedError(CapabilityFabricError):
    """No registered provider supplies the requested capability."""


class AmbiguousCapabilityError(CapabilityFabricError):
    """More than one provider claims a capability and none was named."""

    def __init__(self, capability: Capability, providers: Tuple[str, ...]):
        self.capability = capability
        self.providers = providers
        super().__init__(
            f"capability {capability.value!r} is claimed by multiple "
            f"providers {list(providers)}; name one explicitly "
            f"(no silent shadowing)")


# ---------------------------------------------------------------------------
# provider contract
# ---------------------------------------------------------------------------

@runtime_checkable
class CapabilityProvider(Protocol):
    """A provider of one or more capabilities.

    A provider DECLARES and PREPARES capabilities; it never authorizes
    or executes them.
    """

    #: Stable provider identity.
    provider_id: str

    def list_capabilities(self) -> Tuple[Capability, ...]:
        """Capabilities this provider supplies (deterministic order)."""
        ...

    def declaration(self, capability: Capability) -> CapabilityDefinition:
        """The declaration metadata for one supplied capability."""
        ...

    def build_action_request(
        self,
        capability: Capability,
        target: str,
        *,
        purpose: Optional[str] = None,
        requester: Optional[str] = None,
        plan_id: Optional[str] = None,
        finding_id: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> ActionRequest:
        """Prepare an ordinary ActionRequest. Grants NO authority."""
        ...


# ---------------------------------------------------------------------------
# native provider
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NativeCapabilityProvider:
    """Wraps the EXISTING native capability declarations.

    It invents no capability definitions: `registry` is the same
    authoritative `CapabilityRegistry` used elsewhere. Execution remains
    in the existing capability/ Broker path; this provider only declares
    and prepares.
    """
    registry: CapabilityRegistry
    provider_id: str = NATIVE_PROVIDER_ID

    def list_capabilities(self) -> Tuple[Capability, ...]:
        return tuple(sorted((d.capability
                             for d in self.registry.list_capabilities()),
                            key=lambda c: c.value))

    def declaration(self, capability: Capability) -> CapabilityDefinition:
        if not isinstance(capability, Capability):
            raise ValueError(
                f"capability must be a Capability enum, got "
                f"{type(capability).__name__}")
        return self.registry.lookup_capability(capability)

    def build_action_request(
        self,
        capability: Capability,
        target: str,
        *,
        purpose: Optional[str] = None,
        requester: Optional[str] = None,
        plan_id: Optional[str] = None,
        finding_id: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> ActionRequest:
        declaration = self.declaration(capability)
        if not target:
            raise ValueError("target is required")
        resolved_purpose = purpose or \
            declaration.purpose_template.format(target=target)
        resolved_timeout = (timeout_seconds if timeout_seconds is not None
                            else declaration.timeout_seconds)
        return ActionRequest(
            sequence=0,
            requester=requester or f"provider:{self.provider_id}",
            capability=capability,
            target=target,
            purpose=resolved_purpose,
            plan_id=plan_id,
            finding_id=finding_id,
            timeout_seconds=resolved_timeout,
        )


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

class CapabilityFabric:
    """Deterministic provider registry + capability resolution.

    Construction is explicit (dependency injection): register the
    providers you want. There is no module-level mutable global.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, CapabilityProvider] = {}

    # --- registration / discovery --------------------------------------

    def register(self, provider: CapabilityProvider) -> None:
        """Register a provider; duplicate ids are rejected explicitly."""
        provider_id = getattr(provider, "provider_id", None)
        if not provider_id:
            raise CapabilityFabricError("provider_id is required")
        if provider_id in self._providers:
            raise DuplicateProviderError(
                f"provider already registered: {provider_id!r}")
        self._providers[provider_id] = provider

    def list_providers(self) -> Tuple[str, ...]:
        return tuple(sorted(self._providers))

    def get_provider(self, provider_id: str) -> CapabilityProvider:
        try:
            return self._providers[provider_id]
        except KeyError:
            raise ProviderNotFoundError(
                f"provider not registered: {provider_id!r}") from None

    def providers_for(self, capability: Capability) -> Tuple[str, ...]:
        if not isinstance(capability, Capability):
            raise ValueError(
                f"capability must be a Capability enum, got "
                f"{type(capability).__name__}")
        return tuple(sorted(
            pid for pid, provider in self._providers.items()
            if capability in provider.list_capabilities()))

    # --- resolution -----------------------------------------------------

    def resolve(self, capability: Capability,
                provider_id: Optional[str] = None) -> CapabilityProvider:
        """Resolve capability -> provider. Grants NO authority.

        With an explicit `provider_id`, that provider must supply the
        capability. Without one, resolution is deterministic: a single
        claimant resolves; zero or multiple claimants raise explicitly
        (no silent shadowing).
        """
        if not isinstance(capability, Capability):
            raise ValueError(
                f"capability must be a Capability enum, got "
                f"{type(capability).__name__}")
        if provider_id is not None:
            provider = self.get_provider(provider_id)
            if capability not in provider.list_capabilities():
                raise CapabilityNotProvidedError(
                    f"provider {provider_id!r} does not supply "
                    f"{capability.value!r}")
            return provider
        claimants = self.providers_for(capability)
        if not claimants:
            raise CapabilityNotProvidedError(
                f"no provider supplies capability {capability.value!r}")
        if len(claimants) > 1:
            raise AmbiguousCapabilityError(capability, claimants)
        return self._providers[claimants[0]]


def default_fabric() -> CapabilityFabric:
    """A fresh fabric with the authoritative registry behind NATIVE.

    Builds a NEW registry each call (no shared mutable global state).
    """
    registry = register_default_skills(default_registry())
    fabric = CapabilityFabric()
    fabric.register(NativeCapabilityProvider(registry=registry))
    return fabric


# ---------------------------------------------------------------------------
# C1A provider (Phase 2C) — declared as a first-class capability
# ---------------------------------------------------------------------------

def c1a_capability_definition() -> CapabilityDefinition:
    """The authoritative declaration of the C1A capability.

    The definition grants NO authority; it is metadata used by the Fabric
    to prepare an ordinary ActionRequest. Authorization and execution remain
    with Broker -> Policy -> ProviderRuntime.
    """
    return CapabilityDefinition(
        capability=Capability.C1A_STATIC_FILE_INSPECT,
        description=("Out-of-process static file inspection via the governed "
                     "C1A provider boundary (binary_sink_scan)."),
        target_schema="absolute file path inside the workspace",
        purpose_template="c1a:static-file-inspect:{target}",
        verification_expectation=("bounded ProviderResult with no authority "
                                  "fields; independent reproduction required"),
        version="1.0",
        timeout_seconds=10.0,
        evidence_produced=("provider-receipt",),
        evidence_consumed=("inspection",),
    )


@dataclass(frozen=True)
class C1ACapabilityProvider:
    """Provider declaration for the single C1A capability.

    This provider DECLARES/PREPARES; it never authorizes or executes. The
    execution boundary is the Broker + ProviderRuntime.
    """
    provider_id: str = C1A_PROVIDER_ID
    definition: CapabilityDefinition = field(
        default_factory=c1a_capability_definition)

    def list_capabilities(self) -> Tuple[Capability, ...]:
        return (Capability.C1A_STATIC_FILE_INSPECT,)

    def declaration(self, capability: Capability) -> CapabilityDefinition:
        if capability is not Capability.C1A_STATIC_FILE_INSPECT:
            raise CapabilityNotProvidedError(
                f"provider {self.provider_id!r} does not supply "
                f"{getattr(capability, 'value', capability)!r}")
        return self.definition

    def build_action_request(
        self,
        capability: Capability,
        target: str,
        *,
        purpose: Optional[str] = None,
        requester: Optional[str] = None,
        plan_id: Optional[str] = None,
        finding_id: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> ActionRequest:
        declaration = self.declaration(capability)
        if not target:
            raise ValueError("target is required")
        resolved_purpose = purpose or \
            declaration.purpose_template.format(target=target)
        resolved_timeout = (timeout_seconds if timeout_seconds is not None
                            else declaration.timeout_seconds)
        return ActionRequest(
            sequence=0,
            requester=requester or f"provider:{self.provider_id}",
            capability=capability,
            target=target,
            purpose=resolved_purpose,
            plan_id=plan_id,
            finding_id=finding_id,
            timeout_seconds=resolved_timeout,
        )


def c1a_fabric() -> CapabilityFabric:
    """Fabric with both the native provider and the C1A provider.

    ``default_fabric()`` is intentionally left unchanged (the native
    registry stays at its five authoritative capabilities); C1A is added
    through this explicit, opt-in seam.
    """
    fabric = default_fabric()
    fabric.register(C1ACapabilityProvider())
    return fabric


__all__ = [
    "AmbiguousCapabilityError",
    "C1ACapabilityProvider",
    "CapabilityFabric",
    "CapabilityFabricError",
    "CapabilityNotProvidedError",
    "CapabilityProvider",
    "DuplicateProviderError",
    "NATIVE_PROVIDER_ID",
    "C1A_PROVIDER_ID",
    "NativeCapabilityProvider",
    "ProviderNotFoundError",
    "c1a_capability_definition",
    "c1a_fabric",
    "default_fabric",
]
