# Experiment A, config version 3 — Haiku without extended thinking

Committed before any v3 call.

## F1 — v2 was stopped by the investigator during calibration

v2 (`experiment-A-prereg-v2`) ran 13 of its 20 calibration calls, over the grid points [10,3,10]
to [16,4,16], and all 13 were valid. The run was then stopped by an explicit decision of the
author, not by a rule: the calibration had already shown the same ceiling as v1, and the calls
were diagnostically uninformative. No pilot, no M1, no arm-level outcome of v2 exists or was seen.
The partial calibration is kept in `results_A_v2/`. This stop is a deviation from the v2
protocol, which would have continued to the M1 stop rule, and is reported as such.

## F2 — Why: Haiku under the CLI was running with extended thinking

`--effort low` did not disable thinking on Haiku 4.5. v2 calls produced a median of about 8,900
output tokens for replies of about 930 characters, and took about 75 s, against about 410 tokens
and 6 s for Sonnet in v1, which worked with almost no thinking. v2 therefore did not test "a
weaker model" but "a weaker model with ~9,000 tokens of hidden reasoning per call".

The CLI (2.1.282) disables thinking through the setting `alwaysThinkingEnabled: false` ("When
false, thinking is disabled. When absent or true, thinking is enabled automatically for supported
models") and the environment variable `MAX_THINKING_TOKENS=0`. Since `--setting-sources ""`
loads no settings file, the setting is passed with `--settings`, and the variable is set in the
call's environment; both are applied. Two canary calls on a 5-job instance, outside every module:
381 and 342 output tokens, 6 s each, no structural violation, `--effort low` accepted.

## F3 — What changes in v3

- `model.thinking: disabled`, applied as above; a thinking block in a response is a structural
  violation and aborts the run.
- Instances and results in `instances_A_v3/`, `results_A_v3/`.
- Everything else is v2, and so v1: same model id, grid, seeds, prompts, gates, stop rule,
  decision rules, and analysis script (same sha256).

Consequence for the comparison with v1: v1 (Sonnet) and v3 (Haiku) now both run with essentially
no hidden reasoning, so they differ in the model and not in the thinking regime.
