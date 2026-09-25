"""Runner for Experiment A (experiment-A-feedback-ablation.md, config/experiment_A.frozen.yaml).

Resumable by construction (spec §8a): every call is appended and flushed before the next is
issued, and each invocation rebuilds its state from the results files. A loop attempt is done iff
its last API try is not `api_error`. A usage-limit block ends the batch without writing a row;
the next invocation resumes where this one stopped, interrupted instances first.

    python -m harness.runner_A status
    python -m harness.runner_A calibration --max-calls 10
    python -m harness.runner_A instances
    python -m harness.runner_A pilot --max-calls 10
    python -m harness.runner_A m1 --max-calls 30
    python -m harness.runner_A m4 --max-calls 30

--backend fake --out <dir> --instances-dir <dir> gives a dry run that spends nothing.

Seed derivations (mechanical, recorded in every instance): calibration instance k of grid point g
uses calibration_seed + 100000*g + 1000*k; frozen instance i uses seed + 1000*i; M4 instance i
uses seed + 10_000_000 + 1000*i at the hardest grid point. The vendored generator may skip ahead
up to 50 seeds; the seed actually used is stored.
"""

import argparse
import datetime as dt
import hashlib
import json
import math
import random
import sys
from pathlib import Path

import yaml

from harness import asp_domain, contamination, parsers, prompts_A

ROOT = Path(__file__).resolve().parent.parent
ARMS = ("binary", "diagnostic")


def set_config(path):
    """Load a frozen config; every stage reads these globals."""
    global CFG_PATH, CFG, CONFIG_HASH, ELIGIBLE, INFRA, CLINGO_TIMEOUT
    CFG_PATH = Path(path)
    CFG = yaml.safe_load(open(CFG_PATH))
    CONFIG_HASH = hashlib.sha256(CFG_PATH.read_bytes()).hexdigest()
    ELIGIBLE = set(CFG["branching"]["eligible"])
    INFRA = set(CFG["branching"]["infrastructure"])
    CLINGO_TIMEOUT = CFG["branching"]["clingo_timeout_seconds"]


set_config(ROOT / "config/experiment_A.frozen.yaml")
PILOT_TIMEOUT = 600          # C8: generous, so the pilot latency p99 is not censored
MAX_CONSECUTIVE_API_ERRORS = 3


class Stop(Exception):
    """End this invocation; the message says why. Files already written stay valid."""


# ---------------------------------------------------------------- small utilities

def wilson_upper(k, n, z=1.96):
    if n == 0:
        return 1.0
    p = k / n
    d = 1 + z * z / n
    return min(1.0, (p + z * z / (2 * n)) / d + z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d)


def load_jsonl(path):
    if not Path(path).exists():
        return []
    return [json.loads(l) for l in open(path) if l.strip()]


def append_jsonl(path, row):
    with open(path, "a") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.flush()
        import os
        os.fsync(fh.fileno())


class Run:
    def __init__(self, out, instances_dir, backend):
        self.out, self.idir, self.backend = Path(out), Path(instances_dir), backend
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "prompts").mkdir(exist_ok=True)
        self.derived_path = self.out / "derived.json"
        self.derived = json.loads(self.derived_path.read_text()) if self.derived_path.exists() else {}
        self.batch_id = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
        self.calls_this_batch = 0
        self.consecutive_api_errors = 0
        for blocker in ("STRUCTURAL_ABORT.md",):
            if (self.out / blocker).exists():
                raise Stop(f"{blocker} exists: a human must read it before anything else runs")
        v = self.derived.get("backend_version")
        if v is None:
            self.derived["backend_version"] = backend.version
            self.save_derived()
        elif v != backend.version:
            raise Stop(f"backend version changed: {v} -> {backend.version}; the run aborts (C8)")

    def save_derived(self):
        self.derived_path.write_text(json.dumps(self.derived, indent=2))

    def log(self, msg):
        with open(self.out / "runner.log", "a") as fh:
            fh.write(f"{dt.datetime.now().isoformat()} [{self.batch_id}] {msg}\n")
        print(msg)

    # ------------------------------------------------------------ one model call = one row
    def call(self, file, budget, *, module, inst, instance_id, arm, loop_attempt, prompt,
             timeout_s, blocks=None):
        if self.calls_this_batch >= budget:
            raise Stop(f"batch budget of {budget} calls reached")
        rows = load_jsonl(file)
        api_try = sum(1 for r in rows if r["module"] == module and r["instance_id"] == instance_id
                      and r["arm"] == arm and r["loop_attempt"] == loop_attempt)
        psha = hashlib.sha256(prompt.encode()).hexdigest()
        (self.out / "prompts" / f"{psha}.txt").write_text(prompt)
        try:
            res = self.backend.call(prompt, timeout_s)
        except Exception as e:                     # UsageLimit and anything unexpected
            if type(e).__name__ == "UsageLimit":
                self.log(f"usage limit reached; batch ends, resume later: {str(e)[:200]}")
                raise Stop("usage limit reached")
            raise
        self.calls_this_batch += 1
        code = parsers.extract_code(res.get("text"), "clingo")
        if res.get("outcome_hint") in ("api_error", "timeout", "max_tokens"):
            cls = {"outcome": res["outcome_hint"], "violations": [], "solver_output": ""}
        else:
            cls = asp_domain.classify(inst, code, CLINGO_TIMEOUT)
        matches = contamination.scan(res.get("text"))
        row = {
            "run_id": f"A-{self.batch_id}", "config_hash": CONFIG_HASH,
            "timestamp": dt.datetime.now().isoformat(), "batch_id": self.batch_id,
            "backend": self.backend.name, "backend_version": self.backend.version,
            "model_requested": self.backend.model, "model_id": res.get("model_id"),
            "effort": "low", "temperature": "backend_default", "max_output_tokens": "backend_default",
            "module": module, "domain": "asp", "instance_id": instance_id,
            "instance_seed": inst["seed"], "instance_params": inst["params"],
            "arm": arm, "loop_attempt": loop_attempt, "api_try": api_try,
            "prompt_sha256": psha, "prompt_blocks_sha256": (
                {k: hashlib.sha256(v.encode()).hexdigest() for k, v in blocks.items()}
                if blocks else None),
            "raw_response": res.get("text"), "stop_reason": res.get("stop_reason"),
            "num_turns": res.get("num_turns"), "input_tokens": res.get("input_tokens"),
            "output_tokens": res.get("output_tokens"), "latency_ms": res.get("latency_ms"),
            "cost_usd": res.get("cost_usd"), "session_id": res.get("session_id"),
            "artifact": code, "outcome": cls["outcome"], "violations": cls["violations"],
            "solver_output": (cls.get("solver_output") or "")[:1500],
            "contaminated": bool(matches), "contamination_matches": matches,
            "structural_violations": res.get("structural_violations") or [],
            "notes": res.get("stderr") or None,
        }
        if row["structural_violations"]:
            row["outcome"] = "api_error"           # not an attempt: excluded by the analysis
        append_jsonl(file, row)
        if row["structural_violations"]:
            (self.out / "STRUCTURAL_ABORT.md").write_text(
                f"# Structural check failed\n\nModule {module}, instance {instance_id}, arm {arm}, "
                f"attempt {loop_attempt}:\n\n" + "\n".join(f"- {v}" for v in row["structural_violations"])
                + "\n\nThe run is aborted (AMENDMENTS-v3 C8). Nothing resumes until this file is "
                  "read and removed by a human.\n")
            raise Stop("structural check failed: STRUCTURAL_ABORT.md written")
        if row["outcome"] in INFRA:
            self.consecutive_api_errors += 1
            if self.consecutive_api_errors >= MAX_CONSECUTIVE_API_ERRORS:
                raise Stop(f"{MAX_CONSECUTIVE_API_ERRORS} consecutive api_error: batch ends")
        else:
            self.consecutive_api_errors = 0
        self.log(f"{module} {instance_id} {arm} a{loop_attempt} try{api_try}: {row['outcome']}"
                 f"{' CONTAMINATED' if matches else ''}")
        return row


# ---------------------------------------------------------------- state of a feedback module

def latest(rows, module, instance_id, arm, att):
    """Last try of a loop attempt, by api_try then file order (the analysis script's rule)."""
    best = None
    for pos, r in enumerate(rows):
        if (r["module"], r["instance_id"], r["arm"], r["loop_attempt"]) == (module, instance_id, arm, att):
            if best is None or (r.get("api_try", 0), pos) >= best[0]:
                best = ((r.get("api_try", 0), pos), r)
    return best[1] if best else None


def done(row):
    return row is not None and row["outcome"] not in INFRA


def arm_order(instance_id):
    rng = random.Random(f"{CFG['instances']['seed']}:{instance_id}")
    order = list(ARMS)
    rng.shuffle(order)
    return order


def next_call(rows, module, instance_id):
    """(arm, attempt, previous row) for the next call of this instance, or None if finished."""
    first = latest(rows, module, instance_id, "shared", 1)
    if not done(first):
        return ("shared", 1, None)
    if first["outcome"] not in ELIGIBLE:
        return None
    for att in (2, 3):
        for arm in arm_order(instance_id):
            prev = first if att == 2 else latest(rows, module, instance_id, arm, 2)
            if att == 3 and (not done(prev) or prev["outcome"] == "valid"):
                continue
            if not done(latest(rows, module, instance_id, arm, att)):
                return (arm, att, prev)
    return None


def run_feedback_module(run, file, module, instances, budget, *, timeout_s, target=None,
                        max_attempt1=None, stop_rule=None, cap=None):
    """Pilot, M1 and M4: attempt 1 shared, then both arms, instance by instance."""
    while True:
        rows = [r for r in load_jsonl(file) if r["module"] == module]
        if cap is not None and len(rows) >= cap:
            raise Stop(f"{module}: call cap {cap} reached")
        started = [i["id"] for i in instances
                   if any(r["instance_id"] == i["id"] for r in rows)]
        pending = [iid for iid in started if next_call(rows, module, iid) is not None]
        if pending:
            iid = pending[0]
        else:
            firsts = [latest(rows, module, iid, "shared", 1) for iid in started]
            n_a1 = sum(1 for f in firsts if done(f))
            n_elig = sum(1 for f in firsts if done(f) and f["outcome"] in ELIGIBLE)
            if target is not None and n_elig >= target:
                return f"{module}: target of {target} branched instances reached and all arms finished"
            if max_attempt1 is not None and n_a1 >= max_attempt1:
                return f"{module}: attempt-1 cap {max_attempt1} reached with {n_elig} branched"
            if stop_rule and n_a1 >= 20 and wilson_upper(n_elig, n_a1) * max_attempt1 < target:
                (run.out / f"{module}_STOPPED.md").write_text(
                    f"# {module} stopped: no material\n\n{n_elig} eligible failures in {n_a1} "
                    f"attempt-1 instances; Wilson upper bound x {max_attempt1} < {target}: the "
                    f"contrast has no material (spec §3). Attempt-1 outcomes: "
                    f"{dict(__import__('collections').Counter(f['outcome'] for f in firsts if done(f)))}"
                    f" — a ceiling if nearly all are valid, the symbolic bottleneck if they do not run.\n")
                raise Stop(f"{module}: stop rule fired, {module}_STOPPED.md written")
            remaining = [i["id"] for i in instances if i["id"] not in started]
            if not remaining:
                return f"{module}: instance list exhausted"
            iid = remaining[0]
        inst = next(i for i in instances if i["id"] == iid)
        arm, att, prev = next_call(rows, module, iid)
        if att == 1:
            prompt, blocks = asp_domain.attempt1_prompt(inst), None
        else:
            blocks = prompts_A.blocks(inst, arm, prev, prev.get("artifact"))
            if att == 2:                       # branch-identity gate, both arms, every instance
                other = [a for a in ARMS if a != arm][0]
                if not prompts_A.branch_identity(blocks, prompts_A.blocks(inst, other, prev, prev.get("artifact"))):
                    (run.out / "STRUCTURAL_ABORT.md").write_text(
                        f"# Branch identity failed\n\n{module} {iid}: the attempt-2 contexts differ "
                        f"outside the feedback block.\n")
                    raise Stop("branch identity failed")
            prompt = prompts_A.render(blocks)
        run.call(file, budget, module=module, inst=inst, instance_id=iid, arm=arm,
                 loop_attempt=att, prompt=prompt, timeout_s=timeout_s, blocks=blocks)


# ---------------------------------------------------------------- stages

def load_instances(path):
    return [dict(asp_domain.from_json(d)) for d in json.loads(Path(path).read_text())]


def stage_calibration(run, budget):
    file = run.out / "calibration.jsonl"
    grid, per = CFG["calibration"]["grid"], CFG["calibration"]["per_point"]
    cseed = CFG["instances"]["calibration_seed"]
    cal_path = run.out / "calibration_instances.json"
    if cal_path.exists():
        insts = load_instances(cal_path)
    else:
        insts = []
        for g, params in enumerate(grid):
            for k in range(per):
                inst = asp_domain.generate(*params, seed=cseed + 100000 * g + 1000 * k)
                inst["id"], inst["grid_index"] = f"g{g}k{k}", g
                insts.append(inst)
        cal_path.write_text(json.dumps(insts))
    cap = CFG["budget"]["caps_calls"]["calibration"]
    for inst in insts:
        rows = load_jsonl(file)
        if len(rows) >= cap:
            raise Stop("calibration: call cap reached")
        if done(latest(rows, "calibration", inst["id"], "shared", 1)):
            continue
        run.call(file, budget, module="calibration", inst=inst, instance_id=inst["id"],
                 arm="shared", loop_attempt=1, prompt=asp_domain.attempt1_prompt(inst),
                 timeout_s=PILOT_TIMEOUT)
    rows = load_jsonl(file)
    rates = []
    for g, params in enumerate(grid):
        fs = [latest(rows, "calibration", i["id"], "shared", 1) for i in insts if i["grid_index"] == g]
        fs = [f for f in fs if done(f)]
        k = sum(f["outcome"] in ELIGIBLE for f in fs)
        rates.append({"grid_index": g, "params": params, "eligible": k, "n": len(fs),
                      "rate": k / len(fs) if fs else None,
                      "outcomes": [f["outcome"] for f in fs]})
    best = min((r for r in rates if r["rate"] is not None),
               key=lambda r: (abs(r["rate"] - CFG["calibration"]["target"]), -r["grid_index"]))
    run.derived["calibration"] = {"per_point": rates, "chosen": best}
    run.save_derived()
    return f"calibration complete: chosen grid point {best['params']} (eligible-failure rate {best['rate']:.2f})"


def stage_instances(run):
    cal = run.derived.get("calibration")
    if not cal:
        raise Stop("run calibration first: the frozen list is generated at the chosen difficulty")
    run.idir.mkdir(parents=True, exist_ok=True)
    main_path, m4_path = run.idir / "asp_A.json", run.idir / "asp_A_m4.json"
    if main_path.exists():
        raise Stop(f"{main_path} exists: the instance list is generated once")
    seed = CFG["instances"]["seed"]
    n_main = CFG["instances"]["n_pilot"] + CFG["instances"]["m1_max_attempt1_instances"]
    main = []
    for i in range(n_main):
        inst = asp_domain.generate(*cal["chosen"]["params"], seed=seed + 1000 * i)
        inst["id"] = f"a{i:03d}"
        main.append(inst)
    hardest = CFG["calibration"]["grid"][-1]
    m4 = []
    for i in range(CFG["budget"]["caps_calls"]["m4"]):
        inst = asp_domain.generate(*hardest, seed=seed + 10_000_000 + 1000 * i)
        inst["id"] = f"m4_{i:03d}"
        m4.append(inst)
    main_path.write_text(json.dumps(main))
    m4_path.write_text(json.dumps(m4))
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}" for p in (main_path, m4_path)]
    (run.idir / "INSTANCES_A.sha256").write_text("\n".join(lines) + "\n")
    return f"instances written: {len(main)} main at {cal['chosen']['params']}, {len(m4)} M4 at {hardest}"


def verify_instances(run):
    recorded = dict(l.split()[::-1] for l in (run.idir / "INSTANCES_A.sha256").read_text().splitlines())
    for name, digest in recorded.items():
        if hashlib.sha256((run.idir / name).read_bytes()).hexdigest() != digest:
            raise Stop(f"instance file {name} does not match INSTANCES_A.sha256")


def stage_pilot(run, budget):
    verify_instances(run)
    insts = load_instances(run.idir / "asp_A.json")[:CFG["instances"]["n_pilot"]]
    file = run.out / "pilot.jsonl"
    msg = run_feedback_module(run, file, "pilot", insts, budget, timeout_s=PILOT_TIMEOUT,
                              cap=CFG["budget"]["caps_calls"]["pilot"])
    rows = [r for r in load_jsonl(file) if r["module"] == "pilot"]
    answered = [r for r in rows if r["outcome"] not in INFRA]
    gates = {"contamination_per_arm": {}, "parse_failure_rate": None}
    for arm in ("shared",) + ARMS:
        rs = [r for r in answered if r["arm"] == arm]
        gates["contamination_per_arm"][arm] = (sum(r["contaminated"] for r in rs) / len(rs)) if rs else 0.0
    gates["parse_failure_rate"] = (sum(r["outcome"] == "unparsable" for r in answered) / len(answered)
                                   if answered else 0.0)
    lat = sorted(r["latency_ms"] for r in answered if r.get("latency_ms"))
    p99 = lat[min(len(lat) - 1, math.ceil(0.99 * len(lat)) - 1)] if lat else 0
    timeout = max(180, math.ceil(2 * p99 / 1000))
    g = CFG["gates"]["pilot"]
    failed = [f"contamination {a} {v:.1%} > {g['max_contamination_rate_per_arm']:.0%}"
              for a, v in gates["contamination_per_arm"].items() if v > g["max_contamination_rate_per_arm"]]
    if gates["parse_failure_rate"] > g["max_parse_failure_rate"]:
        failed.append(f"parse failures {gates['parse_failure_rate']:.1%} > {g['max_parse_failure_rate']:.0%}")
    gates.update({"latency_p99_ms": p99, "full_run_timeout_s": timeout, "failed": failed,
                  "passed": not failed})
    run.derived["pilot_gates"], run.derived["timeout_s"] = gates, timeout
    run.save_derived()
    name = "PILOT_REPORT.md" if not failed else "PILOT_BLOCKED.md"
    (run.out / name).write_text(f"# Pilot\n\n{msg}\n\n```json\n{json.dumps(gates, indent=2)}\n```\n")
    if failed:
        raise Stop("pilot gate failed: PILOT_BLOCKED.md written; change nothing")
    return f"{msg}; gates passed; full-run timeout {timeout}s"


def stage_m1(run, budget):
    if not run.derived.get("pilot_gates", {}).get("passed"):
        raise Stop("M1 needs a completed pilot with every gate passed")
    verify_instances(run)
    insts = load_instances(run.idir / "asp_A.json")[CFG["instances"]["n_pilot"]:]
    return run_feedback_module(
        run, run.out / "results.jsonl", "M1", insts, budget, timeout_s=run.derived["timeout_s"],
        target=CFG["instances"]["m1_target_branched"],
        max_attempt1=CFG["instances"]["m1_max_attempt1_instances"], stop_rule=True,
        cap=CFG["budget"]["caps_calls"]["m1"])


def stage_m4(run, budget):
    rows = [r for r in load_jsonl(run.out / "results.jsonl") if r["module"] == "M1"]
    if not rows:
        raise Stop("M4 runs after M1")
    verify_instances(run)
    return run_feedback_module(
        run, run.out / "results.jsonl", "M4", load_instances(run.idir / "asp_A_m4.json"), budget,
        timeout_s=run.derived["timeout_s"], target=CFG["instances"]["m4_target_branched"],
        cap=CFG["instances"]["m4_max_calls"])


def stage_status(run):
    lines = [f"backend {run.backend.name} {run.derived.get('backend_version')}"]
    for name in ("calibration.jsonl", "pilot.jsonl", "results.jsonl"):
        rows = load_jsonl(run.out / name)
        by = {}
        for r in rows:
            by.setdefault(r["module"], []).append(r)
        for m, rs in by.items():
            firsts = {r["instance_id"] for r in rs if r["loop_attempt"] == 1 and r["outcome"] not in INFRA}
            elig = {r["instance_id"] for r in rs if r["loop_attempt"] == 1 and r["outcome"] in ELIGIBLE}
            lines.append(f"{m}: {len(rs)} calls, {len(firsts)} attempt-1 instances, {len(elig)} branched"
                         " (arm outcomes are not shown before the end: spec §8a)")
    for f in ("STRUCTURAL_ABORT.md", "PILOT_BLOCKED.md", "PILOT_REPORT.md", "M1_STOPPED.md"):
        if (run.out / f).exists():
            lines.append(f"file present: {f}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["status", "calibration", "instances", "pilot", "m1", "m4"])
    ap.add_argument("--max-calls", type=int, default=0, help="model calls in this batch")
    ap.add_argument("--backend", choices=["cli", "fake"], default="cli")
    ap.add_argument("--config", default="config/experiment_A.frozen.yaml")
    ap.add_argument("--out", default=None, help="default: the config's results_dir, else results_A")
    ap.add_argument("--instances-dir", default=None, help="default: the hash file's directory")
    args = ap.parse_args(argv)
    set_config(ROOT / args.config if not Path(args.config).is_absolute() else args.config)
    args.out = args.out or CFG["instances"].get("results_dir", "results_A")
    args.instances_dir = args.instances_dir or str(Path(CFG["instances"]["hash_file"]).parent)
    if args.backend == "cli":
        from harness.cli_backend import CliBackend
        backend = CliBackend(CFG["model"]["confirmatory"])
    else:
        from harness.fake_backend import FakeBackend
        backend = FakeBackend()
    try:
        run = Run(ROOT / args.out if not Path(args.out).is_absolute() else args.out,
                  ROOT / args.instances_dir if not Path(args.instances_dir).is_absolute()
                  else args.instances_dir, backend)
        fn = {"status": lambda: stage_status(run), "instances": lambda: stage_instances(run),
              "calibration": lambda: stage_calibration(run, args.max_calls),
              "pilot": lambda: stage_pilot(run, args.max_calls),
              "m1": lambda: stage_m1(run, args.max_calls),
              "m4": lambda: stage_m4(run, args.max_calls)}[args.stage]
        msg = fn()
        print(msg)
        if args.stage not in ("status",):
            run.log(msg)
        return 0
    except Stop as s:
        print(f"STOP: {s}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
