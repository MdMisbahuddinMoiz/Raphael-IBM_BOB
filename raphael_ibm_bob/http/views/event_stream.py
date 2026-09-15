"""raphael_ibm_bob.http.views.event_stream — Server-Sent Events over
the existing Harness event projection.

Read-only transport. There is no second event store: every frame is a
projection of the SAME persisted ledger the JSON API exposes, folded by
`harness.events.collect_events`. This module cannot execute, authorize,
or persist anything.

Frames are deterministic and ordered by the projection's event index,
which is used as the SSE `id:` (a cursor). `Last-Event-ID` / `?after=`
resume from a cursor. The stream closes after the run's terminal event.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterator, Optional

from raphael_ibm_bob.harness import api

SSE_EVENT = "RAPHAEL_EVENT"
STREAM_END = "stream_end"
STREAM_ERROR = "stream_error"

#: Bounded defaults (correctness over cleverness; documented).
DEFAULT_POLL_SECONDS = 0.25
DEFAULT_HEARTBEAT_SECONDS = 10.0
DEFAULT_MAX_SECONDS = 300.0


def _fmt_ts(ts: Any) -> Optional[str]:
    try:
        n = int(ts)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n > 10 ** 17:
        seconds = n / 1_000_000_000
    elif n > 10 ** 11:
        seconds = n / 1_000
    else:
        seconds = n
    try:
        return datetime.fromtimestamp(
            seconds, tz=timezone.utc).isoformat(timespec="milliseconds")
    except (OverflowError, OSError, ValueError):
        return None


def envelope(index: int, event: Dict[str, Any], run_id: str,
             ts_by_seq: Dict[Any, Any]) -> Dict[str, Any]:
    """Stable JSON envelope for one projected event."""
    payload = {k: v for k, v in event.items()
               if k not in ("seq", "type", "run_id")}
    return {
        "sequence": index,
        "type": event.get("type"),
        "run_id": run_id,
        "timestamp": _fmt_ts(ts_by_seq.get(event.get("seq"))),
        "payload": payload,
    }


def event_frame(index: int, event: Dict[str, Any], run_id: str,
                ts_by_seq: Dict[Any, Any]) -> bytes:
    data = json.dumps(envelope(index, event, run_id, ts_by_seq),
                      sort_keys=True)
    return (f"event: {SSE_EVENT}\nid: {index}\ndata: {data}\n\n"
            ).encode("utf-8")


def end_frame(run_id: str, state: str, last: int) -> bytes:
    data = json.dumps({"run_id": run_id, "state": state,
                       "last_sequence": last}, sort_keys=True)
    return f"event: {STREAM_END}\ndata: {data}\n\n".encode("utf-8")


def error_frame(code: str, message: str) -> bytes:
    data = json.dumps({"code": code, "message": message}, sort_keys=True)
    return f"event: {STREAM_ERROR}\ndata: {data}\n\n".encode("utf-8")


#: Single client-side renderer shared by the live console and the
#: Decision Trace page. It consumes only the SSE envelope above and
#: updates whichever elements exist (others are skipped). It never
#: invents state and never executes anything.
LIVE_JS = r"""
(function(){
  var cfg = window.RAPHAEL || {};
  var runId = cfg.runId, skillRole = cfg.skillRole || {};
  var log = document.getElementById('stream-log');
  var dot = document.getElementById('conn-dot');
  var ctext = document.getElementById('conn-text');
  var clast = document.getElementById('conn-last');
  var evcount = document.querySelector('[data-evidence-count]');
  var order = ['INVESTIGATE','REPRODUCE','REMEDIATE','VERIFY','FALSIFY',
               'INDEPENDENT PROBE','QUALITY GATE'];
  var phase = {};
  function setPhase(name, cls){
    var el = document.querySelector('.phase[data-phase="'+name+'"]');
    if(!el) return;
    el.classList.remove('complete','active','refused','attention','pending');
    el.classList.add(cls);
    var m = el.querySelector('.pmark');
    if(m) m.textContent = (cls==='complete'?'\u2713':cls==='active'?'\u25CF':
                           cls==='refused'?'\u2715':cls==='attention'?'!':'\u25CB');
  }
  function advanceTo(name){
    for(var i=0;i<order.length;i++){
      if(order[i]===name){
        for(var j=0;j<i;j++){ if(phase[order[j]]!=='complete'){
          phase[order[j]]='complete'; setPhase(order[j],'complete'); } }
        phase[name]='active'; setPhase(name,'active'); return;
      }
    }
  }
  function complete(name){ phase[name]='complete'; setPhase(name,'complete'); }
  function setText(el,t){ if(el) el.textContent = String(t==null?'':t); }
  function row(actor, what, status, cls){
    if(!log) return;
    var d = document.createElement('div'); d.className='logline';
    var t = new Date().toISOString().substr(11,8);
    d.innerHTML = '<span class="at mono">'+t+'</span>'+
      '<span class="actor"></span><span class="what"></span>'+
      '<span class="st '+(cls||'')+'"></span>';
    d.querySelector('.actor').textContent = actor==null?'':String(actor);
    d.querySelector('.what').textContent = what==null?'':String(what);
    d.querySelector('.st').textContent = status==null?'':String(status);
    log.appendChild(d); log.scrollTop = log.scrollHeight;
  }
  function specActive(requester){
    if(String(requester||'').indexOf('skill:')!==0) return;
    var skill = requester.split('skill:')[1];
    var role = skillRole[skill]; if(!role) return;
    var el = document.querySelector('.spec .row[data-role="'+role+'"]');
    if(!el) return;
    el.classList.remove('ready'); el.classList.add('active');
    var st = el.querySelector('[data-role-state]');
    if(st) st.textContent='ACTIVE';
  }
  function apply(env){
    var p = env.payload || {}, ty = env.type;
    if(ty==='ACTION_REQUESTED'){
      var cap = p.capability || '';
      if(cap==='read'||cap==='list'||cap==='search') advanceTo('INVESTIGATE');
      if(cap==='run_test') advanceTo('REPRODUCE');
      if(cap==='write') advanceTo('REMEDIATE');
      specActive(p.requester);
      row(p.requester, cap+' '+(p.target||''), 'REQ', '');
    } else if(ty==='POLICY_DECISION'){
      var dec = (p.decision||'').toUpperCase();
      row('BOB POLICY', (p.request_seq?'req '+p.request_seq:''), dec,
          dec==='ALLOW'?'ok':'crit');
    } else if(ty==='EXECUTION_RESULT'){
      row('BOB RUNTIME', 'execution', p.success?'SUCCESS':'FAILED',
          p.success?'ok':'crit');
    } else if(ty==='EVIDENCE_RECORDED'){
      if(evcount){ evcount.textContent = (parseInt(evcount.textContent,10)||0)+1; }
      row(p.producer||'evidence', p.evidence_id||'', 'EVIDENCE', '');
    } else if(ty==='VERIFICATION_RESULT'){
      complete('VERIFY'); row('VERIFIER', p.finding_id||'', 'VERIFIED','ok');
    } else if(ty==='FALSIFICATION_RESULT'){
      complete('FALSIFY');
      row('FALSIFIER', p.finding_id||'',
          (p.kind==='counter-example'?'REFUTED':'PASS'),
          p.kind==='counter-example'?'crit':'ok');
    } else if(ty==='REPLAN_CREATED'){
      row('REPLANNER', p.plan_b_id||'', 'REPLAN', 'warn');
    } else if(ty==='FINDING_CHANGED'){
      row('FINDING', (p.finding_id||'')+' '+String(p.prev_state||'')+
          '\u2192'+String(p.state||''), '', '');
    } else if(ty==='GATE_EVALUATED'){
      complete('QUALITY GATE');
      var gp = document.getElementById('gate-panel');
      var g = gp && gp.querySelector('.gate-final');
      if(g) g.textContent = (p.decision||'').toUpperCase();
      row('QUALITY GATE', (p.checks||[]).length+' checks',
          (p.decision||'').toUpperCase(), p.decision==='complete'?'ok':'crit');
    } else if(ty==='RUN_COMPLETED'||ty==='RUN_REFUSED'||ty==='RUN_FAILED'||
              ty==='RUN_CANCELLED'){
      setText(ctext, 'TERMINAL: '+ty);
    }
    setText(clast, 'last event: '+env.sequence);
  }
  if(cfg.terminal){ complete('QUALITY GATE'); return; }
  if(typeof EventSource === 'undefined'){ setText(ctext,'NO STREAM SUPPORT'); return; }
  var es = new EventSource('/runs/'+encodeURIComponent(runId)+'/events/stream');
  es.addEventListener('RAPHAEL_EVENT', function(e){
    if(dot) dot.className='dot live';
    setText(ctext, 'LIVE');
    try { apply(JSON.parse(e.data)); } catch(err){}
  });
  es.addEventListener('stream_end', function(){
    if(dot) dot.className='dot'; setText(ctext,'STREAM CLOSED'); es.close();
  });
  es.addEventListener('stream_error', function(){
    if(dot) dot.className='dot down'; setText(ctext,'STREAM ERROR');
  });
  es.onerror = function(){
    if(dot) dot.className='dot down';
    setText(ctext,'CONNECTION LOST — reconnecting…');
  };
})();
"""


def iter_frames(run_id: str, *, runs_root,
                after: int = 0,
                poll_seconds: float = DEFAULT_POLL_SECONDS,
                heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
                max_seconds: float = DEFAULT_MAX_SECONDS,
                clock: Callable[[], float] = time.monotonic,
                sleep: Callable[[float], None] = time.sleep
                ) -> Iterator[bytes]:
    """Yield SSE frames for a run until terminal, timeout, or stop.

    Deterministic ordering; resumable via `after` (last seen cursor).
    Bounded by `max_seconds`; a heartbeat keeps idle connections alive.
    """
    started = clock()
    last_beat = started
    sent = max(0, int(after or 0))
    yield b"retry: 3000\n\n"
    while clock() - started < max_seconds:
        try:
            records = api.get_evidence(run_id, runs_root)
            events = api.get_events(run_id, runs_root)
            run = api.get_run(run_id, runs_root)
        except FileNotFoundError:
            yield error_frame("RUN_NOT_FOUND", "run not found")
            return
        ts_by_seq = {r.get("seq"): r.get("ts") for r in records}
        total = len(events)
        for index in range(sent + 1, total + 1):
            yield event_frame(index, events[index - 1], run_id, ts_by_seq)
        if total > sent:
            sent = total
        if run.is_terminal() and sent >= total:
            yield end_frame(run_id, run.state, sent)
            return
        if clock() - last_beat >= heartbeat_seconds:
            yield b": ping\n\n"
            last_beat = clock()
        sleep(poll_seconds)
    yield end_frame(run_id, "stream-timeout", sent)


__all__ = [
    "DEFAULT_HEARTBEAT_SECONDS",
    "DEFAULT_MAX_SECONDS",
    "DEFAULT_POLL_SECONDS",
    "LIVE_JS",
    "SSE_EVENT",
    "STREAM_END",
    "STREAM_ERROR",
    "end_frame",
    "envelope",
    "error_frame",
    "event_frame",
    "iter_frames",
]
