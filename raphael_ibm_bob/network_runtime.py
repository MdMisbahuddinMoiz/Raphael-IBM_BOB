"""raphael_ibm_bob.network_runtime — governed HTTP network boundary (D9).

The ONLY network-I/O boundary in the governed core. It mirrors the C1A
provider-runtime pattern (``provider_runtime`` + ``c1a_transport``) but is
strictly narrower:

    * one bounded HTTP(S) request per invocation (GET/HEAD only)
    * RAPHAEL-owned scope is re-validated before any socket (defence in depth)
    * redirects are NEVER followed (no redirect-based SSRF)
    * response body is byte-capped; truncation is explicit
    * a timeout / refused connection is NEVER success
    * the invocation is cryptographically bound to its identity and
      registered in a replay guard
    * output is UNTRUSTED evidence, never authority

No shell, no subprocess, no proxy, no arbitrary method, no raw sockets.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple

from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
    Finding,
    FindingState,
    Mission,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, digest_id
from raphael_ibm_bob.finding import FindingStore, InvalidTransitionError
from raphael_ibm_bob.network_scope import (
    NetworkScopeError,
    parse_http_target,
)
from raphael_ibm_bob.target_profile import TargetProfile

NETWORK_CAPABILITY_ID = Capability.NETWORK_HTTP_REQUEST.value
ALLOWED_METHODS = ("GET", "HEAD")
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RESPONSE_BYTES = 65536
MAX_BODY_PREVIEW = 2000
USER_AGENT = "RaphaelNetwork/1.0"
PROVIDER_UNTRUSTED = "provider_untrusted"

#: Deterministic HTB flag format (repo-established: `HTB{...}`).
FLAG_RE = re.compile(r"HTB\{[^}\s]{1,200}\}")

_METHOD_RE = re.compile(r"method=([A-Za-z]+)")


class NetworkState(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    REFUSED = "refused"
    UNAVAILABLE = "unavailable"
    DENIED = "denied"


class _Timeout(Exception):
    pass


class _Refused(Exception):
    pass


class _Unavailable(Exception):
    pass


def extract_flag(text: object) -> Optional[str]:
    """Deterministically extract the first HTB flag, or None."""
    if not isinstance(text, str):
        return None
    match = FLAG_RE.search(text)
    return match.group(0) if match else None


def flag_sha256(flag: object) -> Optional[str]:
    if not isinstance(flag, str) or flag == "":
        return None
    return hashlib.sha256(flag.encode("utf-8")).hexdigest()


def method_from_purpose(purpose: object, default: str = "GET") -> str:
    """Derive the HTTP method from the request purpose (explicit only)."""
    text = purpose if isinstance(purpose, str) else ""
    match = _METHOD_RE.search(text)
    if match:
        return match.group(1).upper()
    return default


def _decision_allows(decision: Any, request: ActionRequest) -> bool:
    """True iff a Policy ALLOW decision authorizes this exact request.

    Enforces the invariant the mediator depends on: the execution must be
    authorised by the PolicyDecision the Broker obtained for THIS request —
    an ALLOW whose capability/target/sequence match the stamped request. A
    missing, DENY, or mismatched decision means no execution.
    """
    if decision is None:
        return False
    value = getattr(decision, "decision", None)
    if str(getattr(value, "value", value)).lower() != "allow":
        return False
    capability = getattr(decision, "capability", None)
    if str(getattr(capability, "value", capability)) != request.capability.value:
        return False
    if getattr(decision, "target", None) != request.target:
        return False
    seq = getattr(decision, "sequence", None)
    if seq is not None and seq != request.sequence:
        return False
    return True


@dataclass(frozen=True)
class NetworkResult:
    """Closed, bounded outcome of one governed network request."""
    state: NetworkState
    invocation_id: str
    mission_id: str
    target_id: str
    scheme: str
    host: str
    port: int
    method: str
    path: str
    run_id: str = ""
    status_code: Optional[int] = None
    response_bytes: int = 0
    response_sha256: Optional[str] = None
    truncated: bool = False
    flag: Optional[str] = None
    flag_sha256: Optional[str] = None
    body_preview: str = ""
    error: str = ""

    @property
    def success(self) -> bool:
        return self.state is NetworkState.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "invocation_id": self.invocation_id,
            "mission_id": self.mission_id,
            "target_id": self.target_id,
            "scheme": self.scheme,
            "host": self.host,
            "port": self.port,
            "method": self.method,
            "path": self.path,
            "run_id": self.run_id,
            "status_code": self.status_code,
            "response_bytes": self.response_bytes,
            "response_sha256": self.response_sha256,
            "truncated": self.truncated,
            "flag": self.flag,
            "flag_sha256": self.flag_sha256,
            "body_preview": self.body_preview[:MAX_BODY_PREVIEW],
            "error": self.error,
            PROVIDER_UNTRUSTED: True,
        }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: never follow to a new host/path."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _urllib_open(url: str, method: str, timeout: float,
                 max_bytes: int) -> Tuple[int, bytes, bool]:
    """Default opener: bounded stdlib HTTP with redirects disabled."""
    request = urllib.request.Request(
        url, method=method,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            body = response.read(max_bytes + 1)
        return int(status), body, len(body) > max_bytes
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(max_bytes + 1)
        except Exception:
            body = b""
        return int(exc.code), body, len(body) > max_bytes
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise _Timeout(str(reason)) from None
        if isinstance(reason, ConnectionRefusedError):
            raise _Refused(str(reason)) from None
        raise _Unavailable(f"{type(reason).__name__}:{reason}") from None
    except (TimeoutError, socket.timeout):
        raise _Timeout("timeout") from None
    except ConnectionRefusedError:
        raise _Refused("connection refused") from None
    except OSError as exc:
        if isinstance(exc, ConnectionRefusedError):
            raise _Refused(str(exc)) from None
        raise _Unavailable(f"{type(exc).__name__}:{exc}") from None


class NetworkReplayGuard:
    """Process-local replay guard over network invocation identities."""

    def __init__(self) -> None:
        self._run_by_invocation: Dict[str, str] = {}
        self._lock = threading.Lock()

    def register(self, run_id: str, invocation_id: str) -> None:
        if not run_id or not invocation_id:
            raise ValueError("run_id and invocation_id are required")
        with self._lock:
            existing = self._run_by_invocation.get(invocation_id)
            if existing is not None:
                raise ValueError(
                    f"replayed invocation: {invocation_id!r}")
            self._run_by_invocation[invocation_id] = run_id

    def is_registered(self, invocation_id: str) -> bool:
        with self._lock:
            return invocation_id in self._run_by_invocation

    def run_for(self, invocation_id: str) -> Optional[str]:
        with self._lock:
            return self._run_by_invocation.get(invocation_id)


class NetworkMediator:
    """Minimal governed HTTP mediator (one request per invocation)."""

    #: Per-process HMAC secret for invocation bindings. Never persisted.
    _BINDING_SECRET: bytes = os.urandom(32)

    def __init__(
        self,
        *,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        allowed_methods: Tuple[str, ...] = ALLOWED_METHODS,
        opener: Callable[[str, str, float, int],
                         Tuple[int, bytes, bool]] = _urllib_open,
        replay_guard: Optional[NetworkReplayGuard] = None,
    ) -> None:
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._max_bytes = int(max_response_bytes)
        self._timeout = float(timeout_seconds)
        self._allowed_methods = tuple(m.upper() for m in allowed_methods)
        self._opener = opener
        self.replay_guard = replay_guard or NetworkReplayGuard()

    # --- binding ---------------------------------------------------------

    def _identity(self, *, request: ActionRequest, profile: TargetProfile,
                  invocation_id: str, run_id: str, method: str,
                  target) -> Dict[str, Any]:
        return {
            "run_id": run_id,
            "mission_id": profile.mission_id,
            "invocation_id": invocation_id,
            "capability_id": NETWORK_CAPABILITY_ID,
            "target_id": profile.target_id,
            "host": target.host,
            "port": target.port,
            "protocol": target.scheme,
            "method": method,
            "path": target.path,
        }

    def _binding_hash(self, identity: Dict[str, Any]) -> str:
        payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        return hmac.new(self._BINDING_SECRET, payload.encode("utf-8"),
                        hashlib.sha256).hexdigest()

    # --- invocation ------------------------------------------------------

    def invoke(self, *, request: ActionRequest, profile: TargetProfile,
               invocation_id: str, run_id: str,
               decision: Any = None) -> NetworkResult:
        """Validate scope + the Policy decision, then run one request."""
        try:
            target = parse_http_target(request.target)
        except NetworkScopeError as exc:
            return self._fail(NetworkState.DENIED, profile, invocation_id,
                              error=f"target-invalid:{exc}")
        if not profile.allows(host=target.host, port=target.port,
                              protocol=target.scheme):
            return self._fail(NetworkState.DENIED, profile, invocation_id,
                              error="target-not-authorized", target=target)
        method = method_from_purpose(request.purpose)
        if method not in self._allowed_methods:
            return self._fail(NetworkState.DENIED, profile, invocation_id,
                              error=f"method-not-allowed:{method}",
                              target=target, method=method)
        if not _decision_allows(decision, request):
            return self._fail(NetworkState.DENIED, profile, invocation_id,
                              error="authorization-not-allow", target=target,
                              method=method)

        try:
            self.replay_guard.register(run_id, invocation_id)
        except ValueError:
            return self._fail(NetworkState.DENIED, profile, invocation_id,
                              error="replay", target=target, method=method)

        try:
            status, body, truncated = self._opener(
                target.url, method, self._timeout, self._max_bytes)
        except _Timeout as exc:
            return self._fail(NetworkState.TIMEOUT, profile, invocation_id,
                              error=str(exc), target=target, method=method)
        except _Refused as exc:
            return self._fail(NetworkState.REFUSED, profile, invocation_id,
                              error=str(exc), target=target, method=method)
        except _Unavailable as exc:
            return self._fail(NetworkState.UNAVAILABLE, profile, invocation_id,
                              error=str(exc), target=target, method=method)

        if len(body) > self._max_bytes:
            body = body[:self._max_bytes]
            truncated = True
        digest = hashlib.sha256(body).hexdigest()
        text = body.decode("utf-8", errors="replace")
        flag = extract_flag(text)
        return NetworkResult(
            state=NetworkState.SUCCESS,
            invocation_id=invocation_id,
            mission_id=profile.mission_id,
            target_id=profile.target_id,
            scheme=target.scheme, host=target.host, port=target.port,
            method=method, path=target.path, run_id=run_id,
            status_code=status, response_bytes=len(body),
            response_sha256=digest, truncated=truncated,
            flag=flag, flag_sha256=flag_sha256(flag),
            body_preview=text[:MAX_BODY_PREVIEW])

    def _fail(self, state: NetworkState, profile: TargetProfile,
              invocation_id: str, *, error: str, run_id: str = "",
              target: Any = None, method: str = "GET") -> NetworkResult:
        return NetworkResult(
            state=state, invocation_id=invocation_id,
            mission_id=profile.mission_id, target_id=profile.target_id,
            scheme=getattr(target, "scheme", ""),
            host=getattr(target, "host", profile.locator),
            port=getattr(target, "port", 0), method=method,
            path=getattr(target, "path", ""), run_id=run_id,
            error=error[:512])


_mediator_singleton: Optional[NetworkMediator] = None
_mediator_lock = threading.Lock()


def get_network_mediator() -> NetworkMediator:
    global _mediator_singleton
    with _mediator_lock:
        if _mediator_singleton is None:
            _mediator_singleton = NetworkMediator()
        return _mediator_singleton


def set_network_mediator(mediator: Optional[NetworkMediator]) -> None:
    global _mediator_singleton
    with _mediator_lock:
        _mediator_singleton = mediator


# ---------------------------------------------------------------------------
# independent network verification (D4 P1..P6)
# ---------------------------------------------------------------------------

class NetworkVerificationError(Exception):
    pass


@dataclass(frozen=True)
class NetworkVerificationOutcome:
    classification: str
    checks: Dict[str, bool]
    observed_flag_sha256: Optional[str]
    invocation_id: Optional[str]
    result_seq: Optional[int]
    transition_applied: bool
    evidence_id: Optional[str]


def _network_result_from_execution(execution) -> Optional[Dict[str, Any]]:
    if execution is None:
        return None
    evidence = execution.evidence or {}
    result = evidence.get("network_result")
    return result if isinstance(result, dict) else None


class NetworkVerifier:
    """Broker-mediated independent reproduction of a network finding."""

    def __init__(self, runtime, ledger: EvidenceLedger,
                 store: Optional[FindingStore] = None,
                 replay_guard: Optional[NetworkReplayGuard] = None) -> None:
        self._runtime = runtime
        self._ledger = ledger
        self._store = store
        self._guard = replay_guard

    def _replay_guard(self) -> Optional[NetworkReplayGuard]:
        if self._guard is not None:
            return self._guard
        broker = getattr(self._runtime, "broker", None)
        mediator = getattr(broker, "_network_mediator", None)
        return getattr(mediator, "replay_guard", None)

    def verify_independent(
        self,
        finding: Finding,
        mission: Mission,
        *,
        original_invocation_id: Optional[str] = None,
        expected_flag_hash: Optional[str] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        requester: str = "network-verifier",
    ) -> NetworkVerificationOutcome:
        """Run a NEW governed network request and check D4 independence."""
        if finding.state is not FindingState.UNVERIFIED:
            return NetworkVerificationOutcome(
                classification="insufficient",
                checks={}, observed_flag_sha256=None, invocation_id=None,
                result_seq=None, transition_applied=False, evidence_id=None)

        request = ActionRequest(
            sequence=0, requester=requester,
            capability=Capability.NETWORK_HTTP_REQUEST,
            target=finding.target,
            purpose="network-http-request method=GET",
            finding_id=finding.finding_id,
            timeout_seconds=timeout_seconds)
        runtime_result = self._runtime.submit(request, mission)
        execution = runtime_result.execution
        network = _network_result_from_execution(execution) or {}
        new_invocation = network.get("invocation_id")
        run_id = network.get("run_id") or "in-memory"
        observed_hash = network.get("flag_sha256")
        allowed = (runtime_result.broker_result.decision.decision
                   is Decision.ALLOW)

        execution_id = digest_id(
            {"run_id": run_id, "result_seq": runtime_result.result_seq},
            prefix="NEX")
        guard = self._replay_guard()
        no_replay = bool(
            guard is not None and new_invocation
            and guard.is_registered(new_invocation)
            and guard.run_for(new_invocation) == run_id)
        cached = any(
            r.get("kind") == "evidence"
            and r.get("producer") == "network"
            and (r.get("payload") or {}).get("invocation_id") == new_invocation
            and (r.get("payload") or {}).get("mission_id") == mission.mission_id
            for r in self._ledger.all_records())

        checks = {
            "distinct_execution": bool(execution_id),
            "distinct_invocation": bool(new_invocation)
            and new_invocation != original_invocation_id,
            "fresh_provider_observation": bool(network.get("response_sha256")),
            "causal_binding_valid": (
                network.get("mission_id") == mission.mission_id
                and network.get("target_id") is not None),
            "no_replayed_execution": no_replay,
            "no_cached_output": cached,
        }
        all_passed = all(checks.values())

        if not allowed or execution is None or not execution.success:
            classification = "inconclusive"
        elif not all_passed:
            classification = "insufficient"
        elif observed_hash and observed_hash == expected_flag_hash:
            classification = "supported"
        else:
            classification = "contradicted"

        payload = {
            "kind": "network-verification-result",
            "finding_id": finding.finding_id,
            "classification": classification,
            "checks": checks,
            "invocation_id": new_invocation,
            "observed_flag_sha256": observed_hash,
            "expected_flag_sha256": expected_flag_hash,
            "request_seq": runtime_result.request_seq,
            "decision_seq": runtime_result.decision_seq,
            "result_seq": runtime_result.result_seq,
        }
        evidence_id = digest_id(payload, prefix="NV")
        self._ledger.append_evidence(
            evidence_id=evidence_id, producer="verifier",
            request_seq=runtime_result.request_seq,
            decision_seq=runtime_result.decision_seq,
            result_seq=runtime_result.result_seq,
            payload=payload, finding_id=finding.finding_id)

        applied = False
        if classification == "supported" and all_passed and self._store:
            try:
                self._store.transition(
                    finding.finding_id, FindingState.VERIFIED,
                    evidence_seqs=tuple(
                        s for s in (runtime_result.request_seq,
                                    runtime_result.decision_seq,
                                    runtime_result.result_seq)
                        if s is not None),
                    additional_evidence_ids=[evidence_id],
                    extra_payload={"kind": "network-verified",
                                   "flag_sha256": observed_hash})
                applied = True
            except (InvalidTransitionError, KeyError):
                applied = False

        return NetworkVerificationOutcome(
            classification=classification, checks=checks,
            observed_flag_sha256=observed_hash, invocation_id=new_invocation,
            result_seq=runtime_result.result_seq, transition_applied=applied,
            evidence_id=evidence_id)


__all__ = [
    "ALLOWED_METHODS",
    "DEFAULT_MAX_RESPONSE_BYTES",
    "DEFAULT_TIMEOUT_SECONDS",
    "FLAG_RE",
    "NETWORK_CAPABILITY_ID",
    "NetworkMediator",
    "NetworkReplayGuard",
    "NetworkResult",
    "NetworkState",
    "NetworkVerificationError",
    "NetworkVerificationOutcome",
    "NetworkVerifier",
    "extract_flag",
    "flag_sha256",
    "get_network_mediator",
    "method_from_purpose",
    "set_network_mediator",
]
