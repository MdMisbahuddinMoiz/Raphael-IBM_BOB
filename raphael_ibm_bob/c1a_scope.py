"""raphael_ibm_bob.c1a_scope — canonical path-containment semantics.

ONE small helper reused by BOTH the Policy (C1A authorization) and the
QualityGate (Condition E scope). Having two incompatible scope definitions
was explicitly called out as a defect; this module is the single source of
truth for "is this target inside this root / scope?".

Semantics (fail closed):

    * Paths are split into components after normalising separators.
    * ``.`` components are dropped; ``..`` resolves by popping the previous
      component and is REJECTED when it would escape the accumulated root.
    * Containment is checked at COMPONENT boundaries, so a path that merely
      shares a string prefix (``/ws`` vs ``/ws-evil``, ``src`` vs ``srcx``)
      is NOT contained.
    * Empty / malformed / NUL-containing paths are rejected.
    * A relative target may be matched against a relative scope; an absolute
      target against a relative scope is matched only as a component suffix,
      which is the least-surprising behaviour for the existing mission-scope
      convention (e.g. scope ``src/`` with an absolute workspace target).

This module performs NO filesystem access.
"""
from __future__ import annotations

from typing import Tuple


class ScopePathError(ValueError):
    """The supplied path is malformed or attempts traversal escape."""


def canonical_parts(path: str) -> Tuple[bool, Tuple[str, ...]]:
    """Return ``(is_absolute, components)`` for a path-like string.

    Raises :class:`ScopePathError` for non-strings, empty strings, NUL
    bytes, and any ``..`` that escapes above the accumulated root.
    """
    if not isinstance(path, str):
        raise ScopePathError(f"path must be a string, got {type(path).__name__}")
    if path == "" or path.strip() == "":
        raise ScopePathError("path is empty")
    if "\x00" in path:
        raise ScopePathError("path contains NUL")
    normalized = path.replace("\\", "/")
    is_absolute = normalized.startswith("/")
    parts = []
    for segment in normalized.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if not parts:
                raise ScopePathError("path escapes above root via '..'")
            parts.pop()
            continue
        parts.append(segment)
    return is_absolute, tuple(parts)


def within_root(root: str, target: str) -> bool:
    """True iff ``target`` is contained in absolute ``root`` at a boundary.

    ``root`` must be absolute; a relative target is never considered
    contained in an absolute root.
    """
    try:
        root_abs, root_parts = canonical_parts(root)
        target_abs, target_parts = canonical_parts(target)
    except ScopePathError:
        return False
    if not root_abs or not root_parts:
        return False
    if not target_abs:
        return False
    if len(target_parts) < len(root_parts):
        return False
    return target_parts[:len(root_parts)] == root_parts


def scope_contains(scope: str, target: str) -> bool:
    """True iff ``target`` is within ``scope`` under canonical semantics.

    An empty/whitespace scope means "no scope constraint" (True), matching
    the existing Policy/QualityGate convention that an unset scope does not
    restrict the mission. All other inputs fail closed.

    Containment requires the scope and the target to share absoluteness
    (both absolute, or both relative) and then be a COMPONENT-boundary
    prefix. The former absolute-target/relative-scope component-SUFFIX
    fallback was removed: it admitted an unrelated absolute path
    (``/ws/evil/src/x`` under scope ``src``) and is an intra-workspace
    scope escape. Mixed absoluteness now fails closed.
    """
    if scope is None:
        return True
    if isinstance(scope, str) and scope.strip() == "":
        return True
    try:
        scope_abs, scope_parts = canonical_parts(scope)
        target_abs, target_parts = canonical_parts(target)
    except ScopePathError:
        return False
    if not scope_parts:
        return True
    if scope_abs != target_abs:
        return False
    if len(target_parts) < len(scope_parts):
        return False
    return target_parts[:len(scope_parts)] == scope_parts


__all__ = ["ScopePathError", "canonical_parts", "within_root", "scope_contains"]
