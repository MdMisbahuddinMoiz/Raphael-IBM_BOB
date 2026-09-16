"""Evidence Intelligence route — read-only evidence overview.

Presentation only: aggregates the persisted append-only ledger through
`harness.api` (read-only). Never executes a capability, never touches
Broker / Policy / Runtime / QualityGate internals, never mutates
evidence, findings, or artifacts, and opens no outbound path.
"""
from __future__ import annotations

from raphael_ibm_bob.http.app import Response
from raphael_ibm_bob.http.views import evidence_intelligence as _view

HTML = "text/html; charset=utf-8"


def evidence(request, params, config):
    """GET /operations/evidence — persisted evidence across operations."""
    html_doc = _view.render_evidence(runs_root=config.runs_root,
                                     sessions_root=config.sessions_root)
    return Response(200, html_doc, content_type=HTML)


__all__ = ["evidence"]
