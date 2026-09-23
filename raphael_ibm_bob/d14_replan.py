"""D14's immutable replan decision contract.

This module only describes a planner result.  It does not invoke capabilities,
consult policy, or persist evidence.
"""
from __future__ import annotations

from dataclasses import dataclass

from raphael_ibm_bob.capability_selector import ExecutionPlan
from raphael_ibm_bob.contracts import FocusedContext
from raphael_ibm_bob.d14_planner import NextAction


@dataclass(frozen=True, slots=True)
class ReplanDecision:
    """Planner output describing whether a parent plan should be replaced."""

    should_replan: bool
    reason: str
    parent_plan_id: str
    trigger_hypothesis_id: str | None
    focused_context: FocusedContext | None
    execution_plan: ExecutionPlan | None
    next_action: NextAction | None


__all__ = ["ReplanDecision"]
