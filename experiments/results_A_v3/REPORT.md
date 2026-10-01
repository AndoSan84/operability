# Experiment A v3 — run report

Facts only; interpretation belongs to the paper. Config `config/experiment_A_v3.frozen.yaml`
(tag `experiment-A-prereg-v3`); analysis script unmodified (sha256 recorded in the config);
tables as produced in `analysis/tables.md`. Deviations in `DEVIATIONS.md`.

## What was run

| stage | Haiku calls | outcome |
|---|---|---|
| calibration (5 grid points x 4, discarded) | 20 | eligible failures 3/4, 1/4, 1/4, 0/4, 2/4; chosen [18, 5, 18] |
| pilot (6 instances) | 6 | gates passed; no instance branched; full-run timeout 180 s |
| M1 | 193 (3 of them the uncaught limit message) | target reached: 30 branched at 86 attempt-1 instances (cap 90) |
| M2, M3, M4 | 0 | out of v3 scope |

Model `claude-haiku-4-5-20251001` with thinking disabled on every call; Claude CLI 2.1.282
throughout; 11 batches over two sessions (interrupted at 03:24 by the subscription limit, resumed
at 06:48); 0 structural violations; 0 contaminated responses; median 650 output tokens per call.

## Results (M1, confirmatory)

- **Attempt 1:** 36/86 valid (42%), 29 invalid_schedule, 1 unsat, 20 syntax_error. Eligible
  (runnable, semantically failing): 30/86 (35%).
- **Primary** (30 branched instances, both arms finished): one-sided Wilcoxon p = 0.0016;
  Hodges-Lehmann estimate of (binary − diagnostic) attempts-to-success = +0.50; 50% tied pairs.
  Decision rule (p < 0.05 and HL ≥ 0.5): **supported**. The bootstrap 95% interval of HL is
  [0.00, 1.00]; HL moves in half attempts, so the interval is coarse and, as pre-registered, does
  not enter the decision.
- **Sensitivity** (invalid_schedule only, n = 29): p = 0.0016, HL = +0.50, supported.
- **Success within three attempts:** binary 8/30 (27%, 95% CI 14–44%), diagnostic 18/30 (60%,
  42–75%); McNemar p = 0.013.
- **Uptake:** binary 28/56 steps (50%), diagnostic 31/48 (65%).
- **Regression:** binary 6/11 (55%), diagnostic 3/4 (75%); small denominators.
- **Contamination:** 0 in every arm.
