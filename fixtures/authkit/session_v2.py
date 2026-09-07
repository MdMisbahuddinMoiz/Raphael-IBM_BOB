"""fixtures.authkit.session_v2 — the CORRECTED validate_session.

The v2 fix is what the runner writes to session.py in the M7 hero. It
satisfies the independent behavior probe and the test_auth invariants.

The v2 fix DOES NOT modify test_login.py or test_auth.py; it only
changes the validate_session implementation.
"""

from fixtures.authkit.store import lookup_token


def validate_session(token: str, claimed_user_id: str) -> bool:
    """CORRECTED implementation.

    Returns True iff:
        - the token is known
        - the token is not expired
        - the token's bound user_id matches the claimed user_id
    """
    rec = lookup_token(token)
    if rec is None:
        return False
    if rec.get("expired"):
        return False
    if rec.get("user_id") != claimed_user_id:
        return False
    return True
