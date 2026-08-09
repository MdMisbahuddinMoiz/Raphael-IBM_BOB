"""Terminal holdout analysis -- RBS-v4 terminal falsification.

Frozen analysis of evaluations/campaign/rbs_v4_holdout.jsonl.
- INFRA_INVALID matched seeds excluded (EVENT-001 false-lead seed 15; EVENT-002
  contradiction seed 57): whole-seed exclusion, no rerun.
- Statistical standard: EvaluationProtocol.md section 4 (alpha=0.05,
  Bonferroni over k hypotheses, effect sizes with 95% CI).
- No SciPy: exact binomial for McNemar-style discordant pairs; Cliff's delta
  from counts with normal-approximation SE.
- Verdict letter semantics per directive:
    A  Demonstrated: Raphael shows a practically and statistically meaningful advantage.
    B  Partial:      Only part of the architecture clears the registered value threshold.
    C1 Equivalent:   Equivalence established between Raphael and competent prompting.
    C2 Prompted Superior: PROMPTED_AGENT establishes the registered advantage.
    D  Inconclusive: Evidence cannot resolve the question under the preregistered criteria.
  Numeric value thresholds are NOT present in the repo; where a letter needs a
  numeric bar we report estimate + 95% CI and explicitly flag the gap so
  SENTINEL can confirm the threshold -- never fabricate one.
"""
import json, math, statistics as st, datetime as _dt

CAMP = "/home/yaser/raphael-2.0-rbsv2r/evaluations/campaign"
JSONL = CAMP + "/rbs_v4_holdout.jsonl"
OUT = CAMP + "/TERMINAL_ANALYSIS_RESULTS.json"

ARMS = ["FULL_RAPHAEL", "PROMPTED_AGENT", "SCRIPTED_BASELINE", "NO_WORLD_MODEL"]
INFRA_INVALID_SEEDS = {15, 57}  # EVENT-001 (false-lead), EVENT-002 (contradiction)
Z95 = 1.959963984540054


def load_rows():
    rows = []
    with open(JSONL, "r") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def wilson(k, n, z=Z95):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (centre - half, centre + half)


def cliff_delta(a, b):
    """P(a>b) - P(a<b) over all pairs; 95% CI via normal-approx SE."""
    na, nb = len(a), len(b)
    if na == 0 or nb == 0:
        return (None, None)
    gt = 0
    for x in a:
        for y in b:
            if x > y:
                gt += 1
            elif x < y:
                gt -= 1
    d = gt / (na * nb)
    denom = na * nb * (na + nb - 1)
    sd = math.sqrt((na + nb - d * (na + nb - 1)) / denom) if denom > 0 else 0.0
    return (d, (d - 1.96 * sd, d + 1.96 * sd))


def binom_tail(k, n, p=0.5):
    from math import comb
    if n == 0:
        return 1.0
    return sum(comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in range(k, n + 1))


def main():
    rows = load_rows()
    by_arm = {a: [r for r in rows if r["arm"] == a] for a in ARMS}
    print("rows loaded:", len(rows), "by arm:", {a: len(v) for a, v in by_arm.items()})

    # 1) All-row arm summary (with Wilson 95% CI on pass rate)
    stats = {}
    print("\nARM SUMMARY (all collected rows)")
    for a in ARMS:
        rr = by_arm[a]
        n = len(rr)
        sc = [r["score"] for r in rr]
        pas = sum(1 for r in rr if r["verdict"] == "pass")
        mean = st.mean(sc) if sc else 0.0
        std = st.pstdev(sc) if len(sc) > 1 else 0.0
        lo, hi = wilson(pas, n)
        stats[a] = {
            "n": n, "mean_score": round(mean, 4), "score_std": round(std, 4),
            "pass": pas, "pass_rate": round(pas / n, 4) if n else 0.0,
            "pass_rate_ci95": [round(lo, 4), round(hi, 4)],
        }
        print("  %-16s n=%3d mean=%.4f pass=%3d/%-3d (%.3f, CI %s)"
              % (a, n, mean, pas, n, (pas / n if n else 0.0),
                 [round(lo, 4), round(hi, 4)]))

    # 2) valid seeds per arm (exclude infra-invalid whole seeds)
    valid = {a: [r for r in by_arm[a] if r["seed"] not in INFRA_INVALID_SEEDS]
             for a in ARMS}
    print("\nvalid rows (excl. infra seeds):", {a: len(v) for a, v in valid.items()})

    # 3) paired comparisons -- pairs keyed by full cell (template, seed)
    HYP = [
        ("FULL_vs_PROMPTED", "FULL_RAPHAEL", "PROMPTED_AGENT", "primary", "central thesis"),
        ("FULL_vs_NO_WORLD_MODEL", "FULL_RAPHAEL", "NO_WORLD_MODEL", "secondary", "world-model component"),
        ("FULL_vs_SCRIPTED", "FULL_RAPHAEL", "SCRIPTED_BASELINE", "secondary", "operator utility"),
    ]
    k_tests = len(HYP)
    alpha_adj = 0.05 / k_tests
    print("\nCOMPARISONS (Bonferroni alpha_adj = %.4f; pairing key = template+seed)" % alpha_adj)

    comparisons = {}
    for name, arm_a, arm_b, tier, label in HYP:
        A = {(r["template"], r["seed"]): r for r in valid[arm_a]}
        B = {(r["template"], r["seed"]): r for r in valid[arm_b]}
        common = sorted(A.keys() & B.keys())
        sa = [A[k]["score"] for k in common]
        sb = [B[k]["score"] for k in common]
        n_pairs = len(common)
        mean_a = st.mean(sa) if sa else 0.0
        mean_b = st.mean(sb) if sb else 0.0
        diff = mean_a - mean_b
        pass_a = sum(1 for k in common if A[k]["verdict"] == "pass")
        pass_b = sum(1 for k in common if B[k]["verdict"] == "pass")
        discord_ab = sum(1 for k in common
                         if A[k]["verdict"] == "pass" and B[k]["verdict"] == "fail")
        discord_ba = sum(1 for k in common
                         if A[k]["verdict"] == "fail" and B[k]["verdict"] == "pass")
        total_discord = discord_ab + discord_ba
        p_exact = None
        if total_discord > 0:
            k_star = max(discord_ab, discord_ba)
            p_exact = min(2.0 * binom_tail(k_star, total_discord), 1.0)
        d_cliff, ci = cliff_delta(sa, sb)
        sig = (p_exact is not None) and (p_exact < alpha_adj)
        comparisons[name] = {
            "tier": tier, "label": label, "n_pairs": n_pairs,
            "n_A_only": len(A) - n_pairs, "n_B_only": len(B) - n_pairs,
            "mean_A": round(mean_a, 4), "mean_B": round(mean_b, 4),
            "mean_diff_A_minus_B": round(diff, 4),
            "pass_A": pass_a, "pass_B": pass_b,
            "discord_Awin": discord_ab, "discord_Bwin": discord_ba,
            "matched_discord_total": total_discord,
            "mcnemar_exact_p": p_exact,
            "significant_alpha_adj": bool(sig),
            "cliff_delta": (round(d_cliff, 4) if d_cliff is not None else None),
            "cliff_delta_ci95": ([round(ci[0], 4), round(ci[1], 4)] if ci else None),
        }
        print("  %-24s n=%d A=%.4f B=%.4f diff=%+.4f p=%s sig=%s"
              % (name, n_pairs, mean_a, mean_b, diff, p_exact, sig))

    # 4) family discrimination grid (valid seeds, per template)
    fam_rows = {}
    for r in rows:
        fam_rows.setdefault(r["template"], []).append(r)
    family_grid = {}
    for fname, fr in fam_rows.items():
        by_arm_f = {}
        for a in ARMS:
            sub = [r for r in fr if r["arm"] == a and r["seed"] not in INFRA_INVALID_SEEDS]
            n = len(sub)
            pas = sum(1 for x in sub if x["verdict"] == "pass")
            mean = sum(x["score"] for x in sub) / n if n else 0.0
            by_arm_f[a] = {"n": n, "pass": pas, "mean": round(mean, 4)}
        family_grid[fname] = by_arm_f
        print("  %-22s %s" % (fname, {a: v["pass"] for a, v in by_arm_f.items()}))

    result = {
        "campaign": "rbs-v4-holdout",
        "instrument_tag": "terminal-holdout-frozen",
        "generated_at_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "infra_invalid_seeds_excluded": sorted(INFRA_INVALID_SEEDS),
        "arms_summary": stats,
        "comparisons": comparisons,
        "binomial_standard": {"alpha": 0.05, "bonferroni_k": k_tests,
                              "alpha_adj": alpha_adj},
        "family_grid": family_grid,
        "known_gap": {
            "flag": "REGISTERED_NUMERIC_VALUE_THRESHOLD_NOT_FOUND",
            "detail": ("No numeric 'registered value threshold' or 'registered "
                       "advantage' value appears in the preregistration, validation "
                       "freeze, EvaluationProtocol, or claim ledger. Statistics follow "
                       "EvaluationProtocol.md sec 4 (alpha 0.05, Bonferroni, effect "
                       "sizes + 95% CI). Apply letter verdicts only after SENTINEL "
                       "confirms the numeric threshold."),
        },
        "notes": [
            "score in [0,1]; verdict pass/fail per evaluator.",
            "paired by seed; seeds 15 (EVENT-001) and 57 (EVENT-002) excluded wholly.",
        ],
    }
    with open(OUT, "w") as fh:
        json.dump(result, fh, indent=2)
    print("\nWROTE:", OUT)


if __name__ == "__main__":
    main()