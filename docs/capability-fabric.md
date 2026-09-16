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
