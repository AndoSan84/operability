#!/usr/bin/env python3
"""Pre-committed analysis for Experiment A (feedback ablation).

Committed before the first run; its sha256 is recorded in the frozen config and checked by the
test suite. Not modified after the first run: a change means a new config version.

Usage:
    python3 analyze_experiment_A.py --results results/results_A.jsonl --out results/A/

Row schema (one row per API call), fields used here:
    module        M1 | M2 | M3 | M4
    domain        asp | maze
    instance_id
    arm           shared | binary | diagnostic            (M1, M4)
                  nl_loop                                  (M3)
                  m2_nl | m2_mental | m2_exec              (M2)
    loop_attempt  1, 2, 3 (the attempt within the feedback loop)
    api_try       retry counter for the same loop attempt (0, 1, ...)
    outcome       valid | invalid_schedule | unsat | syntax_error | unparsable | refused |
                  api_error | timeout | max_tokens
    violations    list of normalised violation ids from the validator, e.g. "overlap:A:4:6"
    contaminated  bool — response refers to tools, files or execution

Primary population: instances whose shared attempt 1 ran and failed semantically
(invalid_schedule or unsat). Syntactic failures reach both arms with the same solver error, so
no manipulation happens on them; they are reported as the Symbolic Bottleneck, not tested.
"""

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path

from scipy.stats import binomtest, wilcoxon

# ---------------------------------------------------------------- decision rules (frozen)
ALPHA = 0.05
MEI_HL = 0.5                 # Hodges-Lehmann estimate of (binary - diagnostic), in attempts
N_BRANCHED_TARGET = 30       # primary-eligible branched instances
M4_BRANCHED_TARGET = 6
CENSORED = 4                 # attempts-to-success when not repaired within three attempts
BOOTSTRAP_REPS = 10000
BOOTSTRAP_SEED = 20260924
ELIGIBLE = {"invalid_schedule", "unsat"}
SYNTACTIC = {"syntax_error"}
INFRA = {"api_error"}        # the call never reached a model answer: not an attempt


# ---------------------------------------------------------------- statistics

def wilson_ci(k, n, z=1.96):
    if n == 0:
        return [float("nan"), float("nan")]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0.0, c - h), min(1.0, c + h)]


def rate(k, n):
    return {"k": k, "n": n, "rate": (k / n if n else float("nan")), "ci95": wilson_ci(k, n)}


def mcnemar_exact(pairs):
    b = sum(1 for x, y in pairs if x and not y)
    c = sum(1 for x, y in pairs if y and not x)
    p = binomtest(b, b + c, 0.5).pvalue if b + c else 1.0
    return {"n_pairs": len(pairs), "b": b, "c": c, "p": p}


def hodges_lehmann(d):
    if not d:
        return float("nan")
    walsh = sorted((d[i] + d[j]) / 2 for i in range(len(d)) for j in range(i, len(d)))
    m = len(walsh)
    return walsh[m // 2] if m % 2 else (walsh[m // 2 - 1] + walsh[m // 2]) / 2


def bootstrap_hl(d, rng):
    if len(d) < 2:
        return [float("nan"), float("nan")]
    draws = sorted(hodges_lehmann([d[rng.randrange(len(d))] for _ in d])
                   for _ in range(BOOTSTRAP_REPS))
    return [draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws)) - 1]]


def signed_rank_greater(d):
    """One-sided Wilcoxon signed-rank, zeros dropped, normal approximation with correction.
    Chosen for determinism with heavy ties; this is also what the power simulation used."""
    if not any(d):
        return 1.0
    try:
        return float(wilcoxon(d, alternative="greater", zero_method="wilcox",
                              correction=True, method="approx").pvalue)
    except TypeError:        # older scipy without the `method` argument
        return float(wilcoxon(d, alternative="greater", zero_method="wilcox",
                              correction=True).pvalue)


# ---------------------------------------------------------------- loading

def load_jsonl(path):
    if not Path(path).exists():
        return []
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def dedupe(rows):
    """Keep the last API try of each loop attempt. A retried call leaves the failed try in the
    append-only file first; reading the first row would count the error, not the answer."""
    best = {}
    for pos, r in enumerate(rows):
        key = (r["module"], r["domain"], r["instance_id"], r["arm"], r["loop_attempt"])
        rank = (r.get("api_try", 0), pos)
        if key not in best or rank >= best[key][0]:
            best[key] = (rank, r)
    table = defaultdict(dict)
    for (mod, dom, inst, arm, att), (_, r) in best.items():
        table[(mod, dom, inst, arm)][att] = r
    return table


def attempts_to_success(first, later):
    """first: the shared attempt-1 row; later: {2: row, 3: row} of one arm."""
    if first is not None and first["outcome"] == "valid":
        return 1
    for att in (2, 3):
        r = later.get(att)
        if r is not None and r["outcome"] == "valid":
            return att
    return CENSORED


def arm_terminal(later):
    """An arm is finished iff it repaired, or it has a real attempt 3. A pending attempt (the run
    was interrupted, e.g. by the subscription limit) or an infrastructure failure is not a
    censored result: counting it as 4 would score where the batch stopped, not the model."""
    for att in (2, 3):
        r = later.get(att)
        if r is None or r["outcome"] in INFRA:
            return False
        if r["outcome"] == "valid":
            return True
    return True


def violation_set(row):
    if row is None:
        return None
    if row["outcome"] == "valid":
        return set()
    return set(row.get("violations") or [row["outcome"]])


# ---------------------------------------------------------------- M1 / M4: the feedback contrast

def feedback_contrast(table, module, domain, target, confirmatory):
    rng = random.Random(BOOTSTRAP_SEED)
    instances = sorted({inst for (m, d, inst, arm) in table
                        if m == module and d == domain and arm == "shared"})
    firsts = {i: table[(module, domain, i, "shared")].get(1) for i in instances}
    k_infra = sum(1 for r in firsts.values() if r is not None and r["outcome"] in INFRA)
    firsts = {i: r for i, r in firsts.items() if r is not None and r["outcome"] not in INFRA}

    n_first = len(firsts)
    k_valid = sum(r["outcome"] == "valid" for r in firsts.values())
    k_syn = sum(r["outcome"] in SYNTACTIC for r in firsts.values())
    eligible = [i for i, r in firsts.items() if r["outcome"] in ELIGIBLE]
    k_unsat = sum(firsts[i]["outcome"] == "unsat" for i in eligible)

    res = {"module": module, "domain": domain, "confirmatory": confirmatory,
           "attempt1": {"n": n_first,
                        "single_shot_success": rate(k_valid, n_first),
                        "syntactic_failure": rate(k_syn, n_first),
                        "eligible_failure": rate(len(eligible), n_first),
                        "unsat_among_eligible": k_unsat,
                        "infrastructure_excluded": k_infra},
           "branched_target": target, "n_branched": len(eligible),
           "target_reached": len(eligible) >= target}

    def arm(i, name):
        return table.get((module, domain, i, name), {})

    complete = [i for i in eligible
                if arm_terminal(arm(i, "binary")) and arm_terminal(arm(i, "diagnostic"))]
    res["n_branched_complete"] = len(complete)
    res["n_branched_incomplete"] = len(eligible) - len(complete)

    def contrast(pop, label):
        d = [attempts_to_success(firsts[i], arm(i, "binary"))
             - attempts_to_success(firsts[i], arm(i, "diagnostic")) for i in pop]
        if not d:
            return {"population": label, "n": 0, "verdict": "untestable: no branched instances"}
        hl = hodges_lehmann(d)
        p = signed_rank_greater(d)
        out = {"population": label, "n": len(d), "hodges_lehmann": hl,
               "hl_ci95": bootstrap_hl(d, rng), "p_one_sided": p,
               "ties": sum(1 for x in d if x == 0) / len(d),
               "mean_difference": sum(d) / len(d)}
        if confirmatory:
            out["supported"] = bool(p < ALPHA and hl >= MEI_HL)
            out["rule"] = f"one-sided signed-rank p < {ALPHA} and Hodges-Lehmann >= {MEI_HL}"
        else:
            out["note"] = "descriptive: sample too small for a confirmatory claim"
        return out

    res["primary"] = contrast(complete, "runnable attempt 1 that failed semantically")
    res["sensitivity_invalid_schedule_only"] = contrast(
        [i for i in complete if firsts[i]["outcome"] == "invalid_schedule"],
        "invalid schedule only (UNSAT excluded)")

    # secondary: success within three attempts, per arm, paired
    succ = {a: {i: attempts_to_success(firsts[i], arm(i, a)) < CENSORED for i in complete}
            for a in ("binary", "diagnostic")}
    res["success_within_3"] = {
        a: rate(sum(succ[a].values()), len(complete)) for a in succ}
    res["success_within_3"]["mcnemar"] = mcnemar_exact(
        [(succ["diagnostic"][i], succ["binary"][i]) for i in complete])

    # uptake and regression, per arm
    for a in ("binary", "diagnostic"):
        steps = up = reg_n = reg = 0
        for i in complete:
            seq = [firsts[i], arm(i, a).get(2), arm(i, a).get(3)]
            vs = [violation_set(r) for r in seq]
            for k in range(2):
                if vs[k] and vs[k + 1] is not None:
                    steps += 1
                    up += bool(vs[k] - vs[k + 1])       # at least one flagged violation gone
            if vs[0] and vs[1] is not None and vs[2]:
                repaired = vs[0] - vs[1]
                if repaired:
                    reg_n += 1
                    reg += bool(repaired & vs[2])
        res.setdefault("uptake", {})[a] = rate(up, steps)
        res.setdefault("regression", {})[a] = rate(reg, reg_n)

    # contamination, per arm, over every call of the module
    for a in ("shared", "binary", "diagnostic"):
        calls = [r for (m, d, i, arm_), atts in table.items()
                 if m == module and d == domain and arm_ == a for r in atts.values()]
        res.setdefault("contamination", {})[a] = rate(
            sum(bool(r.get("contaminated")) for r in calls), len(calls))
    return res


# ---------------------------------------------------------------- M2: syntax vs execution

def maze_replacement(table):
    arms = ("m2_nl", "m2_mental", "m2_exec")
    insts = sorted({i for (m, d, i, a) in table if m == "M2"})
    ok = {a: {i: (table.get(("M2", "maze", i, a), {}).get(1) or {}).get("outcome") == "valid"
              for i in insts} for a in arms}
    both = lambda a, b: [i for i in insts if table.get(("M2", "maze", i, a)) and table.get(("M2", "maze", i, b))]
    return {"n": len(insts),
            "success": {a: rate(sum(ok[a].values()), len(insts)) for a in arms},
            "nl_vs_mental": mcnemar_exact([(ok["m2_nl"][i], ok["m2_mental"][i]) for i in both("m2_nl", "m2_mental")]),
            "mental_vs_exec": mcnemar_exact([(ok["m2_exec"][i], ok["m2_mental"][i]) for i in both("m2_exec", "m2_mental")]),
            "note": "exploratory; single-shot, n = 20"}


# ---------------------------------------------------------------- M3: medium under the same loop

def medium_contrast(table):
    insts = sorted({i for (m, d, i, a) in table if m == "M3"})
    pairs, nl_s, asp_s, asp_not_looped = [], 0, 0, 0
    for i in insts:
        nl = table.get(("M3", "asp", i, "nl_loop"), {})
        first = table.get(("M1", "asp", i, "shared"), {}).get(1)
        diag = table.get(("M1", "asp", i, "diagnostic"), {})
        if not nl or first is None:
            continue
        if first["outcome"] in INFRA:
            continue
        if first["outcome"] in ELIGIBLE and not arm_terminal(diag):
            continue                     # the ASP loop is still pending: no result yet
        s_nl = any(r["outcome"] == "valid" for r in nl.values())
        # an ASP attempt 1 that did not branch (syntax error, timeout) had no loop: it counts as
        # an ASP failure, conservative against the formal medium, and is counted separately
        s_asp = attempts_to_success(first, diag) < CENSORED
        asp_not_looped += first["outcome"] != "valid" and first["outcome"] not in ELIGIBLE
        pairs.append((s_asp, s_nl))
        nl_s += s_nl
        asp_s += s_asp
    return {"n_paired": len(pairs),
            "nl_loop_success_within_3": rate(nl_s, len(pairs)),
            "asp_diagnostic_success_within_3": rate(asp_s, len(pairs)),
            "mcnemar": mcnemar_exact(pairs),
            "asp_attempt1_not_branched_counted_as_failure": asp_not_looped,
            "note": "exploratory; same diagnostic loop, different medium"}


# ---------------------------------------------------------------- report

def fmt_rate(r):
    if r["n"] == 0:
        return "—"
    return f"{r['k']}/{r['n']} ({r['rate']:.0%}, CI {r['ci95'][0]:.0%}–{r['ci95'][1]:.0%})"


def render_contrast(res):
    a1 = res["attempt1"]
    lines = [f"## {res['module']} — {res['domain']}"
             f"{'' if res['confirmatory'] else ' (descriptive)'}", "",
             f"Attempt 1 (shared): single-shot success {fmt_rate(a1['single_shot_success'])}; "
             f"syntactic failure {fmt_rate(a1['syntactic_failure'])}; "
             f"eligible (runnable, semantically failing) {fmt_rate(a1['eligible_failure'])}, "
             f"of which UNSAT {a1['unsat_among_eligible']}.",
             f"Branched: {res['n_branched']} (target {res['branched_target']}, "
             f"{'reached' if res['target_reached'] else 'NOT reached'}); "
             f"complete in both arms: {res['n_branched_complete']}; "
             f"incomplete (pending or infrastructure): {res['n_branched_incomplete']}. "
             f"Attempt-1 calls lost to infrastructure: {a1['infrastructure_excluded']}.", ""]
    for key in ("primary", "sensitivity_invalid_schedule_only"):
        c = res[key]
        if c["n"] == 0:
            lines.append(f"- **{c['population']}**: {c['verdict']}")
            continue
        verdict = ("supported" if c.get("supported") else "not supported") if "supported" in c else c["note"]
        lines.append(f"- **{c['population']}** (n={c['n']}): Hodges-Lehmann {c['hodges_lehmann']:+.2f} "
                     f"attempts, 95% CI [{c['hl_ci95'][0]:+.2f}, {c['hl_ci95'][1]:+.2f}], "
                     f"one-sided p = {c['p_one_sided']:.4f}, tied pairs {c['ties']:.0%} → **{verdict}**")
    s3 = res["success_within_3"]
    lines += ["", f"Success within 3: binary {fmt_rate(s3['binary'])}, diagnostic "
                  f"{fmt_rate(s3['diagnostic'])}, McNemar p = {s3['mcnemar']['p']:.4f}.",
              f"Uptake: binary {fmt_rate(res['uptake']['binary'])}, diagnostic "
              f"{fmt_rate(res['uptake']['diagnostic'])}. Regression: binary "
              f"{fmt_rate(res['regression']['binary'])}, diagnostic {fmt_rate(res['regression']['diagnostic'])}.",
              "Contamination: " + ", ".join(f"{a} {fmt_rate(r)}" for a, r in res["contamination"].items()), ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", default="results/A/")
    args = ap.parse_args()
    table = dedupe(load_jsonl(args.results))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    summary = {"M1": feedback_contrast(table, "M1", "asp", N_BRANCHED_TARGET, True),
               "M4": feedback_contrast(table, "M4", "asp", M4_BRANCHED_TARGET, False)}
    if any(m == "M2" for (m, *_ ) in table):
        summary["M2"] = maze_replacement(table)
    if any(m == "M3" for (m, *_ ) in table):
        summary["M3"] = medium_contrast(table)

    md = ["# Experiment A — results", "", render_contrast(summary["M1"]), render_contrast(summary["M4"])]
    if "M2" in summary:
        m2 = summary["M2"]
        md += ["## M2 — maze, syntax vs execution (exploratory)", "",
               ", ".join(f"{a} {fmt_rate(r)}" for a, r in m2["success"].items()),
               f"NL vs mental McNemar p = {m2['nl_vs_mental']['p']:.4f}; "
               f"mental vs executed McNemar p = {m2['mental_vs_exec']['p']:.4f}.", ""]
    if "M3" in summary:
        m3 = summary["M3"]
        md += ["## M3 — medium under the same diagnostic loop (exploratory)", "",
               f"NL loop {fmt_rate(m3['nl_loop_success_within_3'])} vs ASP diagnostic "
               f"{fmt_rate(m3['asp_diagnostic_success_within_3'])}, McNemar p = {m3['mcnemar']['p']:.4f}.", ""]

    (out / "tables.md").write_text("\n".join(md))
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    (out / "gates.json").write_text(json.dumps({
        "M1_target_reached": summary["M1"]["target_reached"],
        "M4_target_reached": summary["M4"]["target_reached"]}, indent=2))
    print("\n".join(md))


if __name__ == "__main__":
    main()
