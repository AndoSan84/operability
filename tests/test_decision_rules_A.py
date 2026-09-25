"""Experiment A: the frozen config and the committed analysis must not drift apart.

Needs only the config and the script, so it runs before the harness exists.

    pytest -q tests/test_decision_rules_A.py
"""

import hashlib
import importlib.util

import yaml

CFG = "config/experiment_A.frozen.yaml"
SCRIPT = "analysis/analyze_experiment_A.py"


def _script():
    spec = importlib.util.spec_from_file_location("an_a", SCRIPT)
    an = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(an)
    return an


def test_decision_rules_match_the_analysis_script():
    cfg = yaml.safe_load(open(CFG))
    a, an = cfg["analysis"], _script()
    assert a["alpha"] == an.ALPHA
    assert a["mei_hl"] == an.MEI_HL
    assert a["n_branched_target"] == an.N_BRANCHED_TARGET == cfg["instances"]["m1_target_branched"]
    assert a["m4_branched_target"] == an.M4_BRANCHED_TARGET == cfg["instances"]["m4_target_branched"]
    assert a["censored_value"] == an.CENSORED == cfg["branching"]["censored_value"]
    assert a["bootstrap"]["reps"] == an.BOOTSTRAP_REPS
    assert a["bootstrap"]["seed"] == an.BOOTSTRAP_SEED
    assert set(cfg["branching"]["eligible"]) == an.ELIGIBLE
    assert set(cfg["branching"]["infrastructure"]) == an.INFRA


def test_config_is_frozen_and_contamination_matches_experiment_B():
    a = yaml.safe_load(open(CFG))
    b = yaml.safe_load(open("config/experiment_B.frozen.yaml"))
    assert a["status"] == "frozen"
    assert (a["contamination"]["patterns_case_insensitive"]
            == b["contamination"]["patterns_case_insensitive"])


def test_recorded_sha256_matches_the_analysis_script():
    cfg = yaml.safe_load(open(CFG))
    digest = hashlib.sha256(open(SCRIPT, "rb").read()).hexdigest()
    assert cfg["analysis"]["sha256"] == digest, "the analysis script changed after the freeze"


def test_v2_differs_from_v1_only_where_declared():
    v1 = yaml.safe_load(open(CFG))
    v2 = yaml.safe_load(open("config/experiment_A_v2.frozen.yaml"))
    assert v2["config_version"] == 2 and v2["model"]["confirmatory"] == "claude-haiku-4-5-20251001"
    assert v2["analysis"] == v1["analysis"]            # same decision rules, same script sha256
    for key in ("branching", "feedback_blocks", "calibration", "contamination", "gates", "batches"):
        if key == "calibration":
            assert {k: v for k, v in v2[key].items() if k != "log"} == {k: v for k, v in v1[key].items() if k != "log"}
        else:
            assert v2[key] == v1[key], key
