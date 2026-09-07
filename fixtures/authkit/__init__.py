"""fixtures.authkit — authkit-style hero fixture.

Modules:
    store      - in-memory user/token state.
    session    - the ACTUAL DEFECT lives here (validate_session ignores
                 expiration and user binding).
    login      - the SYMPTOM / DECOY (plausible but wrong fix target).
    test_login - the NAMED test (passes for both v1 broken and v2 fixed).
    test_auth   - the INVARIANT test (fails under v1 broken, passes under v2 fixed).
"""
