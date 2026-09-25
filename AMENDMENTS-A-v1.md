# Amendments v1 to Experiment A, applied before the first run

Findings from the implementation review of `experiment-A-feedback-ablation.md`, and the decision to
run on Sonnet in batches. No model call has been made. The edits below are applied to the spec in
the same commit; `config/experiment_A.frozen.yaml` is created from them. The analysis script is
still to be written and frozen, so this is not yet the pre-registration commit.

Power figures come from simulation: 1,500 replicates per cell, per-retry success probabilities as
stated, arms independent within an instance (conservative for a paired design).

---

## D1 — The effective n is the number of branched instances

The primary test runs only on instances that fail attempt 1; at the target calibration that is
about half of them, so "n = 40" in the original §3 and §6 was the instance count, not the test's
n. Power of the one-sided Wilcoxon by **branched** instances:

| per-retry success, binary → diagnostic | n=20 | n=30 | n=40 | n=60 |
|---|---|---|---|---|
| large, 50% → 80% (true mean difference 0.51 attempts) | 0.72 | 0.85 | **0.95** | 0.99 |
| medium, 40% → 60% (0.40) | 0.42 | 0.60 | **0.69** | 0.83 |
| small, 50% → 65% (0.28) | 0.30 | 0.43 | **0.49** | 0.60 |

**Decision:** the target is **40 branched instances**, the pre-registered minimum is 30. A large
effect is detected reliably, a medium one two times in three, a small one is out of reach of this
budget, and the paper says so.

## D2 — The effect threshold was the effect itself

"Median difference at least half an attempt" fails twice. Paired differences are integers with
30–45% ties, so the median is 0 whenever more than half the pairs tie, even under a real effect
(50% → 80%, n = 20: power 0.38 with the median rule, 0.56 with the mean). And half an attempt is
the *large* effect: 50% → 80% has a true mean difference of 0.51, so with that threshold power
stays near 0.55 however many instances are added.

**Decision:** supported iff the one-sided Wilcoxon p < 0.05 **and** the mean paired difference is
at least **0.25 attempts**. The Hodges-Lehmann estimate and a paired bootstrap 95% CI of the mean
difference (10,000 resamples, seed 20260925) are reported alongside. Zeros are handled by
`zero_method="wilcox"`, fixed now.

## D3 — Only semantic failures branch

A program that does not run gets the solver's error in both arms, so at attempt 2 there is no
manipulation; such instances would enter the primary test and dilute it. Every attempt is
classified, disjointly, as:

- `syntax_error` — Clingo rejects the program (parse or grounding error);
- `no_answer_set` — the program runs and is unsatisfiable, or yields no `start/2` atoms;
- `solver_timeout` — Clingo exceeds its time limit;
- `unparsable` — no ```clingo block in the reply;
- `invalid_schedule` — an answer set whose schedule the validator rejects;
- `valid`.

**Decision:** an instance **branches only if attempt 1 is `invalid_schedule` or
`no_answer_set`** — the two failures a diagnosis can speak to. Instances failing attempt 1 in any
other way do not branch, do not enter the primary test, and are reported under measure 6
(symbolic bottleneck). After the branch every outcome stays in the analysis: a `syntax_error` at
attempt 2 in one arm is that arm's result.

## D4 — The feedback block, defined for every failure type

The binary line "The schedule it produced is not valid" is false for `no_answer_set`, and the
diagnostic arm receives two extra lines (validator error and solver output), not one. The part of
the context that may differ between arms is now a declared **feedback block**:

| failure at attempt k | binary feedback block | diagnostic feedback block |
|---|---|---|
| `invalid_schedule` | `It did not produce a valid schedule.` | `The schedule it produced violates:` + the validator's violations, one per line, + `Clingo output: {{SOLVER_OUTPUT_TRUNCATED}}` |
| `no_answer_set` | `It did not produce a valid schedule.` | `Clingo found no answer set (unsatisfiable, or no start/2 atoms).` + `Clingo output: {{SOLVER_OUTPUT_TRUNCATED}}` |
| `syntax_error`, `solver_timeout` | Clingo's error or timeout message | identical to binary: a precondition, not a manipulation |
| `unparsable` | `Your reply contained no clingo code block.` | identical to binary |

Solver output is truncated to 1,500 characters. Including it is part of the diagnostic
manipulation, and is declared as such: it carries the produced schedule as atoms.

**Branch-identity gate, restated:** the two attempt-2 contexts must be byte-identical after each
arm's feedback block is replaced by a placeholder. Checked mechanically on every branched
instance; a mismatch aborts.

## D5 — Persistence is one message, not a transcript

The retry prompt already carries `{{PREVIOUS_ARTIFACT}}`; a transcript on top would put the
encoding in the context twice. Every call is a single user message: the attempt-1 problem block,
verbatim, followed by the retry prompt, whose `{{PREVIOUS_ARTIFACT}}` is the **most recent**
encoding only. No multi-turn context exists in this experiment, so the inline rendering of C8
does not arise; every other part of C8 (hardened CLI, structural checks, contamination) applies
unchanged.

## D6 — One model, Sonnet, in batches

**Decision:** all confirmatory modules run on Sonnet, for uniformity, in batches of a few dozen
calls, as the subscription allows. Batching is safe only under these rules, fixed now:

1. **Fixed N, analysis only at the end.** Between batches only the operational gates are checked
   (structural checks, contamination, parse failures, CLI version, model id, branch identity) and
   the attempt-1 failure rate, which is shared by both arms. No arm-level outcome is computed
   before the target is reached. Stopping "when it becomes significant" is not available; no
   interim analysis is pre-registered.
2. **An instance lives in one batch:** attempt 1 and both arms, with the order of the two arms'
   calls drawn per instance from the frozen seed, so a day effect falls on both arms alike.
3. **The CLI does not update during the run:** `DISABLE_AUTOUPDATER=1` in the runner's
   environment; a version change aborts, as in C8.
4. **`batch_id` in every row**, and attempt-1 success per batch reported in a drift table.
5. Subscription usage-limit waits fall between batches or inside one, never into the error
   budget, as in C8.

**Instance supply.** Attempt 1 proceeds down the frozen list until 40 instances have branched,
with a cap of 110 attempt-1 instances. After each batch, if even the 95% Wilson upper bound of the
observed branching rate would leave fewer than 30 branched instances at the cap, the run stops and
reports: the contrast would have no material. This replaces the "fewer than 8" floor, which at
n = 8 left power near a coin toss.

## D7 — Budget and ladder, recomputed for Sonnet

Expected cost per branched instance is 2 + (1 − p_binary) + (1 − p_diagnostic) ≈ 2.8 calls, at
most 4. With a branching rate near 0.5:

| module | n | expected calls | cap | model |
|---|---|---|---|---|
| calibration (separate seed stream, discarded) | 5 grid points × 4 | 20 | 24 | Sonnet |
| pilot (not counted in M1) | 6 | ~15 | 24 | Sonnet |
| **M1 — binary vs diagnostic** | 40 branched | ~195 | 280 | Sonnet |
| M2 — maze: NL / code-mental / code-executed | 20 | ~70 | 90 | Sonnet |
| M3 — NL with the same diagnostic loop | 25 | ~45 | 60 | Sonnet |
| M4 — replication of the M1 contrast | 30 branched | ~150 | 200 | Haiku |

M1 is confirmatory. M2 and M3 are exploratory and run only after M1 has completed; the decision to
run them depends on the calls available and is recorded **before** M1 is analysed, so it cannot
depend on M1's result. M4 moves to Haiku: it restores the evidence both reviewers asked for — the
effect on a model of different scale — at a cost the Haiku allowance covers. It is descriptive,
reported with intervals, and optional.

Calibration is coarse by construction: four instances per grid point give a standard error near
±0.25, so the 40–60% band is a target that the elastic instance supply of D6 backs up, not a
measurement.

## D8 — Uptake and regression, operationally

Violations are the validator's set of (constraint type, jobs involved) tuples.

- **Uptake** at k → k+1, for attempts where both k and k+1 produced a schedule: the share of
  violations present at k that are absent at k+1. Per arm, with Wilson intervals over violations
  and a per-instance version as a robustness check.
- **Regression**: a violation present at attempt 1, absent at 2 and present again at 3. Per arm,
  as a count and a rate over instances reaching attempt 3.

---

## Consequences for the paper

The design can now come out in four stated ways: a large effect detected; a medium effect
detected or missed, with the CI saying which; indistinguishable arms with a CI that excludes a
large effect, which is the boundary result of §7; and a run stopped for lack of material, reported
as such. The one confirmatory claim rests on Sonnet alone; the Haiku replication and the two
exploratory modules are labelled as what they are.

---

## D9 — Final decisions before freezing (supersede D1, D2, D6 in part, D7)

Taken after a second power simulation and with the analysis script in hand. Where they differ from
D1–D8, these hold; D3, D4, D5 and D8 stand as refined here. The spec, the config and the script
are frozen together in one commit.

**Power, re-simulated** (800 replicates per cell, one-sided Wilcoxon with continuity correction):

| repair per retry, diagnostic vs binary | branched n | test alone | test + HL ≥ 0.5 |
|---|---|---|---|
| 0.85 vs 0.55 | 20 / 30 / 40 | 0.71 / 0.89 / 0.95 | 0.66 / **0.78** / 0.86 |
| 0.55 vs 0.25 | 20 / 30 / 40 | 0.74 / 0.88 / 0.96 | 0.74 / **0.88** / 0.96 |
| 0.70 vs 0.50 | 20 / 30 / 40 | 0.41 / 0.55 / 0.67 | 0.40 / 0.52 / 0.62 |
| 0.85 vs 0.70 | 20 / 30 / 40 | 0.31 / 0.40 / 0.54 | 0.21 / 0.17 / 0.19 |
| 0.85 vs 0.85 (null) | 20 / 30 / 40 | 0.03 / 0.06 / 0.04 | 0.01 / 0.00 / 0.00 |

1. **Target: 30 eligible branched instances**, attempt-1 cap 90. Early stop after 20 attempt-1
   instances and after every batch if the 95% Wilson upper bound of the eligible-failure rate,
   times 90, is below 30. The upper bound replaces the point estimate: at a true rate of 0.4 (36
   expected at the cap) the point-estimate rule stops the run 25% of the time, the upper bound
   0.4%.
2. **Decision rule: one-sided Wilcoxon p < 0.05 and Hodges-Lehmann ≥ 0.5.** Not the median (0 when
   half the pairs tie; power falls as n grows) and not the mean (0.48 for an 85%/55% repair
   difference, so a 30-point effect never clears half an attempt). The HL bootstrap interval is
   reported, not decisive. D2's mean ≥ 0.25 is withdrawn.
3. **Primary population: attempt 1 runnable and semantically failed** (`invalid_schedule` or
   `unsat`), both arms finished. Pre-specified sensitivity analysis on `invalid_schedule` only.
4. **UNSAT diagnostic text:** "Clingo found no answer set, although the instance admits a valid
   schedule: some constraint in your encoding is stronger than the specification."
5. **Four prompt blocks** — problem, feedback, previous artifact, instruction. Only feedback may
   differ; solver output belongs to it, so the binary arm never receives it. The gate checks the
   other three byte for byte.
6. **One user message per call.** At attempt 3, only attempt 2's artifact and feedback. The
   cumulative context of Definition 1 is not tested, and the paper says so.
7. **M4 on Sonnet**, at the hardest grid point, until 6 branched instances, cap 45 calls;
   descriptive; fewer than 6 means not run. The Haiku replication of D7 is withdrawn: one model
   throughout.
8. **Calibration** chooses the grid point whose eligible-failure rate is closest to 0.5; coarse,
   declared, and not what protects the design.
9. **M2 explicit**: single attempt, three paired conditions, exploratory.

**Corrections to the supplied analysis script.** The frozen script is not the one supplied (sha256
of the supplied version begins `456dd1e4`); the difference is the following, found by running it
on the case the batch design makes routine — a batch interrupted mid-instance when the
subscription blocks:

- **A pending arm was scored as censored.** An arm whose attempt 2 had failed and whose attempt 3
  had not been issued yet counted as 4, giving a difference of +2 in the hypothesised direction
  that measured where the batch stopped, not the model. An arm now enters the analysis only when
  finished: repaired, or with a real attempt 3.
- **An infrastructure failure was scored as a model failure.** An attempt whose last API try is
  `api_error` is not an attempt; the arm stays incomplete until re-run, and is reported as
  incomplete if it never is.
- **Attempt-1 `api_error` rows sat in the single-shot denominator.** They are now excluded and
  counted.
- **M3** skips instances whose ASP loop is still pending, and reports how many ASP attempt-1
  failures had no loop (syntax, timeout) and were counted as ASP failures — conservative against
  the formal medium, stated rather than hidden.

The scenarios are pinned in `tests/test_analysis_edge_cases_A.py`.

**Batches and resumption** (spec §8a): append-only and flushed per call; idempotent resume from
the results file, where an attempt is done iff its last try is not `api_error`; interrupted
instances resume first; no arm-level outcome before the target; `DISABLE_AUTOUPDATER=1`. The
batch size X is an operator's choice per session and integrity does not depend on it.
