"""Post hoc (not pre-registered): locality of the model's edits between consecutive attempts.

ASP: share of the model's rules kept verbatim, statements changed, instance facts kept; schedule:
share of jobs with the same start time (ASP from the solver output, NL from the SCHEDULE line).
Runs on Experiment 2B (results_A_v5) and on Experiment 2A (results_A_v3, per arm).
"""
import collections, json, re, statistics as st


def stmts(code):
    code = re.sub(r"%.*", "", code or "")
    parts = [re.sub(r"\s+", "", p) for p in re.split(r"\.(?=\s|$)", code)]
    parts = [p for p in parts if p]
    rules = [p for p in parts if ":-" in p or "{" in p or p.startswith("#")
             or re.search(r"\b[A-Z]\w*", p.split("(")[1] if "(" in p else "")]
    return rules, [p for p in parts if p not in rules]


def kept(a, b):
    ca, cb = collections.Counter(a), collections.Counter(b)
    return sum((ca & cb).values()) / sum(ca.values())


def changed(a, b):
    ca, cb = collections.Counter(a), collections.Counter(b)
    return sum((ca - cb).values()) + sum((cb - ca).values())


def starts_asp(out):
    return {int(j): int(t) for j, t in re.findall(r"start\((\d+),(\d+)\)", out or "")} or None


def starts_nl(art):
    m = re.search(r"\{(.*)\}", art or "")
    return {int(a): int(b) for a, b in re.findall(r"(\d+)\s*:\s*(\d+)", m.group(1))} if m else None


def same(a, b):
    if not a or not b:
        return None
    return sum(a[k] == b.get(k) for k in a) / len(a)


def load(path):
    return {(r["instance_id"], r["arm"], r["loop_attempt"]): r
            for r in map(json.loads, open(path)) if r["outcome"] != "api_error"}


d = load("results_A_v5/results.jsonl")
for arm in ("m3_asp", "m3_nl"):
    R = collections.defaultdict(list)
    for (i, a, k), r in d.items():
        n = d.get((i, a, k + 1))
        if a != arm or not n:
            continue
        if arm == "m3_asp":
            r1, f1 = stmts(r["artifact"]); r2, f2 = stmts(n["artifact"])
            if r1 and r2:
                R["rules kept"].append(kept(r1, r2)); R["statements changed"].append(changed(r1, r2))
                R["facts kept"].append(kept(f1, f2) if f1 else 1.0)
            s = same(starts_asp(r.get("solver_output")), starts_asp(n.get("solver_output")))
        else:
            s = same(starts_nl(r["artifact"]), starts_nl(n["artifact"]))
        if s is not None:
            R["start times kept"].append(s)
    print(arm, {k: f"median {st.median(v):.2f}, mean {st.mean(v):.2f}, n={len(v)}" for k, v in R.items()})

d = load("results_A_v3/results.jsonl")
for arm in ("binary", "diagnostic"):
    K = []
    for (i, a, k), r in d.items():
        prev = d.get((i, a, k - 1)) or (d.get((i, "shared", 1)) if k == 2 else None)
        if a != arm or not prev:
            continue
        r1, _ = stmts(prev["artifact"]); r2, _ = stmts(r["artifact"])
        if r1 and r2:
            K.append(kept(r1, r2))
    print(arm, f"rules kept median {st.median(K):.2f}, mean {st.mean(K):.2f}, n={len(K)}")
