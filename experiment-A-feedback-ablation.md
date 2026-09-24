# Experiment A — Interpretable feedback, ablated

Pre-registration. Commit before the first run; nothing below is edited after it.

This is the experiment the revision needs: it answers Reviewer 2's Major 3c (diagnostic feedback
against pass/fail at an equal number of attempts, and single-shot execution against an iterated
loop) and Reviewer 1's request for a comparison against prior systems, since every level of the
design instantiates a published configuration.

Experiment B (context strip) does not fit the available budget and becomes future work. Its
pre-registration is published as written, which is worth stating in the response letter: the
design exists, it was costed, and it was not run.

---

## 1. What is manipulated, and what is held constant

Operability names three conditions. This experiment ablates one of them and holds the other two
fixed, which is what makes it interpretable at this scale:

| condition | status |
|---|---|
| executability | held on — Clingo plus the specification checker, in every arm |
| semantic persistence | held on — the previous encoding is in the context in every arm |
| interpretable feedback | **manipulated** — the violated constraint, or only a pass/fail verdict |

Holding persistence on in both arms is deliberate: the previous implementation had it off
everywhere, so the manipulation would otherwise repeat that defect.

## 2. Design

One shared first attempt per instance, then a branch.

```
attempt 1  (identical prompt, run once)
   ├── valid                          → first-attempt success; not branched
   ├── invalid_schedule | no_answer_set → BINARY arm:     attempts 2, 3 with a pass/fail verdict
   │                                     DIAGNOSTIC arm: attempts 2, 3 with the diagnosis
   └── syntax_error | solver_timeout | unparsable → not branched; symbolic bottleneck (measure 6)
```

Both branches receive the same failing encoding, the same number of attempts, and contexts that
differ only in the declared feedback block (§5). Only failures a diagnosis can speak to branch: a
program that does not run gets the solver's error in both arms, which is no manipulation
(AMENDMENTS-A-v1, D3). The single-shot execute-and-check level is the success rate at
attempt 1; no separate arm is paid for it.

**Domain: ASP job-shop only.** The maze is excluded on evidence rather than on cost: in the logged
runs the executed condition never produced an invalid path, so its loop repaired formatting and
tool failures, not reasoning. A domain with nothing to repair cannot test the content of feedback.

**Model:** Sonnet for every confirmatory module, for uniformity, run in batches of a few dozen
calls under the rules of §8a. Haiku runs an optional descriptive replication of the core contrast
(M4). Difficulty is calibrated for Sonnet, so that about half the instances fail attempt 1.

## 3. Budget and priority ladder

Fixed in advance so that nothing is decided after seeing results. Modules run in this order, and
a module starts only if the preceding ones completed within their caps. Expected cost per branched
instance is about 2.8 calls (at most 4).

| module | n | expected calls | cap | model |
|---|---|---|---|---|
| calibration (separate seed stream, discarded) | 5 grid points × 4 | 20 | 24 | Sonnet |
| pilot (not counted in M1) | 6 | ~15 | 24 | Sonnet |
| **M1 — core: binary vs diagnostic** | **40 branched** (min 30) | ~195 | 280 | Sonnet |
| M2 — maze replacement: NL / code-mental / code-executed | 20 | ~70 | 90 | Sonnet |
| M3 — medium: NL with the same diagnostic loop | 25 | ~45 | 60 | Sonnet |
| M4 — replication of the M1 contrast | 30 branched | ~150 | 200 | Haiku |

On exceeding a cap the run stops and reports; it does not shed instances to fit. M1 is the only
confirmatory module. M2 and M3 are exploratory and run only after M1 has completed; whether they
run depends on the calls available, and that decision is recorded before M1 is analysed, so it
cannot depend on M1's result. M4 is optional and descriptive. A module not run is reported as not
run.

**Instance supply for M1.** Attempt 1 proceeds down the frozen list until 40 instances have
branched, with a cap of 110 attempt-1 instances. After each batch, if the 95% Wilson upper bound
of the observed branching rate would leave fewer than 30 branched instances at the cap, the run
stops and reports that the contrast has no material.

M2 exists because Table 3's dataset is lost and Table 4 was produced under a contaminated harness:
it re-establishes the syntax-versus-execution contrast on a current model under the hardened
protocol, at a size honest about its power.

## 4. What each level corresponds to in the literature

- attempt 1 alone — program-aided single-shot execution (PAL, execute-and-check).
- binary feedback, up to 3 attempts — re-prompting with a sound verifier, the configuration
  Stechly et al. found to retain most of the benefit of richer critique in their domains.
- diagnostic feedback, up to 3 attempts — the refinement loop of LLM-Modulo, Self-Debugging and
  Logic-LM, in which the critic names what failed.

The comparison the reviewer asked for is therefore also the comparison against prior work, on
identical instances.

## 5. Prompts

Attempt 1 and the problem block are those of `experiment-B-context-strip.md` §4.4, unchanged.
Every call is a single user message (AMENDMENTS-A-v1, D5): at attempt k ≥ 2, the attempt-1 prompt
verbatim, a blank line, then the retry prompt, whose `{{PREVIOUS_ARTIFACT}}` is the most recent
encoding only. Arms differ **only** in `{{FEEDBACK_BLOCK}}`.

```
Your encoding was run with Clingo. {{FEEDBACK_BLOCK}}

Your previous encoding:
{{PREVIOUS_ARTIFACT}}

Return a corrected program, as exactly one ```clingo code block and nothing else.
```

| failure at attempt k | binary `FEEDBACK_BLOCK` | diagnostic `FEEDBACK_BLOCK` |
|---|---|---|
| `invalid_schedule` | `It did not produce a valid schedule.` | `The schedule it produced violates:` then the validator's violations, one per line, then `Clingo output: {{SOLVER_OUTPUT_TRUNCATED}}` |
| `no_answer_set` | `It did not produce a valid schedule.` | `Clingo found no answer set (unsatisfiable, or no start/2 atoms).` then `Clingo output: {{SOLVER_OUTPUT_TRUNCATED}}` |
| `syntax_error`, `solver_timeout` | Clingo's error or timeout message | identical to binary |
| `unparsable` | `Your reply contained no clingo code block.` | identical to binary |

Solver output is truncated to 1,500 characters. It is part of the diagnostic manipulation and
carries the produced schedule as atoms; that is declared, not incidental. The last two rows are
preconditions, not manipulations, and are recorded as such.

## 6. Measures

1. **Attempts to success** — 2, 3, or censored (4), on branched instances. Primary. Ordinal, so
   each instance carries more information than a success/failure bit, which is what makes 40
   branched instances workable (power in AMENDMENTS-A-v1, D1).
2. **Success within three attempts** — secondary, McNemar on the paired instances.
3. **First-attempt success** — the single-shot level, shared by construction between arms.
4. **Feedback uptake** — for consecutive attempts that both produced a schedule, the share of
   violations present at k that are absent at k + 1; violations are the validator's (constraint
   type, jobs involved) tuples. Computable in both arms, since the validator names the violation
   even when the model is not told it. Wilson intervals over violations, and a per-instance
   version as a robustness check.
5. **Regression** — a violation present at attempt 1, absent at 2 and present again at 3; count and
   rate over instances reaching attempt 3, per arm. This is the quantity Reviewer 1 asks about
   under "chain disloyalty", measured rather than discussed.
6. **Symbolic bottleneck** — the distribution of attempt-1 outcomes over the disjoint categories
   `valid`, `invalid_schedule`, `no_answer_set`, `syntax_error`, `solver_timeout`, `unparsable`.
7. **Contamination** — the rate of responses referring to tools, files or execution, per arm, as
   fixed in C8.

## 7. Pre-registered decisions

- **Primary.** One-sided Wilcoxon signed-rank (`zero_method="wilcox"`) on the paired difference in
  attempts-to-success, binary minus diagnostic, over branched instances; censored cases take the
  value 4. Supported iff p < 0.05 **and** the mean paired difference is at least 0.25 attempts.
  The Hodges-Lehmann estimate and a paired bootstrap 95% CI of the mean difference (10,000
  resamples, seed 20260925) are reported with it. A median threshold is not used: with 30–45% tied
  pairs the median is 0 under a real effect (AMENDMENTS-A-v1, D2).
- **Secondary.** McNemar on success within three attempts; uptake and regression rates with Wilson
  intervals; both reported whatever the primary shows.
- **M3 (medium).** Diagnostic loop on NL against the same loop on ASP, success within three
  attempts, reported with intervals and labelled exploratory; n = 25 does not support a
  confirmatory claim.
- **M4 (Haiku).** Descriptive replication of the M1 contrast, same instances list and rules, with
  intervals. It is evidence of the effect on a model of different scale, not a second
  confirmatory test.
- **Null result.** If diagnostic and binary are indistinguishable, the interpretable-feedback
  condition is downgraded from necessary to facilitating in the manuscript, and the finding is
  reported as a boundary of the framework. This sentence exists so that the outcome cannot be
  reinterpreted later.

## 8. Gates

- **Branch identity**: the two attempt-2 contexts must be byte-identical after each arm's
  `FEEDBACK_BLOCK` is replaced by a placeholder. Checked mechanically on every branched instance;
  a mismatch aborts.
- **Calibration band**: first-attempt success between 0.40 and 0.60 on Sonnet, which is where the
  loop has room to work. Four instances per grid point give a standard error near ±0.25, so the
  band is a target, backed up by the elastic instance supply of §3, not a measurement or a gate.
- **Material**: the stopping rule of §3 on the branching rate (Wilson upper bound, 30 branched
  instances at the cap of 110).
- **Contamination** ≤ 2% per arm in the pilot, **parse failures** ≤ 5%, structural checks on every
  call, subscription rate-limit waits excluded from the error budget, all as fixed in C8.

## 8a. Batches

The run is executed in batches of a few dozen calls, as the subscription allows.

1. **Fixed N, analysis only at the end.** Between batches only the operational gates of §8 and the
   attempt-1 branching rate (shared by both arms) are computed. No arm-level outcome is computed
   before the target is reached; there is no interim analysis and no stopping for significance.
2. **An instance lives in one batch**: attempt 1 and both arms, with the order of the two arms'
   calls drawn per instance from the frozen seed.
3. **The CLI does not update during the run**: `DISABLE_AUTOUPDATER=1`; a version change aborts.
4. **`batch_id` in every row**; attempt-1 success per batch is reported in a drift table.

## 9. Limitations to state in the paper

- One domain, one formalism, one confirmatory model (Sonnet) with a descriptive replication on
  Haiku, small n: the design isolates a mechanism, it does not benchmark. With 40 branched
  instances a large effect is detected reliably, a medium one about two times in three, and a
  small one is out of reach; the CI of the primary says which of these the result is.
- Persistence and executability are held constant, so this experiment ablates one of the three
  conditions; the other two remain untested as separable factors, and Experiment B, which would
  test them, is published as a design and not run.
- The runs go through the Claude CLI in non-interactive mode with the isolation and the
  contamination measure documented in C8; an agent-oriented system prompt cannot be fully removed.
- Attempts are capped at three, so attempts-to-success is censored, and the censoring is identical
  across arms.
