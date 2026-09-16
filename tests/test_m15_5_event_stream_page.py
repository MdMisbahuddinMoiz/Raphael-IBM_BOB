"""tests.test_m15_5_event_stream_page — M15.4.x Event Stream screen.

The Event Stream page is presentation-only: it renders the SAME
authoritative event projection (`harness.events.collect_events`) the
JSON API exposes and subscribes to the SAME SSE endpoint the console
and Decision Trace already use. These tests use the real governed
stack (scripted model + real broker/policy/verifier/falsifier/gate)
and assert on the rendered HTML and the real SSE frames.
"""
from __future__ import annotations

import http.client
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from raphael_ibm_bob.contracts import ActionRequest, Capability, Mission
from raphael_ibm_bob.harness import api
from raphael_ibm_bob.harness.model_run import run_model_mission
from raphael_ibm_bob.harness.providers import DoneSignal
from raphael_ibm_bob.http.app import (
    RaphaelHTTPConfig,
    Request,
    create_server,
    dispatch,
)
from raphael_ibm_bob.http.views import event_stream as es
from raphael_ibm_bob.http.views import event_stream_page as page

PASSING_TEST = (
    "import unittest\n\n\nclass T(unittest.TestCase):\n"
    "    def test_ok(self):\n        self.assertTrue(True)\n"
)


class _Scripted:
    """Deterministic model double: returns queued proposals, then done."""

    def __init__(self, requests):
        self._queue = list(requests)

    def propose(self, context):
        if not self._queue:
            raise DoneSignal("done")
        return self._queue.pop(0)


class _EventStreamCase(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="m154x_"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.ws = self.base / "ws"
        (self.ws / "src").mkdir(parents=True)
        (self.ws / "src" / "__init__.py").write_text("", encoding="utf-8")
        (self.ws / "src" / "cand.txt").write_text("OK\n", encoding="utf-8")
        (self.ws / "src" / "test_ok.py").write_text(PASSING_TEST,
                                                     encoding="utf-8")
        self.sessions = self.base / "sessions"
        self.runs = self.base / "runs"
        self.cfg = RaphaelHTTPConfig(sessions_root=self.sessions,
                                     runs_root=self.runs,
                                     host="127.0.0.1", port=0)
        self.server = create_server(self.cfg)
        self.addCleanup(self.server.server_close)
        threading.Thread(target=self.server.serve_forever,
                         daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    # --- fixtures -------------------------------------------------------

    def mission(self) -> Mission:
        return Mission(
            mission_id="M-events", description="Audit the governed operation",
            scope="src/",
            criteria=["reproduced", "remediated", "verified",
                      "falsification survived", "gate approval"],
            problem={"symptom_target": "src/cand.txt"})

    def _req(self, requester, capability, target, purpose):
        return ActionRequest(sequence=0, requester=requester,
                             capability=capability, target=target,
                             purpose=purpose)

    def _session(self):
        return api.create_session(
            mission=self.mission(), workspace_root=self.ws,
            sessions_root=self.sessions, model="stub-model",
            provider="stub-provider")

    def complete_run(self):
        session = self._session()
        requests = [
            self._req("skill:read-file", Capability.READ,
                      "src/cand.txt", "inspect"),
            self._req("skill:run-test", Capability.RUN_TEST,
                      "src/test_ok.py", "run tests"),
            self._req("skill:write-file", Capability.WRITE,
                      "src/cand.txt", "content=OK\n"),
        ]
        result = run_model_mission(
            session, self.mission(), self.ws, runs_root=self.runs,
            model=_Scripted(requests), probe=lambda: True, max_turns=6,
            sessions_root=self.sessions)
        return result.run.run_id, result

    def deny_run(self):
        session = self._session()
        requests = [self._req("skill:read-file", Capability.READ,
                              "/etc/hostname", "escape")]
        result = run_model_mission(
            session, self.mission(), self.ws, runs_root=self.runs,
            model=_Scripted(requests), probe=None, max_turns=3,
            sessions_root=self.sessions)
        return result.run.run_id, result

    def render(self, run_id):
        response = dispatch(
            Request(method="GET", path=f"/operations/{run_id}/events"),
            self.cfg)
        return response.status, response.content_type, response.body

    def http(self, method, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        conn.request(method, path)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", "replace")
        ctype = resp.getheader("Content-Type")
        conn.close()
        return resp.status, ctype, body


class RouteAndRender(_EventStreamCase):
    def test_A_route_exists(self):
        run_id, _ = self.complete_run()
        status, ctype, html = self.render(run_id)
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("Event Stream", html)

    def test_B_valid_run_renders_page(self):
        run_id, _ = self.complete_run()
        _, _, html = self.render(run_id)
        self.assertIn("EVENT STREAM", html)
        self.assertIn(run_id, html)
        self.assertIn("RUN INSPECTOR", html)

    def test_C_missing_run_is_404(self):
        status, _, body = self.render("does-not-exist")
        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "RUN_NOT_FOUND")

    def test_D_page_contains_real_persisted_events(self):
        run_id, _ = self.complete_run()
        events = api.get_events(run_id, self.runs)
        self.assertTrue(events)
        _, _, html = self.render(run_id)
        self.assertEqual(html.count('class="evrow"'), len(events))

    def test_E_sse_url_is_correct(self):
        run_id, _ = self.complete_run()
        _, _, html = self.render(run_id)
        self.assertIn(f"/runs/{run_id}/events/stream", html)

    def test_F_event_types_render(self):
        run_id, _ = self.complete_run()
        events = api.get_events(run_id, self.runs)
        types = {e.get("type") for e in events}
        _, _, html = self.render(run_id)
        for event_type in types:
            self.assertIn(event_type, html, event_type)
        for expected in ("SESSION_CREATED", "MISSION_STARTED",
                         "ACTION_REQUESTED", "POLICY_DECISION",
                         "EXECUTION_RESULT", "EVIDENCE_RECORDED",
                         "GATE_EVALUATED", "RUN_COMPLETED"):
            self.assertIn(expected, html, expected)

    def test_G_terminal_state_renders(self):
        run_id, result = self.complete_run()
        self.assertTrue(api.get_run(run_id, self.runs).is_terminal())
        _, _, html = self.render(run_id)
        self.assertIn("TERMINAL STATE REACHED", html)
        self.assertIn('class="gate-final">COMPLETE', html)
        self.assertIn("RUN_COMPLETED", html)

    def test_H_ibm_bob_policy_renders(self):
        run_id, _ = self.complete_run()
        _, _, html = self.render(run_id)
        self.assertIn('data-cat="policy"', html)
        self.assertIn("POLICY_DECISION", html)
        self.assertIn("ALLOW", html)
        self.assertIn("BOB POLICY", html)

    def test_H2_deny_reason_is_recorded_reason(self):
        run_id, _ = self.deny_run()
        gate = api.get_gate(run_id, self.runs)
        self.assertEqual(gate["decision"], "refuse")
        deny = [r for r in api.get_evidence(run_id, self.runs)
                if r.get("kind") == "decision"
                and r.get("decision") == "deny"]
        self.assertTrue(deny)
        _, _, html = self.render(run_id)
        self.assertIn("DENY", html)
        self.assertIn(deny[-1].get("reason"), html)

    def test_I_no_hidden_chain_of_thought(self):
        run_id, _ = self.complete_run()
        _, _, html = self.render(run_id)
        for forbidden in ("chain of thought", "chain-of-thought",
                          "scratchpad", "thought process", "<thinking",
                          "internal monologue"):
            self.assertNotIn(forbidden, html.lower())

    def test_J_no_credentials(self):
        run_id, _ = self.complete_run()
        _, _, html = self.render(run_id)
        self.assertNotIn("sk-", html)
        self.assertNotIn("api_key", html)
        self.assertNotIn("api-key", html)


class ClientBehaviour(_EventStreamCase):
    def test_K_filtering_is_client_side(self):
        run_id, _ = self.complete_run()
        _, _, html = self.render(run_id)
        self.assertIn('data-filter="policy"', html)
        self.assertIn('data-cat="policy"', html)
        self.assertIn('id="search"', html)
        self.assertIn('id="follow"', html)
        self.assertIn("applyFilter", html)
        # Client-side filtering only: no server-side search route/query.
        self.assertNotIn("?filter=", html)

    def test_L_details_reflect_persisted_payload(self):
        run_id, _ = self.complete_run()
        events = api.get_events(run_id, self.runs)
        evidence_ids = [e.get("evidence_id") for e in events
                        if e.get("type") == "EVIDENCE_RECORDED"]
        evidence_ids = [eid for eid in evidence_ids if eid]
        self.assertTrue(evidence_ids)
        _, _, html = self.render(run_id)
        for evidence_id in evidence_ids:
            self.assertIn(evidence_id, html)
        self.assertIn("data-env=", html)

    def test_M_page_is_read_only(self):
        run_id, _ = self.complete_run()
        before = len(api.get_evidence(run_id, self.runs))
        status, _, _ = self.render(run_id)
        self.assertEqual(status, 200)
        after = len(api.get_evidence(run_id, self.runs))
        self.assertEqual(before, after)

    def test_N_no_direct_execution_controls(self):
        run_id, _ = self.complete_run()
        _, _, html = self.render(run_id)
        self.assertNotIn("<form", html)
        self.assertNotIn('method="post"', html)
        self.assertNotIn("operations/start", html)
        self.assertNotIn("runs/model", html)
        self.assertNotIn("execute_capability", html)
        # The only interactive elements are filter/search/follow/expand.
        self.assertIn('class="chip', html)
        self.assertIn('id="search"', html)
        self.assertIn('class="evhead"', html)

    def test_O_existing_sse_still_works(self):
        run_id, _ = self.complete_run()
        frames = list(es.iter_frames(run_id, runs_root=self.runs))
        emitted = [f for f in frames
                   if f.startswith(b"event: RAPHAEL_EVENT")]
        events = api.get_events(run_id, self.runs)
        self.assertEqual(len(emitted), len(events))
        self.assertTrue(frames[-1].startswith(b"event: stream_end"))

    def test_served_over_http_as_html(self):
        run_id, _ = self.complete_run()
        status, ctype, body = self.http(
            "GET", f"/operations/{run_id}/events")
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("Event Stream", body)


class Governance(unittest.TestCase):
    def test_route_and_view_use_harness_api_only(self):
        root = Path(page.__file__).resolve().parents[2]
        sources = {
            "routes/operations.py": (root / "http" / "routes" /
                                     "operations.py").read_text("utf-8"),
            "views/event_stream_page.py":
                (root / "http" / "views" /
                 "event_stream_page.py").read_text("utf-8"),
        }
        for name, src in sources.items():
            self.assertIn("harness import api", src, name)
            for token in ("execute_capability(", "import subprocess",
                          "Popen", "import socket", "import urllib",
                          "from urllib", "import http.client",
                          "import requests", "urlopen", "BOBBroker",
                          "BOBPolicy", "BOBRuntime", "BOBQualityGate",
                          "GateVerdict", "write_seal"):
                self.assertNotIn(token, src, f"{token} in {name}")

    def test_no_second_event_store(self):
        src = (Path(page.__file__).resolve().parents[2] / "http" /
               "views" / "event_stream_page.py").read_text("utf-8")
        for token in ("append_evidence", "append_gate", "EvidenceLedger",
                      "LedgerWriter", "run_model_mission(", "def propose("):
            self.assertNotIn(token, src, token)

    def test_classification_covers_all_event_types(self):
        from raphael_ibm_bob.harness.events import EVENT_TYPES
        for event_type in EVENT_TYPES:
            env = {"sequence": 1, "type": event_type, "run_id": "r",
                   "timestamp": None, "payload": {}}
            classified = page._classify(env)
            self.assertIn(classified["cat"],
                          {key for key, _ in page.FILTERS})


if __name__ == "__main__":
    unittest.main()
