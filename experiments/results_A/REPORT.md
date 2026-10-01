# Experiment A — run report

Facts only; interpretation belongs to the paper. Config `config/experiment_A.frozen.yaml`
(pre-registration tag `experiment-A-prereg-v1`), analysis script unmodified (sha256 recorded).

## What was run

| stage | Sonnet calls | outcome |
|---|---|---|
| calibration (5 grid points x 4, discarded instances) | 20 | eligible failures 0/4, 1/4, 0/4, 1/4, 0/4; chosen [16, 4, 16] |
| pilot (6 instances) | 8 | all gates passed; 5/6 valid at attempt 1; the one failure repaired at attempt 2 in both arms |
| M1 | 20 | 20/20 valid at attempt 1; **stop rule fired** after 20 attempt-1 instances |
| M2, M3, M4 | 0 | not run |

Model `claude-sonnet-5` on every call (init event and transcript); Claude CLI 2.1.282 throughout;
0 structural violations; 0 contaminated responses; 0 infrastructure errors; latency median about
6 s, max 10.8 s. One further smoke call on a 5-job instance, outside every module, preceded the
run.

## Results

- **Primary (H: diagnostic < binary in attempts to success): untestable** — 0 eligible branched
  instances in M1. The pre-registered outcome is "a run stopped for lack of material, reported as
  such".
- **Single-shot execute-and-check success (measure 3), M1:** 20/20 (Wilson 95% CI 84%–100%).
  Across every attempt 1 of the run (calibration, pilot, M1, all difficulties): 43/46 (93%).
- **Symbolic bottleneck (measure 6), all attempt 1:** 43 valid, 3 invalid_schedule, 0 unsat, 0
  syntax errors, 0 solver timeouts, 0 unparsable.
- The three attempt-1 failures were invalid schedules; the pilot one violated only machine-overlap
  constraints (10 overlaps). The pilot's single branched instance was repaired at attempt 2 in
  both arms.

## Deviations and notes

- `M1_STOPPED.md` (written by the runner, wording from spec §3) says "the regime is the symbolic
  bottleneck". That wording does not match what happened: there were no syntactic failures. The
  contrast lacked material because attempt 1 almost always succeeded (a ceiling), not because
  programs failed to run.
- M4 was not run: the ladder starts a module only after the preceding ones complete, and M1 ended
  on its stop rule; the M4 grid point ([18, 5, 18]) had 0/4 eligible failures in calibration.
- Instance size does not track difficulty in these data (0, 1, 0, 1, 0 failures over five
  increasing grid points).
