"""raphael_ibm_bob.target_profile — first-class authorized network target (D9).

An HTB target is an explicit, operator-declared object bound to exactly
one ``mission_id``. It is deliberately NOT part of ``contracts.Mission``
(the Mission contract is unchanged): the target lives beside it and is
consulted by Policy (authorization) and the QualityGate (network scope).

Security invariants:

    * a profile belongs to exactly one mission; a run under a different
      mission can never reuse it (``TargetStore.get_target(mission_id)``
      returns None on mismatch -> Policy DENY)
    * platform is ``htb`` (the only MVP platform)
    * the locator is a canonical host/IP and must be inside ``scope``
    * ports / protocols are explicit allow-lists
    * an authorization reference is mandatory (operator-declared)

State is process-local (no database, no filesystem persistence), matching
the D7 VPN and D8 mode state model.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from raphael_ibm_bob.network_scope import (
    NetworkScopeError,
    canonical_host,
    host_in_scope,
)

ALLOWED_PLATFORMS = ("htb",)
#: D12 adds "telnet" for the governed Telnet session capability. Existing
#: HTTP target checks are unchanged; authorization stays exact per protocol.
ALLOWED_PROTOCOLS = ("http", "https", "telnet")


class TargetProfileError(ValueError):
    """The supplied target profile is malformed or unauthorized."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _coerce_ports(value: Any) -> Tuple[int, ...]:
    if isinstance(value, str):
        value = [p for p in value.replace(" ", "").split(",") if p]
    if not isinstance(value, (list, tuple)):
        raise TargetProfileError("allowed_ports must be a list of ports")
    ports = []
    for raw in value:
        try:
            port = int(raw)
        except (TypeError, ValueError):
            raise TargetProfileError(f"invalid port: {raw!r}") from None
        if not (1 <= port <= 65535):
            raise TargetProfileError(f"port out of range: {port}")
        ports.append(port)
    if not ports:
        raise TargetProfileError("at least one allowed port is required")
    return tuple(sorted(set(ports)))


def _coerce_protocols(value: Any) -> Tuple[str, ...]:
    if isinstance(value, str):
        value = [p for p in value.replace(" ", "").split(",") if p]
    if not isinstance(value, (list, tuple)):
        raise TargetProfileError("allowed_protocols must be a list")
    protocols = []
    for raw in value:
        name = str(raw).strip().lower()
        if name not in ALLOWED_PROTOCOLS:
            raise TargetProfileError(f"unsupported protocol: {raw!r}")
        protocols.append(name)
    if not protocols:
        raise TargetProfileError("at least one allowed protocol is required")
    return tuple(sorted(set(protocols)))


@dataclass(frozen=True)
class TargetProfile:
    """An operator-declared, mission-bound authorized network target."""
    target_id: str
    mission_id: str
    platform: str
    locator: str
    allowed_ports: Tuple[int, ...]
    allowed_protocols: Tuple[str, ...]
    scope: str
    authorization_ref: str
    environment: str = "htb"
    version: str = "1.0"
    created_ts: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "mission_id": self.mission_id,
            "platform": self.platform,
            "locator": self.locator,
            "allowed_ports": list(self.allowed_ports),
            "allowed_protocols": list(self.allowed_protocols),
            "scope": self.scope,
            "authorization_ref": self.authorization_ref,
            "environment": self.environment,
            "version": self.version,
            "created_ts": self.created_ts,
        }

    def allows(self, *, host: str, port: int, protocol: str) -> bool:
        """Deterministic host/port/protocol authorization (fail closed)."""
        try:
            canonical = canonical_host(host)
        except NetworkScopeError:
            return False
        if canonical != self.locator:
            return False
        if not host_in_scope(self.scope, canonical):
            return False
        if port not in self.allowed_ports:
            return False
        if protocol.lower() not in self.allowed_protocols:
            return False
        return True


def build_target_profile(
    *,
    mission_id: object,
    locator: object,
    allowed_ports: object,
    allowed_protocols: object,
    scope: object = None,
    authorization_ref: object,
    platform: str = "htb",
    environment: str = "htb",
) -> TargetProfile:
    """Validate operator input and build a TargetProfile."""
    if not isinstance(mission_id, str) or mission_id.strip() == "":
        raise TargetProfileError("mission_id is required")
    if platform not in ALLOWED_PLATFORMS:
        raise TargetProfileError(f"unsupported platform: {platform!r}")
    try:
        canonical_locator = canonical_host(locator)
    except NetworkScopeError as exc:
        raise TargetProfileError(str(exc)) from None
    ports = _coerce_ports(allowed_ports)
    protocols = _coerce_protocols(allowed_protocols)
    if not isinstance(authorization_ref, str) or authorization_ref.strip() == "":
        raise TargetProfileError("authorization_ref is required")
    scope_text = str(scope).strip() if scope not in (None, "") else canonical_locator
    if not host_in_scope(scope_text, canonical_locator):
        raise TargetProfileError(
            "locator is not contained in the declared scope")
    target_id = "TP-" + hashlib.sha256(_canonical({
        "mission_id": mission_id,
        "platform": platform,
        "locator": canonical_locator,
        "ports": list(ports),
        "protocols": list(protocols),
    }).encode("utf-8")).hexdigest()[:16]
    return TargetProfile(
        target_id=target_id,
        mission_id=mission_id,
        platform=platform,
        locator=canonical_locator,
        allowed_ports=ports,
        allowed_protocols=protocols,
        scope=scope_text,
        authorization_ref=authorization_ref.strip(),
        environment=environment,
    )


class TargetStore:
    """Process-local holder for the single active authorized target.

    Mission-bound: ``get_target(mission_id)`` returns the profile only
    when its mission matches, so a target declared for Mission A can
    never be reused by a run under Mission B.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._profile: Optional[TargetProfile] = None

    def set_target(self, profile: TargetProfile) -> TargetProfile:
        if not isinstance(profile, TargetProfile):
            raise TargetProfileError("profile must be a TargetProfile")
        with self._lock:
            self._profile = profile
            return profile

    def get_target(self, mission_id: object) -> Optional[TargetProfile]:
        with self._lock:
            profile = self._profile
        if profile is None:
            return None
        if not isinstance(mission_id, str) or profile.mission_id != mission_id:
            return None
        return profile

    def current(self) -> Optional[TargetProfile]:
        with self._lock:
            return self._profile

    def clear_target(self) -> None:
        with self._lock:
            self._profile = None


_store_singleton: Optional[TargetStore] = None
_store_lock = threading.Lock()


def get_target_store() -> TargetStore:
    """Return the process-wide target store."""
    global _store_singleton
    with _store_lock:
        if _store_singleton is None:
            _store_singleton = TargetStore()
        return _store_singleton


def set_target_store(store: Optional[TargetStore]) -> None:
    """Replace the singleton (tests / advanced embedding)."""
    global _store_singleton
    with _store_lock:
        _store_singleton = store


__all__ = [
    "ALLOWED_PLATFORMS",
    "ALLOWED_PROTOCOLS",
    "TargetProfile",
    "TargetProfileError",
    "TargetStore",
    "build_target_profile",
    "get_target_store",
    "set_target_store",
]
