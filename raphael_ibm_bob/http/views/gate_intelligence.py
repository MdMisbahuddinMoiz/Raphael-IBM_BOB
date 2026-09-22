"""raphael_ibm_bob.http.views.gate_intelligence — M15.8.

Read-only Policy & Quality Gate Intelligence: how RAPHAEL's governed
execution and completion authority are represented for Harness-managed
operations.

    GET /operations/gate   (text/html)

    ACTION REQUEST -> RUNTIME -> BROKER -> POLICY -> ALLOW/DENY
      -> EXECUTION -> EVIDENCE -> VERIFICATION/FALSIFICATION
      -> QUALITY GATE -> COMPLETE / REFUSE

Authoritative source ONLY (via `harness.api`):

- `get_runs` / `get_run`  -> operation, mission, target, workspace, state
- `get_evidence`          -> persisted ledger records: `request`,
                             `decision` (POLICY allow/deny), `result`
                             (execution), `evidence` (verifier / falsifier
                             / probe / regression), `finding`
- `get_gate`              -> the LAST persisted QualityGate record

CRITICAL AUTHORITY RULE
-----------------------
This screen is NOT a Quality Gate and does NOT recompute a verdict. It
DISPLAYS the authoritative persisted `GateRecord.decision` verbatim
(COMPLETE / REFUSE) or IN PROGRESS when the run is still pending/running
with no gate record yet. It never decides PASS/FAIL/COMPLETE/REFUSE.

The persisted gate record carries the evaluated condition names
(`checks`), the refusal `reasons`, evidence refs and finding refs — but
NOT a per-condition pass/fail split. Per-condition pass/fail is therefore
shown as UNKNOWN / NOT VERIFIED rather than re-derived here.

`ALLOW != EXECUTED`: a policy ALLOW is shown as execution only when a
persisted `result` record exists for the same request; a DENY is never
shown as executed. No mutation, no execution, no override, no new store.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from raphael_ibm_bob.harness import api
from raphael_ibm_bob.http.views import decision_trace as dt

HTML = "text/html; charset=utf-8"

FINAL_STATES = ("completed", "refused", "failed", "cancelled")


# ---------------------------------------------------------------------------
# aggregation (read-only, harness.api only)
# ---------------------------------------------------------------------------

def _latest_findings(records: List[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for record in records:
        if record.get("kind") == "finding" and record.get("finding_id"):
            out[record["finding_id"]] = (record.get("state") or "").lower()
    return out


def _run_view(run, records: List[Dict[str, Any]],
              gate: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    requests = {r.get("seq"): r for r in records
                if r.get("kind") == "request"}
    decisions = {r.get("request_seq"): r for r in records
                 if r.get("kind") == "decision"}
    results = {r.get("request_seq"): r for r in records
               if r.get("kind") == "result"}
    evidence = [r for r in records if r.get("kind") == "evidence"]
    findings = _latest_findings(records)

    policy_rows = []
    allow = deny = 0
    for seq in sorted(requests):
        request = requests[seq]
        decision = decisions.get(seq)
        result = results.get(seq)
        dec = (decision or {}).get("decision")
        if dec == "allow":
            allow += 1
        elif dec == "deny":
            deny += 1
        # ALLOW != EXECUTED: execution only from a persisted result record.
        if result is not None:
            executed = "SUCCESS" if result.get("success") else "FAILED"
        elif dec == "deny":
            executed = "NOT EXECUTED (DENY)"
        elif dec == "allow":
            executed = "ALLOWED · NO RESULT RECORD"
        else:
            executed = "UNKNOWN / NOT VERIFIED"
        policy_rows.append({
            "seq": seq,
            "capability": request.get("capability"),
            "target": request.get("target"),
            "requester": request.get("requester"),
            "decision": (dec or "unknown").upper() if dec else
                        "UNKNOWN / NOT VERIFIED",
            "reason": (decision or {}).get("reason") or "—",
            "executed": executed,
        })

    verifications = [r.get("evidence_id") for r in evidence
                     if r.get("producer") == "verifier"
                     and r.get("evidence_id")]
    falsifications = [r.get("evidence_id") for r in evidence
                      if r.get("producer") == "falsifier"
                      and r.get("evidence_id")]
    probes = [r.get("evidence_id") for r in evidence
              if r.get("producer") == "probe" and r.get("evidence_id")]

    if gate is not None:
        verdict = (gate.get("decision") or "unknown").upper()
        verdict_kind = ("ok" if gate.get("decision") == "complete"
                        else "crit" if gate.get("decision") == "refuse"
                        else "muted")
    elif run.state in ("pending", "running"):
        verdict = "IN PROGRESS"
        verdict_kind = "muted"
    else:
        verdict = "UNKNOWN / NOT VERIFIED"
        verdict_kind = "muted"

    passed_conds, failed_conds, unknown_conds, _names = dt.gate_breakdown(gate)

    return {
        "run_id": run.run_id,
        "mission_id": run.mission.mission_id,
        "mission": run.mission.description or run.mission.mission_id,
        "target": (run.mission.problem or {}).get("symptom_target") or "—",
        "workspace": run.workspace_root,
        "state": run.state,
        "terminal": run.is_terminal(),
        "gate": gate,
        "verdict": verdict,
        "verdict_kind": verdict_kind,
        "conditions": list((gate or {}).get("checks", [])),
        "passed_conditions": passed_conds,
        "failed_conditions": failed_conds,
        "unknown_conditions": unknown_conds,
        "reasons": list((gate or {}).get("reasons", [])),
        "gate_evidence_refs": list((gate or {}).get("evidence_refs", [])),
        "gate_finding_refs": list((gate or {}).get("finding_refs", [])),
        "policy_rows": policy_rows,
        "allow": allow,
        "deny": deny,
        "requests": len(requests),
        "results": len(results),
        "evidence": len(evidence),
        "verifications": verifications,
        "falsifications": falsifications,
        "probes": probes,
        "findings": findings,
    }


def collect(*, runs_root, sessions_root) -> Dict[str, Any]:
    del sessions_root
    operations: List[Dict[str, Any]] = []
    for run_id in api.get_runs(runs_root):
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
        operations.append(_run_view(run, records, gate))

    counts = {
        "operations": len(operations),
        "complete": sum(1 for o in operations if o["verdict"] == "COMPLETE"),
        "refuse": sum(1 for o in operations if o["verdict"] == "REFUSE"),
        "in_progress": sum(1 for o in operations
                           if o["verdict"] == "IN PROGRESS"),
        "unknown": sum(1 for o in operations
                       if o["verdict"] == "UNKNOWN / NOT VERIFIED"),
        "allow": sum(o["allow"] for o in operations),
        "deny": sum(o["deny"] for o in operations),
        "verified": sum(1 for o in operations for s in o["findings"].values()
                        if s == "verified"),
        "refuted": sum(1 for o in operations for s in o["findings"].values()
                       if s == "refuted"),
    }
    return {"operations": operations, "counts": counts}


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _summary(data: Dict[str, Any]) -> str:
    c = data["counts"]
    cells = (
        ("OPERATIONS", c["operations"], ""),
        ("COMPLETE", c["complete"], "ok"),
        ("REFUSE", c["refuse"], "crit"),
        ("IN PROGRESS", c["in_progress"], ""),
        ("POLICY ALLOW", c["allow"], ""),
        ("POLICY DENY", c["deny"], "crit"),
        ("VERIFIED", c["verified"], "ok"),
        ("REFUTED", c["refuted"], "crit"),
        ("UNKNOWN / NOT VERIFIED", c["unknown"], ""),
    )
    metrics = "".join(
        f'<div class="metric {kind}"><span class="mv">{value}</span>'
        f'<span class="ml">{dt._e(label)}</span></div>'
        for label, value, kind in cells)
    return ('<section class="panel"><h2>GATE SUMMARY</h2>'
            f'<div class="metrics">{metrics}</div>'
            '<p class="note">Every count is derived from persisted ledger '
            'and gate records. The verdict shown per operation is the '
            'authoritative persisted gate decision and is never '
            'recomputed here.</p></section>')


def _operations_table(data: Dict[str, Any]) -> str:
    if not data["operations"]:
        return ('<section class="panel"><h2>OPERATIONS</h2>'
                '<p class="empty">No Harness-managed operations. Explicit '
                'empty state.</p></section>')
    rows = []
    for op in data["operations"]:
        search = " ".join((op["run_id"], op["mission"], op["target"])).lower()
        rows.append(
            f'<tr class="grow" data-verdict="{dt._e(op["verdict"])}" '
            f'data-search="{dt._e(search)}">'
            f'<td><a class="row-link mono" href="/operations/'
            f'{dt._e(op["run_id"])}">{dt._e(op["run_id"])}</a></td>'
            f'<td>{dt._e(op["mission"])}</td>'
            f'<td class="mono">{dt._e(op["target"])}</td>'
            f'<td>{dt._pill(op["verdict"], op["verdict_kind"])}</td>'
            f'<td class="mono">{len(op["conditions"]) or "—"}</td>'
            f'<td>{dt._pill(op["state"].upper(), "muted")}</td></tr>')
    return ('<section class="panel"><h2>OPERATIONS</h2>'
            '<table class="dense"><thead><tr><th>OPERATION</th>'
            '<th>MISSION</th><th>TARGET</th><th>GATE VERDICT</th>'
            '<th>CONDITIONS</th><th>STATE</th></tr></thead>'
            f'<tbody id="gate-ops">{ "".join(rows) }</tbody></table>'
            '</section>')


def _gate_panels(data: Dict[str, Any]) -> str:
    if not data["operations"]:
        return ""
    panels = []
    for op in data["operations"]:
        gate = op["gate"]
        if gate is None:
            body = (f'<p class="empty">{dt._e(op["verdict"])} — no '
                    f'persisted gate record for this operation.</p>')
        else:
            conds = op["conditions"]
            passed_set = set(op["passed_conditions"])
            failed_set = set(op["failed_conditions"])
            cond_rows_html = []
            for c in conds:
                if c in passed_set:
                    mark, cls = "✓", "ok"
                elif c in failed_set:
                    mark, cls = "✕", "crit"
                else:
                    mark, cls = "•", "muted"
                cond_rows_html.append(
                    f'<div class="chk {cls}"><span class="mark">{mark}</span>'
                    f'<span class="mono">{dt._e(c)}</span></div>')
            cond_rows = "".join(cond_rows_html) or \
                '<p class="empty">No condition names persisted.</p>'
            reasons = "".join(
                f'<li>{dt._e(r)}</li>' for r in op["reasons"]) or \
                '<li class="none">No refusal reasons recorded.</li>'
            refs = ", ".join(dt._e(x) for x in op["gate_evidence_refs"]) \
                or "—"
            frefs = ", ".join(dt._e(x) for x in op["gate_finding_refs"]) \
                or "—"
            body = (
                f'<div class="gate-final {op["verdict_kind"]}">'
                f'{dt._e(op["verdict"])}</div>'
                f'<div class="kvlist">'
                f'<div class="kv"><span class="k">DECISION</span>'
                f'<span class="v mono">{dt._e(gate.get("decision"))}</span></div>'
                f'<div class="kv"><span class="k">CONDITIONS EVALUATED</span>'
                f'<span class="v mono">{len(conds)}</span></div>'
                f'<div class="kv"><span class="k">SEQUENCE</span>'
                f'<span class="v mono">{dt._e(gate.get("seq"))}</span></div>'
                f'<div class="kv"><span class="k">TIMESTAMP</span>'
                f'<span class="v mono">{dt._e(dt._fmt_ts(gate.get("ts")) or "—")}</span></div>'
                f'<div class="kv"><span class="k">DIGEST</span>'
                f'<span class="v mono">{dt._e(gate.get("digest"))}</span></div>'
                f'<div class="kv"><span class="k">EVIDENCE REFS</span>'
                f'<span class="v mono">{refs}</span></div>'
                f'<div class="kv"><span class="k">FINDING REFS</span>'
                f'<span class="v mono">{frefs}</span></div>'
                '</div>'
                '<div class="sublabel">CONDITIONS EVALUATED (persisted '
                'names)</div>'
                f'<div class="checklist">{cond_rows}</div>'
                '<p class="note">Per-condition pass/fail is taken directly '
                'from the persisted gate record (payload.passed / '
                'payload.failed); this screen does not recompute the gate. '
                'A condition recorded in neither collection is shown as '
                'UNKNOWN.</p>'
                '<div class="sublabel">RECORDED REFUSAL REASONS</div>'
                f'<ul class="reasons">{reasons}</ul>')
        panels.append(
            f'<section class="panel gate"><h2>QUALITY GATE · '
            f'{dt._e(op["run_id"])}</h2>{body}</section>')
    return "".join(panels)


def _policy_table(data: Dict[str, Any]) -> str:
    rows = []
    for op in data["operations"]:
        for row in op["policy_rows"]:
            dec = row["decision"]
            dec_kind = ("ok" if dec == "ALLOW"
                        else "crit" if dec == "DENY" else "muted")
            exe = row["executed"]
            exe_kind = ("ok" if exe == "SUCCESS"
                        else "crit" if exe in ("FAILED",
                                               "NOT EXECUTED (DENY)")
                        else "muted")
            rows.append(
                f'<tr>'
                f'<td><a class="row-link mono" href="/operations/'
                f'{dt._e(op["run_id"])}">{dt._e(op["run_id"])}</a></td>'
                f'<td class="mono">{dt._e(row["seq"])}</td>'
                f'<td class="mono">{dt._e(row["capability"])}</td>'
                f'<td class="mono">{dt._e(row["target"])}</td>'
                f'<td class="mono">{dt._e(row["requester"])}</td>'
                f'<td>{dt._pill(dec, dec_kind)}</td>'
                f'<td>{dt._e(row["reason"])}</td>'
                f'<td>{dt._pill(exe, exe_kind)}</td></tr>')
    if not rows:
        return ('<section class="panel"><h2>POLICY DECISIONS</h2>'
                '<p class="empty">No policy decisions persisted.</p>'
                '</section>')
    return ('<section class="panel"><h2>POLICY DECISIONS</h2>'
            '<p class="note">ALLOW is not execution: a request is shown as '
            'EXECUTED only when a persisted execution result exists for the '
            'same request. DENY is never shown as executed.</p>'
            '<table class="dense"><thead><tr><th>OPERATION</th><th>SEQ</th>'
            '<th>CAPABILITY</th><th>TARGET</th><th>REQUESTER</th>'
            '<th>POLICY</th><th>RECORDED REASON</th><th>EXECUTION</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table>'
            '</section>')


def _chain(data: Dict[str, Any]) -> str:
    total_req = sum(o["requests"] for o in data["operations"])
    total_dec = sum(o["allow"] + o["deny"] for o in data["operations"])
    total_res = sum(o["results"] for o in data["operations"])
    steps = [
        ("ACTION REQUEST", f"{total_req} persisted request record(s)",
         total_req > 0),
        ("RUNTIME", "UNKNOWN / NOT VERIFIED — Runtime is not separately "
         "persisted (only its mediated effect)", False),
        ("BROKER", "UNKNOWN / NOT VERIFIED — Broker is not separately "
         "persisted (only its mediated effect)", False),
        ("POLICY", f"{total_dec} persisted decision record(s)",
         total_dec > 0),
        ("ALLOW / DENY",
         f"ALLOW {sum(o['allow'] for o in data['operations'])} · "
         f"DENY {sum(o['deny'] for o in data['operations'])}", total_dec > 0),
        ("EXECUTION", f"{total_res} persisted result record(s)",
         total_res > 0),
    ]
    nodes = []
    for label, detail, observed in steps:
        cls = "node observed" if observed else "node unknown"
        nodes.append(f'<div class="{cls}"><span class="nlabel">{dt._e(label)}'
                     f'</span><span class="ndetail">{dt._e(detail)}</span>'
                     f'</div><span class="arrow">↓</span>')
    return ('<section class="panel"><h2>BROKER / RUNTIME CHAIN</h2>'
            '<div class="chain-v">' + "".join(nodes) + '</div>'
            '<p class="note">A step is marked OBSERVED only when persisted '
            'evidence supports it. Runtime and Broker are mediation, not '
            'persisted records, so they are UNKNOWN / NOT VERIFIED.</p>'
            '</section>')


def _verif(data: Dict[str, Any]) -> str:
    rows = []
    for op in data["operations"]:
        if not (op["verifications"] or op["falsifications"] or op["probes"]):
            continue
        rows.append(
            f'<tr><td class="mono">{dt._e(op["run_id"])}</td>'
            f'<td class="mono">{dt._e(", ".join(op["verifications"]) or "—")}</td>'
            f'<td class="mono">{dt._e(", ".join(op["falsifications"]) or "—")}</td>'
            f'<td class="mono">{dt._e(", ".join(op["probes"]) or "—")}</td>'
            f'<td class="mono">{dt._e(", ".join(op["findings"]) or "—")}</td>'
            f'</tr>')
    if not rows:
        return ('<section class="panel"><h2>VERIFICATION / '
                'FALSIFICATION</h2><p class="empty">No verification, '
                'falsification, or probe evidence persisted.</p></section>')
    return ('<section class="panel"><h2>VERIFICATION / FALSIFICATION</h2>'
            '<p class="note">Only persisted verifier / falsifier / probe '
            'evidence ids are shown.</p>'
            '<table class="dense"><thead><tr><th>OPERATION</th>'
            '<th>VERIFICATION</th><th>FALSIFICATION</th><th>PROBE</th>'
            '<th>FINDINGS</th></tr></thead><tbody>' + "".join(rows) +
            '</tbody></table></section>')


def _nav() -> str:
    return ('<section class="panel"><h2>NAVIGATION</h2><div class="navgrid">'
            '<a class="navlink" href="/command">COMMAND CENTER</a>'
            '<a class="navlink" href="/operations">OPERATIONS</a>'
            '<a class="navlink" href="/operations/findings">FINDINGS</a>'
            '<a class="navlink" href="/operations/evidence">EVIDENCE</a>'
            '</div><p class="note">Per-operation drill-down links appear in '
            'the tables above (console, decision-trace, events) — only for '
            'real resolvable run IDs.</p></section>')


_EXTRA_CSS = """
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
gap:8px;margin:6px 0 12px}
.metric{background:var(--panel2);border:1px solid var(--border);
border-radius:4px;padding:10px 12px;display:grid;gap:2px}
.metric .mv{font-size:22px;font-weight:700;letter-spacing:.04em;color:var(--text)}
.metric .ml{font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;
color:var(--muted)}
.metric.ok .mv{color:var(--ok)}
.metric.crit .mv{color:var(--crit)}
.gate-final{font-size:24px;font-weight:700;letter-spacing:.08em;
margin-bottom:8px}
.gate-final.ok{color:var(--ok)}
.gate-final.crit{color:var(--crit)}
.gate-final.muted{color:var(--muted)}
.checklist{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
gap:3px 16px;margin:8px 0}
.chk{display:flex;gap:8px;font-size:11.5px;align-items:center}
.chk .mark{color:var(--muted);width:10px}
.chk .cond-state{margin-left:auto;color:var(--muted);font-size:10px;
letter-spacing:.04em;text-transform:uppercase}
.reasons{margin:4px 0 0 18px;padding:0;color:var(--sec);font-size:11.5px}
.reasons .none{color:var(--muted);list-style:none;margin-left:-18px}
.chain-v{display:flex;flex-direction:column;align-items:flex-start;gap:2px;
margin:8px 0 14px}
.chain-v .node{padding:6px 12px;border:1px solid var(--border);
border-radius:3px;background:var(--panel2);display:flex;gap:12px;
align-items:center;flex-wrap:wrap}
.chain-v .node.observed{border-color:rgba(53,183,122,.4)}
.chain-v .node.unknown{border-color:rgba(215,160,68,.35)}
.chain-v .nlabel{font-size:11px;letter-spacing:.06em;color:var(--text);
text-transform:uppercase}
.chain-v .ndetail{font-size:11px;color:var(--muted)}
.chain-v .arrow{color:var(--muted);padding-left:14px}
.row-link{color:var(--primary);text-decoration:none}
.navgrid{display:flex;gap:8px;flex-wrap:wrap}
.navlink{font-size:11px;letter-spacing:.05em;text-transform:uppercase;
border:1px solid var(--border);border-radius:10px;padding:5px 11px;
color:var(--primary);text-decoration:none}
.navlink:hover{border-color:var(--primary)}
"""


_JS = r"""
(function(){
  var chips = Array.prototype.slice.call(document.querySelectorAll('.chip'));
  var search = document.getElementById('search');
  var box = document.getElementById('gate-ops');
  var filter = 'all';
  function visible(row){
    if(filter !== 'all' && row.getAttribute('data-verdict') !== filter) return false;
    if(search && search.value){
      var q = search.value.toLowerCase();
      if((row.getAttribute('data-search')||'').indexOf(q) < 0) return false;
    }
    return true;
  }
  function apply(){
    if(!box) return;
    var rows = box.querySelectorAll('.grow');
    for(var i=0;i<rows.length;i++){
      rows[i].style.display = visible(rows[i]) ? '' : 'none';
    }
  }
  chips.forEach(function(chip){
    chip.addEventListener('click', function(){
      filter = chip.getAttribute('data-filter');
      chips.forEach(function(c){ c.classList.remove('active'); });
      chip.classList.add('active'); apply();
    });
  });
  if(search){ search.addEventListener('input', apply); }
})();
"""


def render_gate(*, runs_root, sessions_root) -> str:
    data = collect(runs_root=runs_root, sessions_root=sessions_root)
    chips = ['<button type="button" class="chip active" data-filter="all">'
             'ALL</button>']
    for verdict, label in (("COMPLETE", "COMPLETE"), ("REFUSE", "REFUSE"),
                            ("IN PROGRESS", "IN PROGRESS")):
        chips.append(f'<button type="button" class="chip" '
                     f'data-filter="{dt._e(verdict)}">{dt._e(label)}</button>')
    body = (
        f'{_summary(data)}'
        '<section class="panel"><h2>FILTER &amp; SEARCH</h2>'
        '<div class="filterbar"><div class="chips">' + "".join(chips) +
        '</div><input id="search" class="search" type="search" '
        'placeholder="run id / mission / target…" aria-label="search"></div>'
        '<p class="note">Client-side only; no server query change.</p></section>'
        f'{_operations_table(data)}'
        f'{_gate_panels(data)}'
        f'{_policy_table(data)}'
        f'{_chain(data)}'
        f'{_verif(data)}'
        f'{_nav()}'
        '<p class="readonly">READ-ONLY POLICY &amp; GATE VIEW · aggregated '
        'from harness.api.get_runs/get_run/get_evidence/get_gate · the '
        'Quality Gate remains the sole COMPLETE authority; this screen only '
        'displays persisted verdicts</p>'
    )
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RAPHAEL — Policy &amp; Quality Gate</title>'
        f'<style>{dt._CSS}{_EXTRA_CSS}</style></head><body>'
        '<header class="cmdbar"><span class="brand">RAPHAEL</span>'
        '<span class="screen">Policy &amp; Quality Gate</span>'
        '<span class="banner">GOVERNED OPS // SCOPE-LOCKED</span>'
        '<span class="spacer"></span>'
        f'<span class="cmeta mono">{data["counts"]["complete"]} COMPLETE</span>'
        f'<span class="cmeta mono">{data["counts"]["refuse"]} REFUSE</span>'
        f'<span class="cmeta mono">{data["counts"]["operations"]} OPERATIONS</span>'
        '<span class="led ok"></span></header>'
        f'<main>{body}</main>'
        '<footer class="policystrip mono">POLICY: FAIL-CLOSED · MODE: '
        'GOVERNED · GATE: QUALITY</footer>'
        f'<script>{_JS}</script>'
        "</body></html>")


__all__ = ["collect", "render_gate"]
