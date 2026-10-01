# Amendments v3 to Experiment B, applied before the first run

Decisions on the six findings from the post-application review. Still nothing executed, so
`config_version` stays at 1 and this file joins v1 and v2 in the record.

`analysis/analyze_experiment_B.py` is replaced once more (v3, supplied): untestable λ no longer
takes a slot in the Holm family, the U-probe measure is a per-instance share over multiple probes,
H4 has a three-valued verdict, and the A-probe abstention column is null for the NL cells.

---

## C1 — Untestable λ is neutralised, not merely flagged (accepted)

A λ computed on a negative denominator produced a small p that took the first Holm slot and
weakened the correction for H1 and H2b. In v3 the p is set to 1.0 whenever the testability
condition fails, so the family keeps its fixed size of three without the correction being bought
with a meaningless number.

## C2 — H4 gets more observations, not a wider margin (decision)

The power calculation is right: with one binary probe per cell and roughly half the pairs
discordant, the 90% interval is already ±0.14 wide against a ±0.15 margin, so equivalence would
only ever be declared when the observed difference is near zero.

Widening the margin is the wrong fix. "The two conditions differ by less than 25 points on
abstention" is not a boundary worth writing in a paper. Instead the number of observations goes
up and the measure changes:

- **3 U-probes per instance per cell**, drawn by the harness from a declared pool;
- the per-instance measure is the **share of abstentions over the probes actually issued**, not a
  single binary;
- an instance enters H4 only if at least 2 probes were issued in both compared cells;
- the ±0.15 margin stands.

**experiment_B.frozen.yaml**, `probes:` — replace `per_instance` with

```yaml
  per_instance: {C: 1, U: 3, A: 1}
  u_probe_pool_size: 4          # 3 drawn per instance, deterministically from the frozen seed
  u_probe_min_issued: 2         # below this the instance is excluded from H4 only
```

**experiment-B-context-strip.md §4.9** — add three more templates per domain, so the pool holds
four, each with its feasibility check:

> Maze: (i) the rejected alternative route; (ii) why key {{K1}} was collected before key {{K2}},
> when either order was feasible; (iii) whether a detour through corridor {{R}} was considered;
> (iv) what made the path turn at {{(r,c)}} rather than continuing.
>
> ASP: (i) why job {{I}} starts at t={{T}} rather than the feasible t={{T2}}; (ii) which ordering
> of jobs on machine {{M}} was considered and discarded; (iii) why job {{I}} precedes job {{J}} on
> {{M}} when the reverse was feasible; (iv) whether scheduling {{I}} in the idle window
> [{{T1}},{{T2}}) was considered.
>
> A template is issued only if the harness verifies that the alternative it names is feasible;
> instances for which fewer than two templates are issuable are excluded from H4 and the exclusion
> is reported.

**Three-valued verdict**, pre-registered now rather than after seeing the interval. H4 is reported
as *equivalent* when the 90% CI lies inside the margin, as *difference* when it excludes zero, and
as *inconclusive* otherwise. Failing to establish equivalence is not evidence of a difference, and
the report must not phrase it as one.

**experiment-B-context-strip.md §6, H4** — replace the last sentence with: "Reported as
equivalent, difference, or inconclusive by the rule above. Abstention shares and contradiction
rates are reported for every cell in all three cases."

## C3 — The two circular steps are inverted (accepted, with one addition)

- **Calibration precedes generation.** P1 becomes: calibrate on throwaway instances, then generate
  the frozen list at the chosen difficulty and hash it.
- **The paraphrase budget is computed from the pilot's phase-1 artifacts**, before any paraphrase
  call in the pilot.

The addition: calibration instances are drawn from a **separate seed stream** and never enter any
analysis. Choosing the difficulty by looking at instances that are later measured would bias the
very quantity the calibration is meant to set.

**experiment_B.frozen.yaml**, `instances:` — add

```yaml
  calibration_seed: 20260925    # distinct stream; calibration instances are discarded
```

**ORCHESTRATOR.md §3, P1** — replace with: "Calibrate first, on instances drawn from
`calibration_seed`, logging every grid point; then generate the frozen instance list at the chosen
difficulty and write `INSTANCES.sha256`. Calibration instances are discarded and never appear in
`results.jsonl`."

## C4 — The pilot is separate (decision)

Pilot rows go to `results/pilot.jsonl`; pilot instances do not count toward the 70 and are not
re-used; the full run starts at the next instance in the frozen list. The pilot fixes the
paraphrase budget and decides the gates, so its instances influenced a frozen parameter and cannot
also contribute to the confirmatory analysis. The cap of 120 generated instances absorbs the cost.

**ORCHESTRATOR.md §3, P2 and P3** — state the file separation and the starting offset explicitly.

## C5 — The correction in B6 was itself imprecise (corrected)

`claude_sonnet35_45trials.json` is a file *name*, not a content description: it holds 3 trials, one
per difficulty level, with `n_trials: 3` in its config block and a 2026-02-01 timestamp. The
accurate statement, which is what goes into the record and eventually into the response letter:

> The repository contains an ASP result file run with the Claude Code `sonnet` alias (30 trials),
> a Gemini 2.5 Flash maze file (20 trials), Sonnet 4.6 and Gemini 3 Flash files (10 trials each),
> and a file named `claude_sonnet35_45trials.json` that contains 3 trials. The 135-trial dataset
> behind Table 3 is present neither in the repository nor on the author's machine.

The decision stands: Table 3 is withdrawn rather than reconstructed, and the maze experiment is
re-run under the corrected protocol as part of Experiment A.

## C6 — Minor items (accepted)

- `MEI_GRADE`'s comment is fixed in v3; `a_probe_abstention` is `null` for the NL cells rather
  than a rate computed over probes that were never issued.
- `test_decision_rules_match_the_analysis_script` moves to `tests/test_decision_rules.py`, so it
  can pass before the harness exists. It now also compares `alpha`, `mei_grade` and
  `u_probes_per_cell`.
- `medium` is added to the required-fields test; `probe_id` joins it, since probes are no longer
  unique per instance and cell.
- The call estimate in §8 is rewritten: roughly 2 phase-1 runs (up to 3 attempts each) plus, per
  cell, one perturbation, one C-probe, three U-probes, and for the formal cells one A-probe —
  about 30 calls per instance, near 2,400 per domain at n = 70, plus pilot and calibration.
- `config/gates.pilot.json` keys are fixed by the tests that read them: `inclusion`,
  `phase1_counts`, `calibration_counts`, `c_probe_accuracy`, `parse_failure_rate`,
  `api_error_rate`, `timeout_rate`, `paraphrase_contains_code`. Write the structure into
  ORCHESTRATOR §2 next to the layout, so it is not discovered by reading the tests.

---

Apply C1 to C6, take v3 of the analysis script, then commit the three amendment files together
with the edits and record the script's sha256 in the frozen config. After that commit the
pre-registration is closed: anything further is a new config version and a new results file.

---

## C7 — Corrections found while applying v3

**The frozen analysis script is not the v3 that was supplied.** The supplied v3 has sha256
`9ee882c460ef010e5f2a55ec487b1431096be36894e20ca66728880faaaee85c`; the script committed with this
file has the sha256 recorded in `analysis.sha256` of the frozen config. The difference is the
seven corrections below plus the contamination column of C8, and nothing else. On a synthetic
results file without retries, degenerate domains, missing U-probes or contamination flags, the
two versions produce the same confirmatory numbers.

Why they differ: v3 was produced by textual patches to v2, and three of those patches failed
silently. The command that inserted `MEI_GRADE` left the comment of `MEI_PP` attached to it; the
two later substitutions targeted the clean line, which by then no longer existed, matched
nothing and raised nothing. So v3 lacked both the fixed comment that C6 declares and the
`U_PROBES_PER_CELL` constant that C6's test compares. The two bugs were found by running v3 on
synthetic data, not by reading it.

1. **Retried probes counted the failure.** Probe rows were grouped without deduplication and the
   C- and A-probe measures took the first row. With an `api_error` logged before the retried
   answer, C-probe accuracy was 0% in every cell — and the flatness gate passed, because the
   cells were uniformly broken.
2. **H4 crashed with no eligible instance.** If no instance had at least two U-probes issued in
   both compared cells, the TOST divided by zero and took the whole analysis down. H4 is now
   reported as `untestable` with n = 0.
3. **`MEI_GRADE` comment** fixed, as C6 already stated.
4. **`U_PROBES_PER_CELL = 3` and `U_PROBE_MIN_ISSUED = 2`** added as constants; the hard-coded
   `min_issued=2` now uses the latter, and `tests/test_decision_rules.py` compares both with the
   config.
5. **Deduplication follows the attempt, not the file order.** For each `probe_id` the row with the
   highest `attempt` is kept, ties broken by file order. On an append-only file the two usually
   coincide; when a write lands out of order the file order lies and the attempt does not.
6. **A floor on the control probes.** Flatness passes on uniformly broken data, whatever breaks
   it; item 1 was one cause of that class, not the class. The pilot now also requires pooled
   C-probe accuracy of at least 0.70 per domain (`gates.pilot.c_probe_floor`, key
   `c_probe_pooled` in `gates.pilot.json`), otherwise PILOT_BLOCKED. C-probes are answerable
   from the canonical solution alone and balanced by construction, so chance is 0.50; near chance
   means the canonical state did not reach the context or the pipeline is broken, and in neither
   case is the full run meaningful. In the full run C-probe accuracy is reported per cell, not
   gated.
7. **A domain with no included instance no longer crashes the analysis.** It is reported as
   `no included instances` with its phase-1 counts, and the other domain is analysed normally.
   An analysis that dies on a degenerate domain would also lose the healthy one.

The three scenarios that exposed items 1, 2 and 7 are pinned in
`tests/test_analysis_edge_cases.py` (retry after an API error, in and out of file order; absent
or too few U-probes; zero included instances). Against the supplied v3, five of its seven tests
fail; against the frozen script all pass. The analysis script is the one component nobody
re-reads after the freeze, and until this file it was the only one without coverage.

## C8 — The backend is the Claude CLI, hardened and measured (decision)

**The constraint.** The reported run goes through the Claude CLI in non-interactive mode, on a
subscription, because API credit is not available. The rule it replaces, "API only", was not a
preference: it came from the audit of the previous round, where `claude -p` produced an unknown
model identity (the `sonnet` alias), an agent system prompt, available tools, harness-induced
abstentions counted as reasoning failures (15 of the 29 failed CODE_mental attempts on Gemini were
the model saying it could not execute code), and ten empty `api_error` rows on Sonnet 4.6 behind a
350-second timeout. The difference this time is not the backend; it is that the backend is
declared, hardened and measured.

Two reasons make this matter more here than in general, and both are stated so that the report
cannot be read as ignoring them. An agent framing invites execution precisely in the formal
cells, so any residue interacts with the medium, the independent variable, instead of adding a
constant offset. And H4 measures abstention, the quantity most sensitive to a harness that
suggests execution.

**Hardening, non-negotiable** (`model.cli` in the frozen config):

- a full model id in `--model`, never an alias, read back from the init event and from the
  session transcript of every call; a mismatch aborts;
- the agent system prompt replaced with `--system-prompt`, not appended;
- no tools (`--tools ""`), permissions that deny everything (`--permission-mode dontAsk`), no MCP
  servers (`--strict-mcp-config`), no setting sources, no slash commands;
- a fresh empty temporary working directory per call: no CLAUDE.md, no project memory, no
  settings file with allow rules;
- structural checks on every call, each an abort rather than a rate: no tools in the init event,
  no MCP servers, one model turn, no tool-use blocks, resolved model equal to requested;
- the CLI version recorded at run start and frozen for the run;
- `backend`, `backend_version` and the resolved model id in every row; temperature and output
  limit recorded as `backend_default`, since the CLI does not expose them; `--effort low` as the
  minimum thinking setting;
- a pilot timeout of 600 s so the latency p99 is not censored, then a frozen full-run timeout of
  max(180, 2 x pilot p99); `timeout` (wall-clock kill) and `max_tokens` stay distinct outcomes;
- subscription usage-limit rejections are not model calls: the runner waits for the reset and
  re-issues, logging to `results/runner.log`; they never count toward `api_error`, and the wait
  does not count toward the wall-clock budget.

The adapter keeps an `api` backend, so a replication can choose; the backend is a required field
of every row either way.

**Contamination is a result column.** Every response is scanned with a frozen list of patterns
for references to tools, files or execution (`contamination` in the config); the flag and the
matches go into the row, and the rate is reported per cell, next to the other measures, and per
phase-1 medium. Pilot gate: 2% in any cell, otherwise PILOT_BLOCKED, and the cause is found before
the rest is spent. In the full run it is reported, not gated. It is the artifact that destroyed
Table 4, measured while it happens instead of discovered afterwards.

**What the canary showed** (`evidence/canary-2026-09-24/`, Claude Code 2.1.281). One call with
the flags above:

- no tools, no MCP servers, `dontAsk`, and model `claude-sonnet-5` in the init event and in the
  transcript;
- the system prompt is replaced, but the CLI keeps an agent-identity prefix ("You are a Claude
  agent, built on Anthropic's Claude Agent SDK.") and injects the working environment, the
  model's identity and knowledge cutoff, the date, a token-budget reminder and account context,
  whatever the flags. All of it is constant across cells, and it is declared as part of the
  condition;
- **a harness-built assistant turn cannot be delivered as a turn.** Sent through
  `--input-format stream-json`, it was written before the first user turn, and the model then
  generated its own assistant turn reproducing it (two model calls, 17 output tokens for the
  regenerated turn). For a long cell-specific content that regeneration need not be byte-exact,
  and the byte-exact assistant turn is the manipulation.

Consequences:

- **Inline rendering.** The harness-built message list is rendered by `strip.render_inline` into
  one user message, with a fixed frame that marks the reproduced turns as the model's own earlier
  replies (spec §3). The frame is identical in every cell, so the paired contrasts are
  unaffected; what changes is that the prior turn reaches the model as a reproduced transcript
  rather than as a native turn. That is declared in §9. `messages_sha256` still hashes the
  abstract list, which the leakage test checks; the rendered prompt is stored and hashed as well.
- **Pinned model ids.** The vendor's current ids carry no date (`claude-sonnet-5`). The rule
  "most recent dated snapshot" would have rejected the only mid-tier model and aborted the run at
  start. A pinned id is now a full model id, dated wherever the vendor dates it, never a family
  alias, and verified on every call; `is_pinned_snapshot("claude-sonnet-5")` is true and the
  aliases stay false.

**The paper text, fixed now** (spec §9):

> All runs were executed through the Claude CLI in non-interactive mode, with a pinned model id,
> an empty working directory, no project memory and no tools enabled. We report the rate of
> responses referring to tools, files or execution as a contamination measure (Table X). This
> configuration is a constraint of the setting rather than a design choice: an agent-oriented
> system prompt cannot be fully removed, and it is not equivalent to a bare API call. It bears on
> the abstention measures in particular, since a harness that suggests execution may raise the
> rate at which the model declines to answer; the contamination rates we report bound, but do not
> eliminate, this concern.

A double pilot on both backends would have measured the harness effect directly. Without API
credit it is not possible, and what remains unexcluded is stated in §9 instead.

**Terms of use.** Automating a few thousand calls on a subscription must be checked against the
provider's terms before P2, and the outcome goes into the reproduction instructions.

## C9 — Status: design, not run (decision)

The real budget is a subscription on which Sonnet calls number in the tens to low hundreds, not
the ~2,400 per domain this design needs. With room for one experiment, the one run is Experiment
A (the ablation of interpretable feedback), which answers Reviewer 2's Major 3c and Reviewer 1's
comparison with prior systems. Experiment B supports the new framing, which no reviewer asked for.

This commit therefore closes Experiment B as a design: complete, costed, frozen and not executed.
It is published as written and stated as future work in the response letter. Its harness
decisions — the hardened CLI backend, the contamination measure, inline rendering, deduplication
by attempt, the edge-case tests — carry over to Experiment A, which cites C8 rather than
restating it.
