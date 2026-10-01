"""Post hoc (not pre-registered): how repair proceeds in Experiment 2B (M3).

For each instance and medium, compares consecutive attempts k -> k+1 in which both produced a
schedule: share of reported violations removed, steps introducing new violations, new violations
per step, and repaired violations that return at attempt 3. Also the loop success per initial
failure. Usage: python3 analysis/posthoc/repair_steps.py [results_A_v5/results.jsonl]
"""
import json, statistics as st, sys

path = sys.argv[1] if len(sys.argv) > 1 else "results_A_v5/results.jsonl"
rows = [json.loads(l) for l in open(path)]
d = {(r["instance_id"], r["arm"], r["loop_attempt"]): r for r in rows if r["outcome"] != "api_error"}


def V(r):
    return set(r["violations"] or []) if r and r["outcome"] in ("invalid_schedule", "valid") else None


for arm in ("m3_asp", "m3_nl"):
    rem = tot = new = steps = steps_new = ret = rep = initfail = succ = 0
    first = []
    for i in sorted({k[0] for k in d if k[1] == arm}):
        seq = [d.get((i, arm, a)) for a in (1, 2, 3)]
        if seq[0]["outcome"] == "invalid_schedule":
            first.append(len(seq[0]["violations"]))
        if seq[0]["outcome"] != "valid":
            initfail += 1
            succ += any(s and s["outcome"] == "valid" for s in seq[1:])
        vs = [V(s) for s in seq]
        for k in (0, 1):
            if vs[k] and vs[k + 1] is not None:
                steps += 1; tot += len(vs[k]); rem += len(vs[k] - vs[k + 1])
                n = len(vs[k + 1] - vs[k]); new += n; steps_new += n > 0
        if vs[0] and vs[1] is not None and vs[2] is not None:
            r_ = vs[0] - vs[1]; rep += len(r_); ret += len(r_ & vs[2])
    print(f"{arm}: removed {rem}/{tot} ({rem/tot:.0%}); steps with new {steps_new}/{steps}; "
          f"new per step {new/steps:.2f}; returned {ret}/{rep}; first-attempt median {st.median(first)}; "
          f"loop success after initial failure {succ}/{initfail}")
