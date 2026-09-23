"""tests.test_d12_1_authz_binding — mediator authorization-decision binding.

G6: the network/telnet mediators execute ONLY when handed the actual
PolicyDecision the Broker obtained for the exact ActionRequest. A missing,
DENY, or mismatched decision must refuse with zero execution.
"""
from __future__ import annotations

import unittest

from raphael_ibm_bob.contracts import (
    ActionRequest,
    Capability,
    Decision,
    PolicyDecision,
)
from raphael_ibm_bob.network_runtime import NetworkMediator, NetworkState
from raphael_ibm_bob.target_profile import TargetStore, build_target_profile
from raphael_ibm_bob.telnet_runtime import (
    TelnetMediator,
    TelnetSessionSpec,
    TelnetState,
)

NET_CAP = Capability.NETWORK_HTTP_REQUEST
TEL_CAP = Capability.NETWORK_TELNET_SESSION


def _allow(request, *, capability=None, target=None, sequence=None):
    return PolicyDecision(
        sequence=request.sequence if sequence is None else sequence,
        decision=Decision.ALLOW, reason="ok",
        capability=capability or request.capability,
        target=target or request.target)


def _deny(request, *, capability=None, target=None):
    return PolicyDecision(
        sequence=request.sequence, decision=Decision.DENY, reason="denied",
        capability=capability or request.capability, target=target or request.target)


def _net_profile():
    store = TargetStore()
    store.set_target(build_target_profile(
        mission_id="M", locator="127.0.0.1", allowed_ports=[80],
        allowed_protocols=["http"], scope="127.0.0.1",
        authorization_ref="AUTH"))
    return store.current()


def _tel_profile():
    store = TargetStore()
    store.set_target(build_target_profile(
        mission_id="M", locator="127.0.0.1", allowed_ports=[23],
        allowed_protocols=["telnet"], scope="127.0.0.1",
        authorization_ref="AUTH"))
    return store.current()


def _net_request(target="http://127.0.0.1:80/flag"):
    return ActionRequest(sequence=1, requester="t", capability=NET_CAP,
                         target=target, purpose="network-http-request method=GET",
                         timeout_seconds=5)


def _tel_request(target="telnet://127.0.0.1:23"):
    return ActionRequest(sequence=1, requester="t", capability=TEL_CAP,
                         target=target, purpose="telnet-session",
                         timeout_seconds=5)


def _tel_spec():
    return TelnetSessionSpec(
        target="127.0.0.1", port=23, username="root", password="",
        commands=("pwd",), flag_command="pwd", flag_pattern="[0-9a-f]{32}")


def _fake_opener(tracker):
    def opener(url, method, timeout, max_bytes):
        tracker.append(url)
        return 200, b"ok", False
    return opener


def _fake_session(tracker):
    def session(host, port, username, password, commands, timeout, max_bytes):
        tracker.append(host)
        return {"ok": True, "state": TelnetState.SUCCESS, "error": "",
                "authenticated": True, "auth_decision": "accepted",
                "commands": [{"command": commands[0], "output_sha256": "d",
                              "output_preview": "/root", "bytes": 5, "ok": True}],
                "session_bytes": 10}
    return session


class NetworkDecisionBinding(unittest.TestCase):
    def _run(self, decision):
        tracker = []
        mediator = NetworkMediator(opener=_fake_opener(tracker))
        result = mediator.invoke(
            request=_net_request(), profile=_net_profile(),
            invocation_id="NET-1", run_id="run-1", decision=decision)
        return result, tracker

    def test_valid_allow_executes(self):
        result, tracker = self._run(_allow(_net_request()))
        self.assertIs(result.state, NetworkState.SUCCESS)
        self.assertEqual(len(tracker), 1)

    def test_missing_decision_denied(self):
        result, tracker = self._run(None)
        self.assertIs(result.state, NetworkState.DENIED)
        self.assertEqual(result.error, "authorization-not-allow")
        self.assertEqual(len(tracker), 0)

    def test_deny_decision_denied(self):
        result, tracker = self._run(_deny(_net_request()))
        self.assertIs(result.state, NetworkState.DENIED)
        self.assertEqual(len(tracker), 0)

    def test_wrong_capability_denied(self):
        req = _net_request()
        result, tracker = self._run(_allow(req, capability=Capability.READ))
        self.assertIs(result.state, NetworkState.DENIED)
        self.assertEqual(len(tracker), 0)

    def test_wrong_target_denied(self):
        req = _net_request()
        result, tracker = self._run(
            _allow(req, target="http://127.0.0.1:80/other"))
        self.assertIs(result.state, NetworkState.DENIED)
        self.assertEqual(len(tracker), 0)

    def test_wrong_sequence_denied(self):
        req = _net_request()
        result, tracker = self._run(_allow(req, sequence=999))
        self.assertIs(result.state, NetworkState.DENIED)
        self.assertEqual(len(tracker), 0)


class TelnetDecisionBinding(unittest.TestCase):
    def _run(self, decision):
        tracker = []
        mediator = TelnetMediator(session_fn=_fake_session(tracker))
        result = mediator.invoke(
            request=_tel_request(), profile=_tel_profile(), spec=_tel_spec(),
            invocation_id="TEL-1", run_id="run-1", decision=decision)
        return result, tracker

    def test_valid_allow_executes(self):
        result, tracker = self._run(_allow(_tel_request()))
        self.assertIs(result.state, TelnetState.SUCCESS)
        self.assertEqual(len(tracker), 1)

    def test_missing_decision_denied(self):
        result, tracker = self._run(None)
        self.assertIs(result.state, TelnetState.DENIED)
        self.assertEqual(result.error, "authorization-not-allow")
        self.assertEqual(len(tracker), 0)

    def test_deny_decision_denied(self):
        result, tracker = self._run(_deny(_tel_request()))
        self.assertIs(result.state, TelnetState.DENIED)
        self.assertEqual(len(tracker), 0)

    def test_wrong_capability_denied(self):
        result, tracker = self._run(
            _allow(_tel_request(), capability=Capability.READ))
        self.assertIs(result.state, TelnetState.DENIED)
        self.assertEqual(len(tracker), 0)

    def test_wrong_target_denied(self):
        result, tracker = self._run(
            _allow(_tel_request(), target="telnet://127.0.0.1:2323"))
        self.assertIs(result.state, TelnetState.DENIED)
        self.assertEqual(len(tracker), 0)


if __name__ == "__main__":
    unittest.main()
