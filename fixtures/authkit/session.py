"""fixtures.authkit.session — THE ACTUAL DEFECT lives here.

This module is the target of the authkit hero. The defect is:

    `validate_session(token, claimed_user_id)` does NOT reject:
        - expired tokens (TOKENS[token]["expired"] == True)
        - tokens bound to a *different* user (TOKENS[token]["user_id"] != claimed_user_id)

The defect is deterministic and reproducible. The BUGGY version
behaves as if the token is valid regardless of expiration or binding.
"""

from fixtures.authkit.store import lookup_token, known_user


def validate_session(token: str, claimed_user_id: str) -> bool:
    """BUGGY implementation of validate_session.

    Currently buggy: ignores expiration AND ignores user binding.
    """
    rec = lookup_token(token)
    if rec is None:
        return False
    return known_user(claimed_user_id)
