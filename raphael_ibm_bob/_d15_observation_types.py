"""Typed inputs for D15 normalized observation builders."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Protocol


class GovernedRuntimeSession(Protocol):
    """Runtime session view from which the broker stamps observations."""

    @property
    def session_id(self) -> str:
        """Return the authoritative runtime-owned session identity."""


class _SessionBindingAuthority:
    __slots__ = ()


_SESSION_BINDING_AUTHORITY: Final = _SessionBindingAuthority()


class SessionBindingError(TypeError):
    """Raised when a session stamp is not issued by the governed boundary."""


@dataclass(frozen=True, slots=True, init=False)
class AuthoritativeSessionBinding:
    """Opaque session stamp issued by the governed runtime boundary."""

    _session_id: str = field(repr=False)

    def __init__(
        self,
        session_id: str,
        *,
        authority: _SessionBindingAuthority,
    ) -> None:
        if authority is not _SESSION_BINDING_AUTHORITY:
            raise SessionBindingError(
                "session bindings must be issued by the governed boundary",
            )
        object.__setattr__(self, "_session_id", session_id)

    @classmethod
    def from_governed_runtime(
        cls,
        runtime_session: GovernedRuntimeSession,
    ) -> AuthoritativeSessionBinding:
        """Capture the session identity supplied by broker/runtime state."""
        return cls(
            runtime_session.session_id,
            authority=_SESSION_BINDING_AUTHORITY,
        )

    @property
    def session_id(self) -> str:
        """Return the immutable broker/runtime-issued session identity."""
        return self._session_id


@dataclass(frozen=True, slots=True)
class ObservationContext:
    """Broker/runtime identity shared by one normalized observation."""

    capability_id: str
    target_host: str
    target_port: int | None = None
    session_binding: AuthoritativeSessionBinding | None = None

    @classmethod
    def from_governed_runtime(
        cls,
        *,
        capability_id: str,
        target_host: str,
        runtime_session: GovernedRuntimeSession,
        target_port: int | None = None,
    ) -> ObservationContext:
        """Build context with a session stamp supplied by broker/runtime."""
        return cls(
            capability_id=capability_id,
            target_host=target_host,
            target_port=target_port,
            session_binding=AuthoritativeSessionBinding.from_governed_runtime(
                runtime_session,
            ),
        )


@dataclass(frozen=True, slots=True)
class SshServiceMetadata:
    """Safe SSH service metadata; no banner or key material is accepted."""

    protocol: str = "ssh"
    transport: str = "tcp"
    service_state: str = "open"
    protocol_version: str | None = None
    version_banner_hash: str | None = None
    host_key_algorithms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SmbServiceMetadata:
    """Safe SMB service metadata without shares, users, or credentials."""

    protocol: str = "smb"
    transport: str = "tcp"
    service_state: str = "open"
    dialects: tuple[str, ...] = ()
    signing_status: str | None = None
    capability_flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TlsMetadata:
    """Certificate metadata and hashes, never a certificate or subject name."""

    tls_version: str | None = None
    cipher_suite: str | None = None
    certificate_subject_hash: str | None = None
    certificate_issuer_hash: str | None = None
    certificate_not_before: str | None = None
    certificate_not_after: str | None = None
    certificate_fingerprint: str | None = None
    verification_status: str | None = None


@dataclass(frozen=True, slots=True)
class DnsMetadata:
    """DNS response metadata without names, answers, or queried content."""

    transport: str = "udp"
    response_code: str | int = "NOERROR"
    record_types: tuple[str, ...] = ()
    answer_count: int = 0
    ttl_min: int | None = None
    ttl_max: int | None = None
    dnssec_status: str | None = None


@dataclass(frozen=True, slots=True)
class ServiceBannerMetadata:
    """A service identity hash and version, never a raw banner."""

    protocol: str
    transport: str = "tcp"
    banner_hash: str | None = None
    version: str | None = None


@dataclass(frozen=True, slots=True)
class ArtifactConfigurationMetadata:
    """Structural artifact metadata with no configuration values or contents."""

    artifact_type: str = "configuration"
    artifact_hash: str | None = None
    format: str | None = None
    size_bytes: int | None = None
    entry_count: int | None = None
    schema_version: str | None = None


__all__ = [
    "ArtifactConfigurationMetadata",
    "AuthoritativeSessionBinding",
    "DnsMetadata",
    "GovernedRuntimeSession",
    "ObservationContext",
    "SessionBindingError",
    "ServiceBannerMetadata",
    "SmbServiceMetadata",
    "SshServiceMetadata",
    "TlsMetadata",
]
