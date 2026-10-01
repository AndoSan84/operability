# Post hoc notes (added 2026-10-01)

This file is appended after the pre-registered runs. It does not modify any earlier record; the
amendment files stay as written. It records what was checked or found after the analyses
pre-registered in `AMENDMENTS-A-v1..v5.md`.

## 1. Post hoc analyses

Scripts in `analysis/posthoc/` (see its README). None was pre-registered; the paper labels them so.

- Experiment 2B (M3): repair steps (violations removed, introduced, returning) and locality of the
  model's edits (rules kept between attempts, start times kept).
- Experiment 2A (M1): locality of the edits per arm.
- Experiment 1 (M2): the CODE_mental programs executed offline: 19 of 20 return a valid path; the
  reported path coincides with the program's output in 0 of 20.

## 2. The dataset behind Table 3 of the submitted version

`AMENDMENTS-v2.md` and `AMENDMENTS-v3.md` (C5) record the 135-trial maze dataset as absent from the
machine and from the repository. It was later located on the author's machine, outside the
repository: a results file of 27 January 2026 with 45 mazes (15 per difficulty) whose numbers match
the submitted Table 3. The run used the Claude CLI alias `sonnet` (resolved version not recorded) and
up to three attempts per condition. In the CODE_mental condition, 27 of 103 attempts ended in an
API error caused by the CLI's tool calls; two trials have no model answer. Executed offline, the
CODE_mental programs return a valid path in 65 of 65 attempts; the reported path coincides with the
program's output in 2. The revised paper keeps Table 3, restated accordingly.

## 3. Gemini 2.5 Flash maze run (Table 4)

The Gemini CLI session logs of the run were mapped to its 107 attempts. In most NL and CODE_mental
sessions the model tried to use the CLI's tools (the shell was not available); in 22 sessions it
called a sub-agent; code was actually executed once, in one NL trial, which the revised paper does not
count as an NL success. An earlier 45-maze run of 3 May 2026 failed for infrastructure reasons in
most trials of every condition (no path or no code returned) and was not used.

## 4. Gemini 3 Flash (Experiment 3)

The Gemini CLI session logs show no tool call in the NL and CODE_mental conditions; in the executed
condition the shell tool was reported as not found.

## 5. Answer-parsing defect in the earlier ASP run (added 2026-10-01)

The parser of `asp_scheduling_replication/asp_scheduling_test.py` reads the first "schedule {...}" in
a response rather than the final answer; when the model writes a partial draft first, the draft is
scored. Re-validated with the original validator and the final SCHEDULE line
(`analysis/posthoc/asp_reparse.py`), the single-attempt results of that run become NL 17/30 (57%,
reported 23%) and ASP_mental 7/30 (23%, reported 13%). The 13 NL failures attributed to omitted jobs
disappear: they were drafts. The executed condition parses the solver output and is not affected
(47% at the first attempt, 97% within three). The paper does not report this run; its scheduling
results are those of Experiment 2.

## 6. Earlier maze runs: retries and reasoning settings (added 2026-10-01)

In the Claude Sonnet and Gemini 2.5 Flash maze runs each retry was a new call with the original prompt
and a pass/fail message, without the previous answer. Gemini 2.5 Flash ran with its default dynamic
thinking (the CLI session logs record reasoning tokens in 1,104 of 1,193 responses); for the Sonnet
run the setting was not recorded.
