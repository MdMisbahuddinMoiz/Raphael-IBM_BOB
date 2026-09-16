"""raphael_ibm_bob.http.views.evidence_intelligence — M15.7.

Read-only Evidence Intelligence: the persisted, cross-operation ledger
of everything the governed system recorded, presented as the observable
chain

    OPERATION -> ACTION/EVENT -> EVIDENCE -> FINDING
              -> VERIFICATION / FALSIFICATION -> QUALITY GATE

    GET /operations/evidence   (text/html)

Authoritative source ONLY (via `harness.api`): the run's append-only
ledger `runs/<run_id>/evidence.jsonl`, read through
`harness.api.get_evidence` (`evidence_ledger.LedgerReader`). Every row
is one persisted record (`kind` = request | decision | result |
evidence | finding | gate); nothing is inferred and nothing is invented.

Classification (verification / falsification / refutation / policy /
execution / probe) is derived ONLY from persisted `producer` / record
`kind` / payload `kind` fields. A relationship the ledger does not
carry is shown as UNKNOWN / NOT VERIFIED or NO FINDING REFERENCE.

Presentation only: no mutation, no execution, no new store, no new API,
no artifact store, no stream.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from raphael_ibm_bob.harness import api
from raphael_ibm_bob.http.views import decision_trace as dt

HTML = "text/html; charset=utf-8"

#: Filter categories -> the persisted record/producer they map to.
#: No category is invented: each is a real ledger field value.
FILTERS: Tuple[Tuple[str, str], ...] = (
    ("all", "ALL"),
    ("action", "ACTION"),
    ("policy", "POLICY"),
    ("execution", "EXECUTION"),
    ("evidence", "EVIDENCE"),
    ("finding", "FINDING"),
    ("gate", "GATE"),
    ("verification", "VERIFICATION"),
    ("falsification", "FALSIFICATION"),
    ("refutation", "REFUTATION"),
    ("probe", "PROBE"),
    ("regression", "REGRESSION"),
)

_KIND_LABEL = {
    "request": "ACTION REQUEST",
    "decision": "POLICY DECISION",
    "result": "EXECUTION RESULT",
    "evidence": "EVIDENCE",
    "finding": "FINDING",
    "gate": "GATE DECISION",
}


# ---------------------------------------------------------------------------
# classification (derived only from persisted fields)
# ---------------------------------------------------------------------------

def _categorize(record: Dict[str, Any]) -> str:
    kind = record.get("kind") or ""
    if kind == "decision":
        return "policy"
    if kind == "result":
        return "execution"
    if kind == "gate":
        return "gate"
    if kind == "finding":
        return "finding"
    if kind == "request":
        return "action"
    if kind == "evidence":
        producer = record.get("producer") or ""
        payload_kind = (record.get("payload") or {}).get("kind") or ""
        if producer == "verifier":
            return "verification"
        if producer == "falsifier":
            return "refutation" if payload_kind == "counter-example" \
                else "falsification"
        if producer == "probe" or payload_kind == "probe":
            return "probe"
        if producer == "regression" or payload_kind == "regression":
            return "regression"
        return "evidence"
    return "evidence"


def _actor(record: Dict[str, Any]) -> str:
    kind = record.get("kind") or ""
    return {
        "request": record.get("requester") or "—",
        "decision": "BOB Policy",
        "result": "Runtime",
        "gate": "Quality Gate",
        "finding": "Finding",
        "evidence": record.get("producer") or "evidence",
    }.get(kind, "—")


def _record_summary(record: Dict[str, Any]) -> str:
    kind = record.get("kind") or ""
    payload = record.get("payload") or {}
    if kind == "request":
        return f"{record.get('capability') or ''} " \
               f"{record.get('target') or ''}".strip()
    if kind == "decision":
        return f"{(record.get('decision') or '').upper()} " \
               f"{record.get('reason') or ''}".strip()
    if kind == "result":
        ref = record.get("artifact_ref") or ""
        return ("SUCCESS" if record.get("success") else "FAILED") + \
               (f" · {os.path.basename(ref)}" if ref else "")
    if kind == "gate":
        checks = record.get("checks") or []
        return f"{(record.get('decision') or '').upper()} " \
               f"({len(checks)} checks)"
    if kind == "finding":
        return f"{(record.get('state') or '').upper()} " \
               f"{record.get('summary') or ''}".strip()
    if kind == "evidence":
        label = payload.get("kind") or "evidence"
        return f"{label} · {record.get('evidence_id') or ''}".strip()
    return kind


def _row(run, record: Dict[str, Any]) -> Dict[str, Any]:
    kind = record.get("kind") or ""
    payload = record.get("payload") or {}
    return {
        "run_id": run.run_id,
        "mission_id": run.mission.mission_id,
        "workspace": run.workspace_root,
        "kind": kind,
        "category": _categorize(record),
        "seq": record.get("seq"),
        "ts": record.get("ts"),
        "evidence_id": record.get("evidence_id"),
        "payload_kind": payload.get("kind"),
        "actor": _actor(record),
        "request_seq": record.get("request_seq"),
        "finding_id": record.get("finding_id"),
        "artifact_ref": record.get("artifact_ref"),
        "summary": _record_summary(record),
        "record": record,
    }


def collect(*, runs_root, sessions_root) -> Dict[str, Any]:
    del sessions_root  # no session data is shown on this screen
    rows: List[Dict[str, Any]] = []
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
        for record in records:
            rows.append(_row(run, record))
        operations.append({"run_id": run_id, "state": run.state,
                           "mission_id": run.mission.mission_id})

    by_kind: Dict[str, int] = {}
    for row in rows:
        by_kind[row["kind"]] = by_kind.get(row["kind"], 0) + 1
    evidence_rows = [r for r in rows if r["kind"] == "evidence"]
    artifact_refs = sorted({
        r["artifact_ref"] for r in rows
        if r["kind"] == "result" and r["artifact_ref"]})
    finding_ids = sorted({
        r["finding_id"] for r in rows if r["finding_id"]})
    rows.sort(key=lambda r: (r["run_id"], r["seq"] or 0))
    return {
        "rows": rows,
        "operations": operations,
        "by_kind": by_kind,
        "total": len(rows),
        "evidence_total": len(evidence_rows),
        "artifact_refs": artifact_refs,
        "finding_ids": finding_ids,
    }


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _summary(data: Dict[str, Any]) -> str:
    by_kind = data["by_kind"]
    kinds = ("request", "decision", "result", "evidence", "finding", "gate")
    kind_cells = "".join(
        f'<div class="kv"><span class="k">{dt._e(_KIND_LABEL[k])}</span>'
        f'<span class="v mono">{by_kind.get(k, 0)}</span></div>'
        for k in kinds)
    metrics = (
        '<div class="metrics">'
        f'<div class="metric"><span class="mv">{data["total"]}</span>'
        f'<span class="ml">TOTAL RECORDS</span></div>'
        f'<div class="metric info"><span class="mv">'
        f'{data["evidence_total"]}</span>'
        f'<span class="ml">EVIDENCE RECORDS</span></div>'
        f'<div class="metric"><span class="mv">'
        f'{len(data["operations"])}</span>'
        f'<span class="ml">OPERATIONS</span></div>'
        f'<div class="metric"><span class="mv">'
        f'{len(data["finding_ids"])}</span>'
        f'<span class="ml">FINDINGS REFERENCED</span></div>'
        f'<div class="metric"><span class="mv">'
        f'{len(data["artifact_refs"])}</span>'
        f'<span class="ml">ARTIFACT REFERENCES</span></div>'
        '</div>')
    return ('<section class="panel"><h2>EVIDENCE SUMMARY</h2>'
            f'{metrics}'
            f'<div class="kvlist lifecycle">{kind_cells}</div>'
            '<p class="note">Every record is one persisted append-only '
            'ledger row. Classification uses only the persisted '
            '<span class="mono">kind</span> / '
            '<span class="mono">producer</span> / payload '
            '<span class="mono">kind</span> fields.</p></section>')


def _filterbar() -> str:
    chips = "".join(
        f'<button type="button" class="chip{" active" if key == "all" else ""}"'
        f' data-filter="{dt._e(key)}">{dt._e(label)}</button>'
        for key, label in FILTERS)
    return ('<section class="panel"><h2>FILTER &amp; SEARCH</h2>'
            '<div class="filterbar">'
            f'<div class="chips">{chips}</div>'
            '<input id="search" class="search" type="search" '
            'placeholder="evidence id / summary / source…" '
            'aria-label="search evidence"></div>'
            '<p class="note">Client-side only. No server query semantics '
            'change and no new endpoint.</p></section>')


def _detail(row: Dict[str, Any]) -> str:
    record = row["record"]
    pairs = [("RUN", row["run_id"]), ("MISSION", row["mission_id"]),
             ("RECORD KIND", row["kind"]),
             ("CLASSIFICATION", row["category"].upper()),
             ("SEQUENCE", row["seq"]),
             ("TIMESTAMP", dt._fmt_ts(row["ts"]) or "—"),
             ("SOURCE / ACTOR", row["actor"]),
             ("EVIDENCE ID", row["evidence_id"] or "—"),
             ("PAYLOAD KIND", row["payload_kind"] or "—"),
             ("REQUEST SEQ", row["request_seq"]),
             ("FINDING", row["finding_id"] or "NO FINDING REFERENCE"),
             ("ARTIFACT", row["artifact_ref"] or "—")]
    kv = "".join(
        f'<div class="kv"><span class="k">{dt._e(k)}</span>'
        f'<span class="v mono">{dt._e(v)}</span></div>' for k, v in pairs)
    payload = json.dumps(record, sort_keys=True, indent=2)
    return (f'<div class="sublabel">PERSISTED RECORD</div>'
            f'<div class="kvlist">{kv}</div>'
            '<div class="sublabel">FULL RECORD (persisted)</div>'
            f'<pre class="rec mono">{dt._e(payload)}</pre>')


def _table(data: Dict[str, Any]) -> str:
    if not data["rows"]:
        return ('<section class="panel"><h2>EVIDENCE RECORDS</h2>'
                '<p class="empty">No evidence records persisted across '
                'Harness-managed operations. This is an explicit empty '
                'state.</p></section>')
    rows = []
    for row in data["rows"]:
        eid = row["evidence_id"] or "—"
        finding = (f'<a class="row-link mono" '
                   f'href="/operations/findings">'
                   f'{dt._e(row["finding_id"])}</a>'
                   if row["finding_id"] else
                   '<span class="muted">NO FINDING REFERENCE</span>')
        artifact = (f'<div class="art mono">{dt._e(row["artifact_ref"])}'
                    f'</div>' if row["artifact_ref"] else "")
        search = " ".join(str(x) for x in (
            eid, row["summary"], row["actor"], row["run_id"],
            row["finding_id"] or "", row["kind"])).lower()
        rows.append(
            f'<div class="erow" data-cat="{dt._e(row["category"])}" '
            f'data-search="{dt._e(search)}">'
            f'<button type="button" class="ehead" aria-expanded="false">'
            f'<span class="eid mono">{dt._e(eid)}</span>'
            f'<span class="ets mono">{dt._e(dt._fmt_ts(row["ts"]) or "—")}'
            f'</span>'
            f'<span class="ekind">{dt._e(_KIND_LABEL.get(row["kind"], row["kind"]))}'
            f'{(" · " + dt._e(row["payload_kind"])) if row["payload_kind"] else ""}'
            f'</span>'
            f'<span class="eop"><a class="row-link mono" href="/operations/'
            f'{dt._e(row["run_id"])}">{dt._e(row["run_id"])}</a></span>'
            f'<span class="ereq mono">{dt._e(row["request_seq"] if row["request_seq"] is not None else "—")}</span>'
            f'<span class="efind">{finding}</span>'
            f'<span class="esrc">{dt._e(row["actor"])}</span>'
            f'<span class="esum">{dt._e(row["summary"])}{artifact}</span>'
            f'</button><div class="edet">{_detail(row)}</div></div>')
    return (
        f'<section class="panel"><h2>EVIDENCE RECORDS ({data["total"]})</h2>'
        '<div class="etable">'
        '<div class="erow-head"><span>EVIDENCE ID</span><span>TIME</span>'
        '<span>KIND / TYPE</span><span>OPERATION</span><span>REQ</span>'
        '<span>FINDING</span><span>SOURCE</span><span>SUMMARY</span></div>'
        f'<div id="evidence">{ "".join(rows) }</div></div>'
        '<p class="note">Rows expand in place to the full persisted record. '
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
            f' · <a class="row-link" '
            f'href="/operations/findings">findings</a></td></tr>')
    return ('<section class="panel"><h2>OPERATION CONTEXT</h2>'
            '<p class="note">Only resolvable run IDs are linked. The '
            'chain is OPERATION -> ACTION -> EVIDENCE -> FINDING -> '
            'VERIFICATION/FALSIFICATION -> GATE.</p>'
            '<table class="dense"><thead><tr><th>OPERATION</th>'
            '<th>MISSION</th><th>STATE</th><th>VIEWS</th></tr></thead>'
            f'<tbody>{ "".join(rows) }</tbody></table></section>')


def _nav() -> str:
    return ('<section class="panel"><h2>NAVIGATION</h2><div class="navgrid">'
            '<a class="navlink" href="/command">COMMAND CENTER</a>'
            '<a class="navlink" href="/operations">OPERATIONS</a>'
            '<a class="navlink" href="/operations/findings">'
            'FINDINGS INTELLIGENCE</a></div></section>')


_EXTRA_CSS = """
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
gap:8px;margin:6px 0 12px}
.metric{background:var(--panel2);border:1px solid var(--border);
border-radius:4px;padding:10px 12px;display:grid;gap:2px}
.metric .mv{font-size:22px;font-weight:700;letter-spacing:.04em;color:var(--text)}
.metric .ml{font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;
color:var(--muted)}
.metric.info .mv{color:var(--primary)}
.lifecycle{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
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
.etable{overflow-x:auto}
.erow{border-bottom:1px solid rgba(36,42,51,.6)}
.erow:last-child{border-bottom:none}
.erow-head{display:grid;
grid-template-columns:150px 84px 170px 190px 54px 160px 120px 1fr;
gap:8px;padding:6px 10px;color:var(--muted);font-size:10px;
letter-spacing:.06em;text-transform:uppercase;border-bottom:1px solid
var(--border);min-width:1100px}
.ehead{display:grid;
grid-template-columns:150px 84px 170px 190px 54px 160px 120px 1fr;
gap:8px;align-items:center;width:100%;text-align:left;background:none;
border:none;color:inherit;font:inherit;padding:6px 10px;cursor:pointer;
min-width:1100px}
.ehead > span{min-width:0;overflow:hidden;text-overflow:ellipsis;
white-space:nowrap}
.ehead:hover{background:var(--panel2)}
.eid{color:var(--primary);font-size:11px}
.ets,.ereq,.esrc{color:var(--muted);font-size:11px}
.ekind{color:var(--sec);font-size:10.5px;letter-spacing:.04em;
text-transform:uppercase}
.esum{color:var(--text);font-size:11.5px}
.art{color:var(--muted);font-size:10.5px}
.erow[data-cat="policy"] .ehead{border-left:2px solid rgba(91,127,224,.7)}
.erow[data-cat="verification"] .ehead{border-left:2px solid rgba(53,183,122,.7)}
.erow[data-cat="refutation"] .ehead{border-left:2px solid rgba(211,79,97,.7)}
.erow[data-cat="gate"] .ehead{border-left:2px solid rgba(215,160,68,.7)}
.edet{display:none;padding:10px 14px 14px 14px;background:var(--panel2)}
.erow.open .edet{display:block}
.rec{white-space:pre-wrap;word-break:break-word;color:var(--sec);
font-size:11px;background:var(--bg);border:1px solid var(--border);
border-radius:3px;padding:10px;max-height:420px;overflow:auto;margin:4px 0 0}
.muted{color:var(--muted)}
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
  var box = document.getElementById('evidence');
  var filter = 'all';
  function visible(row){
    if(filter !== 'all' && row.getAttribute('data-cat') !== filter) return false;
    if(search && search.value){
      var q = search.value.toLowerCase();
      if((row.getAttribute('data-search')||'').indexOf(q) < 0) return false;
    }
    return true;
  }
  function apply(){
    if(!box) return;
    var rows = box.querySelectorAll('.erow');
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
      var head = e.target.closest ? e.target.closest('.ehead') : null;
      if(head){ var r = head.parentNode; var o = r.classList.toggle('open');
        head.setAttribute('aria-expanded', o ? 'true' : 'false'); }
    });
  }
})();
"""


def render_evidence(*, runs_root, sessions_root) -> str:
    data = collect(runs_root=runs_root, sessions_root=sessions_root)
    body = (
        f'{_summary(data)}'
        f'{_filterbar()}'
        f'{_table(data)}'
        f'{_operations(data)}'
        f'{_nav()}'
        '<p class="readonly">READ-ONLY EVIDENCE VIEW · aggregated from '
        'harness.api.get_runs/get_run/get_evidence · append-only ledger '
        'records · no mutation, no execution, no new store</p>'
    )
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RAPHAEL — Evidence Intelligence</title>'
        f'<style>{dt._CSS}{_EXTRA_CSS}</style></head><body>'
        '<header class="cmdbar"><span class="brand">RAPHAEL</span>'
        '<span class="screen">Evidence Intelligence</span>'
        '<span class="banner">GOVERNED OPS // SCOPE-LOCKED</span>'
        '<span class="spacer"></span>'
        f'<span class="cmeta mono">{data["total"]} RECORDS</span>'
        f'<span class="cmeta mono">{data["evidence_total"]} EVIDENCE</span>'
        f'<span class="cmeta mono">{len(data["operations"])} OPERATIONS</span>'
        '<span class="led ok"></span></header>'
        f'<main>{body}</main>'
        '<footer class="policystrip mono">POLICY: FAIL-CLOSED · MODE: '
        'GOVERNED · GATE: QUALITY</footer>'
        f'<script>{_JS}</script>'
        "</body></html>")


__all__ = ["FILTERS", "collect", "render_evidence"]
