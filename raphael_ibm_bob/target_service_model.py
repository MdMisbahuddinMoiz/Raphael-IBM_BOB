"""raphael_ibm_bob.target_service_model — D13 normalized target representation.

The target IS its services, scope, authorization, and observations.
Downstream code consumes ``TargetFacts`` — never raw scan output and
never target-specific branches ("if target == X").

Authority boundary: this module describes; it does not authorize.
``AuthorizationScope`` here is a *mirror* of what the operator declared
(the authoritative check remains the Policy layer against the
``target_profile.TargetProfile``). ``is_authorized_for`` is a
presentation/pre-selection convenience only and must never be treated
as a grant.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ServiceRecord:
    """A single discovered service — immutable fact."""
    host: str
    port: int
    protocol: str
    version: Optional[str] = None
    state: str = "open"          # open|filtered|closed
    banner: Optional[str] = None
    discovered_at: float = field(default_factory=time.time)
    source: str = "nmap"         # nmap|manual|prior_observation

    def key(self) -> tuple:
        return (self.host, self.port, self.protocol.lower())


@dataclass(frozen=True)
class AuthorizationScope:
    """Mirror of the operator-declared scope for pre-selection only."""
    target_host: str
    authorized_protocols: frozenset
    authorized_ports: frozenset
    engagement_id: str
    scope_document_ref: str      # reference to signed authorization, never inline


@dataclass
class TargetFacts:
    """Complete normalized representation of a target."""
    target_id: str
    host: str
    services: list = field(default_factory=list)
    authorization: Optional[AuthorizationScope] = None
    platform: Optional[str] = None
    observations: list = field(default_factory=list)
    credential_refs: list = field(default_factory=list)
    mission_id: Optional[str] = None

    def to_facts(self) -> dict:
        """Serializable facts dict consumed by Registry and Selector."""
        return {
            "target_id": self.target_id,
            "host": self.host,
            "services": [
                {"host": s.host, "port": s.port, "protocol": s.protocol,
                 "version": s.version, "state": s.state, "banner": s.banner}
                for s in self.services
            ],
            "platform": self.platform,
            "credential_refs": list(self.credential_refs),
            "mission_id": self.mission_id,
            "authorized": self.authorization is not None,
        }

    def add_service(self, service: ServiceRecord) -> None:
        """Add a discovered service, deduplicated by host:port:protocol."""
        existing = {s.key() for s in self.services}
        if service.key() not in existing:
            self.services.append(service)

    def get_service(self, protocol: str) -> Optional[ServiceRecord]:
        for s in self.services:
            if s.protocol.lower() == protocol.lower() and s.state == "open":
                return s
        return None

    def is_authorized_for(self, protocol: str, port: int) -> bool:
        """Pre-selection convenience. NOT a grant — Policy is authoritative."""
        if self.authorization is None:
            return False
        return (
            protocol.lower() in {p.lower() for p in self.authorization.authorized_protocols}
            and port in self.authorization.authorized_ports
        )


#: Protocol metadata (not a target branch): the conventional port for a
#: protocol, used only to pair declared authorized protocols with ports.
_CANONICAL_PORTS = {
    "http": 80, "https": 443, "telnet": 23, "ssh": 22, "smb": 445,
    "ftp": 21, "rdp": 3389, "mysql": 3306, "postgres": 5432,
}

# nmap service line: "23/tcp   open  telnet   Linux telnetd"
_NMAP_LINE = re.compile(
    r"^(?P<port>\d{1,5})/(?P<proto>tcp|udp)\s+"
    r"(?P<state>open|filtered|closed)\s+"
    r"(?P<service>[A-Za-z0-9_.\-]+)"
    r"(?:\s+(?P<version>.+?))?\s*$"
)


class TargetServiceModel:
    """Builds and enriches TargetFacts from standard ingestion paths."""

    @staticmethod
    def from_nmap(nmap_output: str, target_host: str,
                  authorization: Optional[AuthorizationScope] = None
                  ) -> TargetFacts:
        """Parse nmap "greppable-ish" service lines into TargetFacts."""
        facts = TargetFacts(target_id=f"target_{target_host}",
                            host=target_host, authorization=authorization)
        for line in (nmap_output or "").splitlines():
            match = _NMAP_LINE.match(line.strip())
            if not match:
                continue
            # Only open ports are ingested here; filtered/closed lines are
            # not facts about an exploitable service.
            if match.group("state") != "open":
                continue
            facts.add_service(ServiceRecord(
                host=target_host,
                port=int(match.group("port")),
                protocol=match.group("service").lower(),
                version=(match.group("version") or None),
                state=match.group("state"),
                source="nmap",
            ))
        return facts

    @staticmethod
    def from_manual(host: str, port: int, protocol: str,
                    authorization: Optional[AuthorizationScope] = None
                    ) -> TargetFacts:
        """Manual target specification — no scan output required."""
        if not (1 <= int(port) <= 65535):
            raise ValueError(f"invalid port: {port}")
        facts = TargetFacts(target_id=f"target_{host}", host=host,
                            authorization=authorization)
        facts.add_service(ServiceRecord(host=host, port=int(port),
                                        protocol=protocol.lower(),
                                        source="manual"))
        return facts

    @staticmethod
    def from_target_profile(profile: Any,
                            observations: Optional[list] = None) -> TargetFacts:
        """Bridge the existing D9 TargetProfile into TargetFacts.

        The declared protocol list is expanded to one ServiceRecord per
        authorized (protocol, port) pair held by the profile. The
        authorization *mirror* is populated from the profile, but the
        authoritative gate remains Policy against the profile itself.
        """
        protocols = tuple(str(p).lower() for p in profile.allowed_protocols)
        ports = tuple(int(p) for p in profile.allowed_ports)
        scope = AuthorizationScope(
            target_host=profile.locator,
            authorized_protocols=frozenset(protocols),
            authorized_ports=frozenset(ports),
            engagement_id=profile.mission_id,
            scope_document_ref=profile.authorization_ref,
        )
        facts = TargetFacts(
            target_id=profile.target_id,
            host=profile.locator,
            authorization=scope,
            platform=getattr(profile, "platform", None),
            observations=list(observations or []),
            mission_id=profile.mission_id,
        )
        # Declared (not discovered) services: pair each authorized protocol
        # with its canonical port when the profile permits it, else with the
        # first authorized port. This is protocol-metadata, not a
        # target-specific branch.
        for protocol in protocols:
            canonical = _CANONICAL_PORTS.get(protocol)
            port = canonical if canonical in ports else ports[0]
            facts.add_service(ServiceRecord(
                host=profile.locator, port=port, protocol=protocol,
                state="open", source="prior_observation"))
        return facts


__all__ = [
    "AuthorizationScope",
    "ServiceRecord",
    "TargetFacts",
    "TargetServiceModel",
]
