# Raphael-IBM_BOB — Evidence-Driven AI Control Loop (IBM BOB MVP)

RAPHAEL IBM BOB is a governed agentic execution system: it plans against a
mission, acts only through a mediated boundary (Runtime → Broker →
Policy), verifies and falsifies its own findings, replans from
refuted claims, and lets a single QualityGate decide completion.
Every action leaves append-only evidence. Nothing executes outside
the boundary.

```text
Mission → Plan A → Runtime → Broker → Policy → Evidence → Finding
→ Verification → Falsification → Refutation → Replanning
→ Plan B / Plan C → Independent verification → QualityGate
→ COMPLETE / REFUSE
```

---

## Quickstart & Canonical Judge Demo

No installation step is required: `raphael_ibm_bob`, the demos, and the tests are
stdlib-only in their Python imports. Test execution spawns subprocesses for `RUN_TEST`
capabilities, the independent probe, and sandboxed provider inspection.

```bash
# 1. Canonical judge demonstration (13 stages -> QualityGate: COMPLETE, exit 0)
./scripts/run_demo.sh

# 2. Honest refusal demonstration (exit 1, QualityGate: REFUSE via failed oracle probe)
./scripts/run_demo.sh --refuse

# 3. Validate environment prerequisites (Python, Node, bwrap, pinned digests)
./scripts/run_demo.sh --check-prereqs

# 4. Standard deterministic hero demo
PYTHONPATH=. python3 demos/authkit_hero.py

# 5. Core test suite (209 tests, 0 failures)
PYTHONPATH=. python3 -m unittest tests.test_seam_contracts tests.test_m2_boundary tests.test_m3_evidence tests.test_m4_verifier_falsifier tests.test_m5_replanner_runner tests.test_m6_quality_gate tests.test_m7_hero tests.test_m8_planner tests.test_m9_multi_replan tests.test_m10_1_runs tests.test_m10_2_metrics tests.test_m10_3_benchmark

# 6. T3MP3ST real provider integration suite (30 tests, 0 failures)
PYTHONPATH=. python3 -m unittest tests.test_t3mp3st_integration

# 7. Audit durable run evidence
python3 scripts/audit_runs.py --runs-root runs --output metrics.json
```

Each run writes an isolated `runs/<run_id>/{evidence.jsonl,artifacts/}`
(never `/tmp`, never appended across runs) and outputs the run ID,
evidence path, and gate verdict. Fixture files self-restore on exit,
ensuring `git status` remains clean.

See [`CANONICAL_DEMO.md`](CANONICAL_DEMO.md) for full demo documentation.

---

## Hackathon Demo

The governed **network** path (TESTING / HTB) has a dedicated canonical
entrypoint. It drives the real product HTTP API only — the same endpoints the
UI uses — and reads the persisted run ledger. It never bypasses the
Broker/Policy boundary and never constructs a verdict.

```bash
./scripts/run_hackathon_demo.sh --preflight   # READY / NOT READY / OPTIONAL
./scripts/run_hackathon_demo.sh --success     # governed run  -> 7/7 COMPLETE
./scripts/run_hackathon_demo.sh --refuse      # honest refusal -> REFUSE
./scripts/run_hackathon_demo.sh --tests       # one-command release suite
```

Full documentation: [`docs/HACKATHON_DEMO.md`](docs/HACKATHON_DEMO.md) ·
Operator checklist: [`docs/DEMO_CHECKLIST.md`](docs/DEMO_CHECKLIST.md) ·
Evidence bundle: [`demo/`](demo/README.md).

**What the evaluator will see.** A `TESTING/HTB` run that flows
`TargetProfile → NETWORK_HTTP_REQUEST → Policy ALLOW → execution → independent
probe → RUN_TEST → regression evidence → QualityGate`, with the `decision-trace`
page showing each condition `A`–`G` and the final count (`7/7`).

**What `COMPLETE` means.** All seven QualityGate conditions (A–G) evaluated
green against the ledger, backed by real evidence: a passing `RUN_TEST`
artifact, a `producer="regression"` record with ≥ 2 distinct ALLOWed
capabilities, and an independent `producer="probe"` record with `allowed=true`.
`COMPLETE` is emitted by the QualityGate alone.

**What `REFUSE` means.** Required evidence was absent (e.g. the authorized
service did not answer, so no probe proof exists). Raphael records the failure
and refuses — it never converts failure into `COMPLETE`.

**Current limitations.** The only network capability is `NETWORK_HTTP_REQUEST`
(HTTP GET/HEAD); there is no shell, SMB, Telnet, privilege escalation, port
scanning, or arbitrary HTTP method. The validated Breakout run reaches
`COMPLETE` without capturing a flag: Breakout does not serve its root flag over
HTTP, so condition G is satisfied as "no unresolved/refuted/invalid findings".
It is **not** a claim that Raphael solved Breakout.

---

## Core Invariants

RAPHAEL strictly enforces these foundational invariants across all layers:

1. **DECLARATION != AUTHORIZATION**: Declaring an action or target never grants permission.
2. **PROVIDER RESOLUTION != AUTHORIZATION**: Resolving a tool or provider binary does not authorize its execution.
3. **CAPABILITY RESOLUTION != EXECUTION**: Finding a capability handler does not invoke it.
4. **PROVIDER SUCCESS != VERIFIED FINDING**: A successful scan from a provider is UNTRUSTED evidence, never an authoritative finding.
5. **RETEST != PROOF**: A passing named test does not prove correctness; an independent oracle falsifies false-success decoy fixes.
6. **PROVIDER RESULT != QUALITY GATE COMPLETE**: The provider cannot declare completion. [`BOBQualityGate`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/quality_gate.py) is the SOLE authority permitted to emit `COMPLETE`.

---

## Architecture & Governed Lifecycle

### 1. Mandatory Broker Mediation
[`BOBBroker`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/broker.py) is the sole gateway to capability invocation (`execute_capability`). All requests from callers ([`Runtime`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/runtime.py), [`Planner`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/planner.py), [`Verifier`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/verifier.py), [`Falsifier`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/falsifier.py), [`Replanner`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/replanner.py)) are stamped with dense sequence numbers, validated through policy, and persisted to durable evidence.

### 2. Fail-Closed Policy
[`BOBPolicy`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/policy.py) enforces:
- An explicit capability allow-list: `READ`, `LIST`, `SEARCH`, `WRITE`, `RUN_TEST`, `C1A_STATIC_FILE_INSPECT`.
- Strict workspace path containment (preventing traversal and path escaping).
- Mission-scope containment via canonical path resolution in [`c1a_scope.py`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/c1a_scope.py).
- Capability invariants (e.g. `RUN_TEST` only allows test files matching `test_*.py` or `*_test.py`).

### 3. Cryptographic Authorization Binding
[`C1AAuthorizationBinding`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/c1a_authorization.py) generates single-use HMAC-SHA256 authorization tokens sealing the complete authoritative execution identity (`run_id`, `decision_seq`, `request_seq`, `invocation_id`, `proof_session_id`, `lifecycle_id`, `sandbox_id`, `capability_id`, `provider_id`, `target`, `fixture_path`). Any field mutation, replay, or foreign identity fails closed.

### 4. Append-Only Evidence Ledger
[`EvidenceLedger`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/evidence_ledger.py) records immutable JSONL records with SHA-256 digests. Causal ordering is strictly preserved:
`RequestRecord` $\rightarrow$ `DecisionRecord` $\rightarrow$ `PolicyEvidenceReceipt` $\rightarrow$ `ResultRecord` $\rightarrow$ `ExecutionEvidenceReceipt`.

### 5. Verification vs. Falsification
- **Verification** ([`Verifier`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/verifier.py)): Retests candidate findings against named test fixtures.
- **Falsification** ([`Falsifier`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/falsifier.py)): Actively searches for counter-examples using independent behavior probes (external oracles). When a counter-example is observed, the finding transitions to `REFUTED`.
- **Finding Store** ([`FindingStore`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/finding.py)): Enforces valid lifecycle transitions: `UNVERIFIED` $\rightarrow$ `REFUTED` $\rightarrow$ `SUPERSEDED` / `VERIFIED`. Direct transitions from `UNVERIFIED` to `SUPERSEDED` are rejected.

### 6. Replanning from Refuted Claims
[`Replanner`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/replanner.py) consumes refutation evidence and counter-example receipts from the ledger, rejects decoy targets, and derives Plan B targeting the root defect.

### 7. Output Quality Gate
[`BOBQualityGate`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/quality_gate.py) independently evaluates 7 strict conditions from the ledger before declaring `COMPLETE`:
- **A (Mission criterion)**: Non-empty mission criteria.
- **B (Required tests)**: Required test pass backed by an artifact proving `returncode == 0`.
- **C (Regression breadth)**: Full regression backed by $\ge 2$ distinct allowed capability actions.
- **D (Independent probe)**: Independent behavior probe passes (backed by probe evidence).
- **E (Scope)**: All targets strictly contained in workspace and declared mission scope.
- **F (Evidence)**: Complete request, decision, result, and evidence chain.
- **G (Finding state)**: No unresolved unverified findings, and all refutations followed by replanning.

---

## C1A & T3MP3ST Integration

`Capability.C1A_STATIC_FILE_INSPECT` provides governed out-of-process static-file inspection via T3MP3ST (`binary_sink_scan`). It is **not** an alias of `READ`.

- **Real T3MP3ST Provider**: Executed via the canonical path:
  `RAPHAEL -> bwrap -> RAPHAEL bridge -> binarySinkScanTool.handler()`
- **Bubblewrap Sandbox**: Enforces `--unshare-net` (network denial) and read-only mounts (`--ro-bind`); the sandbox also carries a locally built seccomp filter (`--seccomp`). Remote-kernel seccomp BPF attachment is **not demonstrated** (see Honest Limitations).
- **RAPHAEL-Owned Bridge** ([`provider/t3mp3st_bridge.js`](file:///home/moiz/raphael-2.0-rbsv2r/provider/t3mp3st_bridge.js)): Pinned by SHA-256 digest (`ea5616e...`). The bridge excludes raw authority findings (`severity`, `cwe`, `title`, `details`) from output receipts.
- **Untrusted Evidence**: Provider receipts are recorded with `provider_untrusted: True`. Provider output can never assert `VERIFIED`, `REFUTED`, or `COMPLETE`.
- **Inert Provider Double**: [`InertProviderDouble`](file:///home/moiz/raphael-2.0-rbsv2r/raphael_ibm_bob/adapters/t3mp3st_adapter.py) serves as a standalone local test double when external provider checkouts are absent.

---

## Status & Test Verification

All counts verified by actual command execution:

- **Full Governed BOB Suite (80 modules)**: **1165 tests, 0 failures** (Python 3.14.4).
- **Core Seam & Gov-Loop Suite (12 modules)**: **209 tests, 0 failures**.
- **C1A Provider & Authorization Suite (13 modules)**: **95 tests, 0 failures**.
- **T3MP3ST Integration Suite**: **30 tests, 0 failures** (including real sandboxed provider execution).
- **Isolation Substrate Suite**: **144 tests, 0 failures**.
- **Canonical Demo (`./scripts/run_demo.sh`)**: Exits 0, `Gate: COMPLETE` (demands real sandboxed provider).
- **Refusal Mode (`./scripts/run_demo.sh --refuse`)**: Exits 1, `Gate: REFUSE`.
- **Mock Mode (`./scripts/run_demo.sh --mock`)**: Exits 0, `Gate: COMPLETE` (explicit inert test double).
- **Legacy Root Discovery**: `python3 -m unittest discover -s tests -p "test_*.py"` reports **1183 test entries collected: 1165 governed pass + 18 legacy errors**, with zero governed failures. The **18 pre-existing collection/import errors** come from unadapted legacy modules that import the `arena` substrate (`ModuleNotFoundError`); the error set is byte-identical run-to-run. These modules are outside the governed BOB suite and test-isolated.

---

## Project Layout

```text
raphael_ibm_bob/   Governed core: contracts, broker, policy, workspace,
                   capabilities, runtime, evidence ledger, finding store,
                   verifier, falsifier, replanner, runner, quality gate,
                   c1a_authorization, c1a_transport, c1a_scope,
                   isolation_substrate, seccomp_policy, adapters/
provider/          c1a_launcher.js, t3mp3st_bridge.js (pinned bridge)
demos/             canonical_hero.py (13-stage runner), authkit_hero.py,
                   c1a_live_hero.py, live_authkit_hero.py
probes/            auth_behavior_probe.py (independent oracle)
fixtures/          Deterministic authkit scenario (login.py, session.py, store.py)
scripts/           run_demo.sh (judge runner), audit_runs.py (metrics audit),
                   c1a_live_proof.py (controlled release gate)
tests/             Comprehensive 80-module governed test suite (1165 tests)
runs/              Durable per-run evidence ledgers (git-ignored)
```

---

## Honest Limitations

1. **Live Proof Gate (Live proof is BLOCKED)**: In accordance with Controlled Release requirements, `LIVE_PROOF_AUTHORIZED = False` in [`scripts/c1a_live_proof.py`](file:///home/moiz/raphael-2.0-rbsv2r/scripts/c1a_live_proof.py). While real T3MP3ST executes locally in the bubblewrap sandbox (`provider_execution = VERIFIED`), formal remote M1/M2/M5 closure is marked **NOT VERIFIED** (seccomp `NOT_EXECUTED`).
2. **Benchmark Scope**: Evaluated on the canonical deterministic `authkit` scenario; multi-repo generalization is not claimed.
3. **Legacy Substrate**: The repository substrate includes earlier offensive research platform files in `src/` which are strictly isolated and not imported by the governed IBM BOB runtime.
4. **D5-7 Controlled VulnHub E2E (BLOCKED / OUT OF SCOPE FOR THIS RELEASE)**: no supported controlled VulnHub target/environment is present in this checkout or host. Legacy Stapler (VulnHub) material under `evaluations/campaign/` and `current-state/reports/` is historical evidence from a different lab host; the VM image and lab bridge (`icabr0`, `10.66.0.0/24`) are unavailable here, and the governed runtime has no network target adapter. No VulnHub execution, VM availability, reachable target IP, or kill chain is claimed.

---

## License

MIT License — Copyright (c) 2024-2026 The-Despicable
