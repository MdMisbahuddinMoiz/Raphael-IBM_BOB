"""raphael_ibm_bob.http.views.findings_intelligence — M15.6.

Read-only Findings Intelligence: a persisted, cross-operation view of
every Finding the governed system recorded, with its real lifecycle,
evidence relationship, and operation context.

    GET /operations/findings   (text/html)

Authoritative sources ONLY (via `harness.api`):

- `get_runs` / `get_run`            -> operation, mission, target, workspace
- `get_evidence`                    -> ledger records (kind == "finding"
                                        and the `EvidenceRecord` rows whose
                                        `finding_id` links them)
- `get_session`                     -> model/provider reference (names only)
- `list_skills`                     -> skill -> role declaration

There is no findings API in `harness.api` and none is added: the
persisted ledger records are the authoritative source, read through the
existing read-only `get_evidence` path. Nothing here executes,
authorizes, mutates a finding, mutates evidence, or fabricates a field.

Lifecycle (exact, never renamed or collapsed):

    UNVERIFIED -> VERIFIED
    UNVERIFIED -> REFUTED
    VERIFIED   -> REFUTED | SUPERSEDED
    REFUTED    -> SUPERSEDED

History is shown ONLY where the ledger actually persisted it: every
transition is a `kind="finding"` record carrying `prev_state`/`state`,
so the observed transitions are real. Fields the ledger does not carry
(e.g. `supersedes`, severity/risk/confidence) are shown as
UNKNOWN / NOT VERIFIED, never invented.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from raphael_ibm_bob.harness import api
from raphael_ibm_bob.http.views import decision_trace as dt

HTML = "text/html; charset=utf-8"

STATES: Tuple[str, ...] = ("unverified", "verified", "refuted",
                           "superseded")

_VERIFICATION_PRODUCERS = ("verifier",)
_REFUTATION_PRODUCERS = ("falsifier",)


# ---------------------------------------------------------------------------
# aggregation (read-only, harness.api only)
# ---------------------------------------------------------------------------

def _skill_role() -> Dict[str, str]:
    return {s.id: (s.role or "") for s in api.list_skills()}


def _fmt_start(ts: Any) -> str:
    return dt._fmt_ts(ts) or "—"


def _findings_for_run(run, records: List[Dict[str, Any]],
                      session) -> List[Dict[str, Any]]:
    history: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        if record.get("kind") != "finding":
            continue
        fid = record.get("finding_id")
        if not fid:
            continue
        history.setdefault(fid, []).append(record)

    linked_evidence: Dict[str, List[Dict[str, Any]]] = {}
    linked_requests: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        fid = record.get("finding_id")
        if not fid:
            continue
        if record.get("kind") == "evidence":
            linked_evidence.setdefault(fid, []).append(record)
        elif record.get("kind") == "request":
            linked_requests.setdefault(fid, []).append(record)

    results: List[Dict[str, Any]] = []
    for fid, rows in history.items():
        rows.sort(key=lambda r: r.get("seq") or 0)
        current = rows[-1]
        previous = rows[0]
        evidence = sorted(linked_evidence.get(fid, []),
                          key=lambda r: r.get("seq") or 0)
        requests = linked_requests.get(fid, [])
        skills = sorted({
            (r.get("requester") or "").split("skill:", 1)[1]
            for r in requests
            if (r.get("requester") or "").startswith("skill:")})
        timestamps = [r.get("ts") or 0 for r in rows]
        timestamps += [r.get("ts") or 0 for r in evidence]
        results.append({
            "finding_id": fid,
            "state": (current.get("state") or "unknown").lower(),
            "summary": current.get("summary") or previous.get("summary") or "",
            "target": current.get("target") or previous.get("target") or "",
            "run_id": run.run_id,
            "mission_id": run.mission.mission_id,
            "mission": run.mission.description or run.mission.mission_id,
            "workspace": run.workspace_root,
            "model": getattr(session, "model", None),
            "provider": getattr(session, "provider", None),
            "history": [{
                "seq": r.get("seq"),
                "ts": r.get("ts"),
                "prev_state": r.get("prev_state"),
                "state": r.get("state"),
            } for r in rows],
            "evidence": [{
                "evidence_id": r.get("evidence_id"),
                "producer": r.get("producer"),
                "kind": (r.get("payload") or {}).get("kind"),
                "request_seq": r.get("request_seq"),
                "result_seq": r.get("result_seq"),
                "ts": r.get("ts"),
            } for r in evidence],
            "evidence_count": len(evidence),
            "requests": [{
                "requester": r.get("requester"),
                "capability": r.get("capability"),
                "target": r.get("target"),
                "seq": r.get("seq"),
            } for r in requests],
            "skills": skills,
            "last_ts": max(timestamps) if timestamps else 0,
        })
    return results


def collect(*, runs_root, sessions_root) -> Dict[str, Any]:
    roles = _skill_role()
    findings: List[Dict[str, Any]] = []
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
            session = api.get_session(run.session_id, sessions_root)
        except Exception:
            session = None
        run_findings = _findings_for_run(run, records, session)
        for item in run_findings:
            item["roles"] = sorted({roles.get(s, "") for s in item["skills"]}
                                   - {""})
        findings.extend(run_findings)
        operations.append({"run_id": run_id, "state": run.state,
                           "mission_id": run.mission.mission_id,
                           "mission": run.mission.description,
                           "workspace": run.workspace_root})

    findings.sort(key=lambda f: (f["last_ts"] or 0, f["finding_id"]),
                  reverse=True)
    counts = {state: 0 for state in STATES}
    for item in findings:
        if item["state"] in counts:
            counts[item["state"]] += 1
    return {
        "findings": findings,
        "counts": counts,
        "total": len(findings),
        "operations": operations,
        "targets": sorted({f["workspace"] for f in findings}),
    }


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _status_kind(state: str) -> str:
    return {"verified": "ok", "refuted": "crit",
            "superseded": "muted", "unverified": "warn"}.get(state, "muted")


def _summary(data: Dict[str, Any]) -> str:
    counts = data["counts"]
    metrics = (
        f'<div class="metrics">'
        f'<div class="metric"><span class="mv">{data["total"]}</span>'
        f'<span class="ml">TOTAL FINDINGS</span></div>'
        f'<div class="metric warn"><span class="mv">'
        f'{counts["unverified"]}</span>'
        f'<span class="ml">UNVERIFIED</span></div>'
        f'<div class="metric ok"><span class="mv">{counts["verified"]}</span>'
        f'<span class="ml">VERIFIED</span></div>'
        f'<div class="metric crit"><span class="mv">{counts["refuted"]}</span>'
        f'<span class="ml">REFUTED</span></div>'
        f'<div class="metric"><span class="mv">{counts["superseded"]}</span>'
        f'<span class="ml">SUPERSEDED</span></div>'
        '</div>')
    lifecycle = (
        '<p class="note">Lifecycle (exact, persisted): UNVERIFIED → '
        'VERIFIED | REFUTED · VERIFIED → REFUTED | SUPERSEDED · '
        'REFUTED → SUPERSEDED. REFUTED is not FAILED; a retest is not '
        'proof.</p>')
    return ('<section class="panel"><h2>FINDINGS SUMMARY</h2>'
            f'{metrics}{lifecycle}</section>')


def _filterbar(data: Dict[str, Any]) -> str:
    chips = ['<button type="button" class="chip active" data-filter="all">'
             'ALL</button>']
    for state in STATES:
        chips.append(f'<button type="button" class="chip" '
                     f'data-filter="{dt._e(state)}">'
                     f'{dt._e(state.upper())}</button>')
    return ('<section class="panel"><h2>FILTER &amp; SEARCH</h2>'
            '<div class="filterbar"><div class="chips">'
            + "".join(chips) +
            '</div><input id="search" class="search" type="search" '
            'placeholder="finding id / mission / target…" '
            'aria-label="search findings"></div>'
            '<p class="note">Client-side only. No server query semantics '
            'change and no new endpoint.</p></section>')


def _detail(item: Dict[str, Any]) -> str:
    history_rows = []
    for step in item["history"]:
        prev = (step["prev_state"] or "—")
        history_rows.append(
            f'<div class="kv"><span class="k mono">'
            f'{dt._e(_fmt_start(step["ts"]))}</span>'
            f'<span class="v mono">{dt._e(prev.upper())} → '
            f'{dt._e((step["state"] or "").upper())}</span></div>')
    if not history_rows:
        history_rows.append('<div class="kv"><span class="k">TRANSITIONS'
                            '</span><span class="v">NOT VERIFIED</span>'
                            '</div>')

    evidence_rows = []
    for ev in item["evidence"]:
        evidence_rows.append(
            f'<div class="kv"><span class="k mono">'
            f'{dt._e(ev["evidence_id"] or "—")}</span>'
            f'<span class="v">{dt._e(ev["producer"] or "—")} · '
            f'{dt._e(ev["kind"] or "—")}</span></div>')
    if not evidence_rows:
        evidence_rows.append('<div class="kv"><span class="k">EVIDENCE'
                             '</span><span class="v">none linked</span>'
                             '</div>')

    verification = [ev for ev in item["evidence"]
                    if ev["producer"] in _VERIFICATION_PRODUCERS]
    refutation = [ev for ev in item["evidence"]
                  if ev["producer"] in _REFUTATION_PRODUCERS]

    def _ev_list(rows) -> str:
        if not rows:
            return "NOT VERIFIED"
        return ", ".join(dt._e(r["evidence_id"] or "—") for r in rows)

    requests = item["requests"]
    request_rows = "".join(
        f'<div class="kv"><span class="k mono">{dt._e(r["requester"])}</span>'
        f'<span class="v">{dt._e(r["capability"])} '
        f'{dt._e(r["target"])}</span></div>' for r in requests)
    if not request_rows:
        request_rows = ('<div class="kv"><span class="k">REQUESTS</span>'
                        '<span class="v">none persisted against this '
                        'finding_id</span></div>')

    pairs = [
        ("SUMMARY", item["summary"] or "—"),
        ("TARGET", item["target"] or "—"),
        ("OPERATION", item["run_id"]),
        ("MISSION", item["mission_id"]),
        ("WORKSPACE", item["workspace"]),
        ("MODEL / PROVIDER", f'{item["model"] or "—"} / '
                             f'{item["provider"] or "—"}'),
        ("SUPERSEDES", "UNKNOWN / NOT VERIFIED (not persisted in the "
                       "ledger record)"),
        ("RELATED SKILL(S)", ", ".join(item["skills"]) or "NOT VERIFIED"),
        ("RELATED ROLE(S)", ", ".join(item["roles"]) or "NOT VERIFIED"),
        ("VERIFICATION EVIDENCE", _ev_list(verification)),
        ("REFUTATION EVIDENCE", _ev_list(refutation)),
    ]
    kv = "".join(
        f'<div class="kv"><span class="k">{dt._e(k)}</span>'
        f'<span class="v">{v if k in ("SUPERSEDES",) else dt._e(v)}</span>'
        f'</div>' for k, v in pairs)
    return (
        '<div class="detail-grid">'
        f'<div><div class="sublabel">PERSISTED DETAIL</div>'
        f'<div class="kvlist">{kv}</div></div>'
        f'<div><div class="sublabel">OBSERVED LIFECYCLE TRANSITIONS</div>'
        f'<div class="kvlist">{ "".join(history_rows) }</div>'
        f'<div class="sublabel">LINKED EVIDENCE ({item["evidence_count"]})'
        f'</div><div class="kvlist">{ "".join(evidence_rows) }</div>'
        f'<div class="sublabel">FINDING-LINKED REQUESTS</div>'
        f'<div class="kvlist">{request_rows}</div></div>'
        '</div>')


def _table(data: Dict[str, Any]) -> str:
    if not data["findings"]:
        return ('<section class="panel"><h2>FINDINGS</h2>'
                '<p class="empty">No findings recorded across Harness-'
                'managed operations. This is an explicit empty state, not '
                'a placeholder.</p></section>')
    rows = []
    for item in data["findings"]:
        state = item["state"]
        rows.append(
            f'<div class="frow" data-state="{dt._e(state)}" '
            f'data-search="{dt._e((item["finding_id"] + " " + item["mission"] + " " + item["target"] + " " + item["summary"]).lower())}">'
            f'<button type="button" class="fhead" aria-expanded="false">'
            f'<span class="fid mono">{dt._e(item["finding_id"])}</span>'
            f'<span class="fst"><span class="pill {_status_kind(state)}">'
            f'{dt._e(state.upper())}</span></span>'
            f'<span class="ftarget mono">{dt._e(item["target"] or "—")}</span>'
            f'<span class="fws mono">{dt._e(item["workspace"])}</span>'
            f'<span class="fop"><a class="row-link mono" href="/operations/'
            f'{dt._e(item["run_id"])}">{dt._e(item["run_id"])}</a></span>'
            f'<span class="fmission">{dt._e(item["mission"])}</span>'
            f'<span class="fev mono">{item["evidence_count"]}</span>'
            f'<span class="fts mono">{dt._e(_fmt_start(item["last_ts"]))}'
            f'</span></button>'
            f'<div class="fdet">{_detail(item)}</div></div>')
    return (
        '<section class="panel"><h2>FINDINGS (' + str(data["total"]) +
        ')</h2>'
        '<div class="ftable">'
        '<div class="frow-head"><span>FINDING ID</span><span>STATUS</span>'
        '<span>TARGET</span><span>WORKSPACE</span><span>OPERATION</span>'
        '<span>MISSION</span><span>EVID</span><span>LAST ACTIVITY</span>'
        '</div>'
        f'<div id="findings">{ "".join(rows) }</div>'
        '</div>'
        '<p class="note">Rows expand in place to show the persisted '
        'detail, observed lifecycle transitions, and linked evidence. '
        'Fields the ledger does not carry are shown as UNKNOWN / NOT '
        'VERIFIED.</p></section>')


def _operations(data: Dict[str, Any]) -> str:
    if not data["operations"]:
        return ('<section class="panel"><h2>OPERATION CONTEXT</h2>'
                '<p class="empty">No Harness-managed operations.</p>'
                '</section>')
    rows = []
    for op in data["operations"]:
        rows.append(
            f'<tr><td><a class="row-link mono" href="/operations/'
            f'{dt._e(op["run_id"])}">{dt._e(op["run_id"])}</a></td>'
            f'<td class="mono">{dt._e(op["mission_id"])}</td>'
            f'<td>{dt._pill(op["state"].upper(), "muted")}</td>'
            f'<td class="mono"><a class="row-link" '
            f'href="/operations/{dt._e(op["run_id"])}/decision-trace">'
            f'decision-trace</a> · <a class="row-link" '
            f'href="/operations/{dt._e(op["run_id"])}/events">events</a>'
            f'</td></tr>')
    return ('<section class="panel"><h2>OPERATION CONTEXT</h2>'
            '<p class="note">Only resolvable run IDs are linked.</p>'
            '<table class="dense"><thead><tr><th>OPERATION</th>'
            '<th>MISSION</th><th>STATE</th><th>VIEWS</th></tr></thead>'
            f'<tbody>{ "".join(rows) }</tbody></table></section>')


def _navigation() -> str:
    return ('<section class="panel"><h2>NAVIGATION</h2>'
            '<div class="navgrid">'
            '<a class="navlink" href="/command">COMMAND CENTER</a>'
            '<a class="navlink" href="/operations">OPERATIONS</a>'
            '</div></section>')


_EXTRA_CSS = """
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
gap:8px;margin:6px 0 12px}
.metric{background:var(--panel2);border:1px solid var(--border);
border-radius:4px;padding:10px 12px;display:grid;gap:2px}
.metric .mv{font-size:22px;font-weight:700;letter-spacing:.04em;color:var(--text)}
.metric .ml{font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;
color:var(--muted)}
.metric.ok .mv{color:var(--ok)}
.metric.crit .mv{color:var(--crit)}
.metric.warn .mv{color:var(--warn)}
.filterbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{font:inherit;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;
background:var(--panel2);color:var(--sec);border:1px solid var(--border);
border-radius:10px;padding:4px 10px;cursor:pointer}
.chip:hover{border-color:var(--primary)}
.chip.active{color:var(--text);border-color:var(--primary);
background:rgba(91,127,224,.12)}
.search{font:inherit;font-size:11.5px;background:var(--bg);color:var(--text);
border:1px solid var(--border);border-radius:3px;padding:6px 9px;min-width:220px}
.frow{border-bottom:1px solid rgba(36,42,51,.6)}
.frow:last-child{border-bottom:none}
.ftable{overflow-x:auto}
.frow-head{display:grid;
grid-template-columns:140px 100px 190px 220px 180px 1fr 54px 100px;
gap:8px;padding:6px 10px;color:var(--muted);font-size:10px;
letter-spacing:.06em;text-transform:uppercase;border-bottom:1px solid
var(--border);min-width:1120px}
.fhead{display:grid;
grid-template-columns:140px 100px 190px 220px 180px 1fr 54px 100px;
gap:8px;align-items:center;width:100%;text-align:left;background:none;
border:none;color:inherit;font:inherit;padding:6px 10px;cursor:pointer;
min-width:1120px}
.fhead > span{min-width:0;overflow:hidden;text-overflow:ellipsis;
white-space:nowrap}
.fhead:hover{background:var(--panel2)}
.fid{color:var(--primary);font-size:11.5px;word-break:break-all}
.ftarget,.fws,.fev,.fts{color:var(--sec);font-size:11px;word-break:break-all}
.fmission{color:var(--text);font-size:11.5px}
.fdet{display:none;padding:10px 14px 14px 14px;background:var(--panel2)}
.frow.open .fdet{display:block}
.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media (max-width:1100px){.detail-grid{grid-template-columns:1fr}}
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
  var box = document.getElementById('findings');
  var filter = 'all';
  function visible(row){
    if(filter !== 'all' && row.getAttribute('data-state') !== filter) return false;
    if(search && search.value){
      var q = search.value.toLowerCase();
      if((row.getAttribute('data-search')||'').indexOf(q) < 0) return false;
    }
    return true;
  }
  function apply(){
    if(!box) return;
    var rows = box.querySelectorAll('.frow');
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
  if(box){
    box.addEventListener('click', function(e){
      var head = e.target.closest ? e.target.closest('.fhead') : null;
      if(head){ var r = head.parentNode; var o = r.classList.toggle('open');
        head.setAttribute('aria-expanded', o ? 'true' : 'false'); }
    });
  }
})();
"""


def render_findings(*, runs_root, sessions_root) -> str:
    data = collect(runs_root=runs_root, sessions_root=sessions_root)
    body = (
        f'{_summary(data)}'
        f'{_filterbar(data)}'
        f'{_table(data)}'
        f'{_operations(data)}'
        f'{_navigation()}'
        '<p class="readonly">READ-ONLY FINDINGS VIEW · aggregated from '
        'harness.api (get_runs/get_run/get_evidence/get_session/list_skills) '
        '· no mutation, no execution, no new store</p>'
    )
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RAPHAEL — Findings Intelligence</title>'
        f'<style>{dt._CSS}{_EXTRA_CSS}</style></head><body>'
        '<header class="cmdbar"><span class="brand">RAPHAEL</span>'
        '<span class="screen">Findings Intelligence</span>'
        '<span class="banner">GOVERNED OPS // SCOPE-LOCKED</span>'
        '<span class="spacer"></span>'
        f'<span class="cmeta mono">{data["total"]} FINDINGS</span>'
        f'<span class="cmeta mono">{len(data["operations"])} OPERATIONS</span>'
        '<span class="led ok"></span></header>'
        f'<main>{body}</main>'
        '<footer class="policystrip mono">POLICY: FAIL-CLOSED · MODE: '
        'GOVERNED · GATE: QUALITY</footer>'
        f'<script>{_JS}</script>'
        "</body></html>")


__all__ = ["STATES", "collect", "render_findings"]
