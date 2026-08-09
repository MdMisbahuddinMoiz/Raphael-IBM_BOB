"""test_debug_stderr_epipe.py — REPAIR-VAL-02 regression tests.

SENTINEL-authorized repair: the two "D14-DEBUG" diagnostics previously wrote
directly to the process stderr via ``print(..., file=sys.stderr)``. Under the
full 200-cell capture harness the read end of the stderr pipe is closed by the
reader (HARNESS_OUTPUT_PIPE_EPIPE), causing an EPIPE that aborted the cell at
iteration 0 (actions_dispatched=0, episodes empty) and was recorded as an
INFRA_INVALID with the run-phase "Broken pipe [Errno 32]" family.

The repair (ablation_runner._safe_debug_stderr) must guarantee:
    invariant:  debug-output availability must NOT affect
                episode execution, broker dispatch, tool execution,
                evaluation, or terminal verdict.

These tests verify that invariant directly on the repaired helper.

Tests:
  test_debug_epipe_is_nonfatal       -> EPIPE on stderr write is swallowed;
                                        helper returns without raising.
  test_debug_non_epipe_oserror_is_not_hidden -> errno != EPIPE must surface.

Run: /home/yaser/raphael-2.0/.venv/bin/python -m pytest tests/test_debug_stderr_epipe.py -q
"""

import errno
import io
import sys

sys.path.insert(0, '/home/yaser/raphael-2.0-rbsv2r/src')

from arena.ablation_runner import _safe_debug_stderr


class _EpipeStderr:
    """A file-like that raises EPIPE on any write — mimics a dead capture pipe."""

    def write(self, s):
        raise BrokenPipeError(errno.EPIPE, "Broken pipe")

    def flush(self):
        raise BrokenPipeError(errno.EPIPE, "Broken pipe")


class _NonEpipeStderr:
    def write(self, s):
        raise OSError(errno.EMFILE, "Too many open files")

    def flush(self):
        pass


# ── BP1: EPIPE is nonfatal ─────────────────────────────────────

def test_debug_epipe_is_nonfatal():
    """A broken-pipe stderr write must not abort the cognitive path.

    This directly proves the invariant: if debug output availability is gone
    (EPIPE dead capture pipe), the code that calls _safe_debug_stderr (the
    planner decision path) continues past the debug write.
    """
    saved = sys.stderr
    try:
        sys.stderr = _EpipeStderr()
        # Must NOT raise. Under the old code this print would abort the cell.
        _safe_debug_stderr("[D14-DEBUG] Planner selected: action_id=A")
        _safe_debug_stderr("[D14-DEBUG]   falsif cand: action_id=B")
    finally:
        sys.stderr = saved
    # The fact we reached here means the write did not propagate; to be explicit:
    assert True


def test_debug_epipe_returns_none_broad_path():
    """Even a normal stderr (write succeeds) still works — byte-for-byte."""
    buf = io.StringIO()
    saved = sys.stderr
    try:
        sys.stderr = buf
        _safe_debug_stderr("[D14-DEBUG] marker")
    finally:
        sys.stderr = saved
    assert "[D14-DEBUG] marker" in buf.getvalue()


# ──► Non-EPIPE OSError must NOT be hidden ──────────────────────

def test_debug_non_epipe_oserror_is_not_hidden():
    """A non-EPIPE OSError (e.g. EMFILE) must still surface.

    This prevents the repair from becoming a broad exception sink. Only EPIPE
    is tolerated; any other OSError must propagate to the caller.
    """
    saved = sys.stderr
    raised = False
    try:
        sys.stderr = _NonEpipeStderr()
        try:
            _safe_debug_stderr("[D14-DEBUG] anything")
        except OSError as exc:
            raised = True
            assert exc.errno == errno.EMFILE, f"wrong errno: {exc.errno}"
        finally:
            sys.stderr = saved
    finally:
        sys.stderr = saved
    assert raised, "non-EPIPE OSError was swallowed — must surface"


# ──► Direct traceability: errno guard only passes EPIPE ────────

def test_debug_epipe_by_explicit_errno_is_swallowed():
    """BrokenPipeError is a subclass of OSError with errno EPIPE; swallowed."""
    saved = sys.stderr
    try:
        sys.stderr = _EpipeStderr()
        _safe_debug_stderr("x")  # BrokenPipeError(errno.EPIPE) -> swallowed
    finally:
        sys.stderr = saved


# ── Runner ──────────────────────────────────────────────────────

TESTS = [
    ("EPIPE nonfatal (dead capture pipe)", test_debug_epipe_is_nonfatal),
    ("EPIPE helper byte-path", test_debug_epipe_returns_none_broad_path),
    ("non-EPIPE OSError surfaces", test_debug_non_epipe_oserror_is_not_hidden),
    ("EPIPE exact errno swallowed", test_debug_epipe_by_explicit_errno_is_swallowed),
]


def _run_manual():
    import traceback
    passed = failed = 0
    for name, fn in TESTS:
        try:
            fn()
        except Exception as e:
            failed += 1
            traceback.print_exc()
            print(f"FAIL: {name}: {e}")
        else:
            passed += 1
    print(f"DEBUG-EPIPE GATE: {passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_manual() else 0)