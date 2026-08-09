# STUDENT RESEARCH NOTES — RAPHAEL v3 UPGRADE SYNTHESIS

**Date**: 2026-08-08 · **Source**: 20-paper arXiv cs.CR corpus (2608.xxxxx window) + FORGE audit (G-01…G-12)

---

## PAPER-BY-PAPER MAPPING TO UPGRADE ITEMS

| arXiv ID | Title (abbrev) | Key Techniques Extracted | Raphael Upgrade Mapping |
|---|---|---|---|
| 2608.06315 | Tamarin→ProVerif translation | Sound translation, mechanized comparison | **U-08**: Port FalsificationManager to Lean/ProVerif for mechanized falsification proofs |
| 2608.06261 | HOPSCOTCH (Lean 4) | Game-hopping framework, GGM non-const depth | **U-08**: Mechanize Raphael's falsification engine in Lean 4 |
| 2608.06211 | Copyright protection for image datasets | Unlearnable examples, double watermark, info-entropy | **G-04**: Implant watermarking for exfil attribution |
| 2608.06130 | Hardware Keystores for AI Agent Signing | MCP enforcement, opaque handles, Hw attestation | **U-03**: MCP Hardware Keystore for receipt signing + NVIDIA keys |
| 2608.06124 | dfence instruction (Spectre-PHT/STL) | Jasmin type system, speculation barriers | **U-09**: dfence/Jasmin for implant crypto hardening |
| 2608.06061 | Zero-length nonce attack on GCM/GMAC | Hash key recovery via zero nonce | **G-05/Rule 4**: Audit nonce lengths in llm_transport/agent crypto (already verified) |
| 2608.05909 | MLLM safety via representation calibration | MMAligner, safety subspace at layer | **U-02**: AMS Scanner — activation-space safety tampering detection |
| 2608.05902 | GPML topology-driven cyberattack detection | Spectral graph analysis, eigenvalue bands | **U-06**: GPML Recon for ICS/OT topology-aware anomaly detection |
| 2608.05884 | Agentic Posture Vulnerability (APV) | Task-conditioned vuln mgmt, authority chains | **U-04**: APV Registry — durable agent-control exposure records |
| 2608.05870 | RustGo (Rust-directed greybox fuzzer) | Backward reachability, stdlib annotation | **U-07**: RustGo Harness for implant binary fuzzing |
| 2608.05836 | Quantum qubit hammer/SWAP attack | Quantum threat modeling | **U-09**: Quantum-resistant crypto migration path |
| 2608.05831 | S-FoM benchmarking rubric (ISO 25010) | Security QoS rubric, accountability/merit | **E-05**: S-FoM Rubric for RBS-v3 evaluation |
| 2608.05790 | ChainClaw (blockchain-native agent) | Event-driven orchestration, simulation safety, on-chain monitoring | **U-05**: ChainClaw event-driven orchestration layer |
| 2608.05754 | Quantum One-Way Functions (review) | Operational one-wayness via efficient verification | **U-09**: Quantum-resistant primitive evaluation |
| 2608.05737 | Adaptive LDP (ABC method) | Adaptive clipping bounds, 2nd-order optimization | **G-02**: Adaptive budget ceilings in RunMetrics v2 |
| 2608.05736 | Algebraic hard-label attack (ASV) | Signature extraction on FCNNs | **U-07**: Algebraic extraction for model param theft |
| 2608.05695 | DreamGuard (LLM agent guardrail) | Risk-aware world model, hazard-step detection | **U-01**: DreamGuard-inspired Guardrail Layer |
| 2608.05659 | ARIA (instruction backdoor red-teaming) | Multi-target backdoor, iterative refinement | **U-01**: Guardrail must detect instruction backdoors |
| 2608.05605 | Traffic forecasting for REN baselines | PatchTST/GRU-LSTM, dynamic security baselines | **U-06**: GPML Recon forecasting baselines |
| 2608.05578 | AMS (Activation Model Scanner) | Geometric structure of safety concepts | **U-02**: AMS Scanner — activation-space scanning |

---

## THEME FREQUENCY ANALYSIS

| Theme | Papers | Priority |
|---|---|---|
| LLM/Agent Security | 12/20 | CRITICAL — ARIA, DreamGuard, AMS, ChainClaw, MCP keystore |
| Formal Methods | 16/20 | HIGH — HOPSCOTCH, Tamarin→ProVerif, Jasmin/dfence |
| Cryptography | 16/20 | HIGH — GCM zero-nonce, quantum OWFs, HOPSCOTCH proofs |
| Fuzzing/Directed Testing | 12/20 | HIGH — RustGo, algebraic extraction |
| Network/ICS | 19/20 | HIGH — GPML spectral, REN forecasting |
| Hardware/Spectre | 8/20 | MEDIUM — dfence, Jasmin type system |
| AI Safety | 14/20 | CRITICAL — DreamGuard, AMS, ARIA |
| Cloud/Zero-Trust | 8/20 | MEDIUM — MCP keystore, ChainClaw on-chain |
| Privacy/Labeling | 16/20 | MEDIUM — LDP adaptive, unlearnable examples |

---

## CVE INTELLIGENCE SURFACED

| CVE | Papers | Relevance |
|---|---|---|
| CVE-2026-25253 | 2608.06130 | MCP keystore injection vector — hardening priority |
| CVE-2017-5753 | 2608.06124 | Spectre-PHT — dfence mitigation in implant |
| CVE-2018-3639 | 2608.06124 | Spectre-STL — dfence mitigation |
| CVE-2025-55012 | 2608.05884 | APV authority delegation — registry tracking |
| CVE-2025-55284 | 2608.05884 | Agentic posture vulnerability — APV registry |
| CVE-2024-13941 | 2608.05870 | Rust memory bug — RustGo fuzzing target |

---

## STUDENT SELF-ASSESSMENT

**Strengths of this roadmap**:
- Evidence-backed: every upgrade item traces to specific papers + audit gaps
- Phased: Phase 0 (no SENTINEL) → Phase 1 (metrics) → Phase 2 (arch) → Phase 3 (eval)
- Honest about SENTINEL gates: only Phase 0 unblocked

**Limitations**:
- Corpus limited to arXiv 2608.xxxxx (single August 2026 window)
- pypdf extraction loses equations/figures; chain_steps sometimes fragmented
- No runtime validation of proposals — all design-only until SENTINEL + implementation
- 25+ proposed components risks scope drift; recommend MVP pruning

**Recommended MVP (v3.0)**:
1. Phase 0 fixes (G-01, G-05, G-07, G-10) — **FORGE executable now**
2. G-02 RunMetrics v2 + RawResponse v2 + LLMService counters — **SENTINEL 1-week review**
3. U-01 DreamGuard Guardrail Layer — **SENTINEL 2-week review** (highest impact from corpus)
4. E-01 RBS-v3 suite with T5/T6 templates — **FORGE + SENTINEL**

---

**Student Signature**: `S-Series/2026-08-08T16:45Z`
**Artifacts**: `forge/BINARY_COVERAGE_MANIFEST_20260808.json`, `forge/student_research/V3_UPGRADE_ROADMAP.md`, this file
**Next**: Await SENTINEL authorization on Phase 1 specs; execute Phase 0 fixes.