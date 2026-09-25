"""Experiment A harness: validator, execution, prompts, and the runner's resume behaviour.

No model is called: the runner is driven by harness.fake_backend and by scripted backends.

    pytest -q tests/test_harness_A.py
"""

import itertools
import json
import sys
from pathlib import Path

import pytest

from harness import asp_domain, parsers, prompts_A, runner_A
from harness.fake_backend import CORRECT, FakeBackend, _facts

sys.path.insert(0, str(asp_domain.VENDOR))
import asp_scheduling_test as vendor  # noqa: E402

SMALL = (5, 2, 3)


@pytest.fixture(scope="module")
def small_instances():
    return [asp_domain.generate(*SMALL, seed=100 + 1000 * i) for i in range(4)]


# ---------------------------------------------------------------- validator

def test_reference_solutions_are_valid(small_instances):
    for inst in small_instances:
        assert asp_domain.violations(inst, list(inst["reference_solution"].items())) == []


def test_validator_agrees_with_vendor_and_brute_force(small_instances):
    """Every schedule in [0, deadline]^n: our verdict equals the vendored validator's, and the
    brute-force search finds a valid schedule exactly when the reference solution exists."""
    for inst in small_instances[:2]:
        jobs = sorted(inst["jobs"])
        found_valid = False
        for times in itertools.product(range(inst["deadline"] + 1), repeat=len(jobs)):
            sched = dict(zip(jobs, times))
            ours = asp_domain.violations(inst, list(sched.items())) == []
            theirs = vendor.validate_schedule(
                {"jobs": inst["jobs"], "precedences": [tuple(p) for p in inst["precedences"]],
                 "deadline": inst["deadline"]}, sched)["valid"]
            assert ours == theirs, (sched, asp_domain.violations(inst, list(sched.items())))
            found_valid |= ours
        assert found_valid


def test_all_violations_are_reported_not_only_the_first(small_instances):
    inst = small_instances[0]
    j = sorted(inst["jobs"])
    starts = [(j[0], -1), (j[0], 3), (99, 0)] + [(x, inst["deadline"]) for x in j[1:]]
    v = asp_domain.violations(inst, starts)
    kinds = {x.split(":")[0] for x in v}
    assert {"negative", "duplicate", "unknown_job", "deadline"} <= kinds


# ---------------------------------------------------------------- execution

def _prog(inst):
    return CORRECT.format(facts=_facts(asp_domain.attempt1_prompt(inst)))


def test_correct_encoding_is_valid(small_instances):
    for inst in small_instances:
        assert asp_domain.classify(inst, _prog(inst), 30)["outcome"] == "valid"


def test_outcome_categories(small_instances):
    inst = small_instances[0]
    assert asp_domain.classify(inst, None, 30)["outcome"] == "unparsable"
    assert asp_domain.classify(inst, "start(1,0", 30)["outcome"] == "syntax_error"
    assert asp_domain.classify(inst, "a. :- a.", 30)["outcome"] == "unsat"
    assert asp_domain.classify(inst, "a.", 30)["outcome"] == "unsat"          # no start/2 atoms
    assert asp_domain.classify(inst, "start(1,0).", 30)["outcome"] == "invalid_schedule"
    assert asp_domain.classify(inst, "n(1..300000000).", 1)["outcome"] == "solver_timeout"


# ---------------------------------------------------------------- parsers and prompts

@pytest.mark.parametrize("text,expected", [
    ("```clingo\nstart(1,0).\n```", "start(1,0)."),
    ("```prolog\nstart(1,0).\n```", "start(1,0)."),
    ("```asp\nx.\n```\nthen\n```clingo\ny.\n```", "y."),
    ("no code here", None),
])
def test_extract_code(text, expected):
    got = parsers.extract_code(text, "clingo")
    assert (got.strip() if got else None) == expected


def test_arms_differ_only_in_feedback(small_instances):
    inst = small_instances[0]
    for prev in ({"outcome": "invalid_schedule", "violations": ["overlap:A:1:2"],
                  "solver_output": "SATISFIABLE\nAnswer: start(1,0)"},
                 {"outcome": "unsat", "violations": [], "solver_output": "UNSATISFIABLE"}):
        b = prompts_A.blocks(inst, "binary", prev, "x.")
        d = prompts_A.blocks(inst, "diagnostic", prev, "x.")
        assert prompts_A.branch_identity(b, d) and b["feedback"] != d["feedback"]
        assert "Clingo output" not in b["feedback"] and "Clingo output" in d["feedback"]
        assert b["problem"] == asp_domain.attempt1_prompt(inst)


def test_preconditions_get_identical_feedback(small_instances):
    inst = small_instances[0]
    for prev in ({"outcome": "syntax_error", "violations": [], "solver_output": "parse error"},
                 {"outcome": "unparsable", "violations": [], "solver_output": ""}):
        assert (prompts_A.blocks(inst, "binary", prev, None)
                == prompts_A.blocks(inst, "diagnostic", prev, None))


# ---------------------------------------------------------------- runner

class Scripted(FakeBackend):
    """The fake model, plus scripted interruptions on given call numbers."""

    def __init__(self, limit_at=(), api_error_at=(), structural_at=()):
        super().__init__()
        self.n, self.limit_at, self.api_error_at, self.structural_at = 0, set(limit_at), set(api_error_at), set(structural_at)

    def call(self, prompt, timeout_s):
        self.n += 1
        if self.n in self.limit_at:
            from harness.cli_backend import UsageLimit
            raise UsageLimit("You've hit your usage limit")
        if self.n in self.api_error_at:
            return {"outcome_hint": "api_error", "text": "", "structural_violations": [], "stderr": "boom"}
        res = super().call(prompt, timeout_s)
        if self.n in self.structural_at:
            res["structural_violations"] = ["tools listed: ['Bash']"]
        return res


def _instances(n=12):
    out = []
    for i in range(n):
        inst = asp_domain.generate(*SMALL, seed=5000 + 1000 * i)
        inst["id"] = f"t{i:02d}"
        out.append(inst)
    return out


def _drive(tmp_path, backend, insts, target, budget=1000):
    run = runner_A.Run(tmp_path / "res", tmp_path / "inst", backend)
    return runner_A.run_feedback_module(run, tmp_path / "res" / "results.jsonl", "M1", insts,
                                        budget, timeout_s=60, target=target)


def _answered_keys(path):
    rows = [json.loads(l) for l in open(path)]
    keys = [(r["instance_id"], r["arm"], r["loop_attempt"]) for r in rows if r["outcome"] != "api_error"]
    return rows, keys


def test_usage_limit_ends_the_batch_without_a_row_and_resume_completes(tmp_path):
    insts = _instances()
    with pytest.raises(runner_A.Stop, match="usage limit"):
        _drive(tmp_path, Scripted(limit_at={7}), insts, target=3)
    rows, _ = _answered_keys(tmp_path / "res" / "results.jsonl")
    assert len(rows) == 6                                  # the blocked call left no row
    msg = _drive(tmp_path, Scripted(), insts, target=3)
    assert "target of 3" in msg
    rows, keys = _answered_keys(tmp_path / "res" / "results.jsonl")
    assert len(keys) == len(set(keys))                     # nothing answered twice


def test_small_batches_interrupt_mid_instance_and_resume_exactly(tmp_path):
    insts = _instances()
    for _ in range(40):
        try:
            _drive(tmp_path, Scripted(), insts, target=3, budget=2)
            break
        except runner_A.Stop as s:
            assert "batch budget" in str(s)
    rows, keys = _answered_keys(tmp_path / "res" / "results.jsonl")
    assert len(keys) == len(set(keys))
    ref = tmp_path / "ref"
    ref.mkdir()
    _drive(ref, Scripted(), insts, target=3)
    ref_rows, ref_keys = _answered_keys(ref / "res" / "results.jsonl")
    assert sorted(keys) == sorted(ref_keys)                # same calls as an uninterrupted run
    outcome = {(r["instance_id"], r["arm"], r["loop_attempt"]): r["outcome"] for r in rows}
    assert outcome == {(r["instance_id"], r["arm"], r["loop_attempt"]): r["outcome"] for r in ref_rows}


def test_api_error_is_retried_as_a_new_try(tmp_path):
    insts = _instances()
    _drive(tmp_path, Scripted(api_error_at={1}), insts, target=1)
    rows = [json.loads(l) for l in open(tmp_path / "res" / "results.jsonl")]
    first = [r for r in rows if r["instance_id"] == "t00" and r["loop_attempt"] == 1]
    assert [(r["api_try"], r["outcome"] == "api_error") for r in first] == [(0, True), (1, False)]


def test_structural_violation_aborts_and_blocks_the_next_run(tmp_path):
    insts = _instances()
    with pytest.raises(runner_A.Stop, match="structural"):
        _drive(tmp_path, Scripted(structural_at={2}), insts, target=3)
    assert (tmp_path / "res" / "STRUCTURAL_ABORT.md").exists()
    with pytest.raises(runner_A.Stop, match="STRUCTURAL_ABORT"):
        _drive(tmp_path, Scripted(), insts, target=3)


def test_branch_identity_failure_aborts(tmp_path, monkeypatch):
    insts = _instances()
    real = prompts_A.blocks

    def skewed(inst, arm, prev, artifact):
        b = real(inst, arm, prev, artifact)
        if arm == "diagnostic":
            b["instruction"] += " "
        return b
    monkeypatch.setattr(prompts_A, "blocks", skewed)
    with pytest.raises(runner_A.Stop, match="branch identity"):
        _drive(tmp_path, Scripted(), insts, target=3)


def test_backend_version_change_aborts(tmp_path):
    insts = _instances()
    _drive(tmp_path, Scripted(), insts, target=1)
    other = Scripted()
    other.version = "fake-2"
    with pytest.raises(runner_A.Stop, match="version changed"):
        _drive(tmp_path, other, insts, target=1)


def test_usage_limit_messages_are_recognised():
    from harness.cli_backend import USAGE_LIMIT
    for msg in ("You've hit your monthly spend limit · raise it at claude.ai/settings/usage"
                " · your session limit resets 6:20am (Europe/Zagreb)",
                "You've hit your usage limit", "Claude usage limit reached. Your limit will reset at 5pm"):
        assert USAGE_LIMIT.search(msg), msg
    assert not USAGE_LIMIT.search("```clingo\nstart(1,0).\n```")
