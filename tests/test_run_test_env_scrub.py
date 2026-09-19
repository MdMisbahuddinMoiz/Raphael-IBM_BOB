"""tests.test_run_test_env_scrub — RUN_TEST must not leak secrets."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from raphael_ibm_bob import capabilities  # noqa: E402
from raphael_ibm_bob.broker import BOBBroker  # noqa: E402
from raphael_ibm_bob.contracts import ActionRequest, Capability, Mission  # noqa: E402
from raphael_ibm_bob.policy import BOBPolicy  # noqa: E402
from raphael_ibm_bob.workspace import Workspace  # noqa: E402

_DUMPING_TEST = '''\
import os
import unittest
from pathlib import Path


class T(unittest.TestCase):
    def test_dump_env(self):
        dump = Path(__file__).with_suffix(".envdump")
        dump.write_text("\\n".join(sorted(os.environ)), encoding="utf-8")
        self.assertTrue(True)
'''


class EnvScrub(unittest.TestCase):
    def test_scrubbed_env_excludes_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(tmp)
            with mock.patch.dict(os.environ, {
                    "AWS_SECRET_ACCESS_KEY": "leak",
                    "GITHUB_TOKEN": "leak2",
                    "LANG": "C"}, clear=False):
                env = capabilities._scrubbed_env(ws)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", env)
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertEqual(env["PYTHONPATH"], str(ws.root))

    def test_run_test_child_does_not_see_secrets(self):
        tmp = tempfile.TemporaryDirectory(prefix="c1a_env_")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "src").mkdir()
        test_file = root / "src" / "test_envdump.py"
        test_file.write_text(_DUMPING_TEST, encoding="utf-8")
        workspace = Workspace(root)
        policy = BOBPolicy(workspace)
        broker = BOBBroker(policy, workspace)
        mission = Mission(mission_id="M", description="x", scope=str(root),
                          criteria=["c"])
        with mock.patch.dict(os.environ, {
                "AWS_SECRET_ACCESS_KEY": "leak",
                "GITHUB_TOKEN": "leak2"}, clear=False):
            result = broker.submit(ActionRequest(
                sequence=0, requester="t", capability=Capability.RUN_TEST,
                target=str(test_file), purpose="required-test"), mission)
        self.assertTrue(result.execution.success,
                        msg=result.execution.error)
        dump = test_file.with_suffix(".envdump")
        self.assertTrue(dump.is_file())
        env_text = dump.read_text(encoding="utf-8")
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", env_text)
        self.assertNotIn("GITHUB_TOKEN", env_text)
        self.assertNotIn("leak", env_text)


if __name__ == "__main__":
    unittest.main()
