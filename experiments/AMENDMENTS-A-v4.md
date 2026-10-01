# Experiment A, config version 4 — M2 (maze), exploratory

Committed before any v4 call.

## G1 — The decision to run M2 was taken after M1 was analysed (deviation)

Spec §3 requires the decision to run M2 and M3 to be recorded before M1 is analysed, so that it
cannot depend on M1's result. v3 excluded M2; this decision to run it was taken by the author
after reading the v3 M1 result. It is a deviation and is reported as one. Its consequence is
limited: M2 is exploratory, tests a different question (syntax versus execution on the maze, not
the feedback contrast), and its analysis is the frozen `maze_replacement` of the committed
script, unchanged.

## G2 — What M2 is, fixed now

- **Model and settings:** those of v3 — `claude-haiku-4-5-20251001`, thinking disabled, hardened
  CLI. M2 therefore speaks about the same model as the confirmatory M1.
- **Instances:** 20 mazes from the vendored phase-2 adversarial generator (12×12, 4 keys, wall
  density 0.25: its own `DIFFICULTY`), seeds 7,000,000 + 1000·i — fresh, not the published set.
- **Arms, paired on instance, one attempt each, order drawn per instance:**
  - `m2_nl` — reason in prose, answer a PATH;
  - `m2_mental` — write a BFS program and trace it mentally, without executing it, answer a PATH;
  - `m2_exec` — write a program that prints the PATH; the harness executes it (`python -I`, empty
    temporary directory, 30 s) and validates what it prints.
  Prompts are the vendored ones, verbatim (`standard` medium).
- **Scoring:** the vendored path validator. The answer parser and the program runner are new: a
  PATH counts only as a line of its own (markdown allowed), the last one wins, a PATH inside prose
  is not an answer. Outcomes: valid, invalid_path, unparsable, exec_error, plus the
  infrastructure outcomes.
- **Analysis:** the frozen script: success per arm with Wilson intervals, McNemar nl vs mental and
  mental vs executed, unadjusted, labelled exploratory. Contamination per arm is reported; in the
  mental arm the prompt itself says "do not run the code", so an answer echoing it can match the
  execution patterns, and that is stated when reading the rate.
- **Cap:** 60 calls.
