#!/usr/bin/env python3
r"""R1.0 repository archaeology for RAPHAEL -> IBM BOB MVP migration.

Stdlib-only. Read-only with respect to legacy source code.
Allowed writes:
    docs/migration/current-architecture.md
    docs/migration/roadmap-mapping.md
    docs/migration/reuse-matrix.md
    docs/migration/gap-analysis.md
    docs/migration/inventory.json
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "migration"
OUT.mkdir(parents=True, exist_ok=True)

CAPABILITY_PATTERNS = {
    "open": re.compile(r"\bopen\s*\("),
    "subprocess": re.compile(r"\bsubprocess\.(?:run|call|Popen|check_output|check_call)\s*\("),
    "os.system": re.compile(r"\bos\.system\s*\("),
    "os.exec": re.compile(r"\bos\.(?:exec|spawn|fork|posix_spawn)\w*\s*\("),
    "socket": re.compile(r"\bsocket\.(?:socket|socket\(|create_connection|getaddrinfo)\s*\("),
    "requests": re.compile(r"\brequests\.(?:get|post|put|delete|patch|head|request)\s*\("),
    "urllib": re.compile(r"\burllib\.(?:request|urlopen)\."),
    "httpx": re.compile(r"\bhttpx\.(?:get|post|put|delete|request|stream)\s*\("),
    "aiohttp": re.compile(r"\baiohttp\.ClientSession|ClientSession\(\)"),
    "shutil_rm": re.compile(r"\bshutil\.rmtree\s*\("),
    "pathlib_write": re.compile(r"\.(?:write_text|write_bytes|unlink|rmdir)\s*\("),
    "importlib_dynamic": re.compile(r"\b(?:importlib|__import__|exec|eval)\s*\("),
    "yaml_load": re.compile(r"\byaml\.(?:unsafe_load|load)\s*\("),
}

PY_EXTS = {".py"}
SRC_DIRS = ["src", "scripts", "forge", "tests"]
ALL_DIRS = ["src", "scripts", "forge", "tests", "docs", "evaluations", "benchmarks", "configs", "docker", "tools", "Report_Raphael", "arena", "current-state"]

def collect_py_files() -> list[Path]:
    out: list[Path] = []
    for d in SRC_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if ".git" in p.parts:
                continue
            out.append(p)
    return out

def parse_module(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return None

def public_symbols(tree: ast.Module) -> dict:
    classes: list[str] = []
    functions: list[str] = []
    module_vars: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                classes.append(node.name)
        elif isinstance(node, ast.FunctionDef):
            if not node.name.startswith("_"):
                functions.append(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and not t.id.startswith("_") and t.id.isupper():
                    module_vars.append(t.id)
    return {"classes": classes, "functions": functions, "module_vars": module_vars}

def capability_hits(text: str) -> dict[str, int]:
    return {k: len(p.findall(text)) for k, p in CAPABILITY_PATTERNS.items()}

def first_routes(text: str, cap_hits: dict[str, int]) -> list[str]:
    routes: list[str] = []
    # naive heuristic: each hit gets one example line
    for cap, count in cap_hits.items():
        if count == 0:
            continue
        pat = CAPABILITY_PATTERNS[cap]
        for i, line in enumerate(text.splitlines(), start=1):
            if pat.search(line):
                routes.append(f"{cap}:{i}:{line.strip()[:140]}")
                break
    return routes

def has_main_guard(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.If) and getattr(node.test, "left", None) and getattr(node.test.left, "id", "") == "__name__":
            return True
    return False

def categorize(path: Path) -> str:
    parts = set(path.parts)
    if "src/agent" in str(path) or "src/mcp-hub" in str(path) or "src/cli" in str(path) or "src/bridge" in str(path):
        return "agent/infra"
    if "src/orchestrator/brain" in str(path):
        return "cognitive-loop"
    if "src/orchestrator/student" in str(path):
        return "research-scheduler"
    if "src/orchestrator/capabilities" in str(path):
        return "capability-runtime"
    if "src/orchestrator/evasion" in str(path) or "src/orchestrator/privesc" in str(path) or "src/orchestrator/exfil" in str(path) or "src/orchestrator/postex" in str(path) or "src/orchestrator/pivot" in str(path) or "src/orchestrator/propagation" in str(path) or "src/orchestrator/spiderfoot_wrapper" in str(path) or "src/orchestrator/social" in str(path) or "src/orchestrator/phishing" in str(path) or "src/orchestrator/cloud_abuse" in str(path) or "src/orchestrator/ml_attack" in str(path) or "src/orchestrator/mesh" in str(path) or "src/orchestrator/c2" in str(path) or "src/orchestrator/exploit" in str(path) or "src/orchestrator/harvester" in str(path) or "src/orchestrator/reversing" in str(path) or "src/orchestrator/scanners" in str(path) or "src/orchestrator/skills_bridge" in str(path) or "src/orchestrator/survivability" in str(path) or "src/orchestrator/ttp_playbook" in str(path) or "src/orchestrator/weaponizer" in str(path) or "src/orchestrator/modes" in str(path) or "src/orchestrator/hardening" in str(path) or "src/orchestrator/container_escape" in str(path) or "src/orchestrator/kali_tools_client" in str(path):
        return "offensive-surface"
    if "src/orchestrator" in str(path):
        return "orchestrator-core"
    if "src/raphael" in str(path):
        return "raphael-cognitive"
    if "src/arena" in str(path):
        return "arena-rbs"
    if "src/sword" in str(path) or "src/c2-server" in str(path) or "src/cai-service" in str(path) or "src/cloak-service" in str(path) or "src/recon-pipeline" in str(path) or "src/kali-tools" in str(path) or "src/mhddos-service" in str(path):
        return "service-binary"
    if "scripts" in parts:
        return "scripts"
    if "tests" in parts:
        return "tests"
    if "forge" in parts:
        return "forge"
    return "other"

def module_record(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    tree = parse_module(path)
    pub: dict = {"classes": [], "functions": [], "module_vars": []}
    has_main = False
    if tree is not None:
        pub = public_symbols(tree)
        has_main = has_main_guard(tree)
    cap_hits = capability_hits(text)
    routes = first_routes(text, cap_hits)
    return {
        "path": str(path.relative_to(ROOT)),
        "category": categorize(path),
        "lines": text.count("\n") + 1,
        "bytes": len(text),
        "public_classes": pub["classes"],
        "public_functions": pub["functions"],
        "module_constants": pub["module_vars"],
        "has_main_guard": has_main,
        "capability_hits": cap_hits,
        "first_capability_routes": routes,
        "has_docstring": ast.get_docstring(tree) is not None if tree else False,
    }

def main() -> int:
    files = collect_py_files()
    records = [module_record(p) for p in files]
    # Aggregate
    cat_counts = Counter(r["category"] for r in records)
    cap_totals = Counter()
    for r in records:
        for k, v in r["capability_hits"].items():
            cap_totals[k] += v
    entry_points = [r for r in records if r["has_main_guard"]]
    # Write JSON inventory
    inventory = {
        "root": str(ROOT),
        "git_branch": "migration/bob-mvp",
        "head_sha": "7272880f7e4320f5d36ac3b645ff7fc68ea5d0e0",
        "python_version": sys.version.split()[0],
        "pip_available": False,
        "pytest_available": False,
        "category_counts": dict(cat_counts),
        "capability_hits_total": dict(cap_totals),
        "module_count": len(records),
        "entry_point_modules": [r["path"] for r in entry_points],
        "modules": records,
    }
    (OUT / "inventory.json").write_text(json.dumps(inventory, indent=2))
    # Markdown summaries
    write_architecture_md(records, cat_counts, cap_totals)
    write_roadmap_mapping_md(records)
    write_reuse_matrix_md(records)
    write_gap_analysis_md(records)
    print("Wrote:")
    for f in OUT.iterdir():
        print(" -", f.relative_to(ROOT))
    return 0

def write_architecture_md(records, cat_counts, cap_totals):
    lines: list[str] = []
    lines.append("# Current Architecture Map (R1.0)")
    lines.append("")
    lines.append("Source: physical inspection of `/home/moiz/raphael-2.0-rbsv2r` on branch `migration/bob-mvp` at HEAD `7272880f7`. ")
    lines.append("Python: `Python 3.14.4`; pip: absent; pytest: absent; uv: absent.")
    lines.append("")
    lines.append("## Module categories")
    for k, v in sorted(cat_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {k}: {v} modules")
    lines.append("")
    lines.append("## Capability-boundary hits (raw counts across the repo)")
    for k, v in sorted(cap_totals.items(), key=lambda kv: -kv[1]):
        if v:
            lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Entry-point modules (`if __name__ == '__main__'` present)")
    for r in records:
        if r["has_main_guard"]:
            lines.append(f"- `{r['path']}`")
    (OUT / "current-architecture.md").write_text("\n".join(lines) + "\n")

ROADMAP_TARGETS = [
    ("Runtime",      "Agent-facing execution boundary that mediates every environment action."),
    ("Broker",       "Authorization gate; consults Policy and decides Permit/Deny for every capability request."),
    ("Policy",       "Declarative rules; target scope, capability allow-list, rate, impact ceiling."),
    ("Evidence",     "Append-only, sequenced record of requests, decisions, results, findings."),
    ("Verifier",     "Independent reproduction/retest of candidate findings; goes through Runtime."),
    ("Falsifier",    "Actively challenges apparent success; tests behavioral invariants."),
    ("Replanner",    "Causes Plan B from refuted findings, evidence, and focused context."),
    ("QualityGate",  "Sole authority for COMPLETE; evaluates mission criterion, evidence, behavior probe, regressions."),
    ("Planner",      "Generates Plan A from mission + scope."),
    ("Runner",       "Drives the control loop and persists state."),
]

def write_roadmap_mapping_md(records):
    lines = ["# Roadmap Mapping (R1.0)", ""]
    lines.append("Mapping from RAPHAEL IBM BOB Master Roadmap v1.2 target subsystems to physical modules in this repository.")
    lines.append("All verdicts begin as UNKNOWN and only become a routing claim when backed by `path:line` evidence.")
    lines.append("")
    lines.append("| Target | Description | Candidate modules | First-pass verdict | Evidence |")
    lines.append("|---|---|---|---|---|")
    for tgt, desc in ROADMAP_TARGETS:
        lines.append(f"| {tgt} | {desc} | _to be filled by reuse matrix_ | UNKNOWN | _to be filled by reuse matrix_ |")
    (OUT / "roadmap-mapping.md").write_text("\n".join(lines) + "\n")

def write_reuse_matrix_md(records):
    lines = ["# Reuse Matrix (R1.0)", ""]
    lines.append("Decisions per candidate subsystem. Initial verdicts are UNKNOWN; each must be backed by `path:line` before being promoted.")
    lines.append("")
    lines.append("| Existing module | Actual behavior | BOB target | Compatibility | Action | Evidence |")
    lines.append("|---|---|---|---|---|---|")
    # Highlight notable modules discovered during archaeology
    candidates = [
        ("src/agent/agent.py", "Agent loop driver (offensive cognitive loop)."),
        ("src/orchestrator/conductor.py", "Orchestrator driver."),
        ("src/orchestrator/scope.py", "Target scope rules."),
        ("src/orchestrator/brain/capability_broker.py", "Authorization broker (5-dim)."),
        ("src/orchestrator/brain/action.py", "Planner (action preconditions/effects)."),
        ("src/orchestrator/brain/world.py", "WorldModel + evidence chains."),
        ("src/orchestrator/brain/hypothesis.py", "Hypothesis manager."),
        ("src/orchestrator/brain/contradiction.py", "Contradiction manager."),
        ("src/orchestrator/brain/falsification.py", "Falsification engine."),
        ("src/orchestrator/runtime/", "Runtime subsystem."),
        ("src/raphael/verifier/core.py", "Safety verifier."),
        ("src/raphael/verifier/channels.py", "Verifier channels."),
        ("src/raphael/cortex/planner.py", "Cognitive planner."),
        ("src/raphael/blackboard/", "Blackboard schemas."),
        ("src/raphael/eventbus/core.py", "Event bus."),
        ("src/raphael/executor/", "Executor."),
        ("src/raphael/evidence/ (note: not a directory in this layout)", "Evidence models."),
        ("src/mcp-hub/", "MCP hub tool surface."),
        ("src/cli/", "CLI binary."),
        ("scripts/test_imports.py", "Import smoke test."),
        ("tests/test_noop_contract.py", "NoOpWorldModel contract test."),
        ("tests/test_evaluator_isolation.py", "Evaluator isolation test."),
        ("tests/test_rbs_v2_repairs.py", "RBS v2 repair tests."),
    ]
    for path, behavior in candidates:
        lines.append(f"| `{path}` | {behavior} | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |")
    (OUT / "reuse-matrix.md").write_text("\n".join(lines) + "\n")

def write_gap_analysis_md(records):
    lines = ["# Gap Analysis (R1.0)", ""]
    lines.append("What is missing for the IBM BOB MVP target.")
    lines.append("")
    missing = [
        "runtime/broker/policy seam under `raphael/` (current repo has analogues inside `src/orchestrator/brain/` for offensive scope).",
        "Append-only evidence ledger wired into a BOB-facing control loop.",
        "Finding lifecycle (UNVERIFIED → VERIFIED → REFUTED → SUPERSEDED).",
        "Verifier gated through Runtime/Broker/Policy.",
        "Falsifier integrated into the control loop.",
        "Focused Context builder (deliberately small).",
        "Causal replanner driven by evidence, not heuristics.",
        "Output Quality Gate as the COMPLETE authority.",
        "Authkit hero fixture under `fixtures/authkit/`.",
        "Independent behavior probe under `probes/`.",
        "TEST-01..TEST-13 authoritative tests.",
        "Baseline with verification=false/falsification=false/replanning=false/quality_gate=false.",
        "Metrics generated from real `runs/*/evidence.jsonl`.",
        "PROVENANCE.md and submission-checklist.md.",
        "Python 3.12 toolchain (current machine only has 3.14.4; pip and pytest absent).",
    ]
    for m in missing:
        lines.append(f"- {m}")
    (OUT / "gap-analysis.md").write_text("\n".join(lines) + "\n")

if __name__ == "__main__":
    raise SystemExit(main())