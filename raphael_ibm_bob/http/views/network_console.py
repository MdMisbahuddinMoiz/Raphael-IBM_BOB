"""raphael_ibm_bob.http.views.network_console — HTB VPN operator screen.

Server-rendered shell in the SAME visual language as the other operator
screens (Decision Trace base CSS), plus a small vanilla-JS client that
polls ``/vpn/status`` and drives ``/vpn/connect`` / ``/vpn/disconnect``.

The page ORCHESTRATES the VPN manager only; it holds no execution
authority and never sees profile contents after submission. It does not
implement any target, scanning, or mission functionality (D7 scope).
"""
from __future__ import annotations

from typing import Any, Dict

from raphael_ibm_bob.http.views import decision_trace as dt

HTML = "text/html; charset=utf-8"

_STATE_KIND = {
    "disconnected": "muted",
    "connecting": "info",
    "connected": "ok",
    "disconnecting": "info",
    "failed": "crit",
}


def _shell(title: str, body: str, script: str = "") -> str:
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, "
        "initial-scale=1\">"
        f"<title>{dt._e(title)}</title>"
        f"<style>{dt._CSS}{_EXTRA_CSS}</style></head><body>"
        '<header class="cmdbar"><span class="brand">RAPHAEL</span>'
        '<span class="screen">HTB VPN</span>'
        '<span class="banner">GOVERNED OPS // SCOPE-LOCKED</span>'
        '<span class="spacer"></span>'
        '<span class="dot" id="vpn-led"></span>'
        '<span class="cmeta mono" id="vpn-led-text">—</span></header>'
        f"<main>{body}"
        '<p class="readonly">CONTROLLED VPN LIFECYCLE · orchestration via '
        'the existing HTTP API · no target/scanning/execution controls</p>'
        '</main>'
        '<footer class="policystrip mono">POLICY: FAIL-CLOSED · MODE: '
        'GOVERNED · VPN: OPERATOR-SUPPLIED PROFILE</footer>'
        f'<script>{script}</script>'
        "</body></html>")


def render_network(status: Dict[str, Any]) -> str:
    """Render the VPN operator screen from a status snapshot."""
    body = (
        '<section class="panel vpn"><h2>HTB VPN</h2>'
        '<p class="note">Connect to an authorized Hack The Box lab VPN using '
        'your own <code>.ovpn</code> profile. The profile is validated as '
        'configuration data and never returned or logged. This layer only '
        'establishes connectivity; it does not scan or target anything.</p>'
        f'{_status_block(status)}'
        f'{_profile_form(status)}'
        f'{_controls(status)}'
        f'{_history(status)}'
        '</section>'
        f'{_navigation()}'
    )
    return _shell("RAPHAEL — HTB VPN", body, _JS)


def _status_block(status: Dict[str, Any]) -> str:
    state = str(status.get("state") or "unknown")
    kind = _STATE_KIND.get(state, "muted")
    rows = [
        ("PROFILE", status.get("profile_name")),
        ("INTERFACE", status.get("interface")),
        ("VPN ADDRESS", status.get("address")),
        ("CONNECTED AT", status.get("connected_at")),
        ("PROCESS", status.get("process_state")),
    ]
    error = status.get("error")
    error_html = ""
    if error:
        error_html = (f'<div class="vpn-error">{dt._e(error)}</div>')
    return (
        '<div class="vpn-status">'
        '<div class="vpn-state"><span class="vpn-dot '
        f'{kind}" id="vpn-state-dot"></span>'
        f'<span class="vpn-state-label" id="vpn-state-label">'
        f'{dt._e(state.upper())}</span></div>'
        f'<div id="vpn-meta">{dt._kv([(k, v) for k, v in rows])}</div>'
        f'<div id="vpn-error-slot">{error_html}</div>'
        '</div>')


def _profile_form(status: Dict[str, Any]) -> str:
    return (
        '<form class="vpn-form" id="vpn-connect-form">'
        '<label>PROFILE (.ovpn)<input type="file" id="vpn-profile" '
        'accept=".ovpn,.conf,text/plain" required></label>'
        '<label>API KEY (optional, kept in this browser tab)'
        '<input type="password" id="vpn-api-key" '
        'placeholder="RAPHAEL_API_KEY"></label>'
        '<div class="vpn-actions">'
        '<button class="btn" type="submit" id="vpn-connect">CONNECT</button>'
        '<button class="btn crit" type="button" id="vpn-disconnect" '
        'disabled>DISCONNECT</button>'
        '</div>'
        '<p class="hint" id="vpn-hint">No connection active.</p>'
        '</form>')


def _controls(status: Dict[str, Any]) -> str:
    return (
        '<p class="note">CONNECT validates and starts OpenVPN, then waits '
        'for the tunnel handshake. PROCESS STARTED is not the same as '
        'CONNECTED: the state advances only after OpenVPN reports '
        'initialization complete.</p>')


def _history(status: Dict[str, Any]) -> str:
    events = status.get("history") or []
    if not events:
        return ('<div class="sublabel">LIFECYCLE</div>'
                '<p class="empty">No VPN lifecycle events yet.</p>')
    rows = [[dt._fmt_ts(_epoch(e.get("ts"))), e.get("event")]
            for e in events[-12:]]
    return ('<div class="sublabel">LIFECYCLE</div>'
            + dt._table(["TIME", "EVENT"], rows, mono=(0, 1)))


def _epoch(iso: Any) -> int:
    if not isinstance(iso, str):
        return 0
    try:
        from datetime import datetime
        return int(datetime.fromisoformat(iso).timestamp() * 1000)
    except ValueError:
        return 0


def _navigation() -> str:
    return ('<section class="panel"><h2>NAVIGATION</h2>'
            '<div class="navgrid">'
            '<a class="navlink" href="/command">COMMAND CENTER</a>'
            '<a class="navlink" href="/operations">OPERATIONS</a>'
            '<a class="navlink" href="/operations/findings">FINDINGS</a>'
            '<a class="navlink" href="/operations/evidence">EVIDENCE</a>'
            '<a class="navlink" href="/operations/gate">'
            'POLICY &amp; QUALITY GATE</a>'
            '</div></section>')


_EXTRA_CSS = """
.panel.vpn{border-color:rgba(91,127,224,.35)}
.vpn-status{display:grid;gap:10px;margin:8px 0 16px}
.vpn-state{display:flex;align-items:center;gap:10px}
.vpn-dot{width:10px;height:10px;border-radius:50%;background:var(--muted)}
.vpn-dot.ok{background:var(--ok);box-shadow:0 0 6px var(--ok)}
.vpn-dot.info{background:var(--primary);box-shadow:0 0 6px var(--primary)}
.vpn-dot.crit{background:var(--crit);box-shadow:0 0 6px var(--crit)}
.vpn-state-label{font-weight:700;letter-spacing:.1em;font-size:13px}
.vpn-error{margin-top:6px;padding:8px 10px;border-left:2px solid var(--crit);
background:rgba(211,79,97,.08);color:var(--crit);font-size:12px;
word-break:break-word}
form.vpn-form{display:grid;gap:10px;max-width:620px}
form.vpn-form label{display:grid;gap:4px;font-size:11px;color:var(--muted);
text-transform:uppercase;letter-spacing:.05em}
form.vpn-form input{font:inherit;background:var(--bg);color:var(--text);
border:1px solid var(--border);border-radius:3px;padding:7px 9px}
.vpn-actions{display:flex;gap:10px;flex-wrap:wrap}
.hint{color:var(--muted);font-size:11px;margin:0}
"""


_JS = r"""
(function(){
  var KEY = sessionStorage.getItem('raphael_api_key') || '';
  var dot = document.getElementById('vpn-led');
  var ledText = document.getElementById('vpn-led-text');
  var stateDot = document.getElementById('vpn-state-dot');
  var stateLabel = document.getElementById('vpn-state-label');
  var meta = document.getElementById('vpn-meta');
  var errSlot = document.getElementById('vpn-error-slot');
  var connectBtn = document.getElementById('vpn-connect');
  var disconnectBtn = document.getElementById('vpn-disconnect');
  var hint = document.getElementById('vpn-hint');
  var keyInput = document.getElementById('vpn-api-key');
  if (keyInput) {
    keyInput.value = KEY;
    keyInput.addEventListener('change', function(){
      KEY = keyInput.value.trim();
      sessionStorage.setItem('raphael_api_key', KEY);
      refresh();
    });
  }
  function headers(extra){
    var h = extra || {};
    if (KEY) { h['X-API-Key'] = KEY; }
    return h;
  }
  function api(path, opts){
    opts = opts || {};
    opts.headers = headers(opts.headers || {});
    return fetch(path, opts);
  }
  function esc(s){ var d=document.createElement('div'); d.textContent=s==null?'':String(s); return d.innerHTML; }
  function kv(label, value){
    if (value === null || value === undefined || value === '') return '';
    return '<div class="kv"><span class="k">'+esc(label)+'</span>'+
           '<span class="v">'+esc(value)+'</span></div>';
  }
  function setDot(el, kind){
    if (!el) return;
    el.className = el.className.replace(/\b(ok|info|crit|muted)\b/g,'').trim()+
                   ' '+kind;
  }
  function render(s){
    var state = (s && s.state) || 'unknown';
    var kind = {disconnected:'muted', connecting:'info', connected:'ok',
                disconnecting:'info', failed:'crit'}[state] || 'muted';
    if (stateLabel) stateLabel.textContent = state.toUpperCase();
    setDot(stateDot, kind);
    setDot(dot, kind);
    if (ledText) ledText.textContent = state.toUpperCase();
    if (meta) {
      meta.innerHTML = kv('PROFILE', s.profile_name) +
        kv('INTERFACE', s.interface) + kv('VPN ADDRESS', s.address) +
        kv('CONNECTED AT', s.connected_at) + kv('PROCESS', s.process_state);
    }
    if (errSlot) {
      errSlot.innerHTML = (s && s.error)
        ? '<div class="vpn-error">'+esc(s.error)+'</div>' : '';
    }
    var busy = (state === 'connecting' || state === 'disconnecting');
    var active = (state === 'connected' || state === 'connecting');
    if (connectBtn) connectBtn.disabled = busy || state === 'connected';
    if (disconnectBtn) disconnectBtn.disabled = !active || state === 'disconnecting';
    if (hint) {
      hint.textContent = state === 'connected'
        ? 'Tunnel established. Ready for an authorized HTB target.'
        : state === 'failed' ? 'Connection failed. Review the error, then retry.'
        : state === 'connecting' ? 'Starting OpenVPN and waiting for the tunnel…'
        : state === 'disconnecting' ? 'Terminating OpenVPN…'
        : 'No connection active.';
    }
  }
  function showError(msg){
    if (errSlot) errSlot.innerHTML = '<div class="vpn-error">'+esc(msg)+'</div>';
  }
  async function refresh(){
    try {
      var r = await api('/vpn/status');
      if (!r.ok) { showError('status '+r.status); return; }
      render(await r.json());
    } catch(e) { if (ledText) ledText.textContent = 'OFFLINE'; }
  }
  var form = document.getElementById('vpn-connect-form');
  if (form) form.addEventListener('submit', async function(ev){
    ev.preventDefault();
    var input = document.getElementById('vpn-profile');
    var file = input && input.files && input.files[0];
    if (!file) { showError('select an .ovpn profile first'); return; }
    if (connectBtn) connectBtn.disabled = true;
    render({state:'connecting'});
    try {
      var text = await file.text();
      var r = await api('/vpn/connect', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({profile:text, profile_name:file.name})
      });
      var body = await r.json().catch(function(){ return {}; });
      if (!r.ok) {
        showError((body.error && body.error.message) || ('connect failed ('+r.status+')'));
        await refresh(); return;
      }
      render(body);
    } catch(e) {
      showError('connect failed: '+e);
    }
    refresh();
  });
  if (disconnectBtn) disconnectBtn.addEventListener('click', async function(){
    disconnectBtn.disabled = true;
    try {
      var r = await api('/vpn/disconnect', {method:'POST'});
      var body = await r.json().catch(function(){ return {}; });
      if (!r.ok) { showError((body.error && body.error.message) || 'disconnect failed'); }
      else { render(body); }
    } catch(e) { showError('disconnect failed: '+e); }
    refresh();
  });
  refresh();
  setInterval(refresh, 2000);
})();
"""


__all__ = ["HTML", "render_network"]
