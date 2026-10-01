"""Experiment A v5, module M3: prompts, NL scoring, the runner stage, and the v5 analysis.

    pytest -q tests/test_M3.py
"""

import copy
import hashlib
import importlib.util
import json
import re
import subprocess
import sys

import pytest
import yaml

from harness import asp_domain, prompts_M3, runner_A
from harness.fake_backend import CORRECT, _facts

V5 = "config/experiment_A_v5.frozen.yaml"
SCRIPT = "analysis/analyze_experiment_A_v5.py"
SMALL = (5, 2, 3)


@pytest.fixture(scope="module")
def inst():
    i = asp_domain.generate(*SMALL, seed=100)
    i["id"] = "t"
    return i


# ---------------------------------------------------------------- prompts and scoring

def test_problem_block_is_shared_and_instructions_differ(inst):
    nl, asp = prompts_M3.attempt1(inst, "m3_nl"), prompts_M3.attempt1(inst, "m3_asp")
    problem = asp_domain.problem_block(inst)
    assert nl.startswith(problem) and asp.startswith(problem) and nl != asp
    assert nl.endswith("SCHEDULE: {1: t1, 2: t2, ...}") and "Do not write code" in nl


def test_same_validator_feedback_in_both_media(inst):
    v = ["overlap:A:1:3"]
    nl = prompts_M3.retry(inst, "m3_nl", {"outcome": "invalid_schedule", "violations": v,
                                          "artifact": "SCHEDULE: {1: 0}"})
    asp = prompts_M3.retry(inst, "m3_asp", {"outcome": "invalid_schedule", "violations": v,
                                            "solver_output": "SATISFIABLE", "artifact": "x."})
    line = asp_domain.describe(inst, v[0])
    assert line in nl and line in asp
    assert "Clingo output: SATISFIABLE" in asp and "Clingo output" not in nl
    assert "Your previous schedule:\nSCHEDULE: {1: 0}" in nl and "Your previous encoding:\nx." in asp


def test_medium_specific_feedback(inst):
    nl = prompts_M3.retry(inst, "m3_nl", {"outcome": "unparsable", "violations": [], "artifact": None})
    assert prompts_M3.NL_UNPARSABLE in nl and "Your previous schedule" not in nl
    unsat = prompts_M3.retry(inst, "m3_asp", {"outcome": "unsat", "violations": [], "artifact": "a."})
    assert prompts_M3.UNSAT in unsat and "Clingo output" not in unsat
    syn = prompts_M3.retry(inst, "m3_asp", {"outcome": "syntax_error", "violations": [],
                                            "solver_output": "<block>:1:1: error", "artifact": "a"})
    assert "<block>:1:1: error" in syn


def test_nl_scoring(inst):
    sol = inst["reference_solution"]
    good = "reasoning\nSCHEDULE: {" + ", ".join(f"{j}: {t}" for j, t in sol.items()) + "}"
    assert prompts_M3.classify_nl(inst, good)["outcome"] == "valid"
    assert prompts_M3.classify_nl(inst, "SCHEDULE: {1: 0}")["outcome"] == "invalid_schedule"
    assert prompts_M3.classify_nl(inst, "I cannot do this.")["outcome"] == "unparsable"
    dup = prompts_M3.classify_nl(inst, "SCHEDULE: {1: 0, 1: 5}")
    assert any(v.startswith("duplicate:1") for v in dup["violations"])


# ---------------------------------------------------------------- runner

class Scripted:
    """NL: solves on attempt 2 (fails attempt 1 by omitting job 1). ASP: correct program at
    attempt 1, or a syntax error first when `asp_syntax_first`. Knows nothing about arms but
    what the prompt says."""
    name, version, model = "fake", "fake-1", "fake-model"

    def __init__(self, insts, asp_syntax_first=False, nl_never=False):
        self.by_problem = {asp_domain.problem_block(i): i for i in insts}
        self.asp_syntax_first, self.nl_never = asp_syntax_first, nl_never

    def call(self, prompt, timeout_s):
        inst = next(i for p, i in self.by_problem.items() if prompt.startswith(p))
        retry = "Your schedule is not valid." in prompt or "The result is not a valid" in prompt
        if "Reason in prose" in prompt:
            sol = dict(inst["reference_solution"])
            if not retry or self.nl_never:
                sol.pop(min(sol))
            text = "SCHEDULE: {" + ", ".join(f"{j}: {t}" for j, t in sol.items()) + "}"
        else:
            prog = CORRECT.format(facts=_facts(asp_domain.attempt1_prompt(inst)))
            text = f"```clingo\n{prog.replace('1 {', '1 {{') if self.asp_syntax_first and not retry else prog}\n```"
        return {"outcome_hint": None, "text": text, "model_id": self.model,
                "structural_violations": [], "stderr": ""}


def _insts(n, seed=3000):
    out = []
    for i in range(n):
        x = asp_domain.generate(*SMALL, seed=seed + 1000 * i)
        x["id"] = f"u{i:02d}"
        out.append(x)
    return out


def test_m3_module_loops_both_media_and_resumes(tmp_path):
    runner_A.set_config(runner_A.ROOT / V5)
    try:
        insts = _insts(4)
        be = Scripted(insts, asp_syntax_first=True)
        for _ in range(30):
            run = runner_A.Run(tmp_path / "res", tmp_path / "inst", be)
            try:
                msg = runner_A.run_m3_module(run, tmp_path / "res" / "r.jsonl", "M3", insts, 3,
                                             timeout_s=60, cap=1000)
                break
            except runner_A.Stop as s:
                assert "batch budget" in str(s)
        assert "all 4 instances finished" in msg
    finally:
        runner_A.set_config(runner_A.ROOT / "config/experiment_A.frozen.yaml")
    rows = [json.loads(l) for l in open(tmp_path / "res" / "r.jsonl")]
    keys = [(r["instance_id"], r["arm"], r["loop_attempt"]) for r in rows]
    assert len(keys) == len(set(keys)) == 16                  # 4 x (2 NL + 2 ASP), none twice
    assert {(r["arm"], r["loop_attempt"], r["outcome"]) for r in rows} == {
        ("m3_nl", 1, "invalid_schedule"), ("m3_nl", 2, "valid"),
        ("m3_asp", 1, "syntax_error"), ("m3_asp", 2, "valid")}   # syntax errors are looped
    assert all(r["thinking"] == "disabled" for r in rows)


def test_stage_m3_floor_rule_moves_once(tmp_path, monkeypatch):
    runner_A.set_config(runner_A.ROOT / V5)
    try:
        cfg = copy.deepcopy(runner_A.CFG)
        cfg["m3"].update({"point": list(SMALL), "floor_fallback_point": [4, 2, 2], "n_pilot": 2,
                          "n_instances": 3})
        monkeypatch.setattr(runner_A, "CFG", cfg)
        pool = _insts(0)
        for pt in (SMALL, (4, 2, 2)):
            for seed in (cfg["m3"]["pilot_seed"], cfg["m3"]["seed"]):
                pool += [asp_domain.generate(*pt, seed=seed + 1000 * i) for i in range(3)]
        be = Scripted(pool, nl_never=True)                   # NL never valid at attempt 1
        run = runner_A.Run(tmp_path / "res", tmp_path / "inst", be)
        msg = runner_A.stage_m3(run, 1000)
    finally:
        runner_A.set_config(runner_A.ROOT / "config/experiment_A.frozen.yaml")
    d = json.loads((tmp_path / "res" / "derived.json").read_text())["m3"]
    assert d["moved"] is True and d["point"] == [4, 2, 2] and len(d["pilots"]) == 2
    assert "all 3 instances finished" in msg and "[4, 2, 2]" in msg


# ---------------------------------------------------------------- v5 analysis

def _an():
    spec = importlib.util.spec_from_file_location("an5", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def R(inst, arm, att, outcome, api_try=0, **kw):
    return dict(module="M3", domain="asp", instance_id=inst, arm=arm, loop_attempt=att,
                api_try=api_try, outcome=outcome, **kw)


def _run(tmp_path, rows):
    f = tmp_path / "r.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows))
    p = subprocess.run([sys.executable, SCRIPT, "--results", str(f), "--out", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return json.loads((tmp_path / "o" / "summary.json").read_text())["M3"]


def test_pending_or_infrastructure_arms_are_not_failures(tmp_path):
    rows = [R(0, "m3_asp", 1, "valid"), R(0, "m3_nl", 1, "invalid_schedule"),       # NL pending
            R(1, "m3_asp", 1, "valid"), R(1, "m3_nl", 1, "api_error"),              # NL infra
            R(2, "m3_asp", 1, "valid"), R(2, "m3_nl", 1, "valid")]
    m3 = _run(tmp_path, rows)
    assert m3["n_paired"] == 1 and m3["n_incomplete"] == 2


def test_verdicts(tmp_path):
    def pair(i, asp_ok, nl_ok):
        out = []
        for arm, ok in (("m3_asp", asp_ok), ("m3_nl", nl_ok)):
            out += [R(i, arm, 1, "valid")] if ok else [R(i, arm, a, "invalid_schedule") for a in (1, 2, 3)]
        return out
    adv = [r for i in range(40) for r in pair(i, True, i % 2 == 0)]
    assert _run(tmp_path, adv)["primary"]["verdict"] == "ASP advantage"
    rev = [r for i in range(40) for r in pair(i, i % 2 == 0, True)]
    assert _run(tmp_path, rev)["primary"]["verdict"].startswith("reversal")
    same = [r for i in range(200) for r in pair(i, i % 3 != 0, i % 3 != 0)]
    assert _run(tmp_path, same)["primary"]["verdict"].startswith("bounded")


def test_no_pairs_is_untestable(tmp_path):
    m3 = _run(tmp_path, [R(0, "m3_asp", 1, "valid")])
    assert m3["verdict"].startswith("untestable")


def test_v5_config_matches_script_and_sha():
    cfg = yaml.safe_load(open(V5))
    an = _an()
    a = cfg["analysis"]
    assert a["mei_medium"] == an.MEI_MEDIUM and a["alpha"] == an.ALPHA
    assert a["bootstrap"]["seed"] == an.BOOTSTRAP_SEED and a["bootstrap"]["reps"] == an.BOOTSTRAP_REPS
    assert a["script"] == SCRIPT
    assert a["sha256"] == hashlib.sha256(open(SCRIPT, "rb").read()).hexdigest()
