"""raphael_ibm_bob.c1a_authorization — C1A authorization binding.

Binds a Broker-produced ``PolicyDecision`` to a ``ScopeHandoff`` with the
COMPLETE authoritative identity, and verifies that binding fail-closed.

Security properties:

    * No self-authorized C1A path: every C1A invocation must present a valid
      Broker-produced ALLOW decision.
    * The binding is cryptographically sealed (HMAC-SHA256 over a single
      canonical serialization of the authoritative payload).
    * CORRECTION 1: ``create_binding`` and ``verify_binding`` use the SAME
      canonical payload function (:func:`binding_payload`). The earlier GLM
      package hashed a large payload at creation but reconstructed a smaller
      one at verification; that is not reproduced here.
    * Replay is rejected: an invocation id can be bound once and is
      single-use once invalidated.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from raphael_ibm_bob.c1a_scope import within_root
from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
    PolicyDecision,
)
from raphael_ibm_bob.provider_runtime import (
    C1A_CAPABILITY_ID,
    C1A_PROVIDER_ID,
    ScopeHandoff,
)

#: The authoritative identity fields sealed by the binding. Kept in ONE
#: place so creation and verification cannot drift.
BINDING_FIELDS = (
    "run_id",
    "mission_id",
    "decision_seq",
    "request_seq",
    "invocation_id",
    "proof_session_id",
    "lifecycle_id",
    "sandbox_id",
    "capability_id",
    "provider_id",
    "target",
    "fixture_path",
)


class C1AAuthorizationError(Exception):
    """Fail-closed authorization binding error."""


def _canonical_json(payload: Dict[str, Any]) -> bytes:
    """Deterministic canonical JSON (sorted keys, tight separators)."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def binding_payload(**identity: Any) -> bytes:
    """Canonical serialization of the authoritative binding payload.

    The caller MUST supply exactly the :data:`BINDING_FIELDS` keys. This is
    the single function used by both creation and verification.
    """
    missing = [k for k in BINDING_FIELDS if k not in identity]
    if missing:
        raise C1AAuthorizationError(
            f"binding identity missing fields: {sorted(missing)}")
    return _canonical_json({k: identity[k] for k in BINDING_FIELDS})


@dataclass(frozen=True)
class AuthorizationBinding:
    """A verified binding between a PolicyDecision and a ScopeHandoff."""
    identity: Dict[str, Any]
    binding_hash: str
    handoff: ScopeHandoff
    decision: PolicyDecision

    @property
    def invocation_id(self) -> str:
        return self.identity["invocation_id"]

    @property
    def mission_id(self) -> str:
        return self.identity["mission_id"]

    @property
    def decision_seq(self) -> int:
        return self.identity["decision_seq"]

    @property
    def request_seq(self) -> int:
        return self.identity["request_seq"]

    @property
    def target(self) -> str:
        return self.identity["target"]

    @property
    def proof_session_id(self) -> str:
        return self.identity["proof_session_id"]

    @property
    def lifecycle_id(self) -> str:
        return self.identity["lifecycle_id"]

    @property
    def sandbox_id(self) -> str:
        return self.identity["sandbox_id"]


class C1AAuthorizationBinding:
    """Creates and validates PolicyDecision -> ScopeHandoff bindings."""

    #: Per-process HMAC secret. Not persisted, not exported.
    _BINDING_SECRET: bytes = os.urandom(32)

    def __init__(self) -> None:
        self._active_bindings: Dict[str, AuthorizationBinding] = {}

    # --- creation ---------------------------------------------------------

    def create_binding(
        self,
        *,
        decision: PolicyDecision,
        request: ActionRequest,
        run_id: str,
        mission_id: str,
        workspace_root: str,
        timeout_seconds: Optional[float],
    ) -> AuthorizationBinding:
        """Create a verified binding from an ALLOW decision to a handoff.

        Fails closed if the decision is not ALLOW, the capability is not
        C1A, the mission id is missing, the targets disagree, the target is
        not canonically contained in the workspace, the timeout is not
        positive, or the invocation is already bound (replay).

        ``mission_id`` is the RAPHAEL-owned ``Mission.mission_id``; it is
        sealed into the binding and carried through the handoff so provider
        results can never be grafted across missions. It is NEVER a
        provider-issued identifier (T3MP3ST is a stateless direct handler).
        """
        if not isinstance(mission_id, str) or mission_id.strip() == "":
            raise C1AAuthorizationError(
                "C1A binding requires a non-empty RAPHAEL mission_id")
        if decision.decision is not Decision.ALLOW:
            raise C1AAuthorizationError(
                f"cannot bind non-ALLOW decision: {decision.decision.value}")
        if request.capability is not Capability.C1A_STATIC_FILE_INSPECT:
            raise C1AAuthorizationError(
                f"cannot bind non-C1A capability: {request.capability.value}")
        if decision.capability is not Capability.C1A_STATIC_FILE_INSPECT:
            raise C1AAuthorizationError(
                f"decision capability is not C1A: {decision.capability.value}")
        if request.target != decision.target:
            raise C1AAuthorizationError(
                f"target mismatch: request={request.target!r} "
                f"decision={decision.target!r}")
        if (timeout_seconds is None
                or isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or timeout_seconds <= 0):
            raise C1AAuthorizationError("C1A requires a positive timeout")

        target_canonical = os.path.normpath(os.path.abspath(request.target))
        if not within_root(workspace_root, target_canonical):
            raise C1AAuthorizationError(
                f"C1A target not canonically contained in workspace: "
                f"{target_canonical!r}")

        invocation_id = self._deterministic_id(
            "INV", f"{run_id}:{decision.sequence}:{request.sequence}")
        proof_session_id = self._deterministic_id("PROOF", run_id)
        lifecycle_id = self._deterministic_id(
            "LIFE", f"{run_id}:{invocation_id}")
        sandbox_id = self._deterministic_id(
            "SBOX", f"{run_id}:{invocation_id}:sandbox")

        if invocation_id in self._active_bindings:
            raise C1AAuthorizationError(
                f"invocation already bound (replay): {invocation_id}")

        # Single-file C1A mode: the fixture root is the target's directory,
        # satisfying provider_runtime.validate_scope's direct-child rule.
        fixture_root = os.path.dirname(target_canonical)
        sandbox_digest = hashlib.sha256(
            _canonical_json({
                "sandbox_id": sandbox_id,
                "invocation_id": invocation_id,
                "fixture_path": target_canonical,
            })).hexdigest()

        handoff = ScopeHandoff(
            run_id=run_id,
            proof_session_id=proof_session_id,
            mission_id=mission_id,
            action_request_id=str(request.sequence),
            invocation_id=invocation_id,
            fixture_root=fixture_root,
            fixture_path=target_canonical,
            capability_id=C1A_CAPABILITY_ID,
            provider_id=C1A_PROVIDER_ID,
            network_denied=True,
            timeout_seconds=float(timeout_seconds),
            sandbox_digest=sandbox_digest,
        )

        identity: Dict[str, Any] = {
            "run_id": run_id,
            "mission_id": mission_id,
            "decision_seq": decision.sequence,
            "request_seq": request.sequence,
            "invocation_id": invocation_id,
            "proof_session_id": proof_session_id,
            "lifecycle_id": lifecycle_id,
            "sandbox_id": sandbox_id,
            "capability_id": C1A_CAPABILITY_ID,
            "provider_id": C1A_PROVIDER_ID,
            "target": request.target,
            "fixture_path": target_canonical,
        }
        binding_hash = hmac.new(
            self._BINDING_SECRET, binding_payload(**identity),
            hashlib.sha256).hexdigest()

        binding = AuthorizationBinding(
            identity=identity, binding_hash=binding_hash,
            handoff=handoff, decision=decision)
        self._active_bindings[invocation_id] = binding
        return binding

    # --- verification -----------------------------------------------------

    def verify_binding(
        self,
        invocation_id: str,
        decision: PolicyDecision,
        claimed: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Verify an active binding against the decision.

        ``claimed`` optionally overrides identity fields to prove tampering
        is detected: any override that changes the canonical payload fails.
        Returns False (never raises) on any mismatch.
        """
        binding = self._active_bindings.get(invocation_id)
        if binding is None:
            return False
        if decision is None:
            return False
        if decision.decision is not Decision.ALLOW:
            return False
        if decision.capability is not Capability.C1A_STATIC_FILE_INSPECT:
            return False
        if decision.sequence != binding.identity["decision_seq"]:
            return False
        if decision.target != binding.identity["target"]:
            return False

        identity = dict(binding.identity)
        if claimed:
            for key, value in claimed.items():
                if key not in BINDING_FIELDS:
                    return False
                identity[key] = value
        try:
            expected = hmac.new(
                self._BINDING_SECRET, binding_payload(**identity),
                hashlib.sha256).hexdigest()
        except C1AAuthorizationError:
            return False
        return hmac.compare_digest(binding.binding_hash, expected)

    # --- lifecycle --------------------------------------------------------

    def invalidate_binding(self, invocation_id: str) -> None:
        """Remove a binding after use (single-use)."""
        self._active_bindings.pop(invocation_id, None)

    def is_active(self, invocation_id: str) -> bool:
        return invocation_id in self._active_bindings

    def active_invocations(self) -> tuple:
        return tuple(sorted(self._active_bindings))

    # --- internals --------------------------------------------------------

    @staticmethod
    def _deterministic_id(prefix: str, seed: str) -> str:
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}-{digest}"




__all__ = [
    "AuthorizationBinding",
    "BINDING_FIELDS",
    "C1AAuthorizationBinding",
    "C1AAuthorizationError",
    "binding_payload",
]
