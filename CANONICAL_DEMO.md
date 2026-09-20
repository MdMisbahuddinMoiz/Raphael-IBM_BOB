# RAPHAEL IBM BOB — Canonical Judge Demonstration

This document explains the canonical demonstration runner for judges evaluating the RAPHAEL IBM BOB MVP governed agentic control loop.

---

## 1. Quickstart & Modes

Run from the repository root:

```bash
# 1. Canonical governed hero demonstration (REAL T3MP3ST provider required; exits 0, QualityGate: COMPLETE)
./scripts/run_demo.sh

# 2. Honest refusal demonstration (exits 1, QualityGate: REFUSE via failed oracle probe)
./scripts/run_demo.sh --refuse

# 3. Explicit mock mode (uses InertProviderDouble test double instead of real provider; exits 0, COMPLETE)
./scripts/run_demo.sh --mock

# 4. Environment prerequisite inspection
./scripts/run_demo.sh --check-prereqs
```

### Provider Execution Contract:
- **Default canonical demo (`./scripts/run_demo.sh`)**: Demands the **REAL** pinned T3MP3ST provider checkout in the `bwrap` sandbox. It does **NOT** silently fall back to an inert double. If provider prerequisites are missing, it halts with a clear prerequisite failure (exit code 2).
- **Explicit test double mode (`./scripts/run_demo.sh --mock`)**: Allows running in constrained environments without the compiled T3MP3ST provider dist by explicitly substituting [`InertProviderDouble`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/adapters/t3mp3st_adapter.py) (clearly labeled as a test double).
- **Refusal comparison (`./scripts/run_demo.sh --refuse`)**: Skips replanning after the v1 decoy fix; the external oracle remains red and QualityGate refuses honestly.

No external Python dependencies (`pytest`, `requests`, etc.) are required. The system runs purely on standard library Python (>= 3.11, tested on Python 3.14.4) and Node (>= 22.19.0, tested on v22.22.1).

---

## 2. Structured Output Format

`./scripts/run_demo.sh` executes the end-to-end governed workflow across 13 distinct stages without exposing unverified chain-of-thought:

```text
RAPHAEL IBM BOB

[1] Mission
[2] Planning
[3] Authorization
[4] Broker / Policy
[5] Capability
[6] Execution
[7] Provider
[8] Evidence
[9] Verification
[10] Falsification
[11] Finding
[12] Replanning
[13] QualityGate

RESULT: COMPLETE / REFUSE
Evidence: runs/<run_id>/evidence.jsonl
```

---

## 3. Stage-by-Stage Breakdown

| Stage | Governed Component | Purpose & Verification Invariant |
|---|---|---|
| **[1] Mission** | [`Mission`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/contracts.py) | Declares explicit mission criteria, target file, defect symptom, and scope boundary (`fixtures`). |
| **[2] Planning** | [`Planner`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/planner.py) | Derives Plan A targeting the initial symptom (`login.py` decoy). |
| **[3] Authorization** | [`BOBPolicy`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/policy.py) & [`C1AAuthorizationBinding`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/c1a_authorization.py) | Demonstrates fail-closed rejection on unauthorized targets (`/etc/shadow` $\rightarrow$ `DENY`). Generates single-use HMAC-SHA256 authorization token sealing complete execution identity. |
| **[4] Broker / Policy** | [`BOBBroker`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/broker.py) | Mandatory mediation layer. No capability can be invoked directly; all actions pass `Runtime -> Broker -> Policy`. |
| **[5] Capability** | [`Capability`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/contracts.py) | Explicit allow-list (`READ`, `WRITE`, `LIST`, `SEARCH`, `RUN_TEST`, `C1A_STATIC_FILE_INSPECT`). `C1A` is not an alias for `READ`. |
| **[6] Execution** | Workspace & Bounds | Enforces workspace boundary containment and execution bounds/timeouts. |
| **[7] Provider** | [`T3MP3STAdapter`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/adapters/t3mp3st_adapter.py) | Governed out-of-process provider execution in bubblewrap (`bwrap`) sandbox with network denial and read-only mounts. Normalizes output as **UNTRUSTED evidence**; provider output cannot declare COMPLETE or VERIFIED. |
| **[8] Evidence** | [`EvidenceLedger`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/evidence_ledger.py) | Append-only, content-addressed JSONL ledger with cryptographic SHA-256 digests recording full causal provenance. |
| **[9] Verification** | [`Verifier`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/verifier.py) | Registers candidate finding `F-authkit` (`UNVERIFIED`). Applies v1 decoy fix via Broker WRITE; named unit test `test_login.py` passes under Broker RUN_TEST. Verifier records retest passed. |
| **[10] Falsification** | [`Falsifier`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/falsifier.py) | Executes external oracle (`probes/auth_behavior_probe.py`). Observes counter-example (expired/cross-user tokens accepted). Falsifier refutes candidate finding. |
| **[11] Finding** | [`FindingStore`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/finding.py) | Manages valid lifecycle state transition: `UNVERIFIED` $\rightarrow$ `REFUTED` with counter-example digest. |
| **[12] Replanning** | [`Replanner`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/replanner.py) | Consumes refutation evidence, rejects decoy, derives Plan B targeting `fixtures/authkit/session.py`. Installs v2 fix via Broker WRITE; regression tests and independent oracle pass. (Skipped in `--refuse` mode). |
| **[13] QualityGate** | [`BOBQualityGate`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/quality_gate.py) | Sole authority permitted to issue `COMPLETE`. Evaluates conditions A through G. Issues `COMPLETE` on full green, or `REFUSE` on unhealed failure. |

---

## 4. Exit Codes

- `0`: QualityGate evaluated to `COMPLETE`.
- `1`: QualityGate evaluated to `REFUSE` (e.g. `--refuse` or baseline comparison mode).
- `2`: Fatal environment or configuration error (missing prerequisites or provider unavailable when not in `--mock` mode).

---

## 5. Verification Scope & Limitations

1. **Local Sandboxed Execution Validated**:
   - The canonical demo executes the real pinned T3MP3ST provider locally inside a bubblewrap (`bwrap`) sandbox with network denial (`--unshare-net`) and read-only mounts.
2. **Controlled Release Gate**:
   - In accordance with safety policies, `LIVE_PROOF_AUTHORIZED = False` in [`scripts/c1a_live_proof.py`](file:///home/moiz/raphael-2.0-rbsv2r/scripts/c1a_live_proof.py).
   - Formal remote M1/M2/M5 live proof is marked **NOT VERIFIED**.
   - Seccomp status remains marked **NOT_EXECUTED** where formal seccomp BPF policy compilation is not attached.
3. **Test Suite Accounting**:
   - **Governed BOB Suite**: **1065 tests passed, 0 failures** across all 69 modules in the tree.
   - **Legacy Substrate Root-Discovery Errors**: 18 collection errors occur if running unguided `python3 -m unittest discover` because the tool attempts to import unadapted legacy test modules from the pre-BOB base repository (in `src/arena` requiring `pytest`). These 22 legacy files are strictly outside the governed BOB suite and isolated by test guards.
