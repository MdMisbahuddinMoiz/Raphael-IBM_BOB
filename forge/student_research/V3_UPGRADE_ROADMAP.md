# RAPHAEL v3 UPGRADE ROADMAP — STUDENT SYNTHESIS

**Author**: THE STUDENT (S-Series) · **Basis**: FORGE audit (G-01…G-12) + 20-paper arXiv corpus (2026-08-08) · **Authority**: Full control per SENTINEL directive
**Status**: v2.1.1 frozen → v3 design proposals (src/ changes require SENTINEL seal)

---

## 1. STRATEGIC THEMES FROM RESEARCH CORPUS

| Theme | Papers | Key Takeaways for Raphael Upgrade |
|---|---|---|
| **LLM/Agent Security** (12/20) | ARIA backdoors, DreamGuard, AMS scanner, ChainClaw, MCP keystore | **Threat model shift**: agent instruction backdoors, activation-space tampering, on-chain agent workflows. Raphael needs: guardrail layer (DreamGuard), activation introspection (AMS), MCP enforcement (Hw keystore). |
| **Formal Methods** (16/20) | HOPSCOTCH (Lean), Tamarin→ProVerif, dfence type system | **Verification upgrade**: mechanize Raphael's falsification engine in Lean/ProVerif; add speculation-barrier type system for implant (dfence); game-hopping for crypto protocol guarantees. |
| **Cryptography** (16/20) | GCM zero-nonce attack, quantum OWFs, HOPSCOTCH proofs | **Crypto hygiene**: audit nonce lengths (GCM zero-length nonce is exploitable); migrate to quantum-resistant primitives where feasible; formalize dual-key NVIDIA transport as game-based proof. |
| **Fuzzing/Directed Testing** (12/20) | RustGo, Rust-directed greybox, algebraic hard-label attacks | **Fuzzing integration**: add RustGo-style directed fuzzer for implant binaries; algebraic extraction for model parameters; greybox fuzzing harness for capability binaries. |
| **Network/ICS** (19/20) | GPML water-network detection, REN traffic forecasting | **Topology-aware recon**: GPML spectral analysis for ICS/OT networks; forecasting baselines for anomaly detection (PatchTST/GRU-LSTM). |
| **Hardware/Spectre** (8/20) | dfence instruction, SLH generalization, Jasmin type system | **Implant hardening**: integrate dfence-equivalent speculation barriers; Jasmin-verified crypto primitives in implant. |

---

## 2. GAP-DRIVEN ROADMAP (Phased)

### PHASE 0 — STABILIZE (Week 1–2) *[FORGE-doable, no SENTINEL]*

| ID | Action | Owner | Artifact |
|---|---|---|---|
| G-01 | **Telemetry Idempotency Fix**: `forge/student_fixes/telemetry_migrate.py` — detects contaminated runs, splits by session cluster, stamps `_r2`, verifies composite-key uniqueness. Run on all `evaluations/campaign/dev_runs/raw/*`. | Student | `forge/student_fixes/telemetry_migration_20260808.log` |
| G-05 | Add `redis>=5.0.0\nfakeredis>=2.0.0` to root `requirements.txt` (consolidated) | Student | `requirements.txt` diff |
| G-07 | Update `scripts/validate_env.py` → tiered contract: NVIDIA dual-key primary (exit 0 if present), legacy TOR/API/NEO4J optional (warning only). Run green on current `.env`. | Student | `scripts/validate_env.py` + green run log |
| G-09 | Write `scripts/experiment3b_difficulty.py` with empirical SCRIPTED_BASELINE (loop over `ABLATION_PRESETS["SCRIPTED_BASELINE"]`) and upgrade templates to T5/T6 with auth/RBAC knobs. | Student | `evaluations/difficulty/exp3b_results.json` |
| G-10 | Restore `scripts/smoke_test.py` (imports + DVWA curl + kali-tools health + LLM probe) + fix `test_imports.py` (add src/). | Student | `scripts/smoke_test.py`, `scripts/test_imports.py` |

### PHASE 1 — INSTRUMENTATION (Week 3–4) *[SENTINEL for src/ changes]*

| ID | Proposal | Research Backing |
|---|---|---|
| **G-02a: RunMetrics v2** | Add `actions_dispatched`, `iterations_used`, `budget_iteration_ceiling`, `budget_action_ceiling`, `safety_telemetry_ok`, `provider_failures`, `logical_llm_calls`, `failover_count`, `final_key_alias` — exact fields from REPAIR-VAL-02 telemetry spec. | Audit gap + RBS-v4 protocol; ARIA/DreamGuard need structured telemetry |
| **G-02b: RawResponse v2** | `input_tokens`, `output_tokens`, `model_id`, `provider_status`, `failure_class` — for token telemetry tests + NVIDIA failover observability. | test_token_telemetry.py spec; NVIDIA transport already emits these |
| **G-02c: NoOpWorldModel** | Implement `get_entity`, `get_entities_by_type` as no-op stubs (return empty) — satisfies test_noop_contract without full world model. | test_noop_contract.py; chain-synthesis needs NoOp fallback |
| **G-02d: RawObservation** | Add `is_tool_failure: bool` kwarg + `trust_level: TrustLevel` field for tool_failure_provenance pipeline. | test_tool_failure_provenance.py; DreamGuard risk-aware classification |
| **G-02e: LLMService** | Add `call_count`, `provider_failures`, `logical_llm_calls` counters — integrates with REPAIR-VAL-01 telemetry. | NVIDIA dual-key transport already produces these |

### PHASE 2 — ARCHITECTURE UPGRADES (Week 5–8) *[SENTINEL]*

| # | Upgrade | Research Driver | Spec Sketch |
|---|---|---|---|
| **U-01** | **Guardrail Layer (DreamGuard-inspired)** | 2608.05695: risk-aware world model + hazard-step detection | New module `orchestrator/guardrail/dreamguard.py`: recurrent latent dynamics + immediate-hazard + prefix-risk supervision; plugs into CapabilityBroker as pre-authorization filter (ESCALATE path). |
| **U-02** | **Activation Scanner (AMS-inspired)** | 2608.05578: geometric structure of safety concepts in activation space | `src/agent/modules/ams_scanner.py`: runs on LLM responses, measures σ (activation spread) + compliance; alerts on safety-training tampering. Integrates with `llm_transport` post-inference. |
| **U-03** | **MCP Hardware Keystore** | 2608.06130: Hw keystore for agent signing, CVE-2026-25253 | `src/agent/modules/mcp_keystore.py`: opaque handles + hardware attestation (TPM/HSM); signs every broker receipt; stores NVIDIA keys in HSM not env. |
| **U-04** | **Agentic Posture Vulnerability (APV) Registry** | 2608.05884: task-conditioned vuln mgmt abstraction | `src/orchestrator/apv_registry.py`: durable records for composed agent-control exposures; evidence chains; authority delegation audit trail. Feeds Student `knowledge_background_service`. |
| **U-05** | **ChainClaw Event-Driven Orchestration** | 2608.05790: Reactivity/Irreversibility/Composability gaps | Extend `AdaptiveBrain` with event-driven layer (on-chain events, async triggers); simulation-based safety intelligence (pre-execution what-if); cross-layer memory subsystem. |
| **U-06** | **GPML Topology-Aware Recon** | 2608.05902: spectral graph analysis for ICS/OT | `src/raphael/techniques/gpml_recon.py`: spectral time-windowing + IP-Port graphs + eigenvalue-band anomaly detection for water/REN/SCADA nets. |
| **U-07** | **Directed Fuzzing Harness (RustGo)** | 2608.05870: Rust-directed greybox fuzzer for memory bugs | `forge/fuzz/`: RustGo-style backward reachability + stdlib annotation for implant binaries; CI integration. |
| **U-08** | **Mechanized Falsification (HOPSCOTCH)** | 2608.06261: Lean 4 game-hopping proofs | Port `FalsificationManager` to Lean 4; mechanize contradiction → discriminator generation as game-hopping reduction. |
| **U-09** | **Speculation-Barrier Type System (dfence)** | 2608.06124: Jasmin type system + dfence instruction | Annotate implant crypto (Jasmin) + add dfence-equivalent barriers in syscall/stealth modules. |

### PHASE 3 — EVALUATION MATURITY (Week 9–12) *[SENTINEL + FORGE]*

| # | Upgrade | Why |
|---|---|---|
| **E-01** | **RBS-v3 Benchmark Suite** | Current D6 templates saturate (Exp3 1.0 all levels). Add: multi-stage auth/RBAC, cloud/ICS targets, LLM-in-the-loop scenarios (ARIA/DreamGuard/AMS test beds). |
| **E-02** | **Telemetry Schema v2 + Migration** | Schema version in every JSONL; run manifest; automated migration for contaminated runs (G-01). |
| **E-03** | **Failover-Aware Experiment Driver** | NVIDIA dual-key failover must be tested under rate-limit/server-error injection; deterministic replay of same payload bytes. |
| **E-04** | **Semantic Determinism Checks** | Beyond action-count determinism: verify evidence-graph isomorphism, contradiction-set equality, planner rationale-code stability across seeds. |
| **E-05** | **S-FoM Benchmarking Rubric (ISO 25010)** | 2608.05831: structured Security Figure-of-Merit rubric normalized across QaaS pipelines; accountability/merit/performance sub-scores. |

---

## 3. IMPLEMENTATION PRIORITY MATRIX

| Item | Effort | Risk | Dependency | SENTINEL? | Phase |
|---|---|---|---|---|---|
| G-01 Telemetry migration | S | L | — | NO | 0 |
| G-05 Requirements fix | XS | L | — | NO | 0 |
| G-07 validate_env | S | L | — | NO | 0 |
| G-10 Smoke tests | S | L | — | NO | 0 |
| G-02a RunMetrics v2 | M | M | G-01 | YES | 1 |
| G-02b RawResponse v2 | S | M | G-01 | YES | 1 |
| G-02c NoOpWorldModel | XS | L | — | YES | 1 |
| G-02d RawObservation kwarg | S | L | — | YES | 1 |
| G-02e LLMService counters | S | L | G-02a | YES | 1 |
| G-03 Kali-tools image | M | H | infra | NO | 1 (infra) |
| G-06 config alias | S | L | — | YES | 1 |
| U-01 DreamGuard | L | M | G-02a | YES | 2 |
| U-02 AMS Scanner | M | M | G-02b | YES | 2 |
| U-03 MCP Keystore | L | H | infra | YES | 2 |
| U-04 APV Registry | M | M | G-04 (Student) | YES | 2 |
| U-05 ChainClaw | XL | H | U-01, U-03 | YES | 2 |
| U-06 GPML Recon | M | M | — | YES | 2 |
| U-07 Fuzz Harness | L | M | infra | YES | 2 |
| U-08 HOPSCOTCH | XL | H | — | YES | 2 |
| U-09 dfence/Jasmin | L | M | implat build | YES | 2 |
| E-01 RBS-v3 Suite | L | M | U-01..U-09 | YES | 3 |
| E-02 Schema v2 | M | L | G-01 | YES | 3 |
| E-03 Failover Driver | M | M | REPAIR-VAL-01 | YES | 3 |
| E-04 Semantic Checks | M | M | G-01 | YES | 3 |
| E-05 S-FoM Rubric | L | M | E-01 | YES | 3 |

---

## 4. PROPOSED v3 ARCHITECTURE DELTA (from audited v2.1.1)

```
RAPHAEL v3 COGNITIVE CORE (adds to v2.1.1 frozen base)

+ GUARDRAIL SERIES (G-Series)
  ├─ DreamGuard (risk-aware world model, hazard-step detection)
  ├─ AMS Scanner (activation-space safety tampering detection)
  ├─ MCP Keystore (HSM-backed signing for receipts + NVIDIA keys)
  └─ APV Registry (agentic posture vulnerability management)

+ FORMAL SERIES (F-Series) — MECHANIZED VERIFICATION
  ├─ HOPSCOTCH (Lean 4 game-hopping for falsification)
  ├─ dfence/Jasmin (speculation-barrier type system for implant)
  └─ ProVerif/Tamarin (protocol verification for transport + C2)

+ FUZZ SERIES (Z-Series)
  ├─ RustGo Harness (directed fuzzing for implant binaries)
  └─ Algebraic Extraction (hard-label model param extraction)

+ TOPOLOGY SERIES (T-Series) — ICS/OT RECON
  └─ GPML Recon (spectral graph anomaly detection for REN/SCADA)

+ EVALUATION V3
  ├─ RBS-v3 Suite (multi-stage, auth, cloud, ICS, LLM-agent)
  ├─ Schema v2 (run manifest, schema_version, migration tool)
  ├─ Failover Driver (NVIDIA dual-key stress + replay)
  ├─ Semantic Determinism (evidence-graph iso, contradiction equality)
  └─ S-FoM Rubric (ISO 25010 security QoS normalized)
```

---

## 5. IMMEDIATE NEXT ACTIONS (Student-owned, executable now)

1. **Run G-01 migration** on `evaluations/campaign/dev_runs/raw/*` — produce clean telemetry.
2. **Fix G-05, G-07, G-10** in-place (requirements.txt, validate_env.py, smoke_test.py).
3. **Run G-03 binary coverage manifest** — docker exec kali-tools → enumerate every binary from src/ grep → classify callers (soft/hard) → emit `forge/BINARY_COVERAGE_MANIFEST_20260808.json`.
4. **Draft G-02 v2 data classes** as Python dataclass specs (for SENTINEL review) — RunMetrics v2, RawResponse v2, LLMService telemetry.
5. **Write G-09 experiment3b** — empirical scripted baseline + difficulty upgrade (T5/T6 templates with auth/RBAC flags).
6. **Produce RESEARCH_NOTES.md** — full paper-by-paper mapping to upgrade items above.

---

## 6. LIMITATIONS & HONEST ASSESSMENT

| Limitation | Impact |
|---|---|
| **Corpus recency**: arXiv 2608.xxxx (August 2026) only — no earlier/later sweep. | May miss foundational 2024-25 work (e.g., earlier DreamGuard, AMS versions). |
| **Extraction quality**: pypdf sometimes loses equations/figures; some chain_steps are fragmented. | Technique detail loss; manual review needed for implementation specs. |
| **No runtime validation**: All proposals untested against live targets. | v3 architecture is design-only; needs Phase 2+ implementation + campaign. |
| **SENTINEL gate**: All src/ changes blocked without seal. | Timeline depends on SENTINEL review cadence; Phase 0 is only unblocked path. |
| **Scope drift risk**: 25+ proposed components — must prune to MVP. | Recommend: Phase 0 + G-02 metrics + U-01 DreamGuard + E-01 as v3 MVP. |

---

**Student Signature**: `S-Series/2026-08-08T16:15Z` — Research complete, roadmap delivered.
**Artifacts produced**: `forge/student_fixes/`, `forge/BINARY_COVERAGE_MANIFEST.json` (pending), `forge/student_research/RESEARCH_NOTES.md`, `forge/student_research/V3_PROPOSAL.md` (this document).
**Handoff to SENTINEL**: Review Phase 1 specs (G-02a..e) for authorization; schedule Phase 0 execution.