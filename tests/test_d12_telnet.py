"""tests.test_d12_telnet — governed Telnet capability (D12) unit tests.

Deterministic and offline: a fake session function simulates the target so
the mediator, Policy, Broker, verifier and falsifier are exercised without
touching the network. The real live run lives in test_d12_telnet_live.py and
is skipped unless RAPHAEL_LIVE_MEOW=1.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
    FindingState,
    Mission,
    PolicyDecision,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, create_run_dir
from raphael_ibm_bob.finding import FindingStore
from raphael_ibm_bob.harness.api import create_session
from raphael_ibm_bob.harness.network_run import NetworkRunResult
from raphael_ibm_bob.harness.telnet_run import run_telnet_mission
from raphael_ibm_bob.http.app import (
    RaphaelHTTPConfig,
    Request,
    build_router,
    dispatch,
)
from raphael_ibm_bob.mode import Mode, ModeManager
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.target_profile import TargetStore, build_target_profile
from raphael_ibm_bob.telnet_runtime import (
    COMMAND_ALLOWLIST,
    TelnetMediator,
    TelnetSessionSpec,
    TelnetState,
    build_telnet_spec,
    extract_candidate,
    extract_flag_pattern,
    is_exact_lower_hex32,
    set_telnet_mediator,
    submission_flag,
    validate_command,
)
from raphael_ibm_bob.workspace import Workspace

# A synthetic flag (NOT the real Meow flag).
CANDIDATE = "0123456789abcdef0123456789abcdef"
HOST = "10.129.223.207"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def make_fake_session(flag=CANDIDATE, auth_ok=True, calls=None,
                      extra_outputs=None):
    """A deterministic fake Telnet session function."""
    outputs = {
        "pwd": "/root",
        "ls": "flag.txt\nnotes.txt",
        "cat flag.txt": flag,
        "cat /root/flag.txt": flag,
    }
    if extra_outputs:
        outputs.update(extra_outputs)

    def session(host, port, username, password, commands, timeout, max_bytes):
        if calls is not None:
            calls.append({"host": host, "port": port, "username": username,
                          "password": password, "commands": list(commands),
                          "timeout": timeout, "max_bytes": max_bytes})
        if not auth_ok:
            return {"ok": False, "state": TelnetState.AUTH_FAILED,
                    "error": "auth failed", "authenticated": False,
                    "auth_decision": "rejected", "commands": [],
                    "session_bytes": 0}
        cmds = []
        for c in commands:
            out = outputs.get(c, "")
            cmds.append({"command": c, "output_sha256": _sha(out),
                         "output_preview": out[:2000],
                         "bytes": len(out.encode()), "ok": True})
        return {"ok": True, "state": TelnetState.SUCCESS, "error": "",
                "authenticated": True, "auth_decision": "accepted",
                "commands": cmds, "session_bytes": 42}
    return session


class _Base(unittest.TestCase):
    mission_id = "M-MEOW-D12"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="d12_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ws = self.tmp / "ws"
        self.ws.mkdir()
        (self.ws / "test_ok.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n"
            "    def test_ok(self):\n        self.assertTrue(True)\n")
        self.sessions = self.tmp / "sessions"
        self.runs = self.tmp / "runs"

    def problem(self, **telnet_over):
        telnet = {
            "username": "root", "password": "",
            "commands": ["pwd", "ls", "cat flag.txt"],
            "flag_command": "cat flag.txt", "flag_pattern": "[0-9a-f]{32}",
            "probe_command": "pwd", "negative_control_command": "ls",
            "timeout_seconds": 5,
        }
        telnet.update(telnet_over)
        return {"telnet": telnet, "verification_tests": ["test_ok.py"]}

    def mission(self, **telnet_over):
        return Mission(
            mission_id=self.mission_id, description="governed telnet meow",
            scope="", criteria=["obtain and verify the flag"],
            problem=self.problem(**telnet_over))

    def store(self, *, locator=HOST, ports=(23,), protocols=("telnet",),
              mission_id=None, scope=None):
        store = TargetStore()
        store.set_target(build_target_profile(
            mission_id=mission_id or self.mission_id, locator=locator,
            allowed_ports=list(ports), allowed_protocols=list(protocols),
            scope=scope if scope is not None else locator,
            authorization_ref="HTB-AUTHORIZED-D12"))
        return store

    def drive(self, mission, store, session_fn):
        session = create_session(
            mission=mission, workspace_root=self.ws,
            project_name="d12", sessions_root=self.sessions)
        mediator = TelnetMediator(session_fn=session_fn)
        return run_telnet_mission(
            session, mission, self.ws, runs_root=self.runs,
            sessions_root=self.sessions, target_store=store,
            mediator=mediator)

    def ledger(self, run_id):
        return [json.loads(line) for line in
                (self.runs / run_id / "evidence.jsonl").read_text().splitlines()
                if line.strip()]

    def records(self, run_id, **match):
        out = []
        for r in self.ledger(run_id):
            if all(r.get(k) == v for k, v in match.items()):
                out.append(r)
        return out


# ---------------------------------------------------------------------------
# schema + command allowlist
# ---------------------------------------------------------------------------

class SchemaAndAllowlist(unittest.TestCase):
    def test_capability_enum_value(self):
        self.assertEqual(Capability.NETWORK_TELNET_SESSION.value,
                         "network_telnet_session")
        # HTTP capability semantics are unchanged.
        self.assertEqual(Capability.NETWORK_HTTP_REQUEST.value,
                         "network_http_request")

    def test_command_allowlist_contents(self):
        self.assertEqual(COMMAND_ALLOWLIST, ("pwd", "ls", "cat flag.txt"))

    def test_spec_blank_password_explicit(self):
        spec = TelnetSessionSpec(
            target=HOST, port=23, username="root", password="",
            commands=("pwd", "ls", "cat flag.txt"),
            flag_command="cat flag.txt", flag_pattern="[0-9a-f]{32}")
        self.assertEqual(spec.password, "")           # explicit, not omitted
        view = spec.sensitive_dict()
        self.assertIn("password_present", view)
        self.assertIn("password_is_blank", view)
        self.assertNotIn("password", {k: v for k, v in view.items()
                                      if k == "password"})
        self.assertFalse(view["password_present"])
        self.assertTrue(view["password_is_blank"])

    def test_build_spec_from_mission(self):
        mission = Mission(
            mission_id="M", description="d", scope="", criteria=["c"],
            problem={"telnet": {"username": "root", "password": "",
                                "commands": ["cat flag.txt"],
                                "flag_command": "cat flag.txt",
                                "flag_pattern": "[0-9a-f]{32}"}})
        profile = build_target_profile(
            mission_id="M", locator=HOST, allowed_ports=[23],
            allowed_protocols=["telnet"], scope=HOST, authorization_ref="A")
        spec = build_telnet_spec(mission, profile)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.username, "root")
        self.assertEqual(spec.password, "")

    def test_command_allowlist_enforced(self):
        allow = ("pwd", "ls", "cat flag.txt")
        for ok_cmd in allow:
            self.assertEqual(validate_command(ok_cmd, allow), (True, "ok"))
        for bad, reason in [
            ("bash", "command-forbidden-binary:bash"),
            ("sh", "command-forbidden-binary:sh"),
            ("sudo su", "command-forbidden-binary:sudo"),
            ("nc 1.2.3.4 9", "command-forbidden-binary:nc"),
            ("curl http://x", "command-forbidden-binary:curl"),
            ("wget x", "command-forbidden-binary:wget"),
            ("python3 -c 1", "command-forbidden-binary:python3"),
            ("perl -e 1", "command-forbidden-binary:perl"),
            ("ruby -e 1", "command-forbidden-binary:ruby"),
            ("ssh a@b", "command-forbidden-binary:ssh"),
            ("telnet x", "command-forbidden-binary:telnet"),
            ("cat flag.txt; id", "command-metacharacter:';'"),
            ("cat flag.txt | sh", "command-metacharacter:'|'"),
            ("cat flag.txt > x", "command-metacharacter:'>'"),
            ("cat $(id)", "command-metacharacter:'$'"),
            ("cat `id`", "command-metacharacter:'`'"),
            ("cat flag.txt && ls", "command-metacharacter:'&'"),
            ("cat *.txt", "command-metacharacter:'*'"),
            ("cat /etc/passwd", "command-not-in-allowlist"),
        ]:
            got, why = validate_command(bad, allow)
            self.assertFalse(got, bad)
            self.assertEqual(why, reason, bad)

    def test_candidate_extraction_tied_to_pattern(self):
        self.assertEqual(extract_flag_pattern("blah " + CANDIDATE, "[0-9a-f]{32}"),
                         CANDIDATE)
        self.assertIsNone(extract_flag_pattern("no flag here", "[0-9a-f]{32}"))
        self.assertIsNone(extract_flag_pattern("XYZ", "[0-9a-f]{32}"))


class StrictExtraction(unittest.TestCase):
    P = "[0-9a-f]{32}"
    DECOY = "fedcba9876543210fedcba9876543210"

    def test_exactly_one_standalone_candidate(self):
        self.assertEqual(extract_candidate("out " + CANDIDATE, self.P),
                         (CANDIDATE, 1))
        self.assertEqual(extract_candidate(CANDIDATE + "\n", self.P),
                         (CANDIDATE, 1))
        self.assertEqual(extract_candidate("none here", self.P), (None, 0))
        self.assertEqual(extract_candidate("", self.P), (None, 0))

    def test_ambiguous_or_wrong_length_fails(self):
        # two candidates -> ambiguous -> fail closed
        self.assertEqual(extract_candidate(
            CANDIDATE + " " + self.DECOY, self.P), (None, 2))
        # 31 / 33 / 34 chars -> not a 32-hex token
        self.assertEqual(extract_candidate("0" * 31, self.P), (None, 0))
        self.assertEqual(extract_candidate("0" * 33, self.P), (None, 0))
        # a 32-hex embedded in a 40-hex run is NOT standalone
        self.assertEqual(extract_candidate("0" * 40, self.P), (None, 0))
        # uppercase is not the declared lowercase format
        self.assertEqual(extract_candidate("A" * 32, self.P), (None, 0))

    def test_exact_lower_hex32_and_submission(self):
        self.assertTrue(is_exact_lower_hex32(CANDIDATE))
        self.assertFalse(is_exact_lower_hex32(CANDIDATE.upper()))
        self.assertFalse(is_exact_lower_hex32("0" * 31))
        self.assertEqual(submission_flag(CANDIDATE), "HTB{" + CANDIDATE + "}")
        self.assertIsNone(submission_flag("not-a-flag"))
        # the submission SHA-256 is of the HTB{...} representation, not the raw.
        submission = submission_flag(CANDIDATE)
        self.assertNotEqual(_sha(CANDIDATE), _sha(submission))


# ---------------------------------------------------------------------------
# authorization / scope / mission binding
# ---------------------------------------------------------------------------

class Authorization(_Base):
    def _consult(self, target, mission=None, store=None):
        mission = mission or self.mission()
        store = store or self.store()
        policy = BOBPolicy(Workspace(self.ws), target_store=store)
        return policy.consult(
            ActionRequest(sequence=1, requester="t",
                          capability=Capability.NETWORK_TELNET_SESSION,
                          target=target, purpose="telnet-session",
                          timeout_seconds=5), mission)

    def test_exact_target_authorization(self):
        d = self._consult(f"telnet://{HOST}:23")
        self.assertEqual(d.decision.value, "allow")
        d2 = self._consult("telnet://10.129.223.208:23")
        self.assertEqual(d2.decision.value, "deny")
        self.assertEqual(d2.reason, "telnet-target-mismatch")

    def test_exact_port_authorization(self):
        d = self._consult(f"telnet://{HOST}:2323")
        self.assertEqual(d.decision.value, "deny")
        self.assertEqual(d.reason, "telnet-target-mismatch")

    def test_protocol_authorization(self):
        store = self.store(protocols=("http",))
        d = self._consult(f"telnet://{HOST}:80", store=store)
        self.assertEqual(d.decision.value, "deny")
        self.assertEqual(d.reason, "telnet-target-mismatch")

    def test_mission_binding(self):
        store = self.store(mission_id="M-OTHER")
        d = self._consult(f"telnet://{HOST}:23", store=store)
        self.assertEqual(d.decision.value, "deny")
        self.assertEqual(d.reason, "telnet-no-authorized-target")

    def test_non_telnet_scheme_rejected(self):
        d = self._consult(f"http://{HOST}:23")
        self.assertEqual(d.decision.value, "deny")

    def test_deny_without_execution(self):
        mission = self.mission()
        store = self.store(locator="10.0.0.9")
        ledger = EvidenceLedger(create_run_dir(self.runs)[1])
        try:
            broker = BOBBroker(BOBPolicy(Workspace(self.ws), target_store=store),
                               Workspace(self.ws), ledger=ledger,
                               target_store=store,
                               telnet_mediator=TelnetMediator(
                                   session_fn=make_fake_session()))
            rt = BOBRuntime(broker)
            result = rt.submit(ActionRequest(
                sequence=0, requester="t",
                capability=Capability.NETWORK_TELNET_SESSION,
                target=f"telnet://{HOST}:23", purpose="telnet-session",
                timeout_seconds=5), mission)
            self.assertEqual(result.broker_result.decision.decision.value, "deny")
            self.assertFalse(result.broker_result.capability_invoked)
            self.assertIsNone(result.execution)
            # No telnet execution evidence and no finding.
            self.assertEqual([r for r in ledger.all_records()
                              if r.get("producer") == "telnet"], [])
        finally:
            ledger.close()


# ---------------------------------------------------------------------------
# mediator bounds + replay
# ---------------------------------------------------------------------------

def _allow(request):
    return PolicyDecision(
        sequence=request.sequence, decision=Decision.ALLOW, reason="ok",
        capability=request.capability, target=request.target)


class MediatorBounds(_Base):
    def test_replay_prevention(self):
        mission = self.mission()
        store = self.store()
        profile = store.get_target(self.mission_id)
        spec = build_telnet_spec(mission, profile)
        mediator = TelnetMediator(session_fn=make_fake_session())
        req = ActionRequest(sequence=0, requester="t",
                            capability=Capability.NETWORK_TELNET_SESSION,
                            target=f"telnet://{HOST}:23", purpose="telnet-session",
                            timeout_seconds=5)
        a = mediator.invoke(request=req, profile=profile, spec=spec,
                            invocation_id="TEL-1", run_id="run-1",
                            decision=_allow(req))
        self.assertEqual(a.state, TelnetState.SUCCESS)
        b = mediator.invoke(request=req, profile=profile, spec=spec,
                            invocation_id="TEL-1", run_id="run-1",
                            decision=_allow(req))
        self.assertEqual(b.state, TelnetState.DENIED)
        self.assertIn("replay", b.error)

    def test_timeout_bounds(self):
        mission = self.mission()
        store = self.store()
        profile = store.get_target(self.mission_id)
        spec = build_telnet_spec(mission, profile)
        zero = TelnetSessionSpec(
            target=HOST, port=23, username="root", password="",
            commands=spec.commands, flag_command=spec.flag_command,
            flag_pattern=spec.flag_pattern, timeout_seconds=0)
        mediator = TelnetMediator(session_fn=make_fake_session())
        req = ActionRequest(sequence=0, requester="t",
                            capability=Capability.NETWORK_TELNET_SESSION,
                            target=f"telnet://{HOST}:23", purpose="telnet-session")
        out = mediator.invoke(request=req, profile=profile, spec=zero,
                              invocation_id="TEL-T", run_id="run-1",
                              decision=_allow(req))
        self.assertEqual(out.state, TelnetState.DENIED)
        self.assertEqual(out.error, "timeout-invalid")

    def test_mediator_constructor_rejects_bad_bounds(self):
        with self.assertRaises(ValueError):
            TelnetMediator(max_session_bytes=0)
        with self.assertRaises(ValueError):
            TelnetMediator(timeout_seconds=0)

    def test_session_receives_bounded_max_bytes(self):
        calls = []
        mission = self.mission()
        store = self.store()
        profile = store.get_target(self.mission_id)
        spec = build_telnet_spec(mission, profile)
        mediator = TelnetMediator(session_fn=make_fake_session(calls=calls),
                                  max_session_bytes=1234)
        req = ActionRequest(sequence=0, requester="t",
                            capability=Capability.NETWORK_TELNET_SESSION,
                            target=f"telnet://{HOST}:23", purpose="telnet-session",
                            timeout_seconds=5)
        mediator.invoke(request=req, profile=profile, spec=spec,
                        invocation_id="TEL-B", run_id="run-1",
                        decision=_allow(req))
        self.assertEqual(calls[0]["max_bytes"], 1234)
        self.assertEqual(calls[0]["password"], "")   # blank, explicit usage

    def test_password_not_persisted_in_evidence(self):
        result = self.drive(self.mission(), self.store(),
                            make_fake_session())
        ledger_text = (self.runs / result.run.run_id /
                       "evidence.jsonl").read_text()
        # The password value is never persisted; only presence/decision are.
        self.assertNotIn('"password"', ledger_text)
        self.assertIn('"auth_decision"', ledger_text)
        self.assertIn('"authenticated"', ledger_text)


# ---------------------------------------------------------------------------
# full mission: B/C/D + finding + verification + falsification + COMPLETE
# ---------------------------------------------------------------------------

class FullMission(_Base):
    def _run(self, **telnet_over):
        mission = self.mission(**telnet_over)
        result = self.drive(mission, self.store(), make_fake_session())
        return mission, result

    def test_evidence_hashing_and_candidate(self):
        _mission, result = self._run()
        recs = self.records(result.run.run_id, producer="telnet")
        self.assertTrue(recs)
        telnet = recs[0]["payload"]["telnet_result"]
        flag_cmds = [c for c in telnet["commands"]
                     if c["command"] == "cat flag.txt"]
        self.assertTrue(flag_cmds)
        self.assertTrue(flag_cmds[0]["output_sha256"])
        self.assertEqual(telnet["flag"], CANDIDATE)
        self.assertEqual(telnet["auth_decision"], "accepted")
        self.assertIs(telnet["provider_untrusted"], True)

    def test_independent_verification(self):
        _mission, result = self._run()
        run_id = result.run.run_id
        verifier = self.records(run_id, producer="verifier")
        self.assertTrue(verifier)
        payload = verifier[-1]["payload"]
        self.assertEqual(payload["kind"], "telnet-verification-result")
        self.assertEqual(payload["classification"], "supported")
        self.assertTrue(all(payload["checks"].values()))
        # distinct invocation from the primary flag observation.
        telnet = self.records(run_id, producer="telnet")[0]["payload"][
            "telnet_result"]
        self.assertNotEqual(payload["invocation_id"],
                            telnet["invocation_id"])

    def test_falsification_recorded(self):
        _mission, result = self._run()
        run_id = result.run.run_id
        falsifier = self.records(run_id, producer="falsifier")
        self.assertTrue(falsifier)
        self.assertEqual(falsifier[0]["payload"]["kind"], "challenge")
        # the falsifier ran a distinct negative-control Telnet session.
        neg = [r for r in self.records(run_id, kind="request")
               if "mode=negative-control" in (r.get("purpose") or "")]
        self.assertTrue(neg)
        # Finding remained VERIFIED (negative control did not show the flag).
        findings = self.records(run_id, kind="finding")
        self.assertEqual(findings[-1]["state"], "verified")

    def test_full_mission_reaches_complete(self):
        _mission, result = self._run()
        self.assertEqual(result.run.state, "completed")
        self.assertEqual(result.gate_verdict, "complete")
        self.assertTrue(result.verified)

    def test_probe_evidence_present(self):
        _mission, result = self._run()
        probes = self.records(result.run.run_id, producer="probe")
        self.assertTrue(probes)
        payload = probes[0]["payload"]
        self.assertIs(payload["allowed"], True)
        self.assertEqual(payload["invariant"],
                         "authorized-telnet-endpoint-reachable-and-authenticated")

    def test_result_distinguishes_raw_hash_and_submission(self):
        _mission, result = self._run()
        telnet = self.records(result.run.run_id, producer="telnet")[0][
            "payload"]["telnet_result"]
        self.assertEqual(telnet["raw_flag"], CANDIDATE)
        self.assertEqual(telnet["flag"], CANDIDATE)
        self.assertEqual(telnet["flag_sha256"], _sha(CANDIDATE))
        # the SHA-256 is NOT the flag.
        self.assertNotEqual(telnet["flag_sha256"], telnet["raw_flag"])
        # HTB submission representation derived from the raw candidate.
        self.assertEqual(telnet["submission_flag"], "HTB{" + CANDIDATE + "}")
        self.assertEqual(telnet["submission_sha256"],
                         _sha("HTB{" + CANDIDATE + "}"))
        self.assertNotEqual(telnet["submission_sha256"], telnet["flag_sha256"])
        # provenance: candidate came specifically from `cat flag.txt`.
        self.assertEqual(telnet["flag_source_command"], "cat flag.txt")
        self.assertEqual(telnet["flag_output_sha256"], _sha(CANDIDATE))
        self.assertEqual(telnet["candidate_count"], 1)
        self.assertIs(telnet["candidate_valid"], True)

    def test_candidate_sourced_from_flag_command_only(self):
        # A decoy 32-hex in the probe command output must NOT be used.
        decoy = "fedcba9876543210fedcba9876543210"
        result = self.drive(self.mission(), self.store(),
                            make_fake_session(extra_outputs={"pwd": decoy}))
        telnet = self.records(result.run.run_id, producer="telnet")[0][
            "payload"]["telnet_result"]
        self.assertEqual(result.flag, CANDIDATE)
        self.assertNotEqual(result.flag, decoy)
        self.assertEqual(telnet["flag_source_command"], "cat flag.txt")

    def test_banner_or_non_flag_output_hex_not_used(self):
        # If the flag command output lacks the candidate, it is ABSENT even
        # if other 32-hex strings exist elsewhere in the session.
        decoy = "fedcba9876543210fedcba9876543210"
        result = self.drive(self.mission(), self.store(), make_fake_session(
            extra_outputs={"cat flag.txt": "nothing here", "ls": decoy}))
        self.assertIsNone(result.flag)
        self.assertFalse(result.verified)

    def test_auth_failure_no_finding(self):
        mission = self.mission()
        result = self.drive(mission, self.store(),
                            make_fake_session(auth_ok=False))
        self.assertIsNone(result.flag)
        self.assertFalse(result.verified)
        # no verified finding; gate refuses (D also fails: probe not auth'd).
        findings = self.records(result.run.run_id, kind="finding")
        self.assertFalse([f for f in findings if f.get("state") == "verified"])


class _StubVPN:
    def status(self):
        return {"state": "disconnected", "history": []}

    def connect(self, *a, **k):
        return self.status()

    def disconnect(self):
        return self.status()


class OperationsPath(_Base):
    """The normal product path: TESTING/HTB -> /operations/start."""

    def test_normal_operations_start_reaches_complete(self):
        import re
        calls = []
        set_telnet_mediator(TelnetMediator(
            session_fn=make_fake_session(calls=calls)))
        self.addCleanup(set_telnet_mediator, None)
        mode = ModeManager()
        mode.set(Mode.TESTING, "htb")
        cfg = RaphaelHTTPConfig(
            sessions_root=self.sessions, runs_root=self.runs,
            mode_manager=mode, target_store=self.store(),
            vpn_manager=_StubVPN())
        router = build_router()
        mission = self.mission()
        resp = dispatch(Request(method="POST", path="/sessions", body={
            "workspace_root": str(self.ws), "project_name": "d12",
            "mission": mission.to_dict()}), cfg, router)
        self.assertEqual(resp.status, 201, resp.body)
        sid = resp.body["session_id"]
        resp = dispatch(Request(method="POST", path="/operations/start",
                                body={"session_id": sid}), cfg, router)
        self.assertEqual(resp.status, 200, resp.body)
        match = re.search(r"/operations/([0-9T]+_[0-9a-f]+)", resp.body)
        self.assertIsNotNone(match, resp.body[:200])
        run_id = match.group(1)
        harness = json.loads((self.runs / run_id / "harness.json").read_text())
        self.assertEqual(harness["state"], "completed")
        self.assertEqual(harness["gate_verdict"], "complete")
        # primary + verifier + negative-control + probe sessions.
        self.assertGreaterEqual(len(calls), 4)


if __name__ == "__main__":
    unittest.main()
