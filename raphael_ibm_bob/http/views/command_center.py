"""raphael_ibm_bob.http.views.command_center — RAPHAEL Command Center.

The primary operational overview of the Harness.

    GET /command   (text/html)

It answers, from authoritative persisted state only:

  1. What operations/engagements currently exist?
  2. How many are active?
  3. Which specialists are involved / currently active?
  4. What findings exist, and in which lifecycle state?
  5. What is the current Quality Gate status of each operation?
  6. What models/providers are recorded?
  7. What needs operator attention?

Everything is aggregated read-only through `harness.api` over the
existing Harness concepts (session / workspace / run / mission). There
is NO new backend endpoint, no new metric store, and no fabricated
value: a value the persisted data cannot establish is shown as
UNKNOWN, never invented.

Live updates reuse the EXISTING per-run SSE endpoint
(`/runs/{run_id}/events/stream`) for currently-active operations only;
there is no second event system and no polling loop.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from raphael_ibm_bob.harness import api
from raphael_ibm_bob.http.views import decision_trace as dt

HTML = "text/html; charset=utf-8"

SPECIALIST_ROLES: Tuple[str, ...] = (
    "investigator", "test_analyst", "remediation_planner",
    "verifier", "falsifier", "evidence_analyst",
)

_ACTIVE_STATES = ("pending", "running")
_LIFECYCLE = ("unverified", "verified", "refuted", "superseded")


# ---------------------------------------------------------------------------
# aggregation (read-only, harness.api only)
# ---------------------------------------------------------------------------

def _skill_role_map() -> Dict[str, str]:
    return {s.id: (s.role or "") for s in api.list_skills()}


def _latest_findings(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    findings: Dict[str, Dict[str, Any]] = {}
    for record in records:
        if record.get("kind") != "finding":
            continue
        fid = record.get("finding_id")
        if not fid:
            continue
        findings[fid] = {"state": (record.get("state") or "").lower(),
                         "ts": record.get("ts")}
    return findings


def _run_summary(run, records, gate, tasks, session, skill_role) -> Dict[str, Any]:
    requests = [r for r in records if r.get("kind") == "request"]
    evidence = [r for r in records if r.get("kind") == "evidence"]
    findings = _latest_findings(records)
    roles = []
    for record in requests:
        requester = record.get("requester") or ""
        if requester.startswith("skill:"):
            role = skill_role.get(requester.split("skill:", 1)[1])
            if role and role not in roles:
                roles.append(role)
    task, task_state = dt._active_task(tasks)
    last_ts = max((r.get("ts") or 0) for r in records) if records else 0
    gate_decision = (gate or {}).get("decision")
    return {
        "run_id": run.run_id,
        "mission_id": run.mission.mission_id,
        "mission": run.mission.description or run.mission.mission_id,
        "target": (run.mission.problem or {}).get("symptom_target") or "—",
        "workspace": run.workspace_root,
        "state": run.state,
        "terminal": run.is_terminal(),
        "gate": gate_decision,
        "task": (task or {}).get("name") or "—",
        "task_state": task_state or "—",
        "roles": roles,
        "skills": sorted({r.get("requester", "").split("skill:", 1)[1]
                          for r in requests
                          if (r.get("requester") or "").startswith("skill:")}),
        "findings": findings,
        "evidence_count": len(evidence),
        "record_count": len(records),
        "model": getattr(session, "model", None),
        "provider": getattr(session, "provider", None),
        "last_ts": last_ts,
        "started_at": run.started_at,
    }


def collect(*, runs_root, sessions_root) -> Dict[str, Any]:
    skill_role = _skill_role_map()
    run_ids = api.get_runs(runs_root)
    runs: List[Dict[str, Any]] = []
    for run_id in run_ids:
        try:
            run = api.get_run(run_id, runs_root)
        except Exception:
            continue
        try:
            records = api.get_evidence(run_id, runs_root)
        except Exception:
            records = []
        try:
            gate = api.get_gate(run_id, runs_root)
        except Exception:
            gate = None
        try:
            tasks = api.get_tasks(run_id, runs_root)
        except Exception:
            tasks = {"root": {}, "states": {}}
        try:
            session = api.get_session(run.session_id, sessions_root)
        except Exception:
            session = None
        runs.append(_run_summary(run, records, gate, tasks, session,
                                 skill_role))
    runs.sort(key=lambda r: r["run_id"], reverse=True)

    active = [r for r in runs if r["state"] in _ACTIVE_STATES]

    lifecycle_counts = {state: 0 for state in _LIFECYCLE}
    findings_rows: List[Dict[str, Any]] = []
    for run in runs:
        for fid, info in run["findings"].items():
            state = info["state"]
            if state in lifecycle_counts:
                lifecycle_counts[state] += 1
            findings_rows.append({
                "finding_id": fid, "target": run["target"],
                "state": state, "run_id": run["run_id"],
                "evidence": run["evidence_count"], "ts": info["ts"]})
    findings_rows.sort(key=lambda f: (f["ts"] or 0), reverse=True)

    gate_counts = {"complete": 0, "refuse": 0, "in-progress": 0}
    gate_rows: List[Dict[str, Any]] = []
    total_conditions = len(dt._gate_condition_names())
    for run in runs:
        decision = run["gate"]
        if decision == "complete":
            gate_counts["complete"] += 1
        elif decision == "refuse":
            gate_counts["refuse"] += 1
        else:
            gate_counts["in-progress"] += 1
        passed = 0
        if decision:
            try:
                gate = api.get_gate(run["run_id"], runs_root)
                passed = len([c for c in (gate or {}).get("checks", [])
                              if c in dt._gate_condition_names()])
            except Exception:
                passed = 0
        gate_rows.append({
            "run_id": run["run_id"], "mission_id": run["mission_id"],
            "decision": (decision or "in-progress"),
            "passed": passed, "total": total_conditions})

    # specialist involvement (derived from persisted skill requests)
    specialists = []
    for role in SPECIALIST_ROLES:
        active_run = next((r for r in active if role in r["roles"]), None)
        recent_run = next((r for r in runs if role in r["roles"]), None)
        if active_run is not None:
            state = "ACTIVE"
            current = active_run
        elif recent_run is not None:
            state = "COMPLETED"
            current = recent_run
        else:
            state = "UNKNOWN"
            current = None
        specialists.append({
            "role": role,
            "state": state,
            "run_id": (current or {}).get("run_id") or "—",
            "task": (current or {}).get("task") or "—",
            "skill": ", ".join((current or {}).get("skills") or []) or "—",
        })

    models = sorted({(r["model"] or "—", r["provider"] or "—")
                     for r in runs})

    evidence_total = sum(r["evidence_count"] for r in runs)

    return {
        "runs": runs,
        "active": active,
        "lifecycle_counts": lifecycle_counts,
        "findings_rows": findings_rows,
        "gate_counts": gate_counts,
        "gate_rows": gate_rows,
        "specialists": specialists,
        "models": models,
        "evidence_total": evidence_total,
        "targets": sorted({r["workspace"] for r in runs}),
        "missions": sorted({r["mission_id"] for r in runs}),
    }


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _metric(label: str, value: Any, kind: str = "") -> str:
    return (f'<div class="metric {kind}"><span class="mv">{dt._e(value)}</span>'
            f'<span class="ml">{dt._e(label)}</span></div>')


def _summary(data: Dict[str, Any]) -> str:
    lc = data["lifecycle_counts"]
    gc = data["gate_counts"]
    return (
        '<section class="panel"><h2>OPERATIONAL SUMMARY</h2>'
        '<div class="metrics">'
        + _metric("ACTIVE OPERATIONS", len(data["active"]),
                  "ok" if data["active"] else "")
        + _metric("TOTAL OPERATIONS", len(data["runs"]))
        + _metric("ACTIVE SPECIALISTS",
                  sum(1 for s in data["specialists"] if s["state"] == "ACTIVE"))
        + _metric("OPEN FINDINGS",
                  lc["unverified"] + lc["refuted"],
                  "warn" if (lc["unverified"] + lc["refuted"]) else "")
        + _metric("EVIDENCE RECORDS", data["evidence_total"])
        + _metric("TARGETS", len(data["targets"]))
        + '</div>'
        '<div class="kvlist lifecycle">'
        f'<div class="kv"><span class="k">FINDINGS · UNVERIFIED</span>'
        f'<span class="v mono">{lc["unverified"]}</span></div>'
        f'<div class="kv"><span class="k">FINDINGS · VERIFIED</span>'
        f'<span class="v mono">{lc["verified"]}</span></div>'
        f'<div class="kv"><span class="k">FINDINGS · REFUTED</span>'
        f'<span class="v mono">{lc["refuted"]}</span></div>'
        f'<div class="kv"><span class="k">FINDINGS · SUPERSEDED</span>'
        f'<span class="v mono">{lc["superseded"]}</span></div>'
        f'<div class="kv"><span class="k">GATES · COMPLETE</span>'
        f'<span class="v mono">{gc["complete"]}</span></div>'
        f'<div class="kv"><span class="k">GATES · REFUSE</span>'
        f'<span class="v mono">{gc["refuse"]}</span></div>'
        f'<div class="kv"><span class="k">GATES · IN PROGRESS</span>'
        f'<span class="v mono">{gc["in-progress"]}</span></div>'
        '</div></section>')


def _engagements(data: Dict[str, Any]) -> str:
    rows = []
    for run in data["runs"][:50]:
        gate = (run["gate"] or "in-progress")
        gate_kind = ("ok" if gate == "complete"
                     else "crit" if gate == "refuse" else "muted")
        state_kind = ("ok" if run["state"] == "completed"
                      else "crit" if run["state"] in ("refused", "failed")
                      else "info")
        roles = ", ".join(run["roles"]) or "—"
        rows.append(
            f'<tr>'
            f'<td><a class="row-link mono" href="/operations/'
            f'{dt._e(run["run_id"])}">{dt._e(run["run_id"])}</a></td>'
            f'<td>{dt._e(run["mission"])}</td>'
            f'<td class="mono">{dt._e(run["target"])}</td>'
            f'<td class="mono">{dt._e(run["workspace"])}</td>'
            f'<td>{dt._pill(run["state"].upper(), state_kind)}</td>'
            f'<td>{dt._e(run["task"])}</td>'
            f'<td>{dt._e(roles)}</td>'
            f'<td class="mono">{dt._e(run["model"] or "—")} / '
            f'{dt._e(run["provider"] or "—")}</td>'
            f'<td class="mono">{len(run["findings"])}</td>'
            f'<td class="mono">{run["evidence_count"]}</td>'
            f'<td>{dt._pill(gate.upper(), gate_kind)}</td>'
            f'<td class="mono">{dt._e(dt._fmt_ts(run["last_ts"]))}</td>'
            f'</tr>')
    table = ("<table class=\"dense\"><thead><tr>"
             "<th>OPERATION</th><th>MISSION</th><th>TARGET</th>"
             "<th>WORKSPACE</th><th>STATE</th><th>ACTIVE TASK</th>"
             "<th>SPECIALIST(S)</th><th>MODEL / PROVIDER</th><th>FINDINGS</th>"
             "<th>EVIDENCE</th><th>GATE</th><th>LAST ACTIVITY</th>"
             "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
             if rows else '<p class="empty">No operations yet.</p>')
    note = ('<p class="note">Harness-managed operations only '
            '(runs with a persisted Harness record). '
            f'Showing {min(len(data["runs"]), 50)} of '
            f'{len(data["runs"])}. "Engagement" is not a backend concept: '
            'this table is the session/workspace/run/mission reality.</p>')
    return (f'<section class="panel"><h2>ACTIVE ENGAGEMENTS / TARGETS</h2>'
            f'{note}{table}</section>')


def _specialists(data: Dict[str, Any]) -> str:
    rows = []
    for spec in data["specialists"]:
        state = spec["state"]
        kind = {"ACTIVE": "ok", "COMPLETED": "info",
                "UNKNOWN": "muted"}.get(state, "muted")
        run_link = ("—" if spec["run_id"] == "—"
                    else f'<a class="row-link mono" '
                         f'href="/operations/{dt._e(spec["run_id"])}">'
                         f'{dt._e(spec["run_id"])}</a>')
        rows.append(
            f'<tr><td class="mono">{dt._e(spec["role"])}</td>'
            f'<td>{dt._pill(state, kind)}</td>'
            f'<td>{run_link}</td>'
            f'<td>{dt._e(spec["task"])}</td>'
            f'<td class="mono">{dt._e(spec["skill"])}</td></tr>')
    table = ("<table class=\"dense\"><thead><tr><th>ROLE</th><th>STATE</th>"
             "<th>CURRENT RUN</th><th>CURRENT TASK</th><th>CURRENT SKILL</th>"
             "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")
    note = ('<p class="note">STATE is derived from persisted skill '
            'requests: ACTIVE = involved in a pending/running operation, '
            'COMPLETED = last involvement is terminal, UNKNOWN = no '
            'persisted involvement. Specialist availability/heartbeat is '
            'NOT persisted, so it is not claimed (BLOCKED/READY are never '
            'fabricated).</p>')
    return (f'<section class="panel"><h2>SPECIALIST OPERATIONS (M14)</h2>'
            f'{table}{note}</section>')


def _findings(data: Dict[str, Any]) -> str:
    rows = []
    for finding in data["findings_rows"][:50]:
        state = finding["state"].upper() or "UNKNOWN"
        kind = {"VERIFIED": "ok", "REFUTED": "crit",
                "SUPERSEDED": "muted", "UNVERIFIED": "warn"}.get(state,
                                                                  "muted")
        rows.append(
            f'<tr><td class="mono">{dt._e(finding["finding_id"])}</td>'
            f'<td class="mono">{dt._e(finding["target"])}</td>'
            f'<td>{dt._pill(state, kind)}</td>'
            f'<td><a class="row-link mono" href="/operations/'
            f'{dt._e(finding["run_id"])}">{dt._e(finding["run_id"])}</a></td>'
            f'<td class="mono">{finding["evidence"]}</td>'
            f'<td class="mono">{dt._e(dt._fmt_ts(finding["ts"]))}</td></tr>')
    table = ("<table class=\"dense\"><thead><tr><th>ID</th><th>TARGET</th>"
             "<th>STATUS</th><th>OPERATION</th><th>EVIDENCE</th>"
             "<th>LAST ACTIVITY</th></tr></thead><tbody>"
             + "".join(rows) + "</tbody></table>"
             if rows else '<p class="empty">No findings recorded.</p>')
    return ('<section class="panel"><h2>FINDINGS</h2>'
            '<p class="note">Lifecycle states are the persisted ones '
            '(UNVERIFIED / VERIFIED / REFUTED / SUPERSEDED). The finding '
            'model carries no severity, so none is shown.</p>'
            f'{table}</section>')


def _gates(data: Dict[str, Any]) -> str:
    rows = []
    for gate in data["gate_rows"][:50]:
        decision = gate["decision"]
        kind = ("ok" if decision == "complete"
                else "crit" if decision == "refuse" else "muted")
        label = decision.upper()
        condition = (f'{gate["passed"]}/{gate["total"]}'
                     if decision in ("complete", "refuse") else "—")
        rows.append(
            f'<tr><td><a class="row-link mono" href="/operations/'
            f'{dt._e(gate["run_id"])}/decision-trace">'
            f'{dt._e(gate["run_id"])}</a></td>'
            f'<td class="mono">{dt._e(gate["mission_id"])}</td>'
            f'<td>{dt._pill(label, kind)}</td>'
            f'<td class="mono">{condition}</td></tr>')
    table = ("<table class=\"dense\"><thead><tr><th>OPERATION</th>"
             "<th>MISSION</th><th>GATE</th><th>CONDITIONS</th></tr></thead>"
             "<tbody>" + "".join(rows) + "</tbody></table>"
             if rows else '<p class="empty">No operations.</p>')
    return ('<section class="panel gate"><h2>QUALITY GATE STATUS</h2>'
            '<p class="note">REFUSE is a first-class, intentional outcome '
            '(never collapsed into FAILED). IN PROGRESS means no gate '
            'record is persisted yet.</p>'
            f'{table}</section>')


def _models(data: Dict[str, Any]) -> str:
    if not data["models"]:
        body = '<p class="empty">No model/provider recorded.</p>'
    else:
        body = '<div class="legend-grid">' + "".join(
            f'<span class="lg">{dt._e(m)} / {dt._e(p)}</span>'
            for m, p in data["models"]) + '</div>'
    return ('<section class="panel"><h2>MODEL / PROVIDER (recorded)</h2>'
            '<p class="note">Session labels only — references, never '
            'credentials. The Harness records names, not keys.</p>'
            f'{body}</section>')


def _navigation() -> str:
    links = [
        ("OPERATIONS INDEX", "/operations", True),
        ("FINDINGS", "/operations/findings", True),
        ("EVIDENCE", "/operations/evidence", True),
        ("POLICY & QUALITY GATE", "/operations/gate", True),
        ("DECISION TRACE (per op)", None, True),
        ("EVENT STREAM (per op)", None, True),
        ("CAPABILITY ARSENAL", "/operations/capabilities", True),
        ("OPERATION GRAPH", "/operations/graph", True),
        ("ROLES API", "/roles", True),
        ("SKILLS API", "/skills", True),
        ("CAPABILITIES API", "/capabilities", True),
    ]
    chips = []
    for label, href, available in links:
        if href and available:
            chips.append(f'<a class="navlink" href="{dt._e(href)}">'
                         f'{dt._e(label)}</a>')
        elif available:
            chips.append(f'<span class="navlink muted">{dt._e(label)}</span>')
        else:
            chips.append(f'<span class="navlink unavailable" '
                         f'title="not implemented yet">{dt._e(label)} '
                         f'· UNAVAILABLE</span>')
    return ('<section class="panel"><h2>OPERATOR NAVIGATION</h2>'
            f'<div class="navgrid">{"".join(chips)}</div></section>')


_EXTRA_CSS = """
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
gap:8px;margin:6px 0 12px}
.metric{background:var(--panel2);border:1px solid var(--border);
border-radius:4px;padding:10px 12px;display:grid;gap:2px}
.metric .mv{font-size:22px;font-weight:700;letter-spacing:.04em;
color:var(--text)}
.metric .ml{font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;
color:var(--muted)}
.metric.ok .mv{color:var(--ok)}
.metric.warn .mv{color:var(--warn)}
.lifecycle{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.navgrid{display:flex;gap:8px;flex-wrap:wrap}
.navlink{font-size:11px;letter-spacing:.05em;text-transform:uppercase;
border:1px solid var(--border);border-radius:10px;padding:5px 11px;
color:var(--primary);text-decoration:none}
.navlink:hover{border-color:var(--primary)}
.navlink.muted{color:var(--sec)}
.navlink.unavailable{color:var(--muted);border-style:dashed}
a.row-link{color:var(--primary);text-decoration:none}
"""


def _live_config(data: Dict[str, Any]) -> str:
    return json.dumps({
        "activeRuns": [r["run_id"] for r in data["active"]],
        "runs": [{"run_id": r["run_id"], "state": r["state"]}
                 for r in data["runs"][:50]],
    }, sort_keys=True)


_JS = r"""
(function(){
  var cfg = window.RAPHAEL || {};
  var active = cfg.activeRuns || [];
  var dot = document.getElementById('cc-dot');
  var text = document.getElementById('cc-live');
  var status = document.getElementById('cc-status');
  function setLive(msg, live){
    if(text) text.textContent = msg;
    if(dot) dot.className = 'dot' + (live ? ' live' : live === false ? ' down' : '');
  }
  if(!active.length){
    if(status) status.textContent = 'SNAPSHOT · no active operations';
    setLive('IDLE', null);
    return;
  }
  if(typeof EventSource === 'undefined'){
    if(status) status.textContent = 'NO STREAM SUPPORT';
    return;
  }
  var seen = 0;
  function bump(){
    seen++;
    if(status) status.textContent = 'LIVE · '+seen+' event(s) on active ops';
  }
  active.forEach(function(runId){
    var es = new EventSource(cfg.sseBase + encodeURIComponent(runId) +
                             '/events/stream');
    es.addEventListener('RAPHAEL_EVENT', function(){ setLive('LIVE', true); bump(); });
    es.addEventListener('stream_end', function(){ es.close(); });
    es.onerror = function(){ setLive('RECONNECTING…', false); };
  });
  setLive('LIVE', true);
})();
"""


def render_command(*, runs_root, sessions_root) -> str:
    data = collect(runs_root=runs_root, sessions_root=sessions_root)
    cfg = json.dumps({"activeRuns": [r["run_id"] for r in data["active"]],
                      "sseBase": "/runs/"}, sort_keys=True)
    body = (
        f'{_summary(data)}'
        f'{_engagements(data)}'
        '<div class="grid2">'
        f'{_specialists(data)}'
        f'{_findings(data)}'
        '</div>'
        f'{_gates(data)}'
        f'{_models(data)}'
        f'{_navigation()}'
        '<p class="readonly">READ-ONLY OVERVIEW · aggregated from '
        'harness.api · no execution controls · live via existing per-run '
        'SSE</p>'
    )
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RAPHAEL — Command Center</title>'
        f'<style>{dt._CSS}{_EXTRA_CSS}</style></head><body>'
        '<header class="cmdbar"><span class="brand">RAPHAEL</span>'
        '<span class="screen">Command Center</span>'
        '<span class="banner">GOVERNED OPS // SCOPE-LOCKED</span>'
        '<span class="spacer"></span>'
        f'<span class="cmeta mono">{len(data["active"])} ACTIVE</span>'
        f'<span class="cmeta mono">{len(data["runs"])} TOTAL</span>'
        '<span class="dot" id="cc-dot"></span>'
        '<span class="cmeta mono" id="cc-live">—</span></header>'
        f'<main>{body}'
        '<div class="statusbar"><span class="mono" id="cc-status">'
        'SNAPSHOT</span></div></main>'
        '<footer class="policystrip mono">POLICY: FAIL-CLOSED · MODE: '
        'GOVERNED · GATE: QUALITY</footer>'
        '<script>window.RAPHAEL=' + cfg + ';</script>'
        f'<script>{_JS}</script>'
        "</body></html>")


__all__ = ["SPECIALIST_ROLES", "collect", "render_command"]
