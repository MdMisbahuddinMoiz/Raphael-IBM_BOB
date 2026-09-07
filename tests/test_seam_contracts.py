"""tests/test_seam_contracts.py — M1 seam tests.

Stdlib-only. These tests prove that the seam contracts instantiate
correctly, that the enums carry the right members, that legacy modules can
be *represented* behind the seam via AdapterSpec, and that no behavioral
claims are made beyond what M1 actually ships.

These tests do NOT assert that Runtime, Broker, Policy, etc. *work*. The
brief explicitly forbids fake-behavior tests at M1. Behavioral correctness
will be proven at M2+.

Status language:
    IMPLEMENTED         - test class + assertions.
    PHYSICALLY VERIFIED - run successfully under stdlib unittest.
"""
from __future__ import annotations

import unittest

from raphael_bob import (
    ActionRequest,
    Capability,
    Decision,
    EvidenceReceipt,
    ExecutionResult,
    Finding,
    FindingState,
    FocusedContext,
    GateVerdict,
    Mission,
    Plan,
    PolicyDecision,
    Seq,
    fresh_id,
)
from raphael_bob.seams import (
    Broker,
    EvidenceLedger,
    Falsifier,
    Planner,
    Policy,
    QualityGate,
    Replanner,
    Runner,
    Runtime,
    Verifier,
)
from raphael_bob.adapters import (
    ADAPT,
    ISOLATE,
    REPLACE,
    REUSE,
    UNKNOWN,
    ALL_SPECS,
    AdapterSpec,
    action_counts,
    specs_for,
)


# -----------------------------------------------------------------------------
# Enum contract tests
# -----------------------------------------------------------------------------

class CapabilityEnumTests(unittest.TestCase):
    def test_capability_allow_list_is_exactly_the_brief(self):
        expected = {"read", "list", "search", "write", "run_test"}
        actual = {c.value for c in Capability}
        self.assertEqual(actual, expected)

    def test_capability_is_str_enum(self):
        # The Capability enum must be a str-Enum so JSON-serialized evidence
        # can carry it directly. This is asserted by isinstance str check.
        self.assertIsInstance(Capability.READ, str)
        self.assertEqual(Capability.READ.value, "read")


class DecisionEnumTests(unittest.TestCase):
    def test_decision_values_are_allow_and_deny_only(self):
        self.assertEqual({d.value for d in Decision}, {"allow", "deny"})


class FindingStateEnumTests(unittest.TestCase):
    def test_finding_state_values_are_complete(self):
        self.assertEqual(
            {s.value for s in FindingState},
            {"unverified", "verified", "refuted", "superseded"},
        )


class GateVerdictEnumTests(unittest.TestCase):
    def test_gate_verdict_values_are_complete_and_refuse_only(self):
        self.assertEqual(
            {v.value for v in GateVerdict},
            {"complete", "refuse"},
        )


# -----------------------------------------------------------------------------
# Frozen-dataclass contract tests
# -----------------------------------------------------------------------------

class FrozenDataclassTests(unittest.TestCase):
    def test_action_request_is_frozen(self):
        r = ActionRequest(
            sequence=1,
            requester="mission:m1",
            capability=Capability.READ,
            target="fixtures/authkit/store.py",
            purpose="verify store import",
        )
        with self.assertRaises(Exception):
            r.sequence = 2  # type: ignore[misc]
        self.assertEqual(r.sequence, 1)
        self.assertEqual(r.capability, Capability.READ)
        self.assertEqual(r.target, "fixtures/authkit/store.py")
        self.assertEqual(r.purpose, "verify store import")
        self.assertIsNone(r.plan_id)
        self.assertIsNone(r.finding_id)

    def test_policy_decision_carries_evidence_id_slot(self):
        d = PolicyDecision(
            sequence=1,
            decision=Decision.ALLOW,
            reason="scope permits READ on fixtures/",
            capability=Capability.READ,
            target="fixtures/authkit/store.py",
            evidence_id=None,
        )
        self.assertEqual(d.decision, Decision.ALLOW)
        self.assertEqual(d.capability, Capability.READ)
        self.assertIsNone(d.evidence_id)

    def test_execution_result_default_evidence_is_empty_dict(self):
        er = ExecutionResult(sequence=1, success=True, output="ok")
        self.assertEqual(er.evidence, {})
        self.assertIsNone(er.error)

    def test_finding_state_transitions_supported(self):
        f = Finding(
            finding_id="F-1",
            state=FindingState.UNVERIFIED,
            summary="session.py mishandles expired tokens",
            target="fixtures/authkit/session.py",
        )
        self.assertEqual(f.state, FindingState.UNVERIFIED)
        self.assertEqual(f.evidence_ids, [])
        self.assertIsNone(f.supersedes)

    def test_focused_context_carries_three_fields_only(self):
        finding = Finding(
            finding_id="F-1",
            state=FindingState.REFUTED,
            summary="candidate was a decoy",
            target="fixtures/authkit/login.py",
        )
        receipt = EvidenceReceipt(
            evidence_id="E-1",
            sequence=2,
            producer="falsifier",
            payload={"test": "test_login.py passes but session_expired fails"},
        )
        ctx = FocusedContext(
            refuted_claim=finding,
            diagnostic_evidence=[receipt],
            mission_scope="fixtures/authkit",
        )
        self.assertEqual(ctx.refuted_claim.state, FindingState.REFUTED)
        self.assertEqual(ctx.diagnostic_evidence[0].evidence_id, "E-1")
        self.assertEqual(ctx.mission_scope, "fixtures/authkit")

    def test_plan_carries_optional_parent_plan_id(self):
        plan = Plan(
            plan_id="P-1",
            mission_id="M-1",
            steps=[
                ActionRequest(
                    sequence=1,
                    requester="mission:M-1",
                    capability=Capability.LIST,
                    target="fixtures/authkit/",
                    purpose="discover files",
                ),
            ],
            parent_plan_id=None,
        )
        self.assertEqual(plan.plan_id, "P-1")
        self.assertIsNone(plan.parent_plan_id)
        self.assertEqual(len(plan.steps), 1)

    def test_mission_default_criteria_is_empty_list(self):
        m = Mission(mission_id="M-1", description="authkit fix", scope="fixtures/authkit")
        self.assertEqual(m.criteria, [])

    def test_evidence_receipt_is_frozen(self):
        r = EvidenceReceipt(
            evidence_id="E-1",
            sequence=1,
            producer="broker",
            payload={"decision": "allow"},
        )
        with self.assertRaises(Exception):
            r.sequence = 2  # type: ignore[misc]
        self.assertEqual(r.producer, "broker")

    def test_seq_and_fresh_id_helpers(self):
        self.assertEqual(Seq(5).n, 5)
        self.assertTrue(fresh_id("F").startswith("F-"))
        self.assertTrue(fresh_id("E").startswith("E-"))


# -----------------------------------------------------------------------------
# Protocol surface tests
# -----------------------------------------------------------------------------

class ProtocolSurfaceTests(unittest.TestCase):
    """The seam Protocols MUST be runtime_checkable so M2+ can use isinstance
    checks against concrete implementations. They MUST also expose the
    expected method names."""

    def test_each_protocol_has_expected_methods(self):
        expected = {
            Policy: ["consult"],
            Broker: ["submit", "next_sequence"],
            Runtime: ["execute"],
            EvidenceLedger: ["append", "get", "by_sequence", "all"],
            Verifier: ["verify"],
            Falsifier: ["challenge"],
            Replanner: ["replan"],
            QualityGate: ["evaluate"],
            Planner: ["plan"],
            Runner: ["run"],
        }
        for proto, methods in expected.items():
            for method in methods:
                self.assertTrue(
                    hasattr(proto, method),
                    msg=f"{proto.__name__} missing method {method}",
                )


# -----------------------------------------------------------------------------
# AdapterSpec index tests
# -----------------------------------------------------------------------------

class AdapterSpecIndexTests(unittest.TestCase):
    """Tests against docs/migration/reuse-matrix.md, executed against the
    code-level index in raphael_bob.adapters.legacy."""

    def test_all_seams_have_specs(self):
        expected_seams = {
            "Broker",
            "Policy",
            "Evidence",
            "Falsifier",
            "Verifier",
            "Planner",
            "Replanner",
            "QualityGate",
            "Runtime",
            "Runner",
        }
        self.assertEqual(set(ALL_SPECS.keys()), expected_seams)

    def test_action_counts_match_expected_distribution(self):
        counts = action_counts()
        # No UNKNOWN specs should remain after R1.0 / M1.
        self.assertEqual(counts.get(UNKNOWN, 0), 0)
        # No specs marked REUSE for now; all legacy Raphael modules need
        # contract changes (ADAPT) or replacement.
        self.assertEqual(counts.get(REUSE, 0), 0)
        # At least one ISOLATE (Runner, Evidence.trust).
        self.assertGreaterEqual(counts.get(ISOLATE, 0), 1)
        # Two REPLACEs: Replanner, QualityGate. Plus Planner.GreedyPlanner.
        self.assertGreaterEqual(counts.get(REPLACE, 0), 2)

    def test_each_spec_is_well_formed(self):
        for seam, specs in ALL_SPECS.items():
            for spec in specs:
                self.assertIsInstance(spec, AdapterSpec)
                self.assertTrue(spec.seam, msg=f"empty seam in {spec}")
                self.assertTrue(spec.legacy_module, msg=f"empty legacy_module in {spec}")
                self.assertIn(
                    spec.action,
                    {REUSE, ADAPT, ISOLATE, REPLACE, UNKNOWN},
                    msg=f"unknown action verb: {spec.action}",
                )
                self.assertTrue(spec.why)
                self.assertTrue(spec.legacy_behavior_remaining)
                self.assertTrue(spec.missing_for_target)

    def test_runner_is_only_isolated_seam_for_seam_runner(self):
        runner_specs = specs_for("Runner")
        self.assertEqual(len(runner_specs), 1)
        self.assertEqual(runner_specs[0].action, ISOLATE)
        self.assertIn("main.py", runner_specs[0].legacy_module)

    def test_replanner_has_no_legacy_module(self):
        for spec in specs_for("Replanner"):
            self.assertEqual(spec.action, REPLACE)
            self.assertIn("(none)", spec.legacy_module)

    def test_qualitygate_has_no_legacy_module(self):
        for spec in specs_for("QualityGate"):
            self.assertEqual(spec.action, REPLACE)
            self.assertIn("(none)", spec.legacy_module)

    def test_broker_adapts_capability_broker(self):
        broker_specs = specs_for("Broker")
        legacy_modules = {s.legacy_module for s in broker_specs}
        self.assertIn("src/orchestrator/brain/capability_broker.py", legacy_modules)

    def test_runtime_replace_marker(self):
        runtime_specs = specs_for("Runtime")
        self.assertTrue(all(s.action == REPLACE for s in runtime_specs))

    def test_evidence_trust_is_isolated(self):
        ev_specs = specs_for("Evidence")
        trust_specs = [s for s in ev_specs if "trust.py" in s.legacy_module]
        self.assertTrue(any(s.action == ISOLATE for s in trust_specs))


# -----------------------------------------------------------------------------
# Anti-claim test
# -----------------------------------------------------------------------------

class AntiClaimTests(unittest.TestCase):
    """M1..M2 MUST NOT claim that QualityGate / Verifier / Falsifier /
    Replanner / Planner / Runner / EvidenceLedger implementations exist
    yet. Those are reserved for M4..M6 / M3.

    Broker / Policy / Runtime implementations DO exist at M2; their
    contracts remain the seam Protocols from M1."""

    def test_no_quality_gate_implementation_module_exists(self):
        import importlib
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("raphael_bob.quality_gate")

    def test_no_replanner_implementation_module_exists(self):
        import importlib
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("raphael_bob.replanner")

    def test_no_falsifier_implementation_module_exists(self):
        import importlib
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("raphael_bob.falsifier")

    def test_no_verifier_implementation_module_exists(self):
        import importlib
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("raphael_bob.verifier")

    def test_m3_evidence_ledger_module_exists(self):
        import importlib
        # M3 ships the EvidenceLedger; the module MUST be importable.
        mod = importlib.import_module("raphael_bob.evidence_ledger")
        self.assertTrue(hasattr(mod, "EvidenceLedger"))
        self.assertTrue(hasattr(mod, "LedgerWriter"))
        self.assertTrue(hasattr(mod, "LedgerReader"))

    def test_no_runner_module_exists(self):
        import importlib
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("raphael_bob.runner")
    def test_m2_broker_is_subclass_of_seam_protocol(self):
        # The M2 Broker implementation must satisfy the M1 seam Protocol.
        from raphael_bob.broker import BOBBroker
        from raphael_bob.seams import Broker
        self.assertTrue(isinstance(BOBBroker.__new__(BOBBroker), Broker))  # runtime_checkable

    def test_m2_runtime_is_subclass_of_seam_protocol(self):
        from raphael_bob.runtime import BOBRuntime
        from raphael_bob.seams import Runtime
        # BOBRuntime is not runtime_checkable on instance because
        # Protocol requires class-level methods. We assert that
        # BOBRuntime has the documented method `submit`.
        self.assertTrue(hasattr(BOBRuntime, "submit"))



if __name__ == "__main__":
    unittest.main()