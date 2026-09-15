"""raphael_ibm_bob.harness.events — event stream folded from evidence.

No separate event bus: events are a deterministic projection over
committed ledger records (DeepSeek `session-projection` pattern),
plus two clearly-marked synthetic context events. Replaying the same
ledger always yields the same event list.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

EVENT_TYPES = (
    "SESSION_CREATED",
    "MISSION_STARTED",
    "PLAN_CREATED",
    "ACTION_REQUESTED",
    "POLICY_DECISION",
    "EXECUTION_RESULT",
    "EVIDENCE_RECORDED",
    "FINDING_CHANGED",
    "VERIFICATION_RESULT",
    "FALSIFICATION_RESULT",
    "REPLAN_CREATED",
    "GATE_EVALUATED",
    "RUN_COMPLETED",
    "RUN_REFUSED",
    "RUN_FAILED",
    "RUN_CANCELLED",
)

_TERMINAL_EVENTS = {
    "completed": "RUN_COMPLETED",
    "refused": "RUN_REFUSED",
    "failed": "RUN_FAILED",
    "cancelled": "RUN_CANCELLED",
}


def collect_events(records: List[Dict[str, Any]], *,
                   session_id: str, run_id: str, mission_id: str,
                   terminal: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fold ledger records into a sequenced event list.

    `terminal` overrides the derived terminal event; when None it is
    derived from the last gate record (complete/refuse). Unknown gate
    decisions yield no terminal event.
    """
    events: List[Dict[str, Any]] = [
        {"seq": 0, "type": "SESSION_CREATED", "session_id": session_id,
         "synthetic": True},
        {"seq": 0, "type": "MISSION_STARTED", "session_id": session_id,
         "run_id": run_id, "mission_id": mission_id, "synthetic": True},
    ]
    ordered = sorted(records, key=lambda r: (r.get("seq", 0)))
    seen_plans: List[str] = []
    last_gate = None
    for rec in ordered:
        kind = rec.get("kind")
        seq = rec.get("seq", 0)
        if kind == "request":
            plan_id = rec.get("plan_id")
            if plan_id and plan_id not in seen_plans:
                seen_plans.append(plan_id)
                events.append({"seq": seq, "type": "PLAN_CREATED",
                               "run_id": run_id, "plan_id": plan_id})
            events.append({"seq": seq, "type": "ACTION_REQUESTED",
                           "run_id": run_id,
                           "capability": rec.get("capability"),
                           "target": rec.get("target"),
                           "requester": rec.get("requester"),
                           "plan_id": plan_id})
        elif kind == "decision":
            events.append({"seq": seq, "type": "POLICY_DECISION",
                           "run_id": run_id,
                           "decision": rec.get("decision"),
                           "reason": rec.get("reason"),
                           "request_seq": rec.get("request_seq")})
        elif kind == "result":
            events.append({"seq": seq, "type": "EXECUTION_RESULT",
                           "run_id": run_id,
                           "success": rec.get("success"),
                           "request_seq": rec.get("request_seq"),
                           "artifact_ref": rec.get("artifact_ref")})
        elif kind == "evidence":
            producer = rec.get("producer", "")
            payload = rec.get("payload", {}) or {}
            inner = payload.get("kind", "")
            if producer == "verifier":
                events.append({"seq": seq,
                               "type": "VERIFICATION_RESULT",
                               "run_id": run_id,
                               "kind": inner,
                               "finding_id": rec.get("finding_id")})
            elif producer == "falsifier":
                events.append({"seq": seq,
                               "type": "FALSIFICATION_RESULT",
                               "run_id": run_id,
                               "kind": inner,
                               "finding_id": rec.get("finding_id")})
            elif producer == "replanner":
                events.append({"seq": seq, "type": "REPLAN_CREATED",
                               "run_id": run_id,
                               "parent_plan_id": payload.get(
                                   "parent_plan_id"),
                               "plan_b_id": payload.get("plan_b_id"),
                               "refuted_finding_id": payload.get(
                                   "refuted_finding_id")})
            elif producer in ("policy", "execution"):
                continue  # represented by decision/result events
            else:
                events.append({"seq": seq, "type": "EVIDENCE_RECORDED",
                               "run_id": run_id, "producer": producer,
                               "evidence_id": rec.get("evidence_id")})
        elif kind == "finding":
            events.append({"seq": seq, "type": "FINDING_CHANGED",
                           "run_id": run_id,
                           "finding_id": rec.get("finding_id"),
                           "state": rec.get("state"),
                           "prev_state": rec.get("prev_state")})
        elif kind == "gate":
            last_gate = rec
            events.append({"seq": seq, "type": "GATE_EVALUATED",
                           "run_id": run_id,
                           "decision": rec.get("decision"),
                           "checks": list(rec.get("checks", ()))})
    terminal_event = terminal
    if terminal_event is None and last_gate is not None:
        terminal_event = {"complete": "completed",
                          "refuse": "refused"}.get(
                              last_gate.get("decision"))
    if terminal_event in _TERMINAL_EVENTS:
        terminal_event = _TERMINAL_EVENTS[terminal_event]
    if terminal_event in _TERMINAL_EVENTS.values():
        top = max([e["seq"] for e in events] + [0])
        events.append({"seq": top + 1, "type": terminal_event,
                       "run_id": run_id, "synthetic": True})
    events.sort(key=lambda e: (e["seq"], e["type"]))
    return events


__all__ = [
    "EVENT_TYPES",
    "collect_events",
]
