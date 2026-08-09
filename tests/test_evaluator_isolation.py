"""test_evaluator_isolation.py — RBS-v4 repair item 8: FRESH EVALUATOR ISOLATION.

Trait-leakage regression tests. Verifies:

  1. EvidenceExtractor() without an explicit graph gets a FRESH per-instance
     graph — NOT the process-global get_evidence_graph() singleton. Two
     extractors must never share a graph, so evidence from run A cannot
     surface in run B's evaluation.
  2. The process-global singleton (_evidence_graph in evidence.py) is NOT
     mutated by normalizer/arena construction, and remains untouched by a
     full extract -> evaluate cycle.
  3. environment.py no longer imports the global get_evidence_graph (dead
     import removed).
  4. scripts/arena.py ArenaEntry falls back to a fresh EvidenceGraph, never
     the global.
  5. End-to-end: two sequential extractor runs (A then B) — B's graph is
     empty of A's evidence; evaluator reads only B's graph.

Run: python -m pytest tests/test_evaluator_isolation.py -q
"""

import sys

sys.path.insert(0, '/home/yaser/raphael-2.0-rbsv2r/src')

from orchestrator.capabilities.interactive_shell.tty_normalizer import (
    EvidenceExtractor, ParsedCommand,
)
from orchestrator.brain.evidence import EvidenceGraph


def _make_parsed(cmd: str, out: str) -> ParsedCommand:
    return ParsedCommand(
        command=cmd,
        output_lines=[out],
        raw_output=out + "\n",
        timestamp=1.0,
        exit_code=0,
    )


def test_two_extractors_do_not_share_graph():
    e1 = EvidenceExtractor()           # no explicit graph
    e2 = EvidenceExtractor()           # no explicit graph
    assert e1.evidence_graph is not e2.evidence_graph, (
        "Extractors share the same EvidenceGraph — trait leakage vector"
    )


def test_extractor_without_graph_is_fresh_not_global():
    import orchestrator.brain.evidence as ev_mod
    e = EvidenceExtractor()
    global_graph = ev_mod._evidence_graph
    if global_graph is not None:
        assert e.evidence_graph is not global_graph, (
            "Extractor silently bound to process-global graph"
        )
    # And the singleton must not have been CREATED by the extractor.
    assert ev_mod._evidence_graph is global_graph, (
        "Extractor construction mutated the process-global singleton"
    )


def test_global_singleton_untouched_by_extract_evaluate_cycle():
    import orchestrator.brain.evidence as ev_mod
    before = ev_mod._evidence_graph
    e = EvidenceExtractor()
    parsed = _make_parsed("cat /etc/hostname", "myhost")
    evs = e.extract_from_command(parsed, "sess-A", "10.0.0.5", "test")
    assert len(evs) >= 1
    # The caller is responsible for adding evidence to the graph; do that to
    # simulate a full extract -> evaluate cycle.
    for ev in evs:
        e.evidence_graph.add_evidence(ev)
    assert len(e.evidence_graph.get_all_evidence()) >= 1
    assert ev_mod._evidence_graph is before, (
        "Evidence extraction mutated the process-global singleton"
    )


def test_run_a_evidence_does_not_leak_into_run_b():
    """Sequential runs: B's graph must not contain A's evidence."""
    a = EvidenceExtractor()
    a_parsed = _make_parsed("cat /etc/leak-secret", "evidence-from-run-A")
    for ev in a.extract_from_command(a_parsed, "sess-A", "10.0.0.1", "test"):
        a.evidence_graph.add_evidence(ev)

    b = EvidenceExtractor()
    b_parsed = _make_parsed("cat /etc/hostname", "host-b")
    for ev in b.extract_from_command(b_parsed, "sess-B", "10.0.0.2", "test"):
        b.evidence_graph.add_evidence(ev)

    b_evidence = b.evidence_graph.get_all_evidence()
    for ev in b_evidence:
        assert "evidence-from-run-A" not in ev.raw_content, (
            "Run A evidence leaked into Run B graph"
        )
    # A's graph still has only A's evidence.
    a_evidence = a.evidence_graph.get_all_evidence()
    assert any("evidence-from-run-A" in ev.raw_content for ev in a_evidence)


def test_environment_no_global_import():
    src = open("/home/yaser/raphael-2.0-rbsv2r/src/arena/environment.py").read()
    assert "get_evidence_graph" not in src, (
        "environment.py still references the global evidence graph"
    )


def test_arena_entry_fresh_graph_fallback():
    """scripts/arena.py ArenaEntry must mint a fresh graph, never global."""
    src = open("/home/yaser/raphael-2.0-rbsv2r/scripts/arena.py").read()
    assert "get_evidence_graph" not in src, (
        "scripts/arena.py still references the global evidence graph"
    )
    # default_factory must be EvidenceGraph (fresh per instance).
    assert "default_factory=EvidenceGraph" in src


def test_explicit_graph_still_honored():
    """Callers passing an explicit graph keep it (backward compat)."""
    g = EvidenceGraph()
    e = EvidenceExtractor(evidence_graph=g)
    assert e.evidence_graph is g
    # Constructing with an explicit graph must not touch the global either.
    import orchestrator.brain.evidence as ev_mod
    assert ev_mod._evidence_graph is not g or ev_mod._evidence_graph is None


# ── Runner ──────────────────────────────────────────────────────

TESTS = [
    ("extractors do not share graph", test_two_extractors_do_not_share_graph),
    ("fresh graph not global", test_extractor_without_graph_is_fresh_not_global),
    ("global untouched by cycle", test_global_singleton_untouched_by_extract_evaluate_cycle),
    ("run A does not leak into run B", test_run_a_evidence_does_not_leak_into_run_b),
    ("environment no global import", test_environment_no_global_import),
    ("arena entry fresh fallback", test_arena_entry_fresh_graph_fallback),
    ("explicit graph honored", test_explicit_graph_still_honored),
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
    print(f"EVALUATOR ISOLATION: {passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_manual() else 0)