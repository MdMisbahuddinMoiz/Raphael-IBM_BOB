"""demos.c1a_live_hero — end-to-end governed C1A demonstration.

This demo uses the INERT provider double (test infrastructure), never the
real T3MP3ST provider. It demonstrates:

    * REFUSE when C1A is unauthorized (target outside the workspace),
    * the governed C1A path (authorization binding -> bounded provider ->
      untrusted evidence),
    * COMPLETE only through the real QualityGate.

Live proof remains BLOCKED: the real T3MP3ST provider is an external
dependency that is not present. No M1/M2/M5 claim is made.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from raphael_ibm_bob.adapters.t3mp3st_adapter import (  # noqa: E402
    InertProviderDouble,
)
from raphael_ibm_bob.broker import BOBBroker  # noqa: E402
from raphael_ibm_bob.c1a_authorization import C1AAuthorizationBinding  # noqa: E402
from raphael_ibm_bob.contracts import (  # noqa: E402
    ActionRequest,
    Capability,
    Decision,
    Mission,
)
from raphael_ibm_bob.evidence_ledger import EvidenceLedger, digest_id  # noqa: E402
from raphael_ibm_bob.policy import BOBPolicy  # noqa: E402
from raphael_ibm_bob.quality_gate import BOBQualityGate, GateInputs  # noqa: E402
from raphael_ibm_bob.runtime import BOBRuntime  # noqa: E402
from raphael_ibm_bob.workspace import Workspace  # noqa: E402

_PASSING_TEST = textwrap.dedent('''
    import unittest


    class T(unittest.TestCase):
        def test_ok(self):
            self.assertTrue(True)
''').strip() + "\n"


def _step(idx: int, label: str, detail: str = "") -> None:
    print(f"[{idx:02d}] {label}")
    if detail:
        for line in detail.splitlines():
            print(f"     {line}")


def _persist_probe(ledger, ok: bool) -> None:
    payload = {"kind": "probe", "result": "passed" if ok else "failed",
               "allowed": ok}
    ledger.append_evidence(
        evidence_id=digest_id(payload, prefix="PB"), producer="probe",
        request_seq=0, decision_seq=0, result_seq=None, payload=payload)


def _persist_regression(ledger, ok: bool) -> None:
    payload = {"kind": "regression", "result": "passed" if ok else "failed"}
    ledger.append_evidence(
        evidence_id=digest_id(payload, prefix="RG"), producer="regression",
        request_seq=0, decision_seq=0, result_seq=None, payload=payload)


def run_demo(keep: bool = False) -> int:
    base = Path(tempfile.mkdtemp(prefix="c1a_hero_"))
    try:
        fixtures = base / "fixtures"
        fixtures.mkdir()
        fixture = fixtures / "sink.bin"
        fixture.write_bytes(b"RAPHAEL-C1A-HERO\n")
        src = base / "src"
        src.mkdir()
        test_file = src / "test_pass.py"
        test_file.write_text(_PASSING_TEST, encoding="utf-8")

        workspace = Workspace(base)
        ledger = EvidenceLedger(base / "runs" / "hero")
        policy = BOBPolicy(workspace)
        provider = InertProviderDouble()
        broker = BOBBroker(policy, workspace, ledger=ledger,
                           c1a_provider=provider,
                           c1a_authorization=C1AAuthorizationBinding())
        runtime = BOBRuntime(broker)
        mission = Mission(mission_id="M-c1a-hero", description="c1a hero",
                          scope=str(base), criteria=["governed C1A"])

        _step(1, "Unauthorized C1A -> REFUSE",
              "target=/etc/hostname (outside workspace)")
        # The unauthorized probe uses a SEPARATE, ledger-free broker so it
        # cannot pollute the governed run's evidence with an out-of-scope
        # target (the QualityGate evaluates ALL recorded targets).
        probe_runtime = BOBRuntime(BOBBroker(
            policy, workspace, c1a_provider=provider,
            c1a_authorization=C1AAuthorizationBinding()))
        denied = probe_runtime.submit(ActionRequest(
            sequence=0, requester="hero",
            capability=Capability.C1A_STATIC_FILE_INSPECT,
            target="/etc/hostname", purpose="c1a"), mission)
        _step(1, "decision",
              f"decision={denied.broker_result.decision.decision.value} "
              f"reason={denied.broker_result.decision.reason} "
              f"invoked={denied.broker_result.capability_invoked}")
        assert denied.broker_result.decision.decision is Decision.DENY

        _step(2, "Authorized C1A -> governed provider path")
        allowed = runtime.submit(ActionRequest(
            sequence=0, requester="hero",
            capability=Capability.C1A_STATIC_FILE_INSPECT,
            target=str(fixture), purpose="c1a", timeout_seconds=10.0),
            mission)
        _step(2, "result",
              f"decision={allowed.broker_result.decision.decision.value} "
              f"provider_state="
              f"{(allowed.execution.evidence.get('provider_result') or {}).get('state')} "
              f"untrusted={allowed.execution.evidence['provider_untrusted']}")

        _step(3, "RUN_TEST through the boundary")
        test_result = runtime.submit(ActionRequest(
            sequence=0, requester="hero", capability=Capability.RUN_TEST,
            target=str(test_file), purpose="required-test"), mission)
        _step(3, "test", f"success={test_result.execution.success}")

        _persist_probe(ledger, ok=True)
        _persist_regression(ledger, ok=True)

        _step(4, "QualityGate")
        evaluation = BOBQualityGate(ledger).evaluate(GateInputs(
            mission=mission, findings=[], regression_ok=True,
            behavior_probe_ok=True))
        _step(4, "verdict",
              f"verdict={evaluation.verdict.value} "
              f"failed={list(evaluation.failed)}")
        print(f"Gate: {evaluation.verdict.value.upper()}")
        print("Live proof: BLOCKED (this demo uses the inert double; "
              "live_proof_authorized=False)")
        ledger.close()
        return 0 if evaluation.verdict.value == "complete" else 1
    finally:
        if not keep:
            shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    return run_demo(keep=False)


if __name__ == "__main__":
    raise SystemExit(main())
