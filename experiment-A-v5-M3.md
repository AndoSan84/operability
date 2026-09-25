# Experiment A v5 — M3: the medium under an identical loop

Pre-registration. Committed before the first M3 call. Decided after M1 (v3) and M2 (v4) were
analysed; that sequence is declared here and in the paper.

## 1. Question

Under the same feedback loop — up to three attempts, diagnostic feedback on any failure, the
previously evaluated object in the prompt — does the medium in which the model answers change how
often the task is solved?

The two media are a schedule written in prose (NL) and a Clingo encoding executed by the solver
(ASP). This is the only test in the revision of the claim that an artifact whose semantics is fixed
by an executor is what makes feedback appropriable. It bears on the answer to Reviewer 1 on
originality and on the Kautz classification (the same wiring, different media).

**What the contrast includes by construction.** The ASP arm delegates the search to Clingo; the NL
arm computes the schedule itself. The primary outcome therefore measures the medium as the thesis
defines it — prose against an artifact with executor-fixed semantics — and not formal syntax alone.
The secondary analysis on doubly failed instances (§5) is the part closest to isolating the loop.

## 2. Design

- **Paired and concurrent.** Every instance is run in both arms, in the same batch. The order of the
  two arms is randomised per instance, so that time-of-day and rate-limit pauses cannot line up
  with one medium.
- **Independent attempt 1 per arm.** The media differ, so nothing is shared.
- **Identical loop policy.** Up to three attempts; after any failure — invalid schedule, UNSAT,
  syntax error, unparsable reply — the next attempt receives diagnostic feedback and the previously
  evaluated object. Unlike M1, syntax errors *are* looped: the question here is the medium, and the
  Symbolic Bottleneck is part of what the formal medium costs.
- **Last-step persistence**, as in M1: attempt 3 carries the attempt-2 object and feedback only.

## 3. Instances and model

- ASP job-shop, M1's calibrated difficulty `[18, 5, 18]`, **fresh instances** from a new seed
  stream (none of M1's instances are reused).
- **n = 200 instances.** Power for a 15-point difference in success within three attempts: 0.85
  with independent arms, 0.94 with moderate within-instance correlation. For 10 points no feasible n
  is adequate, and the paper says so.
- `claude-haiku-4-5-20251001`, CLI pinned to 2.1.282 with auto-update disabled; a version mismatch
  at any batch start aborts the run. The thinking/effort setting is written into **every** row.
- **Pilot:** 12 instances from a separate seed, discarded. Floor rule: if either arm solves 0/12 at
  attempt 1, the run moves once to the next easier point of M1's calibration grid, re-pilots, and
  records the move. No other adjustment.

## 4. Prompts

Attempt 1 — NL: `experiment-B-context-strip.md` §4.3, unchanged. ASP: §4.4, identical to M1's
shared attempt.

Retry, NL:

```
Your schedule is not valid.
{{FEEDBACK}}

Your previous schedule:
{{PREVIOUS_SCHEDULE_LINE}}

Provide a corrected schedule. Reason in prose. Do not write code.
End your reply with exactly one line, and write nothing after it:
SCHEDULE: {1: t1, 2: t2, ...}
```

Retry, ASP:

```
Your encoding was run with Clingo. The result is not a valid schedule.
{{FEEDBACK}}

Your previous encoding:
{{PREVIOUS_ARTIFACT}}

Return a corrected program, as exactly one ```clingo code block and nothing else.
```

`FEEDBACK` is the same validator message in both media whenever a schedule exists (for example
`overlap on machine B between jobs 4 and 6`). The medium-specific parts are:

| failure | NL feedback | ASP feedback |
|---|---|---|
| invalid schedule | validator message | validator message + solver output |
| UNSAT | — | "Clingo found no answer set, although the instance admits a valid schedule: some constraint in your encoding is stronger than the specification." |
| syntax / parse | "No schedule could be read from your reply; the final line must be `SCHEDULE: {...}`." (previous-schedule block omitted) | Clingo's error message |

The solver output appears only in the ASP arm because only that medium has a solver; the NL arm's
evaluated object is already the schedule. This asymmetry is intrinsic to the comparison and is
stated as such.

## 5. Measures and decision rules

**Primary — success within three attempts**, paired over all 200 instances. Exact two-sided
McNemar test; effect = p_ASP − p_NL with a paired bootstrap interval (10,000 resamples, seed
20260924). Four pre-registered outcomes:

- **ASP advantage**: difference ≥ +0.15 and p < 0.05;
- **reversal**: difference ≤ −0.15 and p < 0.05 — reported as a reversal, not reinterpreted;
- **bounded**: the 90% interval lies inside ±0.15, so no medium effect of 15 points or more;
- **inconclusive**: anything else.

**Secondary**, reported whatever the primary shows:

- attempt-1 success per medium, paired McNemar — the single-shot comparison, delegation included;
- **repair among doubly failed instances**: those failing attempt 1 in *both* media, success within
  the two remaining attempts, paired McNemar — the loop's effectiveness in each medium on the same
  problems;
- attempts to success (1, 2, 3, censored as 4), two-sided signed-rank test and Hodges–Lehmann;
- failure taxonomy per arm and attempt: invalid by violation type, UNSAT, syntax, unparsable,
  abstention or refusal;
- uptake and regression per arm, with the corrected regression denominator (attempt-3 successes
  included);
- contamination per arm.

## 6. Gates

- CLI version and model id identical on every call; otherwise abort.
- For each instance, the problem block of attempt 1 is byte-identical across the two arms except for
  the medium instruction; checked mechanically.
- Contamination ≤ 2% per arm in the pilot; parse failures are an outcome and are looped, not gated.
- Structural violations abort, as in M1.

## 7. Limitations to state

One model, one domain, one difficulty. The medium contrast includes delegation by construction.
Last-step persistence only. A difference smaller than about 15 points is not detectable at this n.
