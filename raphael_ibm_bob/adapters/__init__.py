"""raphael_ibm_bob.adapters — explicit adapter layer between legacy Raphael and
the IBM BOB MVP seams.

M1 ships only the index in `legacy.py`. M2+ will add concrete adapter
bodies such as `broker_legacy.py`, `policy_legacy.py`, etc. Every adapter
introduced at M2+ MUST be reflected in `legacy.py` so that the seam's
authoritative documentation stays in sync with the actual code.
"""
from raphael_ibm_bob.adapters.legacy import (
    ADAPT,
    ALL_SPECS,
    AdapterSpec,
    BROKER_SPECS,
    EVIDENCE_SPECS,
    FALSIFIER_SPECS,
    ISOLATE,
    PLANNER_SPECS,
    POLICY_SPECS,
    QUALITYGATE_SPECS,
    REPLACE,
    REPLANNER_SPECS,
    REUSE,
    RUNNER_SPECS,
    RUNTIME_SPECS,
    UNKNOWN,
    VERIFIER_SPECS,
    action_counts,
    specs_for,
)

__all__ = [
    "AdapterSpec",
    "ADAPT",
    "ALL_SPECS",
    "BROKER_SPECS",
    "EVIDENCE_SPECS",
    "FALSIFIER_SPECS",
    "ISOLATE",
    "PLANNER_SPECS",
    "POLICY_SPECS",
    "QUALITYGATE_SPECS",
    "REPLACE",
    "REPLANNER_SPECS",
    "REUSE",
    "RUNNER_SPECS",
    "RUNTIME_SPECS",
    "UNKNOWN",
    "VERIFIER_SPECS",
    "action_counts",
    "specs_for",
]