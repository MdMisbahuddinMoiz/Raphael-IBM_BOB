"""raphael_ibm_bob.http.views.operations_console — live operator console.

Server-rendered shell (reusing the Decision Trace data model and CSS)
plus a small vanilla-JS EventSource client. The page ORCHESTRATES
through the existing HTTP/Harness API; it holds no execution authority.

Live updates come from `/runs/{run_id}/events/stream` (the existing
event projection). The same event envelope and the same phase/skill
rules are used server-side and client-side, so there is one renderer.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from raphael_ibm_bob.harness import api
from raphael_ibm_bob.http.views import decision_trace as dt
from raphael_ibm_bob.http.views import event_stream as _stream

HTML = "text/html; charset=utf-8"

_ROLE_ORDER = ("investigator", "test_analyst", "remediation_planner",
               "verifier", "falsifier", "evidence_analyst")

_EXTRA_CSS = """
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media (max-width:1100px){.grid2{grid-template-columns:1fr}}
.spec{display:grid;gap:3px}
.spec .row{display:flex;align-items:center;gap:8px;padding:5px 8px;
border:1px solid var(--border);border-radius:3px;font-size:11px;
text-transform:uppercase;letter-spacing:.05em}
.spec .row.active{border-color:rgba(91,127,224,.5);color:var(--primary)}
.spec .row.complete{border-color:rgba(53,183,122,.4);color:var(--ok)}
.spec .row.ready{color:var(--muted)}
.logline{display:grid;grid-template-columns:70px 110px 1fr auto;gap:8px;
font-family:'JetBrains Mono',ui-monospace,Menlo,Consolas,monospace;
font-size:11.5px;padding:4px 6px;border-bottom:1px solid rgba(36,42,51,.6)}
.logline .at{color:var(--muted)}
.logline .actor{color:var(--primary);text-transform:uppercase}
.logline .what{color:var(--text)}
.logline .st{color:var(--sec)}
.logline .st.ok{color:var(--ok)}
.logline .st.crit{color:var(--crit)}
.logline .st.warn{color:var(--warn)}
#stream-log{max-height:420px;overflow:auto}
.statusbar{display:flex;align-items:center;gap:10px;font-size:11px;
color:var(--sec);margin:8px 0}
.dot{width:8px;height:8px;border-radius:50%;background:var(--muted)}
.dot.live{background:var(--ok);box-shadow:0 0 6px var(--ok)}
.dot.down{background:var(--crit)}
.control{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.btn{font:inherit;font-size:11px;letter-spacing:.08em;text-transform:uppercase;
background:var(--panel2);color:var(--text);border:1px solid var(--border);
border-radius:3px;padding:7px 14px;cursor:pointer}
.btn:hover{border-color:var(--primary)}
.btn[disabled]{opacity:.5;cursor:not-allowed}
.btn.crit{border-color:rgba(211,79,97,.5);color:var(--crit)}
.hint{color:var(--muted);font-size:11px}
form.start{display:grid;gap:10px;max-width:560px}
form.start label{display:grid;gap:4px;font-size:11px;color:var(--muted);
text-transform:uppercase;letter-spacing:.05em}
form.start input,form.start select{font:inherit;background:var(--bg);
color:var(--text);border:1px solid var(--border);border-radius:3px;
padding:7px 9px}
a.row-link{color:var(--primary);text-decoration:none}
fieldset.advanced{border:1px solid var(--border);border-radius:3px;
padding:10px 12px;display:grid;gap:10px;margin:0}
fieldset.advanced legend{font-size:10px;color:var(--muted);
letter-spacing:.08em;text-transform:uppercase;padding:0 4px}
fieldset.advanced .hint{margin:0;line-height:1.5}
.hidden{display:none !important}
.panel.mode{border-color:rgba(91,127,224,.35)}
.mode-radios{display:flex;gap:18px;margin:4px 0 10px}
.modeform label.radio{display:flex;align-items:center;gap:6px;font-size:12px;
letter-spacing:.05em;text-transform:uppercase;color:var(--text)}
.testing-config{display:grid;gap:6px;max-width:420px}
.testing-config label{display:grid;gap:4px;font-size:11px;color:var(--muted);
text-transform:uppercase;letter-spacing:.05em}
.testing-config select{font:inherit;background:var(--bg);color:var(--text);
border:1px solid var(--border);border-radius:3px;padding:7px 9px}
.mode-actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap;
margin-top:10px}
.htb-context{margin-top:12px;padding-top:10px;border-top:1px solid var(--border)}
.muted{color:var(--muted)}
.targetform{display:grid;gap:8px;max-width:560px;margin-top:10px}
.targetform label{display:grid;gap:4px;font-size:11px;color:var(--muted);
text-transform:uppercase;letter-spacing:.05em}
.targetform input{font:inherit;background:var(--bg);color:var(--text);
border:1px solid var(--border);border-radius:3px;padding:7px 9px}
"""


def _shell(title: str, body: str, script: str = "") -> str:
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, "
        "initial-scale=1\">"
        f"<title>{dt._e(title)}</title>"
        f"<style>{dt._CSS}{_EXTRA_CSS}</style></head><body>"
        '<header class="cmdbar"><span class="brand">RAPHAEL</span>'
        '<span class="screen">Operations</span>'
        '<span class="banner">GOVERNED OPS // SCOPE-LOCKED</span>'
        '<span class="spacer"></span><span class="led ok"></span></header>'
        f"<main>{body}"
        '<p class="readonly">READ-ONLY SNAPSHOT STREAM · orchestration via '
        'harness.api · no execution controls</p></main>'
        '<footer class="policystrip mono">POLICY: FAIL-CLOSED · MODE: '
        f'GOVERNED · GATE: QUALITY</footer><script>{script}</script>'
        "</body></html>")


# ---------------------------------------------------------------------------
# index + start operation
# ---------------------------------------------------------------------------

#: Last-resort candidate target, used only when the selected session's
#: mission declares no `problem["symptom_target"]`. It mirrors the
#: Runner's documented default; the UI never invents a target.
DEFAULT_CANDIDATE_TARGET = "src/fixed.py"


def _session_candidate_target(session) -> str:
    """Project a session's mission-derived candidate target, or ''.

    Reads `mission.problem["symptom_target"]` for presentation only.
    The Harness, Policy, and Runner remain authoritative; this grants no
    execution authority and never fabricates a target.
    """
    mission = getattr(session, "mission", None)
    problem = getattr(mission, "problem", None)
    if isinstance(problem, dict):
        target = problem.get("symptom_target")
        if isinstance(target, str) and target.strip():
            return target.strip()
    return ""


def _candidate_targets(sessions: List[str], sessions_root) -> Dict[str, str]:
    """Map session_id -> mission-derived candidate target ('' if none)."""
    targets: Dict[str, str] = {}
    for session_id in sessions:
        try:
            session = api.get_session(session_id, sessions_root)
        except Exception:
            targets[session_id] = ""
            continue
        targets[session_id] = _session_candidate_target(session)
    return targets


_CANDIDATE_DEFAULT_JS = """
(function () {
  var form = document.querySelector('form.start');
  if (!form) { return; }
  var select = form.querySelector('select[name="session_id"]');
  var input = form.querySelector('input[name="candidate_target"]');
  if (!select || !input) { return; }
  var edited = false;
  input.addEventListener('input', function () { edited = true; });
  select.addEventListener('change', function () {
    if (edited) { return; }
    var opt = select.options[select.selectedIndex];
    var target = opt ? (opt.getAttribute('data-candidate-target') || '') : '';
    if (target) { input.value = target; }
  });
})();
"""


_MODE_JS = r"""
(function(){
  var form = document.getElementById('mode-form');
  if (!form) { return; }
  var KEY = sessionStorage.getItem('raphael_api_key') || '';
  var cfg = document.getElementById('testing-config');
  function isTesting(){
    var r = form.querySelector('input[name="raphael_mode"]:checked');
    return !!r && r.value === 'testing';
  }
  function sync(){
    if (cfg) { cfg.classList.toggle('hidden', !isTesting()); }
  }
  form.querySelectorAll('input[name="raphael_mode"]').forEach(function(r){
    r.addEventListener('change', sync);
  });
  sync();
  form.addEventListener('submit', async function(ev){
    ev.preventDefault();
    var mode = isTesting() ? 'testing' : 'normal';
    var body = {mode: mode};
    if (mode === 'testing') {
      var sel = document.getElementById('testing-profile');
      body.testing_profile = (sel && sel.value) || 'htb';
    }
    var h = {'Content-Type': 'application/json'};
    if (KEY) { h['X-API-Key'] = KEY; }
    try {
      var r = await fetch('/mode', {
        method: 'POST', headers: h, body: JSON.stringify(body)});
      if (!r.ok) {
        var b = await r.json().catch(function(){ return {}; });
        var hint = document.getElementById('mode-hint');
        if (hint) { hint.textContent =
          (b.error && b.error.message) || 'mode update failed'; }
        return;
      }
      location.reload();
    } catch (e) {
      var hint2 = document.getElementById('mode-hint');
      if (hint2) { hint2.textContent = 'mode update failed'; }
    }
  });
})();
"""


_TARGET_JS = r"""
(function(){
  var form = document.getElementById('htb-target-form');
  if (!form) { return; }
  var KEY = sessionStorage.getItem('raphael_api_key') || '';
  function hdr(extra){
    var x = extra || {};
    if (KEY) { x['X-API-Key'] = KEY; }
    return x;
  }
  function val(id){ var e = document.getElementById(id); return e ? e.value.trim() : ''; }
  function hint(t){ var e = document.getElementById('tg-hint'); if (e) e.textContent = t; }
  form.addEventListener('submit', async function(ev){
    ev.preventDefault();
    var body = {
      mission_id: val('tg-mission'),
      locator: val('tg-locator'),
      allowed_ports: val('tg-ports'),
      allowed_protocols: val('tg-protocols'),
      scope: val('tg-scope'),
      authorization_ref: val('tg-auth')
    };
    try {
      var r = await fetch('/htb/target', {
        method:'POST', headers: hdr({'Content-Type':'application/json'}),
        body: JSON.stringify(body)
      });
      var b = await r.json().catch(function(){ return {}; });
      if (!r.ok) { hint((b.error && b.error.message) || 'target rejected'); return; }
      location.reload();
    } catch(e) { hint('target update failed'); }
  });
  var clear = document.getElementById('tg-clear');
  if (clear) clear.addEventListener('click', async function(){
    try { await fetch('/htb/target/clear', {method:'POST', headers: hdr()}); }
    catch(e) {}
    location.reload();
  });
})();
"""


def render_index(run_ids: List[str], *, runs_root, sessions_root,
                 vpn_status: dict = None, mode_state: dict = None,
                 target_state: dict = None) -> str:
    rows = []
    for run_id in run_ids:
        try:
            run = api.get_run(run_id, runs_root)
        except Exception:
            continue
        state = dt._state_name(run.state)
        cls = ("ok" if state == "completed" else
               "crit" if state in ("refused", "failed") else "muted")
        rows.append(
            f'<tr><td><a class="row-link mono" '
            f'href="/operations/{dt._e(run_id)}">{dt._e(run_id)}</a></td>'
            f'<td>{dt._e(run.mission.mission_id)}</td>'
            f'<td class="mono">{dt._e(run.workspace_root)}</td>'
            f'<td>{dt._pill(state.upper(), cls)}</td>'
            f'<td class="mono">{dt._e(run.gate_verdict or "—")}</td></tr>')
    table = ("<table class=\"dense\"><thead><tr><th>RUN</th><th>MISSION</th>"
             "<th>WORKSPACE</th><th>STATE</th><th>GATE</th></tr></thead>"
             f"<tbody>{''.join(rows)}</tbody></table>"
             if rows else '<p class="empty">No runs yet.</p>')

    sessions = api.get_sessions(sessions_root)
    targets = _candidate_targets(sessions, sessions_root)
    default_candidate = (
        targets[sessions[0]]
        if sessions and targets.get(sessions[0])
        else DEFAULT_CANDIDATE_TARGET)
    options = "".join(
        f'<option value="{dt._e(s)}" '
        f'data-candidate-target="{dt._e(targets[s])}">'
        f'{dt._e(s)}</option>' for s in sessions)
    testing_htb = (
        (mode_state or {}).get("mode") == "testing"
        and (mode_state or {}).get("testing_profile") == "htb")
    cand_attr = " disabled" if testing_htb else ""
    start = (
        '<section class="panel"><h2>NEW OPERATION</h2>'
        '<p class="note">Starts a governed run through the existing Harness '
        'API. HTTP start is synchronous for model runs — for long live '
        'observation, start out-of-band (CLI) and open the console.</p>'
        '<form class="start" method="post" action="/operations/start">'
        '<label>SESSION<select name="session_id" required>'
        f'{options}</select></label>'
        '<label>EXECUTION MODE<select name="mode">'
        '<option value="runner">runner (deterministic control loop)</option>'
        '<option value="model">model-led</option></select></label>'
        '<label>MAX TURNS<input name="max_turns" type="number" '
        'min="1" max="50" value="14"></label>'
        '<label>CANDIDATE TARGET (runner)'
        + (' <span class="muted">— not used in HTB mode</span>'
           if testing_htb else '')
        + '<input name="candidate_target" '
        f'value="{dt._e(default_candidate)}"{cand_attr}></label>'
        '<fieldset class="advanced"><legend>ADVANCED GOVERNED RUN '
        '(optional, runner)</legend>'
        '<p class="hint">Values map to existing Runner arguments. Every '
        'action still travels UI &rarr; harness.api &rarr; Runner &rarr; '
        'Runtime &rarr; Broker &rarr; Policy.</p>'
        '<label>CANDIDATE SUMMARY<input name="candidate_summary" '
        'placeholder="session.py mishandles tokens"></label>'
        '<label>CHALLENGER TARGET<input name="challenger_target" '
        'placeholder="src/challenger.txt"></label>'
        '<label>CHALLENGER FORBIDDEN SUBSTRING<input '
        'name="challenger_forbidden_substring" '
        'placeholder="BUG: still contains the original defect"></label>'
        '<label>VERIFICATION TEST TARGETS (comma-separated)<input '
        'name="verification_tests" placeholder="src/test_ok.py"></label>'
        '<label>MAX REPLANS<input name="max_replans" type="number" '
        'min="0" max="10" value="1"></label>'
        '</fieldset>'
        '<div><button class="btn" type="submit">START OPERATION</button></div>'
        '</form></section>')

    mode = (mode_state or {}).get("mode", "normal")
    profile = (mode_state or {}).get("testing_profile")
    testing_htb = (mode == "testing" and profile == "htb")
    vpn_html = "" if testing_htb else _vpn_strip(vpn_status)
    body = (f"<h1>OPERATIONS</h1>"
            f"{_mode_panel(mode_state, vpn_status, target_state)}"
            f"{vpn_html}{table}{start}")
    return _shell("RAPHAEL — Operations", body,
                  _CANDIDATE_DEFAULT_JS + _MODE_JS + _TARGET_JS)


_MODE_KIND = {"normal": "muted", "testing": "info"}
_VPN_KIND = {"connected": "ok", "connecting": "info",
             "disconnecting": "info", "failed": "crit",
             "disconnected": "muted"}


def _mode_dict(mode_state) -> dict:
    if isinstance(mode_state, dict):
        return mode_state
    return {"mode": "unknown", "testing_profile": None}


def _vpn_badge(vpn_status) -> str:
    state = str((vpn_status or {}).get("state") or "unknown")
    return dt._pill(state.upper(), _VPN_KIND.get(state, "muted"))


def _htb_context(vpn_status, target_state) -> str:
    """HTB context: VPN + the operator-declared authorized target (D9)."""
    configured = isinstance(target_state, dict) and target_state.get("locator")
    if configured:
        target_cell = dt._e(target_state.get("locator"))
        scope_cell = dt._e(target_state.get("scope") or "—")
        ports_cell = dt._e(", ".join(
            str(p) for p in target_state.get("allowed_ports", [])))
        protos_cell = dt._e(", ".join(
            str(p) for p in target_state.get("allowed_protocols", [])))
        auth_cell = (dt._pill("AUTHORIZED", "ok")
                     + ' <span class="muted">(operator-declared)</span>')
        mission_cell = dt._e(target_state.get("mission_id") or "—")
    else:
        missing = '<span class="muted">Not configured</span>'
        target_cell = missing
        scope_cell = missing
        ports_cell = missing
        protos_cell = missing
        mission_cell = missing
        auth_cell = dt._pill("NOT CONFIGURED", "muted")
    rows = [
        ("VPN", _vpn_badge(vpn_status)),
        ("TARGET", target_cell),
        ("SCOPE", scope_cell),
        ("PORTS", ports_cell),
        ("PROTOCOLS", protos_cell),
        ("AUTHORIZATION", auth_cell),
        ("MISSION", mission_cell),
    ]
    html = "".join(
        f'<div class="kv"><span class="k">{dt._e(k)}</span>'
        f'<span class="v">{v}</span></div>' for k, v in rows)
    return ('<div class="htb-context">'
            '<div class="sublabel">HTB CONTEXT</div>'
            f'<div class="kvlist">{html}</div>'
            + _htb_target_form(target_state)
            + '<div class="mode-actions">'
            '<a class="navlink" href="/operations/network">'
            'OPEN HTB NETWORK</a></div></div>')


def _htb_target_form(target_state) -> str:
    t = target_state if isinstance(target_state, dict) else {}

    def v(key, default=""):
        value = t.get(key)
        return dt._e(value) if value not in (None, "") else default

    ports = (", ".join(str(p) for p in t.get("allowed_ports", []))
             if t else "80,443")
    protos = (", ".join(str(p) for p in t.get("allowed_protocols", []))
              if t else "http,https")
    return (
        '<form class="targetform" id="htb-target-form">'
        '<div class="sublabel">DECLARE AUTHORIZED TARGET</div>'
        '<p class="hint">Authorization is operator-declared for this '
        'authorized lab. Network actions are still gated by Policy.</p>'
        '<label>MISSION ID<input name="mission_id" id="tg-mission" '
        f'value="{v("mission_id")}" required></label>'
        '<label>HOST / IP<input name="locator" id="tg-locator" '
        f'value="{v("locator")}" placeholder="10.129.x.x" required></label>'
        '<label>ALLOWED PORTS<input name="allowed_ports" id="tg-ports" '
        f'value="{dt._e(ports)}" required></label>'
        '<label>ALLOWED PROTOCOLS<input name="allowed_protocols" '
        f'id="tg-protocols" value="{dt._e(protos)}" required></label>'
        '<label>SCOPE (host / CIDR, optional)<input name="scope" '
        f'id="tg-scope" value="{v("scope")}"></label>'
        '<label>AUTHORIZATION REFERENCE<input name="authorization_ref" '
        f'id="tg-auth" value="{v("authorization_ref")}" required></label>'
        '<div class="mode-actions">'
        '<button class="btn" type="submit">SAVE TARGET</button>'
        '<button class="btn crit" type="button" id="tg-clear">CLEAR</button>'
        '<span class="hint" id="tg-hint"></span>'
        '</div></form>')


def _mode_panel(mode_state, vpn_status, target_state=None) -> str:
    """Product mode selector + HTB testing context (D8).

    Configuration only: applying a mode never starts the VPN or any
    network activity. NORMAL hides all testing-specific configuration so
    stale HTB state cannot leak into NORMAL mode.
    """
    state = _mode_dict(mode_state)
    mode = state.get("mode", "normal")
    profile = state.get("testing_profile")
    is_testing = (mode == "testing")
    normal_checked = "" if is_testing else " checked"
    testing_checked = " checked" if is_testing else ""
    htb_selected = " selected" if profile == "htb" else ""
    testing_cls = "testing-config" if is_testing else "testing-config hidden"
    htb = (_htb_context(vpn_status, target_state)
           if (is_testing and profile == "htb") else "")
    return (
        '<section class="panel mode"><h2>RAPHAEL MODE</h2>'
        '<form class="modeform" id="mode-form">'
        '<div class="mode-radios">'
        f'<label class="radio"><input type="radio" name="raphael_mode" '
        f'value="normal"{normal_checked}> NORMAL</label>'
        f'<label class="radio"><input type="radio" name="raphael_mode" '
        f'value="testing"{testing_checked}> TESTING</label>'
        '</div>'
        f'<div id="testing-config" class="{testing_cls}">'
        '<label>TESTING ENVIRONMENT'
        '<select name="testing_profile" id="testing-profile">'
        f'<option value="htb"{htb_selected}>HTB (Hack The Box)</option>'
        '</select></label>'
        '</div>'
        '<div class="mode-actions">'
        '<button class="btn" type="submit">APPLY MODE</button>'
        '<span class="hint" id="mode-hint">Product mode is configuration '
        'only; it never starts the VPN or any network activity.</span>'
        '</div></form>'
        f'{htb}'
        '</section>')


def _vpn_strip(vpn_status) -> str:
    """Compact HTB VPN status strip linking to the VPN console (D7)."""
    if not vpn_status:
        return ('<section class="panel"><h2>HTB VPN</h2>'
                '<p class="note">Connect an authorized lab VPN before '
                'starting a networked operation. '
                '<a class="row-link" href="/operations/network">'
                'Open the VPN console →</a></p></section>')
    state = str(vpn_status.get("state") or "unknown")
    kind = {"connected": "ok", "connecting": "info",
            "disconnecting": "info", "failed": "crit"}.get(state, "muted")
    detail = ""
    if state == "connected":
        detail = (f' · {dt._e(vpn_status.get("interface") or "—")}'
                  f' · {dt._e(vpn_status.get("address") or "—")}')
    return ('<section class="panel"><h2>HTB VPN</h2>'
            f'<p class="note">{dt._pill(state.upper(), kind)}{detail} · '
            '<a class="row-link" href="/operations/network">manage →</a>'
            '</p></section>')


def redirect_page(url: str) -> str:
    body = (f'<p class="note">Operation started. '
            f'<a class="row-link" href="{dt._e(url)}">Open console</a></p>'
            f'<meta http-equiv="refresh" content="0;url={dt._e(url)}">')
    return _shell("RAPHAEL — Starting", body)


# ---------------------------------------------------------------------------
# live console
# ---------------------------------------------------------------------------

def _specialists(d: Dict[str, Any]) -> str:
    skill_role = {s.id: (s.role or "") for s in d["skills"].values()}
    used = {}
    for r in d["requests"]:
        requester = r.get("requester") or ""
        if requester.startswith("skill:"):
            used[requester.split("skill:", 1)[1]] = True
    rows = []
    for role in _ROLE_ORDER:
        skills = [sid for sid, rr in skill_role.items() if rr == role]
        active = any(s in used for s in skills)
        state = "active" if active else "ready"
        rows.append(
            f'<div class="row {state}" data-role="{dt._e(role)}">'
            f'<span class="dot"></span><span>{dt._e(role)}</span>'
            f'<span class="spacer"></span>'
            f'<span class="mono" data-role-state>'
            f'{"ACTIVE" if active else "READY"}</span></div>')
    return ('<section class="panel"><h2>SPECIALISTS</h2>'
            f'<div class="spec">{"".join(rows)}</div></section>')


def _stream_prefill(events: List[Dict[str, Any]]) -> str:
    keep = ("ACTION_REQUESTED", "POLICY_DECISION", "EXECUTION_RESULT",
            "VERIFICATION_RESULT", "FALSIFICATION_RESULT",
            "FINDING_CHANGED", "REPLAN_CREATED", "GATE_EVALUATED")
    lines = []
    for e in events:
        if e.get("type") not in keep:
            continue
        lines.append(
            f'<div class="logline"><span class="at mono">—</span>'
            f'<span class="actor">{dt._e(e.get("requester") or e.get("type"))}'
            f'</span><span class="what">{dt._e(e.get("capability") or e.get("type"))}'
            f' {dt._e(e.get("target") or "")}</span>'
            f'<span class="st">{dt._e(e.get("decision") or "")}</span></div>')
    if not lines:
        lines.append('<div class="empty">Waiting for events…</div>')
    return "".join(lines)


def render_console(run_id: str, *, runs_root, sessions_root) -> str:
    data = dt.collect(run_id, runs_root=runs_root,
                      sessions_root=sessions_root)
    run = data["run"]
    gate_html = dt._stage_gate(data)["html"]
    gate = data["gate"] or {}
    verdict = (gate.get("decision") or "in-progress").upper()
    skill_role = {s.id: (s.role or "") for s in data["skills"].values()}
    cfg = {"runId": run_id, "skillRole": skill_role,
           "terminal": run.is_terminal()}
    controls = _controls(run)
    body = (
        f'{dt._header(data)}'
        f'{dt._pipeline_html(data)}'
        '<div class="statusbar"><span class="dot" id="conn-dot"></span>'
        '<span id="conn-text">CONNECTING…</span>'
        '<span class="spacer"></span>'
        '<span class="mono" id="conn-last">last event: —</span></div>'
        f'{controls}'
        '<div class="grid2">'
        f'{_specialists(data)}'
        '<section class="panel"><h2>OPERATION STREAM</h2>'
        f'<div id="stream-log">{_stream_prefill(data["events"])}</div>'
        '</section></div>'
        '<section class="panel bob" id="bob-panel">'
        f'<h2>IBM BOB CONTROL PLANE</h2>{dt._control_plane(data)}</section>'
        '<section class="panel gate" id="gate-panel"><h2>QUALITY GATE</h2>'
        f'<div class="gate-final">{dt._e(verdict)}</div>{gate_html}</section>'
    )
    return _shell(f"RAPHAEL — {run_id}", body,
                  f"window.RAPHAEL={json.dumps(cfg, sort_keys=True)};{_JS}")


def _controls(run) -> str:
    state = dt._state_name(run.state)
    if state == "pending":
        return ('<section class="panel"><h2>CONTROLS</h2>'
                '<div class="control">'
                f'<form method="post" action="/operations/{dt._e(run.run_id)}/cancel">'
                '<button class="btn crit" type="submit">CANCEL</button>'
                '</form>'
                '<span class="hint">Pending run — cancellation is '
                'cooperative.</span></div></section>')
    if state == "running":
        return ('<section class="panel"><h2>CONTROLS</h2>'
                '<div class="control">'
                f'<button class="btn crit" type="button" disabled>CANCEL</button>'
                '<span class="hint">Running operation cannot be force-killed; '
                'the in-flight timeout remains the bound.</span>'
                '</div></section>')
    return ('<section class="panel"><h2>CONTROLS</h2>'
            '<div class="control">'
            f'<button class="btn crit" type="button" disabled>CANCEL</button>'
            f'<span class="hint">Run is terminal ({dt._e(state)}); it cannot '
            'be cancelled or silently restarted.</span></div></section>')


_JS = _stream.LIVE_JS


__all__ = ["HTML", "redirect_page", "render_console", "render_index"]
