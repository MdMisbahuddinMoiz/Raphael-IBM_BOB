# Gap Analysis (R1.0)

What is missing for the IBM BOB MVP target.

- runtime/broker/policy seam under `raphael/` (current repo has analogues inside `src/orchestrator/brain/` for offensive scope).
- Append-only evidence ledger wired into a BOB-facing control loop.
- Finding lifecycle (UNVERIFIED → VERIFIED → REFUTED → SUPERSEDED).
- Verifier gated through Runtime/Broker/Policy.
- Falsifier integrated into the control loop.
- Focused Context builder (deliberately small).
- Causal replanner driven by evidence, not heuristics.
- Output Quality Gate as the COMPLETE authority.
- Authkit hero fixture under `fixtures/authkit/`.
- Independent behavior probe under `probes/`.
- TEST-01..TEST-13 authoritative tests.
- Baseline with verification=false/falsification=false/replanning=false/quality_gate=false.
- Metrics generated from real `runs/*/evidence.jsonl`.
- PROVENANCE.md and submission-checklist.md.
- Python 3.12 toolchain (current machine only has 3.14.4; pip and pytest absent).
