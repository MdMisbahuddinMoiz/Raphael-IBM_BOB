# Roadmap Mapping (R1.0)

Mapping from RAPHAEL IBM BOB Master Roadmap v1.2 target subsystems to physical modules in this repository.
All verdicts begin as UNKNOWN and only become a routing claim when backed by `path:line` evidence.

| Target | Description | Candidate modules | First-pass verdict | Evidence |
|---|---|---|---|---|
| Runtime | Agent-facing execution boundary that mediates every environment action. | _to be filled by reuse matrix_ | UNKNOWN | _to be filled by reuse matrix_ |
| Broker | Authorization gate; consults Policy and decides Permit/Deny for every capability request. | _to be filled by reuse matrix_ | UNKNOWN | _to be filled by reuse matrix_ |
| Policy | Declarative rules; target scope, capability allow-list, rate, impact ceiling. | _to be filled by reuse matrix_ | UNKNOWN | _to be filled by reuse matrix_ |
| Evidence | Append-only, sequenced record of requests, decisions, results, findings. | _to be filled by reuse matrix_ | UNKNOWN | _to be filled by reuse matrix_ |
| Verifier | Independent reproduction/retest of candidate findings; goes through Runtime. | _to be filled by reuse matrix_ | UNKNOWN | _to be filled by reuse matrix_ |
| Falsifier | Actively challenges apparent success; tests behavioral invariants. | _to be filled by reuse matrix_ | UNKNOWN | _to be filled by reuse matrix_ |
| Replanner | Causes Plan B from refuted findings, evidence, and focused context. | _to be filled by reuse matrix_ | UNKNOWN | _to be filled by reuse matrix_ |
| QualityGate | Sole authority for COMPLETE; evaluates mission criterion, evidence, behavior probe, regressions. | _to be filled by reuse matrix_ | UNKNOWN | _to be filled by reuse matrix_ |
| Planner | Generates Plan A from mission + scope. | _to be filled by reuse matrix_ | UNKNOWN | _to be filled by reuse matrix_ |
| Runner | Drives the control loop and persists state. | _to be filled by reuse matrix_ | UNKNOWN | _to be filled by reuse matrix_ |
