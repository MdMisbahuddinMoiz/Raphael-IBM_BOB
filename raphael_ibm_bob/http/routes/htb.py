"""HTB target routes — operator-declared authorized network target (D9).

Configuration only. These routes never perform network I/O; they record
the mission-bound TargetProfile that Policy and the QualityGate consult.

    GET  /htb/target         current declared target (or null)
    POST /htb/target         declare/replace the target
    POST /htb/target/clear   clear the target
"""
from __future__ import annotations

from raphael_ibm_bob.http import errors
from raphael_ibm_bob.http.routes._common import body_object
from raphael_ibm_bob.target_profile import (
    TargetProfileError,
    build_target_profile,
    get_target_store,
)


def _store(config):
    store = getattr(config, "target_store", None)
    return store if store is not None else get_target_store()


def get_target(request, params, config):
    """GET /htb/target — the currently declared target (safe dict)."""
    profile = _store(config).current()
    return {"configured": profile is not None,
            "target": profile.to_dict() if profile else None}


def set_target(request, params, config):
    """POST /htb/target — declare/replace the authorized target."""
    body = body_object(request)
    try:
        profile = build_target_profile(
            mission_id=body.get("mission_id"),
            locator=body.get("locator"),
            allowed_ports=body.get("allowed_ports"),
            allowed_protocols=body.get("allowed_protocols"),
            scope=body.get("scope"),
            authorization_ref=body.get("authorization_ref"),
            platform=body.get("platform", "htb"),
        )
    except TargetProfileError as exc:
        raise errors.invalid_input(str(exc)) from None
    _store(config).set_target(profile)
    return 201, {"configured": True, "target": profile.to_dict()}


def clear_target(request, params, config):
    """POST /htb/target/clear — remove the declared target."""
    _store(config).clear_target()
    return {"configured": False, "target": None}


__all__ = ["clear_target", "get_target", "set_target"]
