"""Edge cases of the Experiment A analysis, end to end on synthetic results files.

The batch design makes interruptions routine: the subscription blocks mid-instance, a call fails
and is retried, an arm is left pending until the next session. Each scenario checks the numbers,
not only that the script does not crash.

    pytest -q tests/test_analysis_edge_cases_A.py
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path("analysis/analyze_experiment_A.py")


def _load():
    spec = importlib.util.spec_from_file_location("an_a", SCRIPT)
    an = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(an)
    return an


def R(inst, arm, att, outcome, api_try=0, module="M1", domain="asp", **kw):
    return dict(module=module, domain=domain, instance_id=inst, arm=arm, loop_attempt=att,
                api_try=api_try, outcome=outcome, **kw)


def finished_pair(inst, first="invalid_schedule", binary_at=3, diagnostic_at=2):
    """Attempt 1 fails; each arm repairs at the given attempt (4 = never)."""
    rows = [R(inst, "shared", 1, first, violations=["overlap:A:1:2"])]
    for arm, at in (("binary", binary_at), ("diagnostic", diagnostic_at)):
        for att in (2, 3):
            if att < at:
                rows.append(R(inst, arm, att, "invalid_schedule", violations=["overlap:A:1:2"]))
            elif att == at:
                rows.append(R(inst, arm, att, "valid"))
                break
    return rows


def _run(tmp_path, rows):
    res = tmp_path / "results.jsonl"
    res.write_text("\n".join(json.dumps(r) for r in rows))
    out = tmp_path / "out"
    proc = subprocess.run([sys.executable, str(SCRIPT), "--results", str(res), "--out", str(out)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads((out / "summary.json").read_text())


def test_clear_effect_is_supported(tmp_path):
    rows = [r for i in range(30) for r in finished_pair(i, binary_at=4, diagnostic_at=2)]
    m1 = _run(tmp_path, rows)["M1"]
    assert m1["primary"]["n"] == 30 and m1["target_reached"]
    assert m1["primary"]["hodges_lehmann"] == 2.0
    assert m1["primary"]["supported"] is True


def test_no_difference_is_not_supported(tmp_path):
    rows = [r for i in range(30) for r in finished_pair(i, binary_at=2, diagnostic_at=2)]
    m1 = _run(tmp_path, rows)["M1"]
    assert m1["primary"]["p_one_sided"] == 1.0 and m1["primary"]["supported"] is False


def test_retry_keeps_the_answer_whatever_the_file_order(tmp_path):
    base = finished_pair(0, binary_at=2, diagnostic_at=2)
    failed = R(0, "diagnostic", 2, "api_error", api_try=0)
    answer = R(0, "diagnostic", 2, "valid", api_try=1)
    for order in ([failed, answer], [answer, failed]):
        rows = [r for r in base if not (r["arm"] == "diagnostic")] + order
        m1 = _run(tmp_path, rows)["M1"]
        assert m1["n_branched_complete"] == 1
        assert m1["primary"]["n"] == 1 and m1["primary"]["mean_difference"] == 0


def test_arm_pending_after_an_interrupted_batch_is_not_censored(tmp_path):
    rows = [R(0, "shared", 1, "invalid_schedule"), R(0, "binary", 2, "invalid_schedule"),
            R(0, "diagnostic", 2, "valid")]                  # binary attempt 3 not issued yet
    m1 = _run(tmp_path, rows)["M1"]
    assert m1["n_branched"] == 1
    assert m1["n_branched_complete"] == 0 and m1["n_branched_incomplete"] == 1
    assert m1["primary"]["verdict"].startswith("untestable")


def test_infrastructure_failure_is_not_a_model_failure(tmp_path):
    rows = [R(0, "shared", 1, "unsat"), R(0, "binary", 2, "valid"),
            R(0, "diagnostic", 2, "api_error", 0), R(0, "diagnostic", 2, "api_error", 1),
            R(1, "shared", 1, "api_error")]
    m1 = _run(tmp_path, rows)["M1"]
    assert m1["n_branched_complete"] == 0 and m1["n_branched_incomplete"] == 1
    assert m1["attempt1"]["n"] == 1 and m1["attempt1"]["infrastructure_excluded"] == 1


def test_only_semantic_failures_branch_and_unsat_leaves_the_sensitivity_set(tmp_path):
    rows = (finished_pair(0, first="invalid_schedule") + finished_pair(1, first="unsat")
            + [R(2, "shared", 1, "syntax_error"), R(3, "shared", 1, "valid")])
    m1 = _run(tmp_path, rows)["M1"]
    assert m1["n_branched"] == 2 and m1["attempt1"]["unsat_among_eligible"] == 1
    assert m1["attempt1"]["syntactic_failure"]["k"] == 1
    assert m1["attempt1"]["single_shot_success"]["k"] == 1
    assert m1["primary"]["n"] == 2
    assert m1["sensitivity_invalid_schedule_only"]["n"] == 1


def test_zero_branched_instances_is_untestable_not_a_crash(tmp_path):
    rows = [R(i, "shared", 1, "valid") for i in range(5)]
    summary = _run(tmp_path, rows)
    assert summary["M1"]["primary"]["verdict"].startswith("untestable")
    assert summary["M4"]["primary"]["verdict"].startswith("untestable")


def test_m4_is_descriptive(tmp_path):
    rows = [dict(r, module="M4") for i in range(6) for r in finished_pair(i, binary_at=4)]
    m4 = _run(tmp_path, rows)["M4"]
    assert m4["primary"]["n"] == 6 and "supported" not in m4["primary"]


def test_m3_skips_pending_asp_loops_and_counts_unlooped_failures(tmp_path):
    rows = (finished_pair(0)                                           # ASP repaired at 2
            + [R(1, "shared", 1, "invalid_schedule"), R(1, "diagnostic", 2, "invalid_schedule")]
            + [R(2, "shared", 1, "syntax_error")]                      # no ASP loop at all
            + [R(i, "nl_loop", 1, "valid", module="M3") for i in range(3)])
    m3 = _run(tmp_path, rows)["M3"]
    assert m3["n_paired"] == 2                                         # instance 1 still pending
    assert m3["asp_attempt1_not_branched_counted_as_failure"] == 1


def test_uptake_and_regression_per_arm():
    an = _load()
    rows = [R(0, "shared", 1, "invalid_schedule", violations=["a", "b"]),
            R(0, "binary", 2, "invalid_schedule", violations=["b"]),          # a repaired
            R(0, "binary", 3, "invalid_schedule", violations=["a"]),          # a is back
            R(0, "diagnostic", 2, "valid")]
    res = an.feedback_contrast(an.dedupe(rows), "M1", "asp", 30, True)
    assert (res["uptake"]["binary"]["k"], res["uptake"]["binary"]["n"]) == (2, 2)
    assert (res["regression"]["binary"]["k"], res["regression"]["binary"]["n"]) == (1, 1)
    assert res["uptake"]["diagnostic"]["n"] == 1 and res["regression"]["diagnostic"]["n"] == 0


def test_contamination_is_reported_per_arm():
    an = _load()
    rows = finished_pair(0, binary_at=3)
    rows[1]["contaminated"] = True                                    # binary attempt 2
    res = an.feedback_contrast(an.dedupe(rows), "M1", "asp", 30, True)
    assert res["contamination"]["binary"]["k"] == 1
    assert res["contamination"]["diagnostic"]["k"] == 0
