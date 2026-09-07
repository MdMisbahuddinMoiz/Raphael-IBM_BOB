# Gap Analysis (R1.0 — detailed)

What must be created or changed to deliver the IBM BOB MVP from the current
`/home/moiz/raphael-2.0-rbsv2r` substrate. Backed by evidence from
`docs/migration/inventory.json`, `current-architecture.md`, and `reuse-matrix.md`.

## Critical gaps (no on-target module exists)

| Gap | Severity | Why it cannot reuse | Required artifact |
|---|---|---|---|
| Runtime seam (agent-facing, broker-mediated) | BLOCKER | No module on disk matches the brief's `Runtime`. `InteractiveShellCapability` (`src/orchestrator/capabilities/interactive_shell/capability.py:58`) is an abstract base for shell execution, not a broker-mediated agent-facing runtime. | `raphael/runtime.py` (NEW) — adapter exposing READ/LIST/SEARCH/WRITE/RUN_TEST through Broker |
| Replanner (evidence-causal) | BLOCKER | Closest: `GreedyPlanner` (`src/raphael/cognitive/planner.py:69`) selects by UCB1 utility, not by refutation. | `raphael/replanner.py` (NEW) |
| QualityGate (sole COMPLETE authority) | BLOCKER | No module bears this responsibility. `src/arena/conclusion.py` evaluates RBS arena runs, not mission-level COMPLETE. | `raphael/quality_gate.py` (NEW) |
| Append-only JSONL evidence ledger | HIGH | `Evidence` (`src/orchestrator/brain/evidence.py:55`) exists as in-memory graph; no JSONL writer. | `raphael/evidence_ledger.py` (NEW) |
| Finding lifecycle (UNVERIFIED → VERIFIED → REFUTED → SUPERSEDED) | HIGH | `Hypothesis` lifecycle is close but not the brief's finding lifecycle. | `raphael/finding.py` (NEW) |
| Focused Context builder | MEDIUM | `ContradictionManager` (`src/orchestrator/brain/contradiction.py:134`) has discriminator proposals; small reducer needed. | `raphael/focused_context.py` (NEW) |
| Authkit hero fixture | HIGH | None exists. | `fixtures/authkit/{store,session,login,test_login,test_auth}.py` |
| Independent behavior probe | HIGH | None exists. | `probes/auth_behavior_probe.py` |
| TEST-01..TEST-13 authoritative tests | BLOCKER | None exist under that naming. | `tests/test_01_*.py` … `tests/test_13_*.py` |
| Baseline (verification/falsification/replanning/quality_gate=false) | HIGH | None. | `demos/baseline.py` |
| Metrics generator + 5+ runs per mode | HIGH | `d6b_failed.jsonl` is RBS-specific, not MVP evidence ledger. | `scripts/audit_runs.py` + `metrics.json` |
| PROVENANCE.md / submission-checklist.md / demo-runbook.md / metrics-snapshot.json | MEDIUM | None exist. | `docs/PROVENANCE.md` + `docs/submission-checklist.md` + `docs/demo-runbook.md` + `docs/metrics-snapshot.json` |
| Python 3.12 + pytest toolchain | BLOCKER | System Python is 3.14.4; pip/pytest/uv absent. | Bootstrap Python 3.12 + pytest, or document 3.14 plan. |

## Adapt gaps (module exists, contract must change)

| Module | Required adaptation |
|---|---|
| `src/orchestrator/brain/capability_broker.py` | New policy grammar (developer-workflow capabilities, not offensive RoE). Preserve deny-by-default + ActionReceipt + reasons. |
| `src/orchestrator/brain/scope_parser.py` | Replace HackerOne-JSON parser with BOB mission-scope grammar. Keep fail-closed. |
| `src/orchestrator/brain/rate_limiter.py` | Re-key per-target-type dict to BOB scope types. Keep windows + jitter. |
| `src/orchestrator/brain/evidence.py` | Add append-only JSONL serialization (`Evidence.to_jsonl`, `EvidenceLedger.append`). Keep frozen dataclass. |
| `src/orchestrator/brain/contradiction.py` | Wire discriminator execution through the new Runtime. Replace offensive example hypotheses with developer-workflow ones. |
| `src/orchestrator/brain/hypothesis.py` | Add a `Finding` adapter: hypothesis → candidate finding → verified finding. Keep history preservation. |
| `src/orchestrator/brain/world.py` | Reduce entity vocabulary to MVP (file, function, test, capability-request). |
| `src/orchestrator/brain/action.py` | Replace offensive factories (`create_nmap_scan_action`, `create_exploit_action`, …) with MVP factories. Keep `Action.check_preconditions`. |
| `src/orchestrator/brain/strategy.py` / `strategy_learner.py` | Reduce to MVP strategy selection. |
| `src/raphael/verifier/core.py` | Replace canary channels with broker-mediated behavioral retest. Verify by reproduction. |
| `src/raphael/eventbus/core.py` | Replace Redis with in-process stream (zero-network MVP). Keep `trace_id` contextvar. |
| `src/raphael/blackboard/{schemas,contracts}.py` | Trim to MVP state contracts. |
| `src/agent/audit.py` | Rebind output to evidence ledger JSONL. |

## Isolate gaps (legacy/reference only — not in MVP seam)

- 112 `offensive-surface` modules under `src/orchestrator/{evasion,privesc,exfil,postex,pivot,propagation,weaponizer,ml_attack,cloud_abuse,c2,exploit,harvester,reversing,scanners,survivability,ttp_playbook,container_escape,cicd,social,spiderfoot_wrapper,phishing}/`.
- `src/orchestrator/student/` (LLM-bound research scheduler).
- `src/orchestrator/brain/{waf_detector,adaptive_brain,neural_memory,reflection,reasoning}.py` (network/LLM).
- `src/raphael/executor/`, `src/raphael/exploit_factory/`, `src/raphael/techniques/`, `src/raphael/limbic/parallel_recon.py`, `src/raphael/cognitive/{episodic_memory,protocol_inference,ontology_expander,self_modification,thermoregulator}.py`, `src/raphael/hippocampus/`, `src/raphael/memory/`, `src/raphael/scripts/`, `src/raphael/models/`, `src/raphael/cerebellum/`, `src/raphael/circulatory/`, `src/raphael/cortex/`.
- `src/agent/`, `src/agent/modules/`, `src/bridge/`, `src/c2-server/`, `src/cai-service/`, `src/cli/`, `src/cloak-service/`, `src/kali-tools/`, `src/mcp-hub/`, `src/mhddos-service/`, `src/phishing/`, `src/recon-pipeline/`, `src/sword/`, `src/forge/` (none under `forge/`), `src/arena/` (RBS), `Report_Raphael/`.

## Replace gaps

- `src/raphael/cognitive/planner.py:69 GreedyPlanner` — utility-driven, not refutation-driven. Replaced by new Replanner.
- All `tests/test_*.py` under `tests/` — RBS repair tests, not MVP test spine. Replaced by TEST-01..13 + repo-level regression.

## Open decisions for the developer (R1.1 input)

1. **Python toolchain.** Machine has only Python 3.14.4; brief prefers 3.12; pip/pytest/uv absent. Options:
   (a) bootstrap pip via `ensurepip`, install pytest, accept 3.14;
   (b) install Python 3.12 via deadsnakes/ppa or pyenv (not currently installed);
   (c) document 3.14 baseline and run pytest-on-3.14.
   *Awaiting developer decision before any environment change.*
2. **Scope of `REPLACE` for `GreedyPlanner`.** Delete or keep reachable as legacy? Default: keep reachable, do not call from MVP.
3. **Whether to add `CLAUDE.md` / `AGENTS.md` for OMP harness.** Default: not added.
4. **Whether to add a `release` strategy / `pyproject.toml` rename.** Default: keep `pyproject.toml` untouched, add new top-level `pyproject.mvp.toml` only if developer wants it.