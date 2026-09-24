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
