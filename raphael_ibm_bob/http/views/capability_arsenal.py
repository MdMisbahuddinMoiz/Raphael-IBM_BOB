"""raphael_ibm_bob.http.views.capability_arsenal — M15.9.

Read-only Capability Arsenal: the currently DECLARED capabilities,
skills, and roles, aggregated through the existing read-only Harness
API.

    GET /operations/capabilities   (text/html)

Authoritative sources (via `harness.api` only):

- `list_roles()`         -> specialization.RoleRegistry (declared roles)
- `list_capabilities()`  -> skills.CapabilityRegistry (declared capabilities)
- `list_skills()`        -> skills.CapabilityRegistry (declared skills)

CRITICAL SEMANTIC RULE — DECLARATION != AUTHORIZATION
-----------------------------------------------------
A capability/skill/role declaration describes WHAT work is intended and
which evidence shape it implies. It does NOT grant authority to execute
anything. Actual execution remains governed exclusively by:

    ActionRequest -> Runtime -> Broker -> Policy -> Execution -> Evidence
      -> Verification -> Falsification -> Replan -> Quality Gate

This screen is a catalog/observability surface only: no execution
controls, no enable/disable, no authorization, no mutation. Declarations
are descriptive, not permissions. Evidence contracts shown here are
DECLARED contracts, never a claim that the evidence already exists.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from raphael_ibm_bob.capability_fabric import default_fabric
from raphael_ibm_bob.harness import api
from raphael_ibm_bob.http.views import decision_trace as dt

HTML = "text/html; charset=utf-8"

KINDS: Tuple[Tuple[str, str], ...] = (
    ("all", "ALL"),
    ("roles", "ROLES"),
    ("skills", "SKILLS"),
    ("capabilities", "CAPABILITIES"),
)


# ---------------------------------------------------------------------------
# aggregation (read-only, harness.api only)
# ---------------------------------------------------------------------------

def collect() -> Dict[str, Any]:
    roles = api.list_roles()
    capabilities = api.list_capabilities()
    skills = api.list_skills()

    skills_by_id = {s.id: s for s in skills}
    cap_value = {c.capability.value: c for c in capabilities}

    # M16.4: provider identity comes from the authoritative Capability
    # Fabric (side-effect-free resolution), never hardcoded in the view.
    fabric = default_fabric()
    providers = list(fabric.list_providers())

    def _resolution(capability):
        """(resolved_provider_id_or_None, all_claimants) from the Fabric."""
        claimants = tuple(fabric.providers_for(capability))
        resolved = claimants[0] if len(claimants) == 1 else None
        return resolved, claimants

    provider_by_capability = {}
    for c in capabilities:
        resolved, claimants = _resolution(c.capability)
        provider_by_capability[c.capability.value] = {
            "resolved": resolved, "claimants": claimants}


    role_rows = []
    for role in roles:
        role_skills = sorted(s.id for s in skills if s.role == role.id)
        role_rows.append({
            "id": role.id,
            "name": role.name,
            "purpose": role.purpose,
            "capabilities": sorted(c.value for c in role.capabilities),
            "skills": role_skills,
        })

    skill_rows = []
    for skill in skills:
        res = provider_by_capability.get(skill.capability.value, {})
        skill_rows.append({
            "id": skill.id,
            "name": skill.name,
            "version": skill.version,
            "description": skill.description,
            "capability": skill.capability.value,
            "role": skill.role or "—",
            "target_schema": skill.target_schema,
            "purpose_template": skill.purpose_template,
            "success_markers": list(skill.success_markers),
            "prerequisites": list(skill.prerequisites),
            "evidence_produced": list(skill.evidence_produced),
            "evidence_consumed": list(skill.evidence_consumed),
            "provider": res.get("resolved"),
            "provider_claimants": list(res.get("claimants", ())),
        })

    cap_rows = []
    for cap in capabilities:
        cid = cap.capability.value
        associated_skills = sorted(s.id for s in skills
                                   if s.capability.value == cid)
        associated_roles = sorted(r["id"] for r in role_rows
                                  if cid in r["capabilities"])
        res = provider_by_capability.get(cid, {})
        cap_rows.append({
            "id": cid,
            "description": cap.description,
            "version": cap.version,
            "target_schema": cap.target_schema,
            "purpose_template": cap.purpose_template,
            "verification_expectation": cap.verification_expectation,
            "timeout_seconds": cap.timeout_seconds,
            "evidence_produced": list(cap.evidence_produced),
            "evidence_consumed": list(cap.evidence_consumed),
            "skills": associated_skills,
            "roles": associated_roles,
            "provider": res.get("resolved"),
            "provider_claimants": list(res.get("claimants", ())),
        })

    caps_with_evidence = sum(
        1 for c in cap_rows
        if c["evidence_produced"] or c["evidence_consumed"])
    skills_with_prereqs = sum(
        1 for s in skill_rows if s["prerequisites"])
    caps_by_role = {r["id"]: len(r["capabilities"]) for r in role_rows}
    skills_by_role = {r["id"]: len(r["skills"]) for r in role_rows}

    return {
        "roles": role_rows,
        "skills": skill_rows,
        "capabilities": cap_rows,
        "counts": {
            "roles": len(role_rows),
            "skills": len(skill_rows),
            "capabilities": len(cap_rows),
            "caps_with_evidence": caps_with_evidence,
            "skills_with_prereqs": skills_with_prereqs,
        },
        "caps_by_role": caps_by_role,
        "skills_by_role": skills_by_role,
        "providers": providers,
        "unresolved_skills": sorted(
            s["id"] for s in skill_rows if s["capability"] not in cap_value),
    }


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _authority_banner() -> str:
    return ('<section class="panel authority-panel">'
            '<div class="authority-title">DECLARATION ≠ AUTHORIZATION</div>'
            '<p class="note">A capability, skill, or role declaration '
            'describes intended work and its evidence shape. It grants NO '
            'authority to execute. Every execution is governed by '
            '<span class="mono">ActionRequest → Runtime → Broker → Policy '
            '→ Execution → Evidence → Verification → Falsification → '
            'Replan → Quality Gate</span>.</p>'
            '<div class="authority-flags">'
            '<span class="flag">EXECUTION AUTHORITY: GOVERNED ELSEWHERE</span>'
            '<span class="flag">DECLARATION GRANTS NO EXECUTION AUTHORITY</span>'
            '<span class="flag">PROVIDER RESOLUTION ≠ AUTHORIZATION</span>'
            '<span class="flag">PROVIDER RESOLUTION ≠ EXECUTION</span>'
            '<span class="flag">CATALOG / OBSERVABILITY ONLY</span>'
            '</div>'
            '<p class="note">Provider identity describes which provider the '
            'Capability Fabric resolves for a capability. It is NOT '
            'permission, approval, readiness, active execution, or trusted '
            'completion — every action is still governed by '
            '<span class="mono">Runtime → Broker → Policy</span>.</p>'
            '</section>')


def _summary(data: Dict[str, Any]) -> str:
    c = data["counts"]
    metrics = (
        '<div class="metrics">'
        f'<div class="metric"><span class="mv">{c["roles"]}</span>'
        f'<span class="ml">DECLARED ROLES</span></div>'
        f'<div class="metric"><span class="mv">{c["skills"]}</span>'
        f'<span class="ml">DECLARED SKILLS</span></div>'
        f'<div class="metric"><span class="mv">{c["capabilities"]}</span>'
        f'<span class="ml">DECLARED CAPABILITIES</span></div>'
        f'<div class="metric"><span class="mv">{c["caps_with_evidence"]}</span>'
        f'<span class="ml">CAPABILITIES WITH EVIDENCE CONTRACT</span></div>'
        f'<div class="metric"><span class="mv">{c["skills_with_prereqs"]}</span>'
        f'<span class="ml">SKILLS WITH PREREQUISITES</span></div>'
        '</div>')
    role_cells = "".join(
        f'<div class="kv"><span class="k mono">{dt._e(r)}</span>'
        f'<span class="v">capabilities {data["caps_by_role"][r]} · '
        f'skills {data["skills_by_role"][r]}</span></div>'
        for r in data["caps_by_role"])
    return ('<section class="panel"><h2>ARSENAL SUMMARY</h2>'
            f'{metrics}'
            '<div class="sublabel">CURRENT DECLARED PROVIDER(S)</div>'
            f'<div class="row-inline mono">{dt._e(", ".join(data["providers"]) or "NONE")}</div>'
            '<div class="sublabel">DECLARATIONS BY ROLE</div>'
            f'<div class="kvlist lifecycle">{role_cells}</div>'
            '<p class="note">Counts are derived from the authoritative '
            'declaration registry. Nothing here is persisted runtime '
            'state; declarations carry no availability or permission '
            'semantics.</p></section>')


def _filterbar() -> str:
    chips = "".join(
        f'<button type="button" class="chip{" active" if k == "all" else ""}"'
        f' data-filter="{dt._e(k)}">{dt._e(label)}</button>'
        for k, label in KINDS)
    return ('<section class="panel"><h2>FILTER &amp; SEARCH</h2>'
            '<div class="filterbar"><div class="chips">' + chips + '</div>'
            '<input id="search" class="search" type="search" '
            'placeholder="role / skill / capability…" aria-label="search">'
            '</div><p class="note">Client-side only; no server query '
            'change.</p></section>')


def _roles(data: Dict[str, Any]) -> str:
    rows = []
    for role in data["roles"]:
        rows.append(
            f'<div class="arow" data-kind="roles" '
            f'data-search="{dt._e((role["id"] + " " + role["name"] + " " + role["purpose"]).lower())}">'
            f'<button type="button" class="ahead" aria-expanded="false">'
            f'<span class="aid mono">{dt._e(role["id"])}</span>'
            f'<span class="aname">{dt._e(role["name"])}</span>'
            f'<span class="apurpose">{dt._e(role["purpose"])}</span>'
            f'<span class="acount mono">{len(role["skills"])} skills · '
            f'{len(role["capabilities"])} caps</span></button>'
            f'<div class="adet"><div class="kvlist">'
            f'<div class="kv"><span class="k">SKILLS</span>'
            f'<span class="v mono">{dt._e(", ".join(role["skills"]) or "NONE DECLARED")}</span></div>'
            f'<div class="kv"><span class="k">CAPABILITIES</span>'
            f'<span class="v mono">{dt._e(", ".join(role["capabilities"]))}</span></div>'
            '</div></div></div>')
    return ('<section class="panel"><h2>DECLARED ROLES</h2>'
            '<p class="note">Roles describe responsibility, not '
            'permission.</p>'
            f'<div class="atable" id="ars-roles">{"".join(rows)}</div>'
            '</section>')


def _skills(data: Dict[str, Any]) -> str:
    rows = []
    for skill in data["skills"]:
        prereq = ", ".join(skill["prerequisites"]) or "NONE DECLARED"
        rows.append(
            f'<div class="arow" data-kind="skills" '
            f'data-search="{dt._e((skill["id"] + " " + skill["name"] + " " + skill["capability"] + " " + skill["role"]).lower())}">'
            f'<button type="button" class="ahead" aria-expanded="false">'
            f'<span class="aid mono">{dt._e(skill["id"])}</span>'
            f'<span class="aname">{dt._e(skill["name"])}</span>'
            f'<span class="acap">{dt._e(skill["capability"])}</span>'
            f'<span class="arole mono">{dt._e(skill["role"])}</span>'
            f'<span class="acount mono">v{dt._e(skill["version"])}</span>'
            '</button>'
            '<div class="adet"><div class="kvlist">'
            f'<div class="kv"><span class="k">DESCRIPTION</span>'
            f'<span class="v">{dt._e(skill["description"])}</span></div>'
            f'<div class="kv"><span class="k">CAPABILITY</span>'
            f'<span class="v mono">{dt._e(skill["capability"])}</span></div>'
            f'<div class="kv"><span class="k">RESOLVED PROVIDER</span>'
            f'<span class="v mono">{dt._e(skill["provider"] or "UNKNOWN / NOT VERIFIED")}</span></div>'
            f'<div class="kv"><span class="k">ROLE</span>'
            f'<span class="v mono">{dt._e(skill["role"])}</span></div>'
            f'<div class="kv"><span class="k">TARGET SCHEMA</span>'
            f'<span class="v mono">{dt._e(skill["target_schema"])}</span></div>'
            f'<div class="kv"><span class="k">PURPOSE TEMPLATE</span>'
            f'<span class="v mono">{dt._e(skill["purpose_template"])}</span></div>'
            f'<div class="kv"><span class="k">SUCCESS MARKERS</span>'
            f'<span class="v mono">{dt._e(", ".join(skill["success_markers"]) or "NONE DECLARED")}</span></div>'
            f'<div class="kv"><span class="k">PREREQUISITES</span>'
            f'<span class="v mono">{dt._e(prereq)}</span></div>'
            f'<div class="kv"><span class="k">DECLARED EVIDENCE PRODUCED</span>'
            f'<span class="v mono">{dt._e(", ".join(skill["evidence_produced"]) or "NONE")}</span></div>'
            f'<div class="kv"><span class="k">DECLARED EVIDENCE CONSUMED</span>'
            f'<span class="v mono">{dt._e(", ".join(skill["evidence_consumed"]) or "NONE")}</span></div>'
            '</div></div></div>')
    return ('<section class="panel"><h2>DECLARED SKILLS</h2>'
            '<div class="atable" id="ars-skills">' + "".join(rows) +
            '</div></section>')


def _capabilities(data: Dict[str, Any]) -> str:
    rows = []
    for cap in data["capabilities"]:
        evidence = []
        if cap["evidence_produced"]:
            evidence.append("produced: " + ", ".join(cap["evidence_produced"]))
        if cap["evidence_consumed"]:
            evidence.append("consumed: " + ", ".join(cap["evidence_consumed"]))
        rows.append(
            f'<div class="arow" data-kind="capabilities" '
            f'data-search="{dt._e((cap["id"] + " " + cap["description"] + " " + (cap["provider"] or "")).lower())}">'
            f'<button type="button" class="ahead" aria-expanded="false">'
            f'<span class="aid mono">{dt._e(cap["id"])}</span>'
            f'<span class="aname">{dt._e(cap["description"])}</span>'
            f'<span class="aprov mono">{dt._e(cap["provider"] or "UNRESOLVED")}</span>'
            f'<span class="acount mono">v{dt._e(cap["version"])} · '
            f'{len(cap["skills"])} skills</span></button>'
            '<div class="adet"><div class="kvlist">'
            f'<div class="kv"><span class="k">RESOLVED PROVIDER</span>'
            f'<span class="v mono">{dt._e(cap["provider"] or "UNKNOWN / NOT VERIFIED (no single claimant)")}</span></div>'
            f'<div class="kv"><span class="k">PROVIDER CAPABILITY CLAIM</span>'
            f'<span class="v mono">{dt._e(", ".join(cap["provider_claimants"]) or "NONE")}</span></div>'
            f'<div class="kv"><span class="k">VERSION</span>'
            f'<span class="v mono">{dt._e(cap["version"])}</span></div>'
            f'<div class="kv"><span class="k">TARGET SCHEMA</span>'
            f'<span class="v mono">{dt._e(cap["target_schema"])}</span></div>'
            f'<div class="kv"><span class="k">PURPOSE TEMPLATE</span>'
            f'<span class="v mono">{dt._e(cap["purpose_template"])}</span></div>'
            f'<div class="kv"><span class="k">VERIFICATION EXPECTATION</span>'
            f'<span class="v mono">{dt._e(cap["verification_expectation"] or "NONE DECLARED")}</span></div>'
            f'<div class="kv"><span class="k">TIMEOUT SECONDS</span>'
            f'<span class="v mono">{dt._e(cap["timeout_seconds"] if cap["timeout_seconds"] is not None else "BROKER DEFAULT")}</span></div>'
            f'<div class="kv"><span class="k">DECLARED EVIDENCE CONTRACT</span>'
            f'<span class="v mono">{dt._e(" · ".join(evidence) or "NONE DECLARED")}</span></div>'
            f'<div class="kv"><span class="k">ASSOCIATED SKILLS</span>'
            f'<span class="v mono">{dt._e(", ".join(cap["skills"]) or "NONE")}</span></div>'
            f'<div class="kv"><span class="k">ASSOCIATED ROLES</span>'
            f'<span class="v mono">{dt._e(", ".join(cap["roles"]) or "NONE")}</span></div>'
            '</div></div></div>')
    return ('<section class="panel"><h2>DECLARED CAPABILITIES</h2>'
            '<p class="note">The five BOB capabilities are the only '
            'capabilities the source declares; each is enforced by the '
            'governed boundary, not by this catalog.</p>'
            '<div class="atable" id="ars-capabilities">' + "".join(rows) +
            '</div></section>')


def _relationship(data: Dict[str, Any]) -> str:
    blocks = []
    for role in data["roles"]:
        skills = [s for s in data["skills"] if s["role"] == role["id"]]
        if not skills:
            continue
        leaves = "".join(
            f'<div class="rel-skill"><span class="mono">'
            f'{dt._e(s["id"])}</span><span class="rel-arrow">→</span>'
            f'<span class="mono">{dt._e(s["capability"])}</span></div>'
            for s in skills)
        blocks.append(
            f'<div class="rel-role"><span class="mono rel-rid">'
            f'{dt._e(role["id"])}</span>{leaves}</div>')
    return ('<section class="panel"><h2>DECLARED RELATIONSHIP</h2>'
            '<p class="note">ROLE → SKILL → CAPABILITY is a declared '
            'organizational relationship, not an execution pipeline. It '
            'does not imply role selection grants permission.</p>'
            f'<div class="reltree">{"".join(blocks)}</div></section>')


def _evidence_contracts(data: Dict[str, Any]) -> str:
    rows = []
    for cap in data["capabilities"]:
        rows.append(
            f'<tr><td class="mono">{dt._e(cap["id"])}</td>'
            f'<td class="mono">{dt._e(", ".join(cap["evidence_produced"]) or "—")}</td>'
            f'<td class="mono">{dt._e(", ".join(cap["evidence_consumed"]) or "—")}</td></tr>')
    return ('<section class="panel"><h2>DECLARED EVIDENCE CONTRACTS</h2>'
            '<p class="note">These are DECLARED contracts only. They do not '
            'assert that such evidence currently exists — observed, '
            'persisted evidence lives in '
            '<a class="row-link" href="/operations/evidence">Evidence '
            'Intelligence</a>.</p>'
            '<table class="dense"><thead><tr><th>CAPABILITY</th>'
            '<th>DECLARED PRODUCED</th><th>DECLARED CONSUMED</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table>'
            '</section>')


def _nav() -> str:
    return ('<section class="panel"><h2>NAVIGATION</h2><div class="navgrid">'
            '<a class="navlink" href="/command">COMMAND CENTER</a>'
            '<a class="navlink" href="/operations">OPERATIONS</a>'
            '<a class="navlink" href="/operations/findings">FINDINGS</a>'
            '<a class="navlink" href="/operations/evidence">EVIDENCE</a>'
            '<a class="navlink" href="/operations/gate">POLICY &amp; GATE</a>'
            '</div></section>')


_EXTRA_CSS = """
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
gap:8px;margin:6px 0 12px}
.metric{background:var(--panel2);border:1px solid var(--border);
border-radius:4px;padding:10px 12px;display:grid;gap:2px}
.metric .mv{font-size:22px;font-weight:700;letter-spacing:.04em;color:var(--text)}
.metric .ml{font-size:10px;letter-spacing:.07em;text-transform:uppercase;
color:var(--muted)}
.lifecycle{grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.authority-panel{border-color:rgba(91,127,224,.5)}
.authority-title{font-size:16px;font-weight:700;letter-spacing:.1em;
color:var(--primary);margin-bottom:6px}
.authority-flags{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.flag{font-size:10px;letter-spacing:.06em;text-transform:uppercase;
border:1px solid rgba(91,127,224,.5);color:var(--primary);
border-radius:10px;padding:3px 9px}
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
.atable{display:flex;flex-direction:column}
.arow{border-bottom:1px solid rgba(36,42,51,.6)}
.arow:last-child{border-bottom:none}
.ahead{display:grid;
grid-template-columns:160px 200px 1fr 150px;
gap:10px;align-items:center;width:100%;text-align:left;background:none;
border:none;color:inherit;font:inherit;padding:6px 10px;cursor:pointer}
.ahead:hover{background:var(--panel2)}
.ahead > span{min-width:0;overflow:hidden;text-overflow:ellipsis;
white-space:nowrap}
.aid{color:var(--primary);font-size:11.5px}
.aname{color:var(--text);font-size:11.5px}
.apurpose{color:var(--sec);font-size:11px}
.acap{color:var(--ok);font-size:11px}
.aprov{color:var(--primary);font-size:11px}
.arole{color:var(--sec);font-size:11px}
.acount{color:var(--muted);font-size:10.5px;text-align:right}
.adet{display:none;padding:8px 14px 12px 14px;background:var(--panel2)}
.arow.open .adet{display:block}
.reltree{display:grid;gap:8px}
.rel-role{border:1px solid var(--border);border-radius:4px;padding:8px 12px;
background:var(--panel2)}
.rel-rid{color:var(--primary);font-size:12px;letter-spacing:.04em}
.rel-skill{display:flex;gap:10px;align-items:center;padding:3px 0 3px 18px;
font-size:11.5px;color:var(--sec)}
.rel-arrow{color:var(--muted)}
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
  var roots = ['.arow'];
  var filter = 'all';
  function visible(row){
    if(filter !== 'all' && row.getAttribute('data-kind') !== filter) return false;
    if(search && search.value){
      var q = search.value.toLowerCase();
      if((row.getAttribute('data-search')||'').indexOf(q) < 0) return false;
    }
    return true;
  }
  function apply(){
    var rows = document.querySelectorAll('.arow');
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
  document.addEventListener('click', function(e){
    var head = e.target.closest ? e.target.closest('.ahead') : null;
    if(head){ var r = head.parentNode; var o = r.classList.toggle('open');
      head.setAttribute('aria-expanded', o ? 'true' : 'false'); }
  });
})();
"""


def render_arsenal() -> str:
    data = collect()
    body = (
        f'{_authority_banner()}'
        f'{_summary(data)}'
        f'{_filterbar()}'
        f'{_roles(data)}'
        f'{_skills(data)}'
        f'{_capabilities(data)}'
        f'{_relationship(data)}'
        f'{_evidence_contracts(data)}'
        f'{_nav()}'
        '<p class="readonly">READ-ONLY CATALOG · declarations from the '
        'authoritative capability/skill/role registry via harness.api · no '
        'execution authority, no mutation, no enable/disable</p>'
    )
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>RAPHAEL — Capability Arsenal</title>'
        f'<style>{dt._CSS}{_EXTRA_CSS}</style></head><body>'
        '<header class="cmdbar"><span class="brand">RAPHAEL</span>'
        '<span class="screen">Capability Arsenal</span>'
        '<span class="banner">GOVERNED OPS // SCOPE-LOCKED</span>'
        '<span class="spacer"></span>'
        f'<span class="cmeta mono">{data["counts"]["roles"]} ROLES</span>'
        f'<span class="cmeta mono">{data["counts"]["skills"]} SKILLS</span>'
        f'<span class="cmeta mono">{data["counts"]["capabilities"]} '
        'CAPABILITIES</span><span class="led ok"></span></header>'
        f'<main>{body}</main>'
        '<footer class="policystrip mono">POLICY: FAIL-CLOSED · MODE: '
        'GOVERNED · GATE: QUALITY</footer>'
        f'<script>{_JS}</script>'
        "</body></html>")


__all__ = ["KINDS", "collect", "render_arsenal"]
