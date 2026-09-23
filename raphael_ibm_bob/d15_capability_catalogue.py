from __future__ import annotations

from raphael_ibm_bob.capability_registry import (
    CapabilityDescriptor,
    CapabilityRegistry,
    PrerequisiteSpec,
)

_D15_METADATA_MISSIONS = frozenset({"recon", "service_interaction"})


def _metadata_descriptor(
    capability_id: str,
    protocol: str,
    description: str,
    authorization_scope: str,
    evidence_schema: str,
) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id=capability_id,
        protocol=protocol,
        description=description,
        prerequisites=frozenset(
            {
                PrerequisiteSpec(
                    kind="service",
                    predicate=protocol,
                    description=f"{protocol} service on target",
                ),
                PrerequisiteSpec(
                    kind="authorization",
                    predicate=protocol,
                    description=f"{protocol} authorization in scope",
                ),
            }
        ),
        authorization_scope=authorization_scope,
        evidence_schema=evidence_schema,
        execution_adapter=f"raphael_ibm_bob.capability_adapters.{protocol}",
        verifier_binding=None,
        falsifier_binding=None,
        mission_types=_D15_METADATA_MISSIONS,
    )


def smb_metadata_descriptor() -> CapabilityDescriptor:
    return _metadata_descriptor(
        "NETWORK_SMB_METADATA",
        "smb",
        "Governed SMB metadata capability (declaration only).",
        "network_smb",
        "smb_metadata_v1",
    )


def tls_metadata_descriptor() -> CapabilityDescriptor:
    return _metadata_descriptor(
        "NETWORK_TLS_METADATA",
        "tls",
        "Governed TLS metadata capability (declaration only).",
        "network_tls",
        "tls_metadata_v1",
    )


def dns_metadata_descriptor() -> CapabilityDescriptor:
    return _metadata_descriptor(
        "NETWORK_DNS_METADATA",
        "dns",
        "Governed DNS metadata capability (declaration only).",
        "network_dns",
        "dns_metadata_v1",
    )


def generic_service_banner_descriptor() -> CapabilityDescriptor:
    return _metadata_descriptor(
        "NETWORK_GENERIC_SERVICE_BANNER",
        "generic-service",
        "Governed generic service banner capability (declaration only).",
        "network_service_banner",
        "service_banner_v1",
    )


def d15_descriptors() -> list[CapabilityDescriptor]:
    from raphael_ibm_bob.capability_bootstrap import ssh_descriptor

    return [
        ssh_descriptor(),
        smb_metadata_descriptor(),
        tls_metadata_descriptor(),
        dns_metadata_descriptor(),
        generic_service_banner_descriptor(),
    ]


def register_d15_descriptors(registry: CapabilityRegistry) -> CapabilityRegistry:
    from raphael_ibm_bob.capability_bootstrap import InertAdapter

    for descriptor in d15_descriptors():
        if not registry.has(descriptor.capability_id):
            registry.register(descriptor, InertAdapter())
    return registry
