"""raphael_ibm_bob.http — HTTP/JSON presentation layer for the Harness.

Dependency direction is strictly one-way:

    HTTP  ->  harness.api  ->  existing Harness  ->  RAPHAEL core

The core never imports this package. The layer is presentation /
integration only: it exposes sessions, runs, inspection, workspace
views, M14 discovery, and task state over HTTP, but it holds no
execution authority and no second model loop.

Server = Python standard library `http.server`; no new dependencies.
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "HarnessRequestHandler",
    "HarnessHTTPServer",
    "RaphaelHTTPConfig",
    "Request",
    "Response",
    "Router",
    "build_router",
    "config_from_env",
    "create_server",
    "dispatch",
    "error_response",
    "main",
    "serve",
]


def __getattr__(name: str) -> Any:
    """Lazily re-export the app surface (keeps imports cycle-free)."""
    if name in __all__:
        from raphael_ibm_bob.http import app
        return getattr(app, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
