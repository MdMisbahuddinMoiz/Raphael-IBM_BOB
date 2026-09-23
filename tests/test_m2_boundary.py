"""tests/test_m2_boundary.py — M2 controlled-execution boundary tests.

Stdlib-only. Each test exercises a REAL code path through:

    ActionRequest
       ↓
    BOBRuntime.submit
       ↓
    BOBBroker.submit
       ↓
    BOBPolicy.consult
       ↓
    execute_capability (only on ALLOW)
       ↓
    ExecutionResult

NO mocks. NO fakes. NO suppressing the operation after the fact.

Test numbers correspond to the brief's §9 minimum proof set, plus the
§10 boundary test.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Iterator

from raphael_ibm_bob import (
    ActionRequest,
    Capability,
    Decision,
    ExecutionResult,
    Finding,
    FindingState,
    Mission,
    PolicyDecision,
    fresh_id,
)
from raphael_ibm_bob.broker import BOBBroker, BrokerResult
from raphael_ibm_bob.capabilities import execute_capability, CAPABILITY_DISPATCH
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.runtime import BOBRuntime, RuntimeResult
from raphael_ibm_bob.workspace import Workspace


def _workspace_path() -> Path:
    """Create a fresh workspace root with a known file structure."""
    import shutil
    tmp = tempfile.mkdtemp(prefix="raphael_ibm_bob_m2_")
    root = Path(tmp)
    (root / "src").mkdir()
    (root / "src" / "hello.txt").write_text("hello-world\n", encoding="utf-8")
    (root / "src" / "authkit").mkdir()
    (root / "src" / "authkit" / "store.py").write_text("STORE = {}\n", encoding="utf-8")
    (root / "src" / "authkit" / "session.py").write_text(
        "def session(): return {}\n", encoding="utf-8"
    )
    (root / "src" / "test_smoke.py").write_text(textwrap.dedent("""
        import unittest
        class T(unittest.TestCase):
            def test_true(self):
                self.assertTrue(True)
        if __name__ == "__main__":
            unittest.main()
    """).strip() + "\n", encoding="utf-8")
    return root


def _mission(scope: str = "src/") -> Mission:
    return Mission(
        mission_id="M-test",
        description="authkit fix",
        scope=scope,
        criteria=["all named tests pass", "behavior probe passes"],
    )


def _make_harness(testcase: unittest.TestCase, scope: str = "src/") -> "_Harness":
    """Build a harness bound to a fresh workspace; teardown is registered
    on the testcase so the directory survives until the test finishes."""
    root = _workspace_path()
    workspace = Workspace(root)
    h = _Harness(workspace, _mission(scope))
    testcase.addCleanup(_teardown, root)
    return h


def _teardown(root: Path) -> None:
    import shutil
    shutil.rmtree(root, ignore_errors=True)


class _Harness:
    """Convenience bundle: workspace + mission + broker + runtime."""

    def __init__(self, workspace: Workspace, mission: Mission):
        self.workspace = workspace
        self.mission = mission
        self.policy = BOBPolicy(self.workspace)
        self.broker = BOBBroker(self.policy, self.workspace)
        self.runtime = BOBRuntime(self.broker)

    def request(self, cap: Capability, target: str, purpose: str = "p",
                requester: str = "agent") -> ActionRequest:
        return ActionRequest(
            sequence=0,  # Broker will stamp
            requester=requester,
            capability=cap,
            target=target,
            purpose=purpose,
        )


# -----------------------------------------------------------------------------
# 1. Allowed READ succeeds end-to-end
# -----------------------------------------------------------------------------

class AllowedReadSucceeds(unittest.TestCase):
    def test_runtime_broker_policy_capability_chain_for_read(self):
        h = _make_harness(self)
        result: RuntimeResult = h.runtime.submit(
            h.request(Capability.READ, "src/hello.txt"),
            h.mission,
        )
        self.assertEqual(
            result.broker_result.decision.decision, Decision.ALLOW,
            msg=f"expected ALLOW, got {result.broker_result.decision}"
        )
        self.assertTrue(result.broker_result.capability_invoked)
        self.assertIsNotNone(result.execution)
        self.assertTrue(result.execution.success)
        self.assertIn("hello-world", result.execution.evidence["content"])
        # Sequence linkage: execution.sequence == decision.sequence
        self.assertEqual(result.execution.sequence, result.broker_result.decision.sequence)
        self.assertGreater(result.sequence, 0)


# -----------------------------------------------------------------------------
# 2. Allowed WRITE succeeds end-to-end
# -----------------------------------------------------------------------------

class AllowedWriteSucceeds(unittest.TestCase):
    def test_write_creates_file_through_chain(self):
        h = _make_harness(self)
        target = "src/authkit/newfile.txt"
        content = "created-by-runtime"
        result = h.runtime.submit(
            h.request(Capability.WRITE, target, purpose=f"content={content}"),
            h.mission,
        )
        self.assertEqual(result.broker_result.decision.decision, Decision.ALLOW)
        self.assertTrue(result.broker_result.capability_invoked)
        self.assertTrue(result.execution.success)
        # The file MUST actually exist on disk.
        path = h.workspace.resolve(target)
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_text(encoding="utf-8"), content)
        # Audit log captured both decision and execution.
        stages = [e["stage"] for e in h.broker.audit]
        self.assertIn("decision", stages)
        self.assertIn("execution", stages)


# -----------------------------------------------------------------------------
# 3. Out-of-scope WRITE is denied
# -----------------------------------------------------------------------------

class OutOfScopeWriteDenied(unittest.TestCase):
    def test_write_outside_workspace_denied(self):
        h = _make_harness(self)
        result = h.runtime.submit(
            h.request(Capability.WRITE, "/tmp/escape.txt", purpose="content=x"),
            h.mission,
        )
        self.assertEqual(result.broker_result.decision.decision, Decision.DENY)
        self.assertIn("outside", result.broker_result.decision.reason)
        self.assertFalse(result.broker_result.capability_invoked)
        self.assertIsNone(result.execution)
        # No audit execution entry on deny.
        stages = [e["stage"] for e in h.broker.audit]
        self.assertNotIn("execution", stages)


# -----------------------------------------------------------------------------
# 4. Denied WRITE causes zero filesystem change (SIDE-EFFECT PROOF)
# -----------------------------------------------------------------------------

class DeniedWriteNoSideEffect(unittest.TestCase):
    def test_denied_write_does_not_create_file(self):
        root = _workspace_path()
        self.addCleanup(_teardown, root)
        # Use a tight mission scope that does NOT match the file path.
        workspace = Workspace(root)
        mission = Mission(
            mission_id="M-tight",
            description="denied",
            scope="src/store",  # mission scope does NOT match authkit/
            criteria=[],
        )
        h = _Harness(workspace, mission)
        before = sorted(p.name for p in (root / "src" / "authkit").iterdir())
        result = h.runtime.submit(
            h.request(
                Capability.WRITE,
                "src/authkit/session.py",
                purpose="content=MUTATED",
            ),
            mission,
        )
        self.assertEqual(result.broker_result.decision.decision, Decision.DENY)
        self.assertFalse(result.broker_result.capability_invoked)
        # File unchanged.
        content_after = (root / "src" / "authkit" / "session.py").read_text()
        self.assertIn("def session", content_after)
        self.assertNotIn("MUTATED", content_after)
        # No new files.
        after = sorted(p.name for p in (root / "src" / "authkit").iterdir())
        self.assertEqual(before, after)

    def test_denied_capability_blocked_no_side_effect(self):
        h = _make_harness(self)
        # Use RUN_TEST on a non-test file -> DENY.
        result = h.runtime.submit(
            ActionRequest(
                sequence=0,
                requester="agent",
                capability=Capability.RUN_TEST,
                target="src/hello.txt",
                purpose="run",
            ),
            h.mission,
        )
        self.assertEqual(result.broker_result.decision.decision, Decision.DENY)
        self.assertIn("name-pattern", result.broker_result.decision.reason)
        self.assertFalse(result.broker_result.capability_invoked)


# -----------------------------------------------------------------------------
# 5. Broker always consults Policy
# -----------------------------------------------------------------------------

class BrokerAlwaysConsultsPolicy(unittest.TestCase):
    def test_broker_calls_policy_for_every_request(self):
        h = _make_harness(self)
        calls: list[tuple[ActionRequest, Mission]] = []
        original = h.policy.consult

        def spy(request, mission):
            calls.append((request, mission))
            return original(request, mission)

        h.policy.consult = spy  # type: ignore[assignment]
        h.runtime.submit(h.request(Capability.READ, "src/hello.txt"), h.mission)
        h.runtime.submit(h.request(Capability.WRITE, "/tmp/escape", purpose="content=x"), h.mission)
        h.runtime.submit(h.request(Capability.LIST, "src/"), h.mission)
        self.assertEqual(len(calls), 3)


# -----------------------------------------------------------------------------
# 6. Direct capability bypass is prevented/flagged
# -----------------------------------------------------------------------------

class BypassIsBlocked(unittest.TestCase):
    def test_runtime_refuses_non_bobbroker_argument(self):
        class FakeBroker:
            def submit(self, request, mission):
                return None
            def next_sequence(self):
                return 0

        with self.assertRaises(TypeError):
            BOBRuntime(FakeBroker())  # type: ignore[arg-type]
    def test_only_broker_imports_execute_capability(self):
        # Only broker.py is allowed to import execute_capability.
        # We exclude __init__.py because it re-exports the symbol.
        proc = subprocess.run(
            ["grep", "-rln", "--include=*.py",
             "--exclude=__init__.py",
             "from raphael_ibm_bob.capabilities import",
             "raphael_ibm_bob"],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True, text=True,
        )
        importers = [l for l in proc.stdout.splitlines() if l.strip()]
        self.assertEqual(sorted(importers), ["raphael_ibm_bob/broker.py"])
# 7. Runtime routes through Broker
# -----------------------------------------------------------------------------

class RuntimeRoutesThroughBroker(unittest.TestCase):
    def test_runtime_submission_increments_broker_counters(self):
        h = _make_harness(self)
        before_sub = h.broker.submissions
        before_inv = h.broker.capability_invocations
        result = h.runtime.submit(
            h.request(Capability.LIST, "src/"),
            h.mission,
        )
        self.assertEqual(h.broker.submissions, before_sub + 1)
        self.assertTrue(result.broker_result.capability_invoked)
        self.assertEqual(h.broker.capability_invocations, before_inv + 1)

    def test_runtime_rejects_malformed_request(self):
        h = _make_harness(self)
        with self.assertRaises(ValueError):
            h.runtime.submit(
                ActionRequest(
                    sequence=0,
                    requester="",  # missing
                    capability=Capability.READ,
                    target="src/hello.txt",
                    purpose="read",
                ),
                h.mission,
            )


# -----------------------------------------------------------------------------
# 8. Forbidden process/network attempt is denied
# -----------------------------------------------------------------------------

    def test_network_capability_outside_mvp_allow_list_denied(self):
        h = _make_harness(self)
        # Use a string masquerading as a capability value. The
        # dispatch table is keyed on Capability enum members, not
        # arbitrary strings.
        sentinel = "network"
        self.assertNotIn(sentinel, CAPABILITY_DISPATCH)
        with self.assertRaises(ValueError):
            execute_capability(h.workspace, ActionRequest(
                sequence=0,
                requester="agent",
                capability=sentinel,  # type: ignore[arg-type]
                target="src/",
                purpose="connect",
            ))

    def test_policy_does_not_have_network_capability(self):
        h = _make_harness(self)
        # Bypass the enum entirely; the policy must still DENY.
        sentinel = "network"
        decision = h.policy.consult(
            ActionRequest(
                sequence=0,
                requester="agent",
                capability=sentinel,  # type: ignore[arg-type]
                target="src/",
                purpose="connect",
            ),
            h.mission,
        )
        self.assertEqual(decision.decision, Decision.DENY)
        self.assertIn("capability-not-allowed", decision.reason)


# -----------------------------------------------------------------------------
# 9. ExecutionResult links to request sequence (PROVENANCE)
# -----------------------------------------------------------------------------

class ProvenanceLink(unittest.TestCase):
    def test_execution_sequence_matches_decision_sequence(self):
        h = _make_harness(self)
        for cap, target, purpose in [
            (Capability.READ, "src/hello.txt", "p"),
            (Capability.LIST, "src/", "p"),
            (Capability.SEARCH, "src/", "def session"),
            (Capability.WRITE, "src/x.txt", "content=hi"),
        ]:
            result = h.runtime.submit(
                h.request(cap, target, purpose=purpose), h.mission,
            )
            self.assertEqual(result.sequence, result.broker_result.decision.sequence)
            self.assertEqual(result.sequence, result.execution.sequence)

    def test_audit_log_records_decision_then_execution(self):
        h = _make_harness(self)
        h.runtime.submit(
            h.request(Capability.READ, "src/hello.txt"), h.mission,
        )
        stages = [e["stage"] for e in h.broker.audit]
        self.assertEqual(stages[-2:], ["decision", "execution"])
        decision_seq = h.broker.audit[-2]["sequence"]
        execution_seq = h.broker.audit[-1]["sequence"]
        self.assertEqual(decision_seq, execution_seq)


# -----------------------------------------------------------------------------
# 10. Boundary test: structural + behavioral prevention of bypass
# -----------------------------------------------------------------------------

class BoundaryTestNoBypass(unittest.TestCase):
    """A would-be agent/planner/verifier cannot directly call a capability
    implementation to bypass Policy."""

    def test_behavioral_no_bypass_for_out_of_scope_write(self):
        root = _workspace_path()
        self.addCleanup(_teardown, root)
        ledger_dir = Path(tempfile.mkdtemp(prefix="raphael_ibm_bob_m2_ledger_"))
        self.addCleanup(_teardown, ledger_dir)
        workspace = Workspace(root)
        mission = Mission(
            mission_id="M-strict",
            description="strict scope",
            scope="src/nonexistent/",
            criteria=[],
        )
        ledger = EvidenceLedger(ledger_dir)
        self.addCleanup(ledger.close)
        policy = BOBPolicy(workspace)
        broker = BOBBroker(policy, workspace, ledger=ledger)
        runtime = BOBRuntime(broker)
        target = root / "src" / "authkit" / "store.py"
        before = target.read_text(encoding="utf-8")
        invocations_before = broker.capability_invocations

        result = runtime.submit(
            ActionRequest(
                sequence=0,
                requester="agent",
                capability=Capability.WRITE,
                target="src/authkit/store.py",
                purpose="content=MUTATED",
            ),
            mission,
        )

        self.assertEqual(result.broker_result.decision.decision, Decision.DENY)
        self.assertFalse(result.broker_result.capability_invoked)
        self.assertEqual(broker.capability_invocations, invocations_before)
        self.assertIsNone(result.execution)
        self.assertIsNone(result.broker_result.result_seq)
        self.assertIsNone(result.broker_result.execution)

        records = ledger.all_records()
        self.assertTrue(records, "expected the denied request to be recorded")
        self.assertEqual(
            [r for r in records if r.get("kind") == "result"], [],
            "DENY must produce no ExecutionResult record",
        )
        self.assertEqual(
            [r for r in records if r.get("producer") == "execution"], [],
            "DENY must produce no execution evidence",
        )

        after = target.read_text(encoding="utf-8")
        self.assertEqual(before, after)
        self.assertNotIn("MUTATED", after)

        stages = [e["stage"] for e in broker.audit]
        self.assertIn("decision", stages)
        self.assertNotIn("execution", stages)

    def test_mutation_guard_allow_does_invoke_and_record(self):
        """The same instrumentation as the DENY test: on ALLOW the Broker DOES
        invoke and DOES record a result. If a future regression made the Broker
        invoke after DENY, the assertions in the test above would fail."""
        root = _workspace_path()
        self.addCleanup(_teardown, root)
        ledger_dir = Path(tempfile.mkdtemp(prefix="raphael_ibm_bob_m2_ledger_"))
        self.addCleanup(_teardown, ledger_dir)
        workspace = Workspace(root)
        mission = _mission()
        ledger = EvidenceLedger(ledger_dir)
        self.addCleanup(ledger.close)
        broker = BOBBroker(BOBPolicy(workspace), workspace, ledger=ledger)
        runtime = BOBRuntime(broker)
        invocations_before = broker.capability_invocations

        result = runtime.submit(
            ActionRequest(
                sequence=0,
                requester="agent",
                capability=Capability.WRITE,
                target="src/authkit/allowed.txt",
                purpose="content=ok",
            ),
            mission,
        )

        self.assertEqual(result.broker_result.decision.decision, Decision.ALLOW)
        self.assertTrue(result.broker_result.capability_invoked)
        self.assertEqual(broker.capability_invocations, invocations_before + 1)
        self.assertIsNotNone(result.execution)
        self.assertIsNotNone(result.broker_result.result_seq)
        records = ledger.all_records()
        self.assertTrue([r for r in records if r.get("kind") == "result"])
        self.assertTrue([r for r in records if r.get("producer") == "execution"])
        self.assertEqual(
            [e["stage"] for e in broker.audit][-1], "execution")

    def test_structural_only_broker_invokes_execute_capability(self):
        proc = subprocess.run(
            ["grep", "-rln", "--include=*.py",
             "--exclude=__init__.py",
             "from raphael_ibm_bob.capabilities import",
             "raphael_ibm_bob"],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True, text=True,
        )
        importers = sorted(l for l in proc.stdout.splitlines() if l.strip())
        self.assertEqual(importers, ["raphael_ibm_bob/broker.py"])

    def test_structural_runtime_rejects_non_bob_broker(self):
        class FakeBroker:
            def submit(self, request, mission):
                return None
            def next_sequence(self):
                return 0
        with self.assertRaises(TypeError):
            BOBRuntime(FakeBroker())  # type: ignore[arg-type]


# -----------------------------------------------------------------------------
# 11. LIST and SEARCH path coverage
# -----------------------------------------------------------------------------

class ListAndSearch(unittest.TestCase):
    def test_list_returns_entries(self):
        h = _make_harness(self)
        result = h.runtime.submit(
            h.request(Capability.LIST, "src/authkit"), h.mission,
        )
        self.assertEqual(result.broker_result.decision.decision, Decision.ALLOW)
        entries = result.execution.evidence["entries"]
        self.assertIn("store.py", entries)
        self.assertIn("session.py", entries)

    def test_search_finds_pattern(self):
        h = _make_harness(self)
        result = h.runtime.submit(
            h.request(Capability.SEARCH, "src/", purpose="def session"),
            h.mission,
        )
        self.assertEqual(result.broker_result.decision.decision, Decision.ALLOW)
        matches = result.execution.evidence["matches"]
        self.assertTrue(any(m["file"].endswith("session.py") for m in matches))


# -----------------------------------------------------------------------------
# 12. RUN_TEST through the real subprocess boundary
# -----------------------------------------------------------------------------

class RunTestCapability(unittest.TestCase):
    def test_run_test_succeeds_on_valid_test_file(self):
        h = _make_harness(self)
        result = h.runtime.submit(
            h.request(Capability.RUN_TEST, "src/test_smoke.py"),
            h.mission,
        )
        self.assertEqual(result.broker_result.decision.decision, Decision.ALLOW)
        self.assertTrue(result.execution.success)
        self.assertEqual(result.execution.evidence["returncode"], 0)

    def test_run_test_denied_on_non_test_file(self):
        h = _make_harness(self)
        result = h.runtime.submit(
            h.request(Capability.RUN_TEST, "src/hello.txt"),
            h.mission,
        )
        self.assertEqual(result.broker_result.decision.decision, Decision.DENY)
        self.assertIn("name-pattern", result.broker_result.decision.reason)


if __name__ == "__main__":
    unittest.main()