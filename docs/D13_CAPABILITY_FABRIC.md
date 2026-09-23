# D13 Capability Fabric (Implementation in Review)

Status: implementation in review, pending integration validation. This doc describes only what is implemented in `raphael_ibm_bob/` today. It does not claim D13 is complete.

D13 adds a governed capability fabric around the frozen governance core. Policy, Broker, EvidenceLedger, and QualityGate are unchanged. Nothing here grants authority. Every execution still travels the existing path: ActionRequest, Runtime, Broker, Policy, execution, evidence, verification, falsification, QualityGate.

Source modules (all under `raphael_ibm_bob/`):

* `capability_registry.py`
* `capability_selector.py`
* `capability_prerequisites.py`
* `observation_model.py`
* `target_service_model.py`
* `credential_provenance.py`
* `capability_bootstrap.py`

## 1. Capability, CapabilityDescriptor, CapabilityRegistry

A Capability is a declared unit of governed behavior (for example `NETWORK_HTTP_REQUEST`). Declaration is not authorization, and resolution is not execution.

`CapabilityDescriptor` is an immutable dataclass with these fields:

* `capability_id` (equals the `contracts.Capability` enum name for bridged capabilities, for example `"NETWORK_HTTP_REQUEST"`)
* `protocol` (for example `"http"`, `"telnet"`, `"ssh"`)
* `description`
* `prerequisites` (a frozenset of `PrerequisiteSpec`)
* `authorization_scope`
* `evidence_schema`
* `execution_adapter`
* `verifier_binding`
* `falsifier_binding`
* `mission_types` (a frozenset, for example `{"recon", "web_enum", "service_interaction", "flag_capture"}`)
* `schema_version` (default `"1.0"`)

`PrerequisiteSpec` has `kind`, `predicate`, and `description`. Kind is one of `service`, `credential`, `authorization`, `artifact`, `platform`, or `observation`. `CapabilityDescriptor.prerequisite_specs()` returns the specs sorted by `(kind, predicate)`.

`CapabilityRegistry` is the sole index for registration and discovery. Its API is `register(descriptor, adapter)`, `bind_adapter(capability_id, adapter)`, `get(capability_id)`, `has(capability_id)`, `get_adapter(capability_id)`, `discover_for_target(target_facts)`, and `all_capabilities()`. Registration rejects duplicates, requires frozenset prerequisites and mission types, and requires a non null adapter. Discovery matches `descriptor.protocol` against open services in the facts dict. No branch keys off a target name.

Supporting types in the same module: `CapabilityState` (`DISCOVERED`, `AUTHORIZED`, `READY`, `EXECUTING`, `COMPLETE`, `FAILED`, `REFUSED`), `ExecutionAdapter` (a Protocol with `execute(target_facts, credentials, mission_params)`), and `AdapterNotBoundError`. `get_adapter` returns the bound adapter object but never calls `execute` itself.

## 2. TargetFacts, ServiceRecord, TargetServiceModel, AuthorizationScope

Downstream code consumes `TargetFacts`, never raw scan output.

`ServiceRecord` is a frozen fact with `host`, `port`, `protocol`, `version`, `state` (`open`, `filtered`, or `closed`), `banner`, `discovered_at`, and `source` (`nmap`, `manual`, or `prior_observation`). `key()` returns `(host, port, protocol.lower())` for dedup.

`AuthorizationScope` mirrors operator declared scope for preselection only. Fields are `target_host`, `authorized_protocols` (frozenset), `authorized_ports` (frozenset), `engagement_id`, and `scope_document_ref` (a reference to the signed authorization, never inline content). It does not grant anything.

`TargetFacts` holds `target_id`, `host`, `services` (list of `ServiceRecord`), `authorization` (optional `AuthorizationScope`), `platform`, `observations` (list of dicts), `credential_refs`, and `mission_id`. Methods are `to_facts()`, `add_service(service)`, `get_service(protocol)`, and `is_authorized_for(protocol, port)`. `get_service` returns only services with `state == "open"`. `is_authorized_for` is a preselection helper. Policy against the `TargetProfile` stays authoritative.

`TargetServiceModel` builds facts through `from_nmap(nmap_output, target_host, authorization)`, `from_manual(host, port, protocol, authorization)`, and `from_target_profile(profile, observations)`. `from_nmap` parses lines matching `_NMAP_LINE` and ingests only `open` rows. `from_target_profile` expands the profile's allowed protocols into one `ServiceRecord` per protocol, pairing each with its canonical port from `_CANONICAL_PORTS` when permitted (http 80, https 443, telnet 23, ssh 22, smb 445, ftp 21, rdp 3389, mysql 3306, postgres 5432), else the first authorized port. That pairing uses protocol metadata, not target identity.

There is no `if target == X` anywhere in this path. Facts drive everything.

## 3. ObservationRecord, ObservationBuilder, ProvenanceValidator

Every capability output becomes a normalized `ObservationRecord`. Fields are `observation_id`, `capability_id`, `observation_type`, `target_host`, `timestamp`, `content_hash`, `target_port`, `raw_output_ref`, and `provenance` (dict). `to_evidence_dict()` serializes the record for the ledger.

`ObservationBuilder` constructs records without side effects:

* `from_capability_output(capability_id, output, target_host, target_port, observation_type, provenance)` hashes output with SHA-256 into `content_hash`.
* `from_flag_capture(capability_id, flag_content, target_host, target_port, command, session_id)` sets `observation_type="flag"` with provenance `command`, `session_id`, and `extraction="verified_command_output"`.
* `from_credential_discovery(capability_id, credential_type, target_host, fingerprint, provenance)` sets `observation_type="credential_candidate"`.

An observation is evidence about a target. It can't authorize a transition by itself.

`ProvenanceValidator` checks binding to the exact session and command that produced the output:

* `validate_fresh(observation, current_session_id, max_age_seconds=300.0)` returns `(False, ...)` on session mismatch or stale timestamp, else `(True, "fresh")`.
* `validate_command_binding(observation, expected_command)` compares `provenance["command"]` against the expected command.

## 4. PrerequisiteEngine, PrerequisiteResult

`PrerequisiteEngine` answers "given these `TargetFacts`, can this capability run" with no I/O and no authority. Entry points are `evaluate(descriptor, facts, credential_refs)` and `batch_evaluate(descriptors, facts, credential_refs)`.

`PrerequisiteResult` is a dataclass with `capability_id`, `satisfied` (bool), `missing` (list of `"kind: predicate, description"` strings), and `evaluated` (dict from predicate to bool). The implementation does not define a separate `SATISFIED`, `MISSING`, `BLOCKED`, or `UNKNOWN` enum. Callers should read `satisfied` plus the `missing` list: empty means ready, nonempty names what is absent. Unknown prerequisite kinds fail closed by returning `False`.

Predicate grammar by kind:

* `service`: `"protocol"` or `"protocol:port"` (port must match `facts.get_service(protocol).port`).
* `authorization`: `"protocol"`, checked against `facts.authorization.authorized_protocols` (case insensitive). Empty authorization fails closed.
* `credential`: `"credential_type_or_token"`, matched as substring against each ref's `"credential_type credential_id"` token.
* `platform`: `"linux"`, `"windows"`, or `"any"`.
* `observation`: `"observation_type"`, matched against `facts.observations[].type`.
* `artifact`: `"artifact_type"`, matched against `facts.observations[].artifact_type`.

## 5. CapabilitySelector, ExecutionPlan, plan_to_action_requests

`CapabilitySelector` selects from the registry using facts only. Constructor takes optional `registry` (default `get_registry()`) and `prerequisite_engine` (default `PrerequisiteEngine()`). There is no `SelectionDecision` type in the implementation. Selection returns an `ExecutionPlan` directly.

`select_and_compose(mission_type, mission_params, facts, credential_refs)` works in four steps. First it calls `registry.discover_for_target(facts.to_facts())`. Then it keeps descriptors whose `mission_types` contain `mission_type`. Next it runs `batch_evaluate` and splits results into ready and pending. Finally it adds one step per ready descriptor and, for pending ones, tries `_add_prerequisite_steps` (credential gathering via another registered capability when available). `replan(existing_plan, facts, new_observations, credential_refs)` folds `service_discovery` observations into facts via `ServiceRecord(..., source="prior_observation")` and recomposes.

`ExecutionPlan` holds `plan_id`, `mission_id`, `target_id`, `mission_type`, and `steps` (list of `PlanStep`). `add_step(capability_id, params, depends_on, purpose)` appends a `step_N` entry. `ordered_steps()` returns a deterministic topological order and raises `ValueError` on a dependency cycle. `_derive_plan_id` hashes `(mission_id, target_id, mission_type, capability_ids)` into `DP-<12 hex>` so identical inputs give identical ids. `PlanStep` fields are `step_id`, `capability_id`, `params`, `depends_on`, and `purpose`. A plan is a proposal of steps, not a grant.

`plan_to_action_requests(plan, fabric=None, requester="selector")` is the governed bridge. For each ordered step it looks up `Capability[step.capability_id]`, requires `step.params["target"]`, resolves the provider through the existing `capability_fabric` (`default_fabric().resolve(capability)`), and calls `provider.build_action_request(capability, target, purpose, requester, plan_id)`. Capabilities with no governed enum binding (for example `NETWORK_SSH_SESSION` before SSH exists) raise `ValueError` and fail closed. Requests carry no authority and must still be submitted to Runtime, Broker, and Policy.

## 6. CredentialReference, CredentialVault

Credentials are reference and provenance only. Plaintext never reaches the ledger, logs, or serialized evidence.

`CredentialReference` holds `credential_id`, `credential_type`, `target_host`, `provenance` (a `CredentialProvenance`), `state` (a `CredentialState`), `authorized_for_hosts`, `authorized_for_protocols`, `validated_at`, `discovered_at`, and `fingerprint` (SHA-256 of the secret, used as a correlation handle, not proof of possession). `to_evidence_dict()` serializes everything except plaintext.

`CredentialState` values are `DISCOVERED`, `CANDIDATE`, `VALIDATED`, `AUTHORIZED`, and `REVOKED`. `CredentialProvenance` values are `DEFAULT_CREDENTIAL` (`"default"`), `BRUTE_FORCED`, `OBSERVED`, `EXTRACTED`, `PROVIDED`, and `DERIVED`.

`CredentialVault` is process local. API: `store(credential_type, secret, target_host, provenance)` (rejects empty secrets, suggests `"<blank>"` placeholder), `retrieve(credential_id)`, `get_reference(credential_id)`, `mark_validated(credential_id, target_host, protocol)`, `authorize(credential_id, target_host, protocol)`, `is_authorized_for(credential_id, target_host, protocol)`, `revoke(credential_id)`, `wipe()`, and `references_for_target(target_host)`. `is_authorized_for` requires `VALIDATED` or `AUTHORIZED` state plus exact host and protocol membership. `wipe()` drops references as lifecycle hygiene. It can't overwrite allocator memory, so callers treat it accordingly.

## 7. Governed flow

The implemented flow keeps selection outside the trust boundary:

1. Build `TargetFacts` from nmap, manual input, or `TargetProfile`.
2. Derive observations as `ObservationRecord` entries bound to session and command.
3. Call `CapabilityRegistry.discover_for_target` to list applicable capabilities.
4. Call `CapabilitySelector.select_and_compose` to build an `ExecutionPlan`.
5. Convert steps with `plan_to_action_requests` into ordinary `ActionRequest` objects.
6. Submit each request to Runtime, then Broker, then Policy (the existing single path).
7. Execute only on ALLOW through the already implemented capability handler (`MediatedAdapter.execute` builds the request and calls `runtime.submit`).
8. Record evidence, then run verification and falsification, then let QualityGate decide.

D13 does not bypass Policy, Broker, evidence, or QualityGate. `InertAdapter.execute` raises `AdapterNotBoundError` by design. Declared but unbound capabilities (see `NETWORK_SSH_SESSION`) are discoverable yet not executable.

## 8. Target agnostic example (HTTP vs Telnet vs both)

Selection keys off observed services, never target names. Suppose `TargetFacts` for host `10.0.0.9` contains one open service.

Case A, HTTP only: services are `[{host, port 80, protocol "http", state "open"}]`. Discovery returns the `NETWORK_HTTP_REQUEST` descriptor (`protocol="http"`). `select_and_compose("web_enum", ...)` checks `service: http` and `authorization: http`, then `_derive_params` sets `target` to `"http://10.0.0.9:80<path>"`. Telnet never appears because no open `telnet` service exists.

Case B, Telnet only: services are `[{host, port 23, protocol "telnet", state "open"}]`. Discovery returns `NETWORK_TELNET_SESSION` (`protocol="telnet"`). Its prerequisites include `service: telnet`, `authorization: telnet`, and `credential: telnet`. Without a matching credential ref the result lands in pending with `missing` naming the credential, and the selector looks for a registered credential gathering capability before proposing the session step. `_derive_params` would set `target` to `"telnet://10.0.0.9:23"`.

Case C, both: services list both records above. Discovery returns both descriptors, prerequisites are evaluated independently, and the plan contains an HTTP step plus a Telnet step (or its credential gathering prefix) with no special casing. Adding SSH later means registering `ssh_descriptor()` via `register_ssh()`; it becomes discoverable on `protocol="ssh"` facts while still failing closed at `plan_to_action_requests` until a governed enum binding and adapter exist.

## 9. Bootstrap wiring

`capability_bootstrap.py` declares the catalog and the two adapter shapes:

* `InertAdapter`: declaration only, `execute` raises `AdapterNotBoundError`.
* `MediatedAdapter(capability, runtime, mission)`: `execute` requires `mission_params["target"]`, builds an `ActionRequest(sequence=0, requester="adapter:<value>", capability, target, purpose)`, calls `runtime.submit(request, mission)`, and on non allow or missing execution returns a `capability_decision` dict with `executed=False`. On allow it normalizes output through `ObservationBuilder.from_capability_output` with provenance `request_seq` and `decision`.
* `network_descriptors()` returns the HTTP descriptor (`NETWORK_HTTP_REQUEST`, scope `network_http`, schema `http_response_v1`) and the Telnet descriptor (`NETWORK_TELNET_SESSION`, scope `network_telnet`, schema `telnet_session_v1`).
* `register_default(registry)` registers both with `InertAdapter` (idempotent, skips existing ids).
* `register_ssh(registry)` registers `ssh_descriptor()` the same way.
* `bind_governed_adapters(registry, runtime, mission, capability_ids)` binds `MediatedAdapter` per id, skipping ids with no `contracts.Capability` enum member.

## 10. Non goals and review status

D13 is implementation in review, pending integration validation. It doesn't change the frozen governance core, doesn't add execution paths around Broker or Policy, and doesn't branch on target names. Open work sits in integration validation (selector to runtime wiring, end to end evidence checks), not in this doc's scope.
