# RAPHAEL v2.1.1 — ARCHITECTURE (AUDIT-GROUNDED, 2026-08-08)

> Derived from `forge/AUDIT_REPORT_20260808.md`. Every component below was verified to exist in the working tree (439 py files, 97,048 LOC in src/) and resolve on the import map unless marked ⚠️. Frozen cognitive core = **do not modify** without SENTINEL authorization.

---

## 1. OVERVIEW

```
┌────────────────────────────── RAPHAEL v2.1.1 ──────────────────────────────┐
│  COGNITIVE CORE (FROZEN)                     SERVICE FABRIC (LIVE)         │
│  ┌───────────────────────────────────┐      ┌───────────────────────────┐  │
│  │ D-SERIES BRAIN  (51,148 LOC)      │      │ sword        :3600 (host)  │  │
│  │  orchestrator/brain/              │      │ api          :3900         │  │
│  │  action.py world.py               │      │ cai-service  :3201         │  │
│  │  capability_broker.py             │      │ mhddos       :3301         │  │
│  │  hypothesis/contradiction/        │      │ cloak-service:3401 (tor)   │  │
│  │  falsification/reflection/        │      │ c2-server    :3501 (sliver)│  │
│  │  strategy(+learner)/trust/        │      │ phishing     :3502         │  │
│  │  neural_memory/skill_indexer/     │      │ recon-pipeln :3503         │  │
│  │  adaptive_brain/                  │      │ kali-tools   :3800 (892bins)│ │
│  │  P1: scope_parser rate_limiter    │      │ neo4j (graph)              │  │
│  │      waf_detector                 │      │ dvwa (target)              │  │
│  └───────────────────────────────────┘      └───────────────────────────┘  │
│  ┌───────────────────────────────────┐      ┌───────────────────────────┐  │
│  │ S-SERIES STUDENT (verified 10 f)  │      │ IMPLANT (src/agent, 6.6K) │  │
│  │  student.py technique_proposer    │      │  crypto syscall stealth   │  │
│  │  research_scheduler (arxiv/scihub)│      │  credtheft exfil persist  │  │
│  │  chain_synthesizer               │      │  lateral cleanup audit     │  │
│  │  knowledge_background_service    │      └───────────────────────────┘  │
│  │  coverage_gap_filler/stack_matcher│      ┌───────────────────────────┐  │
│  │  payload_mutator (P1-SS-04)      │      │ MCP-HUB (HMAC auth, tools)│  │
│  │  integration_pipeline           │      │  decision_engine · 33 f   │  │
│  └───────────────────────────────────┘      └───────────────────────────┘  │
│                                             ┌───────────────────────────┐  │
│  ┌───────────────────────────────────┐      │ RAPHAEL CORE (12.6k LOC) │  │
│  │ E-SERIES HANDS (brokered)         │      │  eventbus(redis⚠️)        │  │
│  │  SSH/Reverse shell capabilities   │      │  blackboard·circulatory   │  │
│  │  command_filter T1/T2 pipeline   │      │  limbic·cerebellum        │  │
│  │  listener_manager (broker-only)  │      │  hippocampus (episodes)   │  │
│  │  tty_normalizer + evidence ext   │      │  exploit_factory·verifier │  │
│  └───────────────────────────────────┘      │  techniques (15+)        │  │
│                                             └───────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
        ARENA (src/arena, 21.2k LOC) — ablation_runner · d6_manifest · evaluator
        · llm_transport (dual-key NVIDIA failover) · episode/events JSONL
        BENCHMARKS — RBS-v1/v2/v4 registrations · targets/ · scenario factories
```

## 2. COGNITIVE LOOP (VERIFIED IN RUNS)

```
Student → CandidateGenerator(shell/student/recon) → Planner (utility/cost/risk,
rationale codes) → CapabilityBroker (5-dim deny-by-default: target/RoE/cap/rate/
impact + ScopeParser fail-closed + RateLimiter jitter + dual-gate shells)
→ Execution (E-Series / tools via kali client) → TTYNormalizer → EvidenceExtractor
→ WorldModel.ingest_shell_evidence() → ContradictionManager → FalsificationTasks
→ Reflection/Strategy update → loop, max ITERATION_BUDGET=5 / ACTION_BUDGET=20.
```
Verified live: Experiment 0 run trace shows candidates → planner selected → broker
`allow` w/ receipt id → execution → observations → evidence → contradiction
management cycles (see episode JSONL fields).

## 3. AUTHORIZATION MODEL (AUDIT-VERIFIED ARCHITECTURE)

1. **Deny-by-default 5 dimensions** — verified broker denials logged:
   `DENIED: scan on target — ["Target not in allowed scope: ['10.0.52.0/24']"]`
2. **Dual-gate shell sessions** — `authorize_shell_session()` + per-command
   `authorize_shell_command()`; injection chars (`; | & ``) → ESCALATE to T2 LLM.
3. **Listeners broker-exclusive** — no unbrokered reverse-shell path.
4. **P1 in flow** via broker; PayloadMutator max 3 rounds.

## 4. DATA FLOW / TELEMETRY (VERIFIED + ⚠️ DEFECT)

```
AblationRunner → EpisodeRecorder→ raw/{run_id}/episodes.jsonl   ⚠️ appends
              → EventsRecorder → raw/{run_id}/events.jsonl      ⚠️ appends
              → RunMetrics (dataclass) → evaluation_result → summary JSON
Analysis: evaluator (evidence-graph isolated per run) · runconclusion · ablation
⚠️ F-01: append mode without idempotency → re-runs contaminate telemetry
     (same composite key, divergent content — proven in dev_runs raw).
```

## 5. STUDENT (S-SERIES) INTEGRATION — VERIFIED

- research_scheduler: arXiv API pulls (live corpus 2608.xxxx observed in prior run;
  20/20 deep read, 0 failures), scihub stub.
- Knowledge flows into WorldModel TECHNIQUE entities via proposals — candidate
  pool → planner scoring (documented + code present).
- Evidence files exist: `STUDENT_REPORT_TO_SENTINEL_20260808T113606Z.md`,
  research findings JSON+JSONL.

## 6. IMPLANT (src/agent) — VERIFIED IMPORTABLE, CRYPTO-OK

17 files / 6,660 LOC: Hell's Gate/Halo's Gate syscall resolution (syscall.py),
injection, stealth, cred theft, exfil (GCM-encrypted chunking — inverse VERIFIED),
persistence, lateral, cleanup, dependency_check, audit. Not exercised live in
arena (arena is broker/simulated) — implant is E2E-adjacent but untested E2E in
this campaign (gap G-4).

## 7. KNOWN NOT-VERIFIED / GAP ZONES

| Component | State |
|---|---|
| `raphael.brain.*` module (46 core) | imports OK; runtime paths exercised only indirectly |
| Propagation/Mesh engines (v3 trajectory) | present in code but **not frozen-verified** per architecture freeze — see gap report |
| Container escape / CI poison / cloud-abuse phase executors | importable; not run (no live targets) |
| `sword/` package (1.2k LOC) | importable (except config alias); local "sword" service = host runner |
| mcp-hub tool set (33 files) | ~20 tools subprocess to binaries; 5 missing in kali image (Rule 3) |

## 8. ARCHITECTURE RULES (applies to all fixes)

1. v2.x architecture frozen — no cognitive-loop modification without SENTINEL.
2. All fixes first-class: scripts/ and infra (docker/venv/docs) are mutable by FORGE;
   `src/` mutation requires SENTINEL authorization + regression proof.
3. Every change must keep tracked test subset green (127/127) and add new tests
   with raw JSONL evidence (Strike-2 rule: no result without telemetry).
4. New capabilities join as capabilities registered in CapabilityBroker, never
   unbrokered execution paths.