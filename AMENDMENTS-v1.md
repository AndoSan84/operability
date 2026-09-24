# Amendments to Experiment B, applied before the first run

Five defects found during the implementation review, decided and applied here. No model call has
been made yet, so `config_version` stays at 1; this file is the record that the changes preceded
execution. After the first call, any further change means a new config version and a new results
file.

`analysis/analyze_experiment_B.py` is **replaced wholesale** (new version supplied). The edits
below are textual and apply to the other four files.

---

## A1 — The operability repository is a read-only dependency

`git clone https://github.com/AndoSan84/operability.git vendor/operability`

Reuse only the instance generators and the validators, wrapped to the interface in
ORCHESTRATOR.md §2. Do **not** reuse the answer parsers, the runners, or anything that calls a
coding-agent CLI: those are the components whose defects motivated this redesign. The results
files under `vendor/` are evidence for the corrections session and are never modified. If the
135-trial Sonnet maze dataset referenced by Table 3 exists locally, it belongs in `vendor/` too,
not in this experiment.

**ORCHESTRATOR.md §2**, add to the layout block, above `harness/`:

```
vendor/operability/   read-only clone; generators and validators are wrapped, not edited
```

## A2 — The pilot continues automatically

The spec and the orchestrator contradicted each other. The orchestrator is right: the gates are
executable precisely so that no one has to adjudicate the pilot. The single human moment is the
final unblinding, after the committed analysis has run.

**experiment-B-context-strip.md §8, step 2** — replace:

> **Pilot: 10 instances per domain, all five cells. Stop and report.** Check phase-1 success ≥80%,
> C-probes flat, paraphrase length sane, U-probes issuable, parse failures near zero. Do not start
> the full run without review of the pilot.

with:

> **Pilot: 10 instances per domain, all five cells.** Compute `config/gates.pilot.json`, write
> `PILOT_REPORT.md`, and run the pilot-gated tests. If every gate passes, continue to the full run
> without waiting for a human decision. If any gate fails, stop, write `PILOT_BLOCKED.md`, and
> change nothing.

## A3 — The tests now match the hypotheses

Three separate problems, all in the analysis rather than in the design.

**H1 is an interaction.** Comparing `nl_strip` with `form_strip_verbatim` measures the medium
effect under strip, which includes the delegation advantage that the formal medium already has
without any strip. The quantity the hypothesis names is the difference of differences,
(`nl_full` − `nl_strip`) − (`form_full` − `form_strip_verbatim`), and the 10-point minimum effect
is now part of the decision rule rather than prose.

**H2 is a position, not a difference.** "Closer to `nl_strip` than to `form_strip_verbatim`" is
λ = (p_para − p_nl_strip) / (p_verbatim − p_nl_strip), with a bootstrap CI. The denominator can be
indistinguishable from zero — that is exactly the case in which H1 has failed — so "untestable"
is now a pre-registered outcome rather than a number computed on noise.

**H4 was not tested at all,** and it is an assertion of no difference, which a non-significant
p-value does not establish. It is now an equivalence test with a declared margin of ±15
percentage points on U-probe abstention.

**experiment-B-context-strip.md §6** — replace the four hypothesis bullets with:

> - **H1.** The strip costs more in NL than in formal-verbatim. Tested as the difference of
>   differences on perturbation success, with a paired bootstrap CI (10,000 resamples, seed
>   20260924) and a Wilcoxon signed-rank test on the per-instance difference. Supported iff the
>   estimate is at least 10 percentage points and the 95% CI excludes zero.
> - **H2.** `form_strip_para` sits closer to `nl_strip` than to `form_strip_verbatim`. Tested as
>   λ = (p_para − p_nl_strip) / (p_verbatim − p_nl_strip) on perturbation success, with a bootstrap
>   CI, and as a Wilcoxon signed-rank test on A-probe grades between the two formal strip cells.
>   λ is reported as untestable if the CI of the denominator includes zero. Supported iff the
>   upper bound of the λ CI is below 0.5. If instead paraphrase and verbatim are indistinguishable,
>   the claim that the artifact carries what a description cannot is not supported, and the paper
>   says so.
> - **H3.** No medium effect on C-probes. Tested pairwise with Holm correction; a violation flags
>   the run as confounded and the other comparisons as uninterpretable.
> - **H4.** No medium effect on U-probes. Tested as equivalence between `nl_strip` and
>   `form_strip_verbatim` on abstention rate, with a margin of ±0.15 and a 90% bootstrap CI.
>   Equivalence established iff the CI lies inside the margin. Abstention rates and contradiction
>   rates are reported for every cell either way.
>
> H1, H2 and the A-probe test form the confirmatory family and are Holm-corrected within domain.
> Everything else is exploratory and is labelled as such. Null results are reported.

**experiment_B.frozen.yaml**, in `analysis:`, add:

```yaml
  mei_pp: 0.10
  lambda_threshold: 0.5
  tost_margin: 0.15
  bootstrap: {reps: 10000, seed: 20260924}
```

These values must match the constants at the top of the analysis script; the preflight test
compares them.

## A4 — A-probes exist only in the formal cells

In the NL cells there is no artifact, so there is no reference against which an answer about "the
method" could be graded; the grader would have been scoring fluency. A-probes are therefore
administered in `form_full`, `form_strip_verbatim` and `form_strip_para` only, which is where the
H2 comparison lives anyway. The NL cells contribute perturbation success, C-probes and U-probes.

The probe wording also changes. The original question ("what happens when the path enters a cell
containing a key") is partly answerable from the problem statement, which makes it a poor test of
whether the artifact survived. The replacement asks for implementation facts that exist only in
the artifact.

**experiment-B-context-strip.md §4.8** — replace the two probe texts with:

> Maze:
>
> ```
> In the program that produced the solution above, what exactly is stored in the visited set, and
> in what order are frontier nodes expanded?
> Answer in at most 40 words. If this cannot be determined from what you have, answer exactly:
> CANNOT DETERMINE.
> ```
>
> ASP:
>
> ```
> In the encoding that produced the schedule above, which atom represents a job's start time, and
> is the machine-overlap condition expressed as an integrity constraint or inside a choice rule?
> Answer in at most 40 words. If this cannot be determined from what you have, answer exactly:
> CANNOT DETERMINE.
> ```

**experiment-B-context-strip.md §3**, last paragraph — replace "1 perturbation + 1 C-probe +
1 A-probe + 1 U-probe" with "1 perturbation + 1 C-probe + 1 U-probe, plus 1 A-probe in the formal
cells only".

**experiment-B-context-strip.md §5**, measure 3 — append: "administered in the formal cells only;
the grading session therefore only ever receives (program, answer) pairs."

**experiment_B.frozen.yaml**, replace the `probes:` block's first line with:

```yaml
  per_instance: {C: 1, U: 1, A: 1}
  a_probe_cells: [form_full, form_strip_verbatim, form_strip_para]
```

**ORCHESTRATOR.md §3, P4** — append: "A-probes exist only for the formal cells; if any item sent
to the grader lacks a program, that is a bug, not an item to judge."

## A5 — The calibration band is a target, not a gate

The calibration rule allows proceeding with the closest grid point when no point meets the band;
the pilot gate then asserted band membership and would have aborted the run for a difficulty the
calibration had deliberately accepted. Difficulty outside the band costs power, which is a known
cost, not a defect. What should stop the run is a defect: too few instances surviving phase 1, or
a pilot that does not behave like the calibration that preceded it.

**experiment_B.frozen.yaml**, in `calibration:`, append:

```yaml
  band_is_a_target_not_a_gate: true
```

and in `gates.pilot:`, add:

```yaml
    min_inclusion_rate: 0.60           # instances valid in every cell, after phase 1
    max_calibration_deviation: 0.20    # |pilot phase-1 success - calibrated estimate|, per medium
```

**tests/test_preflight.py** — replace `test_pilot_phase1_success_in_band` with:

```python
@pytest.mark.skipif(GATES is None, reason="run after the pilot")
def test_pilot_inclusion_rate():
    for domain, value in GATES["inclusion_rate"].items():
        assert value >= 0.60, (
            f"{domain}: only {value:.0%} of instances are valid in every cell; the paired design "
            f"would run on too few instances")


@pytest.mark.skipif(GATES is None, reason="run after the pilot")
def test_pilot_matches_calibration():
    """A pilot that does not behave like its own calibration means something changed."""
    for medium, value in GATES["phase1_success"].items():
        expected = GATES["calibrated_phase1_success"][medium]
        assert abs(value - expected) <= 0.20, (
            f"{medium}: pilot phase-1 success {value:.2f} vs calibrated {expected:.2f}")
```

and add:

```python
def test_a_probes_are_formal_only():
    from harness import probes
    assert probes.applies_to("A") == {"form_full", "form_strip_verbatim", "form_strip_para"}
    assert probes.applies_to("C") == set(CELLS)
    assert probes.applies_to("U") == set(CELLS)


def test_decision_rules_match_the_analysis_script():
    """The frozen config and the committed analysis must not drift apart."""
    import yaml, importlib.util
    cfg = yaml.safe_load(open("config/experiment_B.frozen.yaml"))["analysis"]
    spec = importlib.util.spec_from_file_location("an", "analysis/analyze_experiment_B.py")
    an = importlib.util.module_from_spec(spec); spec.loader.exec_module(an)
    assert cfg["mei_pp"] == an.MEI_PP
    assert cfg["lambda_threshold"] == an.LAMBDA_THRESHOLD
    assert cfg["tost_margin"] == an.TOST_MARGIN
    assert cfg["bootstrap"]["reps"] == an.BOOTSTRAP_REPS
    assert cfg["bootstrap"]["seed"] == an.BOOTSTRAP_SEED
```

---

## Consequences worth stating in the paper

The confirmatory family is now three tests: the H1 interaction, the H2 position index, and the
H2 A-probe comparison. H4 is an equivalence result and is reported as such. The design can
therefore come out in four distinct ways — the artifact helps and a description does not; the
artifact helps and so does a description; nothing helps; the control probes are not flat and the
run is uninterpretable — and three of the four are publishable statements about the framework's
boundary. That is the point of fixing this before the run rather than after.
