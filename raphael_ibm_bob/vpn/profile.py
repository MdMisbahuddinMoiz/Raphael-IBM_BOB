"""raphael_ibm_bob.vpn.profile — OpenVPN profile validation.

An operator-supplied ``.ovpn`` file is CONFIGURATION DATA, never a
program. This module bounds encoding/size and rejects directives that
would let a profile run an external program, hook, or script on the
host. It never logs or returns the profile contents.

D7 scope: authorized lab profiles (Hack The Box style) that carry inline
``ca``/``cert``/``key``/``tls-auth``/``tls-crypt`` blocks and ordinary
client directives. A profile that genuinely needs script hooks is out of
scope for this MVP and fails closed.
"""
from __future__ import annotations

import re
from typing import Tuple

#: Hard bound on accepted profile size (bytes).
MAX_PROFILE_BYTES = 64 * 1024

#: Inline blocks that are pure configuration data and may appear.
_ALLOWED_BLOCKS = frozenset({
    "ca", "cert", "key", "dh", "tls-auth", "tls-crypt", "tls-crypt-v2",
    "extra-certs", "secret",
})

#: Directives that would enable external program/script execution,
#: arbitrary file redirection, privilege changes, or interactive prompts.
_FORBIDDEN_DIRECTIVES = frozenset({
    # program / script hooks
    "up", "down", "route-up", "route-pre-down", "iproute",
    "iproute-pre-down", "client-connect", "client-disconnect",
    "learn-address", "auth-user-pass-verify", "tls-verify",
    "tls-export-cert", "plugin", "script-security",
    "client-crresponse", "crl-verify",
    # file / process control we own ourselves
    "config", "log", "log-append", "status", "writepid", "cd", "chroot",
    "daemon", "user", "group", "chroot",
    # interactive credential prompt (would hang a headless process)
    "auth-user-pass", "askpass",
})

_DIRECTIVE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_.-]*)")
_BLOCK_OPEN_RE = re.compile(r"^<([A-Za-z0-9_-]+)>\s*$")
_BLOCK_CLOSE_RE = re.compile(r"^</([A-Za-z0-9_-]+)>\s*$")


class ProfileError(ValueError):
    """The supplied profile is not acceptable configuration."""


def _too_big(text: str) -> bool:
    try:
        return len(text.encode("utf-8", "ignore")) > MAX_PROFILE_BYTES
    except Exception:
        return True


def validate_profile(text: object) -> str:
    """Validate a profile and return it unchanged.

    Raises :class:`ProfileError` with a safe message (never the profile
    contents) when the input is not acceptable.
    """
    if not isinstance(text, str):
        raise ProfileError("profile must be text")
    if not text.strip():
        raise ProfileError("profile is empty")
    if _too_big(text):
        raise ProfileError(
            f"profile exceeds {MAX_PROFILE_BYTES} bytes")

    block: Tuple[str, int] | None = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if block is not None:
            close = _BLOCK_CLOSE_RE.match(line)
            if close and close.group(1).lower() == block[0]:
                block = None
            continue
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        opening = _BLOCK_OPEN_RE.match(line)
        if opening:
            name = opening.group(1).lower()
            if name not in _ALLOWED_BLOCKS:
                raise ProfileError(
                    f"profile uses an unsupported inline block: {name}")
            block = (name, lineno)
            continue
        if _BLOCK_CLOSE_RE.match(line):
            continue
        directive = _DIRECTIVE_RE.match(line)
        if not directive:
            continue
        name = directive.group(1).lower()
        if name in _FORBIDDEN_DIRECTIVES:
            raise ProfileError(
                f"profile uses a disallowed directive: {name}")
    if block is not None:
        raise ProfileError(
            f"profile has an unterminated <{block[0]}> block")
    return text


__all__ = ["MAX_PROFILE_BYTES", "ProfileError", "validate_profile"]
