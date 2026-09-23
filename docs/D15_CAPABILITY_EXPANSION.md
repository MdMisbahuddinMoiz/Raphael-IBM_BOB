# D15 Capability Expansion: the two-tier model

Status: descriptor milestone. D15 declares five Tier-1 capabilities and
executes none of them. This doc describes what is implemented in
`raphael_ibm_bob/` today. It does not claim D15 is complete, and it does
not claim any Tier-1 capability is production-ready.

Related docs: `docs/D13_CAPABILITY_FABRIC.md` (the fabric D15 builds on),
`docs/D15_D16_HANDOFF.json` (the machine-readable D16 handoff inventory).

## 0. Which "D15" this is

The checkout contains unrelated historical "D15" material under `src/arena`
(legacy research substrate, for example
`src/arena/manifests/D15_VERIFICATION_REPORT.md` and
`src/arena/manifests/D15_T6_LOG_INJECTION_REPAIR_SPEC.json`). That material
belongs to an older offensive-research track. It is not imported by the
governed runtime, it is not shipped in the product package, and it has
nothing to do with this milestone. When this doc says "D15", it means only
the governed capability-expansion milestone in `raphael_ibm_bob/`:
the catalogue module `raphael_ibm_bob/d15_capability_catalogue.py` and its
tests in `tests/test_d15_capability_catalogue.py`.

## 1. The two-tier model

D15 splits capabilities into two tiers with a hard rule between them:
declaration is not execution.

**Tier 1 (descriptor-only).** Five capabilities exist as immutable
`CapabilityDescriptor` records plus an `InertAdapter` binding:
`NETWORK_SSH_SESSION`, `NETWORK_SMB_METADATA`, `NETWORK_TLS_METADATA`,
`NETWORK_DNS_METADATA`, `NETWORK_GENERIC_SERVICE_BANNER`. They are
discoverable through `CapabilityRegistry.discover_for_target` and
composable through `CapabilitySelector.select_and_compose`, but every
execution path fails closed:

* `InertAdapter.execute` raises `AdapterNotBoundError`
  (`raphael_ibm_bob/capability_bootstrap.py`).
* `plan_to_action_requests` raises `ValueError` for any step whose id has
  no `contracts.Capability` enum member, so no `ActionRequest` can even be
  built for a Tier-1 capability
  (`raphael_ibm_bob/capability_selector.py`).
* The Policy allow-list (`raphael_ibm_bob/policy.py`) contains only the
  existing enum members, so even a hand-built request for a Tier-1 id
  would be denied.

**Tier 2 (executable).** The three existing executable network/file
capabilities are unchanged by D15: `C1A_STATIC_FILE_INSPECT`,
`NETWORK_HTTP_REQUEST`, `NETWORK_TELNET_SESSION`. Promoting any Tier-1
capability to Tier 2 requires an enumerated, approved interface change
covering all five touchpoints: the `contracts.Capability` enum, the
Policy allow-list, the Broker dispatch path, the skill/registry
declarations, and the QualityGate evidence expectations. A partial change
(for example, adding the enum member but not the Policy rule) is not a
promotion. It is a defect, and the remaining fail-closed layers keep it
inert until the set is complete.

## 2. Interface-defect statement

D15 holds a "no governance edits" rule, and that rule applies to Tier 1
only. Concretely: declaring the five Tier-1 descriptors touched none of
the governance core. `contracts.py`, `policy.py`, `broker.py`,
`quality_gate.py`, and the evidence ledger are byte-identical in behavior
to before. The catalogue module imports only the declaration layer
(`capability_registry`, plus `capability_bootstrap` for the SSH descriptor
and `InertAdapter`). It does not import the broker, the policy, the
runtime, or any network primitive.

The rule does not extend to Tier 2. Making a Tier-1 capability executable
is, by definition, a governance edit: it changes the enum, the Policy,
the Broker, the skills, and the QualityGate together, under explicit
approval. Anyone who claims a Tier-1 capability became executable "without
governance changes" is describing the interface defect this section
exists to forbid. If the enum changed but Policy did not (or vice versa),
the layers disagree, and the disagreement must resolve to DENY, never to
an ad hoc bypass.

## 3. Canonical capability contract

Every capability, Tier 1 or Tier 2, is described by one immutable
`CapabilityDescriptor`
(`raphael_ibm_bob/capability_registry.py`):

* `capability_id`: the stable string id. For bridged (executable)
  capabilities it equals the `contracts.Capability` enum name (for example
  `"NETWORK_HTTP_REQUEST"`). Tier-1 ids have no enum member, which is
  exactly what keeps them inert.
* `protocol`: the match key for discovery (`discover_for_target` compares
  it against open services in the target facts).
* `description`: human-readable purpose. Description only, never authority.
* `prerequisites`: a frozenset of `PrerequisiteSpec` (`kind`, `predicate`,
  `description`). Must be a frozenset; anything else is rejected at
  registration.
* `authorization_scope`: the scope string the future Policy rule will key
  on (for example `"network_ssh"`). Today it is a reservation, not a rule.
* `evidence_schema`: the versioned schema id the future observation will
  conform to (for example `"smb_metadata_v1"`).
* `execution_adapter`: a dotted-path string naming the future governed
  adapter (for example
  `"raphael_ibm_bob.capability_adapters.ssh"`). A string, not an import:
  nothing is resolved until the Tier-2 change lands.
* `verifier_binding` / `falsifier_binding`: the verifier/falsifier modules
  that will retest future findings. `None` for all five Tier-1
  descriptors. No binding, no verification path, no verified findings.
* `mission_types`: a frozenset naming the mission types the capability may
  be selected for. Must be a frozenset; anything else is rejected.
* `schema_version`: `"1.0"` across the catalogue.

Registration rules (enforced by `CapabilityRegistry.register`): duplicate
ids raise, null adapters are refused (use `InertAdapter` explicitly),
registration happens at system init, never mid-mission.

## 4. Tier-1 descriptor table

Source of truth: `raphael_ibm_bob/d15_capability_catalogue.py` (plus
`ssh_descriptor()` in `raphael_ibm_bob/capability_bootstrap.py`).
`observation_type` needs a note first: Tier-1 capabilities never execute,
so they have produced zero observations. The table gives the reserved
observation family (from `evidence_schema`) rather than observed output.
See section 5 for the family invariant.

| capability_id | protocol | prerequisites (kind: predicate) | mission_types | observation family (reserved, none produced) |
|---|---|---|---|---|
| NETWORK_SSH_SESSION | ssh | service: ssh; authorization: ssh; credential: ssh_valid | flag_capture, service_interaction, credential_access | ssh_session_v1 |
| NETWORK_SMB_METADATA | smb | service: smb; authorization: smb | recon, service_interaction | smb_metadata_v1 |
| NETWORK_TLS_METADATA | tls | service: tls; authorization: tls | recon, service_interaction | tls_metadata_v1 |
| NETWORK_DNS_METADATA | dns | service: dns; authorization: dns | recon, service_interaction | dns_metadata_v1 |
| NETWORK_GENERIC_SERVICE_BANNER | generic-service | service: generic-service; authorization: generic-service | recon, service_interaction | service_banner_v1 |

Additional per-descriptor facts, all verified against the implementation:

* All five use `InertAdapter`, have `verifier_binding=None` and
  `falsifier_binding=None`, and carry `schema_version="1.0"`.
* Only SSH requires a credential (`credential: ssh_valid`, i.e. a
  validated credential reference, not a password). The four metadata
  descriptors require service plus authorization only, which matches their
  intended read-only metadata semantics.
* SSH is the odd one in mission scope: it alone lists `flag_capture` and
  `credential_access`, reflecting a future interactive session rather than
  passive metadata collection.
* `execution_adapter` strings point at
  `raphael_ibm_bob.capability_adapters.<protocol>`, a module path that
  does not exist yet. That is intentional: the string reserves the
  location where the governed adapter will live after the Tier-2 change.

## 5. Frozen invariants

These hold for Tier 1 today and must keep holding through any Tier-2
promotion. D16 work that breaks any of them is wrong.

**Family-specific observation types.** Observation types are per family,
never a single generic blob. The existing code already works this way:
`ObservationBuilder` produces `network_response`, `flag`, and
`credential_candidate` records (`raphael_ibm_bob/observation_model.py`),
and the two executable network capabilities keep separate evidence
schemas (`http_response_v1`, `telnet_session_v1`). Tier 1 reserves one
schema per family (see the table above). A future implementation must not
merge them into one shared type.

**Broker-stamped session identity.** Session identity originates on the
governed execution path (broker-stamped ledger sequences, carried into
observation provenance as `session_id`) and is checked by
`ProvenanceValidator.validate_fresh`, which rejects observations from a
different session or older than the freshness window
(`raphael_ibm_bob/observation_model.py`). Adapters propagate the stamped
identity; the D14 ledger view resolves it from ledger records
(`raphael_ibm_bob/d14_ledger_view.py`).

**Adapters never get the ledger.** The registry module refuses the
dependency by construction: it must not import `broker`, `policy`,
`runtime`, `quality_gate`, `capabilities.execute_capability`, or any
process/network primitive. `MediatedAdapter` receives only an injected
runtime object and builds an ordinary `ActionRequest` through
`runtime.submit`; it never sees the ledger, never consults Policy itself,
and never executes directly. `InertAdapter` receives nothing at all.

**Tri-state prerequisites.** Prerequisite evaluation is three-valued:
available, missing, unknown. The implementation shape is
`PrerequisiteResult` (`satisfied`, `missing`, `evaluated`) in
`raphael_ibm_bob/capability_prerequisites.py`: `satisfied` plus an empty
`missing` list means ready, a nonempty `missing` list names what is
absent, and unknown prerequisite kinds fail closed (`False`, never an
exception that could be misread as permission). There is deliberately no
enum that a caller could switch on to grant access; the only consumer is
selection, and selection proposes steps, it does not authorize them.

**Ranking via hypothesis_id only.** The D14 planner orders candidates
deterministically and breaks identity ties on `hypothesis_id`: candidates
are sorted by hypothesis key, the winner is the minimum, and the decision
id is a hash over the mission, world revision, plan, selection, and
rejections (`raphael_ibm_bob/d14_planner.py`, `_selection_order_key`).
No branch keys off a target name, a capability name, or any ambient
ordering. D15 introduces no new ranking field; the handoff record carries
a null `new_ranking_field` as an explicit reservation for D16.

## 6. Test evidence (what actually ran)

* `tests/test_d15_capability_catalogue.py`: 6 tests, all passing at time
  of writing (run from WSL: `PYTHONPATH=. python3 -m unittest
  tests.test_d15_capability_catalogue`). They cover catalogue membership
  and prerequisite kinds, inert-adapter registration, duplicate
  registration failing closed, per-protocol discovery, planning failing
  closed without an enum binding, and inert execution raising
  `AdapterNotBoundError`.
* That is the full extent of D15-specific test evidence. There are no
  live-network tests for Tier-1 capabilities, and by design there cannot
  be: the capabilities under test refuse to execute.
* Tier-2 executables are covered by their pre-existing suites (D9/D12
  network tests, the D13 fabric tests, the core seam suites). D15 did not
  add to those suites and did not need to, because D15 changed none of
  those code paths.
* `tests/test_d15_executability_matrix.py`: 6 tests, all passing at time
  of writing (run from WSL: `PYTHONPATH=. python3 -m unittest
  tests.test_d15_executability_matrix tests.test_d15_capability_catalogue`
  reports `Ran 12 tests: OK`). The matrix suite is the executable proof
  behind section 8.5: HTTP and Telnet run through injected offline
  mediators and leave governed ledger evidence, while SSH, SMB, TLS, DNS,
  and Banner are shown descriptor-only (no enum binding, `InertAdapter`,
  plan refusal, Policy DENY).

## 7. Honest limitations

1. **Nothing in Tier 1 works yet, on purpose.** The five descriptors can
   be discovered, selected into plans, and then they refuse. Any demo that
   shows a Tier-1 capability "running" is either showing the refusal path
   or showing something outside the governed boundary.
2. **No verification path exists for Tier 1.** With both bindings `None`,
   there is no retest and no falsification for future Tier-1 findings
   until D16 defines them. The descriptors cannot produce a verified
   finding in their current form.
3. **Metadata semantics are aspirational.** The four metadata descriptors
   intend read-only collection (banner, TLS parameters, DNS records, SMB
   share metadata), but no byte-level contract exists yet: no method
   allow-list, no body cap, no truncation rule, nothing comparable to the
   HTTP runtime's GET/HEAD-only discipline. Writing those contracts is
   D16 work, and each one is a governance decision, not a default.
4. **SSH is the highest-risk promotion.** It is the only Tier-1
   capability requiring a credential and targeting interactive sessions
   and flag capture. Its Tier-2 design needs the Telnet-runtime treatment
   at minimum (bounded session, command allow-list, password never
   persisted, refusal never success) before anything else.
5. **Discovery depends on fact quality.** `discover_for_target` matches on
   protocol strings from target facts. A mislabeled service (or an
   attacker-influenced banner parsed as a protocol) selects the wrong
   descriptor family. Selection is still only a proposal, and Policy still
   gates execution, but D16 should treat protocol labels as untrusted
   input.
6. **The legacy tree is still in the checkout.** `src/`, `arena/`, and
   related research residue remain on disk and are excluded from the
   shipped package only by the packaging include
  (`pyproject.toml` builds from `raphael_ibm_bob` alone). D15 does not
   change that posture. Do not confuse the legacy `src/arena` "D15"
   files with this milestone (see section 0).

## 8. Generic Executable Capability Boundary (D15 Barrier B)

Read this section's status line first: Barrier B is a target design,
not landed code. Nothing below claims a new executable exists. Every
"today" statement cites the as-built code, and every "target" statement
describes the bridge D16 would need to land. The executability matrix
in 8.5 is the one part backed by passing tests right now.

Barrier B generalizes the executable boundary so that adding an
EXECUTABLE capability becomes a registry plus adapter addition instead
of a new governance branch. The target path is:

```text
CapabilityDescriptor -> CapabilityRegistry -> CapabilityAdapter
  -> ActionRequest -> Policy -> Broker -> ExecutionAdapter
  -> Observation -> Evidence/Verification -> QualityGate
```

The hard constraint: D12.2 security semantics stay exactly as they are.
Policy authorization, Broker mediation, scope, evidence provenance,
verification and falsification, QualityGate authority, and the finding
lifecycle do not change. Only the mechanism turns data-driven: lookups
keyed off descriptor fields replace branches keyed off capability names.

### 8.1 The interface defect and its fix

Today, promoting a capability to executable means editing five places
that each branch on the capability name. `policy.py` holds an explicit
enum allow-list plus per-capability consult paths (`_consult_network`,
`_consult_telnet`). `broker.py` dispatches on identity checks
(`_execute_network`, `_execute_telnet`, plus the C1A path). The
QualityGate scope check names the two network capabilities explicitly.
`skills.py` declares one capability definition and skill per executable,
and `plan_to_action_requests` demands a `contracts.Capability` enum
member before it builds any request
(`raphael_ibm_bob/capability_selector.py`).

That shape is the defect. Each name branch is a spot where a partial
change leaves the layers disagreeing: enum added but Policy silent, or
Policy allowing what the Broker cannot dispatch. Section 2 already says
the disagreement must resolve to DENY. Barrier B removes the
disagreement at its source. Under the bridge, none of these modules
names a capability. Policy reads authorization metadata off the
descriptor, the Broker dispatches to the bound adapter, and the
QualityGate evaluates descriptor-declared evidence expectations through
its existing A to G conditions. A promotion then adds data (descriptor,
adapter, policy metadata), and there is no branch left to forget.

### 8.2 The registry-backed generic bridge, hop by hop

Each hop names the as-built anchor and what the bridge changes about it.

| hop | as-built today | Barrier B target |
|---|---|---|
| `CapabilityDescriptor` | Immutable record in `capability_registry.py`; Tier-1 ids have no enum member, which keeps them inert | Same record, plus machine-readable policy metadata (scope grammar, method or command allow-list, timeout bounds, credential need) |
| `CapabilityRegistry` | Declaration index; `register` plus `bind_adapter`, duplicates rejected, init time only | Same authority, plus the single source Policy and Broker read instead of their own name lists |
| `CapabilityAdapter` | `MediatedAdapter` in `capability_bootstrap.py`, built around one `Capability` enum member; `bind_governed_adapters` skips ids with no enum binding | Generic adapter built around a descriptor: same discipline (build an ordinary `ActionRequest`, call `runtime.submit`, never touch Policy, ledger, or network directly), no enum member required |
| `ActionRequest` | `plan_to_action_requests` raises `ValueError` without an enum binding ("no governed Capability enum binding") and refuses unregistered ids | Same fail-closed constructor, but the binding check is registry membership plus a bound governed adapter, not enum membership |
| `Policy` | Allow-list plus per-capability consult branches | One consult path driven by descriptor policy metadata; unknown ids still denied with `capability-not-allowed` |
| `Broker` | Per-capability execute paths behind identity checks | One execute path: hand the ALLOWed request to the bound `ExecutionAdapter`, persist the same request, decision, result, and evidence chain |
| `ExecutionAdapter` | `network_runtime` / `telnet_runtime` mediators, the only I/O boundary for their capability | Same role per capability: bounded I/O, then a normalized observation. Today's shape for that output is `d15_observation.py` (bounded families, no raw protocol bytes, hashes not banners) |
| `Observation` | `ObservationBuilder` records with broker-stamped `session_id` provenance, checked by `ProvenanceValidator.validate_fresh` | Unchanged. New families add builders in the same style; per-family types stay separate (see section 5) |
| `Evidence/Verification` | Ledger chain plus verifier/falsifier modules; all Tier-1 bindings are `None`, so no Tier-1 verification path exists | Promotion fills in real `verifier_binding` / `falsifier_binding` values; findings flow through the existing lifecycle or they do not count |
| `QualityGate` | Seven conditions A to G, sole COMPLETE authority | Unchanged conditions, fed by descriptor-declared expectations instead of per-capability wiring |

### 8.3 Data-driven Policy, Broker, and QualityGate (semantics unchanged)

"Data-driven" here has a narrow meaning. It changes where each module
gets its answers (descriptor fields, not name branches). It must not
change what the answers enforce. Preserved from D12.2, point by point:

* **Policy authorization.** ALLOW stays an explicit, deterministic
  decision with string reasons tests can assert. DENY performs nothing.
* **Broker mediation.** The Broker stays the sole invoker. Every action
  keeps the canonical chain: request, decision, policy receipt, result,
  execution receipt.
* **Scope.** Exact host, port, and protocol matching against the
  mission-bound TargetProfile, plus method or command allow-lists and
  positive timeouts. Descriptor metadata declares these per capability;
  the matching strictness does not loosen.
* **Evidence provenance.** Producer-tagged records, UNTRUSTED marking on
  provider and network output, digest ids, append-only ledger.
* **Verification and falsification.** Independent retest and
  counter-example search through the existing Verifier and Falsifier.
  No binding, no verified findings.
* **QualityGate authority.** Only `BOBQualityGate.evaluate()` emits
  COMPLETE, against ledger-backed conditions A to G.
* **Finding lifecycle.** `UNVERIFIED` to `REFUTED` to `SUPERSEDED` or
  `VERIFIED`, with replanning evidence required after refutation.

Three fail-closed rules carry over with the same force:

1. **Unregistered means refusal.** A plan step naming an unknown id
   fails at request construction, and a hand-built request dies in
   Policy with `capability-not-allowed`. The bridge adds no path around
   either check.
2. **Descriptor-only means fail closed.** An `InertAdapter` binding
   raises `AdapterNotBoundError` on execute. Declared is not executable,
   before and after Barrier B.
3. **No fallback descriptor means no arbitrary runtime.** There is no
   generic "just run it" adapter. A capability with no descriptor, no
   binding, or no policy metadata does not execute, full stop.

### 8.4 How to add a new EXECUTABLE capability (no enum, broker, or gate branch)

1. **Write the descriptor.** Fill every field from section 3, including
   real `authorization_scope`, `evidence_schema`, `execution_adapter`
   path, `verifier_binding`, `falsifier_binding`, and `mission_types`.
   `None` bindings mark a descriptor-only entry, never an executable.
2. **Implement the governed adapter.** Bounded I/O only, through a
   mediator shaped like the existing network and Telnet mediators.
   Output is a normalized observation built the `d15_observation.py`
   way (bounded fields, hashes instead of raw bytes, no credentials).
   The adapter receives an injected runtime, never the ledger, and it
   never consults Policy itself.
3. **Declare the policy metadata.** Scope grammar, allowed methods or
   commands, timeout bounds, credential requirements. This metadata is
   a governance decision per capability, with the HTTP GET/HEAD-only
   discipline as the bar to meet, not a default to inherit.
4. **Register at init and bind the adapter.** Registration stays a
   system-init step, never mid-mission. Duplicate ids stay violations.
5. **Prove it with tests.** Extend the executability matrix
   (`tests/test_d15_executability_matrix.py`): the new row must show
   governed execution with offline mediators and ledger evidence, plus
   the fail-closed proofs (unregistered refusal, inert refusal, DENY
   with no side effect).
6. **Ship no governance branch.** If the change adds a capability name
   check to Policy, Broker, QualityGate, or the selector, it is not
   Barrier B. It is the old five-touchpoint promotion wearing new docs.

Promotion checklist before any executable claim: descriptor registered,
governed adapter bound, policy metadata enforced and tested, normalized
observations produced, verifier and falsifier bindings live, matrix row
green, gate conditions A to G evaluated against real ledger evidence.

### 8.5 Descriptor-only versus executable: the executability matrix

Source of truth: `tests/test_d15_executability_matrix.py` (6 tests,
passing; `Ran 12 tests: OK` together with the catalogue suite). All
target states and provider outcomes in that suite are synthetic. HTTP
and Telnet run through injected offline mediators. Everything else is a
declaration with no enum binding and no governed adapter.

| capability | descriptor | adapter today | enum binding | policy | broker path | verdict |
|---|---|---|---|---|---|---|
| NETWORK_HTTP_REQUEST | yes | governed runtime path (`network_runtime` via Broker) | yes | `_consult_network` ALLOW on authorized target | `_execute_network`, `producer="network"` evidence | executable |
| NETWORK_TELNET_SESSION | yes | governed runtime path (`telnet_runtime` via Broker) | yes | `_consult_telnet` ALLOW on authorized target plus command allow-list | `_execute_telnet`, `producer="telnet"` evidence | executable |
| NETWORK_SSH_SESSION | yes | `InertAdapter` | none | DENY `capability-not-allowed` | none; `plan_to_action_requests` raises `ValueError`, `execute` raises `AdapterNotBoundError` | descriptor-only |
| NETWORK_SMB_METADATA | yes | `InertAdapter` | none | DENY `capability-not-allowed` | none; same double refusal | descriptor-only |
| NETWORK_TLS_METADATA | yes | `InertAdapter` | none | DENY `capability-not-allowed` | none; same double refusal | descriptor-only |
| NETWORK_DNS_METADATA | yes | `InertAdapter` | none | DENY `capability-not-allowed` | none; same double refusal | descriptor-only |
| NETWORK_GENERIC_SERVICE_BANNER | yes | `InertAdapter` | none | DENY `capability-not-allowed` | none; same double refusal | descriptor-only |

Two notes on the table. First, "descriptor-only" is proven, not
assumed: the matrix suite asserts each refusal at three layers (no enum
member, `ValueError` at planning, `AdapterNotBoundError` at the
adapter, DENY at Policy). Second, the D15 observation builders
(`d15_observation.py`: SSH, SMB, TLS, DNS, banner, artifact
configuration) define output shapes only. Shapes are not execution, and
the table does not count them as such.

### 8.6 Honest limitations of the bridge

1. **The bridge itself is not code yet.** Policy, Broker, and
   QualityGate still branch on capability names. Until the generic
   consult, dispatch, and expectation paths land with tests, sections
   8.1 through 8.4 describe intent, and the five-touchpoint rule in
   section 2 still governs promotions.
2. **The matrix proves refusal, not readiness.** Five of seven rows show
   the system saying no correctly. Saying no is necessary and not
   sufficient: byte-level contracts (method allow-lists, body caps,
   truncation rules) exist only for HTTP, and each new family needs its
   own before promotion.
3. **Observation builders have no live path.** The `d15_observation.py`
   families are unit-shaped but never fed by execution, since nothing
   descriptor-only executes. Their first live test must come with the
   first promotion, through the governed path, not around it.
4. **SSH stays the highest-risk promotion.** Credential handling,
   interactive session bounds, and flag-capture semantics need the
   Telnet-runtime treatment at minimum (bounded session, command
   allow-list, secrets never persisted, refusal never success).
5. **Discovery still trusts protocol labels.** `discover_for_target`
   matches descriptor protocols against target facts. A mislabeled
   service proposes the wrong family. Selection is only a proposal and
   Policy still gates, but the bridge should treat protocol strings as
   untrusted input when it lands.
