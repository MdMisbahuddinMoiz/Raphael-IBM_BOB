"""raphael_ibm_bob.c1a_lifecycle — host-side C1A lifecycle orchestration.

Anchors the C1A execution lifecycle on the existing
:class:`~raphael_ibm_bob.b4_lifecycle.LifecycleRecord` state machine:

    CREATED -> SANDBOX_BOUND -> WORKLOAD_BOUND -> RUNNING
            -> TEARDOWN_INITIATED -> TEARDOWN_OBSERVED -> CLOSED

Teardown observation is HOST-OWNED. A provider can never claim teardown;
``close()`` still requires M5-bound provenance, so an inert/direct
lifecycle stops at TEARDOWN_OBSERVED and is never closed without M5.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from raphael_ibm_bob.b4_lifecycle import (
    LifecycleError,
    LifecycleRecord,
    LifecycleState,
    M5TrustAuthority,
    bind_m5_teardown,
)


class C1ALifecycleError(Exception):
    """Fail-closed C1A lifecycle error."""


@dataclass(frozen=True)
class LifecycleObservation:
    """A host-observed lifecycle transition (non-authoritative)."""
    lifecycle_id: str
    from_state: str
    to_state: str
    observed_at: float
    observation_type: str


class C1ALifecycleOrchestrator:
    """Host-side orchestration over LifecycleRecord, with identity binding."""

    def __init__(self, *, m5_authority: Optional[M5TrustAuthority] = None):
        self._authority = m5_authority
        self._records: Dict[str, LifecycleRecord] = {}
        self._observations: Dict[str, list] = {}

    # --- creation / lookup ------------------------------------------------

    def create(self, lifecycle_id: str, proof_session_id: str) -> LifecycleRecord:
        if not lifecycle_id or not proof_session_id:
            raise C1ALifecycleError("lifecycle_id and proof_session_id required")
        if lifecycle_id in self._records:
            raise C1ALifecycleError(f"lifecycle already exists: {lifecycle_id}")
        record = LifecycleRecord.create(lifecycle_id, proof_session_id)
        self._records[lifecycle_id] = record
        self._observations[lifecycle_id] = []
        return record

    def create_for_binding(self, binding: Any) -> LifecycleRecord:
        """Create a lifecycle whose identity is taken from the binding."""
        record = self.create(binding.lifecycle_id, binding.proof_session_id)
        self.assert_binding(record, binding)
        self.bind_sandbox(record, binding.sandbox_id)
        return record

    def get(self, lifecycle_id: str) -> Optional[LifecycleRecord]:
        return self._records.get(lifecycle_id)

    def state(self, lifecycle_id: str) -> Optional[LifecycleState]:
        record = self._records.get(lifecycle_id)
        return record.state if record is not None else None

    def observations(self, lifecycle_id: str) -> tuple:
        return tuple(self._observations.get(lifecycle_id, ()))

    # --- identity enforcement --------------------------------------------

    @staticmethod
    def assert_binding(record: LifecycleRecord, binding: Any) -> None:
        """Reject a foreign lifecycle/proof/sandbox identity (fail closed)."""
        if record.lifecycle_id != binding.lifecycle_id:
            raise C1ALifecycleError(
                "foreign lifecycle identity: "
                f"{record.lifecycle_id!r} != {binding.lifecycle_id!r}")
        if record.proof_session_id != binding.proof_session_id:
            raise C1ALifecycleError("foreign proof-session identity")
        if (record.sandbox_id is not None
                and record.sandbox_id != binding.sandbox_id):
            raise C1ALifecycleError("foreign sandbox identity")

    # --- transitions ------------------------------------------------------

    def _record(self, lifecycle_id: str) -> LifecycleRecord:
        record = self._records.get(lifecycle_id)
        if record is None:
            raise C1ALifecycleError(f"unknown lifecycle: {lifecycle_id}")
        return record

    def _observe(self, record: LifecycleRecord, prev: LifecycleState,
                 kind: str = "host-observed") -> LifecycleObservation:
        observation = LifecycleObservation(
            lifecycle_id=record.lifecycle_id,
            from_state=prev.name,
            to_state=record.state.name,
            observed_at=time.monotonic(),
            observation_type=kind,
        )
        self._observations[record.lifecycle_id].append(observation)
        return observation

    def bind_sandbox(self, record: LifecycleRecord,
                     sandbox_id: str) -> LifecycleObservation:
        prev = record.state
        try:
            record.bind_sandbox(sandbox_id)
        except LifecycleError as exc:
            raise C1ALifecycleError(str(exc)) from None
        return self._observe(record, prev)

    def bind_workload(self, record: LifecycleRecord, pid: int,
                      pid_starttime: str,
                      cgroup: str) -> LifecycleObservation:
        prev = record.state
        try:
            record.bind_workload(pid, pid_starttime, cgroup)
        except LifecycleError as exc:
            raise C1ALifecycleError(str(exc)) from None
        return self._observe(record, prev)

    def start(self, record: LifecycleRecord) -> LifecycleObservation:
        prev = record.state
        try:
            record.start()
        except LifecycleError as exc:
            raise C1ALifecycleError(str(exc)) from None
        return self._observe(record, prev, kind="host-initiated")

    def initiate_teardown(self, record: LifecycleRecord) -> LifecycleObservation:
        prev = record.state
        try:
            record.initiate_teardown()
        except LifecycleError as exc:
            raise C1ALifecycleError(str(exc)) from None
        return self._observe(record, prev, kind="host-initiated")

    # --- teardown ---------------------------------------------------------

    def observe_teardown_direct(self, record: LifecycleRecord,
                                evidence_ref: str,
                                evidence_sha256: str) -> LifecycleObservation:
        """Record a host DIRECT teardown observation (non-M5)."""
        prev = record.state
        try:
            record.observe_teardown(evidence_ref, evidence_sha256)
        except LifecycleError as exc:
            raise C1ALifecycleError(str(exc)) from None
        return self._observe(record, prev)

    def observe_teardown_from_transport(
        self, record: LifecycleRecord, transport_result: Any,
        evidence_ref: str, evidence_sha256: str,
    ) -> bool:
        """Advance teardown ONLY when the host observed process exit.

        Returns True when teardown was recorded; False when the process was
        not observed to exit (orphan possible) and the lifecycle remains in
        TEARDOWN_INITIATED.
        """
        if not getattr(transport_result, "process_exited", False):
            return False
        if getattr(transport_result, "late_output", False):
            return False
        self.observe_teardown_direct(record, evidence_ref, evidence_sha256)
        return True

    def observe_teardown_m5(
        self, record: LifecycleRecord, *,
        m5_evidence: Dict[str, Any], reference: str, sha256: str,
        observation: Any,
    ) -> LifecycleObservation:
        """Bind an authority-authenticated M5 teardown observation."""
        if self._authority is None:
            raise C1ALifecycleError(
                "no M5 trust authority configured (fail closed)")
        prev = record.state
        try:
            bind_m5_teardown(record, m5_evidence, reference, sha256,
                             observation=observation,
                             authority=self._authority)
        except LifecycleError as exc:
            raise C1ALifecycleError(str(exc)) from None
        return self._observe(record, prev, kind="host-observed:m5")

    def close(self, record: LifecycleRecord) -> LifecycleObservation:
        """Close the lifecycle. Requires M5-bound teardown provenance."""
        prev = record.state
        try:
            record.close()
        except LifecycleError as exc:
            raise C1ALifecycleError(str(exc)) from None
        return self._observe(record, prev, kind="host-initiated")


__all__ = [
    "C1ALifecycleError",
    "C1ALifecycleOrchestrator",
    "LifecycleObservation",
]
