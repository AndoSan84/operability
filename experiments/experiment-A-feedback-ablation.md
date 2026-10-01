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
   ├── invalid_schedule | unsat      → BINARY arm:     attempts 2, 3 with a pass/fail verdict
   │                                   DIAGNOSTIC arm: attempts 2, 3 with the diagnosis
   └── syntax_error | solver_timeout | unparsable → not branched; symbolic bottleneck (measure 6)
```

Both branches receive the same failing encoding, the same number of attempts, and contexts that
differ only in the declared feedback block (§5). Only failures a diagnosis can speak to branch: a
program that does not run gets the solver's error in both arms, which is no manipulation
(AMENDMENTS-A-v1, D3 and D9). The single-shot execute-and-check level is the success rate at
attempt 1; no separate arm is paid for it.

**Domain: ASP job-shop only.** The maze is excluded on evidence rather than on cost: in the logged
runs the executed condition never produced an invalid path, so its loop repaired formatting and
tool failures, not reasoning. A domain with nothing to repair cannot test the content of feedback.

**Model:** Sonnet (`claude-sonnet-5`) for every module, for uniformity, run in resumable batches
under the rules of §8a. Difficulty is calibrated for Sonnet, so that about half the instances fail
attempt 1 in an eligible way. M4 is a descriptive replication on Sonnet at the hardest grid point,
not a second model.

## 3. Budget and priority ladder

Fixed in advance so that nothing is decided after seeing results. Modules run in this order, and
a module starts only if the preceding ones completed within their caps. All calls are Sonnet.
Expected cost per branched instance is about 2.8 calls (at most 4).

| module | n | cap (calls) | status |
|---|---|---|---|
| calibration (separate seed stream, discarded) | 5 grid points × 4 | 24 | — |
| pilot (not counted in M1) | 6 | 24 | gates only |
| **M1 — binary vs diagnostic** | **30 branched**, ≤ 90 attempt-1 instances | 210 | confirmatory |
| M2 — maze: NL / code-mental / code-executed | 20, single attempt | 60 | exploratory |
| M3 — NL with the same diagnostic loop | 25 | 75 | exploratory |
| M4 — M1 contrast at the hardest grid point | 6 branched | 45 | descriptive |

On exceeding a cap the run stops and reports; it does not shed instances to fit. M2 and M3 run only
after M1 has completed; whether they run depends on the calls available, and that decision is
recorded before M1 is analysed, so it cannot depend on M1's result. A module not run is reported
as not run; M4 with fewer than 6 branched instances within its cap is reported as not run.

**Instance supply for M1.** Attempt 1 proceeds down the frozen list until 30 instances have
branched (attempt 1 `invalid_schedule` or `unsat`), with a cap of 90 attempt-1 instances. After 20
attempt-1 instances, and after every batch thereafter: if the 95% Wilson upper bound of the
observed eligible-failure rate, times 90, is below 30, the run stops and reports that the regime is
the symbolic bottleneck and the contrast has no material. (The upper bound, not the point
estimate: with a true rate of 0.4, which reaches the target at the cap, a point-estimate rule
after 20 instances stops the run about one time in four.)

**M2**, explicitly: 20 maze instances, one attempt each, in three paired conditions — NL,
code-mental (a program the model traces without execution) and code-executed — exploratory. It
exists because Table 3's dataset is lost and Table 4 was produced under a contaminated harness: it
re-establishes the syntax-versus-execution contrast on a current model under the hardened
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
Every call is one user message made of four blocks, in this order: **problem** (the attempt-1
prompt, verbatim), **feedback**, **previous artifact**, **instruction**. Only the feedback block may
differ between arms; the branch-identity gate checks the other three byte for byte. At attempt 3
the previous-artifact and feedback blocks are those of attempt 2 only: the cumulative context of
Definition 1 is not tested here, and the paper says so.

```
{{PROBLEM}}

Your encoding was run with Clingo. {{FEEDBACK_BLOCK}}

Your previous encoding:
{{PREVIOUS_ARTIFACT}}

Return a corrected program, as exactly one ```clingo code block and nothing else.
```

| failure at attempt k | binary `FEEDBACK_BLOCK` | diagnostic `FEEDBACK_BLOCK` |
|---|---|---|
| `invalid_schedule` | `It did not produce a valid schedule.` | `The schedule it produced violates:` then the validator's violations, one per line, then `Clingo output: {{SOLVER_OUTPUT_TRUNCATED}}` |
| `unsat` | `It did not produce a valid schedule.` | `Clingo found no answer set, although the instance admits a valid schedule: some constraint in your encoding is stronger than the specification.` then `Clingo output: {{SOLVER_OUTPUT_TRUNCATED}}` |
| `syntax_error`, `solver_timeout` | Clingo's error or timeout message | identical to binary |
| `unparsable` | `Your reply contained no clingo code block.` | identical to binary |

Solver output is truncated to 1,500 characters. It belongs to the feedback block, so the binary arm
never receives it; it carries the produced schedule as atoms, and that is part of the diagnostic
manipulation, declared rather than incidental. The last two rows are preconditions, not
manipulations, and are recorded as such.

## 6. Measures

1. **Attempts to success** — 2, 3, or censored (4), on branched instances whose two arms are
   both finished (repaired, or a real attempt 3). Primary. Ordinal, so each instance carries more
   information than a success/failure bit, which is what makes 30 branched instances workable
   (power in AMENDMENTS-A-v1, D9). An arm pending after an interrupted batch, or ended by an
   infrastructure failure, is not a censored result: the instance waits, or is reported as
   incomplete.
2. **Success within three attempts** — secondary, McNemar on the paired instances.
3. **First-attempt success** — the single-shot level, shared by construction between arms.
4. **Feedback uptake** — over consecutive attempts k → k+1 where k failed and k+1 exists, the
   share in which at least one violation flagged at k is gone at k+1; violations are the
   validator's normalised ids (e.g. `overlap:A:4:6`), and a failure without violations (UNSAT,
   syntax) counts as the single violation of its outcome. Per arm, Wilson intervals. Computable in
   both arms, since the validator names the violation even when the model is not told it.
5. **Regression** — a violation present at attempt 1, absent at 2 and present again at 3; count and
   rate over instances reaching attempt 3, per arm. This is the quantity Reviewer 1 asks about
   under "chain disloyalty", measured rather than discussed.
6. **Symbolic bottleneck** — the distribution of attempt-1 outcomes over the disjoint categories
   `valid`, `invalid_schedule`, `unsat`, `syntax_error`, `solver_timeout`, `unparsable`.
7. **Contamination** — the rate of responses referring to tools, files or execution, per arm, as
   fixed in C8.

## 7. Pre-registered decisions

- **Primary.** One-sided Wilcoxon signed-rank (`zero_method="wilcox"`, continuity correction,
  normal approximation) on the paired difference in attempts-to-success, binary minus diagnostic,
  over eligible branched instances with both arms finished; censored cases take the value 4.
  Supported iff p < 0.05 **and** the Hodges-Lehmann estimate is at least 0.5 attempts. A bootstrap
  95% interval of the HL estimate (10,000 resamples, seed 20260924) is reported; HL moves in half
  attempts, so the interval is coarse and does not enter the decision. Neither the median nor the
  mean is used as the threshold: the median is 0 whenever half the pairs tie, and the mean of a
  30-point repair difference (85% vs 55%) is 0.48, below any half-attempt threshold (D9).
- **Sensitivity (pre-specified).** The same test restricted to instances whose attempt 1 was
  `invalid_schedule`, excluding UNSAT.
- **Secondary.** McNemar on success within three attempts; uptake and regression rates with Wilson
  intervals; both reported whatever the primary shows.
- **M3 (medium).** Diagnostic loop on NL against the same loop on ASP, success within three
  attempts, reported with intervals and labelled exploratory; n = 25 does not support a
  confirmatory claim.
- **M4.** Descriptive replication of the M1 contrast at the hardest grid point, 6 branched
  instances, with intervals and no decision. With fewer than 6 it is reported as not run.
- **Null result.** If diagnostic and binary are indistinguishable, the interpretable-feedback
  condition is downgraded from necessary to facilitating in the manuscript, and the finding is
  reported as a boundary of the framework. This sentence exists so that the outcome cannot be
  reinterpreted later.

## 8. Gates

- **Branch identity**: the problem, previous-artifact and instruction blocks of the two attempt-2
  contexts must be byte-identical. Checked mechanically on every branched instance; a mismatch
  aborts.
- **Calibration**: coarse by construction — four instances per grid point, standard error near
  ±0.25. The grid point whose eligible-failure rate is closest to 0.5 is chosen and recorded. The
  design is protected by the sequential supply and the stop rule of §3, not by a band.
- **Material**: the stop rule of §3.
- **Contamination** ≤ 2% per arm in the pilot, **parse failures** ≤ 5%, structural checks on every
  call, all as fixed in C8.

## 8a. Batches and resumption

The run is executed in batches of X calls, X chosen per session. A batch may end at any point,
including because the subscription blocks further calls when its tokens run out; nothing is lost
and nothing is decided by where it ends.

1. **Append-only, flushed per call.** Every call is written to `results_A/results.jsonl` and
   flushed to disk before the next one is issued.
2. **Idempotent resume.** On start, the runner rebuilds the state from the results file. A loop
   attempt is done iff its last API try has an outcome other than `api_error`; everything else is
   issued again, as a new `api_try`, never as an overwrite. A usage-limit block is not a model
   call: the runner records it in `results_A/runner.log`, ends the batch, and the next session
   resumes.
3. **Interrupted instances first.** An instance left mid-loop resumes before any new instance is
   started; its arms keep the order drawn from the frozen seed. `batch_id` in every row records the
   split.
4. **Fixed N, analysis only at the end.** Between batches only the operational gates of §8 and the
   attempt-1 eligible-failure rate (shared by both arms) are computed. No arm-level outcome is
   computed before the target is reached; there is no interim analysis and no stopping for
   significance.
5. **The CLI does not update during the run**: `DISABLE_AUTOUPDATER=1`; a version change aborts.
   Attempt-1 success per batch is reported in a drift table.

## 9. Limitations to state in the paper

- One domain, one formalism, one model, small n: the design isolates a mechanism, it does not
  benchmark. With 30 eligible branched instances a repair difference of 30 points (85% vs 55% per
  attempt) is detected with probability about 0.8; a 15-point difference is not detectable with
  this budget. The design sees a large effect or nothing, and a null result is a statement about
  large effects only.
- Each retry sees only the previous attempt's artifact and feedback; the cumulative context of
  Definition 1 is not tested.
- Persistence and executability are held constant, so this experiment ablates one of the three
  conditions; the other two remain untested as separable factors, and Experiment B, which would
  test them, is published as a design and not run.
- The runs go through the Claude CLI in non-interactive mode with the isolation and the
  contamination measure documented in C8; an agent-oriented system prompt cannot be fully removed.
- Attempts are capped at three, so attempts-to-success is censored, and the censoring is identical
  across arms.
