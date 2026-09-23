"""D14 autonomy-loop phase vocabulary."""
from __future__ import annotations

from enum import StrEnum, unique


@unique
class AutonomyState(StrEnum):
    """A phase of the autonomy loop, never a completion verdict."""

    OBSERVE = "observe"
    UPDATE_WORLD = "update_world"
    SELECT = "select"
    REQUEST = "request"
    EXECUTE = "execute"
    VERIFY = "verify"
    FALSIFY = "falsify"
    REPLAN = "replan"
    STOP = "stop"


__all__ = ["AutonomyState"]
