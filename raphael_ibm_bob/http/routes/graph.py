"""Operation Graph route — read-only task/run structure view.

Presentation only: reads persisted/reconstructed run + task state via
`harness.api` (read-only). No graph store, no graph mutation, no task
controls, no execution.
"""
from __future__ import annotations

from raphael_ibm_bob.http.app import Response
from raphael_ibm_bob.http.views import operation_graph as _view

HTML = "text/html; charset=utf-8"


def graph(request, params, config):
    """GET /operations/graph[?run=<run_id>] — scoped operation graph."""
    del params
    selected = request.query_one("run")
    html_doc = _view.render_graph(runs_root=config.runs_root,
                                  sessions_root=config.sessions_root,
                                  selected_run_id=selected)
    return Response(200, html_doc, content_type=HTML)


__all__ = ["graph"]
