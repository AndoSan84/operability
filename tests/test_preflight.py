"""Preflight and gate assertions for Experiment B.

These tests are written before the harness exists: they define the contract the harness must
satisfy. Until the modules below are implemented they fail at import, which is the intended
starting state.

They are not style checks. Every one of them corresponds to a defect that actually occurred in
the previous round of experiments, or to a way the manipulation can silently fail. The
orchestrator MUST NOT relax a threshold, edit a fixture, or skip a test to get a green run: a
failing gate is a stop, not a task.

    pytest -q tests/test_preflight.py

Contract expected from the harness
----------------------------------
harness.parsers      : extract_path(text), extract_schedule(text), extract_code(text, lang)
harness.domains.maze : generate_instances(seed, n, params), validate(instance, solution),
                       canonical_state(instance, solution), reference_solver(instance),
                       probe_C(instance, solution, rng), probe_A(instance), probe_U(instance, solution, rng)
harness.domains.asp  : same interface
harness.strip        : build_context(cell, instance, phase1_record, paraphrase=None) -> list[dict]
harness.schema       : REQUIRED_FIELDS, OUTCOMES, validate_row(row)
"""

import json
import re
from pathlib import Path

import pytest

from harness import parsers, schema, strip
from harness.domains import asp, maze

DOMAINS = {"maze": maze, "asp": asp}
CELLS = ["nl_full", "nl_strip", "form_full", "form_strip_verbatim", "form_strip_para"]
SEED = 20260924


# ---------------------------------------------------------------- parsers

SCHEDULE_FIXTURES = [
    # (text, expected) — the first case is the defect that corrupted Table 5 of the submission
    ("Reasoning about the schedule.\n\n**SCHEDULE:** {1: 0, 2: 1, 3: 4}", {1: 0, 2: 1, 3: 4}),
    ("SCHEDULE: {1: 0, 2: 1}", {1: 0, 2: 1}),
    ("`SCHEDULE: {1: 0}`", {1: 0}),
    # a draft followed by a final answer: the last one is the answer
    ("SCHEDULE: {1: 9}\nOn reflection that violates a precedence.\nSCHEDULE: {1: 3}", {1: 3}),
    # prose that mentions jobs and times must not be mined for an answer
    ("Job 3 starts at 4 and job 5 at 7, but I cannot produce a full schedule.", None),
    ("", None),
]

PATH_FIXTURES = [
    ("**FINAL PATH:** [(0,0), (0,1)]", [(0, 0), (0, 1)]),
    ("FINAL PATH: [(0,0), (1,0), (2,0)]", [(0, 0), (1, 0), (2, 0)]),
    ("FINAL PATH: [(0,0)]\nActually that is wrong.\nFINAL PATH: [(0,0), (0,1)]", [(0, 0), (0, 1)]),
    ("The format should be FINAL PATH: [(r,c), (r,c), ...] but I cannot solve it.", None),
    ("", None),
]

CODE_FIXTURES = [
    ("```python\nprint(1)\n```", "python", "print(1)"),
    ("```clingo\nstart(1,0).\n```", "clingo", "start(1,0)."),
    # models label ASP as prolog; the parser must accept the alias
    ("```prolog\nstart(1,0).\n```", "clingo", "start(1,0)."),
    ("no code here", "python", None),
]


@pytest.mark.parametrize("text,expected", SCHEDULE_FIXTURES)
def test_extract_schedule(text, expected):
    assert parsers.extract_schedule(text) == expected


@pytest.mark.parametrize("text,expected", PATH_FIXTURES)
def test_extract_path(text, expected):
    assert parsers.extract_path(text) == expected


@pytest.mark.parametrize("text,lang,expected", CODE_FIXTURES)
def test_extract_code(text, lang, expected):
    got = parsers.extract_code(text, lang)
    assert (got.strip() if got else None) == expected


def test_parse_failure_is_not_an_answer():
    """An unparsable reply must be distinguishable from a wrong answer downstream."""
    assert parsers.extract_schedule("I give up.") is None
    assert parsers.extract_path("I give up.") is None


# ---------------------------------------------------------------- validators

@pytest.mark.parametrize("name", list(DOMAINS))
def test_validator_agrees_with_reference(name):
    """Differential test: the validator and an independent reference must never disagree."""
    mod = DOMAINS[name]
    instances = mod.generate_instances(seed=SEED, n=30, params="pilot")
    for inst in instances:
        ref = mod.reference_solver(inst)
        assert mod.validate(inst, ref).valid, f"{name}: reference solution rejected by validator"
        for broken in mod.corrupt(ref, seed=SEED):
            assert not mod.validate(inst, broken).valid, f"{name}: corrupted solution accepted"


@pytest.mark.parametrize("name", list(DOMAINS))
def test_instances_are_frozen(name):
    """The instance set is generated once and hashed; regeneration must be bit-identical."""
    digest = Path("instances/INSTANCES.sha256").read_text().strip().splitlines()
    recorded = dict(line.split()[::-1] for line in digest)
    on_disk = Path(f"instances/{name}.json").read_bytes()
    import hashlib
    assert hashlib.sha256(on_disk).hexdigest() == recorded[f"instances/{name}.json"]


# ---------------------------------------------------------------- canonical state

@pytest.mark.parametrize("name", list(DOMAINS))
def test_canonical_state_is_complete_and_bare(name):
    """The 'perfect summary' must be a valid solution and must contain no derivation."""
    mod = DOMAINS[name]
    for inst in mod.generate_instances(seed=SEED, n=20, params="pilot"):
        sol = mod.reference_solver(inst)
        text = mod.canonical_state(inst, sol)
        # complete: it parses back to exactly the solution and revalidates
        reparsed = (parsers.extract_path(text) if name == "maze" else parsers.extract_schedule(text))
        assert reparsed == sol
        assert mod.validate(inst, reparsed).valid
        # bare: a single answer line, no prose, no code
        assert len(text.strip().splitlines()) == 1
        assert "```" not in text
        assert not re.search(r"\b(because|since|first|then|therefore)\b", text, re.I)


# ---------------------------------------------------------------- the manipulation itself

@pytest.mark.parametrize("name", list(DOMAINS))
def test_context_builder_has_no_leakage(name):
    """The strip is the experiment. Each cell's assistant turn must match its template exactly."""
    mod = DOMAINS[name]
    inst = mod.generate_instances(seed=SEED, n=1, params="pilot")[0]
    sol = mod.reference_solver(inst)
    record = mod.fake_phase1_record(inst, sol)   # prose reasoning + artifact + execution output
    canonical = mod.canonical_state(inst, sol)
    para = "A description of the method in prose, without code."

    ctx = {c: strip.build_context(c, inst, record, paraphrase=para) for c in CELLS}
    for cell, messages in ctx.items():
        assert [m["role"] for m in messages] == ["user", "assistant"]
        assistant = messages[1]["content"]

        if cell == "nl_strip":
            assert assistant.strip() == canonical.strip()
        if cell == "form_strip_verbatim":
            assert record.artifact in assistant and canonical.strip() in assistant
            assert record.reasoning_prose not in assistant
        if cell == "form_strip_para":
            assert para in assistant and canonical.strip() in assistant
            assert record.artifact not in assistant and "```" not in assistant
            assert record.reasoning_prose not in assistant
        if cell.endswith("_full"):
            assert record.reasoning_prose in assistant

        # no cell may carry the derivation into a stripped context
        if "_strip" in cell:
            assert record.reasoning_prose not in assistant


def test_paraphrase_contains_no_code():
    bad = "The method is: ```python\nwhile queue:\n```"
    assert not strip.paraphrase_is_clean(bad)
    assert strip.paraphrase_is_clean("Breadth-first exploration, collecting keys on entry.")


def test_phase2_affordances_are_constant_within_medium():
    """All formal cells must receive the same phase-2 instruction; likewise both NL cells."""
    formal = {strip.affordance_line(c) for c in ["form_full", "form_strip_verbatim", "form_strip_para"]}
    nl = {strip.affordance_line(c) for c in ["nl_full", "nl_strip"]}
    assert len(formal) == 1 and len(nl) == 1 and formal != nl


# ---------------------------------------------------------------- result rows

def test_schema_rejects_an_empty_response_becoming_an_outcome():
    row = {f: "x" for f in schema.REQUIRED_FIELDS}
    row.update({"raw_response": "", "outcome": "invalid", "stop_reason": None})
    with pytest.raises(schema.SchemaError):
        schema.validate_row(row)


def test_outcomes_are_disjoint_and_complete():
    assert set(schema.OUTCOMES) == {
        "valid", "invalid", "unparsable", "abstained", "refused",
        "api_error", "timeout", "max_tokens",
    }


def test_every_row_records_the_resolved_model_and_cost():
    for field in ("model_id", "thinking", "temperature", "stop_reason",
                  "input_tokens", "output_tokens", "messages_sha256"):
        assert field in schema.REQUIRED_FIELDS


def test_model_id_is_a_pinned_snapshot():
    for alias in ("sonnet", "opus", "haiku", "latest", "gpt-5", "gemini-flash"):
        assert not schema.is_pinned_snapshot(alias), f"{alias} is an alias, not a snapshot"
    assert schema.is_pinned_snapshot("claude-sonnet-4-5-20250929")


# ---------------------------------------------------------------- pilot gates

GATES = json.loads(Path("config/gates.pilot.json").read_text()) if Path(
    "config/gates.pilot.json").exists() else None


@pytest.mark.skipif(GATES is None, reason="run after the pilot")
@pytest.mark.parametrize("metric,limit", [
    ("parse_failure_rate", 0.05), ("api_error_rate", 0.05), ("timeout_rate", 0.05),
])
def test_pilot_error_rates(metric, limit):
    for cell, value in GATES[metric].items():
        assert value <= limit, f"{cell}: {metric}={value:.2f} exceeds {limit}"


@pytest.mark.skipif(GATES is None, reason="run after the pilot")
def test_pilot_control_probes_are_flat():
    acc = GATES["c_probe_accuracy"]
    assert max(acc.values()) - min(acc.values()) <= 0.20, (
        "control probes differ across cells: the media are not matched and the design is "
        "confounded. Stop and report; do not tune.")


@pytest.mark.skipif(GATES is None, reason="run after the pilot")
def test_pilot_phase1_success_in_band():
    for medium, value in GATES["phase1_success"].items():
        assert 0.80 <= value <= 0.97, f"{medium}: phase-1 success {value:.2f} outside the band"
