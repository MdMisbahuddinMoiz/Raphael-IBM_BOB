"""test_run_identity.py — RBS-v4 repair item 7: RESUME + LOGICAL IDENTITY.

Verifies:
  1. run_id is DETERMINISTIC: same (config, template, seed, split) -> same run_id
     across independent AblationRunner instances (no random UUID suffix).
  2. Different seed / config / split -> different run_id.
  3. run_id embeds the logical cell (config, template, seed, split) and has no
     uuid hex tail.
  4. ensure_run_dir is idempotent: same run_id -> same run dir (resume-safe,
     overwrites rather than accumulates orphan dirs).
  5. The integrity-gate run_id pattern for holdout rows stays logical-cell
     derived (d6c_holdout_<arch>_<scenario>_s<seed>).

Run: python -m pytest tests/test_run_identity.py -q
"""

import re
import sys

sys.path.insert(0, '/home/yaser/raphael-2.0-rbsv2r/src')

from arena.ablation import ABLATION_PRESETS
from arena.ablation_runner import AblationRunner, ensure_run_dir


class _FakeTemplate:
    """Minimal template: AblationRunner only needs family_id + generate at init."""
    family_id = "T9_SEMANTIC_AMBIGUITY"
    schema_version = 2

    def generate(self, seed=0, split=None, scenario_id_override=None):
        raise NotImplementedError("init-time only")


def _make_runner(seed, config_id="FULL_RAPHAEL", split="validation"):
    return AblationRunner(
        template=_FakeTemplate(),
        config=ABLATION_PRESETS[config_id],
        seed=seed,
        split=split,
    )


def test_run_id_is_deterministic_across_instances():
    r1 = _make_runner(seed=7)
    r2 = _make_runner(seed=7)
    assert r1.run_id == r2.run_id
    assert r1.run_id == "abl_FULL_RAPHAEL_T9_SEMANTIC_AMBIGUITY_s0007_validation"


def test_run_id_has_no_uuid_suffix():
    r = _make_runner(seed=7)
    # Canonical logical-cell format: no trailing uuid hex.
    assert re.fullmatch(r"abl_[A-Z0-9_]+_[A-Za-z0-9_]+_s\d{4}_(validation|holdout|dev)", r.run_id)
    # The old format had _<6 hex chars> at the end; verify that's gone.
    assert not re.search(r"_[0-9a-f]{6}$", r.run_id)


def test_run_id_changes_with_seed():
    assert _make_runner(seed=1).run_id != _make_runner(seed=2).run_id


def test_run_id_changes_with_config():
    assert (_make_runner(seed=1, config_id="FULL_RAPHAEL").run_id
            != _make_runner(seed=1, config_id="NO_LLM").run_id)


def test_run_id_changes_with_split():
    assert (_make_runner(seed=1, split="validation").run_id
            != _make_runner(seed=1, split="holdout").run_id)


def test_ensure_run_dir_idempotent_same_cell():
    r = _make_runner(seed=7)
    d1 = ensure_run_dir(r.run_id)
    d2 = ensure_run_dir(r.run_id)
    assert d1 == d2
    assert d1.name == r.run_id  # dir keyed by logical cell, not random uuid


def test_holdout_row_run_id_is_logical_cell_derived():
    # Contract for d6c_holdout_runner rows: no randomness in run_id.
    pattern = re.compile(r"^d6c_holdout_[A-Z0-9_]+_[A-Za-z0-9_]+_s\d+$")
    assert pattern.match("d6c_holdout_FULL_RAPHAEL_T2_HYPOTHESIS_SENSITIVE_s1073")


# ── Runner ──────────────────────────────────────────────────────

TESTS = [
    ("deterministic run_id", test_run_id_is_deterministic_across_instances),
    ("no uuid suffix", test_run_id_has_no_uuid_suffix),
    ("seed changes run_id", test_run_id_changes_with_seed),
    ("config changes run_id", test_run_id_changes_with_config),
    ("split changes run_id", test_run_id_changes_with_split),
    ("run_dir idempotent", test_ensure_run_dir_idempotent_same_cell),
    ("holdout row logical cell", test_holdout_row_run_id_is_logical_cell_derived),
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
    print(f"RUN IDENTITY: {passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_manual() else 0)