"""Policy & Quality Gate route — read-only governance overview.

Presentation only: aggregates persisted policy decisions and the
authoritative QualityGate record through `harness.api` (read-only).
Never executes a capability, never touches Broker / Policy / Runtime /
QualityGate internals, never recomputes a verdict, never mutates
anything.
"""
from __future__ import annotations

from raphael_ibm_bob.http.app import Response
from raphael_ibm_bob.http.views import gate_intelligence as _view

HTML = "text/html; charset=utf-8"


def gate(request, params, config):
    """GET /operations/gate — persisted policy + authoritative gate state."""
    html_doc = _view.render_gate(runs_root=config.runs_root,
                                 sessions_root=config.sessions_root)
    return Response(200, html_doc, content_type=HTML)


__all__ = ["gate"]
