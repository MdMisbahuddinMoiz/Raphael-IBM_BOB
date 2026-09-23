"""Pure deterministic verification projections used by D16 matrix rows."""
from __future__ import annotations

import json
from typing import assert_never

from raphael_ibm_bob.runtime import RuntimeResult
from tests.d16_autonomous_loop_model import (
    ObservationRoute,
    VerificationResult,
    VerificationStatus,
)


def verify_listing(
    result: RuntimeResult,
    expected_marker: str,
) -> VerificationResult:
    """Check a governed LIST payload without choosing a next action."""
    execution = result.execution
    observed_payload = json.dumps(
        {} if execution is None else execution.evidence,
        sort_keys=True,
    )
    confirmed = (
        execution is not None
        and execution.success
        and expected_marker in observed_payload
    )
    status = (
        VerificationStatus.CONFIRMED
        if confirmed
        else VerificationStatus.FALSIFIED
    )
    return VerificationResult(status, expected_marker, observed_payload)


def route_for_verification(
    verification: VerificationResult,
) -> ObservationRoute:
    """Map a factual verification result to a normalized state route."""
    match verification.status:
        case VerificationStatus.CONFIRMED:
            return ObservationRoute.VERIFICATION_SUCCESS
        case VerificationStatus.FALSIFIED:
            return ObservationRoute.VERIFICATION_FAILURE
        case unreachable:
            assert_never(unreachable)


__all__ = ["route_for_verification", "verify_listing"]
