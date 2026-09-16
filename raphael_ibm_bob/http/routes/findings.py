"""Findings Intelligence route — read-only findings overview.

Presentation only: aggregates persisted findings through `harness.api`
(read-only). Never executes a capability, never touches Broker / Policy /
Runtime / QualityGate internals, never mutates a finding or evidence.
"""
from __future__ import annotations

from raphael_ibm_bob.http.app import Response
from raphael_ibm_bob.http.views import findings_intelligence as _view

HTML = "text/html; charset=utf-8"


def findings(request, params, config):
    """GET /operations/findings — persisted findings across operations."""
    html_doc = _view.render_findings(runs_root=config.runs_root,
                                     sessions_root=config.sessions_root)
    return Response(200, html_doc, content_type=HTML)


__all__ = ["findings"]
