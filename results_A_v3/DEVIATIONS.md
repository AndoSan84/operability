# Experiment A v3 — deviations

## 1. Arm-level results seen before the target (orchestrator error)

At 03:24 on 2026-09-25 the batch driver exited on "3 consecutive api_error". The orchestrator
(Claude Code) took the exit for the end of M1 and ran the committed analysis script on
`results_A_v3/results.jsonl`. M1 had not reached its target: 60 attempt-1 instances, 22 branched
(21 with both arms finished), against a target of 30. The primary statistic was therefore
computed and seen at n = 21, which spec §8a forbids before the target.

Remedy, fixed before any further call: nothing about the run changes. N stays at 30 branched
instances (cap 90 attempt-1), the run resumes and continues to the pre-registered end, and the
reported result is the one computed at that end. No decision — stopping, extending, or any
parameter — depends on the interim value. The interim output was not committed; it is not
reported as a result.

## 2. Subscription limit recorded as api_error

The three `api_error` rows of instance a065, binary arm, attempt 3 (api_try 0–2, 03:24:04–09)
are the subscription's message "You've hit your monthly spend limit … your session limit resets
6:20am", which the usage-limit detector did not recognise. They are not model calls. They stay
in the append-only file; the analysis excludes `api_error`, and the attempt is re-issued as
api_try 3. The detector now matches spend, session, weekly and monthly limits
(`harness/cli_backend.py`, tested).
