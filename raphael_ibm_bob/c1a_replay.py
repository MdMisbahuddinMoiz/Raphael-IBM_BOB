"""raphael_ibm_bob.c1a_replay — lineage, replay, and staleness guards.

Rejects:

    * replayed receipts (a receipt identity already consumed),
    * cross-run substitution (same invocation presented under another run),
    * stale receipts (fixture digest no longer matches the current fixture),
    * malformed receipts (missing/invalid identity fields).

All identity is canonical JSON hashed with SHA-256; no wall-clock or random
input participates.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


class C1AReplayError(Exception):
    """Fail-closed replay/lineage error."""


#: Fields that must be present on a lineage/receipt identity.
LINEAGE_FIELDS = (
    "run_id",
    "invocation_id",
    "proof_session_id",
    "sandbox_id",
    "fixture_path",
    "fixture_sha256",
)


def _canonical(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def compute_lineage_hash(*, run_id: str, invocation_id: str,
                         proof_session_id: str, sandbox_id: str,
                         fixture_path: str, fixture_sha256: str,
                         parent_lineage_hash: Optional[str] = None) -> str:
    return hashlib.sha256(_canonical({
        "run_id": run_id,
        "invocation_id": invocation_id,
        "proof_session_id": proof_session_id,
        "sandbox_id": sandbox_id,
        "fixture_path": fixture_path,
        "fixture_sha256": fixture_sha256,
        "parent_lineage_hash": parent_lineage_hash,
    })).hexdigest()


@dataclass(frozen=True)
class Lineage:
    run_id: str
    invocation_id: str
    proof_session_id: str
    sandbox_id: str
    fixture_path: str
    fixture_sha256: str
    parent_lineage_hash: Optional[str]
    lineage_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "invocation_id": self.invocation_id,
            "proof_session_id": self.proof_session_id,
            "sandbox_id": self.sandbox_id,
            "fixture_path": self.fixture_path,
            "fixture_sha256": self.fixture_sha256,
            "parent_lineage_hash": self.parent_lineage_hash,
            "lineage_hash": self.lineage_hash,
        }


def new_lineage(*, run_id: str, invocation_id: str, proof_session_id: str,
                sandbox_id: str, fixture_path: str, fixture_sha256: str,
                parent_lineage_hash: Optional[str] = None) -> Lineage:
    digest = compute_lineage_hash(
        run_id=run_id, invocation_id=invocation_id,
        proof_session_id=proof_session_id, sandbox_id=sandbox_id,
        fixture_path=fixture_path, fixture_sha256=fixture_sha256,
        parent_lineage_hash=parent_lineage_hash)
    return Lineage(run_id, invocation_id, proof_session_id, sandbox_id,
                   fixture_path, fixture_sha256, parent_lineage_hash, digest)


def lineage_integrity_ok(lineage: Lineage) -> bool:
    expected = compute_lineage_hash(
        run_id=lineage.run_id, invocation_id=lineage.invocation_id,
        proof_session_id=lineage.proof_session_id,
        sandbox_id=lineage.sandbox_id, fixture_path=lineage.fixture_path,
        fixture_sha256=lineage.fixture_sha256,
        parent_lineage_hash=lineage.parent_lineage_hash)
    return expected == lineage.lineage_hash


class C1AReplayGuard:
    """Process-local replay guard over C1A receipt identities."""

    def __init__(self) -> None:
        self._run_by_invocation: Dict[str, str] = {}

    def register(self, lineage: Lineage) -> None:
        if not lineage_integrity_ok(lineage):
            raise C1AReplayError("lineage integrity mismatch")
        for field in ("run_id", "invocation_id", "proof_session_id",
                      "sandbox_id", "fixture_path", "fixture_sha256"):
            if not getattr(lineage, field):
                raise C1AReplayError(f"lineage missing {field}")
        existing = self._run_by_invocation.get(lineage.invocation_id)
        if existing is not None:
            if existing != lineage.run_id:
                raise C1AReplayError(
                    "cross-run substitution: invocation "
                    f"{lineage.invocation_id!r} already bound to run "
                    f"{existing!r}")
            raise C1AReplayError(
                f"replayed invocation: {lineage.invocation_id!r}")
        self._run_by_invocation[lineage.invocation_id] = lineage.run_id

    def is_registered(self, invocation_id: str) -> bool:
        return invocation_id in self._run_by_invocation

    def run_for(self, invocation_id: str) -> Optional[str]:
        return self._run_by_invocation.get(invocation_id)

    def check_receipt(
        self,
        receipt: Dict[str, Any],
        *,
        expected_run_id: str,
        current_fixture_sha256: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Return ``(ok, reason)``; never raises."""
        if not isinstance(receipt, dict):
            return False, "malformed-receipt"
        for field in LINEAGE_FIELDS:
            value = receipt.get(field)
            if not isinstance(value, str) or value == "":
                return False, f"missing-field:{field}"
        if receipt["run_id"] != expected_run_id:
            return False, "cross-run-substitution"
        bound_run = self._run_by_invocation.get(receipt["invocation_id"])
        if bound_run is not None and bound_run != receipt["run_id"]:
            return False, "cross-run-substitution"
        if (current_fixture_sha256 is not None
                and receipt["fixture_sha256"] != current_fixture_sha256):
            return False, "stale-receipt:fixture-digest-changed"
        return True, "ok"


__all__ = [
    "C1AReplayError",
    "C1AReplayGuard",
    "LINEAGE_FIELDS",
    "Lineage",
    "compute_lineage_hash",
    "lineage_integrity_ok",
    "new_lineage",
]
