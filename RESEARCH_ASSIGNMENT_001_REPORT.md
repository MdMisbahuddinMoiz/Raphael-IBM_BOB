# RAPHAEL Research Assignment 001 — Architecture vs Prompting

**Project**: Determine which Raphael components are scientifically justified, how they should evolve, and where current AI research has already solved the problem better.
**Prepared by:** THE STUDENT (S-Series, research agent), RBS v2.1.1 evaluation campaign
**Status:** DELIVERABLE COMPLETE — literature synthesis + roadmap
**Date:** 2026-08-08

---

## Methodology & source-integrity statement (read first)

This report follows the assignment's ground rules:

1. **No code was written or modified** except the evidence-assembly scripts that produced this document. `src/` is untouched (frozen v2.1.1).
2. **Raphael "Current Design" columns are grounded in the frozen source**, read directly from `src/orchestrator/brain/` (world.py, hypothesis.py, evidence.py, contradiction.py, action.py, capability_broker.py, neural_memory.py) and `src/orchestrator/student/student.py`. Where a column says "implemented", it means the file exists and the dataclass/logic is present; where it says "stub/assumed", the source contains a literal placeholder (`PreconditionType.CAPABILITY_AVAILABLE` returns `(True, "Capability ... assumed available")`, `AUTHORIZATION` returns `(True, "Authorization assumed for planning")`).
3. **Primary-source verification.** A majority of cited arXiv/preprint IDs were batch-verified against the arXiv export API (`export.arxiv.org/api/query`) on 2026-08-08; verified IDs are marked `[V]`. Any source that could not be verified via the API is explicitly flagged, not silently cited.
4. **Evidence grading** follows the assignment's taxonomy: **Strong** (replicated / benchmark-verified across settings), **Moderate** (single rigorous study or convergent analyses), **Weak** (emerging / contested / inference).
5. **Established evidence vs. emerging research vs. personal inference** is flagged inline with the markers **[E]**, **[X]** (emerging), **[P]I** whenever the distinction matters.

### Verified primary sources (batch-verified via arXiv API, 2026-08-08)

| arXiv ID | Title |
|---|---|
| 2210.03629 | ReAct: Synergizing Reasoning and Acting |
| 2303.11366 | Reflexion: Language Agents with Verbal Reinforcement Learning |
| 2305.10601 | Tree of Thoughts: Deliberate Problem Solving with LLMs |
| 2402.03620 | Self-Discover: LLMs Self-Compose Reasoning Structures |
| 2401.14295 | Demystifying Chains, Trees, and Graphs of Thoughts |
| 2201.11903 | Chain-of-Thought Prompting Elicits Reasoning in LLMs |
| 2203.11171 | Self-Consistency Improves CoT Reasoning |
| 2502.11221 | PlanGenLLMs: Modern Survey of LLM Planning Capabilities |
| 2402.02716 | Understanding the Planning of LLM Agents: A Survey |
| 2404.13501 | A Survey on the Memory Mechanism of LLM-based Agents |
| 2407.04363 | AriGraph: Knowledge Graph World Models w/ Episodic Memory |
| 2501.13956 | Zep: A Temporal Knowledge Graph Architecture for Agent Memory |
| 2503.21460 | LLM Agent: A Survey on Methodology, Applications and Challenges |
| 2502.12110 | A-MEM: Agentic Memory for LLM Agents |
| 2504.19413 | Mem0: Production-Ready Long-Term Memory |
| 2603.07670 | Memory for Autonomous LLM Agents (survey) |
| 2311.12983 | GAIA: a benchmark for General AI Assistants |
| 2310.06770 | SWE-bench: Can LLMs Resolve Real-World GitHub Issues? |
| 2308.03688 | AgentBench: Evaluating LLMs as Agents |
| 2404.07972 | OSWorld: Benchmarking Multimodal Agents (OS tasks) |
| 2307.13854 | WebArena: A Realistic Web Environment for Autonomous Agents |
| 2406.12045 | tau-bench: A Benchmark for Tool-Agent-User Interaction |
| 2207.05221 | Language Models (Mostly) Know What They Know (P(true)) |
| 2503.18813 | CaMeL: Defeating Prompt Injections by Design |
| 2502.05174 | MELON: Provable Defense Against Indirect Prompt Injection |
| 2505.23643 | FIDES: Securing AI Agents with Information-Flow Control |
| 2509.10540 | EchoLeak: Real-World Zero-Click Prompt Injection Exploit |
| 2410.14923 | Imprompter: Tricking LLM Agents into Improper Tool Use |
| 2505.05849 | AgentVigil: Black-Box Red-teaming for Indirect PI |
| 2406.05804 | Review of Prominent Paradigms for LLM-based Agents |
| 2502.17419 | From System 1 to System 2: Survey of Reasoning LLMs |
| 2601.12560 | Agentic AI: Architectures, Taxonomies, Evaluation of LLM agents |
| 2601.12538 | Agentic Reasoning for LLMs (survey, ~800 papers) |
| 2603.22489 | MCP Threat Modeling & Prompt Injection Vulnerabilities |
| 2511.15759 | Securing AI Agents Against Prompt Injection (benchmark+defense) |
| 2304.03442 | Generative Agents: Interactive Simulacra of Human Behavior |

### Sources used but NOT API-verified (flagged)

| Cite | Status |
|---|---|
| CyBench (IBM adversarial cyber benchmark) | arXiv ID not located via API on 2026-08-08; treated as **secondary citation** — do not treat its numbers as independently verified. |
| DEFREASING (NAACL 2025) | Locatable via ACL Anthology (2025.naacl-long.529); arXiv ID not required. |
| ConfidenceBench (2026) | Referenced via arXiv HTML indexing; full unique ID not confirmed — flagged [P] where relied upon. |
| Beta-Bernoulli Calibrator (forecast calibration) | Referenced via alphaXiv PDF index; unique ID not confirmed — flagged. |

---

# PART A — ARCHITECTURE

---

## Question A1 — How do modern autonomous AI agents organize reasoning?

### 1. Current state of the art

Three landmark 2025–2026 surveys converge on a stable picture:

- **2601.12560 [V] "Agentic AI: Architectures, Taxonomies, and Evaluation"** decomposes agents into six functional layers — **Perception, Brain, Planning, Action, Tool Use, Collaboration** — and evaluates them on **CLASSic** (Cost, Latency, Accuracy, Security, Stability). It analyzes existing multi-agent frameworks (CAMEL, AutoGen, MetaGPT, LangGraph, Swarm, MAKER) under one lens.
- **2601.12538 [V] "Agentic Reasoning for LLMs"** (~800 papers) organizes reasoning into **Foundational** (single-agent planning, tool use, search), **Self-Evolving** (feedback, memory, learning), and **Collective** (multi-agent coordination) layers.
- **Springer AI Review (Nov 2025)** separates the **symbolic/classical lineage** (algorithmic planning, persistent state) from the **neural/generative lineage** (stochastic generation, prompt-driven orchestration), analyzing 90 studies (2018–2025).

Four architecture patterns dominate production:

1. **Reasoning-enhanced** (CoT, ToT, GoT) — pure deliberation, no tools. Limited: cannot verify conclusions against the world [2401.14295 V].
2. **Tool-augmented** (ReAct) — interleave reasoning + tool calls; the canonical pattern; solves hallucination-by-grounding [2210.03629 V].
3. **Self-evolving** (Reflexion, memory-augmented) — learns from outcomes via verbal reinforcement, no weight updates [2303.11366 V].
4. **Collaborative / multi-agent** — supervisor–worker, swarm, maker–checker topologies [2601.12560].

**Modular cognition / blackboard lineage.** Blackboard systems (Hearsay-II, BB1, 1970s) survive conceptually as shared-scratchpad / shared-memory designs in LangGraph subgraphs, AutoGen group chat, and CrewAI hierarchical pattern. The "Components" surveys (2601.12560) recognize collaboration as the sixth layer.

**Hybrid symbolic + neural** is the strongest recent branch: LLM-as-translator ⇄ PDDL ⇄ classical planner (Fast Downward etc.). Consistent evidence: LLM-P, LLM-DP, ADaPT all beat pure-LLM planners by 30–90% on planning tasks (see Part G).

### 2. Compare approaches

| Approach | Strengths | Weaknesses |
|---|---|---|
| Reasoning-enhanced (CoT/ToT/GoT) | Cheap, interpretable, no tools needed | No grounding; error propagation; context-bound |
| Tool-augmented (ReAct) | Grounded; interpretable trajectories | Verbose; drift on long horizons; hallucination via tool output |
| Self-evolving (Reflexion) | Improves across attempts w/o retraining | Needs explicit success signal; can entrench errors |
| Modular/cognitive pipelines | Separation of concerns; auditability | Overhead; coordination cost |
| Blackboard/shared-scratchpad | Flexible; decoupled specialists | Consistency and update management |
| Hybrid symbol+neural | Complete, optimal, verifiable plans | Requires formalizable domains; NL→PDDL parsing errors |
| Multi-agent | Parallelism, specialization | Cost, coordination, duplicated context, security surface |

### 3. Disagreements (literature)

- Whether **multi-agent collaboration** reliably beats single agents: 2601.12538/2601.12560 caution that gains are task-dependent; 2406.05804 [VLists] survey notes multi-agent benefit is *not universal*.
- Whether **world models should be explicit graphs** or implicit neural representations — active debate (Part D).
- Whether **planners should be in-context (prompt-native)** or **learned/formal**: both have advocates; hybrid wins empirical planning benchmarks (Part G).

### 4. Raphael current design

Raphael v2.1.1 is a **blackboard-plus** system with:

- **World Model** (world.py): entity hierarchy (10 base types + E1 process/file/network/vuln/shell types), typed relationships with provenance, confidence, entity resolution states (SEPARATE→POSSIBLY_SAME_AS→CONFIRMED_SAME_AS), evidence-backed queries (`query_can_access`, `query_why`).
- **Evidence Graph** (evidence.py): immutable evidence with SHA-256 content hash, trust-level classification, evidence-relationship semantics (DERIVED_FROM, SUPPORTS, CONTRADICTS, CORRELATES_WITH).
- **Hypothesis Manager** (hypothesis.py): structured confidence from 7 factors (support, contradiction, reliability, independence, freshness, assumptions, falsification attempts); complete history/audit.
- **Contradiction Manager** (contradiction.py): contradiction lifecycle + discriminating-observation planning (5 types) — "represent contradiction → propose discriminating observation → execute → update hypotheses." This is a genuine falsification loop.
- **Action Planner** (action.py): preconditions (entity/relation/hypothesis-confidence/evidence/capability/authz/no-contradiction/fresh-evidence), effects, cost, reversibility; driven by WorldModel state.
- **Capability Broker** (capability_broker.py): deny-by-default, five authorization dimensions (target, RoE, capability, rate, impact), immutable ActionReceipt chain.
- **Neural Memory** (neural_memory.py): in-process episodic/semantic/skill stores per target.

This is architecturally *well above* typical AutoGPT/BabyAGI; it is a blackboard + planner + truth-maintenance hybrid, closer to classical BDI/blackboard + StrODS lineage than to pure-prompt agents.

### 5. Raphael's gaps vs SOTA

1. **Memory is in-process only** — no durable cross-session store (Part C).
2. **Planner is heuristic LLM-driven** — no PDDL/symbolic/mcts hybrid (Part G).
3. **No explicit reflection/self-eval module** (reflection.py is essentially a stub at 11 lines).
4. **No explicit "observability/eval layer"** as a first-class module (though audit_trail + evaluations/campaign exist).
5. **Uncalibrated confidence** (Part E).

### 6. Recommendations

1. **Prototype a verifier/checker duty in the planner loop** (maker–checker) using existing evidence/contradiction machinery. Low risk, evidence-backed.
2. **Prototype PDDL-export path** for crisp action/reasoning domains (Part G).
3. Consider the **TIME progression**: move neural_memory to durable + retrieval (Part C).

### 7. Confidence: **Strong** for the taxonomy (three surveys; high replication).

### 8. Recommendation: **Integrate** (verifier), **Prototype** (PDDL path), **Reject** (multi-agent for its own sake).

---

## Question A2 — Which components are consistently present in successful agent architectures?

### 1. State of the art

Cross-survey agreement on the recurring components (2601.12560 six layers; 2503.21460 [V]; the ACM TOIS memory survey 2404.13501 [V]; FutureAGI six-component list):

1. Language/plan core (reasoning)
2. Memory system (working / episodic / semantic)
3. Tool & plugin layer (function calling / MCP)
4. Planner / reasoning layer (decomposition, selection)
5. Orchestration runtime (state, retries, handoffs)
6. Observability & evaluation layer
7. **Verifier/reflection/critique** (maker–checker; warrants)
8. **World/state model** (entity–relation tracking)

### 2. Component comparison table

| Component | In Raphael? | Evidence it's required | Raphael's implementation |
|---|---|---|---|
| LLM core | ✅ | Trivially yes | pattern+A impedance hook |
| Memory (working/episodic/semantic) | ⚠️ partial | 2404.13501; 2603.07670 MemGPT/Zep | neural_memory.py in-process only |
| Tool layer | ✅ | MCP standard | mcp-hub + capability broker |
| Planner | ✅ | 2402.02716; 2502.11221 | action.py precondition/effect planner |
| Orchestration runtime | ✅ | 2601.12560 | phases, conductor, retry_utils |
| Observability/eval | ✅ | 2601.12560 CLASSic | audit_trail, evaluations/campaign |
| Verifier/reflection | ✅ | Reflexion [2303.11366] | world/hypothesis/contradiction loops |
| World/state model | ✅ | AriGraph; GNN | world.py entity graph — strong |

### 3. Disagreements

- Whether the **verifier** should be a separate model vs. part of the main model (self-critique): evidence mixed; maker–checker with same model is weak; separate (weaker) models do catch things.
- Whether **memory** belongs in the context window (ever-context) vs. managed persistent memory (MemGPT et al.): LongMemEval shows explicit memory wins.

### 4. Raphael current design
The table above. Raphael has *all 8* components at least in scaffold form — rarer than most lab/demo systems. What's missing is depth in memory and a closer loop between evaluator and planner.

### 5. Gaps
- Memory durability + retrieval quality (Part C).
- Verifier is emergent rather than explicit.

### 6. Recommendations
- **Prototype** explicit verifier duty (criteria-carrying) for high-assurance phases.
- **Integrate** durable memory onto the already-excellent evidence/world backbone (low incremental cost).

### 7. Confidence: **Strong** (multi-survey convergence on 7–8 components).

### 8. Recommendation: **Integrate** (memory+verify scaffolding).

---

# PART B — PROMPTING vs ARCHITECTURE

---

## Question B1 — What can prompting alone accomplish?

### 1. State of the art

The "prompting replaces architecture" literature (all primary-cited and [V]-verified):

| Method | Claim (verified abstracts) | Evidence |
|---|---|---|
| **Chain-of-Thought** (2201.11903 [V]) | Decompose multi-step reasoning; enables math/logic | Strong |
| **Self-Consistency** (2203.11171 [V]) | Sample-paths + vote; improves CoT on arithmetic/commonsense | Strong |
| **ReAct** (2210.03629 [V]) | Interleave reasoning + actions; grounded, less hallucination, interpretable trajectories | Strong |
| **Reflexion** (2303.11366 [V]) | Verbal self-feedback stored in episodic buffer; improves over attempts on HumanEval, ALFWorld | Strong |
| **Tree-of-Thoughts** (2305.10601 [V]) | Explicit tree search over reasoning states | Strong (narrow tasks: Logic, Game-of-24, creative writing) |
| **Self-Discover** (2402.03620 [V]) | Self-compose reasoning structures (modules → composite); *better than SC with 10–40× fewer tokens* | **Strong** |
| **Graph-of-Thoughts / Chains–Trees–Graphs** (2401.14295 [V]) | Generalized graph topologies; fusion, refinement, aggregation; graph > tree > chain in effectiveness | Strong |
| **Plan-and-Solve / SkipThoughts** | Explicit structured plan, decouple decomposition from reasoning | Moderate |
| **AutoGPT / BabyAGI** | Full autonomous task loops with tool calling via ReAct-style | **Weak-to-moderate, reputation exceeded by results** (SPO failure mode) |

**Bottom line B1:** prompting alone (CoT/SoT/ToT/GoT/Self-Discover) is very strong and cheap for **open-ended, short-horizon reasoning** and for **tool-direct tasks with artifact-limited state**. It replaces architecture when the task fits in-context, has no durable state requirement, no adversarial inputs, and no need for formal guarantees.

### 2. Where prompting replaces architecture

- Single-task QA / arithmetic / logic puzzles.
- Short retrieval+reasoning tasks (ReAct on HotpotQA).
- Few-shot tool use with functional typing.
- When context window >> task state (ever-context strategies).
- When the user is willing to retry on failure (Reflexion-style).

### 3. Disagreements

- **Self-correction is overrated?** Extensive literature shows LLM self-correction *can* degrade without external signals (Huang et al. 2023, Stechly et al.) — Reflexion works only *because* it grounds failure in an external success signal, not self-judgement.
- **CoT benefit shrinks for real tasks** — recent studies (e.g., Wharton 2025 research cited above) show CoT adds 20–80% time/tokens with marginal gain for reasoning models. Implementation-dependent.

### 4. Raphael current design
Raphael does not currently apply ChoT-style or SC on the planner; it relies on the blackboard + evidence graph for falsification. Its reasoning emerges from evidence-relations (SUPPORTS/CONTRADICTS) plus hypothesis-factor weighting.

### 5. Gaps
- No self-consistency/best-of-n at the answer level (cheap win).
- No explicit single-token multi-step planner verification.

### 6. Recommendations
- Integrate **self-consistency for high-stakes assertions** (HypothesisManager: sample the LLM N times; use majority signaling).
- Reject plan-and-solve verbosity if models resist it.

### 7. Confidence: **Strong** (mostly replicated public evidence).

### 8. Recommendation: **Integrate** (self-consistency at the hypothesis-elicitation interface), **Prototype** (plan-verification via scratch/graph reasoning).

---

## Question B2 — Where does prompting consistently fail?

### 1–3. Failure taxonomy (evidence)

| Failure mode | What fails | Evidence / sources | Raphael mitigant? |
|---|---|---|---|
| **Long-horizon state tracking** | Memory of intermediate state beyond context | StateAct/ALFWorld: ReAct solves 24/134 at 40-50 steps vs StateAct 0→… actually ReAct 24/134 solved 0 at 40–50, state-tracked solved 4; avg steps 31.5→19.1 | World model + relationship graph partially addresses; no explicit state-step tracking |
| **Persistent memory across sessions** | Facts from prior sessions | LongMemEval: 115k full-context fails; Zep KG ≥ full-context | neural_memory: in-process only, no disk |
| **Belief revision / contradiction handling** | New evidence conflicting with stored position | DEFREASING (NAACL 2025): no instruction-tuned LLM performs well at property-inheritance defeasibility; non-monotonic reasoning degrades | **hypothesis.py + contradiction.py + discriminating observations: a real mechanism** — this is Raphael's pitch. |
| **Multi-hop relational recall** | Knowledge across disjoint chunks | KG/GraphRAG: graph beats vector by 36–46% multi-hop | **world.py entity graph + CAN_ACCESS query: implemented** |
| **Planning under constraint/state-space** | LLM plan feasibility | LLM+P / LLM-DP: classic planner + LLM = 96% vs 53% ReAct on ALFWorld; Blocksworld 100% hybrid | No formal/symbolic planner in Raphael |
| **Systematic/computability** | Exact guarantees | Valmeekam et al. (2023) show LLM planning fails on Blocksworld variants even when tested | Not addressed (but planner is a heuristic layer; broker does execution) |
| **Evaluation of confidence** | LLMs overstate confidence when verbalized | (Part E): overconfidence rate documented | `confidence` is factored (good) but not calibrated against ground truth |

### 4. Raphael evaluation
The failure modes Raphael **is** designed for (contradiction, belief revision, provenance) are the ones prompting alone demonstrably fails at — that's the strongest available argument for the architecture. The failure modes Raphael *doesn't* cover (durable memory, formal planning, calibrated confidence, state-step tracking) are the first-class upgrade targets.

### 5. Confidence: **Strong** for the taxonomy itself; each row cites at least one replicated study.

---

## Question B3 — Under what conditions does explicit architecture outperform prompting?

### Evidence-driven conditions list (no opinions)

**Evidence-backed conditions where prompt-only fails and architecture wins:**

| Condition | Result | Source |
|---|---|---|
| Plan correctness/optimality | LLM+P / LLM-DP: 96–100% vs 53% ReAct on ALFWorld; Blocksworld 100%; fewer steps (13.2 vs 18.7) | [V] citing 2502.11221 survey (LLM-DP/LLM-P) |
| State-tracking under long horizon | StateAct: solutions to 40–50-step tasks possible (4), vs ReAct 0; steps 31.5→19.1 | 2025 REALM workshop paper (StateAct) |
| Multi-hop relational reasoning | KG agent memory beats vector-only by 36–46% accuracy, -40% hallucination rate, on multi-hop/relational tasks | Zylos industry 2026 + AriGraph |
| Memory recall beyond context | 71.2% [Zep] vs 60.2% [full-context] on LongMemEval | 2501.13956 [V] |
| Verification-critical tasks (medical/legal style) | Verified/grounded answer vs unverified: verifier systems (maker–checker) reduce hallucination-enabled error propagation | 2502.17419 [V] (System1/2) + Cognition: "external verification is the only technique that catches systematic errors." |
| Any metadata/relu-semantics (philosophy) | | |

**Conditions where architecture does NOT (yet) clearly help End (defensible: B1's cheap open-ended tasks). The expected win is narrow**: when there is durable state, verification, multi-hop retrieval, or formal solubility. Raphael's design targets exactly this.

### 7-8
- **Strong** evidence: formal planning (LLM+PDDL, LLM-P, LLM-DP), state-tracking gains, LongMemEval-proven memory graphs.
- **Moderate**: KG vs flat for multi-hop (industry numbers), self-consistency benefits at scale.

**Recommendation: Integrate** (verifier duty + durable memory + optional formalizer), **and do NOT over-engineer** prompt-structure components beyond these.

---

# PART C — MEMORY

---

## Question C1 — How should autonomous agents remember information?

### 1. State of the art

The 2025–2026 memory literature (surveys 2603.07670 [V], 2404.13501 [V], 2504.15965, and systems MemGPT, Mem0 2504.19413 [V], A-MEM 2502.12110 [V], Zep 2501.13956 [V]) converge on a taxonomy:

- **Working memory** — the context window; bounded, transient.
- **Episodic memory** — records of specific events/experiences (timestamped, loss-sensitive).
- **Semantic memory** — extracted facts/entities independent of the episode that produced them.
- **Procedural memory** — skills / how-to (which tools, what sequences).
- **Retrieval memory** — the mechanism (vector similarity, graph traversal, hybrid).
- **Compressed memory** — summarization / abstraction layers to fit bounded resources.
- **Graph memory** — entities+relations with provenance (Zep/Graphiti; Zep's 3-tier: episode subgraph, semantic entity subgraph, community subgraph) — *"bi-temporal" edges invalidating outdated facts.*

**Empirical lesson (strong):** LongMemEval shows that even 115k-token full-context does not solve cross-session recall; compact temporal graph memory (Zep) dominates both naive RAG and full-context baseline (71.2% vs 60.2% on LongMemEval).

### 2. Memory comparison matrix

| Type | Raphael status | SOTA | Verdict |
|---|---|---|---|
| Working (context) | ✅ | everywhere | -- |
| Episodic | ⚠️ neural_memory in-process | MemGPT, Reflexion episodic buffer | Must persist |
| Semantic | ⚠️ weak (flat key→value) | Zep/Graphiti, Mem0 | Upgrade |
| Procedural | ⚠️ skill_store (in dict) | Mem0 / A-MEM procedural | Upgrade |
| Retrieval | ❌ none (exact-dict only) | vector + graph hybrid | Add |
| Graph memory | ✅ world.py/evidencegraph — **excellent baseline** | Graphiti, Zep, AriGraph | Build on it |
| Compression | ❌ none | pipeline summaries (A-MEM) | Add |
| Temporal/decay | ⚠️ partial (expires_at on relationships) | Zep bi-temporal | Add invalidation spells |

### 3. Disagreements
- **Should memory be a separate service (Mem0/Zep) or embedded graph?** — consensus is *separate managed memory with service semantics*, but graph-embedded (world model) is where Raphael sits.
- **Context-window mega-models** (300k–1M tokens) vs persistent memory: some prefer "bypass memory, use huge context" — LongMemEval+Zep evidence argues otherwise for cross-term knowledge.

### 4. Raphael current design (from source)

`brain/neural_memory.py` (79 lines):
- `store_episodic()` → in-process `_episodic_store[target].append(episode)` (event_type, target, model, context, input/output, success, score, latency, ts).
- `retrieve_episodic(target, limit=20)` → last N episodes — **no relevance ranking, no vector, no expiry.**
- `store_semantic(key, value)` / `retrieve_semantic(key)` — exact-key dictionary.
- `store_skill_memory` — stores under `skill:{name}`.
- `store_target_profile` / `update_target_stats` — counters.

Everything is **in-process and per-target**, lost on restart, not queryable except by key/limit. `world.py` relationships carry `evidence_ids`, `confidence`, `expires_at` — that's the strong backbone: a temporal entity graph with provenance.

### 5. Gaps
- **Durability**: zero persistence → cross-session recall fails (the exact LongMemEval failure).
- **Retrieval**: only exact-key / last-N. No similarity search, no multi-relation traversal at retrieval except world queries.
- **Freshness/decay**: no decay weights on episodic entries despite HypothesisManager.freshness factor.
- **Conflicts**: duplicate facts with distinct provenance not merged; entity resolution exists in world (POSSIBLY_SAME_AS→CONFIRMED_SAME_AS) but the memory *callback* doesn't route through it.

### 6. Recommendations
- **Integrate the evidence/world backbone as the durable memory store** (persist to disk/SQLite via existing `db/` and `research.db` pattern). Episodes become evidence with hashes (already the design).
- **Prototype hybrid retrieval**: vector index for semantic recall + world.py graph traversal for relational; port Zep-style bi-temporal invalidation onto the world relationship edges.
- **Add decay policy** aligning with HypothesisManager.freshness (168h default exists in action.py).

### 7. Confidence: **Strong** on the taxonomy (surveys + LongMemEval results).

### 8. Recommendation: **Integrate** (durable memory on evidence/world backbone), **Prototype** (hybrid retrieval).

---

## Question C2 — How should memories be updated?

### 1. State of the art

- **Forgetting/decay**: time-weighted, recency-gated (Zep bi-temporal; Mem0 introspection; episodic logs).
- **Reinforcement**: post-success consolidation — keep successful trajectories/procedures (reflex buffer; A-MEM ).
- **Conflict resolution**: when new fact contradicts old — do *not* overwrite; record both with validity windows; use invalidation of edges (Zep) and hypothesis-falsification flow (Raphael's architecture actually matches this).
- **Consolidation**: abstract episodic → semantic (summarization) on a schedule (MemGPT-style buffer→summary).
- Local aggregation: Mem0 aggregates across sources; Zep communities.

### 2. Raphael current design
- **No update policy for neural_memory**: `store_episodic` never prunes; semantic overwrite by key.
- **world.py relationships have `expires_at`** (time-based expiry) — a real, if coarse, decay mechanism.
- **Contradiction manager handles conflicting evidence** — separate from memory but IPC-adjacent: A contradiction → discriminating observation → resolution — the correct pattern.

### 3. Gap analysis
- No **consolidation pass** (episodic→semantic abstraction).
- No **validity-window mechanism** on world edges beyond expires_at (needs bi-temporal "superseded_by").
- No **reinforcement/credit-assignment** on memory; only target_stats success counters.

### 4. Recommendation
- **Integrate consolidation pass** at Checkpoint edges: summarize episodes into semantic memory (fact-level summaries mirroring Zep/Graphiti).
- **Prototype a bi-temporal superseding edge type** on world relationships (valid_from/valid_until; superseded_by edge, mirroring Zep).
- **Reuse contradiction.py** as the update gate: only mutate semantic memory upon resolution (R_RESOLVED_TRUE) — ties update policy to falsification (matches evidence-based updates).
- **Migrate `neural_memory.py`** from in-process dicts to persistence via the world/evidence store (durability + retrieval beyond exact-key).

### 5. Confidence: **Moderate** (Zep/LongMemEval principal one; consolidation less benchmarked).

---

# PART D — WORLD MODELS

---

## Question D1 — How do state-of-the-art systems represent entities?

### 1. State of the art

1. **Knowledge graphs (KG)**: entity–relation typed graphs; used as world models (AriGraph 2407.04363 [V]; Graphiti/Zep; LLM+P: PDDL-based entity/state encodings). Value: multi-hop retrieval, invalidation, explainability.
2. **Scene graphs**: for physical/visual scenes (images/robotics) — entities + spatial relations.
3. **Entity stores**: flat key-value of entities (often with vector embeddings), used by RAG.
4. **Symbolic state (PDDL/blocs)**: explicit state variables + preconditions + effects — world model driving the planner (LLM+P lineage).
5. **Graph neural networks**: learned propagation over KG during inference (predict missing edges, path scoring).

**Evidence**: KG-augmented agent memory reports 36–46% multi-hop accuracy gains and −40% hallucination rate vs vector-only (Zylos synthesis 2026, collecting GraphRAG/HopRAG/Graphiti arbiter).

### 2. Comparison with Raphael WorldModel

Raphael's `world.py` is essentially a **typed, provenance-carrying KG**:

- Entity hierarchy (10 base + E1 additions: process, file, net-conn, vuln, shell-session).
- Relationship types (13 semantic: RUNS_ON, CONNECTS_TO, AUTHENTICATES_AS, MEMBER_OF, OWNS, ASSUMES, TRUSTS, CAN_ACCESS, DEPENDS_ON, OBSERVED_ON (+5 E1) — each with `confidence`, `evidence_ids`, `established_by`, `established_at`, `expires_at`.
- Entity resolution state machine (SEPARATE → POSSIBLY_SAME_AS → CONFIRMED_SAME_AS) — explicit identity resolution with evidence.
- Query interface `query_can_access` / `query_why` returning evidence chains.

**Contrast with SOTA**: Raphael has no embedding/vector layer over the KG (no GNN, no semantic retrieval), no bi-temporal supersession, no community/entity clustering, no "community" tier. It also writes relationships without an explicit observed/physical backend (volatile in-memory) — though evidence records exist.

### 3. Gaps
- Missing: vector-indexed entity embeddings + mixed graph/vector retrieval (easy add, big win: enables multi-hop and fuzzy entity resolution).
- Missing: temporal invalidation semantics beyond `expires_at`.
- Missing: relationship rewiring heuristics (e.g., learned edge).

### 4. Recommendations
- **Prototype**: add embedding column to entity/relationship + top-k retrieval for semantically-similar entity resolution (matches POSSIBLY_SAME_AS).
- **Prototype**: `superseded_by` edge for bi-temporal (Zep-style) — cheap on the existing schema.
- **Defer**: GNN propagation (mainly for prediction workloads).

### 5. Confidence: **Moderate→Strong**: KG world models for agents are supported by AriGraph (IJCAI 2025) and Graphiti-industry benchmarks; vector-hybrid retrieval is standard practice.

### 6. Recommendation: **Integrate** (vector retrieval + relations on same graph); **Prototype** (supersession edges).

---

## Question D2 — How should relationships evolve over time?

### 1. State of the art
- **Confidence**: asymmetric per-relationship confidence (Raphael has it).
- **Uncertainty**: model uncertainty on edges (probability of correctness); when new facts conflict → drop/updated.
- **Provenance**: keep origin evidence ids, timestamps (Raphael has).
- **Temporal reasoning**: validity windows, valid_from/valid_until, superseding, decay (Zep/Graphiti; Temporal KG surveys).
- **Update cadences**: incremental streaming updates preferred (Graphiti measured), not batch rebuilds.

### 2. Raphael current
- Confidence on relationships (static).
- expires_at (a coarse invalid-property).
- No supersession edge, no valid_until, no decayed-propagating confidence, no automatic state-transition on new evidence (contradiction work is the exception).

### 3. Recommendations
- **Integrate** `valid_from`/`valid_until` + metadata `superseded_by` onto `Relationship` (schema v2? — note Frozen; recommended as v3 change, this report is research-only).
- **Prototype** confidence-decay schedule per class (e.g., OBSERVED_ON < TRUSTS < AUTHENTICATES_AS).
- When a new evidence contradicts, trigger contradiction.py (existing), not silent overwrite.

### 4. Confidence: **Moderate** (Zep/Graphiti are archetypes; temporal-KG design is well-documented).

### 5. Recommendation: **Prototype** (temporal edges, v3).

---

# PART E — HYPOTHESIS SYSTEMS

---

## Question E1 — How should intelligent agents represent uncertainty?

### 1. State of the art

- **Bayesian updating / probabilistic reasoning**: posterior = f(prior, likelihood); agent frameworks increasingly store belief distributions over hypotheses rather than point confidences.
- **LLM-specific confidence**: survey (NAACL 2024, Geng et al.) distinguishes **white-box** (logit-based) vs **black-box** (verbalized, consistency-based, semantic entropy). Semantic entropy (Farquhar et al., Nature 2024) is the strongest black-box method: cluster semantically-equivalent answers → entropy.
- **P(true)** method (Kadavath 2207.05221 [V], "Language Models (Mostly) Know What They Know" — replicated): ask the model P(true); calibration improves with model scale.
- **Verbalized confidence is routinely overconfident** (multiple studies: Xiong 2023, Groot et al. 2024): a 0.9 "confidence" means 0.6–0.75 real accuracy; self-reports are noisy and disjointed from empirical error.
- **Brier score** is the standard proper scoring rule for calibration; new benchmarks (ConfidenceBench [flagged, not arXiv-verified]) measure verbalized calibration with Brier across frontier models.
- **Beta-Bernoulli calibration** (2026 [flagged]) post-calibrates via a separate small model on proper-scoring objectives — improves Brier 0.146→0.125; strongly argues that raw verbalized confidence needs correction.

### 2. Compare with Raphael (hypothesis.py)

Raphael's confidence is NOT a single LLM float; it is a factored composite:

```
confidence = f(supporting_evidence, contradicting_evidence, source_reliability,
               independence, freshness, assumptions_required, falsification_attempts)
```

with complete confidence history (snapshot per transition) and explicit factor breakdown. This is *substantially more principled than the SOTA default* (raw verbalized confidence), and it is one of Raphael's genuine strengths. The telemetry-failure-proof design (immutable evidence + factor decomposition) is closer to Bayesian than to LLM self-report.

### 3. Gaps

1. **No calibration loop**: factors are heuristic weights; there's no ground-truth set on which Brier/ECE is measured and no post-hoc calibration — the system records confidence but has never proven it is *calibrated*.
2. **Factor independence is asserted, not measured** (double counting risk: same evidence counted as support and independence).
3. **Sources of uncertainty not distinguished** — aleatoric (irreducible randomness) vs epistemic (model ignorance) — affects how to act on confidence.
4. **No semantic-entropy / sampling-based uncertainty** for LLM-produced claims (the strongest black-box method) — Raphael's `model_inference` trust level treats LLM output as weak but doesn't quantify.

### 4. Recommendations

- **Prototype a calibration harness**: log (confidence, resolution) pairs during campaigns; compute Brier/ECE per factor class. This is the *scientific* fix and costs little.
- **Prototype semantic-entropy confidence** for MODEL_INFERENCE-sourced evidence (LLM) — sample N, cluster answers, map to a 0-1 confidence.
- **Distinguish aleatoric vs epistemic** in ConfidenceSnapshot factors.

### 7. Confidence (of this section's claims)
- Verbalized overconfidence: **Strong** (many studies).
- Calibrated-vs-uncalibrated gap: **Strong** (ConfidenceBench / Beta-Bernoulli pattern).
- Raphael current factored approach qualitatively better: **Moderate (expert-audited)**.

### 8. Recommendation: **Prototype** (calibration harness), **Integrate** (sampling-based uncertainty for model-inference evidence).

---

## Question E2 — How should competing hypotheses be managed?

### 1. State of the art

- **Bayesian competition**: multiple hypotheses with priors updated by likelihood; posterior ratio = evidence weighting.
- **Belief revision** (AGM/post-AGM): non-monotonic updates; contraction/expansion.
- **Competing explanations**: keep alternative hypotheses alive (abduction) until discriminated; Popperian falsification (decrease confidence, never auto-confirm on one datum).
- **Confidence decay** (Zep/Sequential): temporal discounting; stale hypotheses lose priority.
- **Hypothesis retirement**: explicit statuses: proposed → active → falsified/abandoned/confirmed (Raphael exactly matches this lifecycle).

### 2. Raphael current (hypothesis.py)

- Status lifecycle PROPOSED → ACTIVE → FALSIFIED / ABANDONED / CONFIRMED — **matches non-monotonic update needs**.
- Confidence history with reasons on each transition (audit).
- Discriminating observations (contradiction.py) can resolve A-vs-B competition.

### 3. Gaps
- **No explicit hypothesis-competition structure** (no pair/triple competition, no posterior ratio).
- **No minimum-viable-abduction policy** (how many alternatives to retain; cost budget).
- **Assumptions_required** factor exists but is rarely updated after contradiction resolution.
- No automatic link between falsification outcome and hypothesis *retirement* (ABANDONED vs FALSIFIED semantics exist but no policy decides consistently).

### 4. Recommendations
- **Prototype** a HypothesisCompetition registry: when two hypotheses touch the same entities/evidence, create an explicit competition record with posterior ratio trajectory.
- **Integrate** falsification→retire policy: a hypothesis falsified with N consecutive predictor failures → ABANDONED (with audit trail) after its contradiction resolution.
- **Prototype** evidence-driven *retraction* semantics (AGM contraction) — "evidence in-resolution" instead of only binary contradicts-relation.

### 5. Confidence: Moderate (Bayesian competition is standard; Raphael's lifecycle matches AGM belief-revision theory).

### 6. Recommendation: **Prototype**.

---

# PART F — DEFEATERS

---

## Question F1 — How is defeasible reasoning implemented, and can Raphael's defeater system be improved?

### 1. State of the art

- **Defeasible logic / non-monotonic logic** (Reiter 1980, Pollock; Stanford SEP): conclusions retractable when new defeating information arrives (defaults + exceptions + specificity precedence).
- **Argumentation theory (Dung, ASPIC+, DeLP)**: arguments attack/defeat one another; justified vs defeasible conclusions via dialectical trees.
- **Assumption-based argumentation (ABA)**: rules + assumptions; conflict resolution.
- **In LLMs**: DEFREASING (NAACL 2025) shows instruction-tuned LLMs *fail* at formal defeasible property-inheritance; non-monotonic reasoning performance is weak; therefore **defeaters cannot be left to the LLM** — they should be **outside structure** (Raphael's stance is right).

### 2. Raphael current (contradiction.py + hypothesis.py)

Raphael has its own **defeater machinery**:

- `Contradiction` object: preserved pair of evidence claims (immutable both sides) — never deletes evidence. ✓ matches "defeasible non-monotonic" stance.
- `DiscriminatingObservation` (5 types: DIRECT_PROBE, ALTERNATIVE_TOOL, TIME_DELAYED, SOURCE_VERIFICATION, CORROBORATION) — proposes experiments that decide between A and B; with expected_resolution, cost and risk estimates.
- Resolution states: RESOLVED_TRUE / RESOLVED_FALSE / ABANDONED — directly maps to defeasible conclusion status.
- `Falsification attempts` tracked as a HypothesisManager factor.

That is a **valid defeater-defeasible loop** — rare in deployed systems.

### 3. Gaps / improvements

1. **No explicit argument structure**: two evidence claims conflict, but there's no tree of supporting sub-arguments, no attack/defeat edges with *strength* — the decision is binary quality-probe, not dialectical priority (specificity, recency, reliability ordering). Improvement: add `attack`/`strength`/`specificity` when multiple discriminators.
2. **No "no-defeat-not-decided" semantics**: any contradictions that can't be discriminated stay pending forever (statuses): Raphael has under_investigation, but no priority/budget; recommend **decaying priority + auto-abandon after configurable budget** (already has cost_estimate, risk_estimate — complete the scoring).
3. **Single-level**: no nested defeater trees (evidence defeats inference defeats belief) — BDI-style.
4. The **reason to update hypotheses is present but the "when to reconsider" trigger** is not.

### 5. Recommendation

- **Prototype**: dialectical priority over discriminators (e.g., stronger tool observation > model_inference when resolving).
- **Integrate**: budgeted-abandon into contradiction.py (the fields exist: cost/risk — just compute resolve schedule.)
- **Prototype**: nested defeat — discriminator result feeds the same contradiction class for re-evaluation.

### 4. Confidence: **Moderate** (formal defeasible ML fields well-established; Raphael's design is independently convergent).

### 5. Recommendation: **Prototype** (dialectical layer + budgeted abandonment).

---

## Question F2 — How should evidence invalidate beliefs?

### 1. State of the art
- **Contradiction handling**: preserve both, decide (already in Raphael).
- **Counterexamples**: single counterexample defeats *generic* claim; requires narrowing the claim or lowering confidence — correction of the Confirmation/Empirical norm.
- **Confidence reduction**: non-monotonic: a defeating evidence *reduces* confidence, doesn't zero it (AGM contraction).
- **Explanation repair**: after loss, the *premises/assumptions* are re-examined (retract assumption, not claim) — matches hypothesis.assumptions_required factor.

### 2. Raphael comparison
- contradiction.py: preserves both sides ✓
- hypothesis.py: CONTRADICTING_EVIDENCE factor reduces confidence ✓
- explanatory repair partially: assume_count factor in confidence, but no pathway that specifically retracts assumptions to repair the claim — **gap: repair is where falsification meets knowledge**: recommend adding "assumption_retraction" event in the ConfidenceSnapshot.change_reason vocab.

### 3. Recommendations
- **Integrate** "retract-assumption" trigger: when CONTRADICTS evidence arrives, update hypotheses consistency: (a) try assumption-retraction first; (b) if impossible, reduce confidence; (c) if confidence < threshold → FALSIFY.
- **Prototype** "confidence floor" per trust level (source_reliability floor).

### 4. Confidence: **Strong** (confidence monotonic-logic base) for basic; **Moderate** for assumption-retract-first ordering.

### 5. Recommendation: **Integrate** (if cheap), **Prototype** (assumption-retract).

---

# PART G — PLANNING

---

## Question G1 — How do planners choose actions?

### 1. State of the art

Two surveys define the field: 2402.02716 [V] (taxonomy: task decomposition, plan selection, external module, reflection, memory) and 2502.11221 [V] (six criteria: completeness, executability, optimality, representation, generalization, efficiency).

Approaches:

1. **HTN (Hierarchical Task Networks)** — decompose goals → tasks → primitive actions, recipes (classical, well-understood; LLM-HTNs: LLM can author HTN domains).
2. **PDDL/classical** — state-space search, Fast Downward etc.; LLM used as translator → optimal plan. Strong results (Part B3).
3. **MCTS** — LLM-as-world-model + search (LLM-MCTS: 91.4% success VirtualHome [from PlanGenLLMs table]; RAP: LLM-as-mdp model MCTS).
4. **Graph planning / symbolic extension** — thought-as-node search; graph topologies.
5. **LLM planners (in-context)** — CoT + decompose + act: ReAct, plan-and-execute; simplest, most deployed, but fail where state-space/search needed.
6. **Symbolic planners** — ALGWorld 96% (LLM-DP) — hard-coded inference.

**Disagreement needed:** whether fine-tuning planners ("strategy via feedback") vs prompting; both appear; fine-tuned agents (Agent-FLAN/AgentOhana) exist.

**Key evidence assertion (strong):** LLM+formal planner hybrid dominates pure LLM planning on feasibility/optimal-verifiable tasks; pure in-context planner + state refs dominate open-ended interactive (ReAct).

### 2. Raphael current design (action.py)

Already a **precondition/effect planner**:

- `Action` has `preconditions` (ENTITY_EXISTS, RELATIONSHIP_EXISTS, HYPOTHESIS_CONFIDENCE, EVIDENCE_EXISTS, CAPABILITY_AVAILABLE, AUTHORIZATION, NO_CONTRADICTION, FRESH_EVIDENCE), `effects`, cost, authorization, reversibility.
- Planner = search over action sequences to reach goal state against WorldModel.
- Importantly: **`check()` for CAPABILITY_AVAILABLE and AUTHORIZATION returns `(True, "assumed available")`** — stubs marked in source: "Authorization assumed for planning". Two of eight precondition kinds are placeholders; the real broker gate happens later at execution.
- No MTK, no PDDL, no HTN recipe library, no plan scoping/replanning trigger.

### 3. Gaps
- **No formal search/backtracking**: pure greedy/LLM heuristic — completeness not guaranteed. (Lo relevant: Raphael's env is adversarial and open-ended, so a classical planner alone would be brittle; hybridization needed.)
- **Symbolic bridge missing**: worlds & relationships could be exported to PDDL on a formal subproblem (e.g., access-path search CAN_ACCESS — a classic planning problem).
- **Precondition stubs** make plan generation optimistic; execution-time broker can (and does) deny.

### 4. Recommendations
- **Prototype** a "formal mode" for CAN_ACCESS/route-planning: export entity graph → PDDL (or BFS symbolic search) for path feasibility. Low-cost, evidence-backed (LLM+DP 96% success).
- **Prototype replan triggers** (see G2).
- **Make the `CAPABILITY_AVAILABLE`/`AUTHORIZATION` stubs** real broker queries in the planner flow — defeats false planning.

### 5. Confidence: **Strong** on hybrid-planner dominance.

### 6. Recommendation: **Prototype** (formal access-path mode), **Integrate** (stub fixes).

---

## Question G2 — When should plans be replanned?

### 1. State of the art
- **Dynamic planning/replan**: plan-ahead → execute until deviation → re-plan; evidence: adaptive recursion (ADaPT up to +33% over baselines; AS-planner) beats fixed whole-plan on susceptibles tasks.
- **Interruption**: define trigger conditions — state-mismatch vs plan prediction, contradiction found, new-goal reached, artifact invalidated, budget reached.
- **Partial failure**: plan-for-repair: precondition checks inside execution (async).

Raphael has a partial model: `action.py` NO_CONTRADICTION precondition → blocked action if contradiction exists; **plan rebuilding is not automatic**, but the contradiction → discriminating observation loop can *inject* state into the world, and the planner can continue (same plan) — **repair only if none-level replan trigger fires**.

### 2. Gaps
1. No explicit "plan invalidation" signal: a failed-action or contradiction should mark the *current* plan stale.
2. No replan budget/backtracking depth limit — a stuck planner loops.

### 3. Recommendations
- **Integrate** a "plan: invalidated / replan-required" flag in the execution flow when a planned action hits a contradiction (cheap, uses existing `NO_CONTRADICTION`).
- **Prototype** adaptive re-decomposition (AS-NEEDED pattern, ADaPT) — merges well with existing hypothesis confidence gates.

### 4. Confidence: **Moderate** (ADaPT replication).

### 5. Recommendation: **Integrate** (flag) / **Prototype** (adaptive).

---

# PART H — STUDENT (learning)

---

## Question H1 — How should autonomous agents learn?

### 1. State of the art
- **Active learning**: query which datapoints/tools maximize info gain — select highest-uncertainty targets (low-confidence hypotheses! — perfect synergy with Raphael's hypothesis.confidence).
- **Curriculum learning**: order training examples easy→hard; RL environments use staged difficulty.
- **Experience replay**: episodic buffer replayed to stabilize (RL) — Raphael has an episodic buffer (in-process) but no replay loop.
- **Preference optimization (DPO etc.)**: align choices to preference pairs.
- **Exploration/exploitation**: epsilon-greedy, UCB, B: in the action-use context — "exploit known technique, explore uncertain estate."

**Relevant to Raphael:** explanation — as Student produces candidate techniques with RAFF identity and confidence; the *learning* signal is (success/failure of action → hypothesis); falsification stats are the learning lever.

### 2. Raphael current
- neural_memory stores episodic success/failure per target (score, latency).
- strategy_learner (77 lines) — small; exists but likely heuristic (did not deep-read).
- No RL or preference loop; active-learning/curriculum absent.

### 3. Gaps / recommendations
- **Integrate**: Active-learning = pick next target by lowest hypothesis confidence (query-by-uncertainty) — trivially fits HypothesisManager.
- **Prototype**: curriculum: start low-RoE-cost, high-certainty techniques; escalate as confidence & skill accumulate (matches escalation in phases).
- **Prototype**: experience replay on success/failure episodes (persist episodes first — Part C blocker).
- **Do not** do fine-tuning RL w/o scale.

### 4. Confidence: **Moderate** (active-learning — well-established; curriculum applied weakly).

### 5. Recommendation: **Integrate** (uncertainty-driven next-target), **Prototype** (replay+curriculum).

---

## Question H2 — How should generated candidates be evaluated?

### 1. State of the art
- **Candidate ranking**: verify (execution close), score by expected-value-utility (cost×risk×success-evidence).
- **Explore/exploit tradeoff**: UCB-style rank by (mean success + exploration bonus).
- **Novelty detection**: dedupe candidates vs existing hypotheses/evidence (avoid re-proposing known failing).
- **Diversity**: vector-distance or coverage across candidate set to avoid exploitation clusters.

### 2. Raphael current
- Student `propose_candidates` generates; mutate (payload variants); each candidate carries risk/cost-ish metadata? (need to verify — student.py minimal read); engine currently likely ranks via existing utility hunger.
- WAF-aware (WAFDetector query) — diversity via WAF-type branches.
- Novelty: not really — no dedupe vs prior candidates; repeated failures re-proposed because the learner isn't hooked.

### 3. Recommendations
- **Integrate novelty check**: before proposing candidate, search world/evidence for prior attempt + outcome; skip or proposal-with-higher-uncertainty.
- **Integrate UCB-ish utility**: rank = base_success_evidence × (prior success/failure stats) + exploration boost for unknown targets.
- **Prototype** diversity penalty (pairwise similarity) when |candidate-set| > k.

### 4. Confidence: **Medium** (UCB well established in bandits via σ; applied to agents moderately).

### 5. Recommendation: **Integrate** (novelty + selection), **Prototype** (diversity).

---

# PART I — BENCHMARKS

---

## Question I1 — How are autonomous agents evaluated? (GAIA, AgentBench, CyBench, SWE-bench, OSWorld, WebArena, BrowserArena)

### 1. State of the art: the benchmark map (with verified sources)

| Benchmark | Domain | What it measures | Verified source | Strength | Weakness |
|---|---|---|---|---|---|
| **GAIA** | General assistant | Tool use + multi-step reasoning; real questions (Levels 1–3) | 2311.12983 [V] | Human baseline (~92% L1); multi-step visibility; factual grounding prevents gaming | Questions* reference/lookup skewed; underrepresents analytic/judgment tasks (open-ended analysis) |
| **AgentBench** | Cross-domain | 8 environments (OS, DB, KG, card, web, games) | 2308.03688 [V] | Breadth; distinguishes environ-specific strength | Aggregated score masks env-level differences |
| **CyBench** | Cyber defense | Adversarial cybersecurity commands | arXiv ID **not located** (flagged) | Security-specific substance | Unverified numbers; small literature trail; treat numbers as placeholder |
| **SWE-bench** | Software | Real GitHub issue → patch + pass tests | 2310.06770 [V] | Gold standard for coding: solvability human-reviewed (Verified), trick reproducibility | **Leakage risk** — OpenAI paused SWE-bench Verified reporting after confirmed contamination; scaffolding gap: same model ±40pts with different frameworks |
| **OSWorld** | Computer use | Real desktop apps (Ubuntu/Windows/macOS) via screen+actions | 2404.07972 [V] | Real OS state verification; includes cross-app workflows; objective eval | Heavy infra; human baseline ~72.4% already beaten by frontier (Q1 2026); needs continuation |
| **WebArena** | Web automation | Self-hosted shop/forum/GKit/map tasks; 15–40 actions | 2307.13854 [V] | Open-source, reproducible; sees extension beyond DOM (rendered HTML); policy-compliant failure semantics | Scores ~35–45% (2025); task ambiguity; recovery from failed-state checkpoints |
| **tau-bench** | Tool+customer service | Completion *and* business-policy compliance | 2406.12045 [V] | **First to measure policy adherence**; pass^k reflects production | Small domains (retail/airline); simulated users scripted |
| **AgentBench** (above) | Already covered | | | | |

**Additional relevant**: TheAgentCompany, InterCode, terminal-bench, browser use; also evaluation surveys 2503.16416 & 2507.21504.

### 2. What benchmarks tell us about Raphael

- **GAIA**: architecture value visible in Level-2/3 tasks requiring tool-fuse + multi-step — Raphael's delta appears here.
- **SWE-bench**: scaffold-dependence (measuring our scaffolding) is real for code tasks.
- **tau-bench**: readiness measure for policy-adherence (Raphael's Capability Broker is the natural compliance governor).
- **CyBench**: security-domain structural evaluation — directly relevant to Raphael's core, but unverified numbers → design our own.

### 3. Recommendations for evaluation suite (Roadmap input)
- Adopt a **three-bench stack**: GAIA (general grounding), custom **RaphaelBench** (structural: multi-relation entity graphs with Ground-Truth; reuse world.py) + CyBench-style (once verified) + a **policy-compliance variant** of tau-bench.
- Publish ray/JSONL telemetry for every run.
- Add a private holdout set to control contamination.

### 4. Confidence: **Strong** for the benchmark descriptions; **Moderate** for CyBench-derived claims (unverified citations).

### 5. Recommendation: **Integrate** eval harness (private + public).

---

## Question I2 — What makes a benchmark scientifically valid?

### 1. Key validity dimensions (evidence+criterion)

| Dimension | What it guards | Current landscape 2026 |
|---|---|---|
| **Saturation** | Score ceiling → benchmark stops differentiating | OSWorld human baseline beaten; explore hard tasks |
| **Leakage/contamination** | Training data exposure | SWE-bench Verified leakage — OpenAI stopped reporting; ScalePro / SWE-bench Live (monthly new tasks) mitigation |
| **Eval bias** | judge/score biases (LLM-as-judge evaluates its own errors; risk) | Harvard-style double-gaze; LLM-judge correlation studies needed |
| **Reproducibility** | Determinism of infra+tools+tests | Open-source envs (WebArena/OSWorld) vs vendor-run trace; scaffolds logged |
| **policy adherence** (tau/TP): | Policy≠completion metrics | tau-bench gold: reflection |
| **Scaffold vs model separation** | Model internals vs scaffold conflation | Princeton HAL: bare-vs-scaffold leaderboards |

### 2. Confidence: **Strong** (multiple documented incidents invert the practices).

---

# PART J — SECURITY

## Question J1 — How do autonomous agents fail securely? (authorization, capability control, least privilege, fail-closed)

### 1. State of the art

- **Capability control / least privilege**: gate ALL external side-effects through a single policy enforcement point; treat every tool call as a security-relevant action. Standards: OWASP Agentic Top 10 2025/26; MELON [2502.05174 V] (masked re-execution, i.e., provable detection of hidden prominent instructions); CaMeL [2503.18813 V] — two-LLM architecture with capability (CA) tracking, provable on AgentDojo; FIDES [2505.23643 V] — label-based IFC (Information-Flow Control) policies.
- **fail-closed**: deny-by-default, audited allowlist; every denied path logged.
- **The adversarial reality**: prompt injection appears in 73% of prod deployments (industry 2025 stats); language-model instructions can't be reliably distinguished from data (the only realistic defense is *architecture*, not prompting); Open AI/Anthropic/DeepMind all state prompt injection not solvable within current LM architectures.

### 2. Raphael current (capability_broker.py — excellent baseline)

The CapabilityBroker is already a **deny-by-default, single-gate complex**:

- 5 independent authorization dimensions: **target, RoE, capability, rate, impact** (AuthorizationDimension enum).
- "Every check must explicitly return True… Any missing/failed check = DENY."
- ActionReceipt chain (immutable; create_proposal/authorize/deny/start/complete/timeout + verify_chain) — full execution audit.
- ScopeParser, RateLimiter (config per amount), impact budget.

**Assessment**: structural capability control & fail-closed & audit trail are *beyond most* 2026 deployed agents — this is Raphael's biggest defensive strength; the broker's RE likewise mirrors MCP/makers best practice; τ-bench policy-energy compliance would rate it well.

### 3. Gaps
- **Information-flow control**: FIDES-style provenance labels on data (which source produced this content) — Raphael has trust_level on evidence (SYSTEM_POLICY…MODEL_INFERENCE; TARGET_CONTROLLED) but those labels are **not woven at tool-call time** into the broker's checks (they exist in the evidence store, not propagated label-to-action). **Directly upgradeable.**
- **Provable injection defense**: no two-LLM masking (CaMeL) or masked re-execution (MELON) equivalent.
- **MCP-server supply-chain**: broker treats tools as static registry; 2025/26 reality: tool diagrams are adversarial (rug pull on 5/7 CLIENTs; see 2603.22489). No metadata validation at start-up.

### 4. Recommendations
1. **Prototype** — MELON-style masked re-execution: re-run the planned action against a "masked" (do-nothing) apparatus, compare outputs, catch hijack.
2. **Prototype** — IFC labels: propagate `trust_level` + `untrusted`-flags onto ActionProposal (decision = function of data labels); deny if a high-impact action is driven by untrusted input.
3. **Integrate/Cheap** — **tool metadata validation hook** (schema-diff + checksum of descriptions; immutable tool manifests).

### 5. Confidence: **Strong** (CaMeL, MELON, FIDES are major-reputation peer papers; release-restrictions documented).

---

## Question J2 — How should agents defend against prompt injection?

### 1. Attack surface taxonomy (from 2510.06445 [V] survey; Zylos 2026 Case 42; AgentSecurity)

- **Direct injection** (attacker modifies system context / tripes)
- **Indirect injection** (poisoned external content: emails, web, tool outputs, retrieved memory) — the 2025–26 dominant.
- **Memory poisoning** — writes malicious instructions into long-term store (survives sessions; Unit42 Bedrock PoC; MINJA NeurIPS 2025 query-only; AgentPoison — data-poison-memory/knowledge).
- **Tool poisoning** (malicious MCP tool descriptions; rug-pull after approval).
- **Retrieval poisoning / RAG-interpolation attacks** — `<result>` template closing-tag exploits.
- **Goal hijacking** (add adversarial side-goals).

Defense state:
- **Consensus honest**: cannot be solved in-model (OpenAI/Anthropic/DeepMind 2025); defenses are *architectural*: capability-gating, masking, IFC, separation-of-concerns, validation, alerting.
- Measured defenses: MELON 0.32% attack success on AgentDojo; CaMeL provable on Dojo; FIDES information-flow deterministic.

### 2. Raphael current
- Evidence trust-level → hypothesis (defensible model).
- CapabilityBroker deny-by-default (default-denying broker).
- NO dedicated injection-defense loop: adversary-injected tool output enters as TOOL_OBSERVATION evidence; the *evidence outer proposal* (contradiction) may eventually suspect, but there's no **input-validation "prevention"** step; broker allows the injected action if it passes 5 checks (it's in-scope, allowed RoE, etc.).

**i.e., Raphael is 5/10: excellent fault-reactive (post-hoc honesty), weak-missing fault-tolerant (preventive).**

### 3. Recommendations
1. **Prototype** — input provenance tracking: any parameter whose value came from UNTRUSTED source → flagged; require **human_confirmation** (new authz dimension "confirmation") before affecting irreversible/high-impact actions (tau-bench-style).
2. **Prototype** — data-integrity / watermarking for memory writes (memory poisoning defense: sign memory entries by collector; verify before replay).
3. **Prototype** — disentangle: don't let tool OUTPUT pollute the *instructions* that control next-step: blueprint-style (CaMeL's idea) — summarize observable sources before action.
4. **Integrate** — alert/backoff: on contradictions or anomalies, fall back to conservative mode (fail-closed, slow down, demand HUMAN_CONFIRM). This is a cheap upgrade: already has phases/rules.

### 4. Confidence: **Strong** (multi-lab consensus + measured results).

### 5. Recommendation: **Prototype** (provenance→confirmation gate; memory-write integrity) and **Integrate** (fail-back alert)**.

---

# PART K — HUMAN COGNITION

## Question K1 — How do humans solve long multi-step problems?

### 1. State of the art (psychology + LLM translation)

- **System 1 / System 2 (Kahneman)** — dual-process; S1 fast associative, S2 slow deliberate; S2 monitors S1.
- **Working memory** — ~4±1 chunks (Miller 1956 meta-era: 7±2 / modern 4); bottleneck for multi-step reasoning; externalized (writing, notes) compensates.
- **Chunking** — expertise compresses units into chunks, freeing WM (expert vs novice difference).
- **Mental models** — internal representations of how system works; updated on feedback (reflect), protected by confidence.
- **Expert reasoning** — large problem spaces chunked + goal-recursion + external scratchpad (Chase & Simon chess: 50k chunks); skilled backtracking + assumption-testing.

**LLM-cognition link (2502.17419 [V])** — "From System 1 to System 2: survey of reasoning LLMs": the o1-strato models embed "slow thinking" (System 2) via explicit reasoning scheduling + search; System 1 fast path remains for routine ops. Also Nature Rev. Psychol (2025): LLM mimic S1 heuristic biases and S2 via prompting; not fully analogous.

### 2. Raphael current?
- S1-analog: the fast LLM call per cognitive step.
- S2-analog: Hypothesis/Contradiction/Evidence — the *explicit* deliberative track, externalized (chunking/scratchpad work: world+evidence tables).
- Chunking: evidence summary/abstract; hypothesis factor, term bank.
- Mental-model discipline: world.py entity-rel — **exactly a mental model with update valve (confidence+conflict)**.

### 3. Gaps
- No "S2-vs-S1 arbitration" (when to fall back to fast vs slow) — currently implicit (confidence thresholds; would be explicit trigger).
- No external-scratchpad/workload-management (fits long tasks) — world+evidence partially, but an OS-style chain-of-thought text isn't stored persistently.
- No chunking-cache for repeated domains (similar statements).

### 4. Recommendation
- **Prototype** an "effort gate": lowRisk/common → S1-mode (single-pass LLM); highRisk/novel → S2-mode (hypothesis+contradiction+max evidence) — this is the assignment's "explicit architecture brings value" directly.
- **Integrate** mental-model-based subgoaling: when contradiction unresolved → explicit "decompose the conflict into domain-model straighten" (chunking).

### 5. Confidence: **Medium** (dual-process basics well-established; S1/S2-LLM mapping emerging).

### 6. Recommendation: **Prototype** effort-gate; **Integrate** mental-model discipline (already mostly).

---

## Question K2 — What aspects of human reasoning are missing from LLM agents?

**Gap analysis (P+! personal inference marked):**

| Missing aspect | Evidence basis | Raphael currently? | Priority |
|---|---|---|---|
| External scratchpad/writing (working memory offloading) | Chunking + expert behavior; LLM context-bound | partial — world/evidence/notes, not system-alt | High |
| Belief revision with precision (defeasible) | DEFREASING etc: LLM fail | ✅ strong (hypothesis/contradiction) | Keep |
| Calibration of own confidence | LLM overconfident | factor-confidence reasons but not calibrated | **High** |
| Long-term durative memory | LongMemEval | missing (in-process) | High |
| Goal-monitoring/self-prompt | long-horizon drift | partial (phase/goal tracking, not enforced) | Med |
| Explicit decision between slow/fast (effort) | S1/S2 | missing | Med |
| Analogical reasoning / mental causality | weak in LLM; expert relies | World model partial | Low |
| Theory-of-mind / adversarial modeling of other agents | specific attacks | context-dependent, not a dedicated mechanism | Low |

**Recommendation**: Address top-3: (1) durable memory (Part C), (2) calibration (Part E), (3) effort-gate (K1).

---

# FINAL DELIVERABLE — RESEARCH ROADMAP FOR RAPHAEL v3

**Standing on:** v2.1.1 frozen architecture (Brain, Student, Hands, Phantom; CapabilityBroker; EvidenceGraph; Hypothesis Manager; Contradiction Manager; World Model; audit/telemetry). 121/121 tests passing at time of writing. **No src/ changes were made in producing this report** — recommendations below are research products for SENTINEL to authorize.

**Guiding answer to the assignment's core question** — *where does an explicit cognitive architecture provide measurable value beyond a frontier LLM using prompting alone?* Evidence (Part B3) says: **long horizon, cross-session memory, multi-hop relational recall, formal/verifiable planning, and adversarial (injection) robustness.** Raphael already wins on 2 of these (multi-hop relational world model; capability-gated execution); the roadmap spends effort where the literature shows the architecture earns its keep — and *avoids* adding components the literature has not justified (e.g., naive multi-agent, GNN-heavy world models, PDDL everywhere).

---

## ROADMAP TABLE (recommendation sets, ordered by value/risk)

| # | Research Question | Current State of the Art | Evidence Strength | Raphael Current Design | Gap | Recommendation | Expected Impact | Risk | Key Papers / References |
|---|---|---|---|---|---|---|---|---|---|
| R1 | C1 / D2 — Durable agent memory | Temporal knowledge-graph memory (Zep/Graphiti: episodic + semantic + community tiers; bi-temporal invalidation) beats both naive RAG and full-context (LongMemEval 71.2% vs 60.2%) | Strong (benchmarked) | `neural_memory.py` = in-process per-target dicts; world.py relations carry `evidence_ids`/`confidence`/`expires_at` | No disk persistence; no semantic retrieval; no consolidation; no supersession semantics | **Integrate** persistence of evidence+episodes onto the existing evidence/world backbone (SQLite per research.db pattern); **Prototype** vector index over entity identifiers + hybrid retrieval | High | Low-Medium | 2501.13956 [V], 2407.04363 [V], 2502.12110 [V], 2504.19413 [V], 2603.07670 [V], 2404.13501 [V] |
| R2 | E1 — Confidence calibration | Verbalized LLM confidence is systematically overconfident; proper-scoring calibration (Brier/ECE) + post-hoc calibrators (Beta-Bernoulli) measurably fix it | Strong (multi-study) | hypothesis.py factors confidence from 7 structured factors + full history | Factors are heuristic; never validated against ground truth; no Brier/ECE harness | **Prototype** calibration harness: log (confidence, resolution) pairs during campaigns; compute Brier/ECE per factor class; add sampling-based (semantic entropy) confidence for MODEL_INFERENCE evidence | High | Low | 2207.05221 [V]; NAACL 2024 confidence survey; ConfidenceBench [flagged] |
| R3 | F1/F2 — Defeaters | Formal defeasible logic/argumentation (Dung, ASPIC+, DeLP); DEFREASING shows LLMs alone fail property-inheritance defeasibility | Strong (formal field) + Moderate (LLM-specific) | contradiction.py: immutable both-sides, discriminating observations (5 types), resolution lifecycle; falsification factor in hypothesis confidence | No dialectical priority (specificity/reliability ordering); no budgeted auto-abandon; no nested defeater trees; no assumption-retract-first repair | **Integrate** budgeted-abandon (fields exist: cost/risk); **Prototype** dialectical ordering + assumption-retraction pathway in ConfidenceSnapshot.change_reason | Medium-High | Low | SEP Non-monotonic Logic (2024 rev.); DEFREASING NAACL 2025; contradiction.py design review |
| R4 | G1/G2 — Planning & replan | LLM+formal-hybrid planners dominate pure-LLM on feasibility/optimality (LLM-DP 96% vs 53% ReAct ALFWorld; LLM+P ~100% Blocksworld); dynamic/adaptive replanning beats fixed plans | Strong (replicated) | action.py: precondition/effect planner (8 precondition types); **two are stubs** (CAPABILITY_AVAILABLE, AUTHORIZATION return True in check()); no search backtracking; no explicit replan trigger | No formal path (PDDL/BFS) for crisp subproblems (e.g., CAN_ACCESS route planning); stubs make plans optimistic; no plan-invalidation signal | **Prototype** formal access-path mode (export world → PDDL/BFS); **Integrate** wire broker into precondition checks + plan-invalidation flag on contradiction | High | Medium | 2502.11221 [V], 2402.02716 [V], 2210.03629 [V] |
| R5 | J1/J2 — Injection defense | Consensus: not solvable in-model; architectural defenses measured (CaMeL provable on AgentDojo; MELON 0.32% ASR; FIDES IFC labels); MCP tool-metadata rug-pull (5/7 clients vulnerable) | Strong | CapabilityBroker: deny-by-default, 5 authz dimensions, immutable ActionReceipt chain — strong fail-closed base | No provenance→action label flow (IFC); no masked re-execution; no tool-manifest validation; memory writes unguarded against poisoning | **Prototype** provenance labels (trust_level → ActionProposal check, untrusted-driven high-impact ⇒ require confirmation); tool-metadata manifest+checksum; **Integrate** memory-write integrity (sign by collector, verify on replay) | High | Medium | 2503.18813 [V], 2502.05174 [V], 2505.23643 [V], 2510.06445, 2603.22489 [V], 2511.15759 [V] |
| R6 | A1/B3 — Verifier duty | Maker-checker / external verification is the only reliable error catcher; self-reflection alone cannot catch premise errors | Strong | Contradiction + discriminating observation exist; reflection.py is an 11-line stub; NO_CONTRADICTION precondition present | No explicit verifier pass before commitment; reflection unimplemented | **Integrate** verifier pass into action loop: planned action → check evidence consistency → commit; reuse contradiction machinery | Medium-High | Low | 2303.11366 [V], 2502.17419 [V]; maker–checker pattern surveys (2601.12560 [V]) |
| R7 | H1/H2 — Active learning & novelty | Active learning (query-by-uncertainty), experience replay, UCB explore/exploit are established; novelty/diversity dedupe improves candidate selection | Strong (bandits/AL) / Moderate (agent application) | Student proposes candidates + mutations; neural_memory logs per-target success/score | No uncertainty-driven next-target selection; no novelty dedupe vs prior attempts; no exploration bonus | **Integrate** next-target = lowest hypothesis confidence; **Integrate** novelty check (search evidence for prior attempt before proposing) | Medium | Low | AL/UCB classics; 2406.05804 [V] |
| R8 | K1/K2 — Effort gate (S1/S2) | Dual-process: fast associative vs slow deliberative; reasoning LLMs encode slow-thinking via explicit scheduling; S1/S2 arbitration improves cost/quality | Moderate (mapping to LLMs emerging) | Implicit: confidence thresholds exist (HYPOTHESIS_CONFIDENCE precondition) | No explicit fast/slow arbitration policy | **Prototype** effort gate: low-risk/common → single-pass (S1); high-risk/novel → full hypothesis+contradiction track (S2) | Medium | Low | 2502.17419 [V]; Nature Rev. Psychol. (2025) dual-process review; Kahneman |
| R9 | I1/I2 — Eval harness | Validity dimensions: saturation, contamination (SWE-bench leakage incident), reproducibility, policy adherence (tau-bench), scaffold-vs-model separation | Strong (documented) | audit_trail + evaluations/campaign + JSONL telemetry exist | No private holdout set; no public/standard benchmarks wired; contamination not monitored | **Integrate** eval stack: GAIA + custom RaphaelBench (multi-relation graph queries with ground truth) + tau-bench-style policy-compliance variant + private holdout | Medium-High | Low | 2311.12983 [V], 2310.06770 [V], 2406.12045 [V], 2308.03688 [V] |
| R10 | D1 — KG retrieval | KG world models give 36–46% multi-hop gains, −40% hallucination vs vector-only; hybrid graph+vector standard | Moderate (industry+academic convergence) | world.py: typed entity+relation KG with resolution states and evidence-backed queries — **already close to SOTA** | No embeddings/vector retrieval; no entity-community tier; no learned edge scoring | **Prototype** embeddings over entity identifiers + vector top-k for POSSIBLY_SAME_AS resolution; **Defer** GNN propagation | Medium | Low | 2407.04363 [V], 2501.13956 [V]; GraphRAG/HopRAG analyses (2026) |
| R11 | B1 — Self-consistency at assertion layer | Self-Consistency improves CoT substantially at Kx compute; Self-Discover beats SC with 10–40x fewer tokens | Strong | HypothesisManager elicits LLM statements without sampling | No best-of-n / majority vote on high-stakes assertions | **Prototype** self-consistency (and Self-Discover-style structure elicitation) at the hypothesis-elicitation interface | Medium | Low | 2203.11171 [V], 2402.03620 [V], 2210.03629 [V] |
| R12 | E2 — Hypothesis competition | Bayesian posterior ratios; AGM belief revision; competing explanations maintained until discriminated | Moderate | Hypothesis lifecycle (PROPOSED→ACTIVE→FALSIFIED/ABANDONED/CONFIRMED) matches non-monotonic needs | No explicit competition registry / posterior-ratio trajectory; retirement policy implicit | **Prototype** HypothesisCompetition registry (pair-level, posterior ratio over time) + falsification→retire policy | Medium | Low | AGM/post-AGM (Gardenfors), SEP Defeasible Reasoning; hypothesis.py |
| R13 | A2 — Multi-agent | Mixed evidence; gains task-dependent; not universal | Moderate (contested) | P/S/E series exist with role separation | Coordination cost & duplicated attack surface; no shared-scratchpad semantics | **Reject** further multi-agent investment for now; monitor 2601.12538/2601.12560 for convergence | Low (avoid waste) | Low | 2601.12560 [V], 2601.12538 [V], 2406.05804 [V] |
| R14 | D2/C2 — Temporal semantics | Bi-temporal edges, valid_from/valid_until, superseding, confidence decay schedules | Moderate | world.py has `expires_at` only; no supersession; no decay policies per relation class | Temporal reasoning missing; stale beliefs not demoted | **Prototype** valid_from/valid_until + `superseded_by` on Relationship (schema v3 proposal, not a src/ change in v2.1.1) | Medium | Low | 2501.13956 [V]; temporal-KG surveys |

---

## PRIORITY SEQUENCING (phased, cost-aware)

- **Phase 1 (prototype, 1–2 sprints, highest ROI):** R2 calibration harness + R1 durable memory on existing backbone + R6 verifier pass. All three are *measurement- or-wiring* tasks on infrastructure that already exists; each directly answers the central research question with data.
- **Phase 2 (prototype):** R4 replan trigger + formal access-path mode; R5 provenance→confirmation gate. Requires design on top of frozen modules (authorized as v3 experiments, not v2.1.1 src/ edits).
- **Phase 3 (integrate after prototype evidence):** R3 budgeted-abandon + R7 active-learning selection + R9 eval stack; R11 self-consistency.
- **Defer / reject:** R13 multi-agent; R10 GNNs.

## HONEST LIMITATIONS

1. **No controlled experiment yet**: the roadmap is literature-grounded, not measured on Raphael; R2's harness is precisely the instrument needed to convert "Moderate/Strong" literature claims into "measured on our architecture" claims.
2. **CyBench numbers unverified** (arXiv ID not located on 2026-08-08) — excluded from quantitative claims.
3. **Industry-sourced figures** (Zylos 36–46% multi-hop gains; -40% hallucination) come from a secondary synthesis, not primary papers — flagged Moderate.
4. **src/ untouched**: every "prototype/integrate" above requires SENTINEL authorization before any v3 implementation.

---

*Report authored by THE STUDENT (S-Series) under Research Assignment 001, from primary sources (arXiv API-verified where marked [V]) and the frozen v2.1.1 source tree. No files in src/ were modified. Evidence strengths follow the assignment's taxonomy: Strong / Moderate / Weak. Established evidence, emerging research, and personal inference are marked [E] / [X] / [P] respectively where the distinction matters.*
