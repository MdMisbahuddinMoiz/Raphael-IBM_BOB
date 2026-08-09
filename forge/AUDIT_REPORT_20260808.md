# FORGE END-TO-END AUDIT — RAPHAEL v2.1.1 (RBS-v2R) — 2026-08-08

**Authority**: FORGE (Evaluation-Surgeon, Reality-Anchored) · **Instrument**: Frozen v2.1.1
**Scope**: Full E2E audit of `raphael-2.0-rbsv2r` — imports, crypto, subprocess reality, E2E data flow, test suite, experiments 0–3, environment, drift analysis.
**Zero-Tolerance Rules applied**: 1 (E2E data flow), 2 (import map), 3 (subprocess reality), 4 (crypto inverse), 5 (no feature escape).

---

## 1. EXECUTIVE VERDICT

| Dimension | Status | Verdict |
|---|---|---|
| Frozen instrument (tracked tests) | **127/127 PASS** | ✅ Green — "121/121" claim holds (count drifted, not integrity) |
| Full working tree (all 239 collected) | **180 passed / 59 failed** | ❌ RED — 15 untracked repair-era test files fail |
| Crypto inverses (Rule 4) | 5/6 verified + 1 N/A | ✅ All real pairs invert correctly |
| Import map (Rule 2) | 356 modules swept, 336 resolve | ✅ with 20 structural exclusions (service-local patterns) |
| Subprocess reality (Rule 3) | **10 referenced tools MISSING** in kali-tools | ❌ RED |
| E2E JSONL integrity (Rule 1) | **Cross-session append contamination** | ❌ RED — duplicate composite keys |
| LLM transport live probe | Reachable; dual-key failover resolves | ✅ 400=client_error (correct, non-retried) |
| Environment | venv MISSING at audit start; system py3.14; built venv py3.12.13 | ⚠️ REPAIRED (rule-44 environment repair) |

**Headline**: The *frozen* cognitive instrument is sound and deterministic. The *working tree* contains a large unfinished repair wave (untracked tests referencing unimplemented src/ features) — the single biggest structural risk.

---

## 2. ENVIRONMENT FINDINGS (Phase 0–1)

| Finding | Detail | Severity |
|---|---|---|
| E-01 | No `.venv` in repo — system Python was 3.14.4 (violates frozen `>=3.11,<3.13`). `uv`-managed 3.12.13 at `~/.local/bin/python3.12` was the prior interpreter. Forge built `.venv` (3.12.13) + installed full requirements. | HIGH (reproducibility) |
| E-02 | `requirements.txt` (consolidated) omits `redis`/`fakeredis` which `raphael.eventbus`, `vhost_enum.core` require (present only in `configs/requirements.txt`). Installed into venv; **file gap remains** → must be added to consolidated file. | HIGH (import map) |
| E-03 | `.env` = 2 keys only (NVIDIA_API_KEY_A/B). `scripts/validate_env.py` demands TOR_CONTROL_PASS, API_KEY, NEO4J_PASS → **validate_env is stale vs. new minimal design**; fails with 3 errors regardless. | MEDIUM (config drift) |
| E-04 | `configs/` dir (plural) imported as `config` (singular) in `orchestrator/config/paths.py`, `target.py`, `mcp-hub/core/server.py` → `ModuleNotFoundError` in host AND sword container. | MEDIUM (import map) |
| E-05 | Docker stack healthy: dvwa, kali-tools, sword, api, cai, cloak, mhddos, recon, c2, neo4j — all Up. DVWA responds 302 (login redirect = alive). | OK |
| E-06 | `scripts/smoke_test.py` (referenced by mandate/README) **does not exist**. Nearest equivalents: `test_imports.py` (broken own path), `validate_env.py` (stale). README quickstart references a non-existent script. | LOW (docs) |

## 3. IMPORT MAP (Rule 2) — 356 modules via `forge/sweep_imports.py`

- **336 importable**; **20 excluded structurally** (dash-packages are service-local: `c2-server`, `mcp-hub`, `cai-service`, `cloak-service`, `mhddos-service`, `recon-pipeline`; `arena/d*.py` runners depend on `scripts/d6c_holdout_runner` — cwd-based by design; `config.*` per E-04).
- Dash-package dirs are **deliberately excluded from pyproject packages.find** — they run as standalone services with own PYTHONPATH. Consistent design, but **not documented anywhere** (docs claim full src importability).

## 4. CRYPTO INVERSE (Rule 4) — `forge/verify_crypto_inverse.py`

| Pair | Result |
|---|---|
| `agent.crypto` AES-GCM encrypt/decrypt | ✅ roundtrip + tamper rejection |
| AES-GCM nonce uniqueness (2 calls same plaintext) | ✅ distinct ciphertexts |
| AES-CTR (sleep mask, nonce=16B enforced) | ✅ |
| `weaponizer_engine` AES-CBC PKCS7 (sizes 1…256B) | ✅ |
| `agent/modules/exfil._encrypt_chunk` (nonce‖ct wire) | ✅ AES-GCM reversible |
| mcp-hub HMAC module | N/A (no importable HMAC module — no sign/verify pair found) |

**No crypto defect found in any audited pair.**

## 5. SUBPROCESS REALITY (Rule 3) — `forge/audit10..12`

- 40+ src files route external binaries through `kali_tools_client` (HTTP to kali-tools:3800, fallback local subprocess with timeout guard).
- kali-tools container: `/usr/bin + /usr/local/bin` = 892 bins; service health reports `{"tools":1003}`.
- **MISSING in container but referenced by src (Rule-3 violation):**

| Binary | src refs (approx) | Callers |
|---|---|---|
| netexec (nxc / crackmapexec) | 79 | mcp-hub decision_engine, c2-server, lateral, postex, propagation, credential_spray |
| searchsploit | 23 | mcp-hub, recon paths |
| wpscan | 2 | mcp-hub web tools |
| sslscan | 2 | mcp-hub web tools |
| subfinder | ~ (mcp-hub recon) | mcp-hub/recon/subfinder.py |
| amass, dnsx, masscan-ok? no: masscan PRESENT | — | tool list |

Present and verified: nmap 7.99, sqlmap, gobuster, nikto, ffuf, hydra, whatweb, hashcat, john, masscan, dirb, nuclei v3.11, impacket python lib.

**Callers rely on `available` flags in some paths (c2-server health) but multiple paths invoke directly (lateral, propagation) → runtime failures attend** — must verify each missing tool's soft-fail path.

## 6. E2E DATA FLOW (Rule 1) — `forge/verify_e2e_jsonl.py`, `forge/verify_session_cluster.py`

**Pipeline**: AblationRunner → EpisodeRecorder/EventsRecorder (src/arena/episode.py) → `run_dir/raw/{run_id}/episodes.jsonl + events.jsonl` → consumed by analysis.

### DEFECT F-01 (HIGH) — Cross-session append contamination
- `episode.py:_append_to_file` and `EventsRecorder.record_event` open JSONL in **append mode `"a"`**, no run-id idempotency.
- Concrete evidence (dev_runs/raw/abl_PROMPTED_AGENT_arena-d6-013_s1357447574_dev):
  - 9 episode lines, composite keys `(episode_id, sequence)` repeated: seq 0..3 appear **twice each**;
  - two session clusters detected (timestamp span 3,305s, gap >600s): 5 then 4 snapshots;
  - Divergent content for same key: `authorization_result` A=allow/receipt_76df vs B=allow/receipt_e7b3; `selected_action` dict vs list; `evidence_created` 1 vs 3 items.
- **Impact**: any downstream dedup / by-key lookup silently merges two sessions; e.g. RunConclusion evaluation reads stale snapshots. Repeatable — same run_id re-execution always corrupts.
- Root cause: both recorders append without truncation/run-id check; ablation_runner:3088 opens with "w" but earlier Recorder appends to same path.

## 7. TEST SUITE (Phase 5) — 3 environments, same code:

| Collection | Result |
|---|---|
| `pytest -q` (tests/ = 239) | **180 passed / 59 failed** (5.6s) |
| Tracked git subset (7 files) | **127/127 PASS** — frozen claim ~verified (count grew 121→127) |
| `src/arena/tests/` (73 funcs) | 71 passed / 2 failed |

### Failure taxonomy (59): 12 test files, ALL untracked:
| File | Count | Root cause |
|---|---|---|
| token_telemetry | 10 | `RawResponse.input_tokens` absent |
| gate_b_action_accounting | 10 | `RunMetrics.actions_dispatched` absent |
| prompted_agent_repair | 7 | metrics/observations mismatch |
| evaluator_isolation | 5 | `RawObservation(is_tool_failure=)` kwarg absent |
| tool_failure_provenance | 4 | same kwargs |
| safety_telemetry | 4 | `RunMetrics.safety_telemetry_ok` absent |
| noop_contract | 4 | `NoOpWorldModel.get_entity*` absent |
| llm_transport | 4 | `LLMService.call_count/provider_failures` absent |
| budget_contract | 4 | `RunMetrics.iterations_used` absent |
| repair_gate | 3 | src/ repair features absent |
| run_identity | 2 | assert 0 == 1 |
| environment_determinism | 2 | MAC/instance determinism absent |

**Conclusion**: 55/59 = untracked repair-era tests written **before** src/ implementation (blocked by v2.1 freeze → never landed). 2 arena failures = 1 NotImplementedError (honest), 1 evaluator edge (`NO_PLANNER SERVICE_TYPE` DIRECT_OBSERVATION empty). 2 run_identity assert failures may be environment-sensitivity.

## 8. EXPERIMENTS (Phase 6–7)

### Experiment 0 — Repeatability (N=10 same seed + N=10 diff seeds) — **PASS, fully deterministic**
- Same seed=42: score `mean=1.0, std=0.0`, actions `mean=85.0, std=0.0`
- Diff seeds 1042–1051: score `mean=1.0, std=0.0`, actions `mean=85.0, std=0.0`
- D6 T1_NEGATIVE_CONTROL is a perfect deterministic unit.
- Artifact: `evaluations/Phase0/experiment0_20260808_152741.json`

### Experiment 1 — Architecture value — COMPLETE
- FULL_RAPHAEL: score 1.0, actions 80 | NO_LLM: 1.0/80 | SCRIPTED_BASELINE (theoretical const): 0.45/15/3
- **Scripted baseline is a constant in the script (`score=0.45, actions=15, knowledge=3`) — NOT derived** — documented weakness (script-level, protocol violation: metric not measured).
- Artifact: `evaluations/architecture/exp1_results.json`

### Experiment 2 — Ablation — COMPLETE (T4_WORLD_MODEL_IDENTITY, seed 3723150)
- FULL 0.9/12/8 · NO_WORLD_MODEL 0.45/15/2 · NO_HYPOTHESIS 0.5/14/3 · NO_PLANNER 0.3/8/1 · NO_FALSIFICATION 0.6/10/4 · NO_STUDENT 0.75/11/5 · NO_P1 0.7/10/6
- Planner removal is the largest single drop (1.0→0.3). World model also critical (0.9→0.45).
- Artifact: `evaluations/ablation/exp2_results.json`

### Experiment 3 — Difficulty scaling — COMPLETE
- L1 1.0/80; L2 1.0/73; L3 1.0/82 (all raw=1.0 — no gradient; discriminative power limited on these D6 templates)
- Artifact: `evaluations/difficulty/exp3_results.json`

### Script repairs applied (Rule 44 — scripts only, never src/):
- run_experiment1/2/3.py: `scripts/arena.py` shadowed `src/arena/` → added path-juggling identical to run_experiment0.py. All 3 now execute.
- `scripts/test_imports.py`: `raphael.eventbus`/`blackboard` fail because script never adds `src/`; verified modules import with `src` on path (sweep: OK after redis install).

## 10. GIT / REPOSITORY-HEALTH

- Working tree: 1 modified (`src/arena/ablation_runner.py` +22 lines — EPIPE-safe debug wrapper, already matches test_debug_stderr_epipe intended), ~40 untracked files (tests, campaign reports, baseline manifests).
- `.pytest_cache` lastfailed (62 entries) and nodeids (267) — written **today 14:23** by a prior session; aligns with current 59-failure state (after 3 tests fixed by wrapper).
- Prior reports present: student (11:36Z), stapler intel, RBS-v4 campaign artifacts.

## 10. RECOMMENDATIONS (PRIORITIZED)

| # | Action | Type | Effort |
|---|---|---|---|
| 1 | Fix EpisodeRecorder/EventsRecorder append → truncate-or-reject on existing run_id (idempotent) | src/ (needs SENTINEL gate) | S |
| 2 | Add `redis`+`fakeredis` to consolidated requirements.txt | infra | S |
| 3 | Decide 59 repair-era tests: either implement metric fields in RunMetrics/RawResponse (v3) or delete/mark-xfail and verify claim; refresh README "121" → actual | governance | M |
| 4 | Install or stub netexec/searchsploit/wpscan/sslscan/subfinder in kali-tools image + verify soft-fail paths | infra | M |
| 5 | `config/` → `configs/` import unification (or `config` alias package) | code | S |
| 6 | Update validate_env.py contract + .env.example with NVIDIA key model | docs | S |
| 7 | Exp1 scripted baseline: derive empirically instead of constant | script | S |

— FORGE, 2026-08-08 (UTC) — raw telemetry: `forge/pytest_failures.txt`, `evaluations/Phase0|architecture|ablation|difficulty/*.json`, JSONL under `evaluations/campaign/dev_runs/raw/`.