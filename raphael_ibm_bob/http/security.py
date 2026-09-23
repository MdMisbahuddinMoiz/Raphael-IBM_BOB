"""raphael_ibm_bob.http.security — HTTP boundary hardening (G7/H-4/H-5/M-12/M-14).

Presentation-layer guards only. This module holds no execution authority:
it validates untrusted HTTP input (resource IDs, Host/Origin/Referer,
bind configuration) and scrubs filesystem paths from error messages.
It never calls the Broker, Policy, Runtime, QualityGate, or ledger.

Model (documented for operators):

* Bind: a non-loopback bind without a configured API key is refused.
  Loopback (`127.0.0.1`, `localhost`, `::1`) keeps working with no key.
* Host: on a loopback-bound server the `Host` header must name loopback
  (or the configured host); anything else is rejected. This blunts
  DNS-rebinding against the browser control surface.
* Origin/CSRF: state-changing requests (POST) carrying an `Origin` (or,
  failing that, a `Referer`) must prove same-origin against `Host`.
  Requests with neither header are non-browser clients (curl, tests,
  server-side callers) and are allowed through — plain same-origin HTML
  form posts always carry one of the two, so the existing UI satisfies
  the check with no token or markup change. `Origin: null`/empty/foreign
  is rejected.
* Resource IDs: `session_id`/`run_id` match a strict allowlist and must
  resolve under their configured root; `task_id` uses a wider (colon- and
  space-tolerant) strict character set with the same containment rule;
  `workspace_id` (a URL-encoded path) must be free of `..` segments, null
  bytes and control characters and is length-bounded. Anything else is
  rejected at the HTTP boundary before the Harness is touched.
* Errors: configured `sessions_root`/`runs_root` absolute paths are
  scrubbed from error messages before they reach the client.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional, Tuple

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

#: Strict allowlist for session/run identifiers (uuid hex, timestamped
#: run ids such as `20260101T000000_abc123`). Must start alnum (kills
#: `.`/`..`/absolute paths outright); no slashes, backslashes, `%`,
#: whitespace, or control characters — so single-, double- and
#: URL-encoded traversal residues cannot match.
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

#: Task identifiers embed `mission_id::name`, so `:` (plus space/`+` for
#: operator-chosen mission ids) is tolerated. Still no `/`, `\`, `%`,
#: null/control characters, and still starts alnum.
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+~ +-]{0,255}$")

MAX_WORKSPACE_ID_CHARS = 1024

#: Query cursor bound for SSE resume (`?after=` / `Last-Event-ID`).
MAX_CURSOR = 1_000_000_000


# -----------------------------------------------------------------------------
# Resource-ID boundary
# -----------------------------------------------------------------------------

def _has_control_chars(value: str) -> bool:
    return any(ord(c) < 0x20 or ord(c) == 0x7F for c in value)


def check_resource_id(value: object, kind: str) -> str:
    """Validate a `session_id`/`run_id`/`task_id` path parameter.

    Returns the value unchanged when valid; raises `ValueError` with a
    path-free message otherwise. `kind` is one of
    `"session_id"`, `"run_id"`, `"task_id"`.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid {kind}")
    if _has_control_chars(value) or "\x00" in value:
        raise ValueError(f"invalid {kind}")
    if "%" in value or "\\" in value:
        # A decoded value still containing `%` is a double-encoding
        # residue (`%252e` -> `%2e`); backslashes are Windows traversal.
        raise ValueError(f"invalid {kind}")
    pattern = _TASK_ID_RE if kind == "task_id" else _ID_RE
    if not pattern.match(value):
        raise ValueError(f"invalid {kind}")
    if value in (".", "..") or value.startswith(".."):
        raise ValueError(f"invalid {kind}")
    return value


def check_workspace_id(value: object) -> str:
    """Validate the URL-decoded `workspace_id` path parameter.

    Workspaces are operator-chosen absolute paths, so a filename
    allowlist cannot apply; instead reject null bytes, control
    characters, `..` segments (on either separator), and oversize input.
    """
    if not isinstance(value, str) or not value:
        raise ValueError("invalid workspace_id")
    if len(value) > MAX_WORKSPACE_ID_CHARS:
        raise ValueError("invalid workspace_id")
    if "\x00" in value or _has_control_chars(value):
        raise ValueError("invalid workspace_id")
    if "%" in value:
        raise ValueError("invalid workspace_id")
    normalized = value.replace("\\", "/")
    if any(segment == ".." for segment in normalized.split("/")):
        raise ValueError("invalid workspace_id")
    return value


def contained_path(root: Path, name: str) -> Path:
    """Resolve `root / name` and require containment under `root`.

    Raises `ValueError` (path-free message) on escape. With the
    allowlists above `name` carries no separator, so this is normally
    trivially true — it is belt-and-braces against future loosening.
    """
    base = Path(root)
    try:
        base_resolved = base.resolve()
    except OSError:
        base_resolved = base.absolute()
    candidate = base / name
    try:
        resolved = candidate.resolve()
    except OSError:
        raise ValueError("invalid resource identifier")
    if resolved != base_resolved and base_resolved not in resolved.parents:
        raise ValueError("invalid resource identifier")
    return resolved


def check_path_params(params: Dict[str, str], config) -> None:
    """Validate every resource-ID path param and its root containment."""
    for key, value in params.items():
        if key == "session_id":
            check_resource_id(value, "session_id")
            contained_path(config.sessions_root, value)
        elif key == "run_id":
            check_resource_id(value, "run_id")
            contained_path(config.runs_root, value)
        elif key == "task_id":
            check_resource_id(value, "task_id")
        elif key == "workspace_id":
            check_workspace_id(value)


def check_body_id(body: object, field: str, kind: str) -> None:
    """Validate an ID supplied inside a JSON/form body (when present)."""
    if not isinstance(body, dict):
        return
    value = body.get(field)
    if value in (None, ""):
        return
    if kind == "workspace_id":
        check_workspace_id(value)
    else:
        check_resource_id(value, kind)


# -----------------------------------------------------------------------------
# Bind / Host / Origin
# -----------------------------------------------------------------------------

def is_loopback_host(host: str) -> bool:
    return host in LOOPBACK_HOSTS


def ensure_bind_allowed(config) -> None:
    """Refuse a non-loopback bind without a configured API key.

    Raises `RuntimeError` (never logs the key). Loopback binds always
    pass, so the default developer flow is unaffected.
    """
    if config.host not in LOOPBACK_HOSTS and not getattr(
            config, "api_key", None):
        raise RuntimeError(
            "refusing to bind non-loopback host "
            f"{config.host!r} without RAPHAEL_API_KEY configured; "
            "set RAPHAEL_API_KEY or bind loopback "
            "(127.0.0.1/localhost/::1)")


def _split_host(raw: str) -> Tuple[str, Optional[str]]:
    """Split a `Host` header into (hostname, port-or-None).

    Handles `host:port`, bare hosts, and bracketed IPv6 (`[::1]:8787`).
    """
    text = (raw or "").strip().lower()
    if not text:
        return "", None
    if text.startswith("["):
        end = text.find("]")
        if end == -1:
            return text, None
        hostname = text[1:end]
        rest = text[end + 1:]
        port = rest[1:] if rest.startswith(":") else None
        return hostname, (port or None)
    if text.count(":") == 1:
        hostname, _, port = text.partition(":")
        return hostname, (port or None)
    return text, None


def check_host(headers: Dict[str, str], config) -> None:
    """Reject foreign `Host` headers (DNS-rebinding guard).

    Skipped when no `Host` header is present (in-process dispatch
    callers). On a loopback-bound server only loopback (or the
    configured host itself) is accepted. On an all-interfaces bind the
    API key is mandatory anyway (see `ensure_bind_allowed`), so any
    syntactically valid Host is accepted there and auth protects the
    surface.
    """
    raw = headers.get("host")
    if raw in (None, ""):
        return
    hostname, _ = _split_host(raw)
    if not hostname:
        raise ValueError("invalid Host header")
    bound = str(getattr(config, "host", "") or "").lower()
    if bound in ("0.0.0.0", "::", ""):
        return  # auth (mandatory here) protects the surface instead
    allowed = set(LOOPBACK_HOSTS) | ({bound} if bound else set())
    if hostname not in allowed:
        raise ValueError("invalid Host header")


def _origin_parts(raw: str) -> Optional[Tuple[str, Optional[str]]]:
    """Parse an Origin/Referer value into (hostname, port-or-None)."""
    text = (raw or "").strip()
    if not text or text == "null":
        return None
    if "://" in text:
        _, _, rest = text.partition("://")
    else:
        rest = text
    rest = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if not rest:
        return None
    hostname, port = _split_host(rest)
    if not hostname:
        return None
    return hostname, port


def _same_origin(candidate: str, host_header: Optional[str],
                 config) -> bool:
    """True when `candidate` (Origin/Referer) matches the request Host."""
    parts = _origin_parts(candidate)
    if parts is None:
        return False
    origin_host, origin_port = parts
    if host_header:
        request_host, request_port = _split_host(host_header)
        if not request_host or origin_host != request_host:
            return False
        if origin_port and request_port and origin_port != request_port:
            return False
        return True
    bound = str(getattr(config, "host", "") or "").lower()
    allowed = set(LOOPBACK_HOSTS) | ({bound} if bound else set())
    return origin_host in allowed


def check_csrf(headers: Dict[str, str], config) -> None:
    """Strict Origin/Referer same-origin check for state-changing calls.

    * `Origin` present (even empty/`null`/foreign) → must be same-origin
      against `Host`, else rejected.
    * Else `Referer` present → same rule.
    * Else neither → non-browser client (curl/tests/server-side); allowed.

    Same-origin browser form posts and `fetch` calls always carry one of
    the two, so the existing server-rendered UI satisfies this with no
    token or markup change, while a cross-site form/fetch from an
    attacker origin (which the browser labels with the foreign Origin)
    is rejected.
    """
    origin_present = "origin" in headers
    referer_present = "referer" in headers
    if origin_present:
        if _same_origin(headers.get("origin") or "", headers.get("host"),
                        config):
            return
        raise ValueError("invalid Origin for state-changing request")
    if referer_present:
        if _same_origin(headers.get("referer") or "", headers.get("host"),
                        config):
            return
        raise ValueError("invalid Referer for state-changing request")
    return


def clamp_cursor(value: object) -> int:
    """Bound an SSE resume cursor to `[0, MAX_CURSOR]` (ints only)."""
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(0, min(number, MAX_CURSOR))


# -----------------------------------------------------------------------------
# Error scrubbing
# -----------------------------------------------------------------------------

def scrub_paths(message: str, config) -> str:
    """Remove configured-root absolute paths from an error message."""
    text = str(message or "")
    if not text:
        return text
    for attr, placeholder in (("sessions_root", "<sessions-root>"),
                              ("runs_root", "<runs-root>")):
        root = getattr(config, attr, None)
        if root is None:
            continue
        for variant in (str(root), str(Path(root).absolute())):
            if variant and variant not in (".", "") and variant in text:
                text = text.replace(variant, placeholder)
        try:
            resolved = str(Path(root).resolve())
        except OSError:
            resolved = ""
        if resolved and resolved not in (".", "") and resolved in text:
            text = text.replace(resolved, placeholder)
    return text


__all__ = [
    "MAX_CURSOR",
    "MAX_WORKSPACE_ID_CHARS",
    "check_body_id",
    "check_csrf",
    "check_host",
    "check_path_params",
    "check_resource_id",
    "check_workspace_id",
    "clamp_cursor",
    "contained_path",
    "ensure_bind_allowed",
    "is_loopback_host",
    "scrub_paths",
]
