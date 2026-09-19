"""tests.c1a_testkit — shared helpers for C1A test modules.

NOT a test module (no ``test_`` prefix) so unittest discovery ignores it.
The inert provider double is TEST INFRASTRUCTURE and is never the real
T3MP3ST provider.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from raphael_ibm_bob.adapters.t3mp3st_adapter import InertProviderDouble
from raphael_ibm_bob.broker import BOBBroker
from raphael_ibm_bob.c1a_authorization import C1AAuthorizationBinding
from raphael_ibm_bob.contracts import ActionRequest, Capability, Mission
from raphael_ibm_bob.evidence_ledger import EvidenceLedger
from raphael_ibm_bob.policy import BOBPolicy
from raphael_ibm_bob.runtime import BOBRuntime
from raphael_ibm_bob.workspace import Workspace

DEFAULT_TIMEOUT = 10.0


class CountingInertProvider(InertProviderDouble):
    """Inert provider double that records invocation count (test only).

    ``InertProviderDouble.invoke`` already increments ``self.calls``; this
    subclass exists only to give tests a clearly-named counter.
    """

    pass


def make_workspace(prefix: str = "c1a_test_"):
    base = Path(tempfile.mkdtemp(prefix=prefix))
    (base / "fixtures").mkdir()
    fixture = base / "fixtures" / "sink.bin"
    fixture.write_bytes(b"RAPHAEL-C1A-FIXTURE-001\n")
    other = base / "fixtures" / "other.bin"
    other.write_bytes(b"OTHER\n")
    return base, fixture, other


def make_mission(root: Path, scope=None) -> Mission:
    return Mission(
        mission_id="M-c1a",
        description="c1a mission",
        scope=str(root) if scope is None else scope,
        criteria=["c1a criterion"],
    )


def make_stack(provider=None, scope=None, with_ledger=True,
               default_timeouts=None):
    root, fixture, other = make_workspace()
    workspace = Workspace(root)
    ledger = None
    if with_ledger:
        ledger = EvidenceLedger(root / "runs" / "run-c1a")
    policy = BOBPolicy(workspace)
    auth = C1AAuthorizationBinding()
    broker = BOBBroker(
        policy, workspace, ledger=ledger, c1a_provider=provider,
        c1a_authorization=auth, default_timeouts=default_timeouts)
    runtime = BOBRuntime(broker)
    mission = make_mission(root, scope=scope)
    return SimpleNamespace(
        root=root, fixture=fixture, other=other, workspace=workspace,
        ledger=ledger, policy=policy, auth=auth, broker=broker,
        runtime=runtime, mission=mission)


def c1a_request(target, timeout=DEFAULT_TIMEOUT, sequence=0,
                finding_id=None, requester="c1a"):
    return ActionRequest(
        sequence=sequence,
        requester=requester,
        capability=Capability.C1A_STATIC_FILE_INSPECT,
        target=str(target),
        purpose="c1a-proof",
        finding_id=finding_id,
        timeout_seconds=timeout,
    )


def cleanup(root: Path) -> None:
    import shutil
    shutil.rmtree(root, ignore_errors=True)


__all__ = [
    "CountingInertProvider",
    "DEFAULT_TIMEOUT",
    "InertProviderDouble",
    "c1a_request",
    "cleanup",
    "make_mission",
    "make_stack",
    "make_workspace",
]
