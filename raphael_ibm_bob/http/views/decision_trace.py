"""raphael_ibm_bob.http.views.decision_trace — read-only operator screen.

Renders the RAPHAEL **Decision Trace**: the observable, persisted
decision-and-evidence chain that explains how a run moved from mission
to a Quality Gate verdict.

This is NOT a chain-of-thought viewer. It renders only what the
governed system already persisted and exposes through `harness.api`:
mission, observable model proposal, selected skill/role, IBM BOB
policy decision, execution result, evidence records, finding state,
verification, falsification, replan, independent probe, and the gate
record. No hidden model reasoning is read, stored, or displayed.

Read-only: every data access goes through `harness.api`. The module
cannot execute, authorize, or persist anything.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any, Dict, List, Optional, Tuple

from raphael_ibm_bob.harness import api

_CAP_READ = ("read", "list", "search")

STAGES: Tuple[Tuple[str, str], ...] = (
    ("mission", "MISSION"),
    ("context", "CONTEXT"),
    ("proposal", "MODEL PROPOSAL"),
    ("specialist", "SPECIALIST SELECTION"),
    ("policy", "IBM BOB POLICY"),
    ("execution", "EXECUTION"),
    ("evidence", "EVIDENCE"),
    ("verification", "VERIFICATION"),
    ("falsification", "FALSIFICATION"),
    ("replan", "REPLAN"),
    ("probe", "INDEPENDENT PROBE"),
    ("gate", "QUALITY GATE"),
)

_STATUS_LABEL = {
    "complete": "COMPLETE",
    "active": "ACTIVE",
    "pending": "PENDING",
    "attention": "ATTENTION",
    "refused": "REFUSED",
    "notrun": "NOT RUN",
    "info": "—",
}


# ---------------------------------------------------------------------------
# small formatting helpers
# ---------------------------------------------------------------------------

def _e(value: Any) -> str:
    if value is None:
        return ""
    return escape(str(value))


def _fmt_ts(ts: Any) -> str:
    """Render an epoch timestamp (ns/ms/s) as UTC HH:MM:SS."""
    try:
        n = int(ts)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    if n > 10 ** 17:          # nanoseconds
        seconds = n / 1_000_000_000
    elif n > 10 ** 11:        # milliseconds
        seconds = n / 1_000
    else:                     # seconds
        seconds = n
    try:
        return datetime.fromtimestamp(
            seconds, tz=timezone.utc).strftime("%H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return ""


def _pill(text: str, kind: str) -> str:
    return f'<span class="pill {kind}">{_e(text)}</span>'


def _status_pill(status: str) -> str:
    kind = {
        "complete": "ok", "active": "info", "pending": "muted",
        "attention": "warn", "refused": "crit", "notrun": "muted",
        "info": "muted",
    }.get(status, "muted")
    return _pill(_STATUS_LABEL.get(status, status.upper()), kind)


def _kv(pairs: List[Tuple[str, Any]]) -> str:
    rows = "".join(
        f'<div class="kv"><span class="k">{_e(k)}</span>'
        f'<span class="v">{_e(v)}</span></div>'
        for k, v in pairs if v not in (None, ""))
    return f'<div class="kvlist">{rows}</div>'


def _table(headers: List[str], rows: List[List[Any]],
           mono: Tuple[int, ...] = ()) -> str:
    if not rows:
        return '<p class="empty">No records.</p>'
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = []
    for row in rows:
        cells = "".join(
            f'<td class="{"mono" if i in mono else ""}">{_e(c)}</td>'
            for i, c in enumerate(row))
        body.append(f"<tr>{cells}</tr>")
    return (f'<table class="dense"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table>')


def _checklist(names: Tuple[str, ...], passed: List[str]) -> str:
    items = []
    for name in names:
        ok = name in passed
        mark = "✓" if ok else "✕"
        cls = "ok" if ok else "crit"
        items.append(
            f'<div class="chk {cls}"><span class="mark">{mark}</span>'
            f'<span class="mono">{_e(name)}</span></div>')
    return f'<div class="checklist">{"".join(items)}</div>'


# ---------------------------------------------------------------------------
# data collection (read-only, harness.api only)
# ---------------------------------------------------------------------------

def _by_kind(records: List[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
    return [r for r in records if r.get("kind") == kind]


def _events_of(events: List[Dict[str, Any]],
               kind: str) -> List[Dict[str, Any]]:
    return [e for e in events if e.get("type") == kind]


def _state_name(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value or "")


def collect(run_id: str, *, runs_root, sessions_root,
            ) -> Dict[str, Any]:
    """Assemble the Decision Trace data model (read-only)."""
    run = api.get_run(run_id, runs_root)
    events = api.get_events(run_id, runs_root)
    records = api.get_evidence(run_id, runs_root)
    gate = api.get_gate(run_id, runs_root)
    tasks = api.get_tasks(run_id, runs_root)
    seal_ok, seal_reason = api.get_seal(run_id, runs_root)
    try:
        session = api.get_session(run.session_id, sessions_root)
    except Exception:
        session = None
    skills = {s.id: s for s in api.list_skills()}
    roles = {r.id: r for r in api.list_roles()}

    requests = _by_kind(records, "request")
    decisions = _by_kind(records, "decision")
    results = _by_kind(records, "result")
    evidence = _by_kind(records, "evidence")
    findings = _by_kind(records, "finding")

    return {
        "run": run,
        "run_id": run_id,
        "session": session,
        "events": events,
        "records": records,
        "gate": gate,
        "tasks": tasks,
        "seal": (seal_ok, seal_reason),
        "requests": requests,
        "decisions": decisions,
        "results": results,
        "evidence": evidence,
        "findings": findings,
        "skills": skills,
        "roles": roles,
        "actions": _events_of(events, "ACTION_REQUESTED"),
        "verifications": _events_of(events, "VERIFICATION_RESULT"),
        "falsifications": _events_of(events, "FALSIFICATION_RESULT"),
        "replans": _events_of(events, "REPLAN_CREATED"),
    }


# ---------------------------------------------------------------------------
# stage builders
# ---------------------------------------------------------------------------

def _stage_mission(d: Dict[str, Any]) -> Dict[str, Any]:
    mission = d["run"].mission
    return {
        "status": "complete",
        "summary": mission.description or mission.mission_id,
        "html": _kv([
            ("MISSION ID", mission.mission_id),
            ("OBJECTIVE", mission.description),
            ("SCOPE", mission.scope),
        ]) + (
            '<div class="sublabel">SUCCESS CRITERIA</div>'
            + ("<ul class=\"criteria\">" + "".join(
                f"<li>{_e(c)}</li>" for c in mission.criteria) + "</ul>"
               if mission.criteria else '<p class="empty">No criteria.</p>')
        ),
    }


def _active_task(tasks: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]],
                                                 Optional[str]]:
    root = (tasks or {}).get("root") or {}
    states = (tasks or {}).get("states") or {}
    subtasks = root.get("subtasks") or []
    for want in ("active", "pending", "completed"):
        for task in subtasks:
            if states.get(task.get("task_id")) == want:
                return task, states.get(task.get("task_id"))
    return (subtasks[0], states.get(subtasks[0].get("task_id"))
            if subtasks else (None, None))


def _stage_context(d: Dict[str, Any]) -> Dict[str, Any]:
    run = d["run"]
    task, task_state = _active_task(d["tasks"])
    role = (task or {}).get("role")
    skills_for_role = sorted(
        s.id for s in d["skills"].values() if getattr(s, "role", None) == role)
    target = (run.mission.problem or {}).get("symptom_target") or \
        (d["requests"][0].get("target") if d["requests"] else "")
    pairs = [
        ("TARGET", target),
        ("WORKSPACE", run.workspace_root),
        ("ACTIVE TASK", (task or {}).get("name")),
        ("TASK STATE", task_state),
        ("ACTIVE ROLE", role),
        ("AVAILABLE SKILLS", ", ".join(skills_for_role) or "—"),
        ("EVIDENCE RECORDS", len(d["records"])),
    ]
    return {
        "status": "info",
        "summary": (f"role={role or '—'} "
                    f"task={(task or {}).get('name') or '—'}"),
        "html": _kv(pairs),
    }


def _stage_proposal(d: Dict[str, Any]) -> Dict[str, Any]:
    rows = [[r.get("seq"), r.get("requester"), r.get("capability"),
             r.get("target"), (r.get("purpose") or "")[:80]]
            for r in d["requests"]]
    return {
        "status": "complete" if d["requests"] else "pending",
        "summary": f"{len(d['requests'])} observable proposal(s)",
        "html": (
            '<p class="note">Only the structured, submitted proposal is '
            'shown — capability, target, purpose, requester. Hidden model '
            'reasoning is not read or displayed.</p>'
            + _table(["SEQ", "REQUESTER", "CAPABILITY", "TARGET", "PURPOSE"],
                     rows, mono=(0, 1, 3))
        ),
    }


def _stage_specialist(d: Dict[str, Any]) -> Dict[str, Any]:
    rows = []
    for r in d["requests"]:
        requester = r.get("requester") or ""
        if not requester.startswith("skill:"):
            continue
        skill_id = requester.split("skill:", 1)[1]
        skill = d["skills"].get(skill_id)
        if skill is None:
            rows.append([skill_id, "—", r.get("capability"), "unregistered"])
            continue
        role = getattr(skill, "role", None) or "—"
        produced = ", ".join(getattr(skill, "evidence_produced", ()) or ())
        consumed = ", ".join(getattr(skill, "evidence_consumed", ()) or ())
        rows.append([role, skill_id, skill.capability.value,
                     f"produced: {produced or '—'}; consumed: {consumed or '—'}"])
    if not rows:
        return {
            "status": "info",
            "summary": "Runner-originated actions (no specialist declaration)",
            "html": ('<p class="note">These actions were proposed by the '
                     'governed Runner/Replanner path, not a declared '
                     'specialist skill.</p>'),
        }
    return {
        "status": "complete",
        "summary": f"{len(rows)} specialist selection(s)",
        "html": (
            '<div class="authority">ROLE ≠ PERMISSION — skill declarations '
            'describe work; IBM BOB Policy controls authorization.</div>'
            + _table(["ROLE", "SKILL", "CAPABILITY", "EVIDENCE CONTRACT"],
                     rows, mono=(1, 2))
        ),
    }


def _pretty_decision(value: str) -> str:
    return _pill((value or "").upper(),
                 "ok" if value == "allow" else "crit")


def _stage_policy(d: Dict[str, Any]) -> Dict[str, Any]:
    denied = [x for x in d["decisions"] if x.get("decision") == "deny"]
    rows = [[x.get("seq"), x.get("request_seq"), x.get("capability"),
             x.get("target"), (x.get("decision") or "").upper(),
             (x.get("reason") or "")[:90]]
            for x in d["decisions"]]
    status = "refused" if denied else ("complete" if d["decisions"] else "pending")
    return {
        "status": status,
        "summary": (f"{len(d['decisions'])} decision(s); "
                    f"{len(denied)} DENY"),
        "html": _table(
            ["SEQ", "REQ", "CAPABILITY", "TARGET", "DECISION", "REASON"],
            rows, mono=(0, 1, 3)),
    }


def _stage_execution(d: Dict[str, Any]) -> Dict[str, Any]:
    rows = [[x.get("seq"), x.get("request_seq"),
             "SUCCESS" if x.get("success") else "FAILED",
             (x.get("output") or x.get("error") or "")[:80],
             x.get("artifact_ref")]
            for x in d["results"]]
    return {
        "status": "complete" if d["results"] else "pending",
        "summary": f"{len(d['results'])} execution result(s)",
        "html": _table(["SEQ", "REQ", "RESULT", "OUTPUT", "ARTIFACT"],
                       rows, mono=(0, 1, 4)),
    }


def _stage_evidence(d: Dict[str, Any]) -> Dict[str, Any]:
    rows = [[x.get("evidence_id"), x.get("producer"),
             (x.get("payload") or {}).get("kind"),
             x.get("finding_id") or "—"]
            for x in d["evidence"]]
    seal_ok, seal_reason = d["seal"]
    seal = _pill("SEAL VALID" if seal_ok else f"SEAL {seal_reason.upper()}",
                 "ok" if seal_ok else "warn")
    return {
        "status": "complete" if d["evidence"] else "pending",
        "summary": f"{len(d['evidence'])} evidence record(s)",
        "html": f'<div class="row-inline">{seal}</div>' + _table(
            ["EVID", "PRODUCER", "KIND", "FINDING"],
            rows, mono=(0, 1, 2)),
    }


def _finding_state(records: List[Dict[str, Any]]) -> str:
    if not records:
        return "—"
    return (records[-1].get("state") or "").upper()


def _stage_verification(d: Dict[str, Any]) -> Dict[str, Any]:
    rows = [[x.get("seq"), x.get("finding_id"), x.get("kind")]
            for x in d["verifications"]]
    return {
        "status": "complete" if d["verifications"] else "pending",
        "summary": (f"{len(d['verifications'])} verification event(s)"
                    if d["verifications"] else "No verification recorded"),
        "html": _table(["SEQ", "FINDING", "KIND"], rows, mono=(1, 2)),
    }


def _stage_falsification(d: Dict[str, Any]) -> Dict[str, Any]:
    rows = [[x.get("seq"), x.get("finding_id"), x.get("kind")]
            for x in d["falsifications"]]
    counter = any(x.get("kind") == "counter-example"
                  for x in d["falsifications"])
    if d["falsifications"]:
        result = "PASS (remains verified)" if not counter else "REFUTED"
        status = "refused" if counter else "complete"
    else:
        result = "Not challenged"
        status = "pending"
    return {
        "status": status,
        "summary": result,
        "html": (
            '<p class="note">Negative-control challenge: can the apparent '
            'fix still fail? This is RAPHAEL’s key differentiator — apparent '
            'success is actively challenged.</p>'
            + _kv([("RESULT", result),
                   ("REFUTATION", "FOUND" if counter else "NOT FOUND")])
            + _table(["SEQ", "FINDING", "KIND"], rows, mono=(1, 2))
        ),
    }


def _stage_replan(d: Dict[str, Any]) -> Dict[str, Any]:
    if d["replans"]:
        rows = [[x.get("seq"), x.get("parent_plan_id"), x.get("plan_b_id"),
                 x.get("refuted_finding_id")]
                for x in d["replans"]]
        return {
            "status": "active",
            "summary": f"{len(d['replans'])} replan(s)",
            "html": _table(["SEQ", "PARENT PLAN", "NEW PLAN", "REFUTED FINDING"],
                           rows, mono=(1, 2, 3)),
        }
    refuted = [f for f in d["findings"] if f.get("state") == "refuted"]
    if refuted:
        return {
            "status": "attention",
            "summary": "Refuted finding without a replan record",
            "html": _kv([("TRIGGER", "Finding REFUTED"),
                         ("REPLAN", "not recorded")]),
        }
    return {
        "status": "info",
        "summary": "Not triggered",
        "html": _kv([
            ("REPLAN", "Not triggered"),
            ("REASON", "Initial remediation survived verification and "
                       "falsification."),
        ]),
    }


def _stage_probe(d: Dict[str, Any]) -> Dict[str, Any]:
    probes = [r for r in d["evidence"] if r.get("producer") == "probe"]
    if not probes:
        return {
            "status": "notrun",
            "summary": "NOT RUN",
            "html": _kv([("RESULT", "NOT RUN"),
                         ("NOTE", "No probe evidence was persisted.")]),
        }
    latest = probes[-1]
    payload = latest.get("payload") or {}
    ok = payload.get("allowed") is True or payload.get("result") == "passed"
    return {
        "status": "complete" if ok else "refused",
        "summary": "PASS" if ok else "FAIL",
        "html": _kv([
            ("RESULT", "PASS" if ok else "FAIL"),
            ("SOURCE", "independent probe"),
            ("EVIDENCE", latest.get("evidence_id")),
        ]),
    }


def _gate_condition_names() -> Tuple[str, ...]:
    return (
        "A:mission-criterion", "B:required-tests", "C:regression",
        "D:independent-behavior-probe", "E:scope", "F:evidence",
        "G:finding-state",
    )


def _stage_gate(d: Dict[str, Any]) -> Dict[str, Any]:
    gate = d["gate"]
    if gate is None:
        return {
            "status": "pending",
            "summary": "No gate record",
            "html": '<p class="empty">No Quality Gate record persisted.</p>',
        }
    checks = list(gate.get("checks", ()))
    names = _gate_condition_names()
    passed = [c for c in checks if c in names]
    failed = [c for c in names if c not in passed]
    decision = (gate.get("decision") or "").upper()
    status = "complete" if decision == "COMPLETE" else "refused"
    return {
        "status": status,
        "summary": f"{len(passed)}/{len(names)} conditions satisfied",
        "html": (
            f'<div class="gate-count">{len(passed)}/{len(names)} '
            f'conditions satisfied</div>'
            '<div class="authority">The Quality Gate is the SOLE '
            'authority permitted to declare COMPLETE.</div>'
            + _checklist(names, passed)
            + _kv([("FINAL", decision)]
                  + [("REASON", r) for r in gate.get("reasons", ())])),
    }


_STAGE_BUILDERS = {
    "mission": _stage_mission,
    "context": _stage_context,
    "proposal": _stage_proposal,
    "specialist": _stage_specialist,
    "policy": _stage_policy,
    "execution": _stage_execution,
    "evidence": _stage_evidence,
    "verification": _stage_verification,
    "falsification": _stage_falsification,
    "replan": _stage_replan,
    "probe": _stage_probe,
    "gate": _stage_gate,
}


def _build_stages(d: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for key, title in STAGES:
        stage = _STAGE_BUILDERS[key](d)
        stage.update({"key": key, "title": title})
        out.append(stage)
    return out


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------

def _pipeline(d: Dict[str, Any]) -> List[Tuple[str, str]]:
    caps = {r.get("capability") for r in d["requests"]}
    wrote = "write" in caps
    tested = "run_test" in caps
    probed = any(r.get("producer") == "probe" for r in d["evidence"])
    gate = d["gate"]
    gate_decision = (gate or {}).get("decision")
    gate_state = ("COMPLETE" if gate_decision == "complete"
                  else "REFUSE" if gate_decision == "refuse"
                  else "IN PROGRESS")
    gate_status = ("complete" if gate_decision == "complete"
                   else "refused" if gate_decision == "refuse" else "pending")

    def phase(done: bool, active: bool = False) -> str:
        return "complete" if done else ("active" if active else "pending")

    return [
        ("INVESTIGATE", phase(any(c in caps for c in _CAP_READ))),
        ("REPRODUCE", phase(tested)),
        ("REMEDIATE", phase(wrote, active=wrote)),
        ("VERIFY", phase(bool(d["verifications"]))),
        ("FALSIFY", phase(bool(d["falsifications"]))),
        ("INDEPENDENT PROBE", phase(probed)),
        ("QUALITY GATE", gate_status),
    ]


# ---------------------------------------------------------------------------
# IBM BOB control plane
# ---------------------------------------------------------------------------

def _control_plane(d: Dict[str, Any]) -> str:
    decided = [x for x in d["decisions"] if x.get("decision") == "deny"]
    picked = decided[-1] if decided else (
        d["decisions"][-1] if d["decisions"] else None)
    chain = (
        '<div class="chain">'
        '<span class="node">ACTION REQUEST</span><span class="arrow">↓</span>'
        '<span class="node">BOB RUNTIME</span><span class="arrow">↓</span>'
        '<span class="node">BOB BROKER</span><span class="arrow">↓</span>'
        '<span class="node">BOB POLICY</span><span class="arrow">↓</span>'
        '<span class="node decision">ALLOW / DENY</span>'
        '<span class="arrow">↓</span>'
        '<span class="node">EXECUTION</span>'
        '</div>')
    if picked is None:
        detail = '<p class="empty">No policy decision recorded.</p>'
    else:
        detail = _kv([
            ("ACTION", f"{str(picked.get('capability','')).upper()} "
                       f"{picked.get('target')}"),
            ("CAPABILITY", str(picked.get("capability", "")).upper()),
            ("TARGET", picked.get("target")),
            ("REQUEST SEQ", picked.get("request_seq")),
            ("DECISION", (picked.get("decision") or "").upper()),
            ("REASON", picked.get("reason")),
            ("SCOPE", d["run"].mission.scope),
        ])
    return (
        f'<section class="panel bob">'
        f'<h2>IBM BOB CONTROL PLANE</h2>'
        f'<p class="note">Every capability action crosses this boundary. '
        f'The model proposes; IBM BOB decides whether it may run.</p>'
        f'{chain}{detail}'
        f'<p class="legend">DENY is recorded and never executed.</p>'
        f'</section>')


def _attribution() -> str:
    bob = [
        ("BOB RUNTIME", "mediated execution"),
        ("BOB BROKER", "normalized / submitted requests"),
        ("BOB POLICY", "authorized / denied each action"),
    ]
    raphael = [
        ("EVIDENCE LEDGER", "persisted execution outcome"),
        ("VERIFIER", "checked claimed behavior"),
        ("FALSIFIER", "challenged apparent success"),
        ("REPLANNER", "derived a new plan on refutation"),
        ("QUALITY GATE", "determined whether COMPLETE is permissible"),
    ]
    def rows(items):
        return "".join(
            f'<div class="kv"><span class="k mono">{_e(k)}</span>'
            f'<span class="v">{_e(v)}</span></div>' for k, v in items)
    return (
        '<section class="panel attrib"><h2>GOVERNANCE ATTRIBUTION</h2>'
        '<div class="attrib-grid">'
        f'<div><h3>IBM BOB CONTROL PLANE</h3>{rows(bob)}</div>'
        f'<div><h3>RAPHAEL VERIFICATION LAYER</h3>{rows(raphael)}</div>'
        '</div></section>')


# ---------------------------------------------------------------------------
# header
# ---------------------------------------------------------------------------

def _header(d: Dict[str, Any]) -> str:
    run = d["run"]
    session = d["session"]
    state = _state_name(run.state)
    if state == "completed":
        status = _pill("COMPLETE", "ok")
    elif state == "refused":
        status = _pill("REFUSE", "crit")
    elif state == "failed":
        status = _pill("FAILED", "crit")
    elif state == "cancelled":
        status = _pill("CANCELLED", "muted")
    else:
        status = _pill(state.upper() or "UNKNOWN", "info")
    mission_id = run.mission.mission_id
    return (
        '<section class="opheader">'
        f'<div class="op-title"><span class="op-id mono">{_e(run.run_id)}</span>'
        f'<span class="op-name">{_e(run.mission.description or mission_id)}</span>'
        f'{status}</div>'
        f'<div class="op-meta">{_kv([("MISSION", mission_id), ("TARGET", (run.mission.problem or {}).get("symptom_target")), ("WORKSPACE", run.workspace_root), ("MODEL", getattr(session, "model", None)), ("PROVIDER", getattr(session, "provider", None)), ("RUN ID", run.run_id)])}</div>'
        '</section>')


def _pipeline_html(d: Dict[str, Any]) -> str:
    parts = []
    for label, status in _pipeline(d):
        mark = {"complete": "✓", "active": "●", "refused": "✕",
                "pending": "○", "attention": "!"}.get(status, "○")
        parts.append(
            f'<div class="phase {status}"><span class="pmark">{mark}</span>'
            f'<span class="plabel">{_e(label)}</span></div>')
    return f'<section class="pipeline" aria-label="Operation pipeline">{"".join(parts)}</section>'


# ---------------------------------------------------------------------------
# trace list + detail
# ---------------------------------------------------------------------------

def _default_stage_key(stages: List[Dict[str, Any]]) -> str:
    for key in ("policy", "gate", "proposal"):
        for stage in stages:
            if stage["key"] == key and stage["status"] not in ("pending", "notrun"):
                return key
    return stages[0]["key"]


def _trace_html(d: Dict[str, Any],
                stages: List[Dict[str, Any]]) -> str:
    default = _default_stage_key(stages)
    rows = []
    panels = []
    for i, stage in enumerate(stages, start=1):
        active = stage["key"] == default
        rows.append(
            f'<button type="button" class="trow {"is-active" if active else ""}" '
            f'data-target="d-{stage["key"]}" aria-controls="d-{stage["key"]}" '
            f'aria-selected="{"true" if active else "false"}">'
            f'<span class="tidx mono">{i:02d}</span>'
            f'<span class="tname">{_e(stage["title"])}</span>'
            f'<span class="tstat">{_status_pill(stage["status"])}</span>'
            f'<span class="tsum">{_e(stage["summary"])}</span>'
            f'</button>')
        panels.append(
            f'<div class="dpanel {"is-active" if active else ""}" '
            f'id="d-{stage["key"]}" role="tabpanel" '
            f'aria-label="{_e(stage["title"])}">'
            f'<h3>{_e(stage["title"])} {_status_pill(stage["status"])}</h3>'
            f'{stage["html"]}</div>')
    return (
        '<section class="trace">'
        f'<div class="trace-list" role="tablist" aria-label="Decision trace">'
        f'{"".join(rows)}</div>'
        f'<div class="trace-detail">{"".join(panels)}</div>'
        '</section>')


def _gate_panel(d: Dict[str, Any]) -> str:
    return _stage_gate(d)["html"]


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def render_decision_trace(run_id: str, *, runs_root, sessions_root) -> str:
    """Return the full HTML page for a run's Decision Trace."""
    data = collect(run_id, runs_root=runs_root,
                   sessions_root=sessions_root)
    stages = _build_stages(data)
    gate = data["gate"] or {}
    decision = (gate.get("decision") or "—").upper()
    title = f"RAPHAEL — Decision Trace — {run_id}"
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)}</title>"
        f"<style>{_CSS}</style></head><body>"
        '<header class="cmdbar">'
        '<span class="brand">RAPHAEL</span>'
        '<span class="screen">Decision Trace</span>'
        '<span class="banner">GOVERNED OPS // SCOPE-LOCKED</span>'
        '<span class="spacer"></span>'
        f'<span class="cmeta mono">{_e(getattr(data["session"], "model", None) or "MODEL N/A")}</span>'
        f'<span class="cmeta mono">{_e(getattr(data["session"], "provider", None) or "PROVIDER N/A")}</span>'
        '<span class="led ok" title="read-only snapshot"></span>'
        '</header>'
        '<main>'
        f'{_header(data)}'
        f'{_pipeline_html(data)}'
        f'{_trace_html(data, stages)}'
        f'{_control_plane(data)}'
        '<section class="panel gate"><h2>QUALITY GATE</h2>'
        f'<div class="gate-final">{_e(decision)}</div>'
        f'{_gate_panel(data)}</section>'
        f'{_attribution()}'
        '<p class="readonly">READ-ONLY SNAPSHOT · rendered from '
        'harness.api · no execution controls</p>'
        '</main>'
        '<footer class="policystrip mono">'
        'POLICY: FAIL-CLOSED · MODE: GOVERNED · GATE: QUALITY</footer>'
        f'<script>{_JS}</script>'
        '</body></html>')


_JS = (
    "(function(){var b=document.querySelectorAll('.trow');"
    "b.forEach(function(x){x.addEventListener('click',function(){"
    "var t=x.getAttribute('data-target');"
    "b.forEach(function(y){y.classList.remove('is-active');"
    "y.setAttribute('aria-selected','false');});"
    "x.classList.add('is-active');x.setAttribute('aria-selected','true');"
    "document.querySelectorAll('.dpanel').forEach(function(p){"
    "p.classList.toggle('is-active',p.id===t);});"
    "});});})();"
)

_CSS = """
:root{--bg:#080A0D;--panel:#101318;--panel2:#151920;--border:#242A33;
--primary:#5B7FE0;--ok:#35B77A;--warn:#D7A044;--crit:#D34F61;
--text:#E7EAF0;--sec:#9299A5;--muted:#5F6773}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--text);
font-family:Inter,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
font-size:13px;line-height:1.45}
.mono,.op-id,.kv .v,.tidx,table.dense td,table.dense th,.cmeta{
font-family:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
a{color:var(--primary)}
main{max-width:1440px;margin:0 auto;padding:14px 18px 40px}
h1,h2,h3{font-weight:600;letter-spacing:.02em}
.cmdbar{display:flex;align-items:center;gap:12px;padding:9px 18px;
background:var(--panel);border-bottom:1px solid var(--border);
position:sticky;top:0;z-index:5}
.brand{font-weight:700;letter-spacing:.16em;color:var(--text)}
.screen{color:var(--sec);border-left:1px solid var(--border);padding-left:12px}
.banner{font-size:11px;color:var(--muted);letter-spacing:.08em;
text-transform:uppercase}
.spacer{flex:1}
.cmeta{font-size:11px;color:var(--sec)}
.led{width:8px;height:8px;border-radius:50%;background:var(--muted)}
.led.ok{background:var(--ok);box-shadow:0 0 6px var(--ok)}
.opheader{margin:14px 0;padding:12px 14px;background:var(--panel2);
border:1px solid var(--border);border-radius:4px}
.op-title{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.op-id{font-size:12px;color:var(--primary)}
.op-name{font-size:15px;font-weight:600}
.op-meta{margin-top:8px}
.pipeline{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0;padding:10px;
background:var(--panel);border:1px solid var(--border);border-radius:4px}
.phase{display:flex;align-items:center;gap:7px;padding:5px 10px;
border:1px solid var(--border);border-radius:3px;font-size:11px;
letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.phase .pmark{font-size:12px}
.phase.complete{color:var(--ok);border-color:rgba(53,183,122,.4)}
.phase.active{color:var(--primary);border-color:rgba(91,127,224,.5);
animation:pulse 2s ease-in-out infinite}
.phase.refused{color:var(--crit);border-color:rgba(211,79,97,.5)}
.phase.attention{color:var(--warn);border-color:rgba(215,160,68,.5)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.6}}
@media (prefers-reduced-motion:reduce){.phase.active{animation:none}}
.trace{display:grid;grid-template-columns:minmax(360px,42%) 1fr;gap:14px;
margin:14px 0}
.trace-list{display:flex;flex-direction:column;gap:2px}
.trow{display:grid;grid-template-columns:34px 1fr auto;gap:6px 10px;
align-items:center;text-align:left;background:var(--panel);
border:1px solid var(--border);border-left:2px solid transparent;
border-radius:3px;padding:7px 10px;color:inherit;cursor:pointer;
font:inherit}
.trow:hover{background:var(--panel2)}
.trow.is-active{border-left-color:var(--primary);background:var(--panel2)}
.trow:focus-visible{outline:2px solid var(--primary);outline-offset:1px}
.tidx{color:var(--muted);font-size:11px}
.tname{font-weight:600;letter-spacing:.03em;text-transform:uppercase;
font-size:11px}
.tstat{justify-self:end}
.tsum{grid-column:2/4;color:var(--sec);font-size:11.5px}
.trace-detail{background:var(--panel);border:1px solid var(--border);
border-radius:4px;padding:14px;min-height:320px}
.dpanel{display:none}
.dpanel.is-active{display:block}
.panel{background:var(--panel);border:1px solid var(--border);
border-radius:4px;padding:14px;margin:14px 0}
.panel h2{font-size:12px;letter-spacing:.12em;color:var(--sec);
text-transform:uppercase;margin:0 0 10px}
.panel h3{font-size:12px;letter-spacing:.08em;text-transform:uppercase;
color:var(--sec);margin:0 0 8px}
.kvlist{display:grid;gap:4px}
.kv{display:grid;grid-template-columns:150px 1fr;gap:10px}
.kv .k{color:var(--muted);font-size:11px;letter-spacing:.05em;
text-transform:uppercase}
.kv .v{color:var(--text);font-size:12px;word-break:break-word}
table.dense{width:100%;border-collapse:collapse;margin-top:8px}
table.dense th{text-align:left;color:var(--muted);font-weight:500;
font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;
border-bottom:1px solid var(--border);padding:5px 8px}
table.dense td{border-bottom:1px solid rgba(36,42,51,.6);padding:5px 8px;
font-size:11.5px;color:var(--sec);vertical-align:top}
.pill{display:inline-block;padding:1px 7px;border-radius:10px;font-size:10px;
letter-spacing:.06em;border:1px solid var(--border);color:var(--sec)}
.pill.ok{color:var(--ok);border-color:rgba(53,183,122,.5)}
.pill.crit{color:var(--crit);border-color:rgba(211,79,97,.5)}
.pill.warn{color:var(--warn);border-color:rgba(215,160,68,.5)}
.pill.info{color:var(--primary);border-color:rgba(91,127,224,.5)}
.pill.muted{color:var(--muted)}
.note{color:var(--muted);font-size:11.5px;margin:6px 0}
.empty{color:var(--muted);font-size:11.5px}
.authority{margin:8px 0;padding:7px 10px;border-left:2px solid var(--primary);
background:rgba(91,127,224,.07);color:var(--sec);font-size:11.5px}
.chain{display:flex;flex-direction:column;align-items:flex-start;gap:2px;
margin:8px 0 14px}
.chain .node{padding:5px 12px;border:1px solid var(--border);
border-radius:3px;font-size:11px;letter-spacing:.06em;color:var(--text);
background:var(--panel2)}
.chain .node.decision{border-color:rgba(215,160,68,.5);color:var(--warn)}
.chain .arrow{color:var(--muted);padding-left:14px}
.bob{border-color:rgba(91,127,224,.4)}
.legend{color:var(--muted);font-size:11px}
.checklist{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
gap:3px 16px;margin:8px 0}
.chk{display:flex;gap:8px;font-size:11.5px}
.chk .mark{width:12px}
.chk.ok .mark{color:var(--ok)}
.chk.crit .mark{color:var(--crit)}
.chk.ok .mono{color:var(--text)}
.gate-final{font-size:20px;font-weight:700;letter-spacing:.08em;
margin-bottom:6px}
.gate-count{color:var(--sec);font-size:11.5px;letter-spacing:.06em;
text-transform:uppercase;margin-bottom:4px}
.readonly{color:var(--muted);font-size:11px;margin-top:18px;
letter-spacing:.05em}
.policystrip{position:sticky;bottom:0;background:var(--panel);
border-top:1px solid var(--border);color:var(--muted);font-size:10.5px;
letter-spacing:.1em;padding:6px 18px;text-align:center}
.attrib-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.criteria{margin:4px 0 0 18px;padding:0;color:var(--sec);font-size:12px}
.sublabel{color:var(--muted);font-size:10.5px;letter-spacing:.08em;
text-transform:uppercase;margin-top:10px}
.row-inline{margin:6px 0}
@media (max-width:1100px){.trace{grid-template-columns:1fr}
.attrib-grid{grid-template-columns:1fr}}
"""


__all__ = ["collect", "render_decision_trace"]
