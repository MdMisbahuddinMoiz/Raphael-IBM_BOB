# Raphael v2.1.1 — Autonomous Cognitive Offensive AI Platform

> **Research-grade autonomous offensive AI system** with a unified cognitive architecture (D-Series Brain, S-Series Student, E-Series Hands, P-Series Stealth) that autonomously probes targets, builds belief-state profiles, researches techniques, and executes stateful operations — all within a strict, brokered authorization envelope.

> **Status**: Frozen v2.1.1 evaluation campaign complete (121/121 tests passing). This repository contains the frozen instrument for RBS-v4 terminal holdout campaign and associated research artifacts.

---

## Architecture Overview

Raphael is a **unified cognitive agent** organized into four operational series:

```
┌─────────────────────────────────────────────────────────────────┐
│                    RAPHAEL COGNITIVE AGENT v2.1.1               │
├─────────────────────────────────────────────────────────────────┤
│  D-SERIES — BRAIN (orchestrator/brain/)                        │
│  ├── Planner (action.py)          ├── WorldModel (world.py)    │
│  ├── CapabilityBroker             ├── Falsification Manager    │
│  ├── Candidate Generator          ├── Contradiction Detection  │
│  ├── Reflection Engine            ├── Strategy Learner         │
│  ├── ScopeParser (SS-01)          ├── RateLimiter (SS-02)      │
│  └── WAFDetector (SS-03)                                                 │
├─────────────────────────────────────────────────────────────────┤
│  S-SERIES — STUDENT (orchestrator/student/)                    │
│  ├── Research Scheduler         ├── Chain Synthesizer          │
│  ├── Knowledge Background Svc   ├── Coverage Gap Filler        │
│  ├── Stack Matcher              ├── PayloadMutator (SS-04)     │
│  └── Research Orchestration                                           │
├─────────────────────────────────────────────────────────────────┤
│  E-SERIES — HANDS (orchestrator/capabilities/interactive_shell/)│
│  ├── SSH Shell Capability       ├── Reverse Shell Capability   │
│  ├── Command Filter Pipeline    ├── Shell Session Store        │
│  ├── TTY Normalizer + Evidence  ├── Listener Manager (Broker)  │
│  └── Interactive Shell Execution                                       │
├─────────────────────────────────────────────────────────────────┤
│  P-SERIES — STEALTH (embedded across D/S/E)                    │
│  ├── ScopeParser (SS-01)          ├── RateLimiter (SS-02)      │
│  ├── WAFDetector (SS-03)          ├── PayloadMutator (SS-04)   │
│  └── Authorization envelope enforcement                            │
└─────────────────────────────────────────────────────────────────┘
```

### Core Cognitive Loop
```
Student (S-Series) → Candidate Generator → Planner (scoring) 
    → CapabilityBroker (authorization) → E-Series (execution)
    → WorldModel update → Falsification/Contradiction → Student learns
```

---

## Key Components

| Component | Module | Purpose |
|-----------|--------|---------|
| **Planner** | `orchestrator/brain/action.py` | Precondition/effect planning with 8 precondition types |
| **WorldModel** | `orchestrator/brain/world.py` | Temporal entity graph with provenance & evidence chains |
| **CapabilityBroker** | `orchestrator/brain/capability_broker.py` | Deny-by-default authorization (5 dimensions) |
| **Hypothesis Manager** | `orchestrator/brain/hypothesis.py` | 7-factor structured confidence with full history |
| **Contradiction Manager** | `orchestrator/brain/contradiction.py` | Immutable both-sides, discriminating observations (5 types) |
| **Falsification Engine** | `orchestrator/brain/falsification.py` | Mandatory evidence validation for Student proposals |
| **Student** | `orchestrator/student/` | Autonomous research, technique synthesis, knowledge management |
| **CapabilityBroker** | `orchestrator/brain/capability_broker.py` | 5-dimension deny-by-default (target/RoE/capability/rate/impact) |
| **SSH/Reverse Shell** | `orchestrator/capabilities/interactive_shell/` | Stateful interactive execution with evidence extraction |

---

## Installation

### Prerequisites
- Python 3.12+
- Docker + Docker Compose (for arena targets: DVWA, VulnerableApp)
- Ollama or OpenAI-compatible API endpoint for LLM inference
- Kali Linux tooling (nmap, sqlmap, gobuster, etc.) — provided via `kali-tools` container

### Quick Start
```bash
# Clone and enter
git clone https://github.com/The-Despicable/raphael-2.0-rbsv2r.git
cd raphael-2.0-rbsv2r

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure environment (copy template and fill in)
cp .env.example .env
# Edit .env with your LLM endpoint, API keys, etc.

# Start arena targets
docker compose -f docker/arena.yml up -d

# Run smoke test
python scripts/smoke_test.py

# Run evaluation campaign (RBS-v4 terminal holdout)
python scripts/run_rbs_v4_holdout_frozen.py
```

### Environment Variables (see `.env.example`)
| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes* | LLM API key (or use local Ollama) |
| `OPENAI_BASE_URL` | No | Custom endpoint (default: Ollama `http://localhost:11434/v1`) |
| `MODEL_ID` | No | Model identifier (default: `nvidia/nemotron-3-ultra`) |
| `TOR_PROXY` | No | Tor proxy for anonymity |
| `API_KEY` | Yes | Internal API authentication |

*Either `OPENAI_API_KEY` or local Ollama instance required.

---

## Reproduction Steps (RBS-v4 Terminal Holdout)

The frozen instrument (v2.1.1) was evaluated via the **RBS-v4 Terminal Holdout Campaign** — a 1,200-run holdout evaluation across 5 scenario families × 4 arms × 60 seeds.

### Reproduce the Terminal Campaign
```bash
# Ensure Docker targets are running
docker compose -f docker/arena.yml up -d

# Run the frozen holdout campaign (exact RBS-v4 instrument)
python scripts/run_rbs_v4_holdout_frozen.py

# Results written to evaluations/campaign/
# - rbs_v4_holdout.jsonl (1,200 rows, SHA-256: 2bf614f8...)
# - Terminal analysis: TERMINAL_ANALYSIS_RESULTS.json
# - D3 independent recomputation artifacts
```

### Key Results (from FINAL_VERDICT_RECORD.md)
| Comparison | Outcome | Effect Size |
|------------|---------|-------------|
| FULL vs NO_WORLD_MODEL | **DEMONSTRATED** | Δ=+0.149, d=+0.773, p=3.16e-30 |
| FULL vs NO_PLANNER | **DEMONSTRATED** | Δ=+0.090, d=+0.547 |
| FULL vs NO_STUDENT | **DEMONSTRATED*** | Δ=+0.021 (with boost confound) |
| FULL vs NO_FALSIFICATION | **DEMONSTRATED*** | Single-template (T10) |
| FULL vs PROMPTED_AGENT | **INSTRUMENT_DEFECT** | 0/300 pass (structural) |
| FULL vs SCRIPTED_BASELINE | **DEMONSTRATED*** | Δ=+0.347 (with defect disclosure) |

*With confound/defect qualifications. Central thesis ("explicit architecture > prompting alone") remains **UNRESOLVED** due to instrument defects in PROMPTED_AGENT and SCRIPTED_BASELINE arms.

### Research Assignment 001
See [`RESEARCH_ASSIGNMENT_001_REPORT.md`](RESEARCH_ASSIGNMENT_001_REPORT.md) for the literature synthesis answering: *"Where does explicit cognitive architecture provide measurable value beyond frontier LLM prompting alone?"* — includes 14-component roadmap (R1–R14) with evidence grades and phased priorities.

---

## Limitations (from LIMITATIONS.md)

| ID | Limitation | Severity | Component |
|----|------------|----------|-----------|
| L-001 | Cognitive loop latency (30-120s/cycle) | MEDIUM | D-Series Brain |
| L-002 | LLM hallucination in technique proposal | HIGH | S-Series Student |
| L-003 | ScopeParser wildcard spoofing edge cases | MEDIUM | P1 ScopeParser |
| L-004 | Falsification Engine ~78% catch rate | HIGH | Falsification Engine |
| L-005 | No persistent cross-session memory | HIGH | NeuralMemory (in-process only) |
| L-006 | PROMPTED_AGENT arm structurally incapable | CRITICAL | Evaluation Instrument |

> **Full limitations**: See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) (24 documented limitations)

---

## Evaluation Artifacts

All RBS-v4 terminal campaign artifacts are preserved in `evaluations/campaign/`:

| File | Description |
|------|-------------|
| `rbs_v4_holdout.jsonl` | Raw data (1,200 rows, SHA-256 `2bf614f8eafa0253...`) |
| `FINAL_VERDICT_RECORD.md` | Terminal verdict with full claim ledger |
| `TERMINAL_ANALYSIS_RESULTS.json` | Terminal analysis (regenerated 2026-08-08) |
| `TERMINAL_D3_RECOMPUTATION_DIFF.txt` | D3 independent recomputation (byte-identical) |
| `TERMINAL_VALIDATION_FREEZE_REPAIR.json` | Post-hoc freeze repair (git commit `a00ee3e1`) |
| `rbs_v4_reproducibility_manifest.json` | Full reproducibility manifest |
| `rbs_v4_claim_ledger.json` | 13 claims with classifications |
| `rbs_v4_threats_to_validity.md` | Threats to validity analysis |
| `GIT_SHOW_a00ee3e1_D1E.txt` | Repair commit pin |

All hashes and frozen manifests are preserved for exact reproducibility.

---

## Project Structure (Post-Cleanup)

```
raphael-2.0-rbsv2r/
├── docs/                    # Architecture, limitations, roadmap, threats
├── evaluations/campaign/    # RBS-v4 terminal holdout artifacts (preserved)
├── orchestrator/           # Core cognitive agent (D/S/E/P series)
│   ├── brain/              # D-Series: planner, world, broker, falsification
│   ├── student/            # S-Series: research, synthesis, knowledge
│   └── capabilities/       # E-Series: SSH, reverse shell, filter pipeline
├── arena/                  # Evaluation arena (DVWA, VulnerableApp targets)
├── scripts/                # Campaign runners, smoke tests, analysis
├── tests/                  # 121 regression tests (all passing)
├── .env.example            # Environment template
├── .gitignore              # Comprehensive ignore rules
└── README.md               # This file
```

**Removed from tracking** (via cleanup commit `2702234b`):
- `src/cli/node_modules/` (55,404 files)
- `Report_Raphael.zip`, `d6b_execution.log`, `*.bak` files
- VPN config with private key (purged from history via `git filter-repo`)

---

## Security & Ethics

- **Authorization envelope**: All execution gated by `CapabilityBroker` deny-by-default (5 dimensions)
- **Scope enforcement**: `ScopeParser` validates target ownership before any action
- **Rate limiting**: Adaptive jitter + emergency brake for live engagements
- **Evidence chain**: Every action produces immutable `ActionReceipt` with full provenance
- **Falsification mandatory**: No technique executes without evidence validation
- **Audit trail**: Complete JSONL telemetry for every run

> **Warning**: This is offensive security research software. Use only against authorized targets with explicit written permission. Unauthorized use is illegal and unethical.

---

## License

```
MIT License

Copyright (c) 2024-2026 The-Despicable

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Citation

If you use this work in research, please cite:

```bibtex
@misc{raphael-v2.1.1,
  title = {Raphael v2.1.1: Autonomous Cognitive Offensive AI Platform},
  author = {The-Despicable},
  year = {2024-2026},
  note = {RBS-v4 Terminal Holdout Campaign — 1,200-run frozen instrument evaluation},
  url = {https://github.com/The-Despicable/raphael-2.0-rbsv2r}
}
```

---

## Related Documentation

- [`docs/Architecture.md`](docs/Architecture.md) — Full architecture specification
- [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) — 24 documented limitations
- [`docs/ThreatsToValidity.md`](docs/ThreatsToValidity.md) — Threats to validity analysis
- [`docs/ResearchRoadmap.md`](docs/ResearchRoadmap.md) — Research roadmap (14 recommendations)
- [`docs/EvaluationProtocol.md`](docs/EvaluationProtocol.md) — Evaluation methodology
- [`RESEARCH_ASSIGNMENT_001_REPORT.md`](RESEARCH_ASSIGNMENT_001_REPORT.md) — Literature synthesis (Architecture vs Prompting)