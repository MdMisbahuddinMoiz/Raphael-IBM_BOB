"""raphael_ibm_bob.mode — product-level mode + testing profile (D8).

Two independent dimensions must never be conflated:

    Product / environment mode   NORMAL | TESTING          (this module)
    Testing profile              HTB                        (this module)
    Execution mode               RUNNER | MODEL             (harness/run, untouched)

Testing Mode is CONFIGURATION STATE ONLY. Selecting ``TESTING -> HTB``
never starts OpenVPN, a scan, a subprocess, or any network activity; the
operator must still connect the VPN explicitly (D7).

State is process-local, matching the existing BOB HTTP presentation
layer (which has no per-user/browser session). It is NOT persisted: a
server restart returns to ``NORMAL``. No database, no second session
store, and no change to ``contracts.Mission``.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class Mode(str, Enum):
    """Product / environment mode."""

    NORMAL = "normal"
    TESTING = "testing"


class TestingProfile(str, Enum):
    """A testing environment profile (extensible; HTB is the first)."""

    HTB = "htb"


class ModeError(ValueError):
    """Invalid mode transition (safe message; never secret)."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_mode(value: Any) -> Mode:
    if isinstance(value, Mode):
        return value
    if isinstance(value, str):
        try:
            return Mode(value.strip().lower())
        except ValueError:
            pass
    raise ModeError(
        f"unknown mode: {value!r} (expected one of "
        f"{[m.value for m in Mode]})")


def _coerce_profile(value: Any) -> TestingProfile:
    if isinstance(value, TestingProfile):
        return value
    if isinstance(value, str):
        try:
            return TestingProfile(value.strip().lower())
        except ValueError:
            pass
    raise ModeError(
        f"unknown testing profile: {value!r} (expected one of "
        f"{[p.value for p in TestingProfile]})")


@dataclass(frozen=True)
class ModeState:
    """Immutable snapshot of the current product mode."""

    mode: Mode = Mode.NORMAL
    testing_profile: Optional[TestingProfile] = None
    updated_at: str = field(default_factory=_utcnow)

    @property
    def is_testing(self) -> bool:
        return self.mode is Mode.TESTING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "testing_profile": (self.testing_profile.value
                                if self.testing_profile else None),
            "updated_at": self.updated_at,
        }


class ModeManager:
    """Process-local owner of the current :class:`ModeState`."""

    def __init__(self, initial: Optional[ModeState] = None) -> None:
        self._lock = threading.Lock()
        self._state = initial or ModeState()

    def state(self) -> ModeState:
        with self._lock:
            return self._state

    def set(self, mode: Any,
            testing_profile: Any = None) -> ModeState:
        """Set the product mode, validating the profile pairing.

        ``TESTING`` requires a testing profile; ``NORMAL`` clears it, so
        stale HTB state can never leak into NORMAL mode.
        """
        resolved = _coerce_mode(mode)
        if resolved is Mode.NORMAL:
            profile: Optional[TestingProfile] = None
        else:
            if testing_profile in (None, ""):
                raise ModeError(
                    "a testing profile is required for TESTING mode")
            profile = _coerce_profile(testing_profile)
        with self._lock:
            self._state = ModeState(mode=resolved, testing_profile=profile)
            return self._state


_mode_singleton: Optional[ModeManager] = None
_mode_lock = threading.Lock()


def get_mode_manager() -> ModeManager:
    """Return the process-wide mode manager."""
    global _mode_singleton
    with _mode_lock:
        if _mode_singleton is None:
            _mode_singleton = ModeManager()
        return _mode_singleton


def set_mode_manager(manager: Optional[ModeManager]) -> None:
    """Replace the singleton (tests / advanced embedding)."""
    global _mode_singleton
    with _mode_lock:
        _mode_singleton = manager


__all__ = [
    "Mode",
    "ModeError",
    "ModeManager",
    "ModeState",
    "TestingProfile",
    "get_mode_manager",
    "set_mode_manager",
]
