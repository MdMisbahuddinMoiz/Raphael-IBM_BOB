"""raphael_ibm_bob.http.views.event_stream_page — Event Stream screen.

The operator's chronological audit view of ONE operation.

    GET /operations/{run_id}/events   (text/html)

"What exactly happened during this operation, in chronological order?"

It is a presentation screen only. It renders the SAME authoritative
event projection the JSON API exposes (`harness.events.collect_events`
folded from the run's persisted ledger) and subscribes to the SAME
Server-Sent Events endpoint the Operations Console and Decision Trace
already use:

    GET /runs/{run_id}/events/stream

There is no second event store, no second event projection, and no
second streaming mechanism. The server renders the persisted history
with `event_stream.envelope` framing, and the client appends new
frames from the existing SSE stream using the identical envelope shape,
so the server (snapshot) and client (live) renderers agree.

Read-only: every data access goes through `harness.api`. The page
cannot execute, authorize, persist, or fabricate anything, and it
exposes no capability-execution controls.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from raphael_ibm_bob.harness import api
from raphael_ibm_bob.http.views import decision_trace as dt
from raphael_ibm_bob.http.views import event_stream as es

HTML = "text/html; charset=utf-8"

#: Filter categories -> actual event types emitted by harness.events.
#: No event category is invented: each chip filters the real projection.
#:   model          PLAN_CREATED + ACTION_REQUESTED (non-skill requester)
#:   specialist     ACTION_REQUESTED (requester starts "skill:")
#:   policy         POLICY_DECISION
#:   execution      EXECUTION_RESULT
#:   evidence       EVIDENCE_RECORDED
#:   finding        FINDING_CHANGED
#:   verification   VERIFICATION_RESULT
#:   falsification  FALSIFICATION_RESULT
#:   replan         REPLAN_CREATED
#:   gate           GATE_EVALUATED
#:   lifecycle      SESSION_CREATED / MISSION_STARTED / RUN_* terminal
FILTERS: Tuple[Tuple[str, str], ...] = (
    ("all", "ALL"),
    ("model", "MODEL"),
    ("specialist", "SPECIALIST"),
    ("policy", "BOB POLICY"),
    ("execution", "EXECUTION"),
    ("evidence", "EVIDENCE"),
    ("finding", "FINDING"),
    ("verification", "VERIFICATION"),
    ("falsification", "FALSIFICATION"),
    ("replan", "REPLAN"),
    ("gate", "GATE"),
    ("lifecycle", "LIFECYCLE"),
)

_TERMINAL_TYPES = ("RUN_COMPLETED", "RUN_REFUSED", "RUN_FAILED",
                   "RUN_CANCELLED")


# ---------------------------------------------------------------------------
# shared classification (mirrored client-side; ONE rule set)
# ---------------------------------------------------------------------------

def _classify(env: Dict[str, Any]) -> Dict[str, str]:
    """Map an event envelope to (category, actor, summary, status, kind)."""
    etype = env.get("type") or ""
    payload = env.get("payload") or {}
    get = payload.get

    if etype == "SESSION_CREATED":
        return {"cat": "lifecycle", "actor": "harness",
                "summary": f"session {get('session_id') or '—'}",
                "status": "", "kind": ""}
    if etype == "MISSION_STARTED":
        return {"cat": "lifecycle", "actor": "harness",
                "summary": f"mission {get('mission_id') or '—'}",
                "status": "", "kind": ""}
    if etype == "PLAN_CREATED":
        return {"cat": "model", "actor": "planner",
                "summary": f"plan {get('plan_id') or '—'}",
                "status": "PLAN", "kind": "info"}
    if etype == "ACTION_REQUESTED":
        requester = get("requester") or ""
        cat = "specialist" if requester.startswith("skill:") else "model"
        summary = f"{get('capability') or ''} {get('target') or ''}".strip()
        return {"cat": cat, "actor": requester or "—",
                "summary": summary or "action", "status": "REQ", "kind": ""}
    if etype == "POLICY_DECISION":
        decision = (get("decision") or "").upper()
        summary = get("reason") or f"request {get('request_seq')}"
        return {"cat": "policy", "actor": "BOB Policy", "summary": summary,
                "status": decision or "—",
                "kind": "ok" if decision == "ALLOW" else "crit"}
    if etype == "EXECUTION_RESULT":
        ok = bool(get("success"))
        return {"cat": "execution", "actor": "Runtime",
                "summary": get("artifact_ref") or
                           f"request {get('request_seq')}",
                "status": "SUCCESS" if ok else "FAILED",
                "kind": "ok" if ok else "crit"}
    if etype == "EVIDENCE_RECORDED":
        return {"cat": "evidence", "actor": get("producer") or "evidence",
                "summary": get("evidence_id") or "",
                "status": "EVIDENCE", "kind": ""}
    if etype == "FINDING_CHANGED":
        state = (get("state") or "").upper()
        return {"cat": "finding", "actor": "finding",
                "summary": (f"{get('finding_id') or ''} "
                            f"{get('prev_state') or ''}→"
                            f"{get('state') or ''}"),
                "status": state, "kind": ""}
    if etype == "VERIFICATION_RESULT":
        return {"cat": "verification", "actor": "verifier",
                "summary": get("finding_id") or "",
                "status": (get("kind") or "VERIFIED").upper(), "kind": "ok"}
    if etype == "FALSIFICATION_RESULT":
        refuted = get("kind") == "counter-example"
        return {"cat": "falsification", "actor": "falsifier",
                "summary": get("finding_id") or "",
                "status": "REFUTED" if refuted else "PASS",
                "kind": "crit" if refuted else "ok"}
    if etype == "REPLAN_CREATED":
        return {"cat": "replan", "actor": "replanner",
                "summary": (f"{get('parent_plan_id') or ''} → "
                            f"{get('plan_b_id') or ''}"),
                "status": "REPLAN", "kind": "warn"}
    if etype == "GATE_EVALUATED":
        decision = (get("decision") or "").upper()
        return {"cat": "gate", "actor": "Quality Gate",
                "summary": f"{len(get('checks') or [])} checks",
                "status": decision or "—",
                "kind": "ok" if decision == "COMPLETE" else "crit"}
    if etype in _TERMINAL_TYPES:
        return {"cat": "lifecycle", "actor": "harness", "summary": "",
                "status": etype.replace("RUN_", ""),
                "kind": "ok" if etype == "RUN_COMPLETED" else "crit"}
    return {"cat": "lifecycle", "actor": "harness", "summary": etype,
            "status": "", "kind": ""}


def _time_of(timestamp: Any) -> str:
    if not timestamp:
        return "—"
    text = str(timestamp)
    if "T" in text and len(text) >= 19:
        return text.split("T", 1)[1][:8]
    return text


def _val(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _details(env: Dict[str, Any]) -> str:
    payload = env.get("payload") or {}
    pairs: List[Tuple[str, Any]] = [
        ("SEQUENCE", env.get("sequence")),
        ("RUN", env.get("run_id")),
        ("TIMESTAMP", env.get("timestamp") or "—"),
        ("TYPE", env.get("type")),
    ]
    pairs.extend((key.upper(), payload[key]) for key in sorted(payload))
    rows = "".join(
        f'<div class="kv"><span class="k">{dt._e(k)}</span>'
        f'<span class="v mono">{dt._e(_val(v))}</span></div>'
        for k, v in pairs)
    return f'<div class="kvlist">{rows}</div>'


def _row(env: Dict[str, Any]) -> str:
    c = _classify(env)
    try:
        seq = int(env.get("sequence") or 0)
    except (TypeError, ValueError):
        seq = 0
    payload_json = json.dumps(env, sort_keys=True)
    return (
        f'<div class="evrow" data-cat="{dt._e(c["cat"])}" data-seq="{seq}">'
        f'<button type="button" class="evhead" aria-expanded="false" '
        f'data-env="{dt._e(payload_json)}">'
        f'<span class="seq mono">{seq:02d}</span>'
        f'<span class="ts mono">{dt._e(_time_of(env.get("timestamp")))}</span>'
        f'<span class="type">{dt._e(env.get("type"))}</span>'
        f'<span class="actor">{dt._e(c["actor"])}</span>'
        f'<span class="sum">{dt._e(c["summary"])}</span>'
        f'<span class="st {c["kind"]}">{dt._e(c["status"])}</span>'
        '</button>'
        f'<div class="det">{_details(env)}</div>'
        '</div>')


# ---------------------------------------------------------------------------
# panels
# ---------------------------------------------------------------------------

def _envelopes(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    ts_by_seq = {r.get("seq"): r.get("ts") for r in data["records"]}
    return [es.envelope(i, event, data["run_id"], ts_by_seq)
            for i, event in enumerate(data["events"], start=1)]


def _statusbar(terminal: bool) -> str:
    return (
        '<div class="statusbar">'
        '<span class="dot" id="conn-dot"></span>'
        '<span id="conn-text">CONNECTING…</span>'
        '<span class="spacer"></span>'
        '<span class="mono" id="stat-count">events: 0</span>'
        '<span class="mono" id="stat-last">last sequence: —</span>'
        '<span class="mono" id="stat-activity">last activity: —</span>'
        '</div>'
        + ('<div class="terminal-banner" id="terminal-banner">'
           'TERMINAL STATE REACHED</div>' if terminal else
           '<div class="terminal-banner hidden" id="terminal-banner"></div>'))


def _filterbar() -> str:
    chips = "".join(
        f'<button type="button" class="chip{" active" if key == "all" else ""}" '
        f'data-filter="{dt._e(key)}">{dt._e(label)}</button>'
        for key, label in FILTERS)
    return (
        '<section class="panel"><h2>FILTER &amp; SEARCH</h2>'
        '<div class="filterbar">'
        f'<div class="chips">{chips}</div>'
        '<input id="search" class="search" type="search" '
        'placeholder="search visible events…" aria-label="search events">'
        '<label class="follow"><input type="checkbox" id="follow" checked> '
        'FOLLOW LIVE</label>'
        '<button type="button" class="btn" id="newpill" hidden>'
        'NEW EVENTS ↓</button>'
        '</div></section>')


def _inspector(data: Dict[str, Any]) -> str:
    last_skill = "—"
    for record in data["requests"]:
        requester = record.get("requester") or ""
        if requester.startswith("skill:"):
            last_skill = requester.split("skill:", 1)[1]
    skill = data["skills"].get(last_skill)
    role = getattr(skill, "role", None) or "—"
    task, task_state = dt._active_task(data["tasks"])
    phase = "—"
    for label, status in dt._pipeline(data):
        if status in ("active", "refused"):
            phase = label
    gate = data["gate"] or {}
    gate_state = (gate.get("decision") or "in-progress").upper()
    pairs = [
        ("CURRENT SPECIALIST", role),
        ("CURRENT SKILL", last_skill),
        ("CURRENT TASK", (task or {}).get("name") or "—"),
        ("TASK STATE", task_state or "—"),
        ("CURRENT PHASE", phase),
        ("EVIDENCE COUNT", len(data["evidence"])),
        ("FINDING COUNT", len(data["findings"])),
        ("GATE STATE", gate_state),
    ]
    rows = "".join(
        f'<div class="kv"><span class="k">{dt._e(k)}</span>'
        f'<span class="v mono">{dt._e(v)}</span></div>' for k, v in pairs)
    return ('<section class="panel"><h2>RUN INSPECTOR</h2>'
            f'<div class="kvlist">{rows}</div>'
            '<p class="note">Authoritative persisted state via '
            'harness.api. No client-only authority.</p></section>')


def _legend() -> str:
    return (
        '<section class="panel"><h2>LEGEND</h2><div class="legend-grid">'
        '<span class="lg model">MODEL</span>'
        '<span class="lg specialist">SPECIALIST</span>'
        '<span class="lg policy">BOB POLICY</span>'
        '<span class="lg execution">EXECUTION</span>'
        '<span class="lg evidence">EVIDENCE</span>'
        '<span class="lg finding">FINDING</span>'
        '<span class="lg verification">VERIFICATION</span>'
        '<span class="lg falsification">FALSIFICATION</span>'
        '<span class="lg replan">REPLAN</span>'
        '<span class="lg gate">GATE</span>'
        '<span class="lg lifecycle">LIFECYCLE</span>'
        '</div><p class="note">Policy ALLOW/DENY and the recorded reason '
        'come from the persisted decision record; DENY reasons are never '
        'fabricated.</p></section>')


_EXTRA_CSS = """
.statusbar{display:flex;align-items:center;gap:12px;font-size:11px;
color:var(--sec);margin:8px 0}
.dot{width:8px;height:8px;border-radius:50%;background:var(--muted)}
.dot.live{background:var(--ok);box-shadow:0 0 6px var(--ok)}
.dot.down{background:var(--crit)}
.terminal-banner{margin:6px 0;padding:8px 12px;border-radius:3px;
border:1px solid rgba(211,79,97,.5);color:var(--crit);font-size:12px;
letter-spacing:.08em;text-transform:uppercase;background:rgba(211,79,97,.08)}
.terminal-banner.hidden{display:none}
.terminal-banner.done{border-color:rgba(53,183,122,.5);color:var(--ok);
background:rgba(53,183,122,.08)}
.filterbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{font:inherit;font-size:10.5px;letter-spacing:.06em;
text-transform:uppercase;background:var(--panel2);color:var(--sec);
border:1px solid var(--border);border-radius:10px;padding:4px 10px;
cursor:pointer}
.chip:hover{border-color:var(--primary)}
.chip.active{color:var(--text);border-color:var(--primary);
background:rgba(91,127,224,.12)}
.search{font:inherit;font-size:11.5px;background:var(--bg);color:var(--text);
border:1px solid var(--border);border-radius:3px;padding:6px 9px;min-width:200px}
.follow{display:flex;align-items:center;gap:6px;font-size:10.5px;
letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.btn{font:inherit;font-size:10.5px;letter-spacing:.06em;
text-transform:uppercase;background:var(--panel2);color:var(--text);
border:1px solid var(--border);border-radius:3px;padding:5px 10px;
cursor:pointer}
.btn:hover{border-color:var(--primary)}
.btn.crit{border-color:rgba(211,79,97,.5);color:var(--crit)}
#events{max-height:620px;overflow:auto;border:1px solid var(--border);
border-radius:4px}
.evrow{border-bottom:1px solid rgba(36,42,51,.6)}
.evrow:last-child{border-bottom:none}
.evhead{display:grid;grid-template-columns:40px 74px 170px 150px 1fr auto;
gap:8px;align-items:center;width:100%;text-align:left;background:none;
border:none;color:inherit;font:inherit;padding:6px 10px;cursor:pointer}
.evhead:hover{background:var(--panel2)}
.evhead .seq{color:var(--muted);font-size:11px}
.evhead .ts{color:var(--muted);font-size:11px}
.evhead .type{font-size:10.5px;letter-spacing:.05em;color:var(--sec);
text-transform:uppercase}
.evhead .actor{font-size:11px;color:var(--primary);word-break:break-word}
.evhead .sum{font-size:11.5px;color:var(--text);word-break:break-word}
.evhead .st{font-size:10px;padding:1px 7px;border-radius:10px;
border:1px solid var(--border);color:var(--sec)}
.evhead .st.ok{color:var(--ok);border-color:rgba(53,183,122,.5)}
.evhead .st.crit{color:var(--crit);border-color:rgba(211,79,97,.5)}
.evhead .st.warn{color:var(--warn);border-color:rgba(215,160,68,.5)}
.evhead .st.info{color:var(--primary);border-color:rgba(91,127,224,.5)}
.det{display:none;padding:8px 14px 12px 54px;background:var(--panel2)}
.evrow.open .det{display:block}
.evrow[data-cat="model"] .evhead .actor{color:var(--primary)}
.evrow[data-cat="specialist"] .evhead .actor{color:var(--ok)}
.evrow[data-cat="policy"] .evhead{border-left:2px solid rgba(91,127,224,.7)}
.evrow[data-cat="gate"] .evhead{border-left:2px solid rgba(215,160,68,.7)}
.evrow[data-cat="falsification"] .evhead{border-left:2px solid rgba(211,79,97,.7)}
.legend-grid{display:flex;gap:8px;flex-wrap:wrap}
.lg{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;
border:1px solid var(--border);border-radius:10px;padding:3px 9px;
color:var(--sec)}
.lg.model,.lg.specialist{color:var(--primary)}
.lg.gate{color:var(--warn)}
.lg.falsification{color:var(--crit)}
.lg.policy{color:var(--ok)}
"""


_JS = r"""
(function(){
  var cfg = window.RAPHAEL || {};
  var runId = cfg.runId, terminal = !!cfg.terminal;
  var box = document.getElementById('events');
  var dot = document.getElementById('conn-dot');
  var ctext = document.getElementById('conn-text');
  var statCount = document.getElementById('stat-count');
  var statLast = document.getElementById('stat-last');
  var statActivity = document.getElementById('stat-activity');
  var banner = document.getElementById('terminal-banner');
  var search = document.getElementById('search');
  var follow = document.getElementById('follow');
  var newpill = document.getElementById('newpill');
  var chips = Array.prototype.slice.call(
      document.querySelectorAll('.chip'));
  var filter = 'all';
  var total = 0, lastSeq = 0;

  function pad(n){ n = Number(n)||0; return (n<10?'0':'')+n; }
  function timeOf(ts){
    if(!ts) return '\u2014';
    var s = String(ts);
    if(s.indexOf('T') >= 0 && s.length >= 19){ return s.split('T')[1].substr(0,8); }
    return s;
  }
  function classify(env){
    var t = env.type || '', p = env.payload || {};
    function g(k){ return p[k]; }
    if(t==='SESSION_CREATED') return {cat:'lifecycle',actor:'harness',summary:'session '+(g('session_id')||'\u2014'),status:'',kind:''};
    if(t==='MISSION_STARTED') return {cat:'lifecycle',actor:'harness',summary:'mission '+(g('mission_id')||'\u2014'),status:'',kind:''};
    if(t==='PLAN_CREATED') return {cat:'model',actor:'planner',summary:'plan '+(g('plan_id')||'\u2014'),status:'PLAN',kind:'info'};
    if(t==='ACTION_REQUESTED'){
      var rq=g('requester')||'';
      return {cat:(rq.indexOf('skill:')===0?'specialist':'model'),actor:(rq||'\u2014'),
              summary:((g('capability')||'')+' '+(g('target')||'')).replace(/\s+$/,''),
              status:'REQ',kind:''};
    }
    if(t==='POLICY_DECISION'){
      var d=(g('decision')||'').toUpperCase();
      return {cat:'policy',actor:'BOB Policy',summary:(g('reason')||('request '+g('request_seq'))),
              status:(d||'\u2014'),kind:(d==='ALLOW'?'ok':'crit')};
    }
    if(t==='EXECUTION_RESULT'){
      var ok=!!g('success');
      return {cat:'execution',actor:'Runtime',summary:(g('artifact_ref')||('request '+g('request_seq'))),
              status:(ok?'SUCCESS':'FAILED'),kind:(ok?'ok':'crit')};
    }
    if(t==='EVIDENCE_RECORDED') return {cat:'evidence',actor:(g('producer')||'evidence'),summary:(g('evidence_id')||''),status:'EVIDENCE',kind:''};
    if(t==='FINDING_CHANGED') return {cat:'finding',actor:'finding',
      summary:((g('finding_id')||'')+' '+(g('prev_state')||'')+'\u2192'+(g('state')||'')),
      status:((g('state')||'').toUpperCase()),kind:''};
    if(t==='VERIFICATION_RESULT') return {cat:'verification',actor:'verifier',summary:(g('finding_id')||''),status:((g('kind')||'VERIFIED').toUpperCase()),kind:'ok'};
    if(t==='FALSIFICATION_RESULT'){
      var ref=(g('kind')==='counter-example');
      return {cat:'falsification',actor:'falsifier',summary:(g('finding_id')||''),
              status:(ref?'REFUTED':'PASS'),kind:(ref?'crit':'ok')};
    }
    if(t==='REPLAN_CREATED') return {cat:'replan',actor:'replanner',
      summary:((g('parent_plan_id')||'')+' \u2192 '+(g('plan_b_id')||'')),status:'REPLAN',kind:'warn'};
    if(t==='GATE_EVALUATED'){
      var gd=(g('decision')||'').toUpperCase();
      return {cat:'gate',actor:'Quality Gate',summary:((g('checks')||[]).length+' checks'),
              status:(gd||'\u2014'),kind:(gd==='COMPLETE'?'ok':'crit')};
    }
    if(t==='RUN_COMPLETED'||t==='RUN_REFUSED'||t==='RUN_FAILED'||t==='RUN_CANCELLED'){
      return {cat:'lifecycle',actor:'harness',summary:'',status:t.replace('RUN_',''),
              kind:(t==='RUN_COMPLETED'?'ok':'crit')};
    }
    return {cat:'lifecycle',actor:'harness',summary:t,status:'',kind:''};
  }
  function details(env){
    var p = env.payload || {}, keys = Object.keys(p).sort();
    var pairs = [['SEQUENCE',env.sequence],['RUN',env.run_id],
                 ['TIMESTAMP',env.timestamp||'\u2014'],['TYPE',env.type]];
    for(var i=0;i<keys.length;i++){ pairs.push([keys[i].toUpperCase(),p[keys[i]]]); }
    var d = document.createElement('div'); d.className='kvlist';
    for(var j=0;j<pairs.length;j++){
      var row = document.createElement('div'); row.className='kv';
      var k = document.createElement('span'); k.className='k'; k.textContent=pairs[j][0];
      var v = document.createElement('span'); v.className='v mono';
      var val = pairs[j][1];
      v.textContent = (val && typeof val==='object')?JSON.stringify(val):String(val==null?'':val);
      row.appendChild(k); row.appendChild(v); d.appendChild(row);
    }
    return d;
  }
  function rowEl(env){
    var c = classify(env);
    var row = document.createElement('div');
    row.className='evrow'; row.setAttribute('data-cat',c.cat);
    row.setAttribute('data-seq',String(env.sequence));
    var btn = document.createElement('button');
    btn.type='button'; btn.className='evhead'; btn.setAttribute('aria-expanded','false');
    function span(cls,txt){ var s=document.createElement('span'); s.className=cls; s.textContent=txt; return s; }
    btn.appendChild(span('seq mono',pad(env.sequence)));
    btn.appendChild(span('ts mono',timeOf(env.timestamp)));
    btn.appendChild(span('type',env.type||''));
    btn.appendChild(span('actor',c.actor));
    btn.appendChild(span('sum',c.summary));
    btn.appendChild(span('st '+c.kind,c.status));
    var det=document.createElement('div'); det.className='det';
    det.appendChild(details(env));
    row.appendChild(btn); row.appendChild(det);
    btn.addEventListener('click',function(){
      var open=row.classList.toggle('open');
      btn.setAttribute('aria-expanded',open?'true':'false');
    });
    return row;
  }
  function visible(row){
    if(filter!=='all' && row.getAttribute('data-cat')!==filter) return false;
    if(search && search.value){
      var q=search.value.toLowerCase();
      if(row.textContent.toLowerCase().indexOf(q)<0) return false;
    }
    return true;
  }
  function applyFilter(){
    var rows=box.querySelectorAll('.evrow'), n=0;
    for(var i=0;i<rows.length;i++){
      var v=visible(rows[i]); rows[i].style.display=v?'':'none'; if(v) n++;
    }
    return n;
  }
  function atBottom(){ return box.scrollHeight - box.scrollTop - box.clientHeight < 40; }
  function scrollBottom(){ box.scrollTop = box.scrollHeight; }
  function setTerminal(label, done){
    if(!banner) return;
    banner.textContent = label;
    banner.className = 'terminal-banner'+(done?' done':'');
  }
  function append(env){
    if(env.sequence <= lastSeq) return;
    lastSeq = env.sequence; total++;
    var row = rowEl(env); box.appendChild(row);
    if(search && search.value){ row.style.display = visible(row)?'':'none'; }
    if(statCount) statCount.textContent = 'events: '+total;
    if(statLast) statLast.textContent = 'last sequence: '+lastSeq;
    if(statActivity) statActivity.textContent = 'last activity: '+timeOf(env.timestamp);
    if(follow && follow.checked && atBottom()){ scrollBottom(); }
    else if(newpill){ newpill.hidden = false; }
    if(env.type==='RUN_COMPLETED'){ setTerminal('RUN COMPLETED', true); }
    else if(env.type==='RUN_REFUSED'){ setTerminal('RUN REFUSED', false); }
    else if(env.type==='RUN_FAILED'){ setTerminal('RUN FAILED', false); }
    else if(env.type==='RUN_CANCELLED'){ setTerminal('RUN CANCELLED', false); }
  }

  var rows0 = box.querySelectorAll('.evrow');
  total = rows0.length;
  lastSeq = 0;
  for(var i=0;i<rows0.length;i++){
    var s=parseInt(rows0[i].getAttribute('data-seq'),10);
    if(s>lastSeq) lastSeq=s;
  }
  if(statCount) statCount.textContent = 'events: '+total;
  if(statLast) statLast.textContent = 'last sequence: '+(lastSeq||'\u2014');

  for(var i=0;i<chips.length;i++){
    (function(chip){ chip.addEventListener('click',function(){
      filter = chip.getAttribute('data-filter');
      for(var j=0;j<chips.length;j++){ chips[j].classList.remove('active'); }
      chip.classList.add('active'); applyFilter();
    }); })(chips[i]);
  }
  if(search){ search.addEventListener('input', applyFilter); }
  if(newpill){ newpill.addEventListener('click',function(){ scrollBottom(); newpill.hidden=true; }); }
  box.addEventListener('click',function(e){
    var head=e.target.closest ? e.target.closest('.evhead') : null;
    if(head){ var r=head.parentNode; var o=r.classList.toggle('open');
      head.setAttribute('aria-expanded',o?'true':'false'); }
  });
  box.addEventListener('scroll',function(){ if(atBottom() && newpill) newpill.hidden=true; });

  if(terminal && banner){ setTerminal('RUN TERMINAL', true); }
  if(terminal){ if(dot) dot.className='dot'; if(ctext) ctext.textContent='TERMINAL — SNAPSHOT'; return; }
  if(typeof EventSource === 'undefined'){ if(ctext) ctext.textContent='NO STREAM SUPPORT'; return; }
  var sseUrl = cfg.sseUrl || ('/runs/'+encodeURIComponent(runId)+'/events/stream');
  var es = new EventSource(sseUrl);
  es.addEventListener('RAPHAEL_EVENT', function(e){
    if(dot) dot.className='dot live';
    if(ctext) ctext.textContent='CONNECTED';
    var env; try{ env=JSON.parse(e.data); }catch(err){ return; }
    append(env);
  });
  es.addEventListener('stream_end', function(e){
    if(dot) dot.className='dot'; if(ctext) ctext.textContent='STREAM CLOSED';
    newpill && (newpill.hidden = true);
    try{ var d=JSON.parse(e.data); if(d && d.state && d.state!=='stream-timeout'){ setTerminal('RUN '+String(d.state).toUpperCase(), d.state==='completed'); } }catch(err){}
    es.close();
  });
  es.addEventListener('stream_error', function(){
    if(dot) dot.className='dot down'; if(ctext) ctext.textContent='STREAM ERROR';
  });
  es.onerror = function(){
    if(dot) dot.className='dot down';
    if(ctext) ctext.textContent='RECONNECTING…';
  };
})();
"""


def render_event_stream(run_id: str, *, runs_root, sessions_root) -> str:
    """Return the full HTML page for a run's Event Stream."""
    data = dt.collect(run_id, runs_root=runs_root,
                      sessions_root=sessions_root)
    run = data["run"]
    envelopes = _envelopes(data)
    rows = "".join(_row(env) for env in envelopes) or (
        '<p class="empty">No events recorded.</p>')
    cfg = json.dumps({"runId": run_id, "terminal": run.is_terminal(),
                      "sseUrl": f"/runs/{run_id}/events/stream"},
                     sort_keys=True)
    title = f"RAPHAEL — Event Stream — {run_id}"
    body = (
        f'{dt._header(data)}'
        f'{dt._pipeline_html(data)}'
        f'{_statusbar(run.is_terminal())}'
        f'{_filterbar()}'
        '<div class="grid2">'
        '<section class="panel"><h2>EVENT STREAM</h2>'
        f'<div id="events">{rows}</div></section>'
        f'{_inspector(data)}'
        '</div>'
        f'{dt._control_plane(data)}'
        '<section class="panel gate"><h2>QUALITY GATE</h2>'
        f'<div class="gate-final">{dt._e(((data["gate"] or {}).get("decision") or "in-progress").upper())}</div>'
        f'{dt._stage_gate(data)["html"]}</section>'
        f'{_legend()}'
        '<p class="readonly">READ-ONLY AUDIT VIEW · events projected from '
        'the persisted ledger · SSE via /runs/{run_id}/events/stream · '
        'no execution controls</p>'
    )
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{dt._e(title)}</title>"
        f"<style>{dt._CSS}{_EXTRA_CSS}</style></head><body>"
        '<header class="cmdbar"><span class="brand">RAPHAEL</span>'
        '<span class="screen">Event Stream</span>'
        '<span class="banner">GOVERNED OPS // SCOPE-LOCKED</span>'
        '<span class="spacer"></span>'
        f'<span class="cmeta mono">{dt._e(getattr(data["session"], "model", None) or "MODEL N/A")}</span>'
        f'<span class="cmeta mono">{dt._e(getattr(data["session"], "provider", None) or "PROVIDER N/A")}</span>'
        '<span class="led ok"></span></header>'
        f'<main>{body}</main>'
        '<footer class="policystrip mono">POLICY: FAIL-CLOSED · MODE: '
        'GOVERNED · GATE: QUALITY</footer>'
        '<script>window.RAPHAEL=' + cfg + ';</script>'
        f'<script>{_JS}</script>'
        "</body></html>")


__all__ = ["FILTERS", "HTML", "render_event_stream"]
