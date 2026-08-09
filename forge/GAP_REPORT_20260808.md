# GAP REPORT — RAPHAEL v2.1.1 → v3 READINESS — 2026-08-08

**Producer**: FORGE · **Source evidence**: `forge/AUDIT_REPORT_20260808.md` + raw telemetry (pytest_failures.txt, dev_runs raw JSONL, experiment JSONs).
**Audience**: SENTINEL (governance) + THE STUDENT (S-Series — full-control research assignment, see §6).

---

## 1. GAP LEDGER (SEVERITY-ORDERED)

| ID | Severity | Gap | Evidence | Recommended disposition |
|---|---|---|---|---|
| G-01 | **CRITICAL** | JSONL telemetry append contamination — re-running same run_id duplicates composite keys with divergent content | dev_runs/raw/abl_PROMPTED_AGENT_arena-d6-013_s1357447574_dev (9 lines, 2 session clusters, dup seq 0..3), episode.py:145/198 append mode | Fix recorder idempotency (truncate+run-id stamp OR reject-on-exists) |
| G-02 | **CRITICAL** | 59 failing untracked repair tests (12 files) — test-first spec suite referencing src/ features never implemented (RunMetrics.actions_dispatched/iterations_used/safety_telemetry_ok, RawResponse.input_tokens, RawObservation(is_tool_failure), LLMService.call_count, NoOpWorldModel.get_entity...) | forge/pytest_failures.txt (59 FAILED, 180 passed) | Decide: implement in v3 w/ tests, or retire with xfail+governance note; refresh README claim |
| G-03 | **HIGH** | 10 tools referenced but MISSING in kali-tools image (netexec 79 refs!, searchsploit 23, wpscan, sslscan, subfinder, amass, dnsx, crackmapexec/nxc) — direct-call paths will fail at runtime | audit11/12 (container exec), mcp-hub/decision_engine etc. | Rebuild image or add wrapper that maps missing→available=False and routes to apt alternatives; verify every direct caller |
| G-04 | **HIGH** | Implant (src/agent) not exercised end-to-end in any arena campaign — crypto/evasion/cleanup modules importable + unit-verified crypto but zero integration evidence | sweep_imports, verify_crypto_inverse (all pass), no agent runtime telemetry in evaluations/ | v3 plan: agent-in-sandbox integration campaign (dedicated target container) |
| G-05 | **HIGH** | `redis`/`fakeredis` omitted from consolidated requirements.txt (only in configs/requirements.txt) — venv installs fail on eventbus/vhost_enum until repaired | sweep imports (eventbus→redis) | Add to consolidated requirements (file-level fix) |
| G-06 | **MEDIUM** | `configs/` (plural) vs `config` (singular) import mismatch — 4 modules broken in both host & sword container | orchestrator/config/*.py, mcp-hub/core/server.py:13 `from config.paths import *` | Alias package or rename; container build fix |
| G-07 | **MEDIUM** | validate_env.py contract stale vs new NVIDIA-only .env (TOR_CONTROL_PASS/API_KEY/NEO4J_PASS required but absent by design) | validate_env run: 3 errors | Update validate_env to tiered contract (NVIDIA keys primary) |
| G-08 | **MEDIUM** | Exp1 scripted baseline is a hard-coded constant (0.45/15/3) — not measured; violates protocol 'measured' requirement | run_experiment1.py:53 | Implement empirical scripted baseline run loop |
| G-09 | **MEDIUM** | Experiment 3 no gradient (1.0/1.0/1.0) — D6 templates saturate; no difficulty discrimination | exp3_results.json | Add Level-2/3 templates w/ auth/RBAC+multi-stage (or increase template difficulty knobs) |
| G-10 | **LOW** | scripts/smoke_test.py documented but missing; test_imports.py unusable as written (no src on path) | README.md:96, test_imports.py:2 | Restore smoke_test; fix test_imports |
| G-11 | **LOW** | README "121/121" stale (127 tracked now; 239 collected; 180 green w/ untracked) | README.md:5,197; pytest run | Refresh status block |
| G-12 | **LOW** | `arena.d1x_*` diagnostic runners import `scripts/d6c_holdout_runner` (cwd-dependent) — packaging hygiene | sweep (10 modules) | Move d6c_holdout_runner into src/arena (as its own module) or sys.path bootstrap in each |

## 1. RULE-4 CRYPTO — clean (no gaps)

## 2. RULE-2 IMPORT MAP — residual list (20 structural):
- dash-packages (mcp-hub, c2-server, cai-service, cloak-service, mhddos-service, recon-pipeline) — service-local by design; document
- config.* alias (G-06); redis (G-05); d6c_holdout_runner (G-12); phishing.main (PermissionError /app) — container-only entrypoint.

## 3. RULE-3 SUBPROCESS — G-03 table already emitted above.

## 4. EXPERIMENTS STATUS (Post-audit measured artifact)

| Exp | Result | Artifact |
|---|---|---|
| E0 Repeatability | deterministic, std=0 both arms | evaluations/Phase0/experiment0_20260808_152741.json |
| E1 Architecture | 1.0 / 1.0 / 0.45(constant) | evaluations/architecture/exp1_results.json |
| E2 Ablation | FULL 0.9; NO_PLANNER 0.3 (biggest drop) | evaluations/ablation/exp2_results.json |
| E3 Difficulty | 1.0 all levels (saturating) | evaluations/difficulty/exp3_results.json |

## 5. STRIKE-LEDGER STATUS
- Strikes: 0/3. All audit writes confined to forge/ (scripts+docs+venv); NO src/ modification during this audit. One pre-existing uncommitted src/ change (ablation_runner.py EPIPE wrapper) predates audit (git status M).

## 6. STUDENT RESEARCH MANDATE (handoff in §Phase 9)
Open research questions the Student must address with full control:
1. **G-02**: Design the v3 metrics contract (RunMetrics v2: actions_dispatched, iterations_used, budget ceilings, safety telemetry) — propose exact field set + data classes, or argue for test retirement.
2. **G-01**: Propose idempotent telemetry schema (run manifest + snapshot dedup + schema_version) incl. migration for existing contaminated runs.
3. **G-03**: Container tool gap strategy: image rebuild vs. in-raphael soft-fail routing; propose binary coverage manifest + auto-check in smoke.
4. **G-04**: Agent-in-sandbox E2E design (dedicated container, legal scope) — phases, targets, metrics.
5. **G-08/G-09**: Empirical scripted baseline + difficulty template upgrades.
6. v3 architecture proposal — drawn from the audited reality, not doc-reality; file in evaluations/campaign/ v3 proposals per protocol.

— FORGE, 2026-08-08 UTC. Restraint: no src/ mutation; minimal script repairs only (run_experiment1-3 path juggling + venv).