# Orchestration brief — Experiment B (context strip)

You are the orchestrator. You build the harness, delegate the runs to isolated sub-sessions, run
the committed analysis, and produce a report. Nobody reviews your work in between, so the checks
are executable rather than editorial.

Companion files, all authoritative:

| file | role |
|---|---|
| `experiment-B-context-strip.md` | the experiment: design, procedure, exact prompts, measures, hypotheses |
| `experiment_B.frozen.yaml` | every parameter and rule, frozen |
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
4. **No aliases.** Every call records a pinned dated snapshot id.
5. **API only.** No coding-agent CLI, no tools, no agent system prompt, no project files in the
   model's context. The models under test see exactly the message list the harness builds.
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
harness/
  models.py        call_model(messages, model_cfg) -> CallResult
  parsers.py       extract_path, extract_schedule, extract_code
  strip.py         build_context(cell, instance, phase1_record, paraphrase=None)
                   affordance_line(cell); paraphrase_is_clean(text)
  schema.py        REQUIRED_FIELDS, OUTCOMES, validate_row, is_pinned_snapshot
  domains/maze.py  generate_instances, validate, canonical_state, reference_solver,
  domains/asp.py   corrupt, fake_phase1_record, probe_C, probe_A, probe_U
runner.py
analysis/analyze_experiment_B.py
tests/test_preflight.py
instances/         maze.json, asp.json, INSTANCES.sha256
results/           results.jsonl, grades.jsonl, calibration.jsonl, tables.md, summary.json
```

Reuse the generators and validators already in the `operability` repository rather than writing
new ones; wrap them to the interface above. Their known defects (the schedule parser, the
stateless retries) are fixed here, not preserved.

### Result row schema (one row per API call)

`run_id, config_hash, timestamp, domain, instance_id, cell, phase, attempt, model_id, thinking,
temperature, max_output_tokens, messages_sha256, raw_response, stop_reason, input_tokens,
output_tokens, latency_ms, cost_usd, parsed_answer, outcome, validator_error, ground_truth,
correct, contradicts_artifact, artifact_retention, notes`

`phase` ∈ {`p1`, `paraphrase`, `p2_perturbation`, `probe_C`, `probe_A`, `probe_U`}.
`outcome` ∈ {`valid`, `invalid`, `unparsable`, `abstained`, `refused`, `api_error`, `timeout`,
`max_tokens`} — disjoint, no catch-all. Full message lists are written to
`results/messages/<sha256>.json`, so the strip is auditable after the fact.

## 3. Phases

**P0 — build.** Implement the harness to the interface above. `pytest -q tests/test_preflight.py`
must pass except the pilot-gated tests, which skip. Record the sha256 of the analysis script into
the frozen config's `analysis.sha256` field (this is the one write to that file, and it happens
before any model call).

**P1 — instances and calibration.** Generate instances once with the frozen seed; write
`INSTANCES.sha256`. Run the calibration rule exactly as written in the config, log every point to
`calibration.jsonl`, freeze the chosen difficulty. If no grid point meets the band, record it and
continue with the closest point.

**P2 — pilot.** 10 instances per domain, all five cells, full pipeline including probes and
grading. Compute `config/gates.pilot.json`, then run the pilot-gated tests. Compute the
paraphrase word budget from the rule and write it into the config as `paraphrase.budget_words`.

- all gates pass → continue to P3;
- any gate fails → **stop**, write `PILOT_BLOCKED.md` with the failing metric, the evidence, and
  what you would change, and do nothing else. Do not change a parameter and re-run.

**P3 — full run.** 70 instances per domain. Verify the analysis script hash and the instance
hashes before the first call. Respect the budget caps; on exceeding them, stop and report.

**P4 — grading.** A-probe answers go to a separate grading session, blind to cell, with shuffled
ids. Re-join grades to cells only in the analysis step.

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
- a pilot gate failing, including the control probes not being flat across cells;
- the resolved model id being an alias, or differing between cells within a run;
- the analysis script hash or the instance hashes not matching what was recorded;
- budget or wall-clock caps exceeded;
- more than 5% of calls in any cell ending in `api_error`, `timeout` or `unparsable`.

## 6. Deliverables

`REPORT.md`, `results/tables.md`, `results/summary.json`, `results/gates.json`,
`results/calibration.jsonl`, `results/results.jsonl`, `results/messages/`, and the repository
state (tests passing, hashes recorded). The frozen config as committed, with only the two fields
the rules fill in: `model.pinned_snapshot` and `paraphrase.budget_words`.

## 7. Out of scope

Experiment A (the condition ablation) has its own spec, which does not exist yet; do not
improvise it. The response letter, the manuscript and the corrections to the previously published
record are handled in separate sessions and must not be mixed into this one.
