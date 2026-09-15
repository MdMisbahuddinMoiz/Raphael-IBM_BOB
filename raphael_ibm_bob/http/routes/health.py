"""GET /health — liveness probe (deterministic, reveals nothing)."""
from __future__ import annotations


def health(request, params, config):
    return {"status": "ok", "service": "raphael-harness"}


__all__ = ["health"]
