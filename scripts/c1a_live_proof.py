"""scripts.c1a_live_proof — controlled live-proof readiness gate.

CORRECTION 5: live proof is NOT authorized here. This entrypoint reports
BLOCKED with the exact external blockers. It never fabricates provider
execution, never claims M1/M2/M5 VERIFIED, and never emits COMPLETE.

Statuses are derived from the REAL repository state; nothing is asserted
without observation.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: CORRECTION 5 — do not flip this without explicit authorization.
LIVE_PROOF_AUTHORIZED = False

from raphael_ibm_bob.adapters.t3mp3st_adapter import (  # noqa: E402
    LAUNCHER_SHA256,
    T3MP3STAdapter,
    launcher_digest_ok,
)
from raphael_ibm_bob.isolation_substrate import (  # noqa: E402
    FIXTURE_SHA256,
    PROVIDER_PIN,
)


@dataclass(frozen=True)
class Prerequisite:
    name: str
    ok: bool
    detail: str


def _provider_available() -> Tuple[bool, str]:
    try:
        T3MP3STAdapter().invoke(None, None)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001 - probe only
        return False, f"{type(exc).__name__}:{exc}"
    return True, "invoked"


def gather_prerequisites(repo_root: Path = ROOT,
                         authorized: Optional[bool] = None) -> List[Prerequisite]:
    effective_authorized = (LIVE_PROOF_AUTHORIZED if authorized is None
                            else bool(authorized))
    provider_ok, provider_detail = _provider_available()
    launcher = repo_root / "provider" / "c1a_launcher.js"
    return [
        Prerequisite("live_proof_authorized", effective_authorized,
                     "authorized by operator" if effective_authorized
                     else "not authorized (CORRECTION 5)"),
        Prerequisite("t3mp3st_provider_present", provider_ok, provider_detail),
        Prerequisite("provider_pin_declared", bool(PROVIDER_PIN), PROVIDER_PIN),
        Prerequisite("fixture_pin_declared", len(FIXTURE_SHA256) == 64,
                     FIXTURE_SHA256),
        Prerequisite("c1a_launcher_present", launcher.is_file(),
                     str(launcher)),
        Prerequisite("c1a_launcher_digest_pinned",
                     launcher.is_file() and launcher_digest_ok(
                         launcher, LAUNCHER_SHA256),
                     LAUNCHER_SHA256),
        Prerequisite("node_runtime_present", bool(shutil.which("node")),
                     shutil.which("node") or "missing"),
        Prerequisite("bwrap_present", bool(shutil.which("bwrap")),
                     shutil.which("bwrap") or "missing"),
    ]


def evaluate(
    repo_root: Path = ROOT,
    *,
    authorized: Optional[bool] = None,
) -> dict:
    effective_authorized = (LIVE_PROOF_AUTHORIZED if authorized is None
                            else bool(authorized))
    prerequisites = gather_prerequisites(repo_root, authorized)
    blockers = [p.name for p in prerequisites if not p.ok]
    status = "READY" if not blockers else "BLOCKED"
    return {
        "status": status,
        "live_proof_authorized": effective_authorized,
        "provider_status": ("available" if any(
            p.name == "t3mp3st_provider_present" and p.ok for p in prerequisites)
            else "UNAVAILABLE (external dependency)"),
        "blockers": blockers,
        "prerequisites": [asdict(p) for p in prerequisites],
        "m1_status": "NOT_EXECUTED",
        "m2_status": "NOT_EXECUTED",
        "m5_status": "NOT_EXECUTED",
        "seccomp_status": "NOT_EXECUTED",
        "claims": {
            "provider_executed": False,
            "mission_complete": False,
            "verified": False,
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    result = evaluate()
    print(json.dumps(result, indent=2, sort_keys=True))
    # BLOCKED is the correct, expected outcome at this stage.
    return 2 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
