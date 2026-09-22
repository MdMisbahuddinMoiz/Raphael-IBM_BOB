"""raphael_ibm_bob.network_scope — canonical network scope semantics (D9).

ONE source of truth for "is this network target inside this authorized
scope?", shared by the Policy and the QualityGate (mirroring the
`c1a_scope` single-source-of-truth discipline for paths).

Fail-closed rules:

    * only ``http``/``https`` schemes; no userinfo, no fragment, no port 0
    * the host is canonicalised (lowercased, brackets/trailing dot
      stripped, validated as IPv4/IPv6/hostname)
    * scope matching is EXACT (host) or CIDR containment — never a string
      prefix, so ``10.129.48.95`` does not match ``10.129.48.950`` and
      ``evil-10.129.48.95`` does not match ``10.129.48.95``
    * an empty scope is NOT a blanket allow for network targets

This module performs NO network I/O.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = {"http": 80, "https": 443}
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
    r"(\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")


class NetworkScopeError(ValueError):
    """A network target or scope is malformed / out of scope."""


def canonical_host(value: object) -> str:
    """Canonicalise a host literal (brackets, case, trailing dot)."""
    if not isinstance(value, str):
        raise NetworkScopeError("host must be a string")
    host = value.strip()
    if host == "":
        raise NetworkScopeError("host is empty")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    host = host.rstrip(".").lower()
    if any(ch in host for ch in "/@?#\\ \t\r\n"):
        raise NetworkScopeError(f"host has forbidden characters: {value!r}")
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    if ":" in host:
        raise NetworkScopeError(f"host must not carry a port: {value!r}")
    if not _HOSTNAME_RE.match(host):
        raise NetworkScopeError(f"invalid hostname: {value!r}")
    return host


@dataclass(frozen=True)
class ParsedTarget:
    """A validated HTTP target derived from one URL."""
    scheme: str
    host: str
    port: int
    path: str
    url: str


def parse_http_target(url: object) -> ParsedTarget:
    """Parse and validate an http(s) URL into a canonical target.

    Rejects unsupported schemes, userinfo, fragments, and bad hosts/ports.
    """
    if not isinstance(url, str) or url.strip() == "":
        raise NetworkScopeError("target url is required")
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise NetworkScopeError(f"unsupported scheme: {scheme or 'none'}")
    if parts.username is not None or parts.password is not None:
        raise NetworkScopeError("userinfo is forbidden in the target url")
    if parts.fragment:
        raise NetworkScopeError("fragment is forbidden in the target url")
    host = canonical_host(parts.hostname or "")
    port = parts.port if parts.port is not None else _ALLOWED_SCHEMES[scheme]
    if not (1 <= port <= 65535):
        raise NetworkScopeError(f"port out of range: {port}")
    path = parts.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    return ParsedTarget(scheme=scheme, host=host, port=port, path=path,
                        url=url.strip())


def host_in_scope(scope: object, host: object) -> bool:
    """True iff ``host`` exactly matches, or is CIDR-contained by, ``scope``.

    ``scope`` is a comma-separated allow-list of host literals and/or
    CIDRs. Empty scope fails closed (no network target is allowed).
    """
    if scope is None or (isinstance(scope, str) and scope.strip() == ""):
        return False
    try:
        canonical = canonical_host(host)
    except NetworkScopeError:
        return False
    for token in str(scope).split(","):
        token = token.strip()
        if token == "":
            continue
        if "/" in token:
            try:
                network = ipaddress.ip_network(token, strict=False)
            except ValueError:
                continue
            try:
                if ipaddress.ip_address(canonical) in network:
                    return True
            except ValueError:
                continue
        else:
            try:
                if canonical_host(token) == canonical:
                    return True
            except NetworkScopeError:
                continue
    return False


def scope_contains_host(scope: object, url: object) -> bool:
    """True iff the URL's host is contained in ``scope`` (fail closed)."""
    try:
        target = parse_http_target(url)
    except NetworkScopeError:
        return False
    return host_in_scope(scope, target.host)


__all__ = [
    "NetworkScopeError",
    "ParsedTarget",
    "canonical_host",
    "host_in_scope",
    "parse_http_target",
    "scope_contains_host",
]
