"""Capability Arsenal route — read-only declaration catalog.

Presentation only: reads the authoritative capability/skill/role
declarations through `harness.api` (read-only). Declarations grant no
execution authority; this route cannot execute, authorize, enable,
disable, or mutate anything.
"""
from __future__ import annotations

from raphael_ibm_bob.http.app import Response
from raphael_ibm_bob.http.views import capability_arsenal as _view

HTML = "text/html; charset=utf-8"


def capabilities(request, params, config):
    """GET /operations/capabilities — declared capabilities/skills/roles."""
    del params, config
    return Response(200, _view.render_arsenal(), content_type=HTML)


__all__ = ["capabilities"]
