# Orchestration brief — Experiment B (context strip)

You are the orchestrator. You build the harness, delegate the runs to isolated sub-sessions, run
the committed analysis, and produce a report. Nobody reviews your work in between, so the checks
are executable rather than editorial.

Companion files, all authoritative:

| file | role |
|---|---|
| `experiment-B-context-strip.md` | the experiment: design, procedure, exact prompts, measures, hypotheses |
| `config/experiment_B.frozen.yaml` | every parameter and rule, frozen |
| `AMENDMENTS-v1.md`, `AMENDMENTS-v2.md` | pre-run amendments, applied to the files above |
| `tests/test_preflight.py` | the contract and the gates, executable |
| `analysis/analyze_experiment_B.py` | the analysis, committed before the run |

## 0. Non-negotiables

1. **Do not edit the frozen config, the prompts, the hypotheses, the thresholds or the tests to
   make something pass.** A failing gate is a stop and a report, not a task to be resolved. If you
   believe a threshold is wrong, write it in the report and stop.
2. **Do not modify `analyze_experiment_B.py` after its hash is recorded.** If the analysis needs a
   change, that is a new config version and a new results file.
3. **Results are append-only.** One results file per config hash. A re-run is a new record, never
   an overwrite. Never delete rows, including failures.
4. **No aliases.** Every call records the full model id it resolved to, dated wherever the
   vendor dates it, and the run aborts if it is an alias or differs from the requested id.
5. **Hardened backend, declared.** The reported run uses the Claude CLI (`model.backend:
   claude_cli`), because API credit is not available. It runs hardened exactly as in
   `model.cli` of the frozen config: no tools, no MCP, permissions denying everything, the agent
   system prompt replaced, a fresh empty temporary working directory per call, no project files,
   memory or allow rules in reach. The structural checks run on every call and abort on the first
   violation. The model sees the harness-built message list rendered by `strip.render_inline`,
   and nothing else the harness controls. The `api` backend stays implemented for replication.
6. **You may not tune difficulty, paraphrase budget or inclusion rules by judgement.** They are
   computed by the rules in the frozen config and logged.

## 1. Isolation between sessions

Each sub-session receives only what it needs. The purpose is that no session that can influence a
number also knows which number we hope for.

| sub-session | receives | must not receive |
|---|---|---|
| implementer | spec §§2–5, frozen config, tests, repo | hypotheses (spec §6), reviews, response letter, briefing |
| runner | built harness, frozen config, instance files | hypotheses, any discussion of expected results |
| grader (A-probes) | pairs of (artifact, answer), shuffled, ids replaced | cell labels, hypotheses, instance provenance |
| analyst | results files, the committed analysis script | permission to modify the script |

You hold the hypotheses. You do not pass them down, and you do not make any decision that the
frozen config already determines. Where the spec and this brief disagree, the spec wins.

## 2. Repository layout and interfaces

```
vendor/operability/   read-only clone; generators and validators are wrapped, not edited
config/            experiment_B.frozen.yaml, gates.pilot.json
harness/
  models.py        call_model(messages, model_cfg) -> CallResult; backends claude_cli and api
  contamination.py PATTERNS (from the frozen config), scan(text)
  parsers.py       extract_path, extract_schedule, extract_code
  strip.py         build_context(cell, instance, phase1_record, paraphrase=None)
                   affordance_line(cell); paraphrase_is_clean(text)
  schema.py        REQUIRED_FIELDS, OUTCOMES, validate_row, is_pinned_snapshot
  probes.py        applies_to(kind), probe generation and ground truth
  domains/maze.py  generate_instances, validate, canonical_state, reference_solver,
  domains/asp.py   corrupt, fake_phase1_record, probe_C, probe_A, probe_U
runner.py
analysis/analyze_experiment_B.py
tests/test_preflight.py
instances/         maze.json, asp.json, INSTANCES.sha256
results/           results.jsonl, pilot.jsonl, grades.jsonl, calibration.jsonl, tables.md,
                   summary.json
```

`config/gates.pilot.json` — written at the end of P2; its keys are fixed by the tests that read
them. Counts are `[successes, trials]`; rates are in [0, 1].

```
inclusion                 {"<domain>": {"included": k, "attempted": n}}
phase1_counts             {"<domain>/<medium>": [k, n]}      pilot phase-1 validity
calibration_counts        {"<domain>/<medium>": [k, n]}      at the chosen grid point
c_probe_accuracy          {"<domain>": {"<cell>": rate}}     flatness is checked within domain
c_probe_pooled            {"<domain>": [k, n]}               all cells pooled; floor 0.70
parse_failure_rate        {"<domain>/<cell>": rate}
api_error_rate            {"<domain>/<cell>": rate}
timeout_rate              {"<domain>/<cell>": rate}
paraphrase_contains_code  {"<domain>": rate}
```

Reuse the generators and validators already in the `operability` repository rather than writing
new ones; wrap them to the interface above. Their known defects (the schedule parser, the
stateless retries) are fixed here, not preserved.

### Result row schema (one row per model call)

`run_id, config_hash, timestamp, backend, backend_version, domain, instance_id, medium, cell,
phase, probe_id, attempt, model_id, thinking,
temperature, max_output_tokens, messages_sha256, raw_response, stop_reason, input_tokens,
output_tokens, latency_ms, cost_usd, parsed_answer, outcome, validator_error, ground_truth,
correct, contradicts_artifact, artifact_retention, contaminated, contamination_matches,
rendered_prompt_sha256, notes`

`phase` ∈ {`p1`, `paraphrase`, `p2_perturbation`, `probe_C`, `probe_A`, `probe_U`}.
`medium` ∈ {`nl`, `formal`} is required on every row. Phase 1 runs once per medium per instance:
`p1` rows are keyed by `(domain, medium, instance_id)` and `cell` is null on them. `probe_id`
identifies the probe (template and draw) on `probe_*` rows, since there are three U-probes per
instance and cell; it is null on other rows.
`outcome` ∈ {`valid`, `invalid`, `unparsable`, `abstained`, `refused`, `api_error`, `timeout`,
`max_tokens`} — disjoint, no catch-all. Full message lists are written to
`results/messages/<sha256>.json`, so the strip is auditable after the fact.

## 3. Phases

**P0 — build.** Before anything else, re-run the CLI canary of C8 on the installed version and
store its transcript under `results/canary/`: it must show no tools, the replaced system prompt,
the requested model id, and what the CLI injects. If the version differs from the one the canary
of C8 was run on, record both. Implement the harness to the interface above. `pytest -q tests/test_preflight.py`
must pass except the pilot-gated tests, which skip. Verify that the sha256 of the analysis script equals
`analysis.sha256` in the frozen config, which was recorded at the pre-registration commit; a
mismatch is a stop.

**P1 — calibration, then instances.** Calibrate first, on instances drawn from
`calibration_seed`, logging every grid point to `calibration.jsonl`; if no grid point meets the
band, record it and continue with the closest point. Then generate the frozen instance list at the
chosen difficulty from `seed` and write `INSTANCES.sha256`. Calibration instances are discarded
and never appear in `results.jsonl` or `pilot.jsonl`.

**P2 — pilot.** The first 10 instances of the frozen list per domain, all five cells, full
pipeline including probes and grading. Pilot rows go to `results/pilot.jsonl`, never to
`results.jsonl`. Run phase 1 for all pilot instances first; compute the paraphrase word budget from
the pilot's phase-1 artifacts by the rule and write it into the config as
`paraphrase.budget_words` **before** any paraphrase call; then run the rest of the pilot. Compute
`config/gates.pilot.json`, then run the pilot-gated tests.

- all gates pass → continue to P3;
- any gate fails → **stop**, write `PILOT_BLOCKED.md` with the failing metric, the evidence, and
  what you would change, and do nothing else. Do not change a parameter and re-run.

**P3 — full run.** Starts at the first instance after the pilot's in the frozen list; pilot
instances are never re-used and do not count toward the target. Proceeds down the list until 70
instances per domain are included (valid phase 1 in both media), with a hard cap of 120 generated
instances including the pilot's; reaching the cap is a stop. Verify the analysis script hash and the instance
hashes before the first call. Respect the budget caps; on exceeding them, stop and report.

**P4 — grading.** A-probe answers go to a separate grading session, blind to cell, with shuffled
ids. Re-join grades to cells only in the analysis step.
A-probes exist only for the formal cells; if any item sent to the grader lacks a program, that is
a bug, not an item to judge.

**P5 — analysis and report.** Run the committed script unmodified. Write `REPORT.md` containing:
what was run, the resolved model id, the calibration outcome, the exclusion rate per cell, the
tables as produced, the gate verdicts, and every deviation from this brief. State results without
interpreting them for or against a hypothesis; the interpretation happens in the paper, not here.

## 4. Sub-session prompts

**Implementer**

```
Build the harness described in ORCHESTRATOR.md §2 and in the spec sections 2 to 5 of
experiment-B-context-strip.md, so that `pytest -q tests/test_preflight.py` passes (pilot-gated
tests will skip). Reuse the generators and validators in the operability repository, wrapped to
the stated interface. Do not modify tests/test_preflight.py, the frozen config, or any prompt
text. If a test cannot be satisfied without changing a prompt or a threshold, stop and report
which one and why.
```

**Runner**

```
Execute phase {P2|P3} exactly as specified in ORCHESTRATOR.md §3 using the frozen config. Do not
change any parameter. Append every call to results/results.jsonl, including failures, with the
full schema. If an assertion, a budget cap or a gate fails, stop immediately and write what
happened; do not retry with different settings.
```

**Grader**

```
You will receive pairs of (program, answer). For each pair, judge whether the answer correctly
describes what the program does, on this scale: 2 correct, 1 partially correct, 0 incorrect or
absent. Mark separately whether the answer is an explicit refusal to answer ("CANNOT DETERMINE").
Output one JSON object per line: {"item_id": ..., "grade": ..., "abstained": ...}. Judge only the
match between answer and program. Do not speculate about where the pairs come from.
```

**Analyst**

```
Run `python3 analysis/analyze_experiment_B.py --results results/results.jsonl
--grades results/grades.jsonl --out results/` without modifying the script, and report its output
verbatim. If the script errors, report the traceback; do not patch it.
```

## 5. What stops the run

- any preflight test failing;
- a pilot gate failing, including the control probes not being flat across cells or falling
  below the 0.70 floor;
- the resolved model id being an alias, differing from the requested id, or differing between
  cells within a run; the CLI version changing mid-run;
- any structural check of `model.cli.structural_checks` failing on any call;
- contamination above 2% in any cell of the pilot;
- the analysis script hash or the instance hashes not matching what was recorded;
- budget or wall-clock caps exceeded;
- more than 5% of calls in any cell ending in `api_error`, `timeout` or `unparsable`.

## 6. Deliverables

`REPORT.md`, `results/tables.md`, `results/summary.json`, `results/gates.json`,
`results/calibration.jsonl`, `results/pilot.jsonl`, `results/results.jsonl`, `results/messages/`, and the repository
state (tests passing, hashes recorded). The frozen config as committed, with only the four fields
the rules fill in: `model.pinned_snapshot`, `model.backend_version`, `paraphrase.budget_words` and
`retries.timeout_seconds`.

## 7. Out of scope

Experiment A (the condition ablation) has its own spec, which does not exist yet; do not
improvise it. The response letter, the manuscript and the corrections to the previously published
record are handled in separate sessions and must not be mixed into this one.
