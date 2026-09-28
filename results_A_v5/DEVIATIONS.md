# Experiment A v5 — deviations

## 1. Four arm-level log lines seen during the run (orchestrator)

At 02:03 on 2026-09-28, checking whether the batch driver had died, the orchestrator read the last
four lines of `runner.log`, which record per-call outcomes: instance m3_004, attempts 1 and 2 of
both arms. It was a liveness check, not an analysis; no statistic was computed and nothing about
the run changed. Spec §8a forbids arm-level outcomes before the end, so it is recorded here. From
then on only call counts and process state were inspected.
