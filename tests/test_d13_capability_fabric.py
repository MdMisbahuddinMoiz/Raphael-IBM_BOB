"""tests.test_d13_capability_fabric — D13 registry-driven capability fabric.

Proves:
  * the registry is the single declaration index (discovery, prerequisites,
    deterministic selection/composition) with ZERO target-specific branches;
  * credential provenance never lets plaintext reach evidence and never
    allows cross-target reuse;
  * observation provenance generalizes the stale-prompt defect guard;
  * the fabric holds NO authority (no broker/policy/runtime imports, no
    process/network primitives), and the governed bridge emits ordinary
    ActionRequests into the EXISTING Runtime -> Broker -> Policy path;
  * adding SSH is descriptor-only and fails closed on execution.
"""
from __future__ import annotations

import dataclasses
import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.capability_bootstrap import (
    InertAdapter,
    MediatedAdapter,
    bind_governed_adapters,
    network_descriptors,
    register_default,
    register_ssh,
    ssh_descriptor,
)
from raphael_ibm_bob.capability_prerequisites import PrerequisiteEngine
from raphael_ibm_bob.capability_registry import (
    AdapterNotBoundError,
    CapabilityDescriptor,
    CapabilityRegistry,
    PrerequisiteSpec,
)
from raphael_ibm_bob.capability_selector import (
    CapabilitySelector,
    ExecutionPlan,
    plan_to_action_requests,
)
from raphael_ibm_bob.contracts import Capability, Mission
from raphael_ibm_bob.credential_provenance import (
    CredentialProvenance,
    CredentialState,
    CredentialVault,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.observation_model import (
    ObservationBuilder,
    ProvenanceValidator,
)
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.target_service_model import (
    AuthorizationScope,
    ServiceRecord,
    TargetFacts,
    TargetServiceModel,
)
from raphael_ibm_bob.workspace import Workspace

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "raphael_ibm_bob"
D13_MODULES = (
    "capability_registry.py",
    "target_service_model.py",
    "capability_prerequisites.py",
    "credential_provenance.py",
    "capability_selector.py",
    "observation_model.py",
    "capability_bootstrap.py",
)


def _facts_with_http(host="10.0.0.5", authorized=True):
    facts = TargetFacts(target_id=f"target_{host}", host=host)
    facts.add_service(ServiceRecord(host=host, port=80, protocol="http"))
    if authorized:
        facts.authorization = AuthorizationScope(
            target_host=host,
            authorized_protocols=frozenset(["http", "telnet"]),
            authorized_ports=frozenset([80, 23]),
            engagement_id="E-1",
            scope_document_ref="scope://signed/1",
        )
    return facts


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="d13_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        (self.ws / "src").mkdir(parents=True)
        (self.ws / "src" / "cand.txt").write_text("OK\n", encoding="utf-8")

    def mission(self, scope="src/"):
        return Mission(mission_id="M-d13", description="d13", scope=scope,
                       criteria=["c"],
                       problem={"symptom_target": "src/cand.txt"})

    def _stack(self):
        run_dir = self.base / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        workspace = Workspace(self.ws)
        ledger = EvidenceLedger(run_dir)
        broker = BOBBroker(BOBPolicy(workspace), workspace, ledger=ledger)
        return BOBRuntime(broker), ledger


class RegistryTests(_Case):
    def test_register_and_get(self):
        reg = CapabilityRegistry()
        reg.register(network_descriptors()[0], InertAdapter())
        desc = reg.get("NETWORK_HTTP_REQUEST")
        self.assertEqual(desc.protocol, "http")
        self.assertTrue(reg.has("NETWORK_HTTP_REQUEST"))

    def test_duplicate_registration_rejected(self):
        reg = CapabilityRegistry()
        reg.register(network_descriptors()[0], InertAdapter())
        with self.assertRaises(ValueError):
            reg.register(network_descriptors()[0], InertAdapter())

    def test_unknown_capability_fails_explicitly(self):
        reg = CapabilityRegistry()
        with self.assertRaises(KeyError):
            reg.get("NOPE")

    def test_prerequisites_must_be_frozenset(self):
        reg = CapabilityRegistry()
        bad = dataclasses.replace(network_descriptors()[0],
                                  prerequisites=[])
        with self.assertRaises(TypeError):
            reg.register(bad, InertAdapter())

    def test_discovery_is_protocol_driven(self):
        reg = CapabilityRegistry()
        register_default(reg)
        register_ssh(reg)
        found = {d.capability_id
                 for d in reg.discover_for_target(
                     _facts_with_http().to_facts())}
        self.assertEqual(found, {"NETWORK_HTTP_REQUEST"})

    def test_discovery_ignores_closed_services(self):
        reg = CapabilityRegistry()
        register_default(reg)
        facts = _facts_with_http()
        facts.services[0] = dataclasses.replace(facts.services[0],
                                                state="closed")
        self.assertEqual(reg.discover_for_target(facts.to_facts()), [])

    def test_inert_adapter_fails_closed(self):
        reg = CapabilityRegistry()
        register_default(reg)
        with self.assertRaises(AdapterNotBoundError):
            reg.get_adapter("NETWORK_HTTP_REQUEST").execute({}, [], {})

    def test_bind_adapter_replaces_and_fails_on_unknown(self):
        reg = CapabilityRegistry()
        register_default(reg)
        with self.assertRaises(KeyError):
            reg.bind_adapter("NOPE", InertAdapter())

        class _Spy:
            def execute(self, target_facts, credentials, mission_params):
                return {"ok": True}

        reg.bind_adapter("NETWORK_HTTP_REQUEST", _Spy())
        self.assertEqual(
            reg.get_adapter("NETWORK_HTTP_REQUEST").execute({}, [], {}),
            {"ok": True})

    def test_registration_log_is_audit_trail(self):
        reg = CapabilityRegistry()
        register_default(reg)
        log = reg.registration_log()
        self.assertEqual(len(log), 2)
        self.assertEqual({e["capability_id"] for e in log},
                         {"NETWORK_HTTP_REQUEST", "NETWORK_TELNET_SESSION"})


class TargetModelTests(_Case):
    def test_from_manual_and_dedupe(self):
        facts = TargetServiceModel.from_manual("h", 23, "telnet")
        facts.add_service(ServiceRecord(host="h", port=23, protocol="telnet"))
        self.assertEqual(len(facts.services), 1)
        self.assertIsNotNone(facts.get_service("telnet"))

    def test_from_nmap_parses_open_tcp(self):
        output = (
            "22/tcp   open  ssh     OpenSSH 8.9\n"
            "23/tcp   open  telnet  Linux telnetd\n"
            "80/tcp   closed http\n"
        )
        facts = TargetServiceModel.from_nmap(output, "10.0.0.5")
        protocols = {s.protocol for s in facts.services}
        self.assertEqual(protocols, {"ssh", "telnet"})
        self.assertIsNone(facts.get_service("http"))

    def test_is_authorized_for_is_descriptive_only(self):
        facts = _facts_with_http()
        self.assertTrue(facts.is_authorized_for("http", 80))
        self.assertFalse(facts.is_authorized_for("http", 8080))
        bare = _facts_with_http(authorized=False)
        self.assertFalse(bare.is_authorized_for("http", 80))


class PrerequisiteTests(_Case):
    def setUp(self):
        super().setUp()
        self.engine = PrerequisiteEngine()
        self.http = network_descriptors()[0]
        self.telnet = network_descriptors()[1]

    def test_service_and_authorization_satisfied(self):
        result = self.engine.evaluate(self.http, _facts_with_http())
        self.assertTrue(result.satisfied, result.missing)

    def test_missing_authorization_fails(self):
        result = self.engine.evaluate(self.http,
                                      _facts_with_http(authorized=False))
        self.assertFalse(result.satisfied)
        self.assertTrue(any("authorization" in m for m in result.missing))

    def test_credential_predicate(self):
        facts = TargetFacts(target_id="t", host="h")
        facts.add_service(ServiceRecord(host="h", port=23, protocol="telnet"))
        facts.authorization = AuthorizationScope(
            target_host="h", authorized_protocols=frozenset(["telnet"]),
            authorized_ports=frozenset([23]), engagement_id="E",
            scope_document_ref="s")
        without = self.engine.evaluate(self.telnet, facts, [])
        self.assertFalse(without.satisfied)
        with_cred = self.engine.evaluate(
            self.telnet, facts, ["telnet_root_blank"])
        self.assertTrue(with_cred.satisfied, with_cred.missing)

    def test_unknown_prerequisite_kind_fails_closed(self):
        desc = CapabilityDescriptor(
            capability_id="X", protocol="x", description="d",
            prerequisites=frozenset([PrerequisiteSpec(kind="bogus",
                                                      predicate="p")]),
            authorization_scope="x", evidence_schema="x",
            execution_adapter="x", verifier_binding=None,
            falsifier_binding=None, mission_types=frozenset(["m"]))
        result = self.engine.evaluate(desc, TargetFacts("t", "h"))
        self.assertFalse(result.satisfied)


class CredentialTests(_Case):
    def test_evidence_never_contains_plaintext(self):
        vault = CredentialVault()
        ref = vault.store("telnet_root_blank", "sup3r-s3cret!", "10.0.0.5",
                          CredentialProvenance.DEFAULT_CREDENTIAL)
        blob = repr(ref.to_evidence_dict())
        self.assertNotIn("sup3r-s3cret!", blob)
        self.assertEqual(vault.retrieve(ref.credential_id), "sup3r-s3cret!")
        self.assertNotIn("sup3r-s3cret!", repr(ref))

    def test_cross_target_reuse_denied(self):
        vault = CredentialVault()
        ref = vault.store("ssh_password", "p", "A",
                          CredentialProvenance.PROVIDED)
        vault.mark_validated(ref.credential_id, "A", "ssh")
        self.assertTrue(vault.is_authorized_for(ref.credential_id, "A", "ssh"))
        self.assertFalse(vault.is_authorized_for(ref.credential_id, "B", "ssh"))

    def test_revoke_and_wipe(self):
        vault = CredentialVault()
        ref = vault.store("ssh_password", "p", "A",
                          CredentialProvenance.PROVIDED)
        vault.wipe()
        self.assertIsNone(vault.retrieve(ref.credential_id))
        ref2 = vault.store("ssh_password", "q", "A",
                           CredentialProvenance.PROVIDED)
        vault.mark_validated(ref2.credential_id, "A", "ssh")
        vault.revoke(ref2.credential_id)
        self.assertEqual(vault.get_reference(ref2.credential_id).state,
                         CredentialState.REVOKED)
        self.assertFalse(vault.is_authorized_for(ref2.credential_id, "A", "ssh"))

    def test_authorize_requires_validation(self):
        vault = CredentialVault()
        ref = vault.store("ssh_password", "p", "A",
                          CredentialProvenance.PROVIDED)
        vault.authorize(ref.credential_id, "A", "ssh")
        # Not yet validated -> authorize does not upgrade state.
        self.assertFalse(vault.is_authorized_for(ref.credential_id, "A", "ssh"))
        vault.mark_validated(ref.credential_id, "A", "ssh")
        vault.authorize(ref.credential_id, "A", "ssh")
        self.assertTrue(vault.is_authorized_for(ref.credential_id, "A", "ssh"))


class ObservationTests(_Case):
    def test_from_capability_output_hashes_content(self):
        import hashlib
        rec = ObservationBuilder.from_capability_output(
            "NETWORK_HTTP_REQUEST", "hello", "h")
        self.assertEqual(rec.content_hash,
                         hashlib.sha256(b"hello").hexdigest())
        self.assertEqual(rec.to_evidence_dict()["observation_type"],
                         "network_response")

    def test_freshness_guard(self):
        rec = ObservationBuilder.from_flag_capture(
            "NETWORK_TELNET_SESSION", "FLAG{x}", "h",
            command="cat flag", session_id="s1")
        ok, _ = ProvenanceValidator.validate_fresh(rec, "s1")
        self.assertTrue(ok)
        bad, why = ProvenanceValidator.validate_fresh(rec, "s2")
        self.assertFalse(bad)
        self.assertIn("session mismatch", why)
        stale = dataclasses.replace(rec, timestamp=0.0)
        bad, why = ProvenanceValidator.validate_fresh(stale, "s1")
        self.assertFalse(bad)
        self.assertIn("stale", why)

    def test_command_binding_guard(self):
        rec = ObservationBuilder.from_flag_capture(
            "NETWORK_TELNET_SESSION", "FLAG{x}", "h",
            command="cat flag", session_id="s1")
        ok, _ = ProvenanceValidator.validate_command_binding(rec, "cat flag")
        self.assertTrue(ok)
        bad, why = ProvenanceValidator.validate_command_binding(rec, "cat /etc/passwd")
        self.assertFalse(bad)
        self.assertIn("command mismatch", why)


class SelectorTests(_Case):
    def setUp(self):
        super().setUp()
        self.reg = CapabilityRegistry()
        register_default(self.reg)
        self.selector = CapabilitySelector(self.reg, PrerequisiteEngine())

    def test_composes_ready_capability(self):
        plan = self.selector.select_and_compose(
            "web_enum", {"mission_id": "M"}, _facts_with_http())
        self.assertEqual([s.capability_id for s in plan.steps],
                         ["NETWORK_HTTP_REQUEST"])
        self.assertEqual(plan.steps[0].params["target"],
                         "http://10.0.0.5:80")

    def test_plan_id_is_deterministic(self):
        a = self.selector.select_and_compose(
            "web_enum", {"mission_id": "M"}, _facts_with_http())
        b = CapabilitySelector(self.reg).select_and_compose(
            "web_enum", {"mission_id": "M"}, _facts_with_http())
        self.assertEqual(a.plan_id, b.plan_id)
        self.assertTrue(a.plan_id.startswith("DP-"))

    def test_unsatisfied_capability_is_not_composed(self):
        # telnet service present + authorized, but no credential -> not ready.
        facts = TargetFacts(target_id="t", host="h")
        facts.add_service(ServiceRecord(host="h", port=23, protocol="telnet"))
        facts.authorization = AuthorizationScope(
            target_host="h", authorized_protocols=frozenset(["telnet"]),
            authorized_ports=frozenset([23]), engagement_id="E",
            scope_document_ref="s")
        plan = self.selector.select_and_compose(
            "flag_capture", {"mission_id": "M"}, facts)
        self.assertEqual([s.capability_id for s in plan.steps], [])

    def test_replan_uses_recorded_mission_type(self):
        plan = self.selector.select_and_compose(
            "web_enum", {"mission_id": "M"}, _facts_with_http())
        facts2 = _facts_with_http()
        replanned = self.selector.replan(plan, facts2, [])
        self.assertEqual(replanned.mission_type, "web_enum")

    def test_no_target_specific_branches_in_source(self):
        src = (PKG / "capability_selector.py").read_text("utf-8")
        for token in ("target ==", "== target", "10.129.", "10.0.0"):
            self.assertNotIn(token, src, token)


class SshProofTests(_Case):
    def test_registering_ssh_adds_a_third_capability(self):
        reg = CapabilityRegistry()
        register_default(reg)
        self.assertEqual({d.capability_id for d in reg.all_capabilities()},
                         {"NETWORK_HTTP_REQUEST", "NETWORK_TELNET_SESSION"})
        register_ssh(reg)
        ids = {d.capability_id for d in reg.all_capabilities()}
        self.assertEqual(ids, {"NETWORK_HTTP_REQUEST",
                               "NETWORK_TELNET_SESSION",
                               "NETWORK_SSH_SESSION"})

    def test_ssh_is_discovered_from_facts(self):
        reg = CapabilityRegistry()
        register_default(reg)
        register_ssh(reg)
        facts = TargetFacts(target_id="t", host="h")
        facts.add_service(ServiceRecord(host="h", port=22, protocol="ssh"))
        found = reg.discover_for_target(facts.to_facts())
        self.assertEqual([d.capability_id for d in found],
                         ["NETWORK_SSH_SESSION"])

    def test_ssh_execution_fails_closed(self):
        reg = CapabilityRegistry()
        register_ssh(reg)
        with self.assertRaises(AdapterNotBoundError):
            reg.get_adapter("NETWORK_SSH_SESSION").execute({}, [], {})

    def test_ssh_has_no_governed_enum_binding(self):
        plan = ExecutionPlan(plan_id="DP-x", mission_id="M", target_id="t")
        plan.add_step("NETWORK_SSH_SESSION", {"target": "ssh://h:22"})
        with self.assertRaises(ValueError):
            plan_to_action_requests(plan)


class GovernedBridgeTests(_Case):
    def test_plan_to_action_requests_emits_ordinary_requests(self):
        plan = ExecutionPlan(plan_id="DP-1", mission_id="M-d13",
                             target_id="ws")
        plan.add_step("READ", {"target": "src/cand.txt"},
                      purpose="inspect")
        requests = plan_to_action_requests(plan)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].capability, Capability.READ)
        self.assertEqual(requests[0].target, "src/cand.txt")

    def test_bridge_allow_path_executes(self):
        plan = ExecutionPlan(plan_id="DP-1", mission_id="M-d13",
                             target_id="ws")
        plan.add_step("READ", {"target": "src/cand.txt"}, purpose="inspect")
        runtime, ledger = self._stack()
        result = runtime.submit(plan_to_action_requests(plan)[0],
                                self.mission())
        self.assertEqual(result.broker_result.decision.decision.value, "allow")
        self.assertTrue(result.execution.success)
        ledger.close()

    def test_bridge_deny_path_stays_deny(self):
        plan = ExecutionPlan(plan_id="DP-2", mission_id="M-d13",
                             target_id="ws")
        plan.add_step("READ", {"target": "/etc/hostname"}, purpose="escape")
        runtime, ledger = self._stack()
        result = runtime.submit(plan_to_action_requests(plan)[0],
                                self.mission())
        self.assertEqual(result.broker_result.decision.decision.value, "deny")
        self.assertIsNone(result.execution)
        ledger.close()

    def test_mediated_adapter_routes_through_runtime(self):
        runtime, ledger = self._stack()
        adapter = MediatedAdapter(Capability.READ, runtime, self.mission())
        observation = adapter.execute({"host": "ws"}, [],
                                      {"target": "src/cand.txt"})
        self.assertEqual(observation["capability_id"], "READ")
        self.assertEqual(observation["observation_type"], "network_response")
        denied = adapter.execute({"host": "ws"}, [],
                                 {"target": "/etc/hostname"})
        self.assertFalse(denied["executed"])
        self.assertEqual(denied["decision"], "deny")
        ledger.close()

    def test_bind_governed_adapters_bridges_registered_caps(self):
        reg = CapabilityRegistry()
        register_default(reg)
        runtime, ledger = self._stack()
        bind_governed_adapters(reg, runtime, self.mission(),
                               capability_ids=["NETWORK_HTTP_REQUEST"])
        # HTTP has a governed enum; binding replaces the inert adapter.
        self.assertNotIsInstance(reg.get_adapter("NETWORK_HTTP_REQUEST"),
                                 InertAdapter)
        ledger.close()


class GovernanceScan(unittest.TestCase):
    FORBIDDEN = (
        "BOBBroker", "BOBPolicy", "BOBRuntime", "BOBQualityGate",
        "execute_capability(", "import subprocess", "import socket",
        "import urllib", "urlopen",
        "from raphael_ibm_bob.broker", "from raphael_ibm_bob.policy",
        "from raphael_ibm_bob.runtime", "from raphael_ibm_bob.quality_gate",
        "from raphael_ibm_bob.capabilities",
    )

    def test_d13_modules_hold_no_authority(self):
        for name in D13_MODULES:
            src = (PKG / name).read_text("utf-8")
            for token in self.FORBIDDEN:
                self.assertNotIn(token, src, f"{token} in {name}")

    def test_registry_has_no_global_self_registration(self):
        # Importing the module must not register anything.
        reg = CapabilityRegistry()
        self.assertEqual(reg.all_capabilities(), [])


if __name__ == "__main__":
    unittest.main()
