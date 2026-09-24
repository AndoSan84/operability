# Experiment B — Context strip and re-derivability

Spec for implementation. This document is the pre-registration: commit it **before** the first
full run and do not edit the hypotheses or the decision rules after seeing results.

Experiment A (the condition ablation: single-shot vs iterated, binary vs diagnostic feedback,
persistence on/off) is specified separately. Both share one harness; build the harness first.

---

## 1. Claim under test

A model that must continue a partially solved task cannot re-derive, within its inference
budget, the intermediate states that produced its own previous answer. The claim of the
Operability framework is that this does not matter when what survives in the context is an
artifact whose behaviour a deterministic executor can regenerate, and that it does matter when
what survives is a description.

Two failure modes are deliberately separated:

- **Not computable** — the model never had the state (Experiment A).
- **Not persisted** — the model had the state, produced a correct answer, and the derivation is
  gone (this experiment).

The experiment does **not** test summarisation quality. The "summary" is generated
deterministically by the harness from ground truth, so it is complete by construction. The
manipulated variable is only *what kind of object* survives in the context.

Operational restatement (use this wording in the paper; avoid "the model remembers why"):
after the derivation is removed, the information that discriminated between alternatives is
either re-derivable from the surviving object at low cost, or it is gone.

---

## 2. Design

Two factors, fully crossed within domain, paired on instances.

| Cell | Medium (phase 1) | What the phase-2 context contains |
|---|---|---|
| `nl_full` | natural language | original reply verbatim, including all prose reasoning |
| `nl_strip` | natural language | canonical solution only |
| `form_full` | formal + execution | original reply verbatim (code + reasoning) + execution output |
| `form_strip_verbatim` | formal + execution | canonical solution + artifact verbatim + execution output |
| `form_strip_para` | formal + execution | canonical solution + prose paraphrase of the artifact + execution output |

`*_full` are the controls that quantify the cost of the strip inside each medium.
`form_strip_para` is the cell that decides the interpretation: same medium of origin, same
phase-2 affordances, description instead of artifact.

Domains: maze-with-keys-and-doors and ASP job-shop scheduling. Reuse the generators and
validators already in the repository; do not write new ones (see §7).

Instances: 70 per domain, identical across all five cells (paired). Difficulty calibrated in the
pilot so that phase-1 success is high (≥80%) — this experiment is about continuation, not about
initial success.

Inclusion rule: an instance enters the analysis only if **every** cell produced a valid phase-1
solution for it. Log the exclusion rate per cell; report it.

---

## 3. Procedure

### Phase 1 — produce the solution
Solve the instance, up to 3 attempts with diagnostic feedback, identically in all cells of the
same medium. Keep: raw reply, artifact, execution output, validated solution.

### Paraphrase step (only `form_strip_para`)
One extra call asking the model to describe its own artifact in prose, with a fixed budget and no
code. Log the paraphrase. This call is part of the condition, not part of the measurement.

### Strip — build the phase-2 context
Phase 2 is **not** a continuation of a live session. The harness constructs the message list
explicitly:

```
[user]      <phase-1 problem prompt, unchanged>
[assistant] <cell-specific content, per the table in §2>
[user]      <phase-2 prompt: perturbation, or one probe>
```

The canonical solution is emitted by the harness from the validated result (the path, or the
job→start map), in the exact output format phase 1 required. It contains every decision taken
and no derivation.

### Phase 2 — perturbation and probes
Each phase-2 prompt is a **separate API call** on the same constructed context, so that answers
cannot influence each other. Per instance and cell: 1 perturbation + 1 C-probe + 1 A-probe +
1 U-probe.

Phase-2 affordances are constant within medium: NL cells reason in prose, formal cells may write
and run code (including `form_strip_para`, which has to reconstruct it from the description).

---

## 4. Exact prompts

Placeholders in `{{ }}`. Keep the output-format lines verbatim: the parsers depend on them.

### 4.1 Maze — phase 1, NL

```
You are solving a maze with keys and doors.

Grid, row-major. '#' is a wall, '.' is an open cell, 'S' is the start, 'G' is the goal,
a lowercase letter is a key, an uppercase letter is a door. A door can be entered only if
the matching key was collected earlier in the path. A key is collected when the path enters
its cell. Moves are up, down, left, right.

{{MAZE}}

Find a valid path from S to G.
Reason in prose. Do not write code.
End your reply with exactly one line, and write nothing after it:
FINAL PATH: [(r,c), (r,c), ...]
```

### 4.2 Maze — phase 1, formal

```
You are solving a maze with keys and doors.

{{same grid block as 4.1}}

Write a Python program that solves this maze and prints the path.
Requirements:
- self-contained, runnable as `python3 solution.py`, no input, standard library only;
- it must print exactly one line: FINAL PATH: [(r,c), (r,c), ...]

Return exactly one ```python code block and nothing else.
```

Retry prompt after a failed attempt (diagnostic, same in all formal cells):

```
Your program was executed. The result is not a valid solution.
{{VALIDATOR_ERROR}}
{{PROGRAM_STDOUT_OR_TRACEBACK}}

Return a corrected program, as exactly one ```python code block and nothing else.
```

### 4.3 ASP — phase 1, NL

```
You are solving a job-shop scheduling problem.

Jobs (id, machine, duration):
{{JOBS}}
Precedence constraints (i before j), meaning job i must finish before job j starts:
{{PRECEDENCES}}
Deadline (all jobs must finish by): {{DEADLINE}}
No two jobs on the same machine may overlap in time.

Produce a schedule: an integer start time for every job.
Reason in prose. Do not write code.
End your reply with exactly one line, and write nothing after it:
SCHEDULE: {1: t1, 2: t2, ...}
```

### 4.4 ASP — phase 1, formal

```
{{same problem block as 4.3}}

Write a Clingo (ASP) program that encodes this problem and whose answer set gives a valid
schedule. Emit the schedule with atoms of the form start(Job, Time).

Return exactly one ```clingo code block and nothing else.
```

Retry prompt: same shape as 4.2, with the solver output and the validator error.

### 4.5 Paraphrase call (`form_strip_para` only)

```
Below is a program you wrote for the task above.

{{ARTIFACT}}

Describe, in prose, the method this program implements, so that a competent reader could
reimplement it. Maximum {{N_WORDS}} words. Do not include code, pseudocode, or literal
identifiers. Return the description only.
```

Set `N_WORDS` to the pilot median artifact length in words, so the description is not starved.

### 4.6 Phase 2 — perturbation

Maze:

```
The specification has changed. Door {{DOOR}} now requires both key {{K1}} and key {{K2}};
everything else is unchanged.

Provide a valid path from S to G under the new specification.
{{AFFORDANCE_LINE}}
End your reply with exactly one line, and write nothing after it:
FINAL PATH: [(r,c), (r,c), ...]
```

ASP:

```
The specification has changed. A new precedence constraint applies: job {{I}} must finish
before job {{J}} starts; everything else is unchanged.

Provide a valid schedule under the new specification.
{{AFFORDANCE_LINE}}
End your reply with exactly one line, and write nothing after it:
SCHEDULE: {1: t1, 2: t2, ...}
```

`AFFORDANCE_LINE`:
- NL cells: `Reason in prose. Do not write code.`
- formal cells: `You may write a program and it will be executed for you; return it as exactly one ```python code block (or ```clingo), followed by the required final line only after the program has been run.` — in practice the harness runs the code block and re-prompts once for the final line, or parses the program's stdout. Pick one and apply it to all formal cells identically.

### 4.7 C-probes — control, answerable from the canonical solution alone

Prediction: **no** difference between cells. These are the manipulation check.

Maze (sample half the probes on cells that lie on the path, half off it):

```
Consider the solution above. Suppose a wall were added at cell {{(r,c)}}.
Would the solution above still be valid?
Answer with exactly one line: VALID: yes or VALID: no. Do not explain.
```

ASP (sample half the windows overlapping a scheduled job on that machine, half not):

```
Consider the schedule above. Suppose machine {{M}} were unavailable during the time window
[{{T1}}, {{T2}}). Would the schedule above still be valid?
Answer with exactly one line: VALID: yes or VALID: no. Do not explain.
```

### 4.8 A-probes — artifact-dependent

Prediction: `form_strip_verbatim` ≈ `form_full` > `form_strip_para` ≈ `nl_strip`.

Maze:

```
In the method that produced the solution above, what happens when the path enters a cell that
contains a key, and at what point is a door checked against the collected keys?
Answer in at most 40 words. If this cannot be determined from what you have, answer exactly:
CANNOT DETERMINE.
```

ASP:

```
In the method that produced the schedule above, what exactly forbids two jobs from overlapping
on the same machine, and what forbids a job from starting before its predecessor finishes?
Answer in at most 40 words. If this cannot be determined from what you have, answer exactly:
CANNOT DETERMINE.
```

Grading: an independent grader model, blind to cell, scores each answer against the phase-1
artifact on a 3-point scale (correct / partially correct / incorrect-or-absent), plus the
abstention flag. Grade a 20% sample by hand and report agreement.

### 4.9 U-probes — not determined by anything that survived

Prediction: no difference between media. Measures silent versus signalled failure.

Maze:

```
Before producing the solution above, which alternative route did you consider and reject,
and for what reason?
If this cannot be determined from what you have, answer exactly: CANNOT DETERMINE.
Otherwise answer in at most 40 words.
```

ASP:

```
Job {{I}} starts at t={{T}} in the schedule above. Starting it at t={{T2}} would also have been
feasible. Why was t={{T}} chosen rather than t={{T2}}?
If this cannot be determined from what you have, answer exactly: CANNOT DETERMINE.
Otherwise answer in at most 40 words.
```

`T2` must be verified feasible by the harness before the probe is issued; drop the probe for
instances where no feasible alternative exists.

Measures: abstention rate; among non-abstentions, the rate of claims that contradict the
artifact or the instance (checkable subset), reported separately from unverifiable claims.

---

## 5. Measures

Per cell, per domain:

1. **Perturbation success** — validator verdict on the phase-2 solution under the modified spec.
2. **C-probe accuracy** — against harness-computed ground truth.
3. **A-probe score** — graded as in §4.8; report abstention separately from wrong answers.
4. **U-probe abstention rate** and contradiction rate.
5. **Artifact retention** (formal cells) — line-level diff between the phase-1 artifact and the
   phase-2 program: fraction of phase-1 lines preserved.
6. **Cost of continuation** — output tokens and wall time for the perturbation call.

Analysis: paired per instance. McNemar for binary outcomes, Wilcoxon signed-rank for scores and
retention. Report point estimates with 95% CIs, not only p-values. Pre-specified comparisons:

- `nl_full` vs `nl_strip`, and `form_full` vs `form_strip_verbatim` — cost of the strip per medium.
- `nl_strip` vs `form_strip_verbatim` — the medium effect under strip.
- `form_strip_verbatim` vs `form_strip_para` — artifact versus description.
- all cells on C-probes — must be flat.
- all cells on U-probes — must be flat.

---

## 6. Pre-registered predictions and decision rules

- **H1.** Strip costs more in NL than in formal-verbatim (interaction). Minimum effect of
  interest: 10 percentage points on perturbation success.
- **H2.** `form_strip_para` is closer to `nl_strip` than to `form_strip_verbatim` on perturbation
  success and A-probes. If instead paraphrase ≈ verbatim, the claim that the artifact carries
  what a description cannot is **not supported**, and the paper must say so: the medium effect
  would then reduce to the formality of the description, not to re-executability.
- **H3.** No medium effect on C-probes. If C-probes differ, the design is confounded and the
  other comparisons are uninterpretable — fix before reporting anything.
- **H4.** No medium effect on U-probes, and abstention well below 100% in every cell. This is the
  boundary of the framework, and it is reported whichever way it comes out.

Null results on H1 and H2 are publishable and must be reported: they bound the framework rather
than refute the Operability conditions, which Experiment A tests directly.

---

## 7. Harness requirements

These are not optional. The previous round of experiments was compromised by their absence.

- **API only.** Call the models through the provider API with pinned snapshot ids. No coding-agent
  CLI, no tools, no agent system prompt, no working directory with project files in it. Record the
  exact model id, the thinking/effort setting, temperature and max tokens in every result row.
- **Parsers first.** Write `extract_path`, `extract_schedule`, `extract_code` with fixture tests
  before anything else. Fixtures must include the markdown-bold case (`**SCHEDULE:** {...}`),
  fenced blocks labelled `prolog`, `asp` and `clingo`, multiple candidate answers in one reply
  (take the last), and replies with no answer at all. A parse failure is its own outcome category,
  never a wrong answer.
- **Validators by differential testing.** Check the repo's maze validator against a reference BFS
  and the schedule validator against a brute-force scheduler on small instances. If they disagree
  on any pilot instance, stop.
- **Disjoint outcome taxonomy** for every call: `valid`, `invalid`, `unparsable`, `abstained`,
  `refused`, `api_error`, `timeout`, `max_tokens`. Never a catch-all.
- **Full logging.** Raw response, stop reason, token usage, latency, cost, seed, and the exact
  message list sent, per call. The message list matters here: the strip is the experiment.
- **Determinism where possible.** Fixed seeds for instance generation; the instance set is
  generated once and committed.
- **Blind grading.** The A-probe grader receives the artifact and the answer, never the cell label.

---

## 8. Run plan

1. Build harness, parsers, validators; run the fixture and differential tests.
2. **Pilot: 10 instances per domain, all five cells. Stop and report.** Check phase-1 success
   ≥80%, C-probes flat, paraphrase length sane, U-probes issuable, parse failures near zero.
   Do not start the full run without review of the pilot.
3. Full run: 70 instances per domain.
4. Analysis script producing one results table per domain plus the six measures of §5.
5. Optional replication on a second model from a different family, same instances, reduced to
   `nl_strip`, `form_strip_verbatim`, `form_strip_para`.

Order of magnitude: 5 cells × 70 instances × (phase 1 up to 3 calls + 4 phase-2 calls) ≈ 2,500
calls per domain, short prompts.

---

## 9. What this experiment does not establish

State these in the paper as written limitations:

- It does not test long-context dilution. The manipulated variable is what survives, not how much
  context surrounds it.
- It does not test summarisation as performed by real agent harnesses; the canonical state is
  complete by construction, which is the best case for the non-operable medium.
- It does not establish convergence of the loop, which remains an open question.
- The U-probes show where the framework stops: information that never left a behavioural trace is
  not recoverable in any medium.
