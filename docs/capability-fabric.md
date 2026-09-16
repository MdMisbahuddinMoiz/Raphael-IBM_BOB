# Capability Fabric — M16.1 seam (native-only)

A **provider-resolution seam** over RAPHAEL's existing native
capabilities. It answers *"which provider can supply this capability?"*
and can **prepare** the ordinary `ActionRequest` the existing execution
path already consumes.

It is **not** an executor, **not** an orchestrator, and **not** an
authority.

```text
capability
   ↓
Capability Fabric          (raphael_ibm_bob/capability_fabric.py)
   ↓
Native Provider            (provider id: "raphael-native")
   ↓
ActionRequest              (existing contract)
   ↓
Runtime → Broker → Policy → Execution → Evidence
   → Verification → Falsification → Quality Gate
```

## Semantic boundaries (preserved deliberately)

```text
DECLARATION != AUTHORIZATION
PROVIDER RESOLUTION != AUTHORIZATION
CAPABILITY RESOLUTION != EXECUTION
```

Resolution means "which provider can supply this capability?". It does
**not** mean "this capability may execute". Only the existing
Runtime → Broker → Policy boundary authorizes execution, and only the
Quality Gate decides completion.

## Provider contract

`CapabilityProvider` (a `typing.Protocol`) declares:

- `provider_id: str`
- `list_capabilities() -> tuple[Capability, ...]`
- `declaration(capability) -> CapabilityDefinition`
- `build_action_request(capability, target, *, purpose, requester,
  plan_id, finding_id, timeout_seconds) -> ActionRequest`

`NativeCapabilityProvider` wraps the authoritative
`skills.CapabilityRegistry` (no invented definitions) and exposes the
five native capabilities: `read`, `list`, `search`, `write`,
`run_test`.

## Registry contract

`CapabilityFabric` (explicit construction; **no module-level mutable
global**):

- `register(provider)` — duplicate `provider_id` is rejected
  (`DuplicateProviderError`).
- `list_providers()` — deterministic, sorted ids.
- `get_provider(provider_id)` — unknown id raises
  `ProviderNotFoundError`.
- `providers_for(capability)` — deterministic, sorted claimants.
- `resolve(capability, provider_id=None)`:
  - explicit id: that provider must supply the capability
    (`CapabilityNotProvidedError` otherwise);
  - no id: exactly one claimant resolves; **zero or multiple claimants
    raise explicitly** (`CapabilityNotProvidedError` /
    `AmbiguousCapabilityError`) — no silent shadowing.

`default_fabric()` returns a fresh fabric with only the native provider
registered.

## What the Fabric must never do

It imports only the declaration layer (`contracts`, `skills`). It does
not import or call the Broker, Policy, Runtime, Quality Gate,
`execute_capability`, subprocess, socket, or urllib. It never mutates
findings or evidence.

## Model-led adoption (M16.2) — IMPLEMENTED

The live OpenAI-compatible adapter no longer builds ActionRequests via
`registry.propose`. The model proposal now flows:

```text
structured proposal {intent, skill, target, purpose[, content]}
   ↓  (declared skill)
SkillDefinition  ->  declared capability
   ↓
Capability Fabric.resolve(capability)
   ↓
Native Provider (build_action_request)
   ↓
ActionRequest
   ↓
Runtime -> Broker -> Policy -> Execution -> Evidence
   -> Verification/Falsification -> Quality Gate
```

Adoption point: `raphael_ibm_bob/harness/providers/openai_compat.py` →
`validate_proposal(data, registry, *, fabric=None)`. A per-adapter Fabric
instance is used (`OpenAICompatAdapter(config, registry, fabric=None)`);
`None` builds a fresh `default_fabric()`. There is **no silent
fallback**: an unknown skill, an unresolvable capability, or a provider
resolution failure raises `StructuredProposalError` and nothing reaches
the Broker. Provider preparation preserves `target`, `purpose`,
`requester` (`skill:<id>`), `plan_id`, `finding_id`, and the declared
`timeout_seconds`.

The deterministic Runner path (`planner.Planner`) and the scripted test
double (`harness.model.ScriptedModelAdapter`) are unchanged; the
`Replanner` builds its own ActionRequest in the deterministic path and is
**not** routed through the Fabric in M16.2 (documented remaining seam).

## Universal adoption (M16.3) — IMPLEMENTED

INVARIANT: **no real RAPHAEL execution path resolves native capability
implementation without traversing the Capability Fabric.**

```text
Model proposal  -> Skill -> capability ─┐
Planner (Plan A) -> mission capability ─┼─> Capability Fabric.resolve
Replanner (Plan B) -> declared capability ┘        │
                                                   ▼
                                     Native Provider.build_action_request
                                                   ▼
                                              ActionRequest
                                                   ▼
                        Runtime -> Broker -> Policy -> Execution
```

- `planner.Planner.plan_a` resolves the mission's declared capability via
  `default_fabric()` (the M8 rule forbids Planner constructor arguments)
  and prepares the step through the Native Provider.
- `replanner.Replanner.replan` resolves `ReplanStrategy.capability` via an
  injected `fabric` (default `default_fabric()`) and prepares the Plan B
  step through the Native Provider.
- No direct `ActionRequest(...)` construction remains in `planner.py` or
  `replanner.py`; neither imports the Broker/Policy/Runtime/Quality Gate.

Exception (documented, test-only): `harness.model.ScriptedModelAdapter`
is a deterministic **TEST DOUBLE** that returns ActionRequests directly.
It is not a live provider and is not a production capability-resolution
path.

## Provider observability (M16.4) — IMPLEMENTED

The Capability Arsenal (`GET /operations/capabilities`) shows, for each
declared capability, the provider resolved by the Capability Fabric:

```text
CAPABILITY   PROVIDER (resolved via the Fabric)
read         raphael-native
list         raphael-native
...
```

The provider id is read from `default_fabric()` (`list_providers()` /
`providers_for(capability)`), never hardcoded in the template, and
resolution is side-effect-free. Provider identity means **capability
resolution only**:

```text
PROVIDER RESOLUTION != AUTHORIZATION
PROVIDER RESOLUTION != EXECUTION
```

It is not permission, approval, readiness, active execution, or trusted
completion. Where a capability has no single claimant, the UI shows
`UNRESOLVED` / `UNKNOWN / NOT VERIFIED` rather than inventing a provider.
Provider availability is not modelled, so no AVAILABLE/READY/CONNECTED
state is shown. Decepticon/T3MP3ST are not displayed.

## Future providers — DESIGN ONLY

The seam makes future providers *structurally possible*; it does **not**
implement them:

```text
RAPHAEL NATIVE PROVIDER
          \
           → Capability Fabric → ActionRequest → Runtime → Broker → Policy
          /
future Decepticon adapter      (DESIGN ONLY — NOT IMPLEMENTED)
future T3MP3ST adapter         (DESIGN ONLY — NOT IMPLEMENTED)
```

Decepticon and T3MP3ST are **not integrated**, not imported, and not
represented as available providers anywhere.
