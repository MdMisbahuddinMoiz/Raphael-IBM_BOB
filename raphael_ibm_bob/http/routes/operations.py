"""Operator screens — read-only HTML presentation over harness.api.

These routes render HTML views from the SAME authoritative data the
JSON endpoints expose. They hold no execution authority: they call
`harness.api`, build a string, and return it. No capability is invoked,
no evidence is written, no verdict is produced.
"""
from __future__ import annotations

from raphael_ibm_bob.harness import api
from raphael_ibm_bob.http.app import Response
from raphael_ibm_bob.http.views import decision_trace as _view

HTML = "text/html; charset=utf-8"


def decision_trace(request, params, config):
    """GET /operations/{run_id}/decision-trace — read-only operator view."""
    html_doc = _view.render_decision_trace(
        params["run_id"], runs_root=config.runs_root,
        sessions_root=config.sessions_root)
    return Response(200, html_doc, content_type=HTML)


__all__ = ["decision_trace"]
