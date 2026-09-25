# Experiment A, config version 2 — Haiku

Committed before any v2 call. v1 (`experiment-A-prereg-v1`, results in `results_A/`) ran to its
pre-registered stop: on Sonnet, 43 of 46 attempt-1 encodings were valid, 20/20 in M1, and the
stop rule fired with no eligible failure. The primary was untestable; that result stands and is
reported as a ceiling datum.

## E1 — What changes

- **Model:** `claude-haiku-4-5-20251001` (full dated id), for calibration, pilot and M1.
- **Files:** `config/experiment_A_v2.frozen.yaml`, instances in `instances_A_v2/`, results in
  `results_A_v2/`. Nothing in v1's files is touched.
- **Scope:** calibration, pilot, M1. M2, M3 and M4 are not run in v2; decided now, before any v2
  call, so it cannot depend on a v2 result.

Everything else is v1 unchanged: spec, decision rules, gates, stop rule, grid, seeds, prompts,
contamination patterns, and the analysis script with the same sha256.

## E2 — Why this and not a new grid

The v1 calibration showed no trend over instance size (0, 1, 0, 1, 0 eligible failures over five
increasing grid points). A job-shop encoding is generic: the same program serves 10 or 18 jobs, so
instance size does not make the encoding harder, and a harder grid would manipulate the wrong
variable. A weaker model changes the failure rate of the encoding itself. A pre-v2 smoke call on a
5-job instance, outside every module, returned an invalid schedule from Haiku, with CLI 2.1.282,
no structural violation, and a latency of 111 s (the pilot timeout of 600 s covers it; the
full-run timeout is then derived from the pilot as in C8).

## E3 — Runner changes (harness, not pre-registered components)

- `--config` selects the frozen config; results and instance directories default to the ones it
  names.
- The stop-rule message no longer asserts "symbolic bottleneck"; it reports the attempt-1
  outcome counts, which distinguish a ceiling from a bottleneck. In v1 the stop was a ceiling.
