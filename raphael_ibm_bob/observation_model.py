"""raphael_ibm_bob.observation_model — D13 normalized observation format.

Every capability's output becomes an ``ObservationRecord`` regardless of
underlying protocol. This is what prevents schema fragmentation as new
capabilities are added, and it is where the D12 stale-prompt defect class
is generalized away: provenance must bind an observation to the exact
session and command that produced it.

Authority boundary: an ObservationRecord is evidence *about* a target.
It is not an authorization and never causes a state transition by itself.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4


@dataclass(frozen=True)
class ObservationRecord:
    """A single normalized observation from a capability execution."""
    observation_id: str
    capability_id: str
    observation_type: str
    target_host: str
    timestamp: float
    content_hash: str
    target_port: Optional[int] = None
    raw_output_ref: Optional[str] = None
    provenance: dict = field(default_factory=dict)

    def to_evidence_dict(self) -> dict:
        return {
            "observation_id": self.observation_id,
            "capability_id": self.capability_id,
            "observation_type": self.observation_type,
            "target_host": self.target_host,
            "target_port": self.target_port,
            "timestamp": self.timestamp,
            "content_hash": self.content_hash,
            "provenance": dict(self.provenance),
        }


class ObservationBuilder:
    """Constructs ObservationRecords from raw capability output."""

    @staticmethod
    def from_capability_output(capability_id: str, output: str,
                               target_host: str, target_port: Optional[int] = None,
                               observation_type: str = "network_response",
                               provenance: Optional[dict] = None
                               ) -> ObservationRecord:
        if not isinstance(output, str):
            output = str(output)
        return ObservationRecord(
            observation_id=str(uuid4()),
            capability_id=capability_id,
            observation_type=observation_type,
            target_host=target_host,
            target_port=target_port,
            timestamp=time.time(),
            content_hash=hashlib.sha256(output.encode("utf-8")).hexdigest(),
            provenance=dict(provenance or {}),
        )

    @staticmethod
    def from_flag_capture(capability_id: str, flag_content: str,
                          target_host: str, target_port: Optional[int] = None,
                          command: Optional[str] = None,
                          session_id: Optional[str] = None
                          ) -> ObservationRecord:
        return ObservationBuilder.from_capability_output(
            capability_id=capability_id,
            output=flag_content,
            target_host=target_host,
            target_port=target_port,
            observation_type="flag",
            provenance={"command": command, "session_id": session_id,
                        "extraction": "verified_command_output"},
        )

    @staticmethod
    def from_credential_discovery(capability_id: str, credential_type: str,
                                  target_host: str, fingerprint: str,
                                  provenance: Optional[dict] = None
                                  ) -> ObservationRecord:
        return ObservationRecord(
            observation_id=str(uuid4()),
            capability_id=capability_id,
            observation_type="credential_candidate",
            target_host=target_host,
            timestamp=time.time(),
            content_hash=fingerprint,
            provenance={"credential_type": credential_type,
                        **dict(provenance or {})},
        )


class ProvenanceValidator:
    """Validates that an observation's provenance is intact."""

    @staticmethod
    def validate_fresh(observation: ObservationRecord,
                       current_session_id: str,
                       max_age_seconds: float = 300.0) -> tuple:
        """Observation must come from the current session and be recent."""
        if observation.provenance.get("session_id") != current_session_id:
            return False, "session mismatch — observation from different session"
        age = time.time() - observation.timestamp
        if age > max_age_seconds:
            return False, f"stale observation — {age:.0f}s old (max {max_age_seconds}s)"
        return True, "fresh"

    @staticmethod
    def validate_command_binding(observation: ObservationRecord,
                                 expected_command: str) -> tuple:
        """Output must be bound to a specific command (not a buffer/prompt)."""
        recorded = observation.provenance.get("command", "")
        if recorded != expected_command:
            return False, (f"command mismatch — expected '{expected_command}', "
                           f"recorded '{recorded}'")
        return True, "command binding verified"


__all__ = ["ObservationBuilder", "ObservationRecord", "ProvenanceValidator"]
