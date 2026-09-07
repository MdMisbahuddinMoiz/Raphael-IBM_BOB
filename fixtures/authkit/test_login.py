"""fixtures.authkit.test_login — the NAMED test that passes for both v1
(broken) and v2 (fixed).

This is the "named test" the roadmap references. It passes even when
session.py's validate_session is broken, because it only exercises
login.py.
"""

import sys
import unittest

# Make fixtures/ importable when this module is loaded by
# `python -m unittest`.
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent.parent))

from fixtures.authkit.login import check_password, login


class LoginTest(unittest.TestCase):
    def test_known_user_can_log_in(self):
        self.assertEqual(login("alice", "wonderland"), "tok-alice-fresh")
        self.assertEqual(login("bob", "builder"), "tok-bob-fresh")

    def test_wrong_password_is_rejected(self):
        self.assertIsNone(login("alice", "wrong"))
        self.assertIsNone(login("bob", ""))

    def test_unknown_user_is_rejected(self):
        self.assertIsNone(login("mallory", "anything"))

    def test_check_password_helper(self):
        self.assertTrue(check_password("alice", "wonderland"))
        self.assertFalse(check_password("alice", "nope"))


if __name__ == "__main__":
    unittest.main()
