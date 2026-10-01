"""The frozen config and the committed analysis must not drift apart.

Kept apart from test_preflight.py so that it runs before the harness exists: it needs only the
config and the analysis script.

    pytest -q tests/test_decision_rules.py
"""

import importlib.util

import yaml


def test_decision_rules_match_the_analysis_script():
    cfg = yaml.safe_load(open("config/experiment_B.frozen.yaml"))
    spec = importlib.util.spec_from_file_location("an", "analysis/analyze_experiment_B.py")
    an = importlib.util.module_from_spec(spec); spec.loader.exec_module(an)
    a = cfg["analysis"]
    assert a["alpha"] == an.ALPHA
    assert a["mei_pp"] == an.MEI_PP
    assert a["mei_grade"] == an.MEI_GRADE
    assert a["lambda_threshold"] == an.LAMBDA_THRESHOLD
    assert a["tost_margin"] == an.TOST_MARGIN
    assert a["bootstrap"]["reps"] == an.BOOTSTRAP_REPS
    assert a["bootstrap"]["seed"] == an.BOOTSTRAP_SEED
    assert cfg["probes"]["per_instance"]["U"] == an.U_PROBES_PER_CELL
    assert cfg["probes"]["u_probe_min_issued"] == an.U_PROBE_MIN_ISSUED


def test_recorded_sha256_matches_the_analysis_script():
    import hashlib
    cfg = yaml.safe_load(open("config/experiment_B.frozen.yaml"))
    digest = hashlib.sha256(open("analysis/analyze_experiment_B.py", "rb").read()).hexdigest()
    assert cfg["analysis"]["sha256"] == digest, "the analysis script changed after the freeze"
