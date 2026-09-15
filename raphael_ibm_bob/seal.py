"""raphael_ibm_bob.seal — T1-3 tamper-evident evidence sealing.

The M3 JSONL ledger is append-only by API but a plain file on disk:
accidental edits, partial writes, or reordered records would otherwise
be silent. The seal is a deterministic SHA-256 hash chain over the
canonical records plus a sidecar manifest (`seal.json`); verification
recomputes and compares. It detects modification, deletion,
reordering, and malformed records.

Adapted concept (not copied code):
- Decepticon evidence chain-of-custody manifest + HMAC-chained RoE
  ledger (`packages/decepticon/decepticon/tools/evidence/tools.py`,
  `.../middleware/_audit_sink.py`): hash the artifacts, verify later.

Deliberately NOT imported: HMAC key management. This seal is UNKEYED
by design — it proves integrity against editing/accidents, not
against an attacker holding write access (who could re-seal). No
secrets are created, stored, or committed. A keyed variant is
deferred until a key-management story exists.

The existing ledger semantics are untouched: sealing reads records
and writes one sidecar file; validation in `audit_runs.py` does not
require seals (old runs stay valid).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from raphael_ibm_bob.evidence_ledger import LedgerReader

SEAL_VERSION = "seal-v1"
SEAL_FILENAME = "seal.json"
_GENESIS = "raphael-seal-v1:genesis"


def _canonical(record: Dict[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def _chain(records: List[Dict[str, Any]]) -> str:
    head = hashlib.sha256(_GENESIS.encode("utf-8")).hexdigest()
    for record in records:
        head = hashlib.sha256(
            (head + _canonical(record)).encode("utf-8")).hexdigest()
    return head


def compute_seal(run_dir: Path) -> Dict[str, Any]:
    """Compute (but do not write) the seal manifest for a run dir."""
    run_dir = Path(run_dir)
    reader = LedgerReader(run_dir / "evidence.jsonl")
    records = list(reader.records())  # raises ValueError if corrupt
    return {
        "version": SEAL_VERSION,
        "algorithm": "sha256-chain",
        "run_id": run_dir.name,
        "record_count": len(records),
        "head": _chain(records),
    }


def write_seal(run_dir: Path) -> Path:
    """Write a deterministic `seal.json` sidecar; return its path."""
    run_dir = Path(run_dir)
    manifest = compute_seal(run_dir)
    path = run_dir / SEAL_FILENAME
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return path


def verify_seal(run_dir: Path) -> Tuple[bool, str]:
    """Recompute and compare. Returns (ok, reason)."""
    run_dir = Path(run_dir)
    seal_path = run_dir / SEAL_FILENAME
    if not seal_path.is_file():
        return False, "missing-seal"
    try:
        manifest = json.loads(seal_path.read_text(encoding="utf-8"))
    except ValueError:
        return False, "malformed-seal"
    if not isinstance(manifest, dict):
        return False, "malformed-seal"
    if manifest.get("version") != SEAL_VERSION:
        return False, f"unsupported-seal-version:{manifest.get('version')}"
    if manifest.get("run_id") != run_dir.name:
        return False, "seal-run-id-mismatch"
    try:
        expected = compute_seal(run_dir)
    except ValueError:
        return False, "malformed-ledger"
    except OSError as exc:
        return False, f"unreadable-ledger:{type(exc).__name__}"
    if manifest.get("record_count") != expected["record_count"]:
        return False, (
            f"record-count-mismatch:sealed={manifest.get('record_count')} "
            f"observed={expected['record_count']}")
    if manifest.get("head") != expected["head"]:
        return False, "head-mismatch:ledger-modified-reordered-or-deleted"
    return True, "seal-ok"


__all__ = [
    "SEAL_VERSION",
    "SEAL_FILENAME",
    "compute_seal",
    "write_seal",
    "verify_seal",
]
