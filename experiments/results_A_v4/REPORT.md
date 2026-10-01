# Experiment A v4 — M2 (maze), run report

Exploratory. Facts only. Config `config/experiment_A_v4.frozen.yaml` (tag
`experiment-A-prereg-v4`); analysis script unmodified; tables in `analysis/tables.md`. The
decision to run M2 was taken after M1 v3 was analysed (AMENDMENTS-A-v4 G1).

## What was run

60 calls: 20 fresh mazes (vendored adversarial generator, 12×12, 4 keys) × three paired arms, one
attempt each, `claude-haiku-4-5-20251001` with thinking disabled, Claude CLI 2.1.282, 3 batches.
0 structural violations, 0 infrastructure errors, 0 contaminated responses. Every NL and
code-mental reply had a parsable PATH line.

## Results

| arm | valid | failures |
|---|---|---|
| NL (prose reasoning) | **0/20** (95% CI 0–16%) | 16 wall traversals, 2 non-adjacent steps, 2 doors without key |
| code-mental (BFS written, traced without execution) | **0/20** (0–16%) | 15 wall traversals, 3 non-adjacent steps, 2 doors without key |
| code-executed (program run by the harness) | **19/20** (76–99%) | 1 program crashed (exception) |

McNemar, unadjusted: NL vs code-mental p = 1.00; code-mental vs code-executed p < 0.0001.
Every valid executed path had the optimal length (median ratio to the reference solution 1.0).
Median output tokens per reply: 1,071 (NL), 1,390 (mental), 1,157 (executed).
