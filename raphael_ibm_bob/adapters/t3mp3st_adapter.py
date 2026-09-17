"""raphael_ibm_bob.adapters.t3mp3st_adapter — Phase 2C C1A adapter.

Contract for the single authorized provider boundary:
``static_file_inspect`` → T3MP3ST ``binary_sink_scan``.

Availability reality (recorded honestly): the **pinned T3MP3ST provider is
not present in this workspace** (no ``src/server.ts`` / ``binary.ts`` /
``arsenal`` and no container substrate). This module therefore implements
the adapter *contract and its fail-closed refusal path*; it never
fabricates a provider response, never spawns a subprocess, and never
opens a network path. The live proof is BLOCKED until the pinned
provider and the isolation substrate exist.

The adapter exposes EXACTLY ONE tool — ``binary_sink_scan``. Every other
tool, catalog adapter, EXTERNAL_TOOL, or generic Arsenal dispatch is
out of contract and refused.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from raphael_ibm_bob.contracts import ActionRequest
from raphael_ibm_bob.provider_runtime import (
    C1A_PROVIDER_ID,
    C1A_TOOL,
    ProviderResult,
    ProviderState,
    ScopeHandoff,
)

#: The only tool this adapter may expose.
EXPOSED_TOOLS: Tuple[str, ...] = (C1A_TOOL,)


class ProviderUnavailableError(Exception):
    """The pinned provider / isolation substrate is not available."""


class OutOfContractToolError(Exception):
    """A tool/capability outside the single authorized C1A contract."""


class T3MP3STAdapter:
    """Out-of-process T3MP3ST boundary for ``binary_sink_scan`` only.

    In this workspace the provider is absent, so `invoke` fails closed
    with `ProviderUnavailableError`. When the pinned provider + isolation
    substrate are provisioned (and all Phase 2C preconditions are green),
    this class is the single place the out-of-process transport is added.
    """

    provider_id = C1A_PROVIDER_ID

    def __init__(self, *, source_root: str = "",
                 endpoint: str = "") -> None:
        # Configuration is accepted but unused until the provider exists.
        self.source_root = source_root
        self.endpoint = endpoint

    @staticmethod
    def exposed_tools() -> Tuple[str, ...]:
        """The closed tool set — never broadened implicitly."""
        return EXPOSED_TOOLS

    def _assert_in_contract(self, tool: str) -> None:
        if tool not in EXPOSED_TOOLS:
            raise OutOfContractToolError(
                f"tool {tool!r} is outside the C1A contract")

    def invoke(self, handoff: ScopeHandoff,
               request: ActionRequest) -> ProviderResult:
        """Refuse honestly: the pinned provider is not available here."""
        self._assert_in_contract(C1A_TOOL)
        raise ProviderUnavailableError(
            "pinned T3MP3ST provider not present in this workspace; "
            "live C1A proof requires the vetted provider clone and the "
            "network-denied isolation substrate")


class InertProviderDouble:
    """A LOCAL, clearly-labelled test double — NOT a provider.

    Produces a bounded, schema-valid C1A payload referencing the exact
    fixture literal, with NO authority fields. Used only by unit tests to
    exercise normalization / B4 wiring without any provider execution.
    """

    provider_id = C1A_PROVIDER_ID
    is_test_double = True

    def __init__(self, *, result_hash: str = "test-hash",
                 extra: Dict[str, Any] | None = None,
                 message: str = "inert test double") -> None:
        self._result_hash = result_hash
        self._extra = dict(extra or {})
        self._message = message
        self.calls = 0

    def invoke(self, handoff: ScopeHandoff,
               request: ActionRequest) -> ProviderResult:
        self.calls += 1
        payload: Dict[str, Any] = {
            "results": [{"path": handoff.fixture_path,
                         "kind": "binary_sink_match", "offset": 0}],
            "artifacts": [],
            "operation_id": "test-op-1",
            "result_hash": self._result_hash,
            "provider_message": self._message,
        }
        payload.update(self._extra)
        raw = json.dumps(payload).encode("utf-8")
        # Reuse the real closed parser/normalizer (M4/M6/M7).
        from raphael_ibm_bob.provider_runtime import normalize_result
        return normalize_result(handoff, raw)


__all__ = [
    "EXPOSED_TOOLS",
    "InertProviderDouble",
    "OutOfContractToolError",
    "ProviderUnavailableError",
    "T3MP3STAdapter",
]
