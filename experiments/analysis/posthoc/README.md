# Post hoc analyses (not pre-registered)

Run after the pre-registered analyses, on the committed results files, and reported in the paper as
not pre-registered. Each script reads only files in this repository.

| script | what it computes | paper |
|---|---|---|
| `repair_steps.py` | Experiment 2B (M3): violations removed, introduced and returning per repair step | Table "How repair proceeds" |
| `edit_locality.py` | Experiments 2A/2B: share of the model's rules kept between attempts; start times kept | same table; "Two conditions, two effects" |
| `m2_mental_code_check.py` | Experiment 1 (M2): the CODE_mental programs executed offline; reported path vs. program output | "Correct code, different path" |

The same offline check was applied to the Claude Sonnet maze run of the original submission, whose
results file is not part of this repository (see `POSTHOC-NOTES.md`).
