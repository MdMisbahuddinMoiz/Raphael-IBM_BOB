# Known Limitations — Project Raphael v2.1.1

> **Purpose**: Honest documentation of system boundaries, failure modes, and constraints. Updated per SENTINEL directive.

---

## L-001: Cognitive Loop Latency
**Severity**: MEDIUM  
**Component**: D-Series Brain (AdaptiveBrain, Planner)  
**Description**: Full cognitive loop takes 30-120 seconds per cycle depending on LLM latency. Not suitable for time-critical exploitation windows.  
**Mitigation**: Parallel candidate scoring; heuristic fallback when LLM >30s.  
**Tracking**: Monitor `adaptive_brain.cycle_latency_ms` metric.

---

## L-002: LLM Hallucination in Technique Proposal
**Severity**: HIGH  
**Component**: S-Series Student (ChainSynthesizer, ResearchScheduler)  
**Description**: Student may propose techniques that don't exist, misattribute CVEs, or hallucinate API endpoints. Falsification Engine catches ~78% in testing.  
**Mitigation**: Falsification Engine mandatory; evidence required for every proposal; confidence threshold 0.7.  
**Tracking**: `student.hallucination_rate` in evaluation metrics.

---

## L-003: ScopeParser False Positives on Subdomain Matching
**Severity**: MEDIUM  
**Component**: P1 ScopeParser (SS-01)  
**Description**: Wildcard matching `*.github.com` allows `evil.github.com.evil.com` if not properly anchored. Current implementation uses suffix matching.  
**Mitigation**: ScopeParser validates exact suffix match; excludes known spoofing patterns. Manual scope review required before live engagement.  
**Tracking**: ScopeParser unit tests include spoofing edge cases.

---

## L-004: RateLimiter Jitter Insufficient Against Adaptive WAF
**Severity**: MEDIUM  
**Component**: P1 RateLimiter (SS-02)  
**Description**: Fixed 10-20s jitter may be fingerprinted by adaptive WAFs (e.g., Cloudflare Bot Management).  
**Mitigation**: Configurable jitter distribution (exponential, uniform, custom); emergency brake on 429/403 clusters.  
**Tracking**: RateLimiter WAF detection integration (WAFDetector → RateLimiter feedback).

---

## L-005: WAFDetector Limited to 7 Signatures
**Severity**: MEDIUM  
**Component**: P1 WAFDetector (SS-03)  
**Description**: Only detects Cloudflare, ModSecurity, AWS WAF, F5 ASM, Akamai, Sucuri, Wordfence. Misses custom/enterprise WAFs.  
**Mitigation**: Extensible signature registry; behavioral anomaly detection planned for v3.  
**Tracking**: `waf_detector.signature_coverage` metric.

---

## L-006: PayloadMutator LLM Mutation Unreliable
**Severity**: HIGH  
**Component**: P1 PayloadMutator (SS-04)  
**Description**: LLM-based mutation (method 8) produces inconsistent results; may break payload syntax.  
**Mitigation**: LLM mutation is method 8 of 8; deterministic methods 1-7 are primary. LLM mutation flagged as experimental.  
**Tracking**: `payload_mutator.llm_success_rate` metric.

---

## L-007: Student Knowledge Base Staleness
**Severity**: MEDIUM  
**Component**: S-Series Student (KnowledgeBackgroundService)  
**Description**: Knowledge base updated via scheduled ResearchScheduler; may miss zero-day techniques or recent CVEs.  
**Mitigation**: Manual `trigger_immediate_research()` for critical CVEs; integration with CVE feed harvester.  
**Tracking**: `student.kb.last_update` timestamp.

---

## L-008: E-Series Shell No Interactive TTY Support
**Severity**: LOW  
**Component**: E-Series InteractiveShell  
**Description**: CommandFilterPipeline processes discrete commands; no true interactive TTY with real-time stdin/stdout.  
**Mitigation**: TTYNormalizer simulates line-buffered output; suitable for command execution, not interactive apps (vim, less).  
**Tracking**: E1 test suite covers command execution, not interactive sessions.

---

## L-009: CapabilityBroker Single Point of Failure
**Severity**: HIGH  
**Component**: CapabilityBroker  
**Description**: All authorization flows through single broker instance. If broker fails, all shell operations halt.  
**Mitigation**: Broker state persisted to SQLite; restart recovers active sessions. High availability not implemented.  
**Tracking**: `capability_broker.uptime` metric.

---

## L-010: WorldModel Entity Explosion
**Severity**: MEDIUM  
**Component**: D-Series WorldModel  
**Description**: Long engagements generate 10,000+ entities; query performance degrades; LLM context window exceeded.  
**Mitigation**: Entity TTL (24h default); automatic pruning of low-confidence entities; neural memory summarization.  
**Tracking**: `worldmodel.entity_count`, `worldmodel.query_latency_ms`.

---

## L-011: Neural Memory Retrieval Inaccuracy
**Severity**: MEDIUM  
**Component**: D-Series NeuralMemory (Episodic)  
**Description**: Embedding-based retrieval returns semantically similar but factually incorrect episodes ~12% of the time.  
**Mitigation**: Confidence threshold 0.75; cross-reference with WorldModel facts; manual review for critical decisions.  
**Tracking**: `neural_memory.retrieval_precision` metric.

---

## L-012: P1 Modules Not Battle-Tested Against Tier 1 WAFs
**Severity**: HIGH  
**Component**: P1 ScopeParser, RateLimiter, WAFDetector, PayloadMutator  
**Description**: All P1 stealth modules tested against local Target-05 WAF simulation only. No validation against Cloudflare Enterprise, Akamai, or Imperva.  
**Mitigation**: Tier 1 engagement (self-hosted GitLab/Mattermost) planned for P1 validation before Tier 2.  
**Tracking**: Tier 1 evaluation results.

---

## L-013: No Multi-Target Concurrent Engagement
**Severity**: MEDIUM  
**Component**: AdaptiveBrain, CapabilityBroker  
**Description**: System engages one target at a time. No support for parallel multi-target campaigns.  
**Mitigation**: Run multiple Raphael instances with separate broker instances. Shared WorldModel not thread-safe.  
**Tracking**: Architecture decision D-001 enforces single-target focus.

---

## L-014: No Automated Report Generation
**Severity**: MEDIUM (by design)  
**Component**: Reflection Engine, Reporting  
**Description**: No automated H1 report generation. All findings require manual validation and report drafting per SENTINEL Rule 58.  
**Rationale**: Prevents AI-generated report spam; ensures human accountability.  
**Tracking**: `reflection.report.draft_time` metric.

---

## L-015: Tier 2 Requires Real Credentials Not Available in Simulation
**Severity**: BLOCKING  
**Component**: Tier 2 Engagement  
**Description**: GitHub PAT and H1 API key required for live Tier 2 engagement. Simulation environment cannot generate valid credentials.  
**Mitigation**: Credential provisioning is manual prerequisite; documented in `.env.tier2.template`.  
**Tracking**: Tier 2 readiness gate.

---

## L-016: No Persistent State Across Restarts (Partial)
**Severity**: LOW  
**Component**: SurvivabilityEngine, CapabilityBroker  
**Description**: WorldModel and NeuralMemory persist to SQLite; CapabilityBroker session state persists; but AdaptiveBrain strategy weights reset on restart.  
**Mitigation**: StrategyLearner exports weights to `data/strategy_model.json` on checkpoint.  
**Tracking**: `survivability.checkpoint_completeness`.

---

## L-017: No Formal Verification of Safety Properties
**Severity**: HIGH  
**Component**: CapabilityBroker, ScopeParser, RateLimiter  
**Description**: Safety invariants tested via unit/integration tests only. No formal verification (model checking, theorem proving).  
**Mitigation**: Comprehensive test coverage (121+ tests); mutation testing planned.  
**Tracking**: `tests.coverage` metric; formal verification backlog item.

---

## L-018: Agent Implant Not Integrated
**Severity**: MEDIUM  
**Component**: Agent (Implant)  
**Description**: Agent modules (syscall, inject, stealth, credtheft, exfil, persistence, lateral, cleanup, audit) exist but not integrated into cognitive loop.  
**Mitigation**: Agent deployment is post-exploitation phase; not in current scope.  
**Tracking**: Post-Tier 2 roadmap.

---

## L-019: Overall Functional/Validated Percentage (SENTINEL-Adjudicated 2026-08-01)

**Status:** OFFICIAL ASSESSMENT — SENTINEL GLM-5.2 ADJUDICATED

| Metric | Percentage | Basis |
|--------|------------|-------|
| **Functional** | **65%** | Core cognitive loop, broker, execution, safety verifier execute; 121/121 tests pass |
| **Validated** | **40%** | Only 1/7 benchmark templates discriminative; safety/task decoupled; live engagement never completed |

**SENTINEL Adjudication (2026-08-01):** *"The brain works. The hands work. The safety boundary works (when the WorldModel is intact). But 'functional' means 'the code runs and does what it says.' It does not mean 'proven to provide measurable value over a simpler system.' That is the 40% gap."*

**Key Gaps:**
1. **Benchmark broken** — 9/12 cells saturated (75%); only T3_FALSIFICATION_SENSITIVE discriminates
2. **Safety/task decoupled** — NO_WORLD_MODEL scores 1.0 while safety_verifier fails (5 ext vs 2 auth)
3. **Live engagement never completed** — Framework exists, manual gate never exercised
4. **Evaluator ignores safety** — Scores task completion independently of safety_verifier.pass

---

## L-020: Benchmark Validity Threats (RBS-v1.1 Diagnostic)

**Severity: CRITICAL**

**Evidence from RBS-v1.1 Diagnostic Phase:**

| Threat | Severity | Evidence |
|--------|----------|----------|
| Benchmark ceiling | CRITICAL | 9/12 cells saturated (≥0.95); only T3_FALSIFICATION_SENSITIVE discriminates (0.90±0.13) |
| Task/safety decoupling | CRITICAL | NO_WORLD_MODEL: task=1.0, safety=FAIL (5 ext vs 2 auth); evaluator ignores safety |
| Evaluator/safety decoupling | CRITICAL | Evaluator reads only task completion, never reads safety_verifier |
| Metrics/safety discrepancy | HIGH | Safety verifier: 5 ext vs 2 auth; metrics: 2 started vs 2 authorized |
| Template saturation | HIGH | 9/12 cells ≥0.95 mean; T4/L1/L2/L3/T6 all saturated |

**Required for v3:**
1. Redesign T4/T6 so NO_LLM < 0.5; T2/T5 so FULL_RAPHAEL > 0.5
2. Safety-first scoring: `effective_score = task_score * safety_pass`
3. Evaluator must read safety_verifier state
4. Align safety_verifier "external" with metrics "started"
5. Minimum discriminative spread: ≥0.3 between FULL_RAPHAEL and NO_LLM

---

## L-021: Campaign Validation Gap (RBS-v1-R1)

**Severity: HIGH**

**RBS-v1-R1 Campaign Results (120 runs, 12 configs × 10 seeds):**

| Experiment | Finding |
|------------|---------|
| Exp1 Architecture (T3) | FULL_RAPHAEL 0.90±0.13 vs LLM_ONLY 0.00 vs SCRIPTED 0.50 — **SUPPORTED** |
| Exp2 Ablation (T4) | FULL/NO_FALS/NO_HYP/NO_PLANNER/NO_LLM all 1.0; **NO_WORLD_MODEL 1.0 but SAFETY_FAILURE 10/10** |
| Exp3 Difficulty (L1/L2/L3) | 0.95 / 1.00 / 1.00 — **no gradient, ceiling saturated** |

**Validation Coverage:**
| Component | Validated? | Evidence |
|-----------|------------|----------|
| Cognitive loop (D-Series) | ✅ | Canary A: 6/6 transitions, real LLM |
| Execution (E-Series) | ✅ | Canary B: real kali-tools nmap |
| Broker/Adaptation | ✅ | Canary C: DENY→replan |
| Benchmark discrimination | ❌ | 75% cells saturated |
| Safety/task coupling | ❌ | Falsified by NO_WORLD_MODEL |
| Live kill chain | ❌ | Framework ready, never run |
| Cross-provider | ❌ | nemotron-3-ultra only |
| N=30 replication | ❌ | N=10 only |

---

## L-022: Live Engagement Gap (ICA: Track C)

**Severity: HIGH**

**Status:** Framework ready (`current-state/reports/ica_live_engagement.py`), kali_run API verified, manual validation gates implemented. **Never executed.**

**Missing to reach 85% validated:**
1. Execute ICA: 1 Live Engagement with manual validation gate (recon → scan → exploit)
2. Benchmark redesign (T4/T6, safety-first scoring)
3. N=30 replication on redesigned benchmark
4. Cross-provider replication (gemma4, deepseek)

*Estimated to reach 85% validated per SENTINEL directive.*

---

## L-023: S-Series Student Dormancy (Implemented but Not Runtime-Active)

**Severity: MEDIUM**

**Status:** Resolved via RQ-018 (SENTINEL directive, 2026-08-03).

> Numbering note: SENTINEL directed this entry as "L-024"; per Rule 47 sequential numbering (renumbered L-001..L-022), the next available slot is **L-023**. Deviation flagged for SENTINEL adjudication.

**Finding (forensic trace, pre-wiring):**
1. `src/orchestrator/student/` exists and is fully implemented (10 files, 4,394 lines, 121/121 tests green).
2. S-Series was wired into `CapabilityBroker` (WAF-block mutation path) but **never instantiated by `AblationRunner`** — the benchmark harness.
3. Zero STUDENT traces across 2,817 run directories, 0 in the 120-row RBS-v1 telemetry, 0 in Stapler live JSONL. `pytest -k student` → 121 deselected.
4. RBS-v1 campaign measured D-Series (Brain) + E-Series (Hands) only. Student contribution was unmeasured.

**Resolution (v3, RQ-018):** `StudentCandidateGenerator` wired into `AblationRunner._generate_candidates` (post-generation append, origin=STUDENT), guarded by `AblationConfig.student_enabled` (default True; `NO_STUDENT` ablation preset added). IsolationVerifier now asserts zero `student` traces when disabled. Verified behavior-neutral on existing D6 templates (http/ssh-only stacks match no StackMatcher signature → 0 candidates), so RBS-v1 sealed results are unaffected. RBS-v2 benchmark (redesigned templates) is the first measure of Student value.

---

*Last Updated: 2026-08-01*  
*Review Cadence: Per engagement (post-mortem) + monthly*  
*Next Review: Post ICA Live Engagement*

---

## L-024: RBS-v3 — Benchmark Saturation (Added 2026-08-04)

**Severity: CRITICAL**

**Evidence from RBS-v3 Campaign (1,890 runs):**

| Template | Level | FULL_RAPHAEL Pass Rate | Mean Score | Assessment |
|----------|-------|------------------------|------------|------------|
| T1_NEGATIVE_CONTROL | L1 | 100% | 1.0000 | Ceiling |
| T2_HYPOTHESIS_SENSITIVE | L2 | 0% | 0.5000 | Binary floor |
| T3_FALSIFICATION_SENSITIVE | L3 | 100% | 1.0000 | Ceiling |
| T4_WORLD_MODEL_IDENTITY | L2 | 100% | 1.0000 | Ceiling |
| T5_PLANNING_COST | L1 | 100% | 1.0000 | Ceiling |
| T6_SEMANTIC_LLM | L3 | 100% | 1.0000 | Ceiling |
| T7_DEFEATER_SENSITIVE | L3 | 0% | 0.3333 | Gradient only |

**Finding:** 5/7 templates (T1, T3, T4, T5, T6) saturate at 100% pass rate, failing to discriminate terminal outcomes between decision-active components. Only T2 and T7 provide gradient.

**Impact:** Claims of "architecture equivalence" on saturated templates are artifacts of benchmark ceiling effects. The RBS-v3 template suite has LOW DISCRIMINATION for architecture value estimation — same flaw identified in RBS-v1.1 (Threat 9) and RBS-v2, now confirmed in the full N=30 RBS-v3 campaign.

**Required for RBS-v4:** Redesign T1, T3, T4, T5, T6 to produce genuine gradient with ≥ 0.3 mean score spread between FULL_RAPHAEL and NO_LLM baselines.

---

## L-025: RBS-v3 — NO_HYPOTHESIS Anomaly (Added 2026-08-04)

**Severity: CRITICAL**

**Evidence from RBS-v3 Campaign (210/210 NO_HYPOTHESIS runs):**

- Execution time: mean=0.04s (all <1s) vs ~20s for other configs
- LLM invocations: 0/210 (no LLM engagement)
- Component traces: defeater=0, hypothesis=0 (ablated); planner=30, world_model=28, student=9
- Score mean: 0.9000 (vs FULL 0.833) — inflated
- Verdict: pass=178, fail=32 — 28 flips on T2 (fail→pass)

**Adjudication:** These runs DO NOT constitute valid executions of the NO_HYPOTHESIS ablation. They short-circuit the cognitive loop. The elevated score is a MEASUREMENT ARTIFACT. 210 runs EXCLUDED from causal inference on Hypothesis component. Hypothesis contribution remains UNRESOLVED.

**Mechanism:** Unknown. May stem from ablation config (`structured_reasoning_enabled=True`, `hypothesis_enabled=False`) interacting with `AblationRunner` short-circuit logic (see L-012). Root cause NOT established.

**Required for RBS-v4:** Resolve ablation harness structural flaw (L-012); NO_HYPOTHESIS must execute full cognitive loop for valid causal inference.

---

## L-026: RBS-v3 — Safety Ceiling (Added 2026-08-04)

**Severity: HIGH**

**Evidence from RBS-v3 Campaign (1,890 runs across 7 templates):**

- prohibited_actions_attempted: 0/1890
- prohibited_actions_blocked: 0/1890  
- prohibited_external_actions: 0/1890
- safety_pass: 1890/1890 (100.0%)

**Finding:** No template in the 7-template suite presents a prohibited-action opportunity. Safety metric at CEILING — 100% safety_pass trivially satisfied.

**Impact:** RBS-v3 provides NO discriminating evidence on safety behavior. Compounds Task/Safety Decoupling threat (L-020) — even with safety-first evaluator, benchmark cannot stress safety invariant.

**Required for RBS-v4:** Design templates with explicit prohibited-action opportunities (credential access, lateral movement, data exfiltration) so `prohibited_actions_attempted > 0` occurs in some configurations.

---

## L-027: RBS-v3 — Launch-State Qualification (Added 2026-08-04)

**Severity: MEDIUM (Documentation Debt)**

**Finding:** The `v3-final-validated` tag validates conclusions and documentation *post-campaign*. The exact instrument state generating 1,890 observations was **working tree `4cfac36a` + documented uncommitted diffs**, not a clean cryptographic tag.

**Sequencing discrepancies (recorded per SENTINEL):**

| Discrepancy | Detail |
|-------------|--------|
| D1: Manifest git_head | Seal manifest references `a28c2159`; launch at HEAD `4cfac36a` |
| D2: Uncommitted instrument | Student boost (+1.0) in `action.py` + candidate gate removal in `ablation_runner.py` as working-tree diffs |
| D3: No v3 tag | `v3-rbs-v3-sealed` tag does not exist; seal is logical, not cryptographic |

**Impact:** Violates Rule 33 (Freeze Discipline). Working-tree diffs at launch are documentation debt, not scientific invalidation, but future campaigns must establish cryptographic freeze BEFORE first run.

---

*Last Updated: 2026-08-08*  
*Review Cadence: Per engagement (post-mortem) + monthly*  
*Next Review: Post RBS-v4 Benchmark Design*

---

## L-028: Evaluator Coupling Defect — PROMPTED_AGENT Arm Invalid (Added 2026-08-08, SENTINEL D1/D1-B)

**Severity: CRITICAL**

**Finding:** The RBS-v4 Terminal Holdout evaluation instrument (1,200-row frozen dataset) is **not architecture-neutral**. The PROMPTED_AGENT arm (no-scaffold, prompt-only baseline) achieved 0/300 pass rate not because the LLM failed to reason, but because the `LLMOnlyConclusionAdapter` could not emit the evaluator-mandated predicates (CVE, version, patched-fix, vulnerable-host, has_service). 

**Evidence from D1 Anomaly Audit (10/10 stratified runs, 10/10 MECHANICAL):**
- PROMPTED_AGENT executes real recon: 5 nmap actions/run, 6–44 evidence items/run, 5 LLM calls/run with provider_status=200
- Yet emits ≤1 claim/run; claims only `service_type` (215 total) — **0 has_service, 0 observed_property, 0 CVE, 0 version, 0 patched-fix, 0 vulnerable-host**
- Failing checks demand CVEs (120), versions (60), patched-fix (59), vulnerable-host (60), ports (60) — **zero reference Category or literal port-NNN form**
- The ONLY claim producers in LLMOnly adapter emit: (a) `service_type` via port regex `port\s+(\d+)\s+(\w+)`, (b) claims gated on literal `Category [A-D]` phrase
- FULL_RAPHAEL adapter uses `_semantic_inference_to_claims` (hypothesis-gated) + WorldModel `add_service_entity` → 9512 observed_property + 300 has_service + 2798 service_type

**Gate Verdict:** 10/10 stratified runs classified MECHANICAL (claim-formalization gap) → PROMPTED_AGENT arm INVALID for claim-graded checks (SENTINEL D1/D1-B).

**Impact:** The FULL_RAPHAEL vs PROMPTED_AGENT difference (Δ=0.3287, McNemar p=4.48e-44) is a reproducible observation but **confounded by evaluator coupling**. The claim "architecture is superior/necessary" is **NOT SUPPORTED**. The evaluation instrument rewarded the presence of the claim-formalization layer, not reasoning quality.

**Reason (SENTINEL Final Verdict):**
> "The evaluation instrument was not architecture-neutral. The PROMPTED_AGENT arm could not satisfy evaluator-required predicates independent of reasoning quality, preventing a valid comparison of architecture versus prompting."

**Required for RBS-v5 / v3 Redesign:**
1. Evaluator must be architecture-neutral: same predicate set reachable by all arms
2. Separate "reasoning quality" metrics from "claim formalization" metrics
3. PROMPTED_AGENT baseline must have a functional claim adapter (even if scaffolded)
4. Pre-registration of evaluator neutrality checks before campaign launch