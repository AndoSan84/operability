# Operability — pre-registered experiments

Pre-registered experiments for the Operability paper. Everything is under git:
the history and the tags are part of the evidence, since they show that every design, config and
analysis script was committed before the calls it governs. Read `git log --oneline` alongside this
file.

This folder contains the pre-registered experiments of the paper, run under a single protocol. The
amendment files record, in order, every decision taken during the work; they are kept as written. Analyses and findings that
came after the pre-registered ones are in `POSTHOC-NOTES.md` and `analysis/posthoc/`.

**Names used in the paper.** Experiment 1 (maze) includes module M2 (`results_A_v4/`);
Experiment 2A (interpretable feedback) is module M1 (`results_A_v3/`); Experiment 2B (the medium
under an identical loop) is module M3 (`results_A_v5/`). The context-strip design (Experiment B)
was pre-registered and not run.

## Reading order

1. `experiment-B-context-strip.md`, `ORCHESTRATOR.md` — the original plan and the harness rules
   (hardened CLI, contamination, append-only results, batches). Experiment B is closed as a
   design, **not run** (budget); its amendments `AMENDMENTS-v1..v3.md` still define the harness
   rules Experiment A inherits (C8: CLI backend, isolation, contamination; C9: status).
2. `experiment-A-feedback-ablation.md` + `AMENDMENTS-A-v1.md` (D1–D9) — Experiment A (M1, M2, M4).
3. `AMENDMENTS-A-v2.md`, `-v3.md`, `-v4.md` — why the model and thinking regime changed, and M2.
4. `experiment-A-v5-M3.md` + `AMENDMENTS-A-v5.md` — M3.
5. The `REPORT.md` and `DEVIATIONS.md` in each `results_A*/` directory.
6. `POSTHOC-NOTES.md` and `analysis/posthoc/` — analyses run after the pre-registered ones.

## Runs and results

| version (tag) | model / regime | module | result | where |
|---|---|---|---|---|
| v1 `experiment-A-prereg-v1` | Sonnet 5, effort low | M1 | **stopped, no material**: 43/46 attempt-1 encodings valid (ceiling); primary untestable | `results_A/` |
| v2 `…-v2` | Haiku 4.5, thinking on (~9k hidden tokens/call) | calibration | **stopped by the author** after 13/13 valid (same ceiling) | `results_A_v2/` |
| v3 `…-v3` | Haiku 4.5, thinking off | M1 (confirmatory) | **supported**: diagnostic vs binary, one-sided Wilcoxon p = 0.0016, HL +0.5 attempts; success within 3: 60% vs 27% | `results_A_v3/` |
| v4 `…-v4` | Haiku 4.5, thinking off | M2 (exploratory) | maze: NL 0/20, code-mental 0/20, code-executed 19/20 | `results_A_v4/` |
| v5 `…-v5` | Haiku 4.5, thinking off | M3 (confirmatory) | **ASP advantage**: success within 3, ASP 78% vs NL 20% (+0.59, 95% CI +0.52..+0.67); repair among doubly failed 63% vs 14% | `results_A_v5/` |

Deviations are recorded where they happened: `results_A_v3/DEVIATIONS.md` (an interim look at
M1 before the target; a subscription message logged as api_error; the regression denominator
corrected in v5, 3/4 → 3/9), `AMENDMENTS-A-v3.md` F1 (v2 stopped), `AMENDMENTS-A-v4.md` G1 (M2
decided after M1 was analysed), `results_A_v5/DEVIATIONS.md` (four log lines seen during M3).

## Layout

- `config/` — frozen configs, one per version; each records the sha256 of its analysis script.
- `analysis/` — `analyze_experiment_A.py` (v1–v4, frozen) and `analyze_experiment_A_v5.py` (v5);
  `analyze_experiment_B.py` (B, frozen, not run).
- `harness/` — runner (`runner_A.py`), hardened CLI backend, ASP and maze domains, prompts,
  parsers, contamination probe, fake backend for dry runs.
- `tests/` — contract and edge-case tests (see below).
- `instances*/` — frozen instance lists with their sha256 files.
- `results_A*/` — append-only `*.jsonl` (one row per model call, raw responses included),
  `prompts/` (every prompt sent, by sha256), `derived.json` (calibration, pilot gates, timeouts),
  `runner.log`, `analysis/` (tables and summary as produced), reports.
- `evidence/canary-2026-09-24/` — the CLI canary behind C8 (redacted).
- `vendor/operability/` — read-only clone of the original repository, pinned at commit
  `e7e7a05031bc7ce2dd15d5f735eefbbfaa778886`; its generators and validators are wrapped, not
  edited. Not tracked by this repository's git (see `.gitignore`); included in the archive.
- `scripts/drive_batches.sh` — the batch driver used for the runs.
- `archive/files.zip` — the original brief as first received.

## Reproducing and checking

```
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt   # clingo, scipy, pyyaml, pytest
.venv/bin/python -m pytest -q tests/ --ignore=tests/test_preflight.py    # 65 tests, no model calls
.venv/bin/python analysis/analyze_experiment_A_v5.py --results results_A_v5/results.jsonl --out /tmp/m3
```

`tests/test_preflight.py` is Experiment B's harness contract; B was never built, so it fails at
import by design. The analysis scripts can be re-run on the committed results files to regenerate
every table; the tests check that each config's recorded sha256 matches its script.

New runs need the Claude CLI logged in (subscription), Python 3.12, and
`scripts/drive_batches.sh <config> <stage> <batch-size> <progress-file>`.

## Outside this folder

- `~/.claude/settings.json` on the author's machine sets `DISABLE_AUTOUPDATER=1` (required by v5
  so the CLI stays at 2.1.282 across pauses). Every row records the CLI version actually used.
- The CLI keeps a session transcript per call under `~/.claude/projects/` on the author's machine.
  They are not included: they carry account context (e-mail, organisation id). The runner checked
  the model id in each of them during the run; the results rows hold the full responses.
