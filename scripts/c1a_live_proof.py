"""scripts.c1a_live_proof — controlled live-proof readiness gate.

CORRECTION 5: live proof is NOT authorized here. This entrypoint reports
BLOCKED with the exact external blockers. It never fabricates provider
execution, never claims M1/M2/M5 VERIFIED, and never emits COMPLETE.

Statuses are derived from the REAL repository state; nothing is asserted
without observation.

The real pinned T3MP3ST provider may be present (compiled checkout at
``T3MP3ST_PROVIDER_DIST``). When present, ``provider_status`` is
``AVAILABLE`` and the provider can execute in the sandbox; the gate still
reports BLOCKED while ``live_proof_authorized`` is false.
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
    MIN_NODE_VERSION,
    T3MP3ST_BRIDGE_SHA256,
    T3MP3STAdapter,
    launcher_digest_ok,
)
from raphael_ibm_bob.isolation_substrate import (  # noqa: E402
    FIXTURE_SHA256,
    PROVIDER_PIN,
    node_version_ok,
    validate_bridge,
)

#: Real provider checkout (compiled dist/). Override with env var.
PROVIDER_DIST = os.environ.get(
    "T3MP3ST_PROVIDER_DIST", "/home/moiz/audit-repos/T3MP3ST/dist")
PROVIDER_REPO = os.environ.get(
    "T3MP3ST_PROVIDER_REPO", "/home/moiz/audit-repos/T3MP3ST")


@dataclass(frozen=True)
class Prerequisite:
    name: str
    ok: bool
    detail: str


def provider_dist_available(dist: str = PROVIDER_DIST) -> bool:
    return (os.path.isdir(dist)
            and os.path.isfile(os.path.join(dist, "arsenal", "binary.js")))


def _node_version(node: Optional[str]) -> str:
    if not node:
        return ""
    import subprocess
    try:
        return subprocess.run([node, "--version"], capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _provider_repo_pin() -> Tuple[bool, str]:
    """Read the checkout HEAD without invoking git (no subprocess)."""
    head = os.path.join(PROVIDER_REPO, ".git", "HEAD")
    try:
        with open(head, "r", encoding="utf-8") as handle:
            value = handle.read().strip()
    except OSError as exc:
        return False, f"unreadable:{type(exc).__name__}"
    if value.startswith("ref:"):
        ref = os.path.join(PROVIDER_REPO, ".git",
                           value.split(":", 1)[1].strip())
        try:
            with open(ref, "r", encoding="utf-8") as handle:
                value = handle.read().strip()
        except OSError as exc:
            return False, f"unreadable:{type(exc).__name__}"
    return value == PROVIDER_PIN, value


def gather_prerequisites(repo_root: Path = ROOT,
                         authorized: Optional[bool] = None) -> List[Prerequisite]:
    effective_authorized = (LIVE_PROOF_AUTHORIZED if authorized is None
                            else bool(authorized))
    launcher = repo_root / "provider" / "c1a_launcher.js"
    bridge = repo_root / "provider" / "t3mp3st_bridge.js"
    node = shutil.which("node")
    node_ver = _node_version(node)
    dist_ok = provider_dist_available()
    pin_ok, pin_detail = _provider_repo_pin()
    try:
        validate_bridge(str(bridge), T3MP3ST_BRIDGE_SHA256)
        bridge_ok = True
    except Exception as exc:  # noqa: BLE001 - probe only
        bridge_ok = False
        bridge = f"{bridge} ({type(exc).__name__})"
    return [
        Prerequisite("live_proof_authorized", effective_authorized,
                     "authorized by operator" if effective_authorized
                     else "not authorized (CORRECTION 5)"),
        Prerequisite("t3mp3st_provider_present", dist_ok,
                     PROVIDER_DIST if dist_ok
                     else f"absent: {PROVIDER_DIST}"),
        Prerequisite("t3mp3st_provider_pin_matches", pin_ok, pin_detail),
        Prerequisite("provider_pin_declared", bool(PROVIDER_PIN), PROVIDER_PIN),
        Prerequisite("fixture_pin_declared", len(FIXTURE_SHA256) == 64,
                     FIXTURE_SHA256),
        Prerequisite("c1a_launcher_present", launcher.is_file(),
                     str(launcher)),
        Prerequisite("c1a_launcher_digest_pinned",
                     launcher.is_file() and launcher_digest_ok(
                         launcher, LAUNCHER_SHA256),
                     LAUNCHER_SHA256),
        Prerequisite("t3mp3st_bridge_present", bridge_ok, str(bridge)),
        Prerequisite("t3mp3st_bridge_digest_pinned", bridge_ok,
                     T3MP3ST_BRIDGE_SHA256),
        Prerequisite("node_runtime_present", bool(node), node or "missing"),
        Prerequisite("node_version_meets_t3mp3st_minimum",
                     bool(node) and node_version_ok(node_ver, MIN_NODE_VERSION),
                     f"{node_ver or 'missing'} (min "
                     f"v{'.'.join(str(n) for n in MIN_NODE_VERSION)})"),
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
    provider_present = any(
        p.name == "t3mp3st_provider_present" and p.ok for p in prerequisites)
    # Live proof requires authorization AND the real provider; while
    # unauthorized it is BLOCKED regardless of provider availability.
    status = "BLOCKED" if (blockers or not effective_authorized) else "READY"
    return {
        "status": status,
        "live_proof_authorized": effective_authorized,
        "provider_status": ("AVAILABLE" if provider_present
                            else "UNAVAILABLE (external dependency)"),
        "provider_dist": PROVIDER_DIST,
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
