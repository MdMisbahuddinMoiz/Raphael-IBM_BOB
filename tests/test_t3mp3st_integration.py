"""tests.test_t3mp3st_integration — real T3MP3ST provider integration.

These tests exercise the ACTUAL pinned T3MP3ST checkout (compiled `dist/`)
through the canonical path

    RAPHAEL -> bwrap -> RAPHAEL bridge -> binarySinkScanTool.handler()

They SKIP (not fail) when the external provider checkout or bwrap is not
present, so the governed suite stays green without the external dependency.
When present, they run the real provider; nothing here is a fabricated
fallback.

The provider source is never modified. Provider output is UNTRUSTED.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.c1a_testkit import cleanup, make_stack  # noqa: E402
from raphael_ibm_bob.adapters.t3mp3st_adapter import (  # noqa: E402
    MIN_NODE_VERSION,
    T3MP3STAdapter,
    T3MP3ST_BRIDGE_SHA256,
    ProviderIntegrityError,
    ProviderUnavailableError,
)
from raphael_ibm_bob.c1a_authorization import (  # noqa: E402
    C1AAuthorizationBinding,
)
from raphael_ibm_bob.contracts import (  # noqa: E402
    ActionRequest,
    Capability,
    Decision,
    Mission,
)
from raphael_ibm_bob.isolation_substrate import (  # noqa: E402
    NODE_CLOSURE_LIBS,
    build_t3mp3st_bwrap_argv,
    node_version_ok,
    parse_node_version,
)
from raphael_ibm_bob.provider_runtime import (  # noqa: E402
    ProviderState,
    invoke_governed,
)

#: Real provider checkout (compiled). Override with T3MP3ST_PROVIDER_DIST.
PROVIDER_DIST = os.environ.get(
    "T3MP3ST_PROVIDER_DIST", "/home/moiz/audit-repos/T3MP3ST/dist")
BRIDGE = ROOT_DIR / "provider" / "t3mp3st_bridge.js"
NODE = shutil.which("node")
BWRAP = shutil.which("bwrap")
HAVE_PROVIDER = os.path.isdir(PROVIDER_DIST) and (Path(PROVIDER_DIST) /
                                                 "arsenal" / "binary.js").is_file()

_VULN_SOURCE = (
    "#include <stdio.h>\n"
    "void vulnerable() {\n"
    "  char buffer[100];\n"
    "  gets(buffer);\n"
    "  system(user_input);\n"
    "  strcpy(buffer, src);\n"
    "}\n"
)


def _require_provider():
    if not HAVE_PROVIDER:
        raise unittest.SkipTest(f"T3MP3ST provider dist not present: "
                                f"{PROVIDER_DIST}")
    if not NODE:
        raise unittest.SkipTest("node not installed")
    if not BWRAP:
        raise unittest.SkipTest("bwrap not installed")


class NodeRuntime(unittest.TestCase):
    def test_node_meets_t3mp3st_minimum(self):
        _require_provider()
        version = subprocess.run([NODE, "--version"], capture_output=True,
                                 text=True).stdout.strip()
        self.assertTrue(node_version_ok(version, MIN_NODE_VERSION),
                        f"node {version} < {MIN_NODE_VERSION}")

    def test_parse_node_version(self):
        self.assertEqual(parse_node_version("v22.22.1"), (22, 22, 1))
        self.assertEqual(parse_node_version("22.19.0"), (22, 19, 0))
        self.assertFalse(node_version_ok("v22.18.9", (22, 19, 0)))
        self.assertTrue(node_version_ok("v22.19.0", (22, 19, 0)))
        self.assertTrue(node_version_ok("v23.0.0", (22, 19, 0)))


class ProviderDist(unittest.TestCase):
    def test_direct_handler_module_present(self):
        _require_provider()
        binary = Path(PROVIDER_DIST) / "arsenal" / "binary.js"
        scope = Path(PROVIDER_DIST) / "arsenal" / "local-file-scope.js"
        self.assertTrue(binary.is_file())
        self.assertTrue(scope.is_file())

    def test_binary_module_closure_is_builtins_only(self):
        # The direct handler's compiled imports must be Node builtins +
        # its own sibling module only (no network-capable import chain).
        _require_provider()
        text = (Path(PROVIDER_DIST) / "arsenal" / "binary.js").read_text(
            encoding="utf-8")
        imports = [ln for ln in text.splitlines() if ln.startswith("import")]
        for ln in imports:
            self.assertTrue(
                "from 'fs'" in ln or "from 'path'" in ln
                or "local-file-scope" in ln or "types/index" in ln,
                f"unexpected import in binary.js: {ln!r}")


class DirectHandlerSmoke(unittest.TestCase):
    """Real binary_sink_scan OUTSIDE the sandbox (proves the handler works)."""

    def test_handler_finds_sinks(self):
        _require_provider()
        tmp = tempfile.mkdtemp(prefix="t3m_direct_")
        self.addCleanup(shutil.rmtree, tmp, True)
        fx = Path(tmp) / "sink.c"
        fx.write_text(_VULN_SOURCE)
        probe = (
            "const m = await import("
            f"'{Path(PROVIDER_DIST).as_uri()}/arsenal/binary.js');"
            f"const r = await m.binarySinkScanTool.handler("
            f"{{parameters:{{path:{json.dumps(str(fx))}}}}});"
            "process.stdout.write(JSON.stringify({success:r.success,"
            "output:r.output,hasFindings:Array.isArray(r.findings)}));"
        )
        env = dict(os.environ)
        env["T3MP3ST_SOURCE_ROOT"] = tmp
        out = subprocess.run([NODE, "--input-type=module", "-e", probe],
                             capture_output=True, text=True, env=env,
                             timeout=60)
        self.assertEqual(out.returncode, 0, msg=out.stderr)
        data = json.loads(out.stdout)
        self.assertTrue(data["success"])
        self.assertIn("B-GETS", data["output"])
        self.assertIn("B-CMD-INJECTION", data["output"])


class PathValidation(unittest.TestCase):
    """Real approvedLocalPath() behavior (correction 5)."""

    def _validate(self, root, target):
        _require_provider()
        probe = (
            "const m = await import("
            f"'{Path(PROVIDER_DIST).as_uri()}/arsenal/local-file-scope.js');"
            f"const r = m.approvedLocalPath('binary_sink_scan',"
            f"{json.dumps(target)}, true);"
            "process.stdout.write(JSON.stringify(r));"
        )
        env = dict(os.environ)
        env["T3MP3ST_SOURCE_ROOT"] = root
        out = subprocess.run([NODE, "--input-type=module", "-e", probe],
                             capture_output=True, text=True, env=env,
                             timeout=60)
        self.assertEqual(out.returncode, 0, msg=out.stderr)
        return json.loads(out.stdout)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t3m_path_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = Path(self.tmp) / "fixture"
        self.root.mkdir()
        (self.root / "sink.c").write_text(_VULN_SOURCE)
        self.sibling = Path(self.tmp) / "fixture_evil"
        self.sibling.mkdir()
        (self.sibling / "evil.c").write_text("evil\n")
        (Path(self.tmp) / "outside.c").write_text("outside\n")

    def test_root_accepted(self):
        self.assertTrue(self._validate(str(self.root), str(self.root))["ok"])

    def test_valid_child_accepted(self):
        r = self._validate(str(self.root), str(self.root / "sink.c"))
        self.assertTrue(r["ok"])

    def test_sibling_prefix_rejected(self):
        r = self._validate(str(self.root), str(self.sibling / "evil.c"))
        self.assertFalse(r["ok"])

    def test_traversal_rejected(self):
        r = self._validate(str(self.root), str(self.root / ".." / "outside.c"))
        self.assertFalse(r["ok"])

    def test_outside_rejected(self):
        r = self._validate(str(self.root), str(Path(self.tmp) / "outside.c"))
        self.assertFalse(r["ok"])

    def test_fixture_evil_rejected(self):
        r = self._validate(str(self.root), str(self.sibling))
        self.assertFalse(r["ok"])


@unittest.skipUnless(HAVE_PROVIDER and NODE and BWRAP,
                     "real T3MP3ST provider + node + bwrap required")
class SandboxExecution(unittest.TestCase):
    """Real provider execution inside the hardened bwrap sandbox."""

    def setUp(self):
        self.stack = make_stack(with_ledger=True)
        self.addCleanup(cleanup, self.stack.root)
        self.stack.fixture.write_text(_VULN_SOURCE)
        self.request = ActionRequest(
            sequence=0, requester="real",
            capability=Capability.C1A_STATIC_FILE_INSPECT,
            target=str(self.stack.fixture), purpose="c1a",
            timeout_seconds=30.0)
        decision = self.stack.policy.consult(self.request, self.stack.mission)
        self.binding = C1AAuthorizationBinding().create_binding(
            decision=decision, request=self.request, run_id="run-real",
            workspace_root=str(self.stack.root), timeout_seconds=30.0)

    def _adapter(self, **over):
        kwargs = dict(provider_dist=PROVIDER_DIST)
        kwargs.update(over)
        return T3MP3STAdapter(**kwargs)

    def test_real_provider_executes_in_sandbox(self):
        result = invoke_governed(self._adapter(), self.binding.handoff,
                                 self.request)
        self.assertIs(result.state, ProviderState.SUCCESS,
                      msg=result.error)
        self.assertIn("binary_sink_scan", result.provider_message)

    def test_bridge_receipt_has_no_authority_fields(self):
        result = invoke_governed(self._adapter(), self.binding.handoff,
                                 self.request)
        for key in ("severity", "cwe", "title", "details", "findings",
                    "verdict", "verified", "complete"):
            self.assertNotIn(key, result.to_dict())

    def test_bwrap_argv_mounts_bridge_and_fixture(self):
        argv = build_t3mp3st_bwrap_argv(
            provider_dist=PROVIDER_DIST, bridge_path=str(BRIDGE),
            fixture_path=str(self.stack.fixture),
            bridge_sha256=T3MP3ST_BRIDGE_SHA256,
            run_id="run-real", invocation_id="INV-real")
        argv = list(argv)
        self.assertIn("/provider/t3mp3st_bridge.js", argv)
        self.assertIn("/fixture", argv)
        self.assertIn("/t3mp3st/dist", argv)
        self.assertIn("--unshare-net", argv)
        self.assertIn("--remount-ro", argv)
        self.assertIn("T3MP3ST_SOURCE_ROOT", argv)
        # No whole-tree binds.
        self.assertNotIn("/usr/lib", argv)

    def test_bridge_digest_mismatch_fails_closed(self):
        adapter = self._adapter(bridge_sha256="0" * 64)
        with self.assertRaises(ProviderIntegrityError):
            adapter.invoke(self.binding.handoff, self.request)

    def test_node_minimum_enforced(self):
        # A bogus node path fails closed (integrity precondition).
        adapter = self._adapter(node_path="/no/such/node-xyz")
        with self.assertRaises(ProviderIntegrityError):
            adapter.invoke(self.binding.handoff, self.request)

    def test_unavailable_without_provider_dist(self):
        with self.assertRaises(ProviderUnavailableError):
            T3MP3STAdapter().invoke(self.binding.handoff, self.request)

    def test_network_denied_inside_sandbox(self):
        argv = list(build_t3mp3st_bwrap_argv(
            provider_dist=PROVIDER_DIST, bridge_path=str(BRIDGE),
            fixture_path=str(self.stack.fixture),
            bridge_sha256=T3MP3ST_BRIDGE_SHA256,
            run_id="run-real", invocation_id="INV-net"))
        # Replace the bridge entrypoint with a network probe.
        argv[-1] = ("const net = await import('net');"
                    "try { const s = net.connect(80, '127.0.0.1');"
                    "s.on('error', () => { process.stdout.write('DENIED');"
                    "process.exit(0); });"
                    "setTimeout(()=>{process.stdout.write('OPEN');"
                    "process.exit(0);},1500); }"
                    "catch (e) { process.stdout.write('DENIED'); }")
        argv.insert(-1, "--input-type=module")
        argv.insert(-1, "-e")
        out = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        self.assertIn("DENIED", out.stdout)

    def test_filesystem_root_is_read_only(self):
        argv = list(build_t3mp3st_bwrap_argv(
            provider_dist=PROVIDER_DIST, bridge_path=str(BRIDGE),
            fixture_path=str(self.stack.fixture),
            bridge_sha256=T3MP3ST_BRIDGE_SHA256,
            run_id="run-real", invocation_id="INV-fs"))
        argv[-1] = ("const fs = await import('fs'); let r = [];"
                    "try { fs.writeFileSync('/newfile','x'); r.push('ROOT_W'); }"
                    "catch(e){ r.push('ROOT_RO'); }"
                    "try { fs.writeFileSync('/fixture','x'); r.push('FX_W'); }"
                    "catch(e){ r.push('FX_RO'); }"
                    "process.stdout.write(JSON.stringify(r));")
        argv.insert(-1, "--input-type=module")
        argv.insert(-1, "-e")
        out = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        self.assertIn("ROOT_RO", out.stdout)
        self.assertIn("FX_RO", out.stdout)
        self.assertNotIn("ROOT_W", out.stdout)
        self.assertNotIn("FX_W", out.stdout)

    def test_fixture_mutation_detected(self):
        # The fixture is mounted read-only; a post-run digest must be equal.
        from raphael_ibm_bob.provider_runtime import (
            fixture_digest, fixture_integrity_ok)
        pre = fixture_digest(str(self.stack.fixture))
        invoke_governed(self._adapter(), self.binding.handoff, self.request)
        post = fixture_digest(str(self.stack.fixture))
        self.assertTrue(fixture_integrity_ok(pre, post))

    def test_provider_result_hash_is_deterministic_digest(self):
        r1 = invoke_governed(self._adapter(), self.binding.handoff,
                             self.request)
        r2 = invoke_governed(self._adapter(), self.binding.handoff,
                             self.request)
        self.assertTrue(r1.result_hash.startswith("sha256:"))
        self.assertEqual(r1.result_hash, r2.result_hash)

    def test_independent_reproduction_matches_by_digest(self):
        # Verification compares the provider result_hash of an INDEPENDENT
        # reproduction, never a string match on provider text.
        from raphael_ibm_bob.c1a_verification import (
            C1AVerifier, VerificationOutcome)
        from raphael_ibm_bob.finding import FindingStore
        from raphael_ibm_bob.contracts import Finding, FindingState
        from raphael_ibm_bob.broker import BOBBroker
        from raphael_ibm_bob.policy import BOBPolicy
        from raphael_ibm_bob.runtime import BOBRuntime
        from raphael_ibm_bob.workspace import Workspace

        stack = make_stack(with_ledger=True)
        self.addCleanup(cleanup, stack.root)
        stack.fixture.write_text(_VULN_SOURCE)
        workspace = Workspace(stack.root)
        broker = BOBBroker(
            BOBPolicy(workspace), workspace, ledger=stack.ledger,
            c1a_provider=T3MP3STAdapter(provider_dist=PROVIDER_DIST),
            c1a_authorization=C1AAuthorizationBinding())
        runtime = BOBRuntime(broker)
        mission = Mission(mission_id="M-v", description="v",
                          scope=str(stack.root), criteria=["c"])
        first = runtime.submit(ActionRequest(
            sequence=0, requester="real",
            capability=Capability.C1A_STATIC_FILE_INSPECT,
            target=str(stack.fixture), purpose="c1a", timeout_seconds=30.0),
            mission)
        digest = (first.execution.evidence.get("provider_result") or {}
                  ).get("result_hash")
        self.assertTrue(digest)

        store = FindingStore(stack.ledger)
        finding = store.register(Finding(
            finding_id="F-real", state=FindingState.UNVERIFIED,
            summary="real", target=str(stack.fixture), evidence_ids=[]))
        verifier = C1AVerifier(runtime, stack.ledger, store)
        outcome = verifier.verify(finding, mission,
                                  expected_result_hash=digest)
        self.assertIs(outcome.outcome, VerificationOutcome.VERIFIED)
        self.assertIs(store.get("F-real").state, FindingState.VERIFIED)

    def test_wrong_digest_is_inconclusive(self):
        from raphael_ibm_bob.c1a_verification import (
            C1AVerifier, VerificationOutcome)
        from raphael_ibm_bob.finding import FindingStore
        from raphael_ibm_bob.contracts import Finding, FindingState
        from raphael_ibm_bob.broker import BOBBroker
        from raphael_ibm_bob.policy import BOBPolicy
        from raphael_ibm_bob.runtime import BOBRuntime
        from raphael_ibm_bob.workspace import Workspace

        stack = make_stack(with_ledger=True)
        self.addCleanup(cleanup, stack.root)
        stack.fixture.write_text(_VULN_SOURCE)
        workspace = Workspace(stack.root)
        broker = BOBBroker(
            BOBPolicy(workspace), workspace, ledger=stack.ledger,
            c1a_provider=T3MP3STAdapter(provider_dist=PROVIDER_DIST),
            c1a_authorization=C1AAuthorizationBinding())
        runtime = BOBRuntime(broker)
        mission = Mission(mission_id="M-v2", description="v",
                          scope=str(stack.root), criteria=["c"])
        store = FindingStore(stack.ledger)
        finding = store.register(Finding(
            finding_id="F-real2", state=FindingState.UNVERIFIED,
            summary="real", target=str(stack.fixture), evidence_ids=[]))
        verifier = C1AVerifier(runtime, stack.ledger, store)
        outcome = verifier.verify(finding, mission,
                                  expected_result_hash="sha256:" + "0" * 64)
        self.assertIs(outcome.outcome, VerificationOutcome.INCONCLUSIVE)
        self.assertIs(store.get("F-real2").state, FindingState.UNVERIFIED)


@unittest.skipUnless(HAVE_PROVIDER and NODE and BWRAP,
                     "real T3MP3ST provider + node + bwrap required")
class EndToEndReal(unittest.TestCase):
    """Full governed path with the real provider."""

    def test_real_provider_through_broker(self):
        from raphael_ibm_bob.broker import BOBBroker
        from raphael_ibm_bob.policy import BOBPolicy
        from raphael_ibm_bob.runtime import BOBRuntime
        from raphael_ibm_bob.workspace import Workspace

        stack = make_stack(with_ledger=True)
        self.addCleanup(cleanup, stack.root)
        stack.fixture.write_text(_VULN_SOURCE)
        workspace = Workspace(stack.root)
        broker = BOBBroker(
            BOBPolicy(workspace), workspace, ledger=stack.ledger,
            c1a_provider=T3MP3STAdapter(provider_dist=PROVIDER_DIST),
            c1a_authorization=C1AAuthorizationBinding())
        runtime = BOBRuntime(broker)
        mission = Mission(mission_id="M-real", description="real",
                          scope=str(stack.root), criteria=["c"])
        result = runtime.submit(ActionRequest(
            sequence=0, requester="real",
            capability=Capability.C1A_STATIC_FILE_INSPECT,
            target=str(stack.fixture), purpose="c1a", timeout_seconds=30.0),
            mission)
        self.assertIs(result.broker_result.decision.decision, Decision.ALLOW)
        self.assertTrue(result.execution.success)
        self.assertTrue(result.execution.evidence["provider_untrusted"])
        provider_records = [r for r in stack.ledger.all_records()
                            if r.get("producer") == "provider"]
        self.assertTrue(provider_records)

    def test_real_provider_denied_outside_workspace(self):
        from raphael_ibm_bob.broker import BOBBroker
        from raphael_ibm_bob.policy import BOBPolicy
        from raphael_ibm_bob.runtime import BOBRuntime
        from raphael_ibm_bob.workspace import Workspace

        stack = make_stack(with_ledger=False)
        self.addCleanup(cleanup, stack.root)
        workspace = Workspace(stack.root)
        adapter = T3MP3STAdapter(provider_dist=PROVIDER_DIST)
        broker = BOBBroker(
            BOBPolicy(workspace), workspace,
            c1a_provider=adapter,
            c1a_authorization=C1AAuthorizationBinding())
        runtime = BOBRuntime(broker)
        mission = Mission(mission_id="M", description="x",
                          scope=str(stack.root), criteria=["c"])
        result = runtime.submit(ActionRequest(
            sequence=0, requester="real",
            capability=Capability.C1A_STATIC_FILE_INSPECT,
            target="/etc/hostname", purpose="c1a", timeout_seconds=10.0),
            mission)
        self.assertIs(result.broker_result.decision.decision, Decision.DENY)


class _StubTransportResult:
    def __init__(self, *, stdout=b"", timed_out=False, late_output=False,
                 process_exited=True, exit_code=0, stdout_truncated=False,
                 elapsed=0.1):
        self.stdout_bytes = stdout
        self.stderr_bytes = b""
        self.timed_out = timed_out
        self.late_output = late_output
        self.process_exited = process_exited
        self.exit_code = exit_code
        self.stdout_truncated = stdout_truncated
        self.elapsed_seconds = elapsed


class _StubTransport:
    def __init__(self, result):
        self._result = result
        self.calls = 0

    def execute(self, argv, timeout_seconds, env=None, cwd=None):
        self.calls += 1
        self.last_argv = list(argv)
        return self._result


@unittest.skipUnless(HAVE_PROVIDER and NODE and BWRAP,
                     "real T3MP3ST provider + node + bwrap required")
class FailurePaths(unittest.TestCase):
    """Malformed/timeout/teardown paths fail closed (stub transport)."""

    def setUp(self):
        self.stack = make_stack(with_ledger=False)
        self.addCleanup(cleanup, self.stack.root)
        self.stack.fixture.write_text(_VULN_SOURCE)
        self.request = ActionRequest(
            sequence=0, requester="real",
            capability=Capability.C1A_STATIC_FILE_INSPECT,
            target=str(self.stack.fixture), purpose="c1a",
            timeout_seconds=30.0)
        decision = self.stack.policy.consult(self.request, self.stack.mission)
        self.binding = C1AAuthorizationBinding().create_binding(
            decision=decision, request=self.request, run_id="run-fail",
            workspace_root=str(self.stack.root), timeout_seconds=30.0)

    def _adapter(self, transport):
        return T3MP3STAdapter(provider_dist=PROVIDER_DIST,
                              transport=transport)

    def test_malformed_receipt_fails_closed(self):
        bad = _StubTransport(_StubTransportResult(stdout=b"{not json"))
        result = self._adapter(bad).invoke(self.binding.handoff, self.request)
        self.assertIs(result.state, ProviderState.FAILURE)
        self.assertFalse(result.success)

    def test_non_object_receipt_fails_closed(self):
        bad = _StubTransport(_StubTransportResult(stdout=b"[1,2]"))
        result = self._adapter(bad).invoke(self.binding.handoff, self.request)
        self.assertIs(result.state, ProviderState.FAILURE)

    def test_timeout_never_becomes_success(self):
        slow = _StubTransport(_StubTransportResult(timed_out=True))
        result = self._adapter(slow).invoke(self.binding.handoff, self.request)
        self.assertIs(result.state, ProviderState.TIMEOUT)
        self.assertFalse(result.success)

    def test_unobserved_exit_preserves_orphan(self):
        gone = _StubTransport(_StubTransportResult(process_exited=False))
        result = self._adapter(gone).invoke(self.binding.handoff, self.request)
        self.assertIs(result.state, ProviderState.UNAVAILABLE)
        self.assertTrue(result.orphan_possible)
        self.assertFalse(result.success)

    def test_authority_fields_rejected_even_if_present(self):
        # A hostile/exfiltrated receipt carrying findings must be rejected
        # by the closed schema, never normalized.
        from raphael_ibm_bob.provider_runtime import parse_closed_payload
        evil = json.dumps({
            "results": [], "artifacts": [],
            "provider_message": "x", "operation_id": "op",
            "result_hash": None, "truncated": False,
            "findings": [{"severity": "high"}],
        }).encode()
        from raphael_ibm_bob.provider_runtime import ProviderSchemaError
        with self.assertRaises(ProviderSchemaError):
            parse_closed_payload(evil, 65536)


if __name__ == "__main__":
    unittest.main()
