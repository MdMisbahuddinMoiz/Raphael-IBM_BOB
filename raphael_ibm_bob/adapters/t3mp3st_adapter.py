"""raphael_ibm_bob.adapters.t3mp3st_adapter — Phase 2C C1A adapter.

Contract for the single authorized provider boundary:
``static_file_inspect`` → T3MP3ST ``binary_sink_scan``.

Two execution adapters exist here, and the distinction is explicit:

    * :class:`T3MP3STAdapter` — the REAL provider. When a compiled pinned
      T3MP3ST checkout is supplied (``provider_dist``) it runs the
      RAPHAEL-owned bridge inside the bwrap sandbox via the canonical path

          RAPHAEL -> bwrap -> bridge -> binarySinkScanTool.handler()

      When no provider is supplied it fails closed with
      ``ProviderUnavailableError``. It never fabricates a provider result.

    * :class:`InertProviderDouble` — LOCAL test infrastructure, never a
      provider, never called "T3MP3ST".

The provider source is mounted read-only and is NEVER modified. Provider
output is UNTRUSTED: the bridge excludes T3MP3ST's ``findings`` array
(severity/cwe/title/details) and RAPHAEL's closed schema independently
rejects any authority field.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
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

#: Pinned SHA-256 of the RAPHAEL-owned T3MP3ST bridge.
T3MP3ST_BRIDGE_SHA256 = (
    "ea5616e1515004fe2fed344eb6787ed29d57a6040e0290ad3069321799056101")

#: Default pinned launcher path (repository-relative, resolved by callers).
DEFAULT_LAUNCHER_PATH = os.path.join("provider", "c1a_launcher.js")
DEFAULT_BRIDGE_PATH = os.path.join("provider", "t3mp3st_bridge.js")
DEFAULT_NODE_PATH = "/usr/bin/node"

#: Minimum Node runtime required by T3MP3ST.
MIN_NODE_VERSION = (22, 19, 0)


class ProviderUnavailableError(Exception):
    """The pinned provider / isolation substrate is not available."""


class OutOfContractToolError(Exception):
    """A tool/capability outside the single authorized C1A contract."""


class ProviderIntegrityError(Exception):
    """A provider/bridge/Node integrity precondition failed (fail closed)."""


class T3MP3STAdapter:
    """Real out-of-process T3MP3ST boundary for ``binary_sink_scan`` only.

    When a compiled pinned provider checkout (``provider_dist``) is supplied,
    :meth:`invoke` runs the RAPHAEL-owned bridge inside the bwrap sandbox via
    the canonical path ``bwrap -> bridge -> binarySinkScanTool.handler()``.
    When it is not, :meth:`invoke` fails closed with
    ``ProviderUnavailableError``; it never fabricates a provider result.

    The provider source is mounted read-only and never modified.
    """

    provider_id = C1A_PROVIDER_ID
    is_real_provider = True

    def __init__(
        self,
        *,
        provider_dist: str = "",
        bridge_path: str = "",
        bridge_sha256: str = T3MP3ST_BRIDGE_SHA256,
        node_path: str = DEFAULT_NODE_PATH,
        transport: Optional[Any] = None,
        source_root: str = "",
        endpoint: str = "",
    ) -> None:
        self.provider_dist = provider_dist
        self.bridge_path = bridge_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            DEFAULT_BRIDGE_PATH)
        self.bridge_sha256 = bridge_sha256
        self.node_path = node_path
        self._transport = transport
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

    def available(self) -> bool:
        """True iff a compiled provider checkout is configured."""
        return bool(self.provider_dist) and os.path.isdir(self.provider_dist)

    def invoke(self, handoff: ScopeHandoff,
               request: ActionRequest) -> ProviderResult:
        """Execute binary_sink_scan through the real sandboxed provider.

        Fails closed (``ProviderUnavailableError``) when no provider is
        configured; fails closed (``ProviderIntegrityError``) on a Node
        version, bridge digest, or provider-dist precondition failure.
        T3MP3ST output is UNTRUSTED and is normalized by RAPHAEL's closed
        schema; the bridge already excludes authority fields.
        """
        self._assert_in_contract(C1A_TOOL)
        if not self.available():
            raise ProviderUnavailableError(
                "pinned T3MP3ST provider not present; live C1A proof "
                "requires the vetted provider clone (provider_dist) and the "
                "network-denied isolation substrate")

        from raphael_ibm_bob.c1a_transport import BoundedTransport
        from raphael_ibm_bob.isolation_substrate import (
            SubstrateConfigError,
            build_t3mp3st_bwrap_argv,
            node_version_ok,
        )

        node = (self.node_path if os.path.isfile(self.node_path)
                else shutil.which(self.node_path))
        if not node:
            raise ProviderIntegrityError(
                f"pinned node runtime not found: {self.node_path!r}")
        try:
            version_text = subprocess.run(
                [node, "--version"], capture_output=True, text=True,
                timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProviderIntegrityError(
                f"node version probe failed: {type(exc).__name__}") from None
        if not node_version_ok(version_text, MIN_NODE_VERSION):
            raise ProviderIntegrityError(
                f"node {version_text!r} does not meet T3MP3ST minimum "
                f"v{'.'.join(str(n) for n in MIN_NODE_VERSION)}")

        try:
            argv = build_t3mp3st_bwrap_argv(
                provider_dist=os.path.realpath(self.provider_dist),
                bridge_path=os.path.realpath(self.bridge_path),
                fixture_path=handoff.fixture_path,
                bridge_sha256=self.bridge_sha256,
                run_id=handoff.run_id,
                invocation_id=handoff.invocation_id,
                node_runtime=node,
            )
        except SubstrateConfigError as exc:
            raise ProviderIntegrityError(str(exc)) from None

        transport = self._transport or BoundedTransport(
            max_stdout_bytes=max(int(handoff.max_response_bytes), 4096) + 4096,
            max_stderr_bytes=8192)
        result = transport.execute(
            list(argv),
            timeout_seconds=float(handoff.timeout_seconds),
            env={},
        )
        if result.timed_out or result.late_output:
            return _bounded_result(
                ProviderState.TIMEOUT, handoff,
                error="t3mp3st sandbox timed out", orphan_possible=True)
        if not result.process_exited:
            return _bounded_result(
                ProviderState.UNAVAILABLE, handoff,
                error="t3mp3st sandbox process not observed to exit",
                orphan_possible=True)
        if result.exit_code != 0:
            return _bounded_result(
                ProviderState.FAILURE, handoff,
                error=f"t3mp3st bridge exit code {result.exit_code}")
        if result.stdout_truncated:
            return _bounded_result(
                ProviderState.PARTIAL, handoff, truncated=True,
                error="t3mp3st bridge stdout truncated")
        return self._normalize_bridge_receipt(handoff, result.stdout_bytes)

    @staticmethod
    def _normalize_bridge_receipt(handoff: ScopeHandoff,
                                  raw: bytes) -> ProviderResult:
        """Translate the bridge receipt into a RAPHAEL ProviderResult.

        The bridge emits only ``success``/``output``/``error``/``tool``.
        The provider's ``findings`` (severity/cwe/title/details) are absent
        by construction; RAPHAEL additionally rejects any authority field via
        the closed schema. The raw output text is preserved as UNTRUSTED
        ``provider_message``; it is never authority.
        """
        from raphael_ibm_bob.provider_runtime import (
            normalize_result,
            parse_closed_payload,
        )

        try:
            receipt = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return _bounded_result(
                ProviderState.FAILURE, handoff,
                error=f"bridge receipt not JSON: {type(exc).__name__}")
        if not isinstance(receipt, dict):
            return _bounded_result(
                ProviderState.FAILURE, handoff,
                error="bridge receipt must be a JSON object")

        success = receipt.get("success") is True
        output = receipt.get("output")
        error_text = receipt.get("error")
        output = output if isinstance(output, str) else ""
        error_text = error_text if isinstance(error_text, str) else ""

        # Deterministic, provider-derived CONTENT DIGEST of the bounded
        # output. This is UNTRUSTED metadata: it fingerprints what the
        # provider returned so an INDEPENDENT reproduction can be compared
        # by digest (result_hash), never by matching an authority string.
        # A digest match is reproduction evidence, not a verdict.
        result_hash = "sha256:" + hashlib.sha256(
            output.encode("utf-8")).hexdigest()

        raphael_payload: Dict[str, Any] = {
            "results": [],
            "artifacts": [],
            "provider_message": output[:2000],
            "operation_id": f"t3mp3st-{handoff.invocation_id}",
            "result_hash": result_hash,
            "truncated": False,
        }
        payload_bytes = json.dumps(raphael_payload).encode("utf-8")
        try:
            parse_closed_payload(payload_bytes, handoff.max_response_bytes)
        except Exception:  # noqa: BLE001 - fail closed
            return _bounded_result(
                ProviderState.FAILURE, handoff,
                error="provider output failed RAPHAEL closed schema")

        if not success or error_text:
            return _bounded_result(
                ProviderState.FAILURE, handoff,
                error=(error_text or "t3mp3st reported failure")[:512])
        return normalize_result(handoff, payload_bytes)


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
    "DEFAULT_BRIDGE_PATH",
    "DEFAULT_LAUNCHER_PATH",
    "DEFAULT_NODE_PATH",
    "EXPOSED_TOOLS",
    "InertProviderDouble",
    "LAUNCHER_SHA256",
    "LauncherIntegrityError",
    "MIN_NODE_VERSION",
    "OutOfContractToolError",
    "ProviderIntegrityError",
    "ProviderUnavailableError",
    "SandboxedLauncherAdapter",
    "T3MP3ST_BRIDGE_SHA256",
    "T3MP3STAdapter",
    "file_sha256",
    "launcher_digest_ok",
]
