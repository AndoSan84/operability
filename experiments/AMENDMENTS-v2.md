# Amendments v2 to Experiment B, applied before the first run

Decisions on the five defects found in the implementation review, plus the minor points. Still no
model call has been made, so `config_version` stays at 1 and this file joins `AMENDMENTS-v1.md`
as the record of what was decided before execution.

`analysis/analyze_experiment_B.py` is **replaced again** (v2 supplied): it now computes inclusion
from medium-level phase-1 rows, fixes the λ sign condition, makes all three confirmatory tests
one-sided with a fixed family size, and lets the Holm-corrected p enter the decisions. The edits
below apply to the other files.

---

## B1 — Phase 1 runs once per medium, not once per cell

Accepted, and it is a design defect rather than a gate problem. With one phase-1 run per cell,
`nl_full` and `nl_strip` start from *different derivations*, so the strip is no longer the only
difference between them and the comparison is confounded with sampling variation in the solution
itself. The five cells are phase-2 treatments built on two phase-1 records per instance.

Consequences:

- `p1` rows are keyed by `(domain, medium, instance_id)`; `cell` is null on them and `medium` ∈
  {`nl`, `formal`} becomes a required schema field on every row.
- An instance is included iff **both media** produced a valid phase-1 solution. Expected inclusion
  is p₁², not p₁⁵.
- The paraphrase is generated once per instance from the single formal artifact.
- `form_full` vs `form_strip_verbatim` and `nl_full` vs `nl_strip` become within-record
  comparisons, which is what the design was supposed to be.
- Phase-1 calls drop from five to two per instance.

**experiment-B-context-strip.md §3** — replace the first two paragraphs of the Procedure with:

> **Phase 1 — produce the solution.** Once per medium per instance: one NL run and one formal run,
> up to 3 attempts with diagnostic feedback. The five cells share these two records; nothing in
> phase 1 differs between cells of the same medium.

**ORCHESTRATOR.md §2**, schema line — add `medium` to the required fields and note that `cell` is
null on `p1` rows.

### Instance supply

Instead of gating on the inclusion rate, the run consumes instances in the frozen order until the
target is reached:

**experiment_B.frozen.yaml**, `instances:` — replace `n_full: 70` with

```yaml
  n_target_included: 70        # phase 1 proceeds down the frozen instance list until reached
  n_max_generated: 120         # hard cap; if reached without the target, stop and report
```

and in `gates.pilot:` replace `min_inclusion_rate` with

```yaml
    min_inclusion_rate_ci_upper: 0.60   # stop only if the 95% Wilson UPPER bound is below 0.60
```

so a pilot that is merely unlucky does not halt a run whose instance supply is itself elastic.

## B2 — The calibration-consistency gate becomes a test, not a threshold

Accepted: a fixed 0.20 deviation between 8 calibration and 10 pilot instances fires on noise at
rates between 17% and 84% depending on the true success probability. The gate is meant to catch a
gross change (a different model, a broken prompt), not a difficulty that sits slightly off the
band.

**experiment_B.frozen.yaml**, `gates.pilot:` — replace `max_calibration_deviation: 0.20` with

```yaml
    calibration_consistency_test: fisher_exact_two_sided
    calibration_consistency_alpha: 0.01   # per check; 4 checks (2 domains x 2 media)
```

**tests/test_preflight.py** — replace the body of `test_pilot_matches_calibration` with a Fisher
exact test on the two counts (calibration successes out of 8, pilot successes out of 10), failing
only at p < 0.01. State in the docstring that the gate is deliberately underpowered: it is a
smoke detector for a changed pipeline, not a test of difficulty.

## B3 — The λ testability condition had a sign bug

Accepted. Checking only that the denominator CI excludes zero lets a *negative* denominator
through, which flips λ and can report H2 as supported when `form_strip_verbatim` is worse than
`nl_strip`. The condition is now `d_lo > 0`, applied in v2 of the script.

The explanatory sentence in AMENDMENTS-v1 §A3 was also wrong and is corrected here: the
denominator is the medium effect under strip, not the difference of differences. H1 can fail with
a large denominator, and the denominator can be null with H1 supported. The two are independent,
which is precisely why H2 needs its own testability condition.

## B4 — Holm now enters the decisions, and the family has a fixed size

Accepted, all four sub-points. In v2:

- `supported` = effect criterion **and** Holm-corrected p < 0.05, for all three confirmatory tests.
- All three are one-sided in the hypothesised direction: H1 that the strip costs more in NL,
  H2a that λ < 0.5, H2b that verbatim grades above paraphrase.
- H2b is always in the family. If every graded pair ties, its p is 1.0 rather than the test being
  dropped, so the family size never depends on the data.
- H2b has a decision rule: mean grade difference ≥ 0.25 on the 0–2 scale, and Holm-corrected
  p < 0.05.

**experiment_B.frozen.yaml**, `analysis:` — add

```yaml
  alpha: 0.05
  mei_grade: 0.25
  one_sided: true
```

and update §6 of the spec so the stated rules match these, since the preflight test now compares
the config with the constants in the script.

## B5 — The A-probes are redesigned

Accepted, and the observation about the paraphrase instruction is the decisive one. An A-probe is
usable only if all four of these hold:

1. the answer is determined by the artifact;
2. it varies across artifacts;
3. it is not derivable from the phase-1 problem statement;
4. it is not excluded from the paraphrase by the paraphrase instruction.

The old probes failed (3) for the ASP atom name, (2) for the integrity-constraint/choice-rule
dichotomy and for the maze visited-set, and anything about identifiers fails (4), which would make
H2b a rigged test.

**New probes.** `experiment-B-context-strip.md §4.8` — replace the probe texts with:

> Maze:
>
> ```
> In the program that produced the solution above, how is the set of collected keys represented,
> and how is the final path reconstructed once the goal is reached?
> Answer in at most 40 words. If this cannot be determined from what you have, answer exactly:
> CANNOT DETERMINE.
> ```
>
> ASP:
>
> ```
> In the encoding that produced the schedule above, how is the range of admissible start times
> bounded, and how is the machine-overlap condition written?
> Answer in at most 40 words. If this cannot be determined from what you have, answer exactly:
> CANNOT DETERMINE.
> ```

Both ask about design choices that differ between artifacts (bitmask / frozenset / sorted tuple /
string; parent map / path carried in the queue; deadline / sum of durations / an explicit makespan
bound; pairwise integrity constraint / auxiliary busy atom / aggregate), none of which is fixed by
the problem statement, and all of which a prose description may legitimately contain.

**Discrimination gate.** A blind fingerprinting session labels every phase-1 artifact on a closed
set of values per field, and the pilot must show variation:

```yaml
a_probe:
  fingerprint_fields:
    maze: [key_set_representation, path_reconstruction]
    asp: [time_horizon_bound, overlap_encoding]
  fingerprint_session: blind          # sees the artifact only, never a cell or a probe answer
  gate_modal_share_max: 0.80          # if one value covers more than 80% of artifacts, the probe
                                      # does not discriminate
  fallback_order:                     # used once, automatically, and recorded
    maze: [frontier_order, duplicate_state_handling]
    asp: [start_time_selection_rule, objective_or_deadline_handling]
  on_second_failure: drop A-probes and report H2b as not testable
```

Grading is unchanged: the blind grader judges the answer against the artifact. The fingerprint is
used only for the discrimination gate, not as the grading key, so a coarse label cannot turn a
correct answer into a wrong one.

## B6 — Minor points, all accepted

- `harness/probes.py` (`applies_to(kind)`, probe generation and ground truth) and
  `config/gates.pilot.json` are added to the layout in ORCHESTRATOR.md §2.
- §5 of the spec is corrected: H4's equivalence test is the declared pair `nl_strip` vs
  `form_strip_verbatim`; abstention and contradiction rates are reported for every cell; and the
  condition that abstention must not saturate at 100% is restored as a reported flag, not a gate.
  v2 of the script emits all three.
- **Vendor pinning.** A clone of `main` is not reproducible. Record the commit in the frozen
  config and check it at run start:

```yaml
vendor:
  operability:
    url: https://github.com/AndoSan84/operability.git
    commit: <sha recorded at clone time>
    path: vendor/operability
    read_only: true
```

- **Table 3 dataset.** Confirmed absent from the machine and from the repository, where only the
  3-trial file exists. It is not recovered. The consequence belongs to the corrections section of
  the response letter and to the paper: the maze experiment is re-run under the corrected protocol
  as part of Experiment A, and the published Table 3 is withdrawn rather than reconstructed. Do
  not attempt to regenerate numbers that match it.

---

## Applying this

Apply B1 to B6 to the four files, replace the analysis script with v2, and produce the diff before
anything is frozen. Then run `pytest -q tests/test_preflight.py`: with the harness still unbuilt
the contract tests fail at import, which is the expected starting state, but
`test_decision_rules_match_the_analysis_script` must already pass once the config edits are in,
because it needs only the config and the script.
