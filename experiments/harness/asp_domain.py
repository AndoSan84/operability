"""ASP job-shop domain for Experiment A.

Instance generation is the vendored generator (vendor/operability, read-only), wrapped so that its
global `random.seed` cannot leak into the caller. Validation is re-implemented to return the full
set of violations, not the first one: the diagnostic feedback and the uptake/regression measures
need all of them. tests/test_asp_domain.py checks it differentially against the vendored
validator and against a brute-force solver.
"""

import json
import random
import subprocess
import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "vendor/operability/asp_scheduling_replication"

PROBLEM_TEMPLATE = """You are solving a job-shop scheduling problem.

Jobs (id, machine, duration):
{jobs}
Precedence constraints (i before j), meaning job i must finish before job j starts:
{precedences}
Deadline (all jobs must finish by): {deadline}
No two jobs on the same machine may overlap in time."""

# experiment-B-context-strip.md §4.4, the formal attempt-1 prompt, used by Experiment A unchanged
ATTEMPT1_TEMPLATE = """{problem}

Write a Clingo (ASP) program that encodes this problem and whose answer set gives a valid
schedule. Emit the schedule with atoms of the form start(Job, Time).

Return exactly one ```clingo code block and nothing else."""


def _vendor():
    if str(VENDOR) not in sys.path:
        sys.path.insert(0, str(VENDOR))
    import asp_scheduling_test
    return asp_scheduling_test


def generate(n_jobs, n_machines, n_precedences, seed, max_offsets=50):
    """One instance, deterministic in (params, seed). The vendored generator can return None;
    successive seeds are tried and the one used is recorded."""
    v = _vendor()
    state = random.getstate()
    try:
        for off in range(max_offsets):
            inst = v.generate_scheduling_instance(n_jobs, n_machines, n_precedences, seed + off)
            if inst is not None:
                return {
                    "params": [n_jobs, n_machines, n_precedences], "seed": seed + off,
                    "jobs": {int(j): {"machine": d["machine"], "duration": int(d["duration"])}
                             for j, d in inst["jobs"].items()},
                    "precedences": [[int(a), int(b)] for a, b in inst["precedences"]],
                    "deadline": int(inst["deadline"]),
                    "reference_solution": {int(j): int(t)
                                           for j, t in inst["reference_solution"].items()},
                }
    finally:
        random.setstate(state)
    raise RuntimeError(f"no instance for {(n_jobs, n_machines, n_precedences)} near seed {seed}")


def from_json(d):
    """JSON turns int keys into strings; restore them."""
    d = dict(d)
    d["jobs"] = {int(j): v for j, v in d["jobs"].items()}
    d["reference_solution"] = {int(j): t for j, t in d["reference_solution"].items()}
    return d


def problem_block(inst):
    jobs = "\n".join(f"({j}, {inst['jobs'][j]['machine']}, {inst['jobs'][j]['duration']})"
                     for j in sorted(inst["jobs"]))
    precs = "\n".join(f"({a}, {b})" for a, b in inst["precedences"]) or "(none)"
    return PROBLEM_TEMPLATE.format(jobs=jobs, precedences=precs, deadline=inst["deadline"])


def attempt1_prompt(inst):
    return ATTEMPT1_TEMPLATE.format(problem=problem_block(inst))


# ---------------------------------------------------------------- validation

def violations(inst, starts):
    """starts: list of (job, time) pairs as emitted (duplicates and unknown jobs preserved).
    Returns a sorted list of normalised ids; empty iff the schedule is valid."""
    jobs, out = inst["jobs"], set()
    seen = {}
    for j, t in starts:
        if j not in jobs:
            out.add(f"unknown_job:{j}")
        elif j in seen and seen[j] != t:
            out.add(f"duplicate:{j}")
        else:
            seen[j] = t
    for j in jobs:
        if j not in seen:
            out.add(f"missing:{j}")
    for j, t in seen.items():
        if t < 0:
            out.add(f"negative:{j}")
        if t + jobs[j]["duration"] > inst["deadline"]:
            out.add(f"deadline:{j}")
    for a, b in inst["precedences"]:
        if a in seen and b in seen and seen[b] < seen[a] + jobs[a]["duration"]:
            out.add(f"precedence:{a}:{b}")
    placed = sorted(seen)
    for x in range(len(placed)):
        for y in range(x + 1, len(placed)):
            a, b = placed[x], placed[y]
            if jobs[a]["machine"] != jobs[b]["machine"]:
                continue
            sa, sb = seen[a], seen[b]
            if sa < sb + jobs[b]["duration"] and sb < sa + jobs[a]["duration"]:
                out.add(f"overlap:{jobs[a]['machine']}:{a}:{b}")
    return sorted(out)


def describe(inst, vid):
    """One human-readable line per violation id, for the diagnostic feedback block."""
    kind, *rest = vid.split(":")
    jobs = inst["jobs"]
    if kind == "overlap":
        m, a, b = rest
        return f"- jobs {a} and {b} overlap on machine {m}"
    if kind == "precedence":
        a, b = rest
        return f"- job {b} starts before job {a} finishes (job {a} must finish before job {b} starts)"
    if kind == "deadline":
        return f"- job {rest[0]} finishes after the deadline {inst['deadline']}"
    if kind == "missing":
        return f"- job {rest[0]} has no start time"
    if kind == "duplicate":
        return f"- job {rest[0]} has more than one start time"
    if kind == "negative":
        return f"- job {rest[0]} has a negative start time"
    if kind == "unknown_job":
        return f"- start time given for job {rest[0]}, which does not exist"
    return f"- {vid}"


# ---------------------------------------------------------------- execution

def run_clingo(program, timeout_s):
    """Run a model-written program in a separate process, so a runaway grounding can be killed.
    Returns (category, starts, solver_output) with category one of
    syntax_error | solver_timeout | unsat | sat."""
    try:
        proc = subprocess.run([sys.executable, "-m", "harness.clingo_worker"], input=program,
                              capture_output=True, text=True, timeout=timeout_s,
                              cwd=str(Path(__file__).resolve().parent.parent))
    except subprocess.TimeoutExpired:
        return "solver_timeout", [], f"Clingo did not finish within {timeout_s} seconds."
    try:
        res = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return "syntax_error", [], (proc.stderr or proc.stdout or "clingo crashed").strip()[-1500:]
    return res["category"], [tuple(x) for x in res["starts"]], res["output"]


def classify(inst, program, timeout_s):
    """Full attempt outcome for a program: category, violations, solver output, schedule."""
    if program is None:
        return {"outcome": "unparsable", "violations": [], "solver_output": ""}
    cat, starts, output = run_clingo(program, timeout_s)
    if cat in ("syntax_error", "solver_timeout"):
        return {"outcome": cat, "violations": [], "solver_output": output}
    if cat == "unsat" or not starts:
        return {"outcome": "unsat", "violations": [], "solver_output": output}
    v = violations(inst, starts)
    return {"outcome": "valid" if not v else "invalid_schedule", "violations": v,
            "solver_output": output, "starts": starts}
