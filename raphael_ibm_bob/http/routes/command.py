"""Command Center route — read-only operational overview.

Aggregates persisted, authoritative state through `harness.api` only.
Never calls a capability, the Broker, Policy, Runtime, or the
QualityGate; never writes evidence; never fabricates a value.

D8 adds a read-only product-mode panel (mode / testing environment /
VPN state); the mode itself is set on the Operations page.
"""
from __future__ import annotations

from raphael_ibm_bob.http.app import Response
from raphael_ibm_bob.http.views import command_center as _view
from raphael_ibm_bob.mode import get_mode_manager
from raphael_ibm_bob.vpn import get_vpn_manager

HTML = "text/html; charset=utf-8"


def _mode_state(config):
    try:
        manager = getattr(config, "mode_manager", None) or get_mode_manager()
        return manager.state().to_dict()
    except Exception:
        return None


def _vpn_status(config):
    try:
        manager = getattr(config, "vpn_manager", None) or get_vpn_manager()
        return manager.status()
    except Exception:
        return None


def command(request, params, config):
    """GET /command — RAPHAEL Command Center."""
    html_doc = _view.render_command(
        runs_root=config.runs_root, sessions_root=config.sessions_root,
        mode_state=_mode_state(config), vpn_status=_vpn_status(config))
    return Response(200, html_doc, content_type=HTML)


def root(request, params, config):
    """GET / — land on the Command Center (no route existed before D9)."""
    from raphael_ibm_bob.http.views.operations_console import redirect_page
    return Response(200, redirect_page("/command"), content_type=HTML)


__all__ = ["command", "root"]
