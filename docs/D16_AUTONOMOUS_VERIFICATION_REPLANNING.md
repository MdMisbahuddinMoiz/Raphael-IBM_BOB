# D16 Autonomous Verification Replanning (Wave 1)

Status: Wave 1 semantics milestone. D16 proves, with passing deterministic
tests, that the agent's next action is a pure function of governed,
newly observed world state — not of target identity, scenario branching,
or speculation. It reuses the frozen D14/D15 contracts without rank
fields and executes nothing new.

Related: `docs/D15_CAPABILITY_EXPANSION.md` (two-tier capability model),
`docs/D13_CAPABILITY_FABRIC.md` (fabric), `docs/D15_D16_HANDOFF.json`
(machine-readable D15→D16 inventory), `docs/PROVENANCE.md` (attribution).

Scope note: this document describes a **generic governed autonomous
security-assessment agent for authorized/CTF targets**. It does not
describe a fully autonomous hacker, it adds no offensive capability, and
it performs no target-name branching. All episodes below use synthetic
targets (`synthetic.invalid`, `127.0.0.1`) on the existing governed
seams.

Provenance of this document: every behavioral claim cites the landed
module and the passing test that pins it. Claim inventory (§10) lists
exactly which tests were run to authorize each claim.

---

## 1. Architecture

D16 Wave 1 is a thin semantic layer over frozen seams. No new execution
path, no new capability, no governance edit.

```
select -> execute -> observe -> update -> replan
```

| Phase | Landed authority | Role in D16 |
|---|---|---|
| `SELECT` | `raphael_ibm_bob/d14_planner.py` (`Planner.plan`, lines 114–193) | Deterministic next-action proposal from a `WorldState`. Non-executing, non-authorizing. |
| `REQUEST` / `EXECUTE` | `raphael_ibm_bob/runtime.py` → `raphael_ibm_bob/broker.py` → `raphael_ibm_bob/policy.py` | The only execution path. Broker stamps dense sequence numbers, consults Policy, persists to the evidence ledger. |
| `OBSERVE` | `raphael_ibm_bob/observation_model.py` (`ObservationRecord`, lines 21–45) + `raphael_ibm_bob/d14_state_codec.py` (`EvidenceBinding`, lines 16–32; `ReadOnlyLedgerView`, lines 27–32) | Normalized observation + its immutable execution binding (evidence id, request seq, policy decision, result success, session id). |
| `UPDATE_WORLD` | `raphael_ibm_bob/d14_world_state.py` (`reduce_world_state`, lines 138–193) | Pure fold of one `ObservationUpdate` into a new immutable `WorldState`. No execution, no evidence writes. |
| `VERIFY` | `raphael_ibm_bob/verifier.py` (`Verifier.verify`, lines 102–250) | Broker-mediated retest of a candidate finding (see §3). |
| `FALSIFY` | `raphael_ibm_bob/falsifier.py` (`Falsifier.challenge`, lines 109–259) | Broker-mediated counter-example search (see §3). |
| `REPLAN` | `raphael_ibm_bob/d14_replan.py` (`ReplanDecision`, lines 15–26); finding-level replan `raphael_ibm_bob/replanner.py` (`Replanner.replan`, lines 114–196) | D16 uses `ReplanDecision` as the plan-replacement descriptor; the finding-level `Replanner` (Plan B from a REFUTED finding) is reused conceptually but is not re-triggered by D16's state loop (see §4). |
| `STOP` | `raphael_ibm_bob/d14_stop.py` (`evaluate`, lines 79–97; `StopCondition`, lines 22–33) | Pure, side-effect-free stop check evaluated before any replan (see §6). |
| Verdict | `raphael_ibm_bob/quality_gate.py` (`BOBQualityGate.evaluate`, conditions A–G, lines 12–36) | Sole authority that may emit `COMPLETE`. D16 never constructs a verdict. |
| Loop vocabulary | `raphael_ibm_bob/d14_loop.py` (`AutonomyState`, lines 8–19) | Phase names (`OBSERVE … REPLAN … STOP`) are vocabulary only, never completion verdicts. |

D16's own landed surface is exactly one test module,
`tests/test_d16_replanning_semantics.py` (4 tests, all passing — §10),
plus the reused frozen D14 seams it cites in its docstring
(`d14_planner.py:114-192`, `d14_replan.py:15-26`, `d14_stop.py:79-97`,
`d14_world_state.py:138-193`).

---

## 2. State transition

### 2.1 World state (D16's replan input)

`WorldState` (`d14_world_state.py:69-93`) is immutable: `mission_id`,
`target_id`, `revision`, deep-copied `TargetFacts`, `endpoints`
(`EndpointBand`: `unknown | candidate | confirmed | refuted |
conflicted`), `hypotheses`, `observations`,
`applied_observation_ids`, `last_source_seq`, `step_count`,
`replan_count`, `failure_count`, `progress_token`, `world_state_hash`.

`initial_world_state` (`d14_world_state.py:107-135`) builds revision 0
from a `Mission` plus existing `TargetFacts`; pre-existing services
start as `CONFIRMED` endpoints. No observation timestamp participates in
the derived hash or progress token.

`reduce_world_state` (`d14_world_state.py:138-193`) folds one
`ObservationUpdate` (observation + monotonic `source_seq` + mandatory
`evidence_id`, `d14_world_state.py:53-66`):

1. `_validate_ingestion` (lines 196–220) resolves the `evidence_id`
   through the read-only ledger view and rejects unless it binds to
   Policy `ALLOW` + successful result + non-empty session, with fresh
   provenance (see §7).
2. Duplicate `observation_id` returns the prior snapshot **unchanged**
   (lines 153–154) — the no-new-state case the first D16 test pins.
3. Otherwise the endpoint band advances via `next_band`
   (`d14_state_codec.py:69-81`), services insert through the existing
   `TargetFacts.add_service` seam on a deep copy (prior snapshot never
   mutated), and revision / step count increment; `replan_count`
   increments only if `replan_requested=True` (lines 174–193).
4. Hash and progress token are recomputed canonically (`_build_state`,
   lines 236–290; payload shape in `d14_state_codec.py:112-145`;
   volatile keys `timestamp` / `discovered_at` excluded,
   `d14_state_codec.py:200-211`).

### 2.2 Finding lifecycle (verification/falsification substrate)

D16 Wave 1 does not alter the M4 finding lifecycle; it documents it
because verification/falsification semantics (§3) and the finding-level
replan trigger (§4) run on it. `FindingStore`
(`raphael_ibm_bob/finding.py:39-44`) is the sole transition authority:

```
UNVERIFIED -> VERIFIED | REFUTED
VERIFIED   -> REFUTED | SUPERSEDED
REFUTED    -> SUPERSEDED
SUPERSEDED -> (terminal)
```

Structural rule: `UNVERIFIED -> SUPERSEDED` is rejected
(`finding.py:10-11,147-151`). Registration requires `UNVERIFIED`
(`finding.py:71-107`); every transition persists a `FindingRecord` to
the evidence ledger before in-memory publication (`finding.py:180-193`).

---

## 3. Verification / falsification semantics

Both engines are broker-mediated: they submit ordinary `ActionRequest`s
through `Runtime -> Broker -> Policy` and only transition on observed,
ALLOW-bound evidence. Neither consults Policy itself nor bypasses the
governed path.

**Verification** (`verifier.py:102-250`). `verify(finding, retest,
mission)`:

- Non-`UNVERIFIED` findings return immediately with
  `finding-not-unverified:*`; no execution.
- Builds a finding-tagged request, submits through the runtime,
  persists a `producer="verifier"`, `kind="retest"` record linked by
  `finding_id` (lines 152–173).
- On Policy `DENY`: finding stays `UNVERIFIED` (`retest-denied:*`); the
  denial is durable in the ledger.
- On `ALLOW`: checks execution succeeded and, if `expected_substring`
  is set, that it appears in the payload; mismatch leaves `UNVERIFIED`
  (`retest-output-mismatch`).
- On match: persists a `kind="observation"` receipt (lines 200–221) and
  transitions `UNVERIFIED -> VERIFIED` (`retest-ok`).

**Falsification** (`falsifier.py:109-259`).
`challenge(finding, spec, mission)` requires `VERIFIED`:

- Non-`VERIFIED` findings return `finding-not-verified:*`; no execution.
- Submits the challenge, persists `kind="challenge"` (lines 145–166).
- `DENY` or failed execution: no transition (`challenge-denied:*` /
  `challenge-execution-failed`).
- Counter-example detection (`_detect_counter_example`, lines 261–278):
  `predicate` takes precedence; else `forbidden_substring` match over
  the payload; else `no-spec` (no counter-example).
- No counter-example: stays `VERIFIED` (`no-counter-example`).
- Observed counter-example: persists `kind="counter-example"` carrying
  the challenge `target` and `capability` (lines 203–228, M5 feed for
  Plan-B target derivation) and transitions `VERIFIED -> REFUTED`
  (`counter-example-observed`).

Net semantics: verification promotes `UNVERIFIED -> VERIFIED` only on
positive retest evidence; falsification demotes to `REFUTED` only on a
real observed counter-example. Absence of a counter-example is not
proof; denial or failure leaves state unchanged and stays durable.

---

## 4. Replanning trigger

D16 Wave 1 distinguishes two replan mechanisms and triggers only the
first; the second is documented for handoff, not invoked.

**(a) State-driven reselect (D16 trigger, tested).** After a governed
observation is folded by `reduce_world_state`, the same `Planner` is
invoked on the new `WorldState`. The trigger is the new observation /
new state — expressed in the tests as `ReplanDecision(should_replan=True,
reason="observation_changed_state", trigger_hypothesis_id="H-A")`
(`test_d16_replanning_semantics.py:213-221`). The planner filters out
already-observed capabilities (case-insensitive match on
`observation.capability_id`, `d14_planner.py:153-161`), so the accepted
Action A observation removes A from the candidates and the same plan
selects its next action B. No rank fields are used: ordering is the
frozen `_selection_order_key` over lifecycle priority → confidence_bps
→ hypothesis id → capability id → canonical params/observations
(`d14_planner.py:271-280`), reused unchanged.

**(b) Refutation-driven Plan B (M5 finding-level, not D16's trigger).**
`Replanner.replan` (`replanner.py:114-196`) fires only on a real
evidence-backed `REFUTED` finding with non-empty diagnostic evidence,
derives the new target from the `counter-example` evidence
(`replanner.py:227-254`), emits exactly one step with
`requester="replanner"`, deterministic id
`derive_plan_b_id(parent, refuted_id)`, parent linkage
(`parent_plan_id`), and a `producer="replanner"` ledger record. D16
Wave 1 constructs no `FocusedContext`s and no Plan Bs; it cites this
path so D17 knows where refutation replanning lives.

Non-triggers (D16-tested): unchanged state (§5, first case), terminal
gate (§6), policy denial before execution (§6).

---

## 5. The action-difference proof

Claim: the replanned action differs from the baseline action **if and
only if** a new governed observation changed the world state; the
difference is causally attributable to that observation/state, with
mission and target identity held constant.

Pinned by two passing tests in
`tests/test_d16_replanning_semantics.py` (run:
`wsl python3 -m unittest tests.test_d16_replanning_semantics -v` →
Ran 4, OK):

**Case 1 — no new state, same action repeats**
(`test_same_action_repeats_when_execution_yields_no_new_state`, lines
167–191). Planning twice against the identical snapshot yields the
identical `NextAction` and the identical deterministic `decision_id`
(`SD-{sha256…}`, `d14_planner.py:243-254`); the test asserts
`world_state_hash` equality, `next_action` equality, and `decision_id`
equality. A `ReplanDecision(should_replan=True,
reason="state_unchanged")` describes the coordinator retry; the proof
point is that no identity or scenario branch is needed to produce the
repeat — determinism of `Planner.plan` on identical input suffices.

**Case 2 — new observation, action changes A → B**
(`test_action_changes_only_after_observation_updates_world_state`,
lines 193–232). Fixture: two-action plan DP-D16, Action A =
`NETWORK_HTTP_REQUEST` → `http://synthetic.invalid:80/`, Action B =
`NETWORK_TELNET_SESSION` → `telnet://synthetic.invalid:23/` (lines
84–96); hypotheses `H-A`, `H-B` bound per action (lines 99–124).
Baseline `planner.plan(state)` selects Action A. A governed success for
A is folded (`_observe`, lines 140–163: `ObservationRecord O-D16-A`,
`http_response`, ALLOW-bound `EvidenceBinding`, session `session-d16`,
fresh timestamp via patched `time.time`). Replanning from the updated
state selects Action B. The test asserts, jointly:

- `replanned_action != baseline_action` (the central difference);
- `replanned_action.capability_id == remaining[0]` (B is exactly the
  unobserved remainder of the same execution plan);
- `replanned.execution_plan == baseline.execution_plan` and
  `replanned.mission_id == baseline.mission_id` (same plan, same
  mission — no swap);
- `updated.target_id == state.target_id` (same target — no target-name
  branching);
- `updated.world_state_hash != state.world_state_hash` with
  `updated.observations[-1].capability_id ==
  baseline_action.capability_id` (the hash delta is bound to the Action
  A observation — causal attribution, not coincidence).

Note on the goal's "baseline Action B vs replanned Action B" phrasing:
the landed proof uses baseline **Action A** vs replanned **Action B**
(HTTP then Telnet). No landed test compares two Action Bs; this
document records what the code proves, not the looser phrasing.

Corroboration (passing, adjacent — not D16 claims): the D14 real-seam
episode (`tests/test_d14_autonomous_episode.py`, Ran 1 OK) executes
Action A through `BOBRuntime` with a synthetic opener, ingests it with
`replan_requested=True`, and derives a different next action with
`world_state_hash` changed and `replan_count == 1`; the D14 autonomy
suite (`tests/test_d14_autonomy.py`, Ran 11 OK) pins selection ordering,
prerequisite gating, denial-without-invocation, and no-progress stop on
the same frozen seams.

---

## 6. Stop conditions

Pure evaluator `evaluate(world_state, last_runtime_result,
gate_evaluation, config)` (`d14_stop.py:79-97`), checked in order,
side-effect-free. First match wins:

1. `MISSION_COMPLETE` — gate evaluation is `GateVerdict.COMPLETE`.
2. `POLICY_DENIAL` — last result carries `Decision.DENY`.
3. `NO_APPLICABLE_CAPABILITY` — rationale contains
   `NO_APPLICABLE_CAPABILITY` with `next_action is None`.
4. `MAX_STEPS` — `step_count >= max_steps` (default 5; provenance:
   `harness/loop.py:113-128`).
5. `MAX_REPLANS` — `replan_count >= max_replans` (default 1;
   provenance: `runner.py:170-214`).
6. `MAX_FAILURES` — `failure_count >= max_failures` (default 5,
   not-yet-ratified).
7. `NO_PROGRESS` — last `no_progress_window` (default 3) states share
   one `(world_state_hash, progress_token)` (not-yet-ratified).
8. `CONFIDENCE_THRESHOLD` — result `confidence_bps >= 2000`
   (not-yet-ratified).

D16 pins two terminal-before-replan cases (both passing):

- **Terminal state stops before replanning**
  (`test_terminal_state_stops_before_replanning`, lines 234–259): after
  the Action A observation the endpoint is `confirmed`; `evaluate(...,
  GateVerdict.COMPLETE, ...)` returns `StopCondition.MISSION_COMPLETE`
  and `ReplanDecision(should_replan=False, reason="terminal_state",
  next_action=None)` carries no replacement action. Completion wins.
- **Ungovernable action refused before observation**
  (`test_ungovernable_action_is_refused_before_observation`, lines
  261–297): D15's declaration-only `NETWORK_SSH_SESSION` (registered via
  `register_ssh`, bound to `InertAdapter`) proposed as an action is
  `Decision.DENY` under `BOBPolicy`; `evaluate` returns
  `StopCondition.POLICY_DENIAL`; `ReplanDecision(should_replan=False,
  reason="policy_denial", next_action=None)` carries nothing, and the
  test asserts `observations == ()` — refusal precedes execution, so no
  observation can ever be created from it.

Stop-audit and finalization payloads (`stop_audit_payload`,
`run_finalize_payload`, `d14_stop.py:100-130`) are built, never
persisted, by D14; the outer coordinator persists them. The QualityGate
conditions A–G (`quality_gate.py:12-36`) remain the sole completion
authority above stops: mission criteria, required tests with
`returncode == 0` artifact, regression breadth (≥2 distinct ALLOWed
capabilities), independent probe, scope containment, evidence-chain
completeness, and finding-state closure (no unresolved `UNVERIFIED`;
every `REFUTED` followed by replan evidence).

---

## 7. Provenance requirements

Every observation admitted to world state must satisfy all of the
following (`d14_world_state.py:196-220`,
`observation_model.py:102-126`, `d14_state_codec.py:16-46`):

1. **Evidence binding**: `ObservationUpdate.evidence_id` is mandatory;
   the read-only ledger view (`EvidenceLedgerView.resolve_evidence`,
   `d14_ledger_view.py:14-46`) must resolve it to a decision record and
   a result record for the same `request_seq`.
2. **ALLOW + success**: `policy_decision == "allow"` (case-insensitive)
   and `result_success is True`; anything else raises `ValueError` and
   the state is untouched.
3. **Session binding**: non-empty `session_id` on the binding; the
   observation's `provenance["session_id"]` must equal it
   (`ProvenanceValidator.validate_fresh` — "session mismatch" rejects
   cross-session observations, the generalized D12 stale-prompt fix).
4. **Freshness**: `time.time() - timestamp <= 300s` (default
   `max_age_seconds`); stale observations rejected.
5. **Command binding** (where applicable): `validate_command_binding`
   ties output to the exact command, not a buffer/prompt.
6. **Canonical hash stability**: `observation_payload`
   (`d14_state_codec.py:187-197`) hashes `content_hash` and canonical
   provenance only — `timestamp`/`discovered_at` excluded
   (`canonical_value`, lines 200–211), so freshness is enforced by the
   validator, not the hash.
7. **Deduplication**: applied `observation_id`s are recorded in
   `applied_observation_ids`; re-ingestion returns the same snapshot
   (`d14_world_state.py:153-154`).
8. **Finding linkage** (verify/falsify path): retest / challenge /
   counter-example receipts carry `finding_id`
   (`verifier.py:152-173,200-221`; `falsifier.py:145-166,203-228`);
   finding transitions persist `FindingRecord`s with evidence seqs
   (`finding.py:180-193`); the finding-level replanner additionally
   rejects cross-finding diagnostics, failed-independence results, and
   authority keys (`replanner.py:198-225`).

---

## 8. Deterministic synthetic episode

The canonical D16 episode (`tests/test_d16_replanning_semantics.py`,
helpers lines 50–163) is fully synthetic and fully deterministic:

- Mission `M-D16`, scope `scope://synthetic/d16`; facts: host
  `synthetic.invalid`, service `synthetic.invalid:80/http` (lines
  50–54, 127–130).
- Fixed two-step plan DP-D16 (Action A HTTP, Action B Telnet) via
  `_FixedSelector`; registry of `network_descriptors()` bound to
  `InertAdapter` (planning only — plan-step execution is not performed
  in the D16 module; observation folding goes through
  `reduce_world_state` with an `_AllowedLedger` stub binding
  allow/success/`session-d16`, lines 65–81).
- Observation `O-D16-A` with patched `time.time() = 1_700_000_000.0`
  (lines 141–144), so hash, progress token, and freshness are
  bit-reproducible run to run.
- Sequence: `plan(state)` → A; `reduce_world_state` → revision + 1,
  hash changed; `plan(updated)` → B; terminal/refusal gates evaluated
  without side effects.
- Reproduction: `wsl python3 -m unittest
  tests.test_d16_replanning_semantics -v` → Ran 4, OK (measured
  2026-09-23 on this tree).

The adjacent real-seam episode
(`tests/test_d14_autonomous_episode.py`) differs deliberately: it runs
Action A through `BOBRuntime` (synthetic opener, no socket), persists a
producer evidence record, folds with `replan_requested=True`, and then
hits `NO_APPLICABLE_CAPABILITY` on the single-capability rig — proving
the seam wiring, not D16's two-action difference.

---

## 9. Security properties

What D16 Wave 1 holds (each tied to a passing assertion, not to prose):

- **Mediation inviolability**: all execution flows through
  `Runtime -> Broker -> Policy`; the planner, reducer, stop evaluator,
  and `ReplanDecision` have no execution import and perform no
  invocation (by construction: `d14_planner.py`, `d14_world_state.py`,
  `d14_stop.py`, `d14_replan.py` import no broker/runtime/policy
  execution path).
- **Fail-closed declaration**: Tier-1 `NETWORK_SSH_SESSION` executes
  nowhere — `InertAdapter.execute` raises `AdapterNotBoundError`
  (`capability_bootstrap.py:35-47`), `plan_to_action_requests` fails on
  unbound ids, and Policy denies the hand-built request
  (`Decision.DENY` asserted in the D16 refusal test).
- **No observation without ALLOW**: `_validate_ingestion` rejects
  DENY / failed / sessionless / stale / unresolvable bindings before
  any fold (`d14_world_state.py:196-220`).
- **Deny-before-execute**: the refusal test asserts `observations == ()`
  after `DENY` — nothing to fold, nothing to replan from.
- **Provenance-bound state**: session match + 300s freshness
  (`observation_model.py:102-126`); canonical hash excludes wall-clock
  fields so determinism and freshness do not conflict.
- **Ledger-gated completion**: only `BOBQualityGate` emits `COMPLETE`
  (`quality_gate.py:1-52`); D16 constructs no verdicts, only
  `ReplanDecision` descriptors and `SelectionDecision`s.
- **No new attack surface**: Wave 1 adds no capability, no network
  primitive, no target grammar, no prompt/branch on target names; the
  only new file is a test module.

---

## 10. Claim inventory (what was actually run)

| Claim in this doc | Authorizing evidence |
|---|---|
| Same-state → same action + same `decision_id` | `test_same_action_repeats_when_execution_yields_no_new_state` — PASS (Ran 4 OK, 2026-09-23) |
| New governed observation → action A→B, same plan/mission/target, hash delta bound to A's observation | `test_action_changes_only_after_observation_updates_world_state` — PASS |
| Terminal `COMPLETE` stops before replan, no next action | `test_terminal_state_stops_before_replanning` — PASS |
| Ungovernable SSH proposal denied before execution, zero observations, `POLICY_DENIAL` | `test_ungovernable_action_is_refused_before_observation` — PASS |
| Real-seam corroboration (execute A → ingest → different next action, `replan_count == 1`) | `tests/test_d14_autonomous_episode` — PASS (Ran 1 OK) |
| Selection ordering / prerequisites / denial-without-invocation / no-progress | `tests/test_d14_autonomy` — PASS (Ran 11 OK) |
| Verification/falsification transition semantics (§3) | Code as landed (`verifier.py`, `falsifier.py`, `finding.py`); covered by the M4 suite (`tests/test_m4_verifier_falsifier.py` in the 210-test core suite), **not re-run for this doc** — no fresh pass claimed here |
| Finding-level Plan-B derivation (§4b) | Code as landed (`replanner.py`); covered by the M5/M9 suites, **not re-run for this doc** — no fresh pass claimed here |

Anything not in this table is description of landed code, not a
pass-claim.

---

## 11. Known residuals

1. **D16 proves state-driven reselect, not refutation-driven replan.**
   The `ReplanDecision(reason="observation_changed_state")` path is
   pinned; end-to-end `REFUTED → Plan B → re-execute → gate` closure in
   the autonomous loop is D17 work.
2. **Single-observation episode.** Only one fold (A→B) is demonstrated;
   multi-step chains, conflicting observations (`conflicted` band),
   failure-kind folds, and `NO_PROGRESS` over the D16 rig are
   unexercised.
3. **`_AllowedLedger` stub.** The D16 module folds through a stub
   ledger view, not a persisted `EvidenceLedger`; real-seam ingestion is
   covered only by the adjacent D14 episode test.
4. **Not-yet-ratified bounds.** `MAX_FAILURES`, `NO_PROGRESS_WINDOW`,
   `CONFIDENCE_THRESHOLD_BPS` (`d14_stop.py:15-19`) are implemented but
   flagged not-yet-ratified; D16 exercises none of them directly.
5. **Hypothesis dynamics frozen.** Confidence bands (`d14_hypothesis.py`)
   are descriptive metadata; no landed path updates bands from
   observations in Wave 1.
6. **No live target.** Synthetic hosts only; no network socket is
   opened by the D16 module (the D14 episode uses a synthetic opener).
   Breakout/VulnHub scope limits in the README are unchanged.

---

## 12. D17 handoff

Suggested Wave 2 scope (no code changed by this doc):

1. **Close the refutation loop in the autonomous rig**: drive
   `VERIFIED → REFUTED` (falsifier with a synthetic counter-example)
   into `Replanner.replan` into re-execution, asserting Plan B's
   `parent_plan_id` linkage and `producer="replanner"` receipt inside a
   multi-step episode. Reuse `replan_count` / `MAX_REPLANS=1` accounting
   so the second replan hits `MAX_REPLANS` deterministically.
2. **Multi-fold episode**: extend the D16 two-action rig to A→B→C with a
   conflicting third observation; assert `conflicted` banding and
   `NO_PROGRESS` / `NO_APPLICABLE_CAPABILITY` termination.
3. **Real-ledger D16**: replace `_AllowedLedger` with
   `EvidenceLedgerView` over a temp `EvidenceLedger` (as the D14 episode
   does) so the ALLOW binding is persisted, not stubbed.
4. **Hypothesis-band dynamics**: decide whether observations update
   `confidence_band`/`confidence_bps` or bands stay descriptive; either
   way, pin `_selection_order_key` behavior with a dedicated test.
5. **Gate closure**: run the episode to `BOBQualityGate.evaluate` and
   assert condition G (refuted-followed-by-replan) green on the ledger.

Constraints carried forward: modify no frozen D14/D15 seam semantics to
do it; no new offensive capabilities; no target-name branching; every
new claim ships with its passing test command in the claim inventory.
