"""raphael_ibm_bob.http.views.operation_graph — M15.10.

Read-only Operation Graph: the persisted / reconstructed Harness
operation structure for one run.

    GET /operations/graph[?run=<run_id>]   (text/html)

    RUN -> MISSION -> TASKS -> TASK STATE -> ROLE/SKILL/CAPABILITY
        -> ACTION/EVIDENCE -> FINDING/VERIFICATION -> QUALITY GATE

HONESTY ABOUT THE CURRENT MODEL
-------------------------------
The current implementation does NOT have a dynamic, branching,
autonomous task graph. `specialization.decompose_mission()` yields a
FIXED five-step pipeline derived from the mission
(investigate -> reproduce -> remediate -> verify -> validate). The page
states this explicitly and never implies dynamic branching or graph
mutation.

Two task sources, distinguished physically:

- PERSISTED TASK STATE: the model-led path writes `runs/<id>/tasks.json`;
  `harness.api.get_tasks` returns it verbatim.
- DERIVED / RECONSTRUCTED VIEW: when `tasks.json` is absent,
  `harness.api.get_tasks` re-derives the fixed decomposition from the
  mission (all steps pending). The page labels which source applies.

Read-only: `harness.api` only (`get_runs`, `get_run`, `get_tasks`,
`get_evidence`, `get_gate`, `get_session`, `list_skills`). There is NO
graph engine, no graph store, no mutation, no execution, no controls.
Refutation/replan edges are shown ONLY when persisted evidence carries
them (`producer="replanner"`); otherwise the page says so.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from raphael_ibm_bob.harness import api
from raphael_ibm_bob.http.views import decision_trace as dt

HTML = "text/html; charset=utf-8"


# ---------------------------------------------------------------------------
# aggregation (read-only, harness.api only)
# ---------------------------------------------------------------------------

def _latest_findings(records: List[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for record in records:
        if record.get("kind") == "finding" and record.get("finding_id"):
            out[record["finding_id"]] = (record.get("state") or "").lower()
    return out


def collect(*, runs_root, sessions_root,
            selected_run_id: Optional[str] = None) -> Dict[str, Any]:
    runs = api.get_runs(runs_root)
    selected = selected_run_id if selected_run_id in runs else (
        runs[-1] if runs else None)
    skill_cap = {s.id: s.capability.value for s in api.list_skills()}
    data: Dict[str, Any] = {
        "runs": runs,
        "selected": selected,
        "empty": not runs,
    }
    if selected is None:
        return data

    run = api.get_run(selected, runs_root)
    tasks = api.get_tasks(selected, runs_root)
    records = api.get_evidence(selected, runs_root)
    gate = api.get_gate(selected, runs_root)
    try:
        session = api.get_session(run.session_id, sessions_root)
    except Exception:
        session = None

    root = tasks.get("root") or {}
    states = tasks.get("states") or {}
    subtasks = []
    for task in root.get("subtasks", []):
        skills = list(task.get("skills") or [])
        capabilities = sorted({skill_cap[s] for s in skills if s in skill_cap})
        subtasks.append({
            "task_id": task.get("task_id"),
            "name": task.get("name"),
            "description": task.get("description"),
            "role": task.get("role"),
            "skills": skills,
            "capabilities": capabilities,
            "state": states.get(task.get("task_id"), "UNKNOWN / NOT VERIFIED"),
        })

    findings = _latest_findings(records)
    refuted = sorted(f for f, s in findings.items() if s == "refuted")
    replans = [r for r in records if r.get("producer") == "replanner"]
    evidence = [r for r in records if r.get("kind") == "evidence"]
    verifications = [r.get("evidence_id") for r in evidence
                     if r.get("producer") == "verifier" and r.get("evidence_id")]
    falsifications = [r.get("evidence_id") for r in evidence
                      if r.get("producer") == "falsifier" and r.get("evidence_id")]
    probes = [r.get("evidence_id") for r in evidence
              if r.get("producer") == "probe" and r.get("evidence_id")]

    persisted = (Path(runs_root) / selected / "tasks.json").is_file()
    data.update({
        "empty": False,
        "run": run,
        "mission_id": run.mission.mission_id,
        "mission": run.mission.description or run.mission.mission_id,
        "target": (run.mission.problem or {}).get("symptom_target") or "—",
        "workspace": run.workspace_root,
        "state": run.state,
        "gate": gate,
        "model": getattr(session, "model", None),
        "provider": getattr(session, "provider", None),
        "root_task_id": root.get("task_id"),
        "root_role": root.get("role"),
        "subtasks": subtasks,
        "task_source": ("PERSISTED (runs/<run_id>/tasks.json)"
                        if persisted else
                        "DERIVED (decompose_mission; no tasks.json)"),
        "persisted": persisted,
        "evidence_count": len(evidence),
        "findings": findings,
        "refuted": refuted,
        "replans": [{
            "parent_plan_id": (r.get("payload") or {}).get("parent_plan_id"),
            "plan_b_id": (r.get("payload") or {}).get("plan_b_id"),
            "refuted_finding_id": (r.get("payload") or {}).get("refuted_finding_id"),
            "evidence_id": r.get("evidence_id"),
        } for r in replans],
        "verifications": verifications,
        "falsifications": falsifications,
        "probes": probes,
    })
    return data


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _disclaimers(data: Dict[str, Any]) -> str:
    return (
        '<section class="panel model-panel"><h2>CURRENT ORCHESTRATION MODEL</h2>'
        '<div class="model-title">FIXED TASK PIPELINE</div>'
        '<p class="note">The current system has NO dynamic branching, '
        'autonomous task creation, or graph mutation. '
        '<span class="mono">specialization.decompose_mission()</span> yields '
        'a fixed five-step pipeline derived from the mission '
        '(investigate → reproduce → remediate → verify → validate). This '
        'screen visualizes that current structure honestly; it is not the '
        'future dynamic-orchestration architecture.</p>'
        '<div class="flags">'
        '<span class="flag">FIXED 5-STEP PIPELINE</span>'
        '<span class="flag">NO DYNAMIC BRANCHING</span>'
        '<span class="flag">READ-ONLY VIEW (NOT AN EDITOR)</span>'
        '</div></section>')


def _run_selector(data: Dict[str, Any]) -> str:
    runs = data["runs"]
    if not runs:
        return ""
    links = []
    for run_id in runs:
        cls = "runlink active" if run_id == data["selected"] else "runlink"
        links.append(f'<a class="{cls} mono" href="/operations/graph?run='
                     f'{dt._e(run_id)}">{dt._e(run_id)}</a>')
    return ('<section class="panel"><h2>OPERATION SELECTOR</h2>'
            '<p class="note">The graph is scoped to ONE operation; unrelated '
            'runs are never merged into a global graph.</p>'
            f'<div class="runs">{ "".join(links) }</div></section>')


def _run_summary(data: Dict[str, Any]) -> str:
    if data["empty"]:
        return ('<section class="panel"><h2>OPERATION</h2>'
                '<p class="empty">No Harness-managed operations. This is an '
                'explicit empty state.</p></section>')
    gate = data["gate"] or {}
    decision = (gate.get("decision") or "in-progress").upper()
    kind = ("ok" if gate.get("decision") == "complete"
            else "crit" if gate.get("decision") == "refuse" else "muted")
    source_kind = "ok" if data["persisted"] else "warn"
    pairs = [
        ("RUN", data["run"].run_id),
        ("MISSION", data["mission_id"]),
        ("TARGET", data["target"]),
        ("WORKSPACE", data["workspace"]),
        ("RUN STATE", data["state"]),
        ("MODEL / PROVIDER", f'{data["model"] or "—"} / '
                             f'{data["provider"] or "—"}'),
    ]
    kv = "".join(
        f'<div class="kv"><span class="k">{dt._e(k)}</span>'
        f'<span class="v mono">{dt._e(v)}</span></div>' for k, v in pairs)
    return ('<section class="panel"><h2>OPERATION</h2>'
            f'<div class="kvlist">{kv}</div>'
            '<div class="sublabel">TASK STATE SOURCE</div>'
            f'<div class="row-inline">{dt._pill(data["task_source"], source_kind)}</div>'
            '<div class="row-inline">'
            f'{dt._pill("GATE: " + decision, kind)}</div>'
            '<p class="note">PERSISTED = the run wrote '
            '<span class="mono">tasks.json</span>; DERIVED = no '
            '<span class="mono">tasks.json</span>, so the fixed pipeline is '
            'reconstructed from the mission.</p></section>')


def _task_node(task: Dict[str, Any]) -> str:
    state = str(task["state"]).lower()
    kind = {"completed": "ok", "active": "info", "refuted": "crit",
            "blocked": "warn", "cancelled": "muted",
            "pending": "muted"}.get(state, "muted")
    caps = ", ".join(task["capabilities"]) or "UNKNOWN / NOT VERIFIED"
    skills = ", ".join(task["skills"]) or "NONE DECLARED"
    search = " ".join(str(x) for x in (
        task["task_id"], task["name"], task["role"], skills, caps)).lower()
    return (
        f'<div class="tnode vstep" data-search="{dt._e(search)}">'
        f'<button type="button" class="thead" aria-expanded="false">'
        f'<span class="tname mono">{dt._e(task["name"])}</span>'
        f'<span class="tstate">{dt._pill(str(task["state"]).upper(), kind)}</span>'
        f'<span class="trole mono">{dt._e(task["role"])}</span></button>'
        '<div class="tbody"><div class="kvlist">'
        f'<div class="kv"><span class="k">TASK ID</span>'
        f'<span class="v mono">{dt._e(task["task_id"])}</span></div>'
        f'<div class="kv"><span class="k">STEP</span>'
        f'<span class="v">{dt._e(task["description"])}</span></div>'
        f'<div class="kv"><span class="k">ROLE (DECLARED)</span>'
        f'<span class="v mono">{dt._e(task["role"])}</span></div>'
        f'<div class="kv"><span class="k">SKILLS (DECLARED)</span>'
        f'<span class="v mono">{dt._e(skills)}</span></div>'
        f'<div class="kv"><span class="k">CAPABILITY (DERIVED FROM SKILL)</span>'
        f'<span class="v mono">{dt._e(caps)}</span></div>'
        '<div class="kv"><span class="k">TARGET / PURPOSE</span>'
        '<span class="v">UNKNOWN / NOT VERIFIED (not persisted per task)</span></div>'
        '<div class="kv"><span class="k">EVIDENCE COUNT</span>'
        '<span class="v">UNKNOWN / NOT VERIFIED (not persisted per task)</span></div>'
        '</div></div></div>')


def _graph(data: Dict[str, Any]) -> str:
    if data["empty"]:
        return ""
    nodes = []
    nodes.append('<div class="gnode run"><span class="glabel">RUN</span>'
                 f'<span class="gval mono">{dt._e(data["run"].run_id)}</span>'
                 f'<span class="gsub mono">{dt._e(data["state"].upper())}</span>'
                 '</div><div class="garrow">↓</div>')
    nodes.append('<div class="gnode mission"><span class="glabel">MISSION</span>'
                 f'<span class="gval mono">{dt._e(data["mission_id"])}</span>'
                 f'<span class="gsub">{dt._e(data["mission"])}</span>'
                 '</div><div class="garrow">↓</div>')
    nodes.append('<div class="gnode root"><span class="glabel">TASK (root)</span>'
                 f'<span class="gval mono">{dt._e(data["root_task_id"])}</span>'
                 f'<span class="gsub mono">role {dt._e(data["root_role"])}'
                 '</span></div><div class="garrow">↓</div>')
    nodes.append('<div class="tasklist">' +
                 "".join(_task_node(t) for t in data["subtasks"]) +
                 '</div><div class="garrow">↓</div>')
    outcomes = []
    outcomes.append(f'<span class="ochip">EVIDENCE {data["evidence_count"]}</span>')
    if data["findings"]:
        for fid, st in sorted(data["findings"].items()):
            outcomes.append(f'<span class="ochip mono">{dt._e(fid)}:'
                            f'{dt._e(st.upper())}</span>')
    if data["verifications"]:
        outcomes.append(f'<span class="ochip ok">VERIFIED '
                        f'{len(data["verifications"])}</span>')
    if data["falsifications"]:
        outcomes.append(f'<span class="ochip crit">FALSIFIED '
                        f'{len(data["falsifications"])}</span>')
    gate = data["gate"] or {}
    gdecision = (gate.get("decision") or "in-progress").upper()
    gkind = ("ok" if gate.get("decision") == "complete"
             else "crit" if gate.get("decision") == "refuse" else "muted")
    outcomes.append(f'{dt._pill("GATE: " + gdecision, gkind)}')
    nodes.append('<div class="gnode outcomes"><span class="glabel">OUTCOMES'
                 '(per run)</span><div class="ochips">' +
                 "".join(outcomes) + '</div></div>')
    return ('<section class="panel"><h2>OPERATION GRAPH</h2>'
            '<p class="note">Click a task to expand its declared '
            'role/skill/capability. TASK→EVIDENCE and TASK→TARGET are not '
            'persisted per task, so they are shown as UNKNOWN / NOT '
            'VERIFIED rather than invented.</p>'
            f'<div class="graph">{"".join(nodes)}</div>'
            '<div class="links">'
            f'<a class="row-link" href="/operations/{dt._e(data["run"].run_id)}">console</a>'
            f' · <a class="row-link" href="/operations/{dt._e(data["run"].run_id)}/decision-trace">decision-trace</a>'
            f' · <a class="row-link" href="/operations/{dt._e(data["run"].run_id)}/events">events</a>'
            f' · <a class="row-link" href="/operations/evidence">evidence</a>'
            f' · <a class="row-link" href="/operations/findings">findings</a>'
            '</div></section>')


def _replan(data: Dict[str, Any]) -> str:
    if data["empty"]:
        return ""
    if data["replans"]:
        rows = []
        for r in data["replans"]:
            rows.append(
                f'<div class="kv"><span class="k mono">'
                f'{dt._e(r["refuted_finding_id"] or "—")}</span>'
                f'<span class="v mono">{dt._e(r["parent_plan_id"] or "—")} → '
                f'{dt._e(r["plan_b_id"] or "—")}</span></div>')
        body = ('<p class="note">A replan edge exists in this run\'s '
                'persisted evidence.</p>'
                f'<div class="kvlist">{"".join(rows)}</div>')
    else:
        body = ('<p class="empty">NO REFUTATION/REPLAN RECORD — no '
                'producer="replanner" evidence is persisted for this run. '
                'Refutation/replan edges are shown ONLY when the persisted '
                'evidence carries them.</p>')
        if data["refuted"]:
            body += (f'<p class="note">Refuted findings present without a '
                     f'replan record: {dt._e(", ".join(data["refuted"]))}'
                     f'</p>')
    return ('<section class="panel"><h2>REFUTATION / REPLAN</h2>'
            f'{body}</section>')


def _nav() -> str:
    return ('<section class="panel"><h2>NAVIGATION</h2><div class="navgrid">'
            '<a class="navlink" href="/command">COMMAND CENTER</a>'
            '<a class="navlink" href="/operations">OPERATIONS</a>'
            '<a class="navlink" href="/operations/findings">FINDINGS</a>'
            '<a class="navlink" href="/operations/evidence">EVIDENCE</a>'
            '<a class="navlink" href="/operations/gate">POLICY &amp; GATE</a>'
            '<a class="navlink" href="/operations/capabilities">ARSENAL</a>'
            '</div></section>')


_EXTRA_CSS = """
.model-panel{border-color:rgba(215,160,68,.5)}
.model-title{font-size:16px;font-weight:700;letter-spacing:.1em;
color:var(--warn);margin-bottom:6px}
.flags{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.flag{font-size:10px;letter-spacing:.06em;text-transform:uppercase;
border:1px solid rgba(215,160,68,.5);color:var(--warn);border-radius:10px;
padding:3px 9px}
.runs{display:flex;gap:8px;flex-wrap:wrap}
.runlink{font-size:11px;border:1px solid var(--border);border-radius:10px;
padding:4px 10px;color:var(--sec);text-decoration:none}
.runlink.active{color:var(--text);border-color:var(--primary);
background:rgba(91,127,224,.12)}
.runlink:hover{border-color:var(--primary)}
.row-inline{margin:6px 0}
.graph{display:flex;flex-direction:column;align-items:stretch;margin:8px 0}
.gnode{border:1px solid var(--border);border-radius:4px;padding:8px 12px;
background:var(--panel2);display:flex;gap:12px;align-items:center;
flex-wrap:wrap}
.gnode.run{border-color:rgba(91,127,224,.5)}
.gnode.mission{border-color:rgba(91,127,224,.4)}
.glabel{font-size:10px;letter-spacing:.08em;text-transform:uppercase;
color:var(--muted);min-width:90px}
.gval{color:var(--text);font-size:12px}
.gsub{color:var(--sec);font-size:11px}
.garrow{color:var(--muted);padding:3px 0 3px 16px}
.tasklist{display:flex;flex-direction:column;gap:4px}
.tnode{border:1px solid var(--border);border-left:2px solid
rgba(91,127,224,.5);border-radius:3px;background:var(--panel)}
.thead{display:grid;grid-template-columns:180px 130px 1fr;gap:10px;
align-items:center;width:100%;text-align:left;background:none;border:none;
color:inherit;font:inherit;padding:6px 10px;cursor:pointer}
.thead:hover{background:var(--panel2)}
.tname{color:var(--text);font-size:11.5px;text-transform:uppercase;
letter-spacing:.05em}
.trole{color:var(--sec);font-size:11px}
.tbody{display:none;padding:8px 14px 12px 14px;background:var(--panel2)}
.tnode.open .tbody{display:block}
.gnode.outcomes{flex-direction:column;align-items:flex-start}
.ochips{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px}
.ochip{font-size:10.5px;letter-spacing:.05em;border:1px solid var(--border);
border-radius:10px;padding:3px 9px;color:var(--sec)}
.ochip.ok{color:var(--ok);border-color:rgba(53,183,122,.5)}
.ochip.crit{color:var(--crit);border-color:rgba(211,79,97,.5)}
.links{margin-top:10px}
.filterbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.search{font:inherit;font-size:11.5px;background:var(--bg);color:var(--text);
border:1px solid var(--border);border-radius:3px;padding:6px 9px;min-width:220px}
.row-link{color:var(--primary);text-decoration:none}
.navgrid{display:flex;gap:8px;flex-wrap:wrap}
.navlink{font-size:11px;letter-spacing:.05em;text-transform:uppercase;
border:1px solid var(--border);border-radius:10px;padding:5px 11px;
color:var(--primary);text-decoration:none}
.navlink:hover{border-color:var(--primary)}
"""


_JS = r"""
(function(){
  var search = document.getElementById('search');
  var box = document.getElementById('graph-tasks');
  function apply(){
    if(!box) return;
    var rows = box.querySelectorAll('.vstep');
    for(var i=0;i<rows.length;i++){
      var show = true;
      if(search && search.value){
        var q = search.value.toLowerCase();
        show = (rows[i].getAttribute('data-search')||'').indexOf(q) >= 0;
      }
      rows[i].style.display = show ? '' : 'none';
    }
  }
  if(search){ search.addEventListener('input', apply); }
  document.addEventListener('click', function(e){
    var head = e.target.closest ? e.target.closest('.thead') : null;
    if(head){ var r = head.parentNode; var o = r.classList.toggle('open');
      head.setAttribute('aria-expanded', o ? 'true' : 'false'); }
  });
})();
"""


def render_graph(*, runs_root, sessions_root,
                 selected_run_id: Optional[str] = None) -> str:
    data = collect(runs_root=runs_root, sessions_root=sessions_root,
                   selected_run_id=selected_run_id)
    filterbar = ('<section class="panel"><h2>FILTER</h2>'
                 '<div class="filterbar"><input id="search" class="search" '
                 'type="search" placeholder="task / role / skill / capability…" '
                 'aria-label="search tasks"></div>'
                 '<p class="note">Client-side only; filters the task nodes '
                 'below. No server query change beyond run selection.</p>'
                 '</section>')
    graph = _graph(data)
    if graph:
        graph = graph.replace('<div class="tasklist">',
                              '<div class="tasklist" id="graph-tasks">', 1)
    body = (
        f'{_disclaimers(data)}'
        f'{_run_selector(data)}'
        f'{_run_summary(data)}'
        f'{filterbar if not data["empty"] else ""}'
        f'{graph}'
        f'{_replan(data)}'
        f'{_nav()}'
        '<p class="readonly">READ-ONLY OPERATION GRAPH · task/run state via '
        'harness.api · current model = fixed pipeline · no graph mutation, '
        'no execution, no task controls</p>'
    )
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RAPHAEL — Operation Graph</title>'
        f'<style>{dt._CSS}{_EXTRA_CSS}</style></head><body>'
        '<header class="cmdbar"><span class="brand">RAPHAEL</span>'
        '<span class="screen">Operation Graph</span>'
        '<span class="banner">GOVERNED OPS // SCOPE-LOCKED</span>'
        '<span class="spacer"></span>'
        f'<span class="cmeta mono">{len(data["runs"])} OPERATIONS</span>'
        '<span class="led ok"></span></header>'
        f'<main>{body}</main>'
        '<footer class="policystrip mono">POLICY: FAIL-CLOSED · MODE: '
        'GOVERNED · GATE: QUALITY</footer>'
        f'<script>{_JS}</script>'
        "</body></html>")


__all__ = ["collect", "render_graph"]
