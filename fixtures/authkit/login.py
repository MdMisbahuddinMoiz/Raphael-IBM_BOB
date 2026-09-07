"""fixtures.authkit.login — the SYMPTOM / DECOY lives here.

login.py looks like a plausible place where the bug could be: a typo,
a wrong comparison, an off-by-one. The FIX appears to work, but the
REAL bug is in session.py, not here. This module exists to make
the hero a real planning story rather than a script.
"""

from fixtures.authkit.store import USERS, known_user


def check_password(user_id: str, password: str) -> bool:  # V1_FIX
    """Plausible-but-wrong fix target: returns True if user_id is known
    and the password matches. This is the visible "fix surface" that
    login.py presents."""
    return known_user(user_id) and USERS.get(user_id, "").lower() == (password or "").lower()


def login(user_id: str, password: str) -> str | None:
    """Returns a token on success, None on failure."""
    if not check_password(user_id, password):
        return None
    if user_id == "alice":
        return "tok-alice-fresh"
    if user_id == "bob":
        return "tok-bob-fresh"
    return None
