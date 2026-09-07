"""probes.auth_behavior_probe — independent behavioral probe for the
authkit hero.

This probe is independently authored from the test_login.py / test_auth.py
test suite. It exercises the same session.validate_session entry point
but with a different surface and a different assertion shape:

    - It does NOT subclass unittest.TestCase.
    - It does NOT import any test_* module.
    - It does NOT copy any test assertion.
    - It is callable both as a script and as a library function.

The probe is the M6 "independent behavior probe" that the QualityGate's
condition D requires. When the authkit's validate_session is buggy, the
probe returns (False, [details...]) meaning behavior is broken. When the
authkit is correctly fixed, the probe returns (True, []).

Protocol:

    result = run_probe()
    if not result.ok:
        for detail in result.failures:
            print(detail)
        sys.exit(2)
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass, field
from typing import List

# Make the fixtures/ tree importable when the probe runs from any cwd.
_FIXURES_PARENT = str(pathlib.Path(__file__).resolve().parent.parent)
if _FIXURES_PARENT not in sys.path:
    sys.path.insert(0, _FIXURES_PARENT)

from fixtures.authkit.session import validate_session  # noqa: E402


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    failures: List[str] = field(default_factory=list)


# Each scenario is a (token, claimed_user_id, expected_outcome) tuple.
# `expected_outcome=True` means validate_session must accept.
# `expected_outcome=False` means validate_session must reject.
SCENARIOS = [
    ("tok-alice-fresh", "alice", True,  "fresh alice token is accepted"),
    ("tok-bob-fresh",   "bob",   True,  "fresh bob token is accepted"),
    ("tok-alice-stale", "alice", False, "expired alice token is rejected"),
    ("tok-bob-stale",   "bob",   False, "expired bob token is rejected"),
    ("tok-cross",       "bob",   False, "alice token rejected when claimed by bob"),
    ("tok-cross",       "alice", True,  "alice token accepted when claimed by alice"),
    ("tok-alice-fresh", "bob",   False, "alice token rejected when claimed by bob"),
    ("tok-bob-fresh",   "alice", False, "bob token rejected when claimed by alice"),
    ("tok-does-not-exist", "alice", False, "unknown token rejected"),
    ("",                 "alice", False, "empty token rejected"),
]


def run_probe() -> ProbeResult:
    """Run every scenario and return a ProbeResult."""
    failures: List[str] = []
    for token, claimed, expected, desc in SCENARIOS:
        actual = bool(validate_session(token, claimed))
        if actual != expected:
            failures.append(
                f"FAIL: {desc!r}: "
                f"validate_session({token!r}, {claimed!r}) "
                f"returned {actual}, expected {expected}"
            )
    return ProbeResult(ok=not failures, failures=failures)


if __name__ == "__main__":
    result = run_probe()
    if result.ok:
        print("OK: independent behavior probe passed")
        sys.exit(0)
    for f in result.failures:
        print(f)
    sys.exit(2)
