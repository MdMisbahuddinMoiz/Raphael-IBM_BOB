"""raphael_ibm_bob.credential_provenance — D13 credential provenance & vault.

Tracks WHERE credentials came from, WHAT they are authorized for, and
WHEN they were validated. Evidence carries only a fingerprint; plaintext
lives solely in the process-local vault and is never logged, serialized,
or written to the ledger.

Security notes (deliberate limits):
    * The vault is process-local and wiped on exit / explicit `wipe()`.
    * `wipe()` drops references; it does not overwrite allocator memory
      (Python cannot guarantee this) — treat it as lifecycle hygiene.
    * `fingerprint` is the full SHA-256 of the secret. It is a
      correlation handle, not a reversible commitment to a short secret;
      never treat it as proof of possession.
    * `is_authorized_for` is per-target/per-protocol to prevent
      cross-target credential reuse. It is a *descriptive* check; the
      governed authorization remains Policy + TargetProfile.
"""
from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CredentialState(Enum):
    DISCOVERED = "discovered"
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    AUTHORIZED = "authorized"
    REVOKED = "revoked"


class CredentialProvenance(Enum):
    DEFAULT_CREDENTIAL = "default"
    BRUTE_FORCED = "brute_forced"
    OBSERVED = "observed"
    EXTRACTED = "extracted"
    PROVIDED = "provided"
    DERIVED = "derived"


@dataclass
class CredentialReference:
    """A reference to a credential. NEVER contains plaintext."""
    credential_id: str
    credential_type: str
    target_host: str
    provenance: CredentialProvenance
    state: CredentialState
    authorized_for_hosts: list = field(default_factory=list)
    authorized_for_protocols: list = field(default_factory=list)
    validated_at: Optional[float] = None
    discovered_at: float = field(default_factory=time.time)
    fingerprint: Optional[str] = None

    def to_evidence_dict(self) -> dict:
        """Serialization for the ledger: no plaintext, no reusable secret."""
        return {
            "credential_id": self.credential_id,
            "credential_type": self.credential_type,
            "target_host": self.target_host,
            "provenance": self.provenance.value,
            "state": self.state.value,
            "authorized_for_hosts": list(self.authorized_for_hosts),
            "authorized_for_protocols": list(self.authorized_for_protocols),
            "fingerprint": self.fingerprint,
            "validated_at": self.validated_at,
            "discovered_at": self.discovered_at,
        }


class CredentialVault:
    """Process-local credential storage. Plaintext lives HERE only."""

    def __init__(self) -> None:
        self._secrets: dict = {}
        self._references: dict = {}
        self._lock = threading.Lock()

    def store(self, credential_type: str, secret: str, target_host: str,
              provenance: CredentialProvenance) -> CredentialReference:
        """Store a credential and return its reference. Secret never leaves."""
        if not credential_type:
            raise ValueError("credential_type is required")
        if not isinstance(secret, str) or secret == "":
            # Blank/empty default credentials are represented explicitly
            # rather than by an empty string, to keep evidence meaningful.
            raise ValueError("secret must be a non-empty string "
                             "(use placeholder '<blank>' if applicable)")
        if not isinstance(provenance, CredentialProvenance):
            raise TypeError("provenance must be a CredentialProvenance")
        fingerprint = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        from uuid import uuid4
        cred_id = str(uuid4())
        reference = CredentialReference(
            credential_id=cred_id,
            credential_type=credential_type,
            target_host=target_host,
            provenance=provenance,
            state=CredentialState.DISCOVERED,
            fingerprint=fingerprint,
        )
        with self._lock:
            self._secrets[cred_id] = secret
            self._references[cred_id] = reference
        return reference

    def retrieve(self, credential_id: str) -> Optional[str]:
        """Retrieve plaintext. Process-local only; callers must not log it."""
        with self._lock:
            return self._secrets.get(credential_id)

    def get_reference(self, credential_id: str) -> Optional[CredentialReference]:
        with self._lock:
            return self._references.get(credential_id)

    def mark_validated(self, credential_id: str, target_host: str,
                       protocol: str) -> None:
        with self._lock:
            ref = self._references.get(credential_id)
            if ref is None:
                return
            ref.state = CredentialState.VALIDATED
            ref.validated_at = time.time()
            if target_host not in ref.authorized_for_hosts:
                ref.authorized_for_hosts.append(target_host)
            if protocol not in ref.authorized_for_protocols:
                ref.authorized_for_protocols.append(protocol)

    def authorize(self, credential_id: str, target_host: str,
                  protocol: str) -> None:
        """Promote a validated credential to AUTHORIZED for a scope."""
        with self._lock:
            ref = self._references.get(credential_id)
            if ref is None:
                return
            if ref.state is CredentialState.VALIDATED:
                ref.state = CredentialState.AUTHORIZED
            if target_host not in ref.authorized_for_hosts:
                ref.authorized_for_hosts.append(target_host)
            if protocol not in ref.authorized_for_protocols:
                ref.authorized_for_protocols.append(protocol)

    def is_authorized_for(self, credential_id: str, target_host: str,
                          protocol: str) -> bool:
        """Exact per-target/per-protocol reuse check (fail closed)."""
        with self._lock:
            ref = self._references.get(credential_id)
            if ref is None:
                return False
            if ref.state not in (CredentialState.VALIDATED,
                                 CredentialState.AUTHORIZED):
                return False
            return (target_host in ref.authorized_for_hosts
                    and protocol in ref.authorized_for_protocols)

    def revoke(self, credential_id: str) -> None:
        with self._lock:
            self._secrets.pop(credential_id, None)
            ref = self._references.get(credential_id)
            if ref:
                ref.state = CredentialState.REVOKED

    def wipe(self) -> None:
        """Emergency wipe — removes all plaintext secrets."""
        with self._lock:
            self._secrets.clear()

    def references_for_target(self, target_host: str) -> list:
        with self._lock:
            return [r for r in self._references.values()
                    if r.target_host == target_host]


__all__ = [
    "CredentialProvenance",
    "CredentialReference",
    "CredentialState",
    "CredentialVault",
]
