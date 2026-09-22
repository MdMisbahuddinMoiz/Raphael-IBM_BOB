"""Mode routes — product mode + testing profile over the existing HTTP API.

Configuration only. These routes never start OpenVPN, a scan, a
subprocess, or any network activity; they only record the operator's
declared mode.

    GET  /mode    current product mode + testing profile
    POST /mode    set mode (and testing profile for TESTING)
"""
from __future__ import annotations

from raphael_ibm_bob.http import errors
from raphael_ibm_bob.http.routes._common import body_object
from raphael_ibm_bob.mode import ModeError, get_mode_manager


def _manager(config):
    manager = getattr(config, "mode_manager", None)
    return manager if manager is not None else get_mode_manager()


def get_mode(request, params, config):
    """GET /mode — current product mode."""
    return _manager(config).state().to_dict()


def set_mode(request, params, config):
    """POST /mode — set product mode (+ testing profile for TESTING)."""
    body = body_object(request)
    try:
        state = _manager(config).set(
            body.get("mode"), body.get("testing_profile"))
    except ModeError as exc:
        raise errors.invalid_input(str(exc)) from None
    return 200, state.to_dict()


__all__ = ["get_mode", "set_mode"]
