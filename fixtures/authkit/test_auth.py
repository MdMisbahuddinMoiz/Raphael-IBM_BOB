"""fixtures.authkit.test_auth — invariant tests that EXPOSE the actual
defect in session.py.

These tests fail under the BUGGY validate_session and pass under the
CORRECTED validate_session. They are independent of login.py and
represent the deeper invariants the authkit must satisfy.
"""

import sys
import unittest
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from fixtures.authkit.session import validate_session


class AuthTest(unittest.TestCase):
    def test_expired_token_is_rejected(self):
        # BUG: under the buggy implementation, validate_session returns
        # True for expired tokens.
        self.assertFalse(validate_session("tok-alice-stale", "alice"))
        self.assertFalse(validate_session("tok-bob-stale", "bob"))

    def test_token_bound_to_other_user_is_rejected(self):
        # BUG: under the buggy implementation, a token bound to alice
        # is accepted when bob claims it.
        self.assertFalse(validate_session("tok-cross", "bob"))
        # And a fresh alice token is rejected when a different user
        # claims it.
        self.assertFalse(validate_session("tok-alice-fresh", "bob"))

    def test_valid_token_is_accepted(self):
        self.assertTrue(validate_session("tok-alice-fresh", "alice"))
        self.assertTrue(validate_session("tok-bob-fresh", "bob"))

    def test_unknown_token_is_rejected(self):
        self.assertFalse(validate_session("tok-does-not-exist", "alice"))


if __name__ == "__main__":
    unittest.main()
