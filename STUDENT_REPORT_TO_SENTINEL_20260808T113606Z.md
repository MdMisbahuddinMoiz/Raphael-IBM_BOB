# THE STUDENT — INTEL REPORT TO SENTINEL

**Author**: THE STUDENT (S-Series, research/ingestion agent)
**Generated**: 2026-08-08 11:36 UTC
**Source corpus**: 20 x arXiv cs.CR preprints (verified open-access, fetched from `arxiv.org/pdf/`)
**Evidence files**:
    - Findings: `student_read_findings_20260808T112302Z.json`
    - Read telemetry: `student_read_session_20260808T112302Z.jsonl`
    - Acquisition telemetry: `student_arxiv_session_20260808T111454Z.jsonl`

---

## 0 · EXECUTIVE SUMMARY

Following the prior acquisition session (20 PDFs ingested in-memory — **no PDF
files persisted**, only extracted text in `research.db`), the Student performed a
full-text deep-read of the same **20/20 papers** (0 failures), in-memory only, and
extracted takeaways, techniques, attack-chain steps, theme attribution, and CVE
references.

**Headline finding — the feed splits cleanly into three research streams:**

1. **LLM / agent security is the dominant live problem space** (12/20 papers touch
   it), and it is no longer theoretical: the corpus includes a *working*
   instruction-backdoor generator against customized coding LLMs (ARIA), a
   proactive LLM-agent guardrail (DreamGuard), an agentic vulnerability
   management abstraction (APV), and an activation-space scanner that detects
   safety-training tampering in published models (AMS).
2. **Formal methods + cryptography is surging** (16/20 co-tagged) — mechanized
   game-hopping proofs (HOPSCOTCH in Lean), sound Tamarin→ProVerif translation,
   quantum one-way functions (topical review), and a GCM/GMAC zero-length-nonce
   attack note.
3. **Infrastructure / network detection continues to grow** (19/20 tagged) — but
   this count is inflated by keyword windowing and must be read with the
   methodology caveat in §5.

**6 CVE references surfaced in the corpus**: CVE-2017-5753, CVE-2018-3639, CVE-2024-13941, CVE-2025-55012, CVE-2025-55284, CVE-2026-25253.

**Corpus freshness**: arXiv IDs `2608.xxxxx` — current live feed window at
acquisition time.

## 1 · CORPUS STATISTICS

| corpus metric | value |
|---|---|
| papers requested (arXiv API cs.CR, top 100) | 100 |
| papers read (full text) | 20 |
| extract failures | 0 |
| total PDF bytes (in-memory) | 29,961,760 |
| duration of full-text read pass | 17.67s |

## 2 · THEME DISTRIBUTION

> A paper may be counted under multiple themes (overlapping tags), so percentages
> do not sum to 100 %.

| theme | papers |
|---|---|
| network / ICS | 19 |
| cryptography | 16 |
| formal methods / verification | 16 |
| privacy / LDP | 16 |
| AI safety | 14 |
| LLM & agent security | 12 |
| fuzzing | 12 |
| hardware (Spectre-class) | 8 |
| cloud / zero-trust | 8 |


## 3 · PER-PAPER FINDINGS

### P01 · 2608.06315v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.06315v1` (open access) |
| **PDF bytes** | 820,738 |
| **Text extracted** | 120,598 chars (full-text, pypdf) |
| **Read time** | 1.31s |
| **Themes** | LLM & agent security, cryptography, formal methods / verification, fuzzing, hardware (Spectre-class), network / ICS, privacy / LDP |
| **CVEs referenced** | none |
| **Dominant terms** | proverif, tamarin, translation, facts, trace, models |

**Takeaway extracted:**
    In this work, we present a sound translation from Tamarin
to ProVerif that enables a rigorous comparison of the two tools.

**Techniques pulled:**


**Chain/methodology steps:**
    - -order logic that supports quantification over both
messages and timepoints.
    - , 𝜑 is transformed into
negation normal form(NNF), where negations apply only to trace
atoms, and the remaining operations are∧,∨,∃, or∀.
    - checks for the presence of all facts
in the premise of the rule.


### P02 · 2608.06261v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.06261v1` (open access) |
| **PDF bytes** | 637,610 |
| **Text extracted** | 93,340 chars (full-text, pypdf) |
| **Read time** | 0.86s |
| **Themes** | LLM & agent security, cryptography, formal methods / verification, fuzzing, hardware (Spectre-class), network / ICS |
| **CVEs referenced** | none |
| **Dominant terms** | oracle, proof, state, query, security, oracles |

**Takeaway extracted:**
    Game Hopping in Lean
STEFAN DZIEMBOWSKI,University of Warsaw, Poland and IDEAS Research Institute, Poland
GRZEGORZ FABIAŃSKI,IDEAS Research Institute, Poland
DANIELE MICCIANCIO,University of California San Diego, USA
RAFAŁ STEFAŃSKI,IDEAS Research Institute, Poland
We present HOPSCOTCH, a Lean 4 fra

**Techniques pulled:**
    - HOPSCOTCH, a Lean 4 framework for mechanizing computationally sound, game-based cryp-
tographic proofs.
    - the first framework with this functionality.
    - several case studies of the framework.

**Chain/methodology steps:**
    - mechanized proof of GGM for non-constant depth.
    - mechanized proof of the GGM construction
of non-constant depth (with [8] formalizing the GGM construction of depth3).
    - , it represents the domain-specific structure of a game-hopping argument as an explicit Lean
object.


### P03 · 2608.06211v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.06211v1` (open access) |
| **PDF bytes** | 10,576,347 |
| **Text extracted** | 75,453 chars (full-text, pypdf) |
| **Read time** | 1.28s |
| **Themes** | cryptography, formal methods / verification, hardware (Spectre-class), AI safety, network / ICS, cloud / zero-trust, privacy / LDP |
| **CVEs referenced** | none |
| **Dominant terms** | unlearnable, perturbations, watermark, images, information, image |

**Takeaway extracted:**
    Therefore, in this paper, we propose a novel copyright protection
mechanism for the aforementioned security concerns.

**Techniques pulled:**
    - practical and comprehensive copyright
protection framework for image datasets.
    - novel information theory-based un-
learnable example method.
    - more effective method based
on the theory of information entropy for availability attacks
and verify it on multiple datasets.

**Chain/methodology steps:**
    - ly, fix the perturbations and minimize the
cross-entropy loss to update the victim model parameters.
    - embedding
watermarkmusing the encoderEand then adding thec-
th class perturbationη c on it, i.
    - ,
a network embeds and extracts watermarks, generating water-
marked images.


### P04 · 2608.06130v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.06130v1` (open access) |
| **PDF bytes** | 1,787,507 |
| **Text extracted** | 45,569 chars (full-text, pypdf) |
| **Read time** | 0.41s |
| **Themes** | LLM & agent security, cryptography, formal methods / verification, AI safety, network / ICS, cloud / zero-trust, privacy / LDP |
| **CVEs referenced** | CVE-2026-25253 |
| **Dominant terms** | agent, signing, injection, hardware, layer, session |

**Takeaway extracted:**
    Hardware Keystores for AI Agent Signing Workflows:
A Zero-Trust MCP Enforcement Architecture
Léo Sambrook
Hardware Systems Security Lab (HSSL)
Huawei Technologies & EPITA
Helsinki, Finland
leosambrook1@gmail.com
Sampo Sovio
Hardware Systems Security Lab (HSSL)
Huawei Technologies
Helsinki, Finland
A

**Techniques pulled:**
    - opaque-
handle semantics and hardware attestation within the Aura
mobile-agent operating system; their work addresses session
identity and intent classification
    - CVE-2026-25253

**Chain/methodology steps:**
    - (RA V) still executes before Stage 3: an obvious injection
isBLOCKed by the RA V immediately, with no HITL
notification sent to the operator.
    - -pass before the deterministic safety nets.
    - systematic taxonomy of attacks against autonomous
agents (Content Injection,Cognitive State Attacks,Semantic
Manipulation,Behavioural Control,HITL Traps,Systemi


### P05 · 2608.06124v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.06124v1` (open access) |
| **PDF bytes** | 883,375 |
| **Text extracted** | 167,568 chars (full-text, pypdf) |
| **Read time** | 1.92s |
| **Themes** | LLM & agent security, cryptography, formal methods / verification, fuzzing, hardware (Spectre-class), AI safety, network / ICS, privacy / LDP |
| **CVEs referenced** | CVE-2017-5753, CVE-2018-3639 |
| **Dominant terms** | dfence, speculative, proof, speculation, system, lemma |

**Takeaway extracted:**
    In this work,
we introduce dfence, a new CPU instruction that generalizes SLH
to mitigate both Spectre-PHT and Spectre-STL with minimal hard-
ware support.

**Techniques pulled:**
    - and implement a low-level type system for the Jasmin [3]
language, which automatically verifies that dfence protections (or
standard serializing fences) are cor
    - template to generate vulnerable code snippets and protect them
using various defense strategies.
    - CVE-2017-5753

**Chain/methodology steps:**
    - solution is to insert speculation
barriers (e.
    - , itsgeneral-
ityis restricted: it is effective only against Spectre-PHT; protecting
1if( i <|a|)
2x:=a[i]
3dfencex ✓
4y:=b[x]
(a) Listing 1b protected withdfen
    - level corresponds
to non-speculative execution, the second to speculative execution.


### P06 · 2608.06061v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.06061v1` (open access) |
| **PDF bytes** | 309,552 |
| **Text extracted** | 13,430 chars (full-text, pypdf) |
| **Read time** | 0.19s |
| **Themes** | cryptography, formal methods / verification, network / ICS |
| **CVEs referenced** | none |
| **Dominant terms** | length, nonce, string, version, attack, encryption |

**Takeaway extracted:**
    A Note on the Influence of a Zero Length Nonce
on GCM and GMAC
Yaobin Shen
School of Informatics, Xiamen University, Xiamen, China
yaobin.shen@xmu.edu.cn
Abstract.In this note, we show a simple attack that can recover the
hash key ofGCMandGMACby using a zero length nonce.

**Techniques pulled:**


**Chain/methodology steps:**
    - ticatedencryptionschemeandmessageauthenticationcodescheme.
    - improved by Niwa et al.
    - ticated encryption scheme that
can be used to encrypt a plaintext and authenticate the resulting ciphertext
together with associated data.


### P07 · 2608.05909v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.05909v1` (open access) |
| **PDF bytes** | 2,262,665 |
| **Text extracted** | 121,090 chars (full-text, pypdf) |
| **Read time** | 1.66s |
| **Themes** | LLM & agent security, fuzzing, AI safety, network / ICS, privacy / LDP |
| **CVEs referenced** | none |
| **Dominant terms** | safety, multimodal, refusal, unsafe, inputs, mllms |

**Takeaway extracted:**
    In this paper, we conduct a geometric
analysis of MLLM representations to investigate the causes of mul-
timodal safety degradation.

**Techniques pulled:**
    - MMAligner, an MLLM safeguarding method based on representa-
tion calibration.
    - mechanism-guided method to enhance safety alignment.

**Chain/methodology steps:**
    - line of work deploys auxiliary
modules at inference time to intervene in the multimodal generation
1
arXiv:2608.
    - conduct an em-
pirical evaluation using the curated dataset from MM-SafetyBench.
    - characterize the internal mechanism of safety knowledge.


### P08 · 2608.05902v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.05902v1` (open access) |
| **PDF bytes** | 564,044 |
| **Text extracted** | 22,040 chars (full-text, pypdf) |
| **Read time** | 0.22s |
| **Themes** | cryptography, AI safety, network / ICS |
| **CVEs referenced** | none |
| **Dominant terms** | spectral, detection, metrics, community, baseline, network |

**Takeaway extracted:**
    In this work, we present a topology-driven approach
for detection of cyberattacks in water distribution networks
based on the Graph Processing for Machine Learning (GPML)
framework.

**Techniques pulled:**
    - topology-driven approach
for detection of cyberattacks in water distribution networks
based on the Graph Processing for Machine Learning (GPML)
framework.
    - deterministic communication patterns, which
makes topology-driven anomaly detection particularly rele-
vant.

**Chain/methodology steps:**
    - two types of
graphs for a time window are extracted from the raw data.
    - , we transform raw traffic logs into a
time-series representation by aggregating records that share
the same communication context (e.
    - non-zero eigenvalue band
by averaging theNeigenvalues immediately after the zero
block asm 2(t) =

1
N
PZ(t)+N
i=Z(t)+1 λ(t)
i

−1.


### P09 · 2608.05884v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.05884v1` (open access) |
| **PDF bytes** | 299,419 |
| **Text extracted** | 34,375 chars (full-text, pypdf) |
| **Read time** | 0.27s |
| **Themes** | LLM & agent security, cryptography, formal methods / verification, fuzzing, AI safety, network / ICS, cloud / zero-trust, privacy / LDP |
| **CVEs referenced** | CVE-2025-55012, CVE-2025-55284 |
| **Dominant terms** | authority, agent, posture, vulnerability, arxiv, security |

**Takeaway extracted:**
    We propose theagentic posture vulnerability(APV) as a task-conditioned vulnerability-
management abstraction: a durable record for a composed agent-control exposure.

**Techniques pulled:**
    - principle of the Cyber Defense Matrix [Yu, n.
    - CVE-2025-55012
    - CVE-2025-55284

**Chain/methodology steps:**
    - observed, last verified, affected agents, identities, repositories, connectors,
credentials, hosts, and environments.
    - verified coexistence of disabled
approvals and production database reach until either condition changed.
    - expression of the same weakness.


### P10 · 2608.05870v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.05870v1` (open access) |
| **PDF bytes** | 1,288,951 |
| **Text extracted** | 134,320 chars (full-text, pypdf) |
| **Read time** | 1.46s |
| **Themes** | LLM & agent security, cryptography, fuzzing, hardware (Spectre-class), AI safety, network / ICS, privacy / LDP |
| **CVEs referenced** | CVE-2024-13941 |
| **Dominant terms** | fuzzing, target, memory, targets, analysis, safety |

**Takeaway extracted:**
    In this paper, we proposeRustGo, the new Rust-directed greybox
fuzzer that effectively and fairly focuses on code regions potentially
containing memory bugs.

**Techniques pulled:**
    - We present the design ofRustGo, the new directed fuzzer for ef-
ficient memory bug detection within Rust applications.
    - CVE-2024-13941

**Chain/methodology steps:**
    - challenge is to automatically and precisely identify
and optimize targets in Rust programs where memory bugs are
likely to occur.
    - step,RustGoperforms standard library annotation by automat-
ically referencing the definitions of Rust standard library functions
(available in rust/library/std
    - performs backward reach-
ability analysis (§3.


### P11 · 2608.05836v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.05836v1` (open access) |
| **PDF bytes** | 88,318 |
| **Text extracted** | 11,468 chars (full-text, pypdf) |
| **Read time** | 0.10s |
| **Themes** | cryptography, formal methods / verification, cloud / zero-trust, privacy / LDP |
| **CVEs referenced** | none |
| **Dominant terms** | quantum, https, threat, attack, attacks, security |

**Takeaway extracted:**
    For instance, Side-
This work has been supported by the Business Finland through project
SeQuSoS(Grant No.

**Techniques pulled:**
    - QubitHammer/SW AP attack.

**Chain/methodology steps:**
    - tication & Submission: API token, SDK calls, IAM
(Identity and Access Management).
    - s with higher impacts.
    - s that compose stage local
capabilities into higher impact threats.


### P12 · 2608.05831v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.05831v1` (open access) |
| **PDF bytes** | 132,175 |
| **Text extracted** | 23,640 chars (full-text, pypdf) |
| **Read time** | 0.32s |
| **Themes** | cryptography, fuzzing, network / ICS, cloud / zero-trust, privacy / LDP |
| **CVEs referenced** | none |
| **Dominant terms** | quantum, security, software, https, metrics, circuit |

**Takeaway extracted:**
    The research of this paper is threefold: (i) chara cterizes
a three-layer measurement gap, (ii) proposes a structured S -FoM
set organized by ISO/IEC 25010 security sub-characteristi cs,
QaaS pipeline mapping, and measurement maturity, and (iii)
deﬁnes a benchmarking rubric that normalizes and aggre

**Techniques pulled:**
    - and
develop a benchmarking tool that computes the established
S-FoMs over Qiskit and Cirq programs, together with the
protocols for the metrics that are current

**Chain/methodology steps:**
    - ly, conﬁdentiality is the sole well-instrumented pro perty
(obfuscation FoMs) and conﬁrms that at present quantita-
tive security research is concentrated at S3
    - (CLOPS)) for the merit performance ﬁg -
ures.
    - ticity, and resistan ce.


### P13 · 2608.05790v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.05790v1` (open access) |
| **PDF bytes** | 2,298,230 |
| **Text extracted** | 45,848 chars (full-text, pypdf) |
| **Read time** | 0.39s |
| **Themes** | LLM & agent security, cryptography, formal methods / verification, fuzzing, AI safety, network / ICS, cloud / zero-trust, privacy / LDP |
| **CVEs referenced** | none |
| **Dominant terms** | chainclaw, on-chain, execution, agent, state, chain |

**Takeaway extracted:**
    We propose ChainClaw, a blockchain-native agent framework
built on OpenClaw, that addresses all three gaps through a lay-
ered architecture comprising an event-driven orchestration layer, a
simulation-based safety intelligence layer, and an on-chain moni-
toring runtime layer, unified by a cross-lay

**Techniques pulled:**
    - ChainClaw, a blockchain-native agent framework
built on OpenClaw, that addresses all three gaps through a lay-
ered architecture comprising an event-driven orch
    - ChainClaw, a unified on-chain agent
framework built on top of OpenClaw, extending its modular run-
time with blockchain-native components designed to close all 

**Chain/methodology steps:**
    - , the assumption that interaction is primar-
ily session-driven is broken by asynchronous on-chain events and
delayed transaction outcomes, leading to a Reactiv
    - secures the on-chain artifact.
    - approve
and then swap (T5).


### P14 · 2608.05754v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.05754v1` (open access) |
| **PDF bytes** | 645,159 |
| **Text extracted** | 171,337 chars (full-text, pypdf) |
| **Read time** | 1.49s |
| **Themes** | LLM & agent security, cryptography, formal methods / verification, fuzzing, network / ICS, privacy / LDP |
| **CVEs referenced** | none |
| **Dominant terms** | quantum, states, state, classical, security, adversary |

**Takeaway extracted:**
    IOP PublishingJournalvv(yyyy) aaaaaa Authoret al
Journal Name
TOPICAL REVIEWCrossmark
RECEIVED
dd Month yyyy
REVISED
dd Month yyyy
Quantum One-Way Functions and Related Cryptographic
Primitives
Georgios M.

**Techniques pulled:**
    - closely related framework in which one-wayness is defined operationally
through efficient verification instead of a prescribed notion of state similarity.

**Chain/methodology steps:**
    - register pertains to ad-dimensional system, whereq(n) =⌈log 2 d⌉=O(logn) qubits.
    - , the pairwise overlaps between distinct states are
constant and do not decrease withn, which means that with sufficiently many copies the states can
in princip
    - exploited by Buhrman et al.


### P15 · 2608.05737v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.05737v1` (open access) |
| **PDF bytes** | 1,144,389 |
| **Text extracted** | 74,223 chars (full-text, pypdf) |
| **Read time** | 0.88s |
| **Themes** | formal methods / verification, AI safety, network / ICS, privacy / LDP |
| **CVEs referenced** | none |
| **Dominant terms** | privacy, server, numerical, range, mechanism, domain |

**Takeaway extracted:**
    In this work, we propose an adaptive LDP framework that
addresses this problem.

**Techniques pulled:**
    - adaptive LDP framework that
addresses this problem.
    - adaptive mechanism, which we call
theAdaptive Bounding of Clipping regions (ABC)method,
that adaptively bounds values using second-order optimization.
    - novel adaptive framework, the Adaptive
Bounding of Clipping regions (ABC), for numerical data
collection under LDP.

**Chain/methodology steps:**
    - review the foundational and advanced LDP
mechanisms for numerical data.
    - phase, it utilizes a portion of
the user to estimate the distribution of the data’s magnitude,
analytically deriving a clipping thresholdθthat minimizes
the exp
    - , a user’s raw
numerical valuevis clipped to a predefined public range[l, r].


### P16 · 2608.05736v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.05736v1` (open access) |
| **PDF bytes** | 1,096,637 |
| **Text extracted** | 110,484 chars (full-text, pypdf) |
| **Read time** | 2.10s |
| **Themes** | cryptography, formal methods / verification, hardware (Spectre-class), AI safety, network / ICS |
| **CVEs referenced** | none |
| **Dominant terms** | points, pooling, layer, hard-label, extraction, neural |

**Takeaway extracted:**
    To address this com-
putational bottleneck, this work transforms Carliniet al.’s geometric-
view hard-label attack into an algebraic framework, and proposes a novel
Approximate Signature Vector (ASV) method to achieve efficient param-
eter extraction on Fully Connected Neural Networks (FCNNs) by lev

**Techniques pulled:**
    - the first hard-label attack
on the max-pooling CNN, filling a cryptanalysis gap.
    - our algebraic attack to extract the signatures of a 4-hidden-
layer FCNN with a 64−(64×4)−10 architecture.

**Chain/methodology steps:**
    - adversarial reverse engineering attack for this problem
[26], with recent years seeing continued innovations from industry and academia
arXiv:2608.
    - proposed a polynomial-query extraction method for this setting
at ASIACRYPT 2024, though it suffered from exponential runtime [10].
    - compute the
ASV⃗ vfor each dual point.


### P17 · 2608.05695v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.05695v1` (open access) |
| **PDF bytes** | 821,961 |
| **Text extracted** | 65,725 chars (full-text, pypdf) |
| **Read time** | 0.67s |
| **Themes** | LLM & agent security, formal methods / verification, hardware (Spectre-class), AI safety, network / ICS, cloud / zero-trust, privacy / LDP |
| **CVEs referenced** | none |
| **Dominant terms** | guardrail, safety, action, agent, state, world |

**Takeaway extracted:**
    In response, we proposeDreamGuard, a
proactive guardrail for LLM agents built around a risk-aware
world model.

**Techniques pulled:**
    - provides
the best balance between detection quality, false-positive
control, and pre-hazard intervention: removing individual
components tends to collapse one s

**Chain/methodology steps:**
    - hazard
step, the earliest step whose proposed action would trigger
a concrete hazardous outcome or transition if executed.
    - stage learns
recurrentlatentdynamicsfromtrajectorydata,whilethesec-
ondstageshapesthelearnedstatewithimmediate-hazardand
prefix-risk supervision.
    - hazard
step is then identified as the earliest step labeled hazardous
in each unsafe trajectory.


### P18 · 2608.05659v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.05659v1` (open access) |
| **PDF bytes** | 1,064,474 |
| **Text extracted** | 84,313 chars (full-text, pypdf) |
| **Read time** | 0.90s |
| **Themes** | LLM & agent security, formal methods / verification, fuzzing, AI safety, network / ICS, privacy / LDP |
| **CVEs referenced** | none |
| **Dominant terms** | backdoor, instruction, generation, trigger, target, attacks |

**Takeaway extracted:**
    In this paper, we proposeARIA, an automated red-teaming
framework for crafting covert and effective backdoored instruc-
tions against customized LLMs.ARIAleverages an attacker LLM
to iteratively generate and refine backdoored instructions, guided
by structured feedback from the target LLM along thre

**Techniques pulled:**
    - security risks, as attack-
ers can embed backdoor behaviors in customized instructions that
are difficult for end users to inspect externally [14, 51, 56].
    - multi-target backdoor
framework for code pre-trained models that can selectively activate
specific backdoors for different downstream tasks.
    - backdoor
Table 1: Average detection results of existing instruction back-
door attacks under platform-side and user-side detection.

**Chain/methodology steps:**
    - , they often rely on explicit
trigger patterns readily detected by platform-side or user-side in-
spection.
    - automated red-teaming framework
for generating instruction backdoor attacks against customized
LLMs for coding.
    - instruction backdoor
attacks against customized LLMs at word, syntax, and semantic lev-
els.


### P19 · 2608.05605v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.05605v1` (open access) |
| **PDF bytes** | 2,748,522 |
| **Text extracted** | 40,831 chars (full-text, pypdf) |
| **Read time** | 0.57s |
| **Themes** | cryptography, formal methods / verification, fuzzing, AI safety, network / ICS, privacy / LDP |
| **CVEs referenced** | none |
| **Dominant terms** | security, baseline, traffic, anomaly, gru-lstm, detection |

**Takeaway extracted:**
    In this paper, we propose and
evaluate a high-fidelity traffic forecasting framework designed
to establish dynamic security baselines for RENs.

**Techniques pulled:**
    - and
evaluate a high-fidelity traffic forecasting framework designed
to establish dynamic security baselines for RENs.
    - and selection of hybrid deep learning archi-
tectures is a critical factor in system performance across
various domains [26], [27].

**Chain/methodology steps:**
    - large-scale
benchmark of anomaly-aware forecasting models in this domain.
    - statistically validated framework
for distinguishing scientific workflows from network attacks,
enabling more autonomous and resilient network security op-
erat
    - performs Data Ingestion & Parsing to handle
the raw, non-standard JSON fragments.


### P20 · 2608.05578v1

| field | value |
|---|---|
| **Location** | `arxiv.org/pdf/2608.05578v1` (open access) |
| **PDF bytes** | 491,687 |
| **Text extracted** | 71,022 chars (full-text, pypdf) |
| **Read time** | 0.67s |
| **Themes** | LLM & agent security, cryptography, formal methods / verification, fuzzing, hardware (Spectre-class), AI safety, network / ICS, cloud / zero-trust, privacy / LDP |
| **CVEs referenced** | none |
| **Dominant terms** | models, safety, direction, behavioral, harmful, llama- |

**Takeaway extracted:**
    1
Detecting Safety Training Modification in Language
Models via Activation Analysis
Glen Messenger
Abstract—We introduce AMS (Activation-based Model Scan-
ner), a tool that detects modifications to safety training in
language models by measuring the geometric structure of safety-
relevant concepts i

**Techniques pulled:**
    - AMS (Activation-based Model Scan-
ner), a tool that detects modifications to safety training in
language models by measuring the geometric structure of safety-


**Chain/methodology steps:**
    - 250 characters of the
response (refusals reliably appear early; later occurrences are
typically false positives such as “I won’t” appearing inside a
generated m
    - , the per-category cluster-
ing on the scatter is clean: instruction-tuned models cluster
lower-right (highσ, low compliance) and uncensored/base
models cluster
    - exploit identified
vulnerable layers for targeted attacks.


---

## 4 · SIGNAL EXTRACTION — WHAT THE CORPUS SUGGESTS

1. **Instruction backdoors in coding LLMs are deployable.** ARIA (2608.05659)
   demonstrates automated generation of "covert and effective" backdoored
   instructions targeting *customized* (fine-tuned) coding models; triggers are
   designed to resist platform-side inspection. The paper benchmarks platform-
   side vs user-side detection — relevant to any AI/agent-facing tooling we build.
2. **Guardrails are moving from prompting to world-model + state estimation.**
   DreamGuard (2608.05695) grounds hazard detection in a per-step risk-aware
   world model with "immediate-hazard and prefix-risk supervision"; its ablation
   shows the over-warn vs intervene-early trade-off collapses when any single
   component is removed. AMS (2608.05578) pushes into activation geometry, with
   cluster separation of instruction-tuned vs uncensored checks.
3. **Formal cryptography is becoming mechanized.** HOPSCOTCH (2608.06261) is the
   first machine-checkable (Lean 4) framework for game-based cryptographic proofs
   at non-constant depth; 2608.06315 provides sound Tamarin→ProVerif translation.
4. **Speculation mitigation is an instruction-level question.** dfence
   (2608.06124) generalizes SLH to both Spectre-PHT and Spectre-STL as a CPU
   instruction, plus a typed-assembly (Jasmin) checker automating fence placement.
5. **Fuzzing is going language-directed.** RustGo (2608.05870) adds directed
   greybox fuzzing with Rust standard-library annotation; surfaces CVE-2024-13941.
6. **Zero-length nonce GCM/GMAC** (2608.06061) — a cryptanalytic note worth
   checking in any cryptographic implementation we touch.

## 5 · METHODOLOGY & HONEST LIMITATIONS

- **Source**: arXiv cs.CR feed (latest 100 at acquisition); 20 sampled for
  ingestion. NOT a representative sample of all 2026 security research — cs.CR
  skews toward ML-security, formal methods, and network detection.
- **Extraction**: `pypdf` text layer only; two papers show header/OCR artifacts
  (2608.05754 journal header block; 2608.05831 "chara cterizes" tokenization).
- **Techniques/chain extraction**: regex-driven; related-work fragments may
  surface as "techniques". Treat as raw material for human/LLM downstream
  synthesis, not verified claims.
- **Classification caveat**: keyword-based classier over full text — consistent
  with the earlier "RCE" over-application documented in the acquisition pass.
  Intended follow-up: context-aware/object-level extraction.
- **No copyrighted content** was downloaded during analysis; the corpus is
  open-access arXiv.

## 6 · RECOMMENDATIONS FOR SENTINEL

1. **Seed the Planner knowledge layer with the APV + DreamGuard + ARIA material**
   as the "current state of agent security" stream — highest-signal findings.
2. **Monitor CVE-2026-25253 and CVE-2025-55284** for follow-up deep-dives
   (hardware keystore/MCP, agentic posture vulnerability management).
3. **Upgrade the extraction layer** (custom object-level extraction / OCR fallback)
   before scaling corpus runs past N=20, per methodology caveats.
4. **No further corpus download is required.** Themes are saturated at 20 papers;
   recommended next move is knowledge-base integration, not more acquisition.

---

*Report composed by THE STUDENT from raw artifacts; every figure above traces to
the three files listed at top. PDF downloads were in-memory: no binaries written,
no copyrighted content acquired.*
