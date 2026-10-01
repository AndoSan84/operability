# Operability

Code, data and pre-registrations for the paper *Operability as Structural Grounding: Conditions for
Epistemic Appropriation in LLMs*.

The repository has two parts.

- **`experiments/`** — the pre-registered experiments. Every design, configuration, prompt set and
  analysis script was committed before the model calls it governs; each pre-registration is
  identified by a git tag (`experiment-A-prereg-v1` … `v5`, `experiment-B-design-v1`). Results are
  append-only, one row per model call with the raw response. Start from `experiments/README.md`.
- **`maze_keys_doors_replication/`** and **`asp_scheduling_replication/`** — earlier runs, made
  without pre-registration through agentic command-line interfaces. The paper reports some of them
  and describes how the interfaces affected them.

## Where each result of the paper comes from

| paper | data |
|---|---|
| Experiment 1, Claude Sonnet (Table 3) | `maze_keys_doors_replication/phase1_zone_maze/results/maze_keys_doors_sonnet.json` |
| Experiment 1, Claude Haiku 4.5 (Table 4) | `experiments/results_A_v4/` (module M2) |
| Experiment 1, Gemini 2.5 Flash (Table 5) | `maze_keys_doors_replication/phase1_zone_maze/results/gemini25flash_20trials.json` |
| Experiment 2A (Table 6) | `experiments/results_A_v3/` (module M1) |
| Experiment 2B (Tables 6–7) | `experiments/results_A_v5/` (module M3) |
| Experiment 3 (Tables 8–9, Figure 3, Box 1) | `maze_keys_doors_replication/phase2_adversarial_maze/results/` |
| Analyses not pre-registered | `experiments/analysis/posthoc/`, `experiments/POSTHOC-NOTES.md` |

Notes on the earlier runs:

- `phase1_zone_maze/results/claude_sonnet35_45trials.json` contains 3 trials despite its name; the
  45-maze Claude Sonnet run is `maze_keys_doors_sonnet.json` (27 January 2026, model requested
  through the CLI alias `sonnet`, resolved version not recorded).
- `asp_scheduling_replication/` contains an earlier scheduling run that the paper does not report;
  the scheduling results of the paper are those of Experiment 2.

## Running the pre-registered experiments

The experiments use the maze and scheduling generators and validators of this repository as a
read-only dependency, expected at `experiments/vendor/operability/` (pinned at commit `e7e7a05`).
From the repository root:

```
git worktree add experiments/vendor/operability e7e7a05
cd experiments
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q tests/ --ignore=tests/test_preflight.py
```

See `experiments/README.md` for the analyses and for re-running the model calls.
