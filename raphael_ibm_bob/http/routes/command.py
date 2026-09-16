"""Command Center route — read-only operational overview.

Aggregates persisted, authoritative state through `harness.api` only.
Never calls a capability, the Broker, Policy, Runtime, or the
QualityGate; never writes evidence; never fabricates a value.
"""
from __future__ import annotations

from raphael_ibm_bob.http.app import Response
from raphael_ibm_bob.http.views import command_center as _view

HTML = "text/html; charset=utf-8"


def command(request, params, config):
    """GET /command — RAPHAEL Command Center."""
    html_doc = _view.render_command(runs_root=config.runs_root,
                                    sessions_root=config.sessions_root)
    return Response(200, html_doc, content_type=HTML)


__all__ = ["command"]
