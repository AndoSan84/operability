"""Experiment A, module M2 (maze): parser, scoring, program runner, and the stage end to end.

    pytest -q tests/test_maze_M2.py
"""

import json

import pytest

from harness import maze_domain, runner_A


@pytest.fixture(scope="module")
def maze():
    inst = maze_domain.generate(7_000_000)
    inst["id"] = "t"
    return inst, maze_domain._vendor().solve_maze(inst["maze"], inst["n_keys"])


@pytest.mark.parametrize("text,expected", [
    ("PATH: [(0,0), (0,1)]", [(0, 0), (0, 1)]),
    ("**PATH:** [(0,0), (1,0)]", [(0, 0), (1, 0)]),
    ("PATH: [(0,0)]\nwrong, again:\nPATH: [(0,0), (0,1)]", [(0, 0), (0, 1)]),
    ("so the PATH: [(0,0), (0,1)] would be it, but I am unsure", None),
    ("End your response with exactly this format:\nPATH: [(0,0), (r1,c1), ...]", None),
    ("", None),
])
def test_extract_path(text, expected):
    assert maze_domain.extract_path(text) == expected


def _path_text(path):
    return "PATH: [" + ", ".join(f"({r},{c})" for r, c in path) + "]"


def test_scoring_of_prose_and_mental_answers(maze):
    inst, sol = maze
    for arm in ("m2_nl", "m2_mental"):
        assert maze_domain.classify(inst, arm, "reasoning\n" + _path_text(sol))["outcome"] == "valid"
        assert maze_domain.classify(inst, arm, _path_text(sol[:-1]))["outcome"] == "invalid_path"
        assert maze_domain.classify(inst, arm, "no answer")["outcome"] == "unparsable"


def test_scoring_of_executed_programs(maze):
    inst, sol = maze
    ok = f"```python\nprint({_path_text(sol)!r})\n```"
    assert maze_domain.classify(inst, "m2_exec", ok)["outcome"] == "valid"
    crash = "```python\nraise SystemExit('boom')\n```"
    assert maze_domain.classify(inst, "m2_exec", crash)["outcome"] == "exec_error"
    silent = "```python\nx = 1\n```"
    assert maze_domain.classify(inst, "m2_exec", silent)["outcome"] == "unparsable"
    assert maze_domain.classify(inst, "m2_exec", _path_text(sol))["outcome"] == "unparsable"


def test_program_runs_isolated_in_an_empty_directory():
    out, err = maze_domain.run_program("import os; print(os.listdir('.'))")
    assert err is None and out.strip() == "['solution.py']"
    out, err = maze_domain.run_program("while True: pass", timeout_s=1)
    assert err.startswith("timeout")


class Solver:
    """Answers every M2 prompt correctly, except the code-mental arm, which it leaves unparsable."""
    name, version, model = "fake", "fake-1", "fake-model"

    def __init__(self, insts):
        v = maze_domain._vendor()
        self.answers = {}
        for inst in insts:
            path = _path_text(v.solve_maze(inst["maze"], inst["n_keys"]))
            for arm in maze_domain.CELLS:
                text = {"m2_nl": path, "m2_mental": "I traced it but lost count.",
                        "m2_exec": f"```python\nprint({path!r})\n```"}[arm]
                self.answers[maze_domain.prompt(inst, arm)] = text

    def call(self, prompt, timeout_s):
        return {"outcome_hint": None, "text": self.answers[prompt], "model_id": self.model,
                "structural_violations": [], "stderr": ""}


def test_stage_m2_end_to_end_with_resume(tmp_path):
    runner_A.set_config(runner_A.ROOT / "config/experiment_A_v4.frozen.yaml")
    try:
        m2 = runner_A.CFG["m2"]
        insts = [maze_domain.generate(m2["seed_base"] + 1000 * i) for i in range(m2["n_instances"])]
        backend = Solver(insts)
        run = runner_A.Run(tmp_path / "res", tmp_path / "inst", backend)
        with pytest.raises(runner_A.Stop, match="batch budget"):
            runner_A.stage_m2(run, 7)
        run = runner_A.Run(tmp_path / "res", tmp_path / "inst", backend)
        assert "all 20" in runner_A.stage_m2(run, 1000)
    finally:
        runner_A.set_config(runner_A.ROOT / "config/experiment_A.frozen.yaml")
    rows = [json.loads(l) for l in open(tmp_path / "res" / "results.jsonl")]
    assert len(rows) == 60 and len({(r["instance_id"], r["arm"]) for r in rows}) == 60
    by_arm = {a: [r["outcome"] for r in rows if r["arm"] == a] for a in maze_domain.CELLS}
    assert by_arm["m2_nl"] == ["valid"] * 20 and by_arm["m2_exec"] == ["valid"] * 20
    assert by_arm["m2_mental"] == ["unparsable"] * 20
