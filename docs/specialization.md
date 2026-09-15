# M14 — Decepticon-Inspired Capability Specialization

A **Decepticon-inspired specialization model implemented inside
RAPHAEL**. It adds declared roles, richer skill/capability
declarations, role-aware discovery, task decomposition, and evidence
contracts — all as **metadata**. It does not import, vendor, or depend
on Decepticon, and it adds no offensive capability, execution path,
subprocess, or network surface.

## The invariant

A role or skill is a **declaration**, never **authority**. Every
executable action still travels:

```text
Model / Specialist → Skill Registry → ActionRequest
  → Runtime → Broker → Policy → Execution → Evidence
  → Verification → Falsification → Replan → QualityGate
```

Role metadata cannot authorize, widen scope, register a capability,
write evidence, or decide completion.

## 1. Role model

`raphael_ibm_bob.specialization.Role` (frozen) — `id`, `name`,
`purpose`, `capabilities` (the capabilities the role is *meant* to
use). A deliberately small vocabulary of six safe roles
(`DEFAULT_ROLES`):

| Role | Purpose | Capabilities |
|---|---|---|
| `investigator` | locate relevant implementation and evidence | READ, LIST, SEARCH |
| `test_analyst` | execute authorized verification tests | RUN_TEST |
| `remediation_planner` | propose a corrective change | WRITE |
| `verifier` | establish whether the correction satisfies the proof obligation | READ, RUN_TEST |
| `falsifier` | challenge apparent success with negative controls | READ, SEARCH |
| `evidence_analyst` | interpret persisted evidence and reconstruct state | READ, LIST |

`RoleRegistry` indexes roles; `default_roles()` returns the six.
Roles describe *responsibility*, not permission.

## 2. Skill model

`SkillDefinition` (frozen, extended) adds: `role` (optional),
`evidence_produced`, `evidence_consumed`, `prerequisites`. Existing
fields (`id`, `name`, `version`, `description`, `capability`,
`target_schema`, `purpose_template`, `success_markers`, `challenge`)
are unchanged, so existing skills/tests remain valid.

Validation on registration: the role must be known; the skill's
capability must be one the role declares; prerequisites must already
be registered. A skill still cannot execute itself and still cannot
bypass the registry, ActionRequest validation, Broker, or Policy.

## 3. Capability declarations

`CapabilityDefinition` (frozen, extended) adds `evidence_produced` /
`evidence_consumed` describing the capability's evidence shape. The
five authoritative capabilities are unchanged in behavior, e.g.
`RUN_TEST` produces `test-execution`, `WRITE` produces `remediation`
and consumes `inspection`.

## 4. Task decomposition

`specialization.decompose_mission(mission)` deterministically builds a
`TaskPlan` — a descriptive tree, not a planner:

```text
<mission>            (role: evidence_analyst)
  ├── investigate    (investigator)
  ├── reproduce      (test_analyst)
  ├── remediate      (remediation_planner)
  ├── verify         (verifier)
  └── validate       (evidence_analyst)
```

`TaskState` = `pending | active | completed | refuted | blocked |
cancelled`, with a small validated transition table. States are
orchestration metadata: they are persisted to `tasks.json` in the run
directory and are distinct from the run lifecycle. The actual
Planner/Replanner remain authoritative for planning decisions; the
decomposition layer sits *above* execution.

## 5. Evidence contracts

Each skill declares what evidence it produces/consumes. `evidence_contract(skill)`
returns that declaration. These are **contracts, not permissions**:
there is one authoritative evidence ledger (`evidence.jsonl`), unchanged,
and no second evidence database. Declarations never write evidence.

## 6. Role-aware context

`ModelContext` gains `available_roles` and `active_task` (compact).
The live provider's skill catalog now includes each skill's `role` and
evidence contract. Context is bounded and deterministic — the whole
registry is never dumped, and the model can *discover* but not
*grant* capabilities.

## 7. Governance boundaries

- `CapabilityRegistry` remains the only catalog authority (roles +
  skills + capabilities).
- Discovery is read-only; a proposal outside the registry is rejected.
- A role-selected skill still yields an ordinary `ActionRequest`
  submitted through the Broker/Policy boundary.
- DENY still prevents execution; invalid proposals never reach the
  Broker.
- A task marked COMPLETED cannot make the run COMPLETE; the
  Falsifier and the QualityGate remain authoritative.

## 8. Decepticon-inspired concepts adapted

Concepts only, no code: the separation of a **role registry** and a
**skill registry** from execution (`packages/decepticon-core/.../registry/`),
and per-skill **declared contracts** (`.../registry/skills.py`).
RAPHAEL re-expresses these as its own dataclasses over its own
governance chain.

## 9. Decepticon capabilities explicitly rejected

Not added, in any form: reconnaissance/scanners, exploit chains,
payload generation, C2, phishing, credential attacks, AD/BloodHound
attack infrastructure, exfiltration, offensive persistence, an
offensive specialist fleet, attack-graph execution, dual-network
attack infrastructure, browser/cloud/RE attack tooling. No Decepticon
source is vendored and Decepticon is not a dependency
(`pyproject.toml`/`requirements.txt` clean; no imports).

## 10. Live validation result

Live model-led harness run (DeepSeek V4.1 Flash via OpenCode Go),
through the M13 Harness API: **run `20260915T164725_8c09a5`**,
terminal `done`, `Gate: COMPLETE` (7/7). Selected roles/skills flowed
through the governed path:

- `investigator` → `read-file` (session.py, test_auth.py, store.py)
- `test_analyst` → `run-test` (test_auth.py, test_login.py)
- `remediation_planner` → `write-file` (session.py)

Every action was BROKER/POLICY-mediated (all ALLOW), the finding went
unverified→verified, the Falsifier challenged it, and the QualityGate
returned COMPLETE. `tasks.json` recorded `investigate`/`reproduce`
completed and `remediate` active. This is one scenario; it does not
establish generalized autonomous specialization.

## 11. Limitations

- Task decomposition is a fixed generic pipeline (no dynamic planning);
  the Planner/Replanner remain the planning authorities.
- Roles are a small fixed vocabulary; no custom role registration from
  the model (by design).
- Task-state advancement is a simple capability→step mapping, not a
  full workflow engine.
- One live run; not a statistical result.
