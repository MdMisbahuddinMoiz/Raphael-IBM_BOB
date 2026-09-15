"""Shared input parsing for HTTP routes (no execution authority)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from raphael_ibm_bob.contracts import Mission
from raphael_ibm_bob.http import errors

_MISSION_FIELDS = {"mission_id", "description", "scope", "criteria",
                   "problem"}


def body_object(request) -> Dict[str, Any]:
    """Return the request body as a dict (or an empty dict)."""
    body = request.body
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise errors.bad_request("request body must be a JSON object")
    return body


def mission_from_body(request) -> Optional[Mission]:
    """Build a Mission from an optional `mission` object.

    Unknown fields are rejected rather than ignored, so a typo never
    silently becomes a defaulted mission.
    """
    body = body_object(request)
    data = body.get("mission")
    if data is None:
        return None
    if not isinstance(data, dict):
        raise errors.invalid_input("mission must be an object")
    unknown = set(data) - _MISSION_FIELDS
    if unknown:
        raise errors.invalid_input(
            f"unknown mission fields: {sorted(unknown)}")
    if "mission_id" not in data:
        raise errors.invalid_input("mission.mission_id is required")
    return Mission(
        mission_id=data["mission_id"],
        description=data.get("description", ""),
        scope=data.get("scope", ""),
        criteria=list(data.get("criteria", [])),
        problem=dict(data.get("problem", {})),
    )


def required(body: Dict[str, Any], field: str) -> Any:
    value = body.get(field)
    if value in (None, ""):
        raise errors.invalid_input(f"{field} is required")
    return value


__all__ = ["body_object", "mission_from_body", "required"]
