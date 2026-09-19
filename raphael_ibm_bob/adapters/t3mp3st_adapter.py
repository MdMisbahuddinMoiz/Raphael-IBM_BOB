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

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

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

#: Pinned SHA-256 of the single-purpose C1A launcher. A mismatch fails
#: closed; the launcher is never executed from an unpinned copy.
LAUNCHER_SHA256 = (
    "f3af9fff319b8dc0ee96c91bf5b9e7ebde9fbccfcf9873d93fae695c5adaf303")

#: Default pinned launcher path (repository-relative, resolved by callers).
DEFAULT_LAUNCHER_PATH = os.path.join("provider", "c1a_launcher.js")
DEFAULT_NODE_PATH = "/usr/bin/node"


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


class LauncherIntegrityError(Exception):
    """The pinned launcher digest did not match (fail closed)."""


def file_sha256(path: os.PathLike | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def launcher_digest_ok(path: os.PathLike | str,
                       expected: str = LAUNCHER_SHA256) -> bool:
    try:
        return file_sha256(path) == expected
    except OSError:
        return False


def _bounded_result(state: ProviderState, handoff: ScopeHandoff,
                    *, error: str = "", truncated: bool = False,
                    orphan_possible: bool = False) -> ProviderResult:
    return ProviderResult(
        state=state,
        run_id=handoff.run_id,
        action_request_id=handoff.action_request_id,
        invocation_id=handoff.invocation_id,
        proof_session_id=handoff.proof_session_id,
        capability_id=handoff.capability_id,
        provider_id=handoff.provider_id,
        truncated=truncated,
        cancellation_acknowledged=False,
        orphan_possible=orphan_possible,
        error=error[:512],
    )


class SandboxedLauncherAdapter:
    """Runs the PINNED launcher through the bounded transport.

    This is the transport adapter for the local launcher. It is NOT
    T3MP3ST and NOT a test double. The real T3MP3ST provider is absent, so
    this adapter can only run the pinned launcher; it never fabricates a
    provider result and never claims the provider was executed.
    """

    provider_id = C1A_PROVIDER_ID
    is_real_provider = False

    def __init__(
        self,
        *,
        launcher_path: Optional[str] = None,
        expected_sha256: str = LAUNCHER_SHA256,
        node_path: str = DEFAULT_NODE_PATH,
        transport: Optional[Any] = None,
    ) -> None:
        self.launcher_path = launcher_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            DEFAULT_LAUNCHER_PATH)
        self.expected_sha256 = expected_sha256
        self.node_path = node_path
        self._transport = transport

    def invoke(self, handoff: ScopeHandoff,
               request: ActionRequest) -> ProviderResult:
        from raphael_ibm_bob.c1a_transport import BoundedTransport

        launcher = Path(self.launcher_path)
        if not launcher.is_file():
            raise ProviderUnavailableError(
                f"pinned C1A launcher not found: {launcher}")
        if not launcher_digest_ok(launcher, self.expected_sha256):
            raise LauncherIntegrityError(
                "launcher digest mismatch (fail closed)")

        node = (self.node_path if os.path.isfile(self.node_path)
                else shutil.which(self.node_path))
        if not node:
            raise ProviderUnavailableError(
                f"pinned node runtime not found: {self.node_path!r}")

        env = {
            "RAPHAEL_RUN_ID": handoff.run_id,
            "RAPHAEL_INVOCATION_ID": handoff.invocation_id,
            "RAPHAEL_PROOF_SESSION_ID": handoff.proof_session_id,
            "RAPHAEL_FIXTURE_PATH": handoff.fixture_path,
        }
        transport = self._transport or BoundedTransport(
            max_stdout_bytes=max(int(handoff.max_response_bytes), 4096) + 4096,
            max_stderr_bytes=8192)
        result = transport.execute(
            [node, str(launcher)],
            timeout_seconds=float(handoff.timeout_seconds),
            env=env,
            cwd=str(launcher.parent),
        )
        if result.timed_out or result.late_output:
            return _bounded_result(
                ProviderState.TIMEOUT, handoff,
                error="launcher transport timed out", orphan_possible=True)
        if not result.process_exited:
            return _bounded_result(
                ProviderState.UNAVAILABLE, handoff,
                error="launcher process not observed to exit",
                orphan_possible=True)
        if result.exit_code != 0:
            return _bounded_result(
                ProviderState.FAILURE, handoff,
                error=f"launcher exit code {result.exit_code}")
        if result.stdout_truncated:
            return _bounded_result(
                ProviderState.PARTIAL, handoff, truncated=True,
                error="launcher stdout truncated")
        from raphael_ibm_bob.provider_runtime import normalize_result
        return normalize_result(handoff, result.stdout_bytes)


__all__ = [
    "DEFAULT_LAUNCHER_PATH",
    "DEFAULT_NODE_PATH",
    "EXPOSED_TOOLS",
    "InertProviderDouble",
    "LAUNCHER_SHA256",
    "LauncherIntegrityError",
    "OutOfContractToolError",
    "ProviderUnavailableError",
    "SandboxedLauncherAdapter",
    "T3MP3STAdapter",
    "file_sha256",
    "launcher_digest_ok",
]
