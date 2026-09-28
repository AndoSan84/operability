# Experiment A v5 — M3 (medium under an identical loop), run report

Confirmatory. Facts only. Spec `experiment-A-v5-M3.md`, config `config/experiment_A_v5.frozen.yaml`
(tag `experiment-A-prereg-v5`), analysis `analysis/analyze_experiment_A_v5.py` unmodified (sha256
in the config); tables in `analysis/tables.md`. Deviations in `DEVIATIONS.md`.

## What was run

- **Pilot** (discarded, 118 calls): at [18, 5, 18] NL solved 0/12 at attempt 1 (ASP 4/12), so the
  floor rule moved the run once to [16, 4, 16]; the re-pilot gave NL 1/12, ASP 4/12, contamination
  0 in both arms. Full-run timeout 180 s.
- **M3:** 200 fresh instances at [16, 4, 16], both media on every instance, 954 calls, paused once by
  the author at 97% of the subscription budget (during the pilot) and resumed after the reset.
  `claude-haiku-4-5-20251001`, thinking disabled on every row, Claude CLI 2.1.282 throughout.
  0 structural violations, 0 infrastructure errors, 0 contaminated responses. One ASP attempt 3
  ended in the 180 s timeout (a model outcome in the taxonomy, counted as a failed attempt).

## Primary

Success within three attempts, paired over 200 instances (all complete):
**ASP 78%, NL 20%**, difference **+0.59** (95% CI [+0.52, +0.67]; 90% CI [+0.53, +0.65]),
exact McNemar p < 0.0001 → pre-registered verdict **ASP advantage**.

## Secondary

- **Attempt 1:** ASP 82/200 (41%), NL 9/200 (4%); McNemar p < 0.0001.
- **Repair among doubly failed** (both media failed attempt 1, n = 113): ASP 71/113 (63%),
  NL 16/113 (14%); McNemar p < 0.0001.
- **Attempts to success:** Hodges-Lehmann (NL − ASP) +1.5 attempts, two-sided p < 0.0001.
- **Failure taxonomy, attempt 1:** ASP — 52 syntax errors, 57 overlap, 10 deadline, 1 precedence,
  1 UNSAT; NL — overlap 169, precedence 135, deadline 11 (counts of instances showing each type;
  an NL schedule usually violates several).
- **Uptake** (share of steps in which at least one flagged violation disappears): ASP 120/192
  (62%), NL 359/362 (99%). **Regression** (a repaired violation back at attempt 3, corrected
  denominator): ASP 5/32 (16%), NL 88/170 (52%).
- **Contamination:** 0/392 ASP calls, 0/562 NL calls.
