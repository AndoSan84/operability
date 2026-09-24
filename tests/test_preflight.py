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
harness.probes       : applies_to(kind) -> set of cells
harness.contamination: PATTERNS, scan(text) -> list of matched patterns
harness.strip        : also render_inline(messages) -> str, the single user message the CLI gets
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
                  "input_tokens", "output_tokens", "messages_sha256", "medium", "probe_id",
                  "backend", "backend_version", "contaminated", "contamination_matches"):
        assert field in schema.REQUIRED_FIELDS


def test_model_id_is_a_pinned_snapshot():
    for alias in ("sonnet", "opus", "haiku", "latest", "gpt-5", "gemini-flash",
                  "claude-3-5-sonnet-latest", "default"):
        assert not schema.is_pinned_snapshot(alias), f"{alias} is an alias, not a snapshot"
    assert schema.is_pinned_snapshot("claude-sonnet-4-5-20250929")
    # the vendor's current ids carry no date: a full id is pinned, a family alias is not (C8)
    assert schema.is_pinned_snapshot("claude-sonnet-5")


# ---------------------------------------------------------------- CLI backend (C8)

CONTAMINATED = [
    "I don't have access to a code execution environment.",
    "Let me run this with the Bash tool.",
    "<function_calls>",
    "I cannot execute the program here.",
    "I'll run it now.",
    "It depends on the working directory.",
]
CLEAN = [
    "FINAL PATH: [(0,0), (0,1)]",
    "```python\nprint(\"FINAL PATH: []\")\n```",
    "SCHEDULE: {1: 0}",
    "Job 3 must run after job 2 finishes.",
    "The program reads the grid and runs a BFS.",
    "CANNOT DETERMINE.",
    "Collected keys are stored as a frozenset; the path is rebuilt from a parent map.",
]


def test_contamination_patterns_are_the_frozen_ones():
    import yaml
    from harness import contamination
    cfg = yaml.safe_load(open("config/experiment_B.frozen.yaml"))["contamination"]
    assert list(contamination.PATTERNS) == cfg["patterns_case_insensitive"]


@pytest.mark.parametrize("text", CONTAMINATED)
def test_contamination_flags_tool_file_execution_talk(text):
    from harness import contamination
    assert contamination.scan(text)


@pytest.mark.parametrize("text", CLEAN)
def test_contamination_leaves_task_answers_alone(text):
    from harness import contamination
    assert not contamination.scan(text)


@pytest.mark.parametrize("name", list(DOMAINS))
def test_inline_rendering_is_verbatim_ordered_and_cell_blind(name):
    """The CLI cannot carry a harness-built assistant turn (C8), so the message list is rendered
    into one user message. Every turn must survive byte-exact and in order, and the rendering
    must not depend on the cell."""
    mod = DOMAINS[name]
    inst = mod.generate_instances(seed=SEED, n=1, params="pilot")[0]
    record = mod.fake_phase1_record(inst, mod.reference_solver(inst))
    for cell in CELLS:
        messages = strip.build_context(cell, inst, record, paraphrase="A prose description.")
        messages = messages + [{"role": "user", "content": "PHASE-2 PROMPT"}]
        rendered = strip.render_inline(messages)
        assert rendered == strip.render_inline(messages)
        pos = [rendered.index(m["content"]) for m in messages]
        assert pos == sorted(pos)


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
    for domain, acc in GATES["c_probe_accuracy"].items():
        assert max(acc.values()) - min(acc.values()) <= 0.20, (
            f"{domain}: control probes differ across cells: the media are not matched and the "
            f"design is confounded. Stop and report; do not tune.")


@pytest.mark.skipif(GATES is None, reason="run after the pilot")
def test_pilot_control_probes_above_floor():
    """Flatness passes on uniformly broken data; a floor does not.

    C-probes are answerable from the canonical solution alone and balanced by construction, so
    chance is 0.50. Pooled accuracy below 0.70 in a domain means either the canonical state never
    reached the context or the pipeline is broken; in neither case is the full run meaningful.
    """
    for domain, (k, n) in GATES["c_probe_pooled"].items():
        assert n > 0 and k / n >= 0.70, (
            f"{domain}: pooled C-probe accuracy {k}/{n} is below the 0.70 floor")


@pytest.mark.skipif(GATES is None, reason="run after the pilot")
def test_pilot_paraphrases_contain_no_code():
    for domain, value in GATES["paraphrase_contains_code"].items():
        assert value == 0.0, f"{domain}: {value:.0%} of paraphrases contain code"


@pytest.mark.skipif(GATES is None, reason="run after the pilot")
def test_pilot_inclusion_rate():
    """Instance supply is elastic (n_target_included), so this only catches a real collapse:
    it fails iff the 95% Wilson UPPER bound of the inclusion rate is below 0.60."""
    for domain, g in GATES["inclusion"].items():
        k, n = g["included"], g["attempted"]
        z = 1.96
        p = k / n
        centre = (p + z * z / (2 * n)) / (1 + z * z / n)
        half = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / (1 + z * z / n)
        upper = min(1.0, centre + half)
        assert upper >= 0.60, (
            f"{domain}: {k}/{n} instances valid in both media (Wilson upper {upper:.2f}); "
            f"the paired design would collapse")


@pytest.mark.skipif(GATES is None, reason="run after the pilot")
def test_pilot_matches_calibration():
    """A pilot that does not behave like its own calibration means something changed.

    Deliberately underpowered: 8 calibration vs 10 pilot instances cannot detect a modest shift
    in difficulty, and is not meant to. This is a smoke detector for a changed pipeline (a
    different model, a broken prompt), not a test of difficulty. Fisher exact, two-sided,
    fails only at p < 0.01, per domain and medium.
    """
    from scipy.stats import fisher_exact
    for key, (pil_k, pil_n) in GATES["phase1_counts"].items():
        cal_k, cal_n = GATES["calibration_counts"][key]
        _, p = fisher_exact([[cal_k, cal_n - cal_k], [pil_k, pil_n - pil_k]])
        assert p >= 0.01, (
            f"{key}: pilot phase-1 success {pil_k}/{pil_n} vs calibrated {cal_k}/{cal_n}, "
            f"Fisher p={p:.4f}")


def test_a_probes_are_formal_only():
    from harness import probes
    assert probes.applies_to("A") == {"form_full", "form_strip_verbatim", "form_strip_para"}
    assert probes.applies_to("C") == set(CELLS)
    assert probes.applies_to("U") == set(CELLS)
