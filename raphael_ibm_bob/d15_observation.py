"""D15 normalized observations for metadata-only capability families.

The builders deliberately reuse ``ObservationBuilder`` from
``observation_model.py:47-99`` and put the bounded family payload in
``ObservationRecord.provenance["normalized"]``.  No builder accepts raw
protocol output, credentials, configuration values, or file contents.
"""
from __future__ import annotations

# noqa: SIZE_OK — D15 family builders and their compatibility aliases stay one facade.

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import replace
from typing import Final, TypeAlias

from raphael_ibm_bob._d15_observation_types import (
    ArtifactConfigurationMetadata,
    AuthoritativeSessionBinding,
    DnsMetadata,
    ObservationContext,
    ServiceBannerMetadata,
    SmbServiceMetadata,
    SshServiceMetadata,
    TlsMetadata,
)
from raphael_ibm_bob.d14_state_codec import ExecutionBinding
from raphael_ibm_bob.observation_model import ObservationBuilder, ObservationRecord


NormalizedValue: TypeAlias = str | int | None | list[str]
NormalizedMetadata: TypeAlias = dict[str, NormalizedValue]

_MAX_TEXT_LENGTH: Final = 128
_MAX_LIST_ITEMS: Final = 32
_MAX_COUNT: Final = 1_000_000
_MAX_PORT: Final = 65_535
_SAFE_REFERENCE: Final = re.compile(r"^[a-z0-9._:/+-]+$")


class ObservationNormalizationError(ValueError):
    """Raised when a D15 field cannot be represented safely."""


def _text(value: str | None, field: str, *, lowercase: bool = False) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ObservationNormalizationError(f"{field} must be text")
    normalized = " ".join(value.strip().split())
    if lowercase:
        normalized = normalized.casefold()
    return normalized[:_MAX_TEXT_LENGTH].rstrip() or None


def _required_text(value: str, field: str, *, lowercase: bool = False) -> str:
    normalized = _text(value, field, lowercase=lowercase)
    if normalized is None:
        raise ObservationNormalizationError(f"{field} is required")
    return normalized


def _family_protocol(value: str, expected: str) -> str:
    protocol = _required_text(value, "protocol", lowercase=True)
    if protocol != expected:
        raise ObservationNormalizationError(f"protocol must be {expected}")
    return protocol


def _reference(value: str | None, field: str) -> str | None:
    normalized = _text(value, field, lowercase=True)
    if normalized is None:
        return None
    if _SAFE_REFERENCE.fullmatch(normalized) is None:
        raise ObservationNormalizationError(f"{field} is not a bounded reference")
    return normalized


def _tokens(values: Sequence[str], field: str) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise ObservationNormalizationError(f"{field} must be a sequence of values")
    normalized = {
        token
        for value in values
        if (token := _text(value, field, lowercase=True)) is not None
    }
    return sorted(normalized)[:_MAX_LIST_ITEMS]


def _count(value: int | None, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ObservationNormalizationError(f"{field} must be an integer")
    return min(max(value, 0), _MAX_COUNT)


def _port(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ObservationNormalizationError("target_port must be an integer")
    if not 0 <= value <= _MAX_PORT:
        raise ObservationNormalizationError("target_port is outside the port range")
    return value


def _context(context: ObservationContext) -> tuple[str, str, str, int | None]:
    binding = context.session_binding
    if binding is None:
        raise ObservationNormalizationError(
            "authoritative session binding is required",
        )
    if not isinstance(binding, AuthoritativeSessionBinding):
        raise ObservationNormalizationError(
            "session binding must be issued by the governed boundary",
        )
    return (
        _required_text(context.capability_id, "capability_id"),
        _required_text(context.target_host, "target_host"),
        _required_text(binding.session_id, "session_id"),
        _port(context.target_port),
    )


def _record(
    context: ObservationContext,
    observation_type: str,
    normalized: NormalizedMetadata,
) -> ObservationRecord:
    capability_id, target_host, session_id, target_port = _context(context)
    canonical_metadata = {key: normalized[key] for key in sorted(normalized)}
    canonical = json.dumps(
        canonical_metadata,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return ObservationBuilder.from_capability_output(
        capability_id=capability_id,
        output=canonical,
        target_host=target_host,
        target_port=target_port,
        observation_type=observation_type,
        provenance={"session_id": session_id, "normalized": canonical_metadata},
    )


def associate_observation(
    observation: ObservationRecord,
    binding: ExecutionBinding,
) -> ObservationRecord:
    """Attach a normalized observation to one runtime-issued execution link."""
    session_id = observation.provenance.get("session_id")
    if session_id != binding.session_binding.session_id:
        raise ObservationNormalizationError(
            "observation session does not match runtime session binding",
        )
    if observation.capability_id.casefold() != binding.capability_id.casefold():
        raise ObservationNormalizationError(
            "observation capability does not match governed execution",
        )
    normalized = observation.provenance.get("normalized")
    if not isinstance(normalized, dict):
        raise ObservationNormalizationError(
            "execution association requires normalized metadata",
        )
    execution_binding = binding.to_provenance()
    existing_binding = observation.provenance.get("execution_binding")
    if existing_binding is not None and existing_binding != execution_binding:
        raise ObservationNormalizationError(
            "observation has a conflicting execution association",
        )
    provenance = dict(observation.provenance)
    provenance["execution_binding"] = execution_binding
    identity = {
        "capability_id": observation.capability_id,
        "observation_type": observation.observation_type,
        "target_host": observation.target_host,
        "target_port": observation.target_port,
        "content_hash": observation.content_hash,
        "normalized": normalized,
        "execution_binding": execution_binding,
    }
    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    observation_id = "D16-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return replace(
        observation,
        observation_id=observation_id,
        provenance=provenance,
    )


def build_ssh_service(
    context: ObservationContext,
    metadata: SshServiceMetadata | None = None,
) -> ObservationRecord:
    """Build a bounded ``ssh_service`` observation."""
    data = metadata or SshServiceMetadata()
    return _record(context, "ssh_service", {
        "host_key_algorithms": _tokens(data.host_key_algorithms, "host_key_algorithms"),
        "protocol": _family_protocol(data.protocol, "ssh"),
        "protocol_version": _text(data.protocol_version, "protocol_version"),
        "service_state": _required_text(data.service_state, "service_state", lowercase=True),
        "transport": _required_text(data.transport, "transport", lowercase=True),
        "version_banner_hash": _reference(data.version_banner_hash, "version_banner_hash"),
    })


def build_smb_service(
    context: ObservationContext,
    metadata: SmbServiceMetadata | None = None,
) -> ObservationRecord:
    """Build a bounded ``smb_service`` observation."""
    data = metadata or SmbServiceMetadata()
    return _record(context, "smb_service", {
        "capability_flags": _tokens(data.capability_flags, "capability_flags"),
        "dialects": _tokens(data.dialects, "dialects"),
        "protocol": _family_protocol(data.protocol, "smb"),
        "service_state": _required_text(data.service_state, "service_state", lowercase=True),
        "signing_status": _text(data.signing_status, "signing_status", lowercase=True),
        "transport": _required_text(data.transport, "transport", lowercase=True),
    })


def build_tls_metadata(
    context: ObservationContext,
    metadata: TlsMetadata | None = None,
) -> ObservationRecord:
    """Build a bounded ``tls_metadata`` observation."""
    data = metadata or TlsMetadata()
    return _record(context, "tls_metadata", {
        "certificate_fingerprint": _reference(data.certificate_fingerprint, "certificate_fingerprint"),
        "certificate_issuer_hash": _reference(data.certificate_issuer_hash, "certificate_issuer_hash"),
        "certificate_not_after": _text(data.certificate_not_after, "certificate_not_after"),
        "certificate_not_before": _text(data.certificate_not_before, "certificate_not_before"),
        "certificate_subject_hash": _reference(data.certificate_subject_hash, "certificate_subject_hash"),
        "cipher_suite": _text(data.cipher_suite, "cipher_suite", lowercase=True),
        "tls_version": _text(data.tls_version, "tls_version", lowercase=True),
        "verification_status": _text(data.verification_status, "verification_status", lowercase=True),
    })


def build_dns_metadata(
    context: ObservationContext,
    metadata: DnsMetadata | None = None,
) -> ObservationRecord:
    """Build a bounded ``dns_metadata`` observation."""
    data = metadata or DnsMetadata()
    response_code = (
        str(data.response_code)
        if isinstance(data.response_code, int) and not isinstance(data.response_code, bool)
        else data.response_code
    )
    ttl_min = _count(data.ttl_min, "ttl_min")
    ttl_max = _count(data.ttl_max, "ttl_max")
    if ttl_min is not None and ttl_max is not None and ttl_min > ttl_max:
        ttl_min, ttl_max = ttl_max, ttl_min
    return _record(context, "dns_metadata", {
        "answer_count": _count(data.answer_count, "answer_count") or 0,
        "dnssec_status": _text(data.dnssec_status, "dnssec_status", lowercase=True),
        "record_types": _tokens(data.record_types, "record_types"),
        "response_code": _required_text(response_code, "response_code", lowercase=True),
        "transport": _required_text(data.transport, "transport", lowercase=True),
        "ttl_max": ttl_max,
        "ttl_min": ttl_min,
    })


def build_service_banner(
    context: ObservationContext,
    metadata: ServiceBannerMetadata,
) -> ObservationRecord:
    """Build a bounded ``service_banner`` observation without raw banner text."""
    return _record(context, "service_banner", {
        "banner_hash": _reference(metadata.banner_hash, "banner_hash"),
        "protocol": _required_text(metadata.protocol, "protocol", lowercase=True),
        "transport": _required_text(metadata.transport, "transport", lowercase=True),
        "version": _text(metadata.version, "version"),
    })


def build_artifact_configuration(
    context: ObservationContext,
    metadata: ArtifactConfigurationMetadata | None = None,
) -> ObservationRecord:
    """Build structural ``artifact_configuration`` metadata only."""
    data = metadata or ArtifactConfigurationMetadata()
    return _record(context, "artifact_configuration", {
        "artifact_hash": _reference(data.artifact_hash, "artifact_hash"),
        "artifact_type": _required_text(data.artifact_type, "artifact_type", lowercase=True),
        "entry_count": _count(data.entry_count, "entry_count"),
        "format": _text(data.format, "format", lowercase=True),
        "schema_version": _text(data.schema_version, "schema_version"),
        "size_bytes": _count(data.size_bytes, "size_bytes"),
    })


build_ssh_service_observation = build_ssh_service
build_smb_service_observation = build_smb_service
build_tls_metadata_observation = build_tls_metadata
build_dns_metadata_observation = build_dns_metadata
build_service_banner_observation = build_service_banner
build_artifact_configuration_observation = build_artifact_configuration


__all__ = [
    "ArtifactConfigurationMetadata",
    "AuthoritativeSessionBinding",
    "DnsMetadata",
    "ObservationContext",
    "ObservationNormalizationError",
    "ServiceBannerMetadata",
    "SmbServiceMetadata",
    "SshServiceMetadata",
    "TlsMetadata",
    "associate_observation",
    "build_artifact_configuration",
    "build_artifact_configuration_observation",
    "build_dns_metadata",
    "build_dns_metadata_observation",
    "build_service_banner",
    "build_service_banner_observation",
    "build_smb_service",
    "build_smb_service_observation",
    "build_ssh_service",
    "build_ssh_service_observation",
    "build_tls_metadata",
    "build_tls_metadata_observation",
]
