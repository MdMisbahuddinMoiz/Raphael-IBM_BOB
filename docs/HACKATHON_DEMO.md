# RAPHAEL × IBM BOB — Hackathon Demo

This document explains what the demonstration shows, how to run it, what the
evaluator will see, and — precisely — what it does **not** claim.

Canonical entrypoint:

```bash
./scripts/run_hackathon_demo.sh --preflight   # READY / NOT READY / OPTIONAL
./scripts/run_hackathon_demo.sh --status      # environment + recent runs
./scripts/run_hackathon_demo.sh --success     # governed run → 7/7 COMPLETE
./scripts/run_hackathon_demo.sh --refuse      # honest refusal → REFUSE
./scripts/run_hackathon_demo.sh --tests       # one-command release suite
```

---

## 1. What RAPHAEL × IBM BOB demonstrates

Raphael is a **governed agentic execution loop**. It plans against a mission,
executes only through a mediated boundary, records append-only evidence, verifies
and falsifies its own findings, and lets a **single** QualityGate decide
completion.

The demo shows the governed **network** path end-to-end:

```text
TESTING / HTB
  → TargetProfile (authorized target)
  → NETWORK_HTTP_REQUEST (the only network capability: HTTP GET/HEAD)
  → Policy ALLOW
  → execution through Runtime → Broker → Policy → NetworkMediator
  → independent behavior probe (separate governed observation)
  → RUN_TEST
  → regression evidence
  → QualityGate
  → 7/7 COMPLETE
```

and the honest counterpart:

```text
target/service unavailable (or required evidence absent)
  → no fabricated result
  → QualityGate REFUSE
```

---

## 2. Architecture

```text
                                  Operator
                                     │  (UI / HTTP API only)
                                     ▼
                             BOB HTTP / UI
                    /command /operations /mode /htb/target
                                     │
                                     ▼
                                  Harness
              (mission session, deterministic network runner)
                                     │
                                     ▼
                                  Mission
                (criteria, scope, problem: paths + tests)
                                     │
                                     ▼
                              ActionRequest
                    (capability, target, purpose, timeout)
                                     │
                                     ▼
                                  Runtime
                                     │
                                     ▼
                                  Broker ─────────────► EvidenceLedger
                                     │                  (append-only JSONL)
                                     ▼
                                  Policy
                       (allow-list, scope, TargetProfile)
                                     │
                                     ▼
                                 Capability
                    (READ/WRITE/LIST/SEARCH/RUN_TEST/…,
                     NETWORK_HTTP_REQUEST = HTTP GET/HEAD only)
                                     │
                                     ▼
                             NetworkMediator
                        (out-of-process HTTP GET, no redirects,
                         replay guard, digest of response)
                                     │
                                     ▼
                              EvidenceLedger
                                     │
               ┌─────────────────────┼─────────────────────┐
               ▼                     ▼                     ▼
            Verifier              Probe                 Falsifier
        (independent verify)  (independent          (decoy / counter-
                               behavior oracle)       example challenge)
               └─────────────────────┼─────────────────────┘
                                     ▼
                               QualityGate  (conditions A–G)
                                     │
                        ┌────────────┴────────────┐
                        ▼                          ▼
                    COMPLETE                    REFUSE
```

> **COMPLETE can only come from the QualityGate.** No caller, provider,
> capability, or demo script can emit it. The demo driver only *reads* the
> persisted gate record.

---

## 3. Governance flow

1. **Declare** — the operator declares a `TargetProfile` (platform, locator,
   allowed ports/protocols, scope, authorization reference). Declaration is not
   authorization.
2. **Request** — the Harness builds an `ActionRequest`; the Runtime stamps it
   with dense sequence numbers.
3. **Mediate** — the Broker routes every request through Policy. Policy enforces
   the capability allow-list and target scope (network targets against the
   `TargetProfile` scope, not the workspace path).
4. **Execute** — only an ALLOWed capability executes; `NETWORK_HTTP_REQUEST`
   issues a single out-of-process HTTP GET (no redirects, no scanning).
5. **Record** — request → decision → result → evidence are appended to the
   immutable ledger with SHA-256 digests.
6. **Verify / Probe / Falsify** — the Verifier confirms findings, the
   independent probe asserts a behavior invariant, the Falsifier challenges the
   finding (a decoy path must not return the flag).
7. **Gate** — `BOBQualityGate` evaluates conditions **A–G** purely from the
   ledger and issues `COMPLETE` or `REFUSE`.

### QualityGate conditions

| # | Condition | Requirement |
|---|---|---|
| A | `A:mission-criterion` | non-empty mission criteria |
| B | `B:required-tests` | a `RUN_TEST` whose artifact reports `returncode == 0` |
| C | `C:regression` | a `producer="regression"` record + ≥ 2 distinct ALLOWed capabilities |
| D | `D:independent-behavior-probe` | a `producer="probe"` record with `payload.allowed is True` |
| E | `E:scope` | every target within the mission scope / TargetProfile scope |
| F | `F:evidence` | complete request → decision → result → evidence chain |
| G | `G:finding-state` | no unresolved UNVERIFIED, REFUTED-without-replan, or invalid VERIFIED findings |

---

## 4. Success demo (DEMO A)

```bash
./scripts/run_hackathon_demo.sh --success
```

The driver talks only to the product HTTP API and then reads the persisted run.

Expected (validated) output — abbreviated:

```text
[6] Governed execution
     run_id: 20260922T184344_cad5ac
[7] Evidence
     producers: ['execution', 'network', 'policy', 'probe', 'regression']
[8] Verification / probe
     probe: allowed=True invariant=authorized-http-endpoint-reachable-and-serving status=200 bytes=11159
     regression: test=test_ok.py returncode=0 result=passed
[9] QualityGate
     [*] A:mission-criterion
     [*] B:required-tests
     [*] C:regression
     [*] D:independent-behavior-probe
     [*] E:scope
     [*] F:evidence
     [*] G:finding-state
[10] Final verdict
     conditions: 7/7
     verdict: COMPLETE
RESULT: 7/7 COMPLETE
```

Exit code `0`.

---

## 5. Refusal demo (DEMO B)

```bash
./scripts/run_hackathon_demo.sh --refuse
```

The driver declares an **authorized but unavailable** service. The governed
requests are ALLOWed by Policy, but the service does not answer, so no probe
evidence exists. Raphael records the failure and the gate refuses.

```text
[7] Evidence
     producers: ['execution', 'network', 'policy', 'regression']
     network: / state=refused status=None bytes=0
[9] QualityGate
     [x] D:independent-behavior-probe
     failed: ['D:independent-behavior-probe']
     reasons: ['behavior_probe_ok=False (no probe proof supplied)']
[10] Final verdict
     conditions: 6/7
     verdict: REFUSE
RESULT: REFUSE (honest: failure was not reported as COMPLETE)
```

Exit code `0` (the demo objective — an honest refusal — was met). If a refusal
run ever rendered `COMPLETE`, the driver would exit `1`.

---

## 6. UI pages to open

| Page | What to look at |
|---|---|
| `/command` | Command Center — mission + recent runs |
| `/operations` | Operations console — mode, VPN, target, start |
| `/operations/{run_id}` | run overview, state, gate verdict |
| `/operations/{run_id}/decision-trace` | gate A–G checklist (7/7 or the failed condition) |
| `/operations/{run_id}/events` | append-only event stream |
| `/operations/findings` | findings and their lifecycle states |
| `/operations/evidence` | evidence records by producer |
| `/runs` | durable run index |
| `/runs/{run_id}/gate` | the persisted gate record |
| `/mode` | product mode (`testing` / `htb`) |
| `/vpn/status` | VPN state (secrets never exposed) |
| `/htb/target` | declared TargetProfile |

---

## 7. Exact operator sequence

```bash
cd <repo>
# 1. (optional external target) bring up the VPN
# 2. start the server
RAPHAEL_OPENVPN_BIN=/usr/sbin/openvpn PYTHONPATH=. \
  python3 -m raphael_ibm_bob.http --host 127.0.0.1 --port 8787 &

# 3. preflight
./scripts/run_hackathon_demo.sh --preflight

# 4. success
./scripts/run_hackathon_demo.sh --success

# 5. refusal
./scripts/run_hackathon_demo.sh --refuse

# 6. one-command release suite
./scripts/run_hackathon_demo.sh --tests
```

Environment overrides: `RAPHAEL_BASE_URL`, `RAPHAEL_TARGET_HOST`,
`RAPHAEL_TARGET_PORT`, `RAPHAEL_REQUEST_PATH`, `RAPHAEL_PROBE_PATH`,
`RAPHAEL_MISSION_ID`.

---

## 8. Expected QualityGate output

Success: all seven conditions PASS, `failed=[]`, `unknown=[]` → `COMPLETE (7/7)`.

Refusal: `D:independent-behavior-probe` FAIL with reason
`behavior_probe_ok=False (no probe proof supplied)` → `REFUSE (6/7)`.

The pass/fail split shown in the UI is derived from the **persisted** gate
record (its `payload.passed/failed` when present, otherwise its `reasons`);
UNKNOWN is preserved as UNKNOWN and never rendered as a pass.

---

## 9. Evidence interpretation

For a run, `runs/<run_id>/` contains `harness.json` (run record),
`evidence.jsonl` (append-only ledger), and `artifacts/` (result payloads).

Key records:

- `request` / `decision` / `result` — the governed action and its Policy outcome.
- evidence `producer="network"` — the raw HTTP observation (state, status,
  bytes, response digest, invocation id).
- evidence `producer="probe"` — the independent behavior probe; condition D
  requires `allowed is True` and a distinct invocation from the flag request.
- evidence `producer="regression"` — the regression proof tied to the passing
  `RUN_TEST`.
- `gate` — the QualityGate decision (the sole completion authority).

See [`demo/success/`](../demo/success) and [`demo/refusal/`](../demo/refusal)
for exported, machine-readable bundles (`run.json`, `ledger.jsonl`, `gate.json`,
`summary.json`, `transcript.txt`).

---

## 10. Known limitations

- **No exploitation.** The governed capability is `NETWORK_HTTP_REQUEST`
  (HTTP GET/HEAD only). There is no shell, SMB, Telnet, privilege escalation,
  port scanning, or arbitrary HTTP method.
- **No HTTP-served flag from the Breakout VM.** Breakout's flags live in files
  (`/root/rOOt.txt`, `/home/cyber/user.txt`) and are not served by the HTTP
  surface; the mission's flag pattern is `HTB{...}`. The successful run
  therefore reaches `COMPLETE` with condition G satisfied as "no unresolved /
  refuted / invalid findings" — **not** by capturing a flag.
- **VPN** is required only for external HTB targets; the local demo target does
  not need it.
- **Legacy substrate** under `src/` is outside the governed runtime and is not
  imported by it.

### Claim boundary (explicit)

Do **not** claim that "Raphael solved Breakout" or that "Raphael captured and
verified the Breakout root flag". The validated claim is:

> Raphael executed a governed HTTP operation against the Breakout VM, produced
> independent behavior-probe evidence, satisfied the required regression/evidence
> conditions, and reached QualityGate `COMPLETE`. The Breakout VM did not expose
> its final root flag through the governed HTTP capability.

---

## 11. Reproducibility

1. Python ≥ 3.11 (validated on 3.14.4). No third-party Python packages are
   required by the governed core or the demo.
2. Start the server (see §7).
3. For a local target: any HTTP service that answers `GET /` and `GET /index.html`
   (e.g. a stock Apache page). For an external HTB target: connect the VPN and
   set `RAPHAEL_TARGET_HOST` / `RAPHAEL_TARGET_PORT`.
4. Run `--preflight`, `--success`, `--refuse`, `--tests`.
5. Re-export evidence for any run with:
   `python3 scripts/demo_export.py <run_id> demo/<name>`.

The validated reference runs are
`20260922T184344_cad5ac` (COMPLETE, 7/7) and `20260922T184344_7686de`
(REFUSE, 6/7).
