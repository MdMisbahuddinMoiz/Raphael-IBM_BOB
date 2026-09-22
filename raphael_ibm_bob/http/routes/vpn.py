"""VPN routes — controlled OpenVPN lifecycle over the existing HTTP API.

These routes are the ONLY entry point to the VPN manager. They never
execute a capability, never touch the Broker/Policy/Runtime/QualityGate,
and never construct a shell command. The manager is resolved from the
server config (tests/embedding) or the process-wide singleton.

    GET  /vpn/status       read-only, secret-free state
    POST /vpn/connect      validate profile + start OpenVPN + wait
    POST /vpn/disconnect   terminate + clean up (idempotent)
"""
from __future__ import annotations

from raphael_ibm_bob.http import errors
from raphael_ibm_bob.http.errors import ApiError
from raphael_ibm_bob.http.routes._common import body_object
from raphael_ibm_bob.vpn import VPNError, get_vpn_manager


def _manager(config):
    manager = getattr(config, "vpn_manager", None)
    return manager if manager is not None else get_vpn_manager()


def _vpn_error(exc: VPNError) -> ApiError:
    return ApiError(exc.status, exc.code, exc.message)


def status(request, params, config):
    """GET /vpn/status — safe connection state."""
    return _manager(config).status()


def connect(request, params, config):
    """POST /vpn/connect — profile in the body, contents only."""
    body = body_object(request)
    profile = body.get("profile")
    if not isinstance(profile, str) or not profile.strip():
        raise errors.invalid_input(
            "profile is required (the .ovpn file contents as text)")
    profile_name = body.get("profile_name", "profile.ovpn")
    try:
        result = _manager(config).connect(profile, profile_name)
    except VPNError as exc:
        raise _vpn_error(exc) from None
    return 201, result


def disconnect(request, params, config):
    """POST /vpn/disconnect — terminate and clean up."""
    try:
        result = _manager(config).disconnect()
    except VPNError as exc:
        raise _vpn_error(exc) from None
    return 200, result


__all__ = ["connect", "disconnect", "status"]
