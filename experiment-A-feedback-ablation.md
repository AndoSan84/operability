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
   ├── valid   → instance contributes attempts_to_success = 1 to both arms
   └── invalid → BINARY arm:     attempts 2, 3 with a pass/fail verdict
                 DIAGNOSTIC arm: attempts 2, 3 with the violated constraint
```

Both branches receive the same failing encoding, the same number of attempts, and contexts that
differ only in the feedback line. The single-shot execute-and-check level is the success rate at
attempt 1; no separate arm is paid for it.

**Domain: ASP job-shop only.** The maze is excluded on evidence rather than on cost: in the logged
runs the executed condition never produced an invalid path, so its loop repaired formatting and
tool failures, not reasoning. A domain with nothing to repair cannot test the content of feedback.

**Model:** Haiku for the main design, Sonnet for a small replication of the same contrast. The
main model being the weaker one is an advantage here: more first-attempt failures means more
instances in which the loop can be observed working.

## 3. Budget and priority ladder

Fixed in advance so that nothing is decided after seeing results. Modules run in this order, and
a module starts only if the preceding ones completed within their estimate.

| module | n | est. calls | model |
|---|---|---|---|
| calibration (throwaway instances) | — | ~20 | Haiku |
| pilot, core design | 6 | ~15 | Haiku |
| **M1 — core: binary vs diagnostic** | 40 | ~95 | Haiku |
| **M2 — maze replacement: NL / code-mental / code-executed** | 20 | ~70 | Haiku |
| **M3 — medium: NL with the same diagnostic loop** | 25 | ~45 | Haiku |
| **M4 — replication of the core contrast** | 12 | ~29 | Sonnet |

Hard caps: 350 Haiku calls, 45 Sonnet calls. On exceeding a cap the run stops and reports; it does
not shed instances to fit. If M4 cannot run within the Sonnet cap, it is reported as not run.

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
Attempts 2 and 3 differ between arms **only** in the feedback line.

Diagnostic:

```
Your encoding was run with Clingo. The schedule it produced is not valid.
{{VALIDATOR_ERROR}}
Clingo output: {{SOLVER_OUTPUT_TRUNCATED}}

Your previous encoding:
{{PREVIOUS_ARTIFACT}}

Return a corrected program, as exactly one ```clingo code block and nothing else.
```

Binary:

```
Your encoding was run with Clingo. The schedule it produced is not valid.

Your previous encoding:
{{PREVIOUS_ARTIFACT}}

Return a corrected program, as exactly one ```clingo code block and nothing else.
```

Syntactic failures (Clingo refuses the program) return the solver's error in both arms: a program
that does not run is not a feedback manipulation, it is a precondition. Record those attempts
separately.

## 6. Measures

1. **Attempts to success** — 1, 2, 3, or censored. Primary. Ordinal, so each instance carries more
   information than a success/failure bit, which is what makes n = 40 workable.
2. **Success within three attempts** — secondary, McNemar on the paired instances.
3. **First-attempt success** — the single-shot level, shared by construction between arms.
4. **Feedback uptake** — the proportion of attempts in which the violation present at attempt k is
   absent at k + 1. Computable in both arms, since the validator names the violation even when the
   model is not told it.
5. **Regression** — a violation repaired at attempt k reappearing at k + 1. This is the quantity
   Reviewer 1 asks about under "chain disloyalty", measured rather than discussed.
6. **Symbolic bottleneck** — first-attempt syntactic validity and semantic validity, reported
   separately.
7. **Contamination** — the rate of responses referring to tools, files or execution, per arm, as
   fixed in C8.

## 7. Pre-registered decisions

- **Primary.** One-sided Wilcoxon signed-rank on attempts-to-success, diagnostic fewer than
  binary, over instances that failed attempt 1. Censored cases take the value 4. Supported iff
  p < 0.05 and the median difference is at least half an attempt.
- **Secondary.** McNemar on success within three attempts; uptake and regression rates with Wilson
  intervals; both reported whatever the primary shows.
- **M3 (medium).** Diagnostic loop on NL against the same loop on ASP, success within three
  attempts, reported with intervals and labelled exploratory; n = 25 does not support a
  confirmatory claim.
- **M4 (Sonnet).** Descriptive replication with intervals. With n = 12 only a large effect is
  visible; the paper says so rather than reporting a p-value as if it settled anything.
- **Null result.** If diagnostic and binary are indistinguishable, the interpretable-feedback
  condition is downgraded from necessary to facilitating in the manuscript, and the finding is
  reported as a boundary of the framework. This sentence exists so that the outcome cannot be
  reinterpreted later.

## 8. Gates

- **Branch identity**: the two attempt-2 contexts must be byte-identical except for the feedback
  line. Checked mechanically on every branched instance; a mismatch aborts.
- **Calibration band**: first-attempt success between 0.40 and 0.60, which is where the loop has
  room to work. Outside the band the closest grid point is used and recorded; the band is a
  target, not a gate.
- **Floor on the shared attempt**: if fewer than 8 instances fail attempt 1, the contrast has no
  material and the run stops with a report — there is nothing to repair.
- **Contamination** ≤ 2% per arm in the pilot, **parse failures** ≤ 5%, subscription rate-limit
  waits excluded from the error budget, all as fixed in C8.

## 9. Limitations to state in the paper

- One domain, one formalism, two models, small n: the design isolates a mechanism, it does not
  benchmark.
- Persistence and executability are held constant, so this experiment ablates one of the three
  conditions; the other two remain untested as separable factors, and Experiment B, which would
  test them, is published as a design and not run.
- The runs go through the Claude CLI in non-interactive mode with the isolation and the
  contamination measure documented in C8; an agent-oriented system prompt cannot be fully removed.
- Attempts are capped at three, so attempts-to-success is censored, and the censoring is identical
  across arms.
