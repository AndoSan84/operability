#!/usr/bin/env python3
"""Pre-committed analysis for Experiment B (context strip).

Committed before the full run; its sha256 is recorded in the frozen config at pilot time and
checked before the full run. Do not modify it after the first full run: a change means a new
config version and a new results file.

Usage:
    python3 analyze_experiment_B.py --results results/results.jsonl \
                                    --grades results/grades.jsonl \
                                    --out results/

Inputs
------
results.jsonl : one row per API call, schema in ORCHESTRATOR.md
grades.jsonl  : one row per A-probe answer, produced by the blind grading session
                {"domain":..., "instance_id":..., "cell":..., "grade":0|1|2, "abstained":bool}
                (the grading session never sees `cell`; the orchestrator re-joins it here)

Outputs
-------
tables.md      : human-readable tables, one section per domain
summary.json   : every number the paper will cite
gates.json     : gate verdicts, including the C-probe flatness check
"""

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path

from scipy.stats import binomtest, wilcoxon

CELLS = ["nl_full", "nl_strip", "form_full", "form_strip_verbatim", "form_strip_para"]
FORMAL = ["form_full", "form_strip_verbatim", "form_strip_para"]
A_PROBE_CELLS = FORMAL          # NL cells have no artifact, so no A-probe reference exists

# Decision rules, fixed here. Nothing else is confirmatory; anything further is exploratory and
# is labelled as such in the paper.
ALPHA = 0.05
MEI_PP = 0.10                   # H1: minimum effect of interest, in proportion points
MEI_GRADE = 0.25                # H2b: minimum mean grade difference, on the 0-2 scale
LAMBDA_THRESHOLD = 0.5          # H2: paraphrase closer to nl_strip than to verbatim
TOST_MARGIN = 0.15              # H4: equivalence margin on U-probe abstention
BOOTSTRAP_REPS = 10000
BOOTSTRAP_SEED = 20260924
U_PROBES_PER_CELL = 3           # H4: U-probes drawn per instance and cell
U_PROBE_MIN_ISSUED = 2          # H4: below this the instance is excluded from H4 only

SECONDARY = [
    ("nl_full", "nl_strip", "cost of the strip, NL"),
    ("form_full", "form_strip_verbatim", "cost of the strip, formal"),
    ("nl_strip", "form_strip_verbatim", "medium effect under strip (descriptive)"),
    ("nl_strip", "form_strip_para", "description vs NL"),
]

# ---------------------------------------------------------------- statistics

def wilson_ci(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def mcnemar_exact(pairs):
    """pairs: list of (outcome_a, outcome_b) booleans, paired on instance."""
    b = sum(1 for a, c in pairs if a and not c)
    c = sum(1 for a, c in pairs if c and not a)
    if b + c == 0:
        return {"n_pairs": len(pairs), "b": b, "c": c, "p": 1.0}
    p = binomtest(b, b + c, 0.5).pvalue
    return {"n_pairs": len(pairs), "b": b, "c": c, "p": p}


def _boot_indices(n, rng):
    return [rng.randrange(n) for _ in range(n)]


def bootstrap_did(per_instance, rng):
    """H1: ((nl_full - nl_strip) - (form_full - form_strip_verbatim)), in proportion points."""
    def stat(rows):
        n = len(rows)
        nl = sum(r[0] for r in rows) / n - sum(r[1] for r in rows) / n
        fo = sum(r[2] for r in rows) / n - sum(r[3] for r in rows) / n
        return nl - fo
    point = stat(per_instance)
    draws = []
    for _ in range(BOOTSTRAP_REPS):
        idx = _boot_indices(len(per_instance), rng)
        draws.append(stat([per_instance[i] for i in idx]))
    draws.sort()
    lo, hi = draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws)) - 1]
    return {"did": point, "ci95": [lo, hi],
            "p_boot_le_0": sum(1 for d in draws if d <= 0) / len(draws)}


def bootstrap_lambda(per_instance, rng):
    """H2: position of form_strip_para between nl_strip (0) and form_strip_verbatim (1).

    per_instance rows are (nl_strip, form_strip_verbatim, form_strip_para) booleans.
    Undefined when the denominator is not distinguishable from zero; that case is reported as
    'untestable', which is a pre-registered outcome, not a failure.
    """
    def rates(rows):
        n = len(rows)
        return (sum(r[0] for r in rows) / n, sum(r[1] for r in rows) / n,
                sum(r[2] for r in rows) / n)
    a, b, c = rates(per_instance)
    denom_draws, lam_draws = [], []
    for _ in range(BOOTSTRAP_REPS):
        idx = _boot_indices(len(per_instance), rng)
        ra, rb, rc = rates([per_instance[i] for i in idx])
        denom_draws.append(rb - ra)
        if abs(rb - ra) > 1e-9:
            lam_draws.append((rc - ra) / (rb - ra))
    denom_draws.sort()
    d_lo, d_hi = denom_draws[int(0.025 * len(denom_draws))], denom_draws[int(0.975 * len(denom_draws)) - 1]
    out = {"p_nl_strip": a, "p_verbatim": b, "p_para": c,
           "denominator": b - a, "denominator_ci95": [d_lo, d_hi],
           "testable": d_lo > 0}   # the denominator must be positive, or lambda flips sign
    if lam_draws:
        lam_draws.sort()
        out["lambda"] = ((c - a) / (b - a)) if abs(b - a) > 1e-9 else None
        out["ci95"] = [lam_draws[int(0.025 * len(lam_draws))],
                       lam_draws[int(0.975 * len(lam_draws)) - 1]]
        out["p_boot_ge_threshold"] = sum(1 for l in lam_draws if l >= LAMBDA_THRESHOLD) / len(lam_draws)
    return out


def tost_equivalence(map_a, map_b, instances, rng, margin=TOST_MARGIN):
    """H4: the two cells are equivalent iff the 90% CI of the difference lies inside +-margin."""
    rows = [(map_a[i], map_b[i]) for i in instances]
    def diff(rs):
        n = len(rs)
        return sum(r[0] for r in rs) / n - sum(r[1] for r in rs) / n
    point = diff(rows)
    draws = sorted(diff([rows[i] for i in _boot_indices(len(rows), rng)])
                   for _ in range(BOOTSTRAP_REPS))
    lo, hi = draws[int(0.05 * len(draws))], draws[int(0.95 * len(draws)) - 1]
    return {"difference": point, "ci90": [lo, hi], "margin": margin,
            "equivalent": lo > -margin and hi < margin}


def holm(pvals):
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals)
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        val = (m - rank) * pvals[i]
        running = max(running, min(1.0, val))
        adj[i] = running
    return adj


# ---------------------------------------------------------------- loading

def load_jsonl(path):
    if path is None or not Path(path).exists():
        return []
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


MEDIA = ["nl", "formal"]
CELL_MEDIUM = {"nl_full": "nl", "nl_strip": "nl", "form_full": "formal",
               "form_strip_verbatim": "formal", "form_strip_para": "formal"}


def index_rows(rows):
    """Phase 1 is run once per medium per instance; every later phase is per cell.

    p1 rows are keyed (domain, medium, instance, 'p1'); all other phases (domain, cell,
    instance, phase). Only the last attempt of each key is kept. Probe rows are grouped per
    (domain, cell, instance, phase); a probe_id logged more than once (a retried call) keeps only
    the row with the highest attempt, ties broken by file order. The attempt, not the file order,
    decides, because a write that lands out of order makes the file order lie.
    """
    idx, probes = {}, defaultdict(list)
    for r in rows:
        if r["phase"].startswith("probe_"):
            group = probes[(r["domain"], r["cell"], r["instance_id"], r["phase"])]
            pid = r.get("probe_id")
            prev = next((x for x in group if pid is not None and x.get("probe_id") == pid), None)
            if prev is None:
                group.append(r)
            elif r.get("attempt", 1) >= prev.get("attempt", 1):
                group[group.index(prev)] = r
            continue
        key = ((r["domain"], r["medium"], r["instance_id"], "p1") if r["phase"] == "p1"
               else (r["domain"], r["cell"], r["instance_id"], r["phase"]))
        prev = idx.get(key)
        if prev is None or r.get("attempt", 1) >= prev.get("attempt", 1):
            idx[key] = r
    return idx, probes


def included_instances(idx, domain):
    """An instance is included iff BOTH media produced a valid phase-1 solution for it."""
    per_medium = defaultdict(set)
    seen = set()
    for (d, key, inst, phase), row in idx.items():
        if d == domain and phase == "p1":
            seen.add(inst)
            if row["outcome"] == "valid":
                per_medium[key].add(inst)
    if len(per_medium) < len(MEDIA):
        return set(), {m: len(per_medium.get(m, ())) for m in MEDIA} | {"any_medium": len(seen)}
    included = set.intersection(*(per_medium[m] for m in MEDIA))
    return included, ({m: len(per_medium[m]) for m in MEDIA}
                      | {"any_medium": len(seen),
                         "inclusion_rate": (len(included) / len(seen)) if seen else float("nan")})


# ---------------------------------------------------------------- measures

def binary_measure(idx, domain, cell, instances, phase, predicate):
    out = {}
    for inst in instances:
        row = idx.get((domain, cell, inst, phase))
        out[inst] = bool(row is not None and predicate(row))
    return out


def probe_binary(probes, domain, cell, instances, phase, predicate):
    out = {}
    for inst in instances:
        rows = probes.get((domain, cell, inst, phase), [])
        out[inst] = bool(rows) and predicate(rows[0])
    return out


def probe_proportion(probes, domain, cell, instances, phase, predicate, min_issued=1):
    """Per-instance share over the probes actually issued; None below min_issued."""
    out = {}
    for inst in instances:
        rows = probes.get((domain, cell, inst, phase), [])
        out[inst] = (sum(1 for r in rows if predicate(r)) / len(rows)
                     if len(rows) >= min_issued else None)
    return out


def aggregate_rate(probes, domain, cell, instances, phase, predicate, only=lambda r: True):
    """Probe-level descriptive rate; clustering within instance is ignored by design."""
    rows = [r for inst in instances for r in probes.get((domain, cell, inst, phase), []) if only(r)]
    k = sum(1 for r in rows if predicate(r))
    lo, hi = wilson_ci(k, len(rows))
    return {"k": k, "n": len(rows), "rate": (k / len(rows) if rows else float("nan")),
            "ci95": [lo, hi]}


def contamination_rate(idx, probes, domain, cell, instances):
    """Share of this cell's phase-2 responses (perturbation and every probe) that the harness
    flagged as referring to tools, files or execution. A result column, not an internal check."""
    rows = []
    for inst in instances:
        row = idx.get((domain, cell, inst, "p2_perturbation"))
        if row is not None:
            rows.append(row)
        for phase in ("probe_C", "probe_A", "probe_U"):
            rows.extend(probes.get((domain, cell, inst, phase), []))
    k = sum(1 for r in rows if r.get("contaminated") is True)
    lo, hi = wilson_ci(k, len(rows))
    return {"k": k, "n": len(rows), "rate": (k / len(rows) if rows else float("nan")),
            "ci95": [lo, hi]}


def mean_of(d):
    vals = [v for v in d.values() if v is not None]
    return {"mean": (sum(vals) / len(vals) if vals else float("nan")), "n": len(vals)}


def rate(d):
    k = sum(1 for v in d.values() if v)
    n = len(d)
    lo, hi = wilson_ci(k, n)
    return {"k": k, "n": n, "rate": (k / n if n else float("nan")), "ci95": [lo, hi]}


def paired_test(map_a, map_b, instances):
    pairs = [(map_a[i], map_b[i]) for i in instances]
    return mcnemar_exact(pairs)


def retention_values(idx, domain, cell, instances):
    vals = []
    for inst in instances:
        row = idx.get((domain, cell, inst, "p2_perturbation"))
        if row is not None and row.get("artifact_retention") is not None:
            vals.append(row["artifact_retention"])
    return vals


# ---------------------------------------------------------------- analysis

def analyse_domain(idx, probes, grades_idx, domain):
    instances, coverage = included_instances(idx, domain)
    instances = sorted(instances)
    res = {"domain": domain, "n_included": len(instances), "coverage": coverage, "cells": {}}
    if not instances:
        # a degenerate domain must not take the healthy one down with it
        res["status"] = "no included instances"
        return res
    res["status"] = "analysed"

    perturb, cprobe, uabst, agrade, ucontr = {}, {}, {}, {}, {}
    for cell in CELLS:
        perturb[cell] = binary_measure(idx, domain, cell, instances, "p2_perturbation",
                                       lambda r: r["outcome"] == "valid")
        cprobe[cell] = probe_binary(probes, domain, cell, instances, "probe_C",
                                    lambda r: r.get("correct") is True)
        uabst[cell] = probe_proportion(probes, domain, cell, instances, "probe_U",
                                       lambda r: r["outcome"] == "abstained",
                                       min_issued=U_PROBE_MIN_ISSUED)
        ucontr[cell] = aggregate_rate(probes, domain, cell, instances, "probe_U",
                                      lambda r: r.get("contradicts_artifact") is True,
                                      only=lambda r: r["outcome"] != "abstained")
        agrade[cell] = ({i: grades_idx.get((domain, cell, i)) for i in instances}
                        if cell in A_PROBE_CELLS else {i: None for i in instances})

        graded = [g["grade"] for g in agrade[cell].values() if g is not None]
        res["cells"][cell] = {
            "perturbation_success": rate(perturb[cell]),
            "c_probe_accuracy": rate(cprobe[cell]),
            "u_probe_abstention": mean_of(uabst[cell]),
            "u_probe_contradiction": ucontr[cell],
            "contamination": contamination_rate(idx, probes, domain, cell, instances),
            "a_probe_mean_grade": (sum(graded) / len(graded)) if graded else None,
            "a_probe_n_graded": len(graded),
            "a_probe_abstention": (rate(probe_binary(probes, domain, cell, instances, "probe_A",
                                                     lambda r: r["outcome"] == "abstained"))
                                   if cell in A_PROBE_CELLS else None),
            "artifact_retention_median": (
                sorted(retention_values(idx, domain, cell, instances))[
                    len(retention_values(idx, domain, cell, instances)) // 2]
                if cell in FORMAL and retention_values(idx, domain, cell, instances) else None),
        }

    p1_rows = {m: [idx[(domain, m, i, "p1")] for i in instances if (domain, m, i, "p1") in idx]
               for m in MEDIA}
    res["p1_contamination"] = {m: (sum(1 for r in rs if r.get("contaminated") is True) / len(rs)
                                   if rs else float("nan")) for m, rs in p1_rows.items()}

    rng = random.Random(BOOTSTRAP_SEED)

    # ---- confirmatory family (Holm-corrected within domain)
    primary = []

    did_rows = [(perturb["nl_full"][i], perturb["nl_strip"][i],
                 perturb["form_full"][i], perturb["form_strip_verbatim"][i]) for i in instances]
    did = bootstrap_did(did_rows, rng)
    d_i = [(r[0] - r[1]) - (r[2] - r[3]) for r in did_rows]
    w = wilcoxon(d_i, alternative="greater") if any(d_i) else None
    primary.append({
        "hypothesis": "H1", "measure": "perturbation_success",
        "test": "difference-in-differences (strip cost, NL minus formal)",
        "estimate_pp": did["did"], "ci95": did["ci95"], "n_pairs": len(instances),
        "p": float(w.pvalue) if w is not None else 1.0,
        "rule": f"one-sided; supported iff DiD >= {MEI_PP:.2f}, the 95% CI excludes 0, "
                f"and Holm-corrected p < {ALPHA}",
    })

    lam_rows = [(perturb["nl_strip"][i], perturb["form_strip_verbatim"][i],
                 perturb["form_strip_para"][i]) for i in instances]
    lam = bootstrap_lambda(lam_rows, rng)
    primary.append({
        "hypothesis": "H2a", "measure": "perturbation_success",
        "test": "position of form_strip_para between nl_strip (0) and verbatim (1)",
        "estimate": lam.get("lambda"), "ci95": lam.get("ci95"),
        "denominator": lam["denominator"], "denominator_ci95": lam["denominator_ci95"],
        "n_pairs": len(instances),
        "p": (lam.get("p_boot_ge_threshold", 1.0) if lam["testable"] else 1.0),
        "rule": f"testable only if the 95% CI of the denominator is strictly positive; supported "
                f"iff the upper CI bound of lambda is below {LAMBDA_THRESHOLD} and Holm-corrected "
                f"p < {ALPHA}",
        "untestable": not lam["testable"],
    })

    ga = [agrade["form_strip_verbatim"][i]["grade"] for i in instances
          if agrade["form_strip_verbatim"][i] and agrade["form_strip_para"][i]]
    gb = [agrade["form_strip_para"][i]["grade"] for i in instances
          if agrade["form_strip_verbatim"][i] and agrade["form_strip_para"][i]]
    # H2b is always in the family, so its size never depends on the data
    if ga and any(x != y for x, y in zip(ga, gb)):
        w2 = wilcoxon(ga, gb, alternative="greater")   # verbatim > paraphrase, one-sided
        stat, p2 = float(w2.statistic), float(w2.pvalue)
    else:
        stat, p2 = None, 1.0
    mean_v = sum(ga) / len(ga) if ga else float("nan")
    mean_p = sum(gb) / len(gb) if gb else float("nan")
    primary.append({"hypothesis": "H2b", "measure": "a_probe_grade",
                    "test": "verbatim vs paraphrase, formal cells only, one-sided",
                    "n_pairs": len(ga), "statistic": stat, "p": p2,
                    "estimate": (mean_v - mean_p), "mean_verbatim": mean_v, "mean_para": mean_p,
                    "rule": f"supported iff the mean grade difference >= {MEI_GRADE} and "
                            f"Holm-corrected p < {ALPHA}"})

    for t, p_adj in zip(primary, holm([t["p"] for t in primary])):
        t["p_holm"] = p_adj

    # decisions use the corrected p, never the raw one
    for t in primary:
        if t["hypothesis"] == "H1":
            t["supported"] = bool(t["estimate_pp"] >= MEI_PP and t["ci95"][0] > 0
                                  and t["p_holm"] < ALPHA)
        elif t["hypothesis"] == "H2a":
            t["supported"] = bool(lam["testable"] and lam.get("ci95")
                                  and lam["ci95"][1] < LAMBDA_THRESHOLD and t["p_holm"] < ALPHA)
        elif t["hypothesis"] == "H2b":
            t["supported"] = bool(t["estimate"] >= MEI_GRADE and t["p_holm"] < ALPHA)

    # ---- H4: equivalence on the unanswerable probes
    h4_instances = [i for i in instances
                    if uabst["nl_strip"][i] is not None and uabst["form_strip_verbatim"][i] is not None]
    if h4_instances:
        h4 = tost_equivalence(uabst["nl_strip"], uabst["form_strip_verbatim"], h4_instances, rng)
        lo, hi = h4["ci90"]
        h4["verdict"] = ("equivalent" if lo > -TOST_MARGIN and hi < TOST_MARGIN
                         else "difference" if (lo > 0 or hi < 0) else "inconclusive")
    else:   # no instance had enough issuable U-probes in both cells
        h4 = {"difference": None, "ci90": None, "margin": TOST_MARGIN, "equivalent": False,
              "verdict": "untestable"}
    h4["n_instances"] = len(h4_instances)
    h4.update({"hypothesis": "H4", "measure": "u_probe_abstention",
               "test": "equivalence (TOST via 90% bootstrap CI), nl_strip vs form_strip_verbatim",
               "rule": f"equivalent iff the 90% CI lies inside +-{TOST_MARGIN:.2f}",
               "per_cell_abstention": {c: mean_of(uabst[c])["mean"] for c in CELLS},
               "per_cell_contradiction": {c: ucontr[c]["rate"] for c in CELLS},
               "saturated": [c for c in CELLS if mean_of(uabst[c])["mean"] >= 0.99]})

    # ---- exploratory family, unadjusted
    secondary = []
    for a, b, label in SECONDARY:
        t = paired_test(perturb[a], perturb[b], instances)
        t.update({"comparison": f"{a} vs {b}", "label": label,
                  "measure": "perturbation_success", "family": "secondary", "p_holm": None})
        secondary.append(t)

    res["tests"] = {"primary": primary, "h4_equivalence": h4, "secondary": secondary}
    # gate: C-probes must be flat across cells, otherwise the design is confounded
    flat = []
    for i, a in enumerate(CELLS):
        for b in CELLS[i + 1:]:
            t = paired_test(cprobe[a], cprobe[b], instances)
            t["comparison"] = f"{a} vs {b}"
            flat.append(t)
    for t, p_adj in zip(flat, holm([t["p"] for t in flat])):
        t["p_holm"] = p_adj
    res["c_probe_flatness"] = {
        "tests": flat,
        "violated": any(t["p_holm"] < 0.05 for t in flat),
    }
    return res


def render(res):
    if res["status"] != "analysed":
        return "\n".join([f"## {res['domain']}", "", f"**{res['status']}.**",
                          f"Phase-1 validity per medium: {res['coverage']}"]) + "\n"
    lines = [f"## {res['domain']}", "",
             f"Instances included (valid phase 1 in both media): {res['n_included']}",
             f"Phase-1 validity per medium: {res['coverage']}", "",
             "| cell | perturbation | C-probe | A-probe grade | U abstention | retention "
             "| contamination |",
             "|---|---|---|---|---|---|---|"]
    for cell in CELLS:
        c = res["cells"][cell]
        ps, cp = c["perturbation_success"], c["c_probe_accuracy"]
        ua = c["u_probe_abstention"]["mean"]
        grade = "—" if c["a_probe_mean_grade"] is None else f"{c['a_probe_mean_grade']:.2f}"
        ret = "—" if c["artifact_retention_median"] is None else f"{c['artifact_retention_median']:.2f}"
        co = c["contamination"]
        lines.append(
            f"| `{cell}` | {ps['k']}/{ps['n']} ({ps['rate']:.0%}, CI {ps['ci95'][0]:.0%}–{ps['ci95'][1]:.0%}) "
            f"| {cp['rate']:.0%} | {grade} | {ua:.0%} | {ret} | {co['k']}/{co['n']} ({co['rate']:.1%}) |")
    lines += ["", "Phase-1 contamination per medium: " + ", ".join(
        f"{m} {v:.1%}" for m, v in res["p1_contamination"].items())]
    lines += ["", "### Confirmatory tests (Holm-corrected within domain)", "",
              "| hypothesis | measure | estimate | 95% CI | p | p (Holm) | supported |",
              "|---|---|---|---|---|---|---|"]
    for t in res["tests"]["primary"]:
        est = t.get("estimate_pp", t.get("estimate"))
        est = "—" if est is None else f"{est:+.3f}"
        ci = t.get("ci95")
        ci = "—" if not ci else f"[{ci[0]:+.3f}, {ci[1]:+.3f}]"
        sup = "untestable" if t.get("untestable") else ("yes" if t.get("supported") else
                                                       ("—" if "supported" not in t else "no"))
        lines.append(f"| {t['hypothesis']} | {t['measure']} | {est} | {ci} "
                     f"| {t['p']:.4f} | {t['p_holm']:.4f} | {sup} |")
    h4 = res["tests"]["h4_equivalence"]
    if h4["ci90"] is None:
        lines += ["", f"**H4** (n=0): no instance with at least {U_PROBE_MIN_ISSUED} U-probes "
                      f"issued in both cells → **{h4['verdict']}**"]
    else:
        lines += ["", f"**H4** (n={h4['n_instances']}): difference {h4['difference']:+.3f}, 90% CI "
                      f"[{h4['ci90'][0]:+.3f}, {h4['ci90'][1]:+.3f}], margin ±{h4['margin']:.2f} → "
                      f"**{h4['verdict']}**"]
    lines += ["", "### Exploratory comparisons (unadjusted)", "",
              "| comparison | measure | n | p | note |", "|---|---|---|---|---|"]
    for t in res["tests"]["secondary"]:
        lines.append(f"| {t['comparison']} | {t['measure']} | {t.get('n_pairs','—')} "
                     f"| {t['p']:.4f} | {t['label']} |")
    v = res["c_probe_flatness"]["violated"]
    lines += ["", f"**C-probe flatness gate: {'VIOLATED' if v else 'passed'}**"]
    if v:
        lines.append("The control probes differ across cells. The media are not matched and the "
                     "other comparisons are not interpretable; report this and stop.")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--grades", default=None)
    ap.add_argument("--out", default="results/")
    args = ap.parse_args()

    rows = load_jsonl(args.results)
    idx, probes = index_rows(rows)
    grades_idx = {(g["domain"], g["cell"], g["instance_id"]): g for g in load_jsonl(args.grades)}

    domains = sorted({r["domain"] for r in rows})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    summary, md = [], ["# Experiment B — results", ""]
    for d in domains:
        res = analyse_domain(idx, probes, grades_idx, d)
        summary.append(res)
        md.append(render(res))

    (out / "tables.md").write_text("\n".join(md))
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    (out / "gates.json").write_text(json.dumps(
        {r["domain"]: ({"c_probe_flatness_violated": r["c_probe_flatness"]["violated"]}
                       if r["status"] == "analysed" else {"status": r["status"]})
         for r in summary}, indent=2))
    print("\n".join(md))


if __name__ == "__main__":
    main()
