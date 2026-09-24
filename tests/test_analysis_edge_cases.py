"""Edge cases of the committed analysis script.

The analysis is the one piece nobody re-reads after the freeze, so the failure modes found while
applying the amendments are pinned here. Each scenario runs the script end to end on a synthetic
results file and checks the numbers, not only that it does not crash. Needs only the script.

    pytest -q tests/test_analysis_edge_cases.py
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path("analysis/analyze_experiment_B.py")
CELLS = ["nl_full", "nl_strip", "form_full", "form_strip_verbatim", "form_strip_para"]
FORMAL = CELLS[2:]
N = 12


def _load():
    spec = importlib.util.spec_from_file_location("an", SCRIPT)
    an = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(an)
    return an


def _domain_rows(domain, *, p1_valid=True, u_probes=3, c_retry=None, contaminated_cell=None):
    """Every C-probe is correct and half the U-probes abstain, so the expected numbers are known.

    c_retry: None, "in_order" (api_error attempt 1, then the answer attempt 2) or "out_of_order"
    (the attempt-2 answer is written before the attempt-1 api_error).
    """
    rows = []
    for i in range(N):
        for m in ("nl", "formal"):
            rows.append(dict(domain=domain, instance_id=i, medium=m, cell=None, phase="p1",
                             attempt=1, outcome="valid" if p1_valid else "invalid"))
        for c in CELLS:
            med = "nl" if c.startswith("nl") else "formal"
            base = dict(domain=domain, instance_id=i, medium=med, cell=c)
            rows.append(dict(base, phase="p2_perturbation", attempt=1,
                             outcome="valid" if (i + CELLS.index(c)) % 2 else "invalid"))
            failed = dict(base, phase="probe_C", probe_id="C0", attempt=1,
                          outcome="api_error", correct=None)
            answer = dict(base, phase="probe_C", probe_id="C0",
                          attempt=1 if c_retry is None else 2, outcome="valid", correct=True)
            if c_retry == "in_order":
                rows += [failed, answer]
            elif c_retry == "out_of_order":
                rows += [answer, failed]
            else:
                rows.append(answer)
            for u in range(u_probes):
                rows.append(dict(base, phase="probe_U", probe_id=f"U{u}", attempt=1,
                                 outcome="abstained" if (i + u) % 2 else "valid",
                                 contradicts_artifact=False,
                                 contaminated=(c == contaminated_cell and u == 0)))
            if c in FORMAL:
                rows.append(dict(base, phase="probe_A", probe_id="A0", attempt=1,
                                 outcome="valid"))
    return rows


def _run(tmp_path, rows):
    res = tmp_path / "results.jsonl"
    res.write_text("\n".join(json.dumps(r) for r in rows))
    out = tmp_path / "out"
    proc = subprocess.run([sys.executable, str(SCRIPT), "--results", str(res), "--out", str(out)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    summary = {d["domain"]: d for d in json.loads((out / "summary.json").read_text())}
    gates = json.loads((out / "gates.json").read_text())
    return summary, gates


def test_retried_probe_keeps_the_answer_not_the_api_error(tmp_path):
    summary, _ = _run(tmp_path, _domain_rows("maze", c_retry="in_order"))
    for cell in CELLS:
        acc = summary["maze"]["cells"][cell]["c_probe_accuracy"]
        assert (acc["k"], acc["n"]) == (N, N), cell


def test_retry_dedup_follows_the_attempt_not_the_file_order(tmp_path):
    summary, _ = _run(tmp_path, _domain_rows("maze", c_retry="out_of_order"))
    for cell in CELLS:
        acc = summary["maze"]["cells"][cell]["c_probe_accuracy"]
        assert (acc["k"], acc["n"]) == (N, N), cell


def test_same_attempt_tie_is_broken_by_file_order():
    an = _load()
    first = dict(domain="maze", cell="nl_strip", instance_id=0, phase="probe_C",
                 probe_id="C0", attempt=1, outcome="api_error")
    second = dict(first, outcome="valid")
    _, probes = an.index_rows([first, second])
    assert probes[("maze", "nl_strip", 0, "probe_C")] == [second]


def test_three_u_probes_are_counted_per_instance(tmp_path):
    summary, _ = _run(tmp_path, _domain_rows("maze"))
    h4 = summary["maze"]["tests"]["h4_equivalence"]
    assert h4["n_instances"] == N
    # instance i abstains on probes u with (i + u) odd: 1 of 3 for even i, 2 of 3 for odd i
    assert abs(summary["maze"]["cells"]["nl_strip"]["u_probe_abstention"]["mean"] - 0.5) < 1e-9


def test_domain_without_issuable_u_probes_makes_h4_untestable(tmp_path):
    rows = _domain_rows("maze") + _domain_rows("asp", u_probes=0)
    summary, _ = _run(tmp_path, rows)
    assert summary["asp"]["tests"]["h4_equivalence"]["verdict"] == "untestable"
    assert summary["asp"]["tests"]["h4_equivalence"]["n_instances"] == 0
    assert summary["maze"]["tests"]["h4_equivalence"]["verdict"] != "untestable"


def test_u_probes_below_min_issued_exclude_the_instance_from_h4_only(tmp_path):
    an = _load()
    summary, _ = _run(tmp_path, _domain_rows("maze", u_probes=an.U_PROBE_MIN_ISSUED - 1))
    assert summary["maze"]["tests"]["h4_equivalence"]["verdict"] == "untestable"
    assert summary["maze"]["n_included"] == N          # the rest of the analysis is untouched
    assert len(summary["maze"]["tests"]["primary"]) == 3


def test_domain_with_no_included_instance_does_not_sink_the_other(tmp_path):
    rows = _domain_rows("maze") + _domain_rows("asp", p1_valid=False)
    summary, gates = _run(tmp_path, rows)
    assert summary["asp"]["status"] == "no included instances"
    assert summary["asp"]["n_included"] == 0
    assert summary["asp"]["coverage"]["any_medium"] == N
    assert gates["asp"] == {"status": "no included instances"}
    assert summary["maze"]["status"] == "analysed"
    assert summary["maze"]["n_included"] == N
    assert "c_probe_flatness_violated" in gates["maze"]


def test_contamination_is_a_per_cell_result_column(tmp_path):
    summary, _ = _run(tmp_path, _domain_rows("maze", contaminated_cell="form_strip_para"))
    cells = summary["maze"]["cells"]
    # per instance: 1 perturbation + 1 C + 3 U (+ 1 A in formal cells); one U-probe flagged
    para = cells["form_strip_para"]["contamination"]
    assert (para["k"], para["n"]) == (N, N * 6)
    for cell in ("nl_full", "nl_strip", "form_full", "form_strip_verbatim"):
        assert cells[cell]["contamination"]["k"] == 0, cell
    assert (tmp_path / "out" / "tables.md").read_text().count("| contamination |") == 1
