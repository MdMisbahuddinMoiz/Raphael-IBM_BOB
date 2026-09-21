"""tests.test_c1a_security_invariants — adversarial C1A boundary regressions.

Each test asserts a fail-closed invariant added to the governed C1A path:

    1. ``C1AAuthorizationBinding.verify_binding`` runs BEFORE provider
       dispatch (a binding that cannot be re-verified never reaches the
       provider).
    2. ``invoke_governed`` enforces ``runtime.provider_id ==
       handoff.provider_id`` before provider execution.
    3. ``mission_id`` is bound through Mission -> AuthorizationBinding ->
       ScopeHandoff -> ProviderResult/evidence and cannot be grafted.
    4. ``C1AReplayGuard`` is wired into the production Broker path and
       prevents ProviderResult/result lineage grafting across executions.

No real T3MP3ST provider is executed here; the inert double and synthetic
runtimes are test infrastructure only.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.c1a_testkit import (  # noqa: E402
    CountingInertProvider,
    c1a_request,
    cleanup,
    make_stack,
)
from raphael_ibm_bob.c1a_authorization import (  # noqa: E402
    BINDING_FIELDS,
    C1AAuthorizationError,
)
from raphael_ibm_bob.c1a_replay import (  # noqa: E402
    C1AReplayError,
    C1AReplayGuard,
    new_lineage,
)
from raphael_ibm_bob.contracts import Decision, PolicyDecision  # noqa: E402
from raphael_ibm_bob.provider_runtime import (  # noqa: E402
    C1A_PROVIDER_ID,
    ProviderResult,
    ProviderState,
    ScopeViolation,
    invoke_governed,
    validate_scope,
)

MISSION_ID = "M-c1a"
FIXTURE_SHA = "a" * 64


def _allow(sequence, target):
    from raphael_ibm_bob.contracts import Capability
    return PolicyDecision(
        sequence=sequence, decision=Decision.ALLOW, reason="ok",
        capability=Capability.C1A_STATIC_FILE_INSPECT, target=str(target))


class _ProviderIdRuntime:
    """Records whether its ``invoke`` was reached (must not be on mismatch)."""

    def __init__(self, provider_id=C1A_PROVIDER_ID):
        self.provider_id = provider_id
        self.calls = 0

    def invoke(self, handoff, request):  # pragma: no cover - asserted not called
        self.calls += 1
        raise AssertionError("provider invoked despite provider_id mismatch")


class _GraftingRuntime:
    """Returns a ProviderResult whose lineage was bound to another execution."""

    provider_id = C1A_PROVIDER_ID

    def __init__(self, **overrides):
        self.overrides = overrides
        self.calls = 0

    def invoke(self, handoff, request):
        self.calls += 1
        base = dict(
            state=ProviderState.SUCCESS,
            run_id=handoff.run_id,
            action_request_id=handoff.action_request_id,
            invocation_id=handoff.invocation_id,
            proof_session_id=handoff.proof_session_id,
            capability_id=handoff.capability_id,
            provider_id=handoff.provider_id,
            mission_id=handoff.mission_id,
            result_hash="sha256:deadbeef",
        )
        base.update(self.overrides)
        return ProviderResult(**base)


class VerifyBindingBeforeDispatch(unittest.TestCase):
    def setUp(self):
        self.provider = CountingInertProvider()
        self.stack = make_stack(provider=self.provider, with_ledger=True)
        self.addCleanup(cleanup, self.stack.root)

    def _submit(self):
        return self.stack.runtime.submit(
            c1a_request(self.stack.fixture), self.stack.mission)

    def test_verify_failure_blocks_provider_dispatch(self):
        with mock.patch.object(self.stack.auth, "verify_binding",
                               return_value=False):
            result = self._submit()
        self.assertIs(result.broker_result.decision.decision, Decision.ALLOW)
        self.assertEqual(self.provider.calls, 0,
                         "provider ran without a verified binding")
        self.assertFalse(result.execution.success)
        self.assertIn("binding verification failed", result.execution.error)

    def test_verify_success_allows_dispatch(self):
        result = self._submit()
        self.assertTrue(result.execution.success)
        self.assertEqual(self.provider.calls, 1)

    def test_consumed_binding_cannot_be_verified(self):
        decision = _allow(1, self.stack.fixture)
        binding = self.stack.auth.create_binding(
            decision=decision,
            request=c1a_request(self.stack.fixture, sequence=1),
            run_id="run-1", mission_id=MISSION_ID,
            workspace_root=str(self.stack.root), timeout_seconds=10.0)
        self.assertTrue(
            self.stack.auth.verify_binding(binding.invocation_id, decision))
        self.stack.auth.invalidate_binding(binding.invocation_id)
        self.assertFalse(
            self.stack.auth.verify_binding(binding.invocation_id, decision))


class ProviderIdentityEnforcement(unittest.TestCase):
    def setUp(self):
        self.stack = make_stack(with_ledger=False)
        self.addCleanup(cleanup, self.stack.root)
        request = c1a_request(self.stack.fixture)
        decision = self.stack.policy.consult(request, self.stack.mission)
        self.binding = self.stack.auth.create_binding(
            decision=decision, request=request, run_id="run-1",
            mission_id=self.stack.mission.mission_id,
            workspace_root=str(self.stack.root), timeout_seconds=10.0)
        self.handoff = self.binding.handoff
        self.request = request

    def test_runtime_provider_id_mismatch_fails_closed(self):
        foreign = _ProviderIdRuntime(provider_id="decepticon")
        with self.assertRaises(ScopeViolation):
            invoke_governed(foreign, self.handoff, self.request)
        self.assertEqual(foreign.calls, 0,
                         "foreign provider was executed before identity check")

    def test_matching_provider_id_executes(self):
        runtime = _ProviderIdRuntime(provider_id=C1A_PROVIDER_ID)
        # A matching-id runtime that raises must surface as UNAVAILABLE, not
        # ScopeViolation: proves the check is identity-only, not a blanket
        # refusal.
        result = invoke_governed(runtime, self.handoff, self.request)
        self.assertIs(result.state, ProviderState.UNAVAILABLE)
        self.assertEqual(runtime.calls, 1)


class MissionLineage(unittest.TestCase):
    def setUp(self):
        self.stack = make_stack(provider=CountingInertProvider(),
                                with_ledger=True)
        self.addCleanup(cleanup, self.stack.root)
        self.request = c1a_request(self.stack.fixture)
        self.decision = self.stack.policy.consult(
            self.request, self.stack.mission)
        self.binding = self.stack.auth.create_binding(
            decision=self.decision, request=self.request, run_id="run-1",
            mission_id=self.stack.mission.mission_id,
            workspace_root=str(self.stack.root), timeout_seconds=10.0)
        self.handoff = self.binding.handoff

    def test_mission_id_is_a_sealed_binding_field(self):
        self.assertIn("mission_id", BINDING_FIELDS)
        self.assertEqual(self.binding.identity["mission_id"],
                         self.stack.mission.mission_id)
        self.assertEqual(self.binding.mission_id,
                         self.stack.mission.mission_id)

    def test_handoff_carries_mission_id(self):
        self.assertEqual(self.handoff.mission_id,
                         self.stack.mission.mission_id)

    def test_empty_mission_id_rejected(self):
        for bad in ("", "   ", None):
            with self.assertRaises(C1AAuthorizationError):
                self.stack.auth.create_binding(
                    decision=self.decision, request=self.request,
                    run_id="run-1", mission_id=bad,
                    workspace_root=str(self.stack.root), timeout_seconds=10.0)

    def test_scope_requires_nonempty_mission_id(self):
        from dataclasses import replace
        with self.assertRaises(ScopeViolation):
            validate_scope(replace(self.handoff, mission_id=""), self.request)

    def test_mission_id_tamper_fails_verification(self):
        self.assertFalse(self.stack.auth.verify_binding(
            self.binding.invocation_id, self.decision,
            claimed={"mission_id": "M-evil"}))

    def test_provider_result_carries_mission_id(self):
        result = invoke_governed(
            CountingInertProvider(), self.handoff, self.request)
        self.assertIs(result.state, ProviderState.SUCCESS)
        self.assertEqual(result.mission_id, self.stack.mission.mission_id)
        self.assertEqual(result.to_dict()["mission_id"],
                         self.stack.mission.mission_id)

    def test_mission_graft_rejected(self):
        graft = _GraftingRuntime(mission_id="M-foreign")
        result = invoke_governed(graft, self.handoff, self.request)
        self.assertEqual(graft.calls, 1)
        self.assertIs(result.state, ProviderState.FAILURE)
        self.assertFalse(result.success)
        self.assertIn("lineage mismatch", result.error)

    def test_broker_evidence_carries_mission_and_lineage(self):
        submission = self.stack.runtime.submit(self.request, self.stack.mission)
        self.assertTrue(submission.execution.success)
        evidence = submission.execution.evidence
        self.assertEqual(evidence["mission_id"], self.stack.mission.mission_id)
        records = [r for r in self.stack.ledger.all_records()
                   if r.get("producer") == "provider"]
        self.assertTrue(records)
        payload = records[-1]["payload"]
        self.assertEqual(payload["mission_id"], self.stack.mission.mission_id)
        self.assertEqual(len(payload["fixture_sha256"]), 64)
        int(payload["fixture_sha256"], 16)
        self.assertEqual(len(payload["lineage_hash"]), 64)
        int(payload["lineage_hash"], 16)


class ReplayGuardWiring(unittest.TestCase):
    def setUp(self):
        self.provider = CountingInertProvider()
        self.stack = make_stack(provider=self.provider, with_ledger=True)
        self.addCleanup(cleanup, self.stack.root)

    def _submit(self):
        return self.stack.runtime.submit(
            c1a_request(self.stack.fixture), self.stack.mission)

    def test_broker_owns_a_single_replay_guard(self):
        guard = self.stack.broker.c1a_replay_guard
        self.assertIsInstance(guard, C1AReplayGuard)
        self.assertIs(guard, self.stack.broker.c1a_replay_guard)

    def test_broker_registers_execution_lineage(self):
        result = self._submit()
        self.assertTrue(result.execution.success)
        invocation_id = result.execution.evidence["invocation_id"]
        guard = self.stack.broker.c1a_replay_guard
        self.assertTrue(guard.is_registered(invocation_id))
        self.assertEqual(guard.run_for(invocation_id),
                         self.stack.ledger.run_dir().name)

    def test_replayed_invocation_rejected_by_guard(self):
        result = self._submit()
        invocation_id = result.execution.evidence["invocation_id"]
        guard = self.stack.broker.c1a_replay_guard
        replay = new_lineage(
            run_id=self.stack.ledger.run_dir().name,
            invocation_id=invocation_id,
            proof_session_id="PS-replay",
            sandbox_id="SBOX-replay",
            fixture_path=str(self.stack.fixture),
            fixture_sha256=FIXTURE_SHA)
        with self.assertRaises(C1AReplayError):
            guard.register(replay)

    def test_cross_run_lineage_substitution_rejected(self):
        guard = C1AReplayGuard()
        guard.register(new_lineage(
            run_id="run-1", invocation_id="INV-x",
            proof_session_id="PS-1", sandbox_id="SBOX-1",
            fixture_path="/fixture/sink.bin", fixture_sha256=FIXTURE_SHA))
        with self.assertRaises(C1AReplayError):
            guard.register(new_lineage(
                run_id="run-2", invocation_id="INV-x",
                proof_session_id="PS-2", sandbox_id="SBOX-2",
                fixture_path="/fixture/sink.bin", fixture_sha256=FIXTURE_SHA))

    def test_guard_failure_blocks_provider_dispatch(self):
        with mock.patch.object(
                self.stack.broker.c1a_replay_guard, "register",
                side_effect=C1AReplayError("replayed invocation")):
            result = self._submit()
        self.assertEqual(self.provider.calls, 0,
                         "provider ran after replay rejection")
        self.assertFalse(result.execution.success)
        self.assertIn("C1AReplayError", result.execution.error)

    def test_provider_result_invocation_graft_rejected(self):
        request = c1a_request(self.stack.fixture)
        decision = self.stack.policy.consult(request, self.stack.mission)
        binding = self.stack.auth.create_binding(
            decision=decision, request=request, run_id="run-1",
            mission_id=self.stack.mission.mission_id,
            workspace_root=str(self.stack.root), timeout_seconds=10.0)
        graft = _GraftingRuntime(invocation_id="INV-from-another-execution")
        result = invoke_governed(graft, binding.handoff, request)
        self.assertEqual(graft.calls, 1)
        self.assertIs(result.state, ProviderState.FAILURE)
        self.assertFalse(result.success)
        self.assertIn("lineage mismatch", result.error)
        # The rejection is re-bound to THIS handoff, never the grafted id.
        self.assertEqual(result.invocation_id, binding.handoff.invocation_id)


if __name__ == "__main__":
    unittest.main()
