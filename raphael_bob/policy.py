"""raphael_bob.policy — BOB MVP Policy implementation.

FAIL-CLOSED.

For an `ActionRequest`, returns a `PolicyDecision` with either ALLOW or DENY.
Reasons are deterministic strings so tests can assert them.

Decision inputs:
    - Capability must be one of READ/LIST/SEARCH/WRITE/RUN_TEST.
    - Target must resolve under the declared Workspace.
    - Capability-specific invariants:
        WRITE: target must NOT exist as a directory; the resolved path
               must be inside the workspace and the parent directory must
               exist.
        READ:  target must be a regular file inside the workspace.
        LIST:  target must be a directory inside the workspace.
        SEARCH: target must be a directory inside the workspace.
        RUN_TEST: target must be a regular file ending in test_*.py or
                  *_test.py and live inside the workspace.
    - Mission scope, if set, is treated as a substring constraint on the
      target. A target whose normalized form does not contain the mission
      scope substring is denied with `reason="scope"`.

This module NEVER performs the action. It only decides.

Legacy semantics:
    src/orchestrator/brain/scope_parser.py (ScopeParser, fail-closed) is
    the source of inspiration; the BOB policy grammar is different.
    src/orchestrator/brain/rate_limiter.py is not used at M2 because the
    MVP has no time-window rate limit semantics.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from raphael_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
    Mission,
    PolicyDecision,
)
from raphael_bob.workspace import Workspace


class BOBPolicy:
    """MVP Policy. Fail-closed. Pure (no side effects)."""

    def __init__(self, workspace: Workspace):
        self._workspace = workspace

    def consult(self, request: ActionRequest, mission: Mission) -> PolicyDecision:
        # 1. Capability must be in the MVP allow-list.
        if request.capability not in {
            Capability.READ,
            Capability.LIST,
            Capability.SEARCH,
            Capability.WRITE,
            Capability.RUN_TEST,
        }:
            cap_str = getattr(request.capability, "value", str(request.capability))
            return self._deny(request, f"capability-not-allowed:{cap_str}")

        # 2. Target must be a non-empty string.
        if not request.target or not isinstance(request.target, str):
            return self._deny(request, "target-empty-or-invalid")

        # 3. Workspace containment check.
        try:
            resolved = self._workspace.resolve(request.target)
        except PermissionError:
            return self._deny(request, "target-outside-workspace")
        except FileNotFoundError:
            # READ/LIST/SEARCH/RUN_TEST need the path to exist; WRITE
            # needs the parent to exist. We let capability checks below
            # decide whether existence matters.
            resolved = None  # type: ignore[assignment]

        # 4. Mission scope substring check.
        if mission.scope:
            target_norm = request.target.replace("\\", "/")
            if mission.scope not in target_norm:
                return self._deny(request, "scope-mismatch")

        # 5. Capability-specific invariants.
        if request.capability == Capability.READ:
            if resolved is None:
                return self._deny(request, "read-target-missing")
            if not resolved.is_file():
                return self._deny(request, "read-target-not-file")
            return self._allow(request)

        if request.capability == Capability.LIST:
            if resolved is None:
                return self._deny(request, "list-target-missing")
            if not resolved.is_dir():
                return self._deny(request, "list-target-not-directory")
            return self._allow(request)

        if request.capability == Capability.SEARCH:
            if resolved is None:
                return self._deny(request, "search-target-missing")
            if not resolved.is_dir():
                return self._deny(request, "search-target-not-directory")
            return self._allow(request)

        if request.capability == Capability.WRITE:
            # WRITE allows the target to not yet exist; its parent must.
            assert resolved is not None  # workspace.resolve did not raise
            if resolved.exists() and resolved.is_dir():
                return self._deny(request, "write-target-is-directory")
            parent = resolved.parent
            if not parent.is_dir():
                return self._deny(request, "write-parent-missing")
            return self._allow(request)

        if request.capability == Capability.RUN_TEST:
            if resolved is None:
                return self._deny(request, "run_test-target-missing")
            if not resolved.is_file():
                return self._deny(request, "run_test-target-not-file")
            name = resolved.name
            if not (name.startswith("test_") and name.endswith(".py")) and \
               not (name.endswith("_test.py")):
                return self._deny(request, "run_test-name-pattern")
            return self._allow(request)

        # Unreachable: capability allow-list is exhaustive above.
        return self._deny(request, f"unhandled-capability:{request.capability.value}")

    # Helpers -----------------------------------------------------------------

    def _allow(self, request: ActionRequest) -> PolicyDecision:
        return PolicyDecision(
            sequence=request.sequence,
            decision=Decision.ALLOW,
            reason="ok",
            capability=request.capability,
            target=request.target,
            evidence_id=None,
        )

    def _deny(self, request: ActionRequest, reason: str) -> PolicyDecision:
        return PolicyDecision(
            sequence=request.sequence,
            decision=Decision.DENY,
            reason=reason,
            capability=request.capability,
            target=request.target,
            evidence_id=None,
        )


__all__ = ["BOBPolicy"]