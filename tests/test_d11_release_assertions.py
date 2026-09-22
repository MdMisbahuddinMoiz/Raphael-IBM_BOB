"""tests.test_d11_release_assertions — D11 release-freeze assertions.

Contractual checks only: the demo entrypoint and documentation exist, the demo
evidence bundles carry the PERSISTED gate decisions (not invented ones), the
gate presentation reproduces the persisted verdict, no secret material ships in
the demo package, and the demo tooling cannot manufacture COMPLETE or bypass the
Broker/Policy boundary.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from raphael_ibm_bob.http.views.decision_trace import gate_breakdown

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "demo"


class EntrypointsAndDocs(unittest.TestCase):
    def test_demo_entrypoint_exists_and_executable(self):
        entry = REPO / "scripts" / "run_hackathon_demo.sh"
        self.assertTrue(entry.is_file(), "demo entrypoint missing")
        self.assertTrue(entry.stat().st_mode & 0o111, "entrypoint not executable")

    def test_expected_release_documentation_exists(self):
        for rel in ("docs/HACKATHON_DEMO.md", "docs/DEMO_CHECKLIST.md",
                    "demo/README.md", "scripts/hackathon_demo.py",
                    "scripts/demo_export.py"):
            self.assertTrue((REPO / rel).is_file(), f"missing {rel}")
        self.assertIn("Hackathon Demo",
                      (REPO / "README.md").read_text(encoding="utf-8"))

    def test_demo_docs_state_the_claim_boundary(self):
        doc = (REPO / "docs" / "HACKATHON_DEMO.md").read_text(
            encoding="utf-8").lower()
        # The boundary must be stated explicitly...
        self.assertIn("claim boundary", doc)
        self.assertIn("did not expose", doc)
        self.assertIn("do **not** claim", doc)
        # ...and the generated transcripts must never assert a captured flag.
        for name in ("success", "refusal"):
            text = (DEMO / name / "transcript.txt").read_text(
                encoding="utf-8").lower()
            for phrase in ("flag captured", "root flag", "solved breakout",
                           "owned the box"):
                self.assertNotIn(phrase, text, f"{name} transcript overclaims")


class DemoCannotCheat(unittest.TestCase):
    """The demo tooling must not manufacture verdicts or bypass boundaries."""

    FORBIDDEN = (
        "BOBQualityGate",        # must not evaluate the gate itself
        "GateInputs",
        "append_gate",           # must not write gate records
        "execute_capability",    # must not invoke capabilities directly
        "NetworkMediator",       # must not touch the mediator directly
        "BOBBroker",
        "BOBPolicy",
        "BOBRuntime",
    )

    def _demo_sources(self):
        files = [
            REPO / "scripts" / "hackathon_demo.py",
            REPO / "scripts" / "run_hackathon_demo.sh",
            REPO / "scripts" / "demo_export.py",
        ]
        return {f: f.read_text(encoding="utf-8") for f in files}

    def test_no_demo_code_manufactures_complete_or_bypasses_boundary(self):
        for path, text in self._demo_sources().items():
            for token in self.FORBIDDEN:
                self.assertNotIn(
                    token, text,
                    f"{path.name} references forbidden construct {token!r}")

    def test_demo_reads_the_persisted_verdict(self):
        text = (REPO / "scripts" / "hackathon_demo.py").read_text(
            encoding="utf-8")
        # The verdict is READ from the persisted run/gate record.
        self.assertIn('harness.get("gate_verdict")', text)
        self.assertIn("gate_breakdown", text)


class DemoBundles(unittest.TestCase):
    def _bundle(self, name):
        d = DEMO / name
        return (json.loads((d / "run.json").read_text(encoding="utf-8")),
                json.loads((d / "gate.json").read_text(encoding="utf-8")),
                json.loads((d / "summary.json").read_text(encoding="utf-8")),
                (d / "ledger.jsonl").read_text(encoding="utf-8"))

    def test_success_bundle_has_persisted_complete_decision(self):
        run, gate, summary, ledger = self._bundle("success")
        self.assertEqual(run["state"], "completed")
        self.assertEqual(run["gate_verdict"], "complete")
        self.assertEqual(gate["decision"], "complete")
        self.assertEqual(summary["conditions"]["count"], "7/7")
        self.assertEqual(summary["conditions"]["failed"], [])
        # real independent probe evidence is present in the persisted ledger.
        records = [json.loads(line) for line in ledger.splitlines()
                   if line.strip()]
        probes = [r for r in records
                  if r.get("kind") == "evidence"
                  and r.get("producer") == "probe"]
        self.assertTrue(probes, "no producer=probe record persisted")
        self.assertIs(probes[0]["payload"]["allowed"], True)

    def test_refusal_bundle_has_persisted_refuse_decision(self):
        run, gate, summary, ledger = self._bundle("refusal")
        self.assertEqual(run["state"], "refused")
        self.assertEqual(run["gate_verdict"], "refuse")
        self.assertEqual(gate["decision"], "refuse")
        self.assertEqual(summary["conditions"]["count"], "6/7")
        self.assertIn("D:independent-behavior-probe",
                      summary["conditions"]["failed"])

    def test_gate_presentation_matches_persisted_verdict(self):
        for name, expect_verdict in (("success", "complete"),
                                     ("refusal", "refuse")):
            _run, gate, summary, _ledger = self._bundle(name)
            passed, failed, unknown, names = gate_breakdown(gate)
            decision = (gate.get("decision") or "").lower()
            self.assertEqual(decision, expect_verdict)
            if decision == "complete":
                self.assertEqual(failed, [])
                self.assertEqual(len(passed), len(names))
            else:
                self.assertTrue(failed)
            # the exported summary agrees with the presentation layer.
            self.assertEqual(summary["conditions"]["passed"], passed)
            self.assertEqual(summary["conditions"]["failed"], failed)

    def test_no_secret_material_in_demo_package(self):
        patterns = ("BEGIN RSA PRIVATE KEY", "BEGIN OPENVPN", "PRIVATE KEY",
                    "-----BEGIN", "auth-user-pass", ".ovpn", "client.key",
                    "Authorization: Bearer")
        for path in DEMO.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in patterns:
                self.assertNotIn(pat, text, f"{path} contains {pat!r}")


if __name__ == "__main__":
    unittest.main()
