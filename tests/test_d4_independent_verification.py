"""tests.test_d4_independent_verification — D4 adversarial verification suite.

Maps the GLM D4 design onto the production RAPHAEL code. Independence is
causal/evidential (P1..P6), not infrastructural: same mission, finding,
provider, target, capability, inputs, and sandbox are allowed; the execution,
invocation, and provider observation must be NEW and provenance must
terminate at the NEW invocation.

No real T3MP3ST provider executes here; the inert double is test
infrastructure only.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.c1a_testkit import (  # noqa: E402
    CountingInertProvider,
    c1a_request,
    cleanup,
    make_mission,
    make_stack,
)
from raphael_ibm_bob.c1a_falsification import (  # noqa: E402
    C1AFalsifier,
    FalsificationClassification,
    FalsificationResult,
)
from raphael_ibm_bob.c1a_verification import (  # noqa: E402
    MINIMUM_INDEPENDENT_EXECUTIONS,
    C1AVerifier,
    ExecutionRef,
    VerificationClassification,
    VerificationGovernanceError,
    VerificationInProgressError,
    VerificationRequest,
    VerificationRequestError,
    VerificationResult,
    VerificationValidator,
    build_verification_request,
    evaluate_independence,
    execution_ref_from_runtime_result,
    validate_lineage,
)
from raphael_ibm_bob.contracts import (  # noqa: E402
    Finding,
    FindingState,
)
from raphael_ibm_bob.quality_gate import (  # noqa: E402
    BOBQualityGate,
    GateInputs,
)
from raphael_ibm_bob.finding import FindingStore  # noqa: E402


MISSION_ID = "M-c1a"
FINDING_ID = "F-d4"


class _Base(unittest.TestCase):
    def _stack(self, provider=None, with_ledger=True):
        stack = make_stack(provider=provider or CountingInertProvider(),
                           with_ledger=with_ledger)
        self.addCleanup(cleanup, stack.root)
        return stack

    def _original(self, stack, finding_id=FINDING_ID):
        """Run the ORIGINAL governed execution and return (runtime_result, ref)."""
        rt = stack.runtime.submit(c1a_request(stack.fixture), stack.mission)
        ref = execution_ref_from_runtime_result(
            rt, mission_id=stack.mission.mission_id, finding_id=finding_id)
        return rt, ref

    def _finding(self, stack, *, finding_id=FINDING_ID,
                 state=FindingState.UNVERIFIED, target=None, mission_id=MISSION_ID):
        store = FindingStore(stack.ledger)
        finding = Finding(
            finding_id=finding_id,
            state=state,
            summary="d4 candidate",
            target=str(target if target is not None else stack.fixture),
            mission_id=mission_id,
        )
        store.register(finding)
        return store, store.get(finding_id)

    def _request(self, stack, *, purpose="verify", finding=None, original=None,
                 finding_id=FINDING_ID):
        if original is None:
            _, original = self._original(stack, finding_id)
        if finding is None:
            _, finding = self._finding(stack, finding_id=finding_id)
        return finding, build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger,
            purpose=purpose)


class ValidIndependentVerification(_Base):
    # Test 1, 26
    def test_valid_independent_verification_succeeds(self):
        stack = self._stack()
        rt, original = self._original(stack)
        store, finding = self._finding(stack)
        request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger)
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        result = verifier.verify_independent(
            request, stack.mission, expected_result_hash="test-hash")

        self.assertIs(result.classification,
                      VerificationClassification.SUPPORTED)
        self.assertTrue(result.independence.all_passed)
        self.assertTrue(result.lineage.valid)
        self.assertTrue(result.transition_applied)
        self.assertIs(store.get(FINDING_ID).state, FindingState.VERIFIED)
        self.assertIs(result._mint is not None, True)

    # Test 26 explicitly: same provider + same target + same inputs + NEW
    # execution + NEW observation succeeds.
    def test_same_infrastructure_new_execution_succeeds(self):
        stack = self._stack()
        _, original = self._original(stack)
        store, finding = self._finding(stack)
        request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger)
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        result = verifier.verify_independent(
            request, stack.mission, expected_result_hash="test-hash")
        self.assertTrue(result.independence.distinct_execution)
        self.assertTrue(result.independence.distinct_invocation)
        self.assertTrue(result.independence.fresh_provider_observation)
        # Same mission/target/capability/provider are explicitly allowed.
        self.assertEqual(result.mission_id, original.mission_id)
        self.assertNotEqual(result.verification_execution.execution_id,
                            original.execution_id)
        self.assertNotEqual(result.verification_execution.invocation_id,
                            original.invocation_id)

    def test_minimum_independent_executions_not_satisfied_by_original(self):
        stack = self._stack()
        _, original = self._original(stack)
        store, finding = self._finding(stack)
        request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger)
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        result = verifier.verify_independent(
            request, stack.mission, expected_result_hash="test-hash")
        self.assertEqual(MINIMUM_INDEPENDENT_EXECUTIONS, 1)
        self.assertGreaterEqual(
            result.independence.independent_execution_count(),
            MINIMUM_INDEPENDENT_EXECUTIONS)

    # Test 24, 25
    def test_mission_and_execution_lineage_intact(self):
        stack = self._stack()
        _, original = self._original(stack)
        store, finding = self._finding(stack)
        request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger)
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        result = verifier.verify_independent(
            request, stack.mission, expected_result_hash="test-hash")
        self.assertEqual(result.mission_id, request.mission_id)
        self.assertEqual(result.finding_id, request.finding_id)
        self.assertEqual(result.mission_id, finding.mission_id)
        self.assertEqual(result.verification_execution.finding_id, FINDING_ID)

    # Test 30
    def test_original_and_verification_do_not_share_execution_state(self):
        stack = self._stack()
        _, original = self._original(stack)
        store, finding = self._finding(stack)
        request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger)
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        result = verifier.verify_independent(
            request, stack.mission, expected_result_hash="test-hash")
        self.assertNotEqual(original.execution_id,
                            result.verification_execution.execution_id)
        self.assertNotEqual(original.invocation_id,
                            result.verification_execution.invocation_id)


class AntiGrafting(_Base):
    def _setup(self):
        stack = self._stack()
        rt, original = self._original(stack)
        store, finding = self._finding(stack)
        request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger)
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        pr = rt.execution.evidence["provider_result"]
        return stack, original, request, verifier, pr

    def _assess(self, verifier, request, ref, pr, expected="test-hash"):
        return verifier.assess_observation(
            request, provider_result=pr, verification_execution=ref,
            expected_result_hash=expected)

    # Test 2, 15
    def test_original_execution_reuse_fails(self):
        _, original, request, verifier, pr = self._setup()
        result = self._assess(verifier, request, original, pr)
        self.assertIs(result.classification,
                      VerificationClassification.INSUFFICIENT)
        self.assertFalse(result.transition_applied)
        self.assertFalse(result.independence.distinct_execution)

    # Test 3
    def test_original_provider_result_reuse_fails(self):
        _, original, request, verifier, pr = self._setup()
        new_exec = ExecutionRef(
            mission_id=original.mission_id, run_id=original.run_id,
            execution_id="EX-brand-new",
            invocation_id=original.invocation_id,
            provider_result_ref=original.provider_result_ref,
            finding_id=FINDING_ID)
        result = self._assess(verifier, request, new_exec, pr)
        self.assertIs(result.classification,
                      VerificationClassification.INSUFFICIENT)
        self.assertFalse(result.independence.distinct_invocation)
        self.assertFalse(result.independence.fresh_provider_observation)

    # Test 27
    def test_new_provider_result_record_with_copied_observation_fails(self):
        _, original, request, verifier, pr = self._setup()
        copied = ExecutionRef(
            mission_id=original.mission_id, run_id=original.run_id,
            execution_id="EX-copied",
            invocation_id="INV-copied",
            provider_result_ref=original.provider_result_ref,
            finding_id=FINDING_ID)
        result = self._assess(verifier, request, copied, pr)
        self.assertIs(result.classification,
                      VerificationClassification.INSUFFICIENT)
        self.assertFalse(result.independence.fresh_provider_observation)

    # Test 28
    def test_new_invocation_with_replayed_output_fails(self):
        _, original, request, verifier, pr = self._setup()
        replayed = ExecutionRef(
            mission_id=original.mission_id, run_id=original.run_id,
            execution_id="EX-replay",
            invocation_id="INV-replay",
            provider_result_ref="PR-replay",
            finding_id=FINDING_ID)
        result = self._assess(verifier, request, replayed, pr)
        self.assertIs(result.classification,
                      VerificationClassification.INSUFFICIENT)
        self.assertFalse(result.independence.causal_binding_valid)

    # Test 4, 5
    def test_original_evidence_reuse_and_cross_run_graft_fail(self):
        _, original, request, verifier, pr = self._setup()
        foreign_run = ExecutionRef(
            mission_id=original.mission_id, run_id="some-other-run",
            execution_id="EX-foreign", invocation_id="INV-foreign",
            provider_result_ref="PR-foreign", finding_id=FINDING_ID)
        result = self._assess(verifier, request, foreign_run, pr)
        self.assertIs(result.classification,
                      VerificationClassification.INSUFFICIENT)
        self.assertFalse(result.independence.no_replayed_execution)

    # Test 6
    def test_cross_finding_graft_fails(self):
        _, original, request, verifier, pr = self._setup()
        foreign_finding = ExecutionRef(
            mission_id=original.mission_id, run_id=original.run_id,
            execution_id="EX-f", invocation_id="INV-f",
            provider_result_ref="PR-f", finding_id="F-other")
        result = self._assess(verifier, request, foreign_finding, pr)
        self.assertIs(result.classification,
                      VerificationClassification.INSUFFICIENT)
        self.assertFalse(result.lineage.valid)

    # Test 7
    def test_cross_mission_graft_fails(self):
        _, original, request, verifier, pr = self._setup()
        pr = dict(pr)
        pr["mission_id"] = "M-other"
        foreign = ExecutionRef(
            mission_id="M-other", run_id=original.run_id,
            execution_id="EX-m", invocation_id="INV-m",
            provider_result_ref="PR-m", finding_id=FINDING_ID)
        result = self._assess(verifier, request, foreign, pr)
        self.assertIs(result.classification,
                      VerificationClassification.INSUFFICIENT)

    # Test 13
    def test_wrong_provider_fails(self):
        _, original, request, verifier, pr = self._setup()
        pr = dict(pr)
        pr["provider_id"] = "decepticon"
        new_exec = ExecutionRef(
            mission_id=original.mission_id, run_id=original.run_id,
            execution_id="EX-wp", invocation_id="INV-wp",
            provider_result_ref="PR-wp", finding_id=FINDING_ID)
        result = self._assess(verifier, request, new_exec, pr)
        self.assertIs(result.classification,
                      VerificationClassification.INSUFFICIENT)
        self.assertFalse(result.lineage.valid)

    # Test 14
    def test_wrong_capability_fails(self):
        _, original, request, verifier, pr = self._setup()
        pr = dict(pr)
        pr["capability_id"] = "read"
        new_exec = ExecutionRef(
            mission_id=original.mission_id, run_id=original.run_id,
            execution_id="EX-wc", invocation_id="INV-wc",
            provider_result_ref="PR-wc", finding_id=FINDING_ID)
        result = self._assess(verifier, request, new_exec, pr)
        self.assertIs(result.classification,
                      VerificationClassification.INSUFFICIENT)

    # Test 12
    def test_replayed_verification_result_fails(self):
        _, original, request, verifier, pr = self._setup()
        reused = ExecutionRef(
            mission_id=original.mission_id, run_id=original.run_id,
            execution_id=original.execution_id,
            invocation_id=original.invocation_id,
            provider_result_ref=original.provider_result_ref,
            finding_id=FINDING_ID)
        result = self._assess(verifier, request, reused, pr)
        self.assertIs(result.classification,
                      VerificationClassification.INSUFFICIENT)
        self.assertFalse(result.transition_applied)


class ConstructionAuthority(_Base):
    # Test 8
    def test_verification_request_cannot_be_forged(self):
        stack = self._stack()
        _, original = self._original(stack)
        with self.assertRaises(VerificationRequestError):
            VerificationRequest(
                record_id="VR-forged", mission_id=MISSION_ID,
                finding_id=FINDING_ID, original_execution=original,
                target=str(stack.fixture), capability="x", scope="s")

    # Test 8 / 29
    def test_verification_result_cannot_be_forged(self):
        stack = self._stack()
        _, original = self._original(stack)
        _, finding = self._finding(stack)
        request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger)
        checks = evaluate_independence(
            request=request, verification=original, provider_result={})
        lineage = validate_lineage(
            request=request, verification=original, provider_result={})
        with self.assertRaises(VerificationGovernanceError):
            VerificationResult(
                result_id="VRS-forged",
                classification=VerificationClassification.SUPPORTED,
                verification_request_ref="VR-x",
                verification_execution=original,
                finding_id=FINDING_ID, mission_id=MISSION_ID,
                independence=checks,
                lineage=lineage,
                observation={})

    # Test 29
    def test_result_referencing_nonexistent_records_fails(self):
        stack = self._stack()
        _, original = self._original(stack)
        store, finding = self._finding(stack)
        # A request built WITHOUT a ledger is not recorded, so the validator
        # reports the referenced request record missing.
        request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original)
        # Rebuild a well-formed minted result via the verifier, then validate
        # against a ledger that never saw the request.
        from raphael_ibm_bob.c1a_verification import _mint_verification_result
        lineage = validate_lineage(
            request=request, verification=original, provider_result={})
        checks = evaluate_independence(
            request=request, verification=original, provider_result={})
        result = _mint_verification_result(
            request=request, verification=original,
            independence=checks, lineage=lineage,
            classification=VerificationClassification.INSUFFICIENT,
            provider_result={})
        validator = VerificationValidator(stack.ledger)
        verdict = validator.validate(result)
        self.assertFalse(verdict.valid)
        self.assertIn("verification-request-record-not-found",
                      verdict.reasons)


class FindingLifecycleGuards(_Base):
    # Test 17
    def test_nonexistent_finding_fails(self):
        # A finding that was never registered cannot be verified: the
        # lifecycle store has no such id.
        stack = self._stack()
        _, original = self._original(stack, "F-ghost")
        unregistered = Finding(
            finding_id="F-ghost", state=FindingState.UNVERIFIED,
            summary="ghost", target=str(stack.fixture), mission_id=MISSION_ID)
        # build succeeds (it only inspects the value object) but the verifier
        # must not transition a finding the store does not own.
        request = build_verification_request(
            mission=stack.mission, finding=unregistered,
            original_execution=original, ledger=stack.ledger)
        store = FindingStore(stack.ledger)
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        result = verifier.verify_independent(
            request, stack.mission, expected_result_hash="test-hash")
        self.assertFalse(result.transition_applied)
        self.assertIsNone(store.get("F-ghost"))

    # Test 18
    def test_superseded_finding_fails(self):
        stack = self._stack()
        _, original = self._original(stack)
        _, finding = self._finding(stack, state=FindingState.SUPERSEDED)
        with self.assertRaises(VerificationRequestError):
            build_verification_request(
                mission=stack.mission, finding=finding,
                original_execution=original, ledger=stack.ledger)

    # Test 19
    def test_already_verified_finding_fails_by_default(self):
        stack = self._stack()
        _, original = self._original(stack)
        _, finding = self._finding(stack, state=FindingState.VERIFIED)
        with self.assertRaises(VerificationRequestError):
            build_verification_request(
                mission=stack.mission, finding=finding,
                original_execution=original, ledger=stack.ledger)

    def test_finding_without_mission_fails_closed(self):
        stack = self._stack()
        _, original = self._original(stack)
        finding = Finding(
            finding_id=FINDING_ID, state=FindingState.UNVERIFIED,
            summary="no mission", target=str(stack.fixture), mission_id=None)
        with self.assertRaises(VerificationRequestError):
            build_verification_request(
                mission=stack.mission, finding=finding,
                original_execution=original, ledger=stack.ledger)

    # Test 11
    def test_duplicate_active_verification_fails(self):
        stack = self._stack()
        store, finding = self._finding(stack)
        _, original = self._original(stack)
        request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger)
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        verifier._active_verifications.add(FINDING_ID)
        try:
            with self.assertRaises(VerificationInProgressError):
                verifier.verify_independent(request, stack.mission,
                                            expected_result_hash="test-hash")
        finally:
            verifier._active_verifications.discard(FINDING_ID)


class ProviderAuthority(_Base):
    # Test 9
    def test_provider_verified_claim_grants_no_authority(self):
        provider = CountingInertProvider(extra={"verified": True})
        stack = self._stack(provider=provider)
        _, original = self._original(stack)
        store, finding = self._finding(stack)
        request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger)
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        result = verifier.verify_independent(
            request, stack.mission, expected_result_hash="test-hash")
        self.assertIsNot(result.classification,
                         VerificationClassification.SUPPORTED)
        self.assertFalse(result.transition_applied)
        self.assertNotIn("verified", result.observation)
        self.assertFalse(result.supported)

    # Test 15
    def test_wrong_target_observation_fails(self):
        provider = CountingInertProvider(
            extra={"results": [{"path": "/etc/passwd", "kind": "x"}]})
        stack = self._stack(provider=provider)
        _, original = self._original(stack)
        store, finding = self._finding(stack)
        request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger)
        # The target is DERIVED from the finding, never caller-supplied.
        self.assertEqual(request.target, finding.target)
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        result = verifier.verify_independent(
            request, stack.mission, expected_result_hash="test-hash")
        self.assertIsNot(result.classification,
                         VerificationClassification.SUPPORTED)
        self.assertFalse(result.transition_applied)

    # Test 10
    def test_verification_without_authorization_fails(self):
        stack = self._stack()
        store, finding = self._finding(stack, target=stack.root / "missing.bin")
        _, original = self._original(stack)
        request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger)
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        result = verifier.verify_independent(
            request, stack.mission, expected_result_hash="test-hash")
        # No ALLOW decision means no observation: fail closed, never SUPPORTED.
        self.assertIsNot(result.classification,
                         VerificationClassification.SUPPORTED)
        self.assertFalse(result.transition_applied)
        self.assertIs(store.get(FINDING_ID).state, FindingState.UNVERIFIED)

    # Test 16 (wrong mission/scope)
    def test_wrong_mission_scope_fails(self):
        stack = self._stack()
        _, original = self._original(stack)
        store, finding = self._finding(stack)
        request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger)
        other_mission = make_mission(stack.root)
        other_mission = other_mission.__class__(
            mission_id="M-other", description="other",
            scope=str(stack.root), criteria=["x"])
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        result = verifier.verify_independent(
            request, other_mission, expected_result_hash="test-hash")
        self.assertIs(result.classification,
                      VerificationClassification.INSUFFICIENT)
        self.assertFalse(result.transition_applied)


class FalsificationD4(_Base):
    # Test 20
    def test_valid_independent_falsification_refutes(self):
        stack = self._stack()
        _, original = self._original(stack)
        store, finding = self._finding(stack)
        verify_request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger)
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        verified = verifier.verify_independent(
            verify_request, stack.mission, expected_result_hash="test-hash")
        self.assertTrue(verified.transition_applied)

        current = store.get(FINDING_ID)
        falsify_request = build_verification_request(
            mission=stack.mission, finding=current,
            original_execution=verified.verification_execution,
            ledger=stack.ledger, purpose="falsify")
        falsifier = C1AFalsifier(stack.runtime, stack.ledger, store)
        result = falsifier.challenge_independent(
            falsify_request, stack.mission,
            expected_result_hash="different-hash")
        self.assertIs(result.classification,
                      FalsificationClassification.DISPROVED)
        self.assertTrue(result.transition_applied)
        self.assertIs(store.get(FINDING_ID).state, FindingState.REFUTED)

    def test_falsification_no_contradiction_keeps_verified(self):
        stack = self._stack()
        _, original = self._original(stack)
        store, finding = self._finding(stack)
        verify_request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger)
        verifier = C1AVerifier(stack.runtime, stack.ledger, store)
        verified = verifier.verify_independent(
            verify_request, stack.mission, expected_result_hash="test-hash")
        current = store.get(FINDING_ID)
        falsify_request = build_verification_request(
            mission=stack.mission, finding=current,
            original_execution=verified.verification_execution,
            ledger=stack.ledger, purpose="falsify")
        falsifier = C1AFalsifier(stack.runtime, stack.ledger, store)
        result = falsifier.challenge_independent(
            falsify_request, stack.mission, expected_result_hash="test-hash")
        self.assertIs(result.classification,
                      FalsificationClassification.NOT_DISPROVED)
        self.assertFalse(result.transition_applied)
        self.assertIs(store.get(FINDING_ID).state, FindingState.VERIFIED)

    def test_falsification_result_cannot_be_forged(self):
        stack = self._stack()
        _, original = self._original(stack)
        with self.assertRaises(Exception):
            FalsificationResult(
                result_id="FRS-forged",
                classification=FalsificationClassification.DISPROVED,
                verification_request_ref="VR-x",
                falsification_execution=original,
                finding_id=FINDING_ID, mission_id=MISSION_ID,
                independence=evaluate_independence(
                    request=None, verification=original, provider_result={}),
                lineage=validate_lineage(
                    request=None, verification=original, provider_result={}),
                observation={})

    # Test 18 (D4-I18)
    def test_falsification_evidence_must_belong_to_own_execution(self):
        stack = self._stack()
        rt, original = self._original(stack)
        pr = rt.execution.evidence["provider_result"]
        store, finding = self._finding(stack, state=FindingState.VERIFIED)
        request = build_verification_request(
            mission=stack.mission, finding=finding,
            original_execution=original, ledger=stack.ledger,
            purpose="falsify")
        falsifier = C1AFalsifier(stack.runtime, stack.ledger, store)  # noqa: F841
        # Reusing the original execution as the falsification execution must
        # not produce DISPROVED (no distinct execution).
        checks = evaluate_independence(
            request=request, verification=original, provider_result=pr)
        self.assertFalse(checks.distinct_execution)
        self.assertFalse(checks.all_passed)


class QualityGateD4(_Base):
    # Test 21
    def test_falsification_cannot_create_complete(self):
        stack = self._stack()
        gate = BOBQualityGate(stack.ledger)
        finding = Finding(
            finding_id=FINDING_ID, state=FindingState.REFUTED,
            summary="refuted", target=str(stack.fixture), mission_id=MISSION_ID)
        evaluation = gate.evaluate(GateInputs(
            mission=stack.mission, findings=[finding],
            regression_ok=False, behavior_probe_ok=False))
        self.assertNotIn("COMPLETE", evaluation.verdict.value.upper())
        self.assertIn("G:finding-state", evaluation.failed)

    # Test 22, AE
    def test_quality_gate_rejects_invalid_verification_chain(self):
        stack = self._stack()
        from raphael_ibm_bob.evidence_ledger import digest_id
        payload = {
            "kind": "verification-result",
            "finding_id": FINDING_ID,
            "mission_id": MISSION_ID,
            "supported": False,
            "independence": {"all_passed": False},
            "lineage": {"valid": False},
        }
        stack.ledger.append_evidence(
            evidence_id=digest_id(payload, prefix="VR"),
            producer="verifier", request_seq=0, decision_seq=0,
            result_seq=None, payload=payload, finding_id=FINDING_ID)
        finding = Finding(
            finding_id=FINDING_ID, state=FindingState.VERIFIED,
            summary="verified", target=str(stack.fixture), mission_id=MISSION_ID)
        gate = BOBQualityGate(stack.ledger)
        evaluation = gate.evaluate(GateInputs(
            mission=stack.mission, findings=[finding],
            regression_ok=False, behavior_probe_ok=False))
        self.assertIn("G:finding-state", evaluation.failed)

    def test_quality_gate_accepts_valid_verification_chain(self):
        stack = self._stack()
        from raphael_ibm_bob.evidence_ledger import digest_id
        payload = {
            "kind": "verification-result",
            "finding_id": FINDING_ID,
            "mission_id": MISSION_ID,
            "supported": True,
            "independence": {"all_passed": True},
            "lineage": {"valid": True},
        }
        stack.ledger.append_evidence(
            evidence_id=digest_id(payload, prefix="VR"),
            producer="verifier", request_seq=0, decision_seq=0,
            result_seq=None, payload=payload, finding_id=FINDING_ID)
        finding = Finding(
            finding_id=FINDING_ID, state=FindingState.VERIFIED,
            summary="verified", target=str(stack.fixture), mission_id=MISSION_ID)
        gate = BOBQualityGate(stack.ledger)
        evaluation = gate.evaluate(GateInputs(
            mission=stack.mission, findings=[finding],
            regression_ok=False, behavior_probe_ok=False))
        self.assertIn("G:finding-state", evaluation.passed)


class ReplannerD4(_Base):
    # Test 23
    def test_replanner_rejects_unrelated_evidence(self):
        from raphael_ibm_bob.contracts import (
            EvidenceReceipt, FocusedContext, Plan,
        )
        from raphael_ibm_bob.replanner import Replanner

        stack = self._stack()
        store, finding = self._finding(stack)
        finding = store.get(FINDING_ID)
        # Force REFUTED so the replanner accepts the lifecycle precondition.
        store.transition(FINDING_ID, FindingState.REFUTED)
        refuted = store.get(FINDING_ID)
        bad_evidence = EvidenceReceipt(
            evidence_id="E-x", sequence=1, producer="falsifier",
            payload={"payload": {"kind": "counter-example",
                                 "finding_id": "F-other"}})
        ctx = FocusedContext(
            refuted_claim=refuted, diagnostic_evidence=[bad_evidence],
            mission_scope=stack.mission.scope)
        plan = Plan(plan_id="P-a", mission_id=MISSION_ID, steps=[])
        replanner = Replanner(store, stack.ledger)
        with self.assertRaises(ValueError):
            replanner.replan(ctx, plan)

    def test_replanner_rejects_failed_independence_evidence(self):
        from raphael_ibm_bob.contracts import (
            EvidenceReceipt, FocusedContext, Plan,
        )
        from raphael_ibm_bob.replanner import Replanner

        stack = self._stack()
        store, finding = self._finding(stack)
        store.transition(FINDING_ID, FindingState.REFUTED)
        refuted = store.get(FINDING_ID)
        bad_evidence = EvidenceReceipt(
            evidence_id="E-y", sequence=1, producer="verifier",
            payload={"payload": {
                "kind": "verification-result",
                "finding_id": FINDING_ID,
                "independence": {"all_passed": False},
                "lineage": {"valid": False}}})
        ctx = FocusedContext(
            refuted_claim=refuted, diagnostic_evidence=[bad_evidence],
            mission_scope=stack.mission.scope)
        plan = Plan(plan_id="P-a", mission_id=MISSION_ID, steps=[])
        replanner = Replanner(store, stack.ledger)
        with self.assertRaises(ValueError):
            replanner.replan(ctx, plan)


if __name__ == "__main__":
    unittest.main()
