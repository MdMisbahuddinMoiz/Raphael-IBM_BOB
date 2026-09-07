"""fixtures.authkit.store — minimal in-memory user/session state."""
from __future__ import annotations

# Simulated user database: user_id -> password
USERS: dict[str, str] = {
    "alice": "wonderland",
    "bob": "builder",
}

# Simulated token registry: token -> user_id, with an `expired` flag.
# Tokens with an `expired=True` flag are considered invalid by the FIXED
# session module, but NOT by the BUGGY one (this is the actual defect).
TOKENS: dict[str, dict] = {
    "tok-alice-fresh": {"user_id": "alice", "expired": False},
    "tok-bob-fresh":   {"user_id": "bob",   "expired": False},
    "tok-alice-stale": {"user_id": "alice", "expired": True},
    "tok-bob-stale":   {"user_id": "bob",   "expired": True},
    "tok-cross":       {"user_id": "alice", "expired": False},  # bound to alice
}


def known_user(user_id: str) -> bool:
    return user_id in USERS


def lookup_token(token: str) -> dict | None:
    return TOKENS.get(token)


__all__ = ["USERS", "TOKENS", "known_user", "lookup_token"]
