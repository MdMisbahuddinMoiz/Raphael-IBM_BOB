"""tests.test_d9_network — D9 governed network execution tests.

Deterministic and offline: a local stdlib HTTP server on 127.0.0.1 (no
external network) stands in for an authorized HTB web target. No shell,
no Kali, no nmap, no legacy imports.

Covers: target model/store, canonical network scope, Policy ALLOW/DENY,
the NetworkMediator (success/timeout/refused/byte-cap/redirect/one-request),
untrusted evidence, flag extraction, D4 independent verification,
falsification, and the existing QualityGate (positive + negative).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.contracts import (
    ActionRequest, Capability, Decision, Finding, FindingState, Mission,
)
from raphael_ibm_bob.evidence_ledger import (
    EvidenceLedger, create_run_dir, digest_id,
)
from raphael_ibm_bob.falsifier import ChallengeSpec, Falsifier
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.network_runtime import (
    NetworkMediator, NetworkState, NetworkVerifier, extract_flag, flag_sha256,
)
from raphael_ibm_bob.network_scope import (
    NetworkScopeError, canonical_host, host_in_scope, parse_http_target,
    scope_contains_host,
)
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.quality_gate import BOBQualityGate, GateInputs
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.target_profile import (
    TargetProfileError, TargetStore, build_target_profile,
)
from raphael_ibm_bob.workspace import Workspace

FLAG = "HTB{deterministic_d9_fixture_flag}"
FLAG_HASH = hashlib.sha256(FLAG.encode()).hexdigest()
REPO = Path(__file__).resolve().parents[1]


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body: bytes):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/flag":
            self._send(200, f"welcome {FLAG}".encode())
        elif path == "/verify":
            self._send(200, f"confirmed {FLAG}".encode())
        elif path == "/decoy":
            self._send(200, b"nothing here")
        elif path == "/big":
            self._send(200, b"A" * 200000)
        elif path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://evil.example/")
            self.end_headers()
        elif path == "/slow":
            time.sleep(1.5)
            self._send(200, b"slow")
        else:
            self._send(404, b"nope")

    def do_HEAD(self):
        path = urlsplit(self.path).path
        if path == "/flag":
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self._send(404, b"")


@contextmanager
def http_fixture():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


class _GovCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="d9_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ws = self.tmp / "ws"
        self.ws.mkdir()
        (self.ws / "test_ok.py").write_text(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n",
            encoding="utf-8")
        self.run_id, self.run_dir = create_run_dir(self.tmp / "runs")

    def _mission(self):
        return Mission(mission_id="M-d9", description="htb flag",
                       scope="", criteria=["capture the flag"])

    def _profile(self, port, locator="127.0.0.1"):
        return build_target_profile(
            mission_id="M-d9", locator=locator, allowed_ports=[port],
            allowed_protocols=["http"],
            authorization_ref="HTB-lab-authorization-123")

    def _stack(self, profile, *, mediator=None, store=None):
        store = store or TargetStore()
        store.set_target(profile)
        mediator = mediator or NetworkMediator()
        policy = BOBPolicy(Workspace(self.ws), target_store=store)
        ledger = EvidenceLedger(self.run_dir)
        self.addCleanup(ledger.close)
        broker = BOBBroker(policy, Workspace(self.ws), ledger=ledger,
                           network_mediator=mediator, target_store=store)
        runtime = BOBRuntime(broker)
        findings = FindingStore(ledger)
        gate = BOBQualityGate(ledger, target_store=store)
        verifier = NetworkVerifier(runtime, ledger, findings,
                                   replay_guard=mediator.replay_guard)
        falsifier = Falsifier(runtime, ledger, findings)
        return dict(store=store, mediator=mediator, policy=policy,
                    ledger=ledger, broker=broker, runtime=runtime,
                    findings=findings, gate=gate, verifier=verifier,
                    falsifier=falsifier)

    def _net_request(self, url, method="GET", timeout=5.0, seq=0):
        return ActionRequest(
            sequence=seq, requester="tester",
            capability=Capability.NETWORK_HTTP_REQUEST, target=url,
            purpose=f"network-http-request method={method}",
            timeout_seconds=timeout)


# ---------------------------------------------------------------------------
# target model
# ---------------------------------------------------------------------------

class TargetModel(unittest.TestCase):
    def test_valid_profile(self):
        p = build_target_profile(
            mission_id="M1", locator="10.129.48.95", allowed_ports=[80, 443],
            allowed_protocols=["http", "https"], authorization_ref="auth-1")
        self.assertEqual(p.platform, "htb")
        self.assertEqual(p.locator, "10.129.48.95")
        self.assertEqual(p.allowed_ports, (80, 443))
        self.assertTrue(p.target_id.startswith("TP-"))
        self.assertTrue(p.allows(host="10.129.48.95", port=80, protocol="http"))

    def test_target_id_deterministic(self):
        kw = dict(mission_id="M1", locator="10.129.48.95",
                  allowed_ports=[80], allowed_protocols=["http"],
                  authorization_ref="a")
        self.assertEqual(build_target_profile(**kw).target_id,
                         build_target_profile(**kw).target_id)

    def test_invalid_platform(self):
        with self.assertRaises(TargetProfileError):
            build_target_profile(mission_id="M1", locator="h", platform="bogus",
                                 allowed_ports=[80], allowed_protocols=["http"],
                                 authorization_ref="a")

    def test_invalid_protocol(self):
        with self.assertRaises(TargetProfileError):
            build_target_profile(mission_id="M1", locator="h", allowed_ports=[80],
                                 allowed_protocols=["gopher"],
                                 authorization_ref="a")

    def test_invalid_port(self):
        with self.assertRaises(TargetProfileError):
            build_target_profile(mission_id="M1", locator="h",
                                 allowed_ports=[70000],
                                 allowed_protocols=["http"],
                                 authorization_ref="a")

    def test_missing_authorization(self):
        with self.assertRaises(TargetProfileError):
            build_target_profile(mission_id="M1", locator="h",
                                 allowed_ports=[80], allowed_protocols=["http"],
                                 authorization_ref="")

    def test_missing_mission(self):
        with self.assertRaises(TargetProfileError):
            build_target_profile(mission_id="", locator="h",
                                 allowed_ports=[80], allowed_protocols=["http"],
                                 authorization_ref="a")

    def test_scope_must_contain_locator(self):
        with self.assertRaises(TargetProfileError):
            build_target_profile(mission_id="M1", locator="10.0.0.5",
                                 allowed_ports=[80], allowed_protocols=["http"],
                                 scope="10.0.0.0/30", authorization_ref="a")

    def test_store_mission_binding(self):
        store = TargetStore()
        store.set_target(build_target_profile(
            mission_id="A", locator="h", allowed_ports=[80],
            allowed_protocols=["http"], authorization_ref="a"))
        self.assertIsNotNone(store.get_target("A"))
        self.assertIsNone(store.get_target("B"))
        store.clear_target()
        self.assertIsNone(store.get_target("A"))


# ---------------------------------------------------------------------------
# canonical network scope
# ---------------------------------------------------------------------------

class NetworkScope(unittest.TestCase):
    def test_parse_default_ports(self):
        t = parse_http_target("http://example.com/x")
        self.assertEqual((t.scheme, t.port, t.path), ("http", 80, "/x"))
        t2 = parse_http_target("https://example.com")
        self.assertEqual((t2.scheme, t2.port), ("https", 443))

    def test_reject_schemes(self):
        for url in ("ftp://h/x", "file:///etc/passwd", "gopher://h",
                    "data:text/plain,x", "javascript:alert(1)"):
            with self.assertRaises(NetworkScopeError):
                parse_http_target(url)

    def test_reject_userinfo_and_fragment(self):
        with self.assertRaises(NetworkScopeError):
            parse_http_target("http://user:pass@h/x")
        with self.assertRaises(NetworkScopeError):
            parse_http_target("http://h/x#frag")

    def test_prefix_spoof_rejected(self):
        self.assertFalse(host_in_scope("10.129.48.95", "10.129.48.950"))
        self.assertFalse(host_in_scope("10.129.48.95", "evil-10.129.48.95"))
        self.assertTrue(host_in_scope("10.129.48.95", "10.129.48.95"))
        self.assertTrue(host_in_scope("10.129.48.0/24", "10.129.48.95"))

    def test_empty_scope_fails_closed(self):
        self.assertFalse(host_in_scope("", "10.0.0.1"))
        self.assertFalse(scope_contains_host("", "http://10.0.0.1/x"))


# ---------------------------------------------------------------------------
# policy
# ---------------------------------------------------------------------------

class PolicyNetwork(_GovCase):
    def test_allow_authorized(self):
        with http_fixture() as port:
            s = self._stack(self._profile(port))
            d = s["policy"].consult(
                self._net_request(f"http://127.0.0.1:{port}/flag"), self._mission())
            self.assertIs(d.decision, Decision.ALLOW, d.reason)

    def test_deny_wrong_port(self):
        with http_fixture() as port:
            s = self._stack(self._profile(port))
            d = s["policy"].consult(
                self._net_request(f"http://127.0.0.1:{port + 1}/flag"),
                self._mission())
            self.assertIs(d.decision, Decision.DENY)
            self.assertEqual(d.reason, "network-target-mismatch")

    def test_deny_wrong_protocol(self):
        with http_fixture() as port:
            s = self._stack(self._profile(port))
            d = s["policy"].consult(
                self._net_request(f"https://127.0.0.1:{port}/flag"),
                self._mission())
            self.assertIs(d.decision, Decision.DENY)

    def test_deny_prefix_spoof_host(self):
        with http_fixture() as port:
            s = self._stack(self._profile(port))
            d = s["policy"].consult(
                self._net_request(f"http://127.0.0.10:{port}/flag"),
                self._mission())
            self.assertIs(d.decision, Decision.DENY)

    def test_deny_wrong_mission(self):
        with http_fixture() as port:
            s = self._stack(self._profile(port))
            mission = Mission(mission_id="OTHER", description="x", scope="",
                              criteria=["c"])
            d = s["policy"].consult(
                self._net_request(f"http://127.0.0.1:{port}/flag"), mission)
            self.assertIs(d.decision, Decision.DENY)
            self.assertEqual(d.reason, "network-no-authorized-target")

    def test_deny_method(self):
        with http_fixture() as port:
            s = self._stack(self._profile(port))
            d = s["policy"].consult(
                self._net_request(f"http://127.0.0.1:{port}/flag",
                                  method="POST"),
                self._mission())
            self.assertIs(d.decision, Decision.DENY)

    def test_deny_invalid_timeout(self):
        with http_fixture() as port:
            s = self._stack(self._profile(port))
            req = self._net_request(f"http://127.0.0.1:{port}/flag", timeout=-1)
            d = s["policy"].consult(req, self._mission())
            self.assertIs(d.decision, Decision.DENY)

    def test_deny_means_no_result(self):
        with http_fixture() as port:
            s = self._stack(self._profile(port))
            rt = s["runtime"].submit(
                self._net_request(f"http://127.0.0.1:{port + 1}/flag"),
                self._mission())
            self.assertIs(rt.broker_result.decision.decision, Decision.DENY)
            self.assertFalse(rt.broker_result.capability_invoked)
            self.assertIsNone(rt.broker_result.result_seq)
            self.assertIsNone(rt.execution)


# ---------------------------------------------------------------------------
# mediator
# ---------------------------------------------------------------------------

class Mediator(_GovCase):
    def _invoke(self, port, path="/flag", method="GET", mediator=None):
        s = self._stack(self._profile(port), mediator=mediator)
        return s["mediator"].invoke(
            request=self._net_request(f"http://127.0.0.1:{port}{path}", method),
            profile=s["store"].current(), invocation_id="NET-test", run_id="run-1")

    def test_success_and_flag(self):
        with http_fixture() as port:
            r = self._invoke(port)
            self.assertIs(r.state, NetworkState.SUCCESS)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.flag, FLAG)
            self.assertEqual(r.flag_sha256, FLAG_HASH)
            self.assertEqual(r.response_sha256,
                             hashlib.sha256(f"welcome {FLAG}".encode()).hexdigest())

    def test_head(self):
        with http_fixture() as port:
            r = self._invoke(port, method="HEAD")
            self.assertIs(r.state, NetworkState.SUCCESS)
            self.assertEqual(r.response_bytes, 0)

    def test_byte_cap_truncation(self):
        with http_fixture() as port:
            m = NetworkMediator(max_response_bytes=1024)
            r = self._invoke(port, path="/big", mediator=m)
            self.assertTrue(r.truncated)
            self.assertEqual(r.response_bytes, 1024)

    def test_redirect_blocked(self):
        with http_fixture() as port:
            r = self._invoke(port, path="/redirect")
            self.assertIs(r.state, NetworkState.SUCCESS)
            self.assertEqual(r.status_code, 302)
            self.assertNotIn("evil.example", r.body_preview)

    def test_timeout(self):
        def opener(url, method, timeout, max_bytes):
            raise __import__("raphael_ibm_bob.network_runtime",
                             fromlist=["_Timeout"])._Timeout("boom")
        with http_fixture() as port:
            r = self._invoke(port, mediator=NetworkMediator(opener=opener))
            self.assertIs(r.state, NetworkState.TIMEOUT)
            self.assertFalse(r.success)

    def test_refused(self):
        def opener(url, method, timeout, max_bytes):
            raise __import__("raphael_ibm_bob.network_runtime",
                             fromlist=["_Refused"])._Refused("nope")
        with http_fixture() as port:
            r = self._invoke(port, mediator=NetworkMediator(opener=opener))
            self.assertIs(r.state, NetworkState.REFUSED)
            self.assertFalse(r.success)

    def test_one_request_per_invocation(self):
        calls = []

        def opener(url, method, timeout, max_bytes):
            calls.append(url)
            return 200, b"ok", False
        with http_fixture() as port:
            self._invoke(port, mediator=NetworkMediator(opener=opener))
        self.assertEqual(len(calls), 1)

    def test_invalid_scheme_denied(self):
        with http_fixture() as port:
            s = self._stack(self._profile(port))
            r = s["mediator"].invoke(
                request=self._net_request("ftp://127.0.0.1/flag"),
                profile=s["store"].current(), invocation_id="NET-x",
                run_id="run-1")
            self.assertIs(r.state, NetworkState.DENIED)


# ---------------------------------------------------------------------------
# evidence / flag
# ---------------------------------------------------------------------------

class EvidenceAndFlag(_GovCase):
    def test_untrusted_evidence_and_flag_marker(self):
        with http_fixture() as port:
            s = self._stack(self._profile(port))
            rt = s["runtime"].submit(
                self._net_request(f"http://127.0.0.1:{port}/flag"),
                self._mission())
            self.assertIs(rt.broker_result.decision.decision, Decision.ALLOW)
            self.assertTrue(rt.execution.success)
            ev = rt.execution.evidence
            self.assertTrue(ev["provider_untrusted"])
            self.assertEqual(ev["flag"], FLAG)
            self.assertEqual(ev["flag_sha256"], FLAG_HASH)
            self.assertIn("response_sha256", ev)
            network_records = [
                r for r in s["ledger"].all_records()
                if r.get("kind") == "evidence" and r.get("producer") == "network"]
            self.assertEqual(len(network_records), 1)
            blob = json.dumps(network_records[0])
            for forbidden in ("verified", "\"complete\"", "severity"):
                self.assertNotIn(forbidden, blob)

    def test_no_flag_in_decoy(self):
        self.assertIsNone(extract_flag("nothing here"))
        self.assertEqual(flag_sha256(FLAG), FLAG_HASH)
        self.assertIsNone(flag_sha256(None))


# ---------------------------------------------------------------------------
# verification / falsification
# ---------------------------------------------------------------------------

class Verification(_GovCase):
    def _verified_setup(self, port):
        s = self._stack(self._profile(port))
        orig = s["runtime"].submit(
            self._net_request(f"http://127.0.0.1:{port}/flag"), self._mission())
        inv = orig.execution.evidence["invocation_id"]
        finding = Finding(
            finding_id="F-d9-flag", state=FindingState.UNVERIFIED,
            summary=f"htb-flag:{FLAG_HASH[:12]}",
            target=f"http://127.0.0.1:{port}/flag", mission_id="M-d9")
        s["findings"].register(finding)
        return s, inv

    def test_independent_verification(self):
        with http_fixture() as port:
            s, inv = self._verified_setup(port)
            out = s["verifier"].verify_independent(
                s["findings"].get("F-d9-flag"), self._mission(),
                original_invocation_id=inv, expected_flag_hash=FLAG_HASH)
            self.assertEqual(out.classification, "supported", out.checks)
            self.assertTrue(all(out.checks.values()), out.checks)
            self.assertTrue(out.transition_applied)
            self.assertIs(s["findings"].get("F-d9-flag").state,
                          FindingState.VERIFIED)

    def test_contradicted_hash_no_transition(self):
        with http_fixture() as port:
            s, inv = self._verified_setup(port)
            out = s["verifier"].verify_independent(
                s["findings"].get("F-d9-flag"), self._mission(),
                original_invocation_id=inv, expected_flag_hash="deadbeef")
            self.assertEqual(out.classification, "contradicted")
            self.assertFalse(out.transition_applied)

    def test_falsification_decoy_clean(self):
        with http_fixture() as port:
            s, inv = self._verified_setup(port)
            s["verifier"].verify_independent(
                s["findings"].get("F-d9-flag"), self._mission(),
                original_invocation_id=inv, expected_flag_hash=FLAG_HASH)
            outcome = s["falsifier"].challenge(
                s["findings"].get("F-d9-flag"),
                ChallengeSpec(
                    capability=Capability.NETWORK_HTTP_REQUEST,
                    target=f"http://127.0.0.1:{port}/decoy",
                    purpose="network-http-request method=GET",
                    predicate=lambda payload: bool(
                        (payload.get("network_result") or {}).get("flag"))),
                self._mission())
            self.assertFalse(outcome.counter_example_observed)
            self.assertIs(s["findings"].get("F-d9-flag").state,
                          FindingState.VERIFIED)

    def test_falsification_counter_example_refutes(self):
        with http_fixture() as port:
            s, inv = self._verified_setup(port)
            s["verifier"].verify_independent(
                s["findings"].get("F-d9-flag"), self._mission(),
                original_invocation_id=inv, expected_flag_hash=FLAG_HASH)
            outcome = s["falsifier"].challenge(
                s["findings"].get("F-d9-flag"),
                ChallengeSpec(
                    capability=Capability.NETWORK_HTTP_REQUEST,
                    target=f"http://127.0.0.1:{port}/flag",
                    purpose="network-http-request method=GET",
                    predicate=lambda payload: bool(
                        (payload.get("network_result") or {}).get("flag"))),
                self._mission())
            self.assertTrue(outcome.counter_example_observed)
            self.assertIs(s["findings"].get("F-d9-flag").state,
                          FindingState.REFUTED)


# ---------------------------------------------------------------------------
# quality gate
# ---------------------------------------------------------------------------

class QualityGate(_GovCase):
    def _run_test(self, s):
        return s["runtime"].submit(
            ActionRequest(sequence=0, requester="tester",
                          capability=Capability.RUN_TEST, target="test_ok.py",
                          purpose="required-test", timeout_seconds=30.0),
            self._mission())

    def _persist(self, s, producer, payload):
        s["ledger"].append_evidence(
            evidence_id=digest_id(payload, prefix=producer[:1].upper()),
            producer=producer, request_seq=0, decision_seq=0,
            result_seq=None, payload=payload)

    def test_complete_happy_path(self):
        with http_fixture() as port:
            s = self._stack(self._profile(port))
            orig = s["runtime"].submit(
                self._net_request(f"http://127.0.0.1:{port}/flag"),
                self._mission())
            inv = orig.execution.evidence["invocation_id"]
            self._run_test(s)
            finding = Finding(
                finding_id="F-d9-flag", state=FindingState.UNVERIFIED,
                summary=f"htb-flag:{FLAG_HASH[:12]}",
                target=f"http://127.0.0.1:{port}/flag", mission_id="M-d9")
            s["findings"].register(finding)
            out = s["verifier"].verify_independent(
                s["findings"].get("F-d9-flag"), self._mission(),
                original_invocation_id=inv, expected_flag_hash=FLAG_HASH)
            self.assertEqual(out.classification, "supported")
            self._persist(s, "regression",
                          {"kind": "regression", "mission_id": "M-d9",
                           "result": "passed"})
            self._persist(s, "probe",
                          {"kind": "probe", "allowed": True,
                           "result": "passed",
                           "source": "network-independent-verification"})
            evaluation = s["gate"].evaluate(GateInputs(
                mission=self._mission(),
                findings=list(s["findings"].all()),
                regression_ok=True, behavior_probe_ok=True))
            self.assertEqual(evaluation.verdict.value, "complete",
                             (evaluation.failed, evaluation.reasons))

    def test_refuse_unverified_finding(self):
        with http_fixture() as port:
            s = self._stack(self._profile(port))
            s["runtime"].submit(
                self._net_request(f"http://127.0.0.1:{port}/flag"),
                self._mission())
            self._run_test(s)
            s["findings"].register(Finding(
                finding_id="F-open", state=FindingState.UNVERIFIED,
                summary="unverified", target=f"http://127.0.0.1:{port}/flag",
                mission_id="M-d9"))
            self._persist(s, "regression",
                          {"kind": "regression", "mission_id": "M-d9",
                           "result": "passed"})
            self._persist(s, "probe", {"kind": "probe", "allowed": True})
            evaluation = s["gate"].evaluate(GateInputs(
                mission=self._mission(), findings=list(s["findings"].all()),
                regression_ok=True, behavior_probe_ok=True))
            self.assertEqual(evaluation.verdict.value, "refuse")
            self.assertIn("G:finding-state", evaluation.failed)

    def test_refuse_no_probe(self):
        with http_fixture() as port:
            s = self._stack(self._profile(port))
            s["runtime"].submit(
                self._net_request(f"http://127.0.0.1:{port}/flag"),
                self._mission())
            self._run_test(s)
            s["findings"].register(Finding(
                finding_id="F-v", state=FindingState.VERIFIED,
                summary="v", target=f"http://127.0.0.1:{port}/flag",
                mission_id="M-d9"))
            self._persist(s, "regression",
                          {"kind": "regression", "mission_id": "M-d9",
                           "result": "passed"})
            evaluation = s["gate"].evaluate(GateInputs(
                mission=self._mission(), findings=list(s["findings"].all()),
                regression_ok=True, behavior_probe_ok=False))
            self.assertEqual(evaluation.verdict.value, "refuse")
            self.assertIn("D:independent-behavior-probe", evaluation.failed)

    def test_refuse_network_scope_violation(self):
        with http_fixture() as port:
            s = self._stack(self._profile(port))
            s["runtime"].submit(
                self._net_request(f"http://127.0.0.1:{port}/flag"),
                self._mission())
            self._run_test(s)
            s["findings"].register(Finding(
                finding_id="F-v", state=FindingState.VERIFIED,
                summary="v", target=f"http://127.0.0.1:{port}/flag",
                mission_id="M-d9"))
            self._persist(s, "regression",
                          {"kind": "regression", "mission_id": "M-d9",
                           "result": "passed"})
            self._persist(s, "probe", {"kind": "probe", "allowed": True})
            # Gate with an empty target store must fail condition E.
            gate = BOBQualityGate(s["ledger"], target_store=TargetStore())
            evaluation = gate.evaluate(GateInputs(
                mission=self._mission(), findings=list(s["findings"].all()),
                regression_ok=True, behavior_probe_ok=True))
            self.assertEqual(evaluation.verdict.value, "refuse")
            self.assertIn("E:scope", evaluation.failed)


# ---------------------------------------------------------------------------
# target API + operations UI
# ---------------------------------------------------------------------------

class TargetAPI(unittest.TestCase):
    def setUp(self):
        from raphael_ibm_bob.http.app import (
            RaphaelHTTPConfig, Request, build_router, dispatch)
        self._dispatch = dispatch
        self._Request = Request
        self.store = TargetStore()
        self.cfg = RaphaelHTTPConfig(target_store=self.store)
        self.router = build_router()

    def call(self, method, path, body=None):
        return self._dispatch(
            self._Request(method=method, path=path, body=body),
            self.cfg, self.router)

    def test_declare_and_get_and_clear(self):
        body = {"mission_id": "M-d9", "locator": "10.129.48.95",
                "allowed_ports": "80,443", "allowed_protocols": "http,https",
                "authorization_ref": "auth-1"}
        resp = self.call("POST", "/htb/target", body)
        self.assertEqual(resp.status, 201, resp.body)
        self.assertTrue(resp.body["configured"])
        self.assertEqual(resp.body["target"]["locator"], "10.129.48.95")
        got = self.call("GET", "/htb/target")
        self.assertTrue(got.body["configured"])
        cleared = self.call("POST", "/htb/target/clear")
        self.assertFalse(cleared.body["configured"])

    def test_reject_invalid_target(self):
        resp = self.call("POST", "/htb/target",
                         {"mission_id": "M", "locator": "h",
                          "allowed_ports": "0", "allowed_protocols": "http",
                          "authorization_ref": "a"})
        self.assertEqual(resp.status, 422)
        self.assertEqual(resp.body["error"]["code"], "INVALID_INPUT")


class OperationsView(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="d9ui_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _render(self, target_state):
        from raphael_ibm_bob.http.views.operations_console import render_index
        return render_index(
            [], runs_root=self.tmp, sessions_root=self.tmp,
            vpn_status={"state": "connected"},
            mode_state={"mode": "testing", "testing_profile": "htb"},
            target_state=target_state)

    def test_unconfigured(self):
        html = self._render(None)
        self.assertIn("HTB CONTEXT", html)
        self.assertIn("NOT CONFIGURED", html)
        self.assertIn("SAVE TARGET", html)

    def test_configured(self):
        html = self._render({
            "mission_id": "M-d9", "locator": "10.129.48.95",
            "allowed_ports": [80, 443], "allowed_protocols": ["http", "https"],
            "scope": "10.129.48.95", "authorization_ref": "auth-1"})
        self.assertIn("AUTHORIZED", html)
        self.assertIn("10.129.48.95", html)


# ---------------------------------------------------------------------------
# security guards
# ---------------------------------------------------------------------------

class SecurityGuards(unittest.TestCase):
    def test_no_shell_or_legacy_imports(self):
        for rel in ("raphael_ibm_bob/network_runtime.py",
                    "raphael_ibm_bob/network_scope.py",
                    "raphael_ibm_bob/target_profile.py"):
            text = (REPO / rel).read_text(encoding="utf-8")
            for needle in ("shell=True", "import nmap", "masscan", "nuclei",
                           "kali_tools_client", "src.orchestrator",
                           "from src.orchestrator", "import src.raphael"):
                self.assertNotIn(needle, text, f"{rel}: {needle}")

    def test_mediator_has_no_subprocess_or_proxy(self):
        text = (REPO / "raphael_ibm_bob/network_runtime.py").read_text(
            encoding="utf-8")
        for needle in ("import subprocess", "subprocess.", "ProxyHandler",
                       "os.system", "build_opener("):
            if needle == "build_opener(":
                continue  # urllib's opener builder is expected
            self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
