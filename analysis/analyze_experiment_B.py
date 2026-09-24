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
from collections import defaultdict
from pathlib import Path

from scipy.stats import binomtest, wilcoxon

CELLS = ["nl_full", "nl_strip", "form_full", "form_strip_verbatim", "form_strip_para"]
FORMAL = {"form_full", "form_strip_verbatim", "form_strip_para"}

# Pre-specified comparisons. Nothing else is tested; anything further is exploratory and is
# labelled as such in the paper.
# Two families, fixed here so that the multiplicity correction cannot be chosen after the fact.
# PRIMARY carries the hypotheses and is Holm-corrected within domain. SECONDARY is reported with
# unadjusted p and labelled exploratory in the paper.
PRIMARY = [
    ("nl_strip", "form_strip_verbatim", "medium effect under strip (H1)"),
    ("form_strip_verbatim", "form_strip_para", "artifact vs description (H2)"),
]
SECONDARY = [
    ("nl_full", "nl_strip", "cost of the strip, NL"),
    ("form_full", "form_strip_verbatim", "cost of the strip, formal"),
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


def index_rows(rows):
    """(domain, cell, instance_id, phase) -> row, keeping the last attempt of each phase."""
    idx = {}
    for r in rows:
        key = (r["domain"], r["cell"], r["instance_id"], r["phase"])
        prev = idx.get(key)
        if prev is None or r.get("attempt", 1) >= prev.get("attempt", 1):
            idx[key] = r
    return idx


def included_instances(idx, domain):
    """An instance is included iff every cell produced a valid phase-1 solution for it."""
    per_cell = defaultdict(set)
    for (d, cell, inst, phase), row in idx.items():
        if d == domain and phase == "p1" and row["outcome"] == "valid":
            per_cell[cell].add(inst)
    if not per_cell:
        return set(), {}
    included = set.intersection(*(per_cell[c] for c in CELLS if c in per_cell)) if len(per_cell) == len(CELLS) else set()
    seen = set()
    for s in per_cell.values():
        seen |= s
    return included, {c: len(per_cell.get(c, ())) for c in CELLS} | {"any_cell": len(seen)}


# ---------------------------------------------------------------- measures

def binary_measure(idx, domain, cell, instances, phase, predicate):
    out = {}
    for inst in instances:
        row = idx.get((domain, cell, inst, phase))
        out[inst] = bool(row is not None and predicate(row))
    return out


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

def analyse_domain(idx, grades_idx, domain):
    instances, coverage = included_instances(idx, domain)
    instances = sorted(instances)
    res = {"domain": domain, "n_included": len(instances), "coverage": coverage, "cells": {}}

    perturb, cprobe, uabst, ucontr, agrade = {}, {}, {}, {}, {}
    for cell in CELLS:
        perturb[cell] = binary_measure(idx, domain, cell, instances, "p2_perturbation",
                                       lambda r: r["outcome"] == "valid")
        cprobe[cell] = binary_measure(idx, domain, cell, instances, "probe_C",
                                      lambda r: r.get("correct") is True)
        uabst[cell] = binary_measure(idx, domain, cell, instances, "probe_U",
                                     lambda r: r["outcome"] == "abstained")
        ucontr[cell] = binary_measure(idx, domain, cell, instances, "probe_U",
                                      lambda r: r.get("contradicts_artifact") is True)
        agrade[cell] = {i: grades_idx.get((domain, cell, i)) for i in instances}

        graded = [g["grade"] for g in agrade[cell].values() if g is not None]
        res["cells"][cell] = {
            "perturbation_success": rate(perturb[cell]),
            "c_probe_accuracy": rate(cprobe[cell]),
            "u_probe_abstention": rate(uabst[cell]),
            "u_probe_contradiction": rate(ucontr[cell]),
            "a_probe_mean_grade": (sum(graded) / len(graded)) if graded else None,
            "a_probe_n_graded": len(graded),
            "a_probe_abstention": rate(binary_measure(
                idx, domain, cell, instances, "probe_A", lambda r: r["outcome"] == "abstained")),
            "artifact_retention_median": (
                sorted(retention_values(idx, domain, cell, instances))[
                    len(retention_values(idx, domain, cell, instances)) // 2]
                if cell in FORMAL and retention_values(idx, domain, cell, instances) else None),
        }

    # primary family: perturbation success, Holm-corrected within domain
    primary = []
    for a, b, label in PRIMARY:
        t = paired_test(perturb[a], perturb[b], instances)
        t.update({"comparison": f"{a} vs {b}", "label": label,
                  "measure": "perturbation_success", "family": "primary"})
        primary.append(t)
    for t, p_adj in zip(primary, holm([t["p"] for t in primary])):
        t["p_holm"] = p_adj

    # secondary family: everything else, unadjusted, exploratory
    secondary = []
    for a, b, label in SECONDARY:
        t = paired_test(perturb[a], perturb[b], instances)
        t.update({"comparison": f"{a} vs {b}", "label": label,
                  "measure": "perturbation_success", "family": "secondary", "p_holm": None})
        secondary.append(t)
    for a, b, label in PRIMARY + SECONDARY:
        ga = [agrade[a][i]["grade"] for i in instances if agrade[a][i] and agrade[b][i]]
        gb = [agrade[b][i]["grade"] for i in instances if agrade[a][i] and agrade[b][i]]
        if ga and any(x != y for x, y in zip(ga, gb)):
            stat, p = wilcoxon(ga, gb)
            secondary.append({"comparison": f"{a} vs {b}", "label": label,
                              "measure": "a_probe_grade", "family": "secondary",
                              "n_pairs": len(ga), "statistic": float(stat),
                              "p": float(p), "p_holm": None})
    res["tests"] = primary + secondary

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
    lines = [f"## {res['domain']}", "",
             f"Instances included (valid phase 1 in every cell): {res['n_included']}",
             f"Phase-1 validity per cell: {res['coverage']}", "",
             "| cell | perturbation | C-probe | A-probe grade | U abstention | retention |",
             "|---|---|---|---|---|---|"]
    for cell in CELLS:
        c = res["cells"][cell]
        ps, cp, ua = c["perturbation_success"], c["c_probe_accuracy"], c["u_probe_abstention"]
        grade = "—" if c["a_probe_mean_grade"] is None else f"{c['a_probe_mean_grade']:.2f}"
        ret = "—" if c["artifact_retention_median"] is None else f"{c['artifact_retention_median']:.2f}"
        lines.append(
            f"| `{cell}` | {ps['k']}/{ps['n']} ({ps['rate']:.0%}, CI {ps['ci95'][0]:.0%}–{ps['ci95'][1]:.0%}) "
            f"| {cp['rate']:.0%} | {grade} | {ua['rate']:.0%} | {ret} |")
    lines += ["", "### Pre-specified comparisons", "",
              "| family | comparison | measure | n | p | p (Holm) | note |",
              "|---|---|---|---|---|---|---|"]
    for t in res["tests"]:
        ph = "—" if t.get("p_holm") is None else f"{t['p_holm']:.4f}"
        lines.append(f"| {t['family']} | {t['comparison']} | {t['measure']} | {t.get('n_pairs','—')} "
                     f"| {t['p']:.4f} | {ph} | {t['label']} |")
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
    idx = index_rows(rows)
    grades_idx = {(g["domain"], g["cell"], g["instance_id"]): g for g in load_jsonl(args.grades)}

    domains = sorted({r["domain"] for r in rows})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    summary, md = [], ["# Experiment B — results", ""]
    for d in domains:
        res = analyse_domain(idx, grades_idx, d)
        summary.append(res)
        md.append(render(res))

    (out / "tables.md").write_text("\n".join(md))
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    (out / "gates.json").write_text(json.dumps(
        {r["domain"]: {"c_probe_flatness_violated": r["c_probe_flatness"]["violated"]}
         for r in summary}, indent=2))
    print("\n".join(md))


if __name__ == "__main__":
    main()
