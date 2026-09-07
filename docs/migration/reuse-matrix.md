# Reuse Matrix (R1.0)

Decisions per candidate subsystem. Initial verdicts are UNKNOWN; each must be backed by `path:line` before being promoted.

| Existing module | Actual behavior | BOB target | Compatibility | Action | Evidence |
|---|---|---|---|---|---|
| `src/agent/agent.py` | Agent loop driver (offensive cognitive loop). | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/orchestrator/conductor.py` | Orchestrator driver. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/orchestrator/scope.py` | Target scope rules. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/orchestrator/brain/capability_broker.py` | Authorization broker (5-dim). | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/orchestrator/brain/action.py` | Planner (action preconditions/effects). | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/orchestrator/brain/world.py` | WorldModel + evidence chains. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/orchestrator/brain/hypothesis.py` | Hypothesis manager. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/orchestrator/brain/contradiction.py` | Contradiction manager. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/orchestrator/brain/falsification.py` | Falsification engine. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/orchestrator/runtime/` | Runtime subsystem. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/raphael/verifier/core.py` | Safety verifier. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/raphael/verifier/channels.py` | Verifier channels. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/raphael/cortex/planner.py` | Cognitive planner. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/raphael/blackboard/` | Blackboard schemas. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/raphael/eventbus/core.py` | Event bus. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/raphael/executor/` | Executor. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/raphael/evidence/ (note: not a directory in this layout)` | Evidence models. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/mcp-hub/` | MCP hub tool surface. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `src/cli/` | CLI binary. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `scripts/test_imports.py` | Import smoke test. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `tests/test_noop_contract.py` | NoOpWorldModel contract test. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `tests/test_evaluator_isolation.py` | Evaluator isolation test. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
| `tests/test_rbs_v2_repairs.py` | RBS v2 repair tests. | _see roadmap mapping_ | UNKNOWN | UNKNOWN | _path:line required_ |
