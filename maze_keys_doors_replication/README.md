# Maze Keys-and-Doors Experiment

Replication package for the maze keys-and-doors task from the Operability paper.
The experiment tests whether LLMs benefit from code execution (vs. mental simulation)
when solving state-tracking problems.

Three conditions are compared across all experiments:

| Condition | Description |
|---|---|
| **NL** | Natural language reasoning only |
| **CODE_mental** | Write BFS algorithm, mentally trace it (no execution) |
| **CODE_executed** | Write BFS algorithm, execute with Python interpreter |

---

## Phase 1 — Zone Maze (original)

**Location:** `phase1_zone_maze/`

### Design

A structured maze with horizontal wall bands and a single-door passage per band.
Keys and doors follow a strict zone order (key `a` → door `A` → key `b` → ...).
The zone structure makes the maze analytically solvable via topological reasoning.

### Difficulty levels

| Level | Grid | Keys |
|---|---|---|
| Easy | 8×8 | 1 |
| Medium | 10×10 | 2 |
| Hard | 12×12 | 3 |

### Running

**Claude Sonnet (original paper):**
```bash
cd phase1_zone_maze
python3 maze_keys_doors_test.py 45 sonnet
```

**Gemini:**
```bash
cd phase1_zone_maze
python3 maze_keys_doors_test_gemini.py 20 gemini-2.5-flash
```

### Results

| Model | NL | CODE_mental | CODE_executed |
|---|---|---|---|
| Claude Sonnet 3.5 (45 trials) | 71% | 56% | 100% |
| Gemini 2.5 Flash (20 trials) | 75% | 60% | 100% |

**Execution effect (CODE_executed vs CODE_mental): p = 0.0033** (Fisher exact test).

Key finding: the zone structure allows topological shortcutting — models identify
the chamber sequence without running BFS. This motivates Phase 2.

---

## Phase 2 — Adversarial Random Maze

**Location:** `phase2_adversarial_maze/`

### Design

Keys, doors, and walls are placed uniformly at random. An adversarial filter
retains only instances where:

1. **No doorless solution exists** — every valid path must traverse at least one locked door.
2. **Greedy key ordering fails** — nearest-key-first differs from BFS-optimal.
3. **Backtracking required** — the optimal path moves ≥3 Manhattan steps away from the goal.

This eliminates topological shortcuts and forces genuine BFS reasoning.
The metric is **path efficiency** (path length / BFS-optimal length); 1.0 = optimal.

### Configuration

- Grid: 12×12, 4 keys, wall density 0.25
- 10 instances per model, seed base = 5,000,000

### Running

```bash
cd phase2_adversarial_maze
python3 maze_adversarial_test.py 10 gemini-3-flash-preview --media standard
python3 maze_adversarial_test.py 10 claude-sonnet-4-6 --media standard
```

Difficulty presets (optional):
```bash
python3 maze_adversarial_test.py 10 <model> --difficulty easy    # 8×8, 2 keys
python3 maze_adversarial_test.py 10 <model> --difficulty medium  # 10×10, 3 keys
python3 maze_adversarial_test.py 10 <model> --difficulty hard    # 12×12, 4 keys (default)
```

### Results

| Model | NL acc | NL efficiency | CODE_mental acc | CODE_executed acc | CODE_executed efficiency |
|---|---|---|---|---|---|
| Gemini 3 Flash Preview (10 trials) | 100% | 1.301x | 100% | 100% | 1.000x |
| Claude Sonnet 4.6 (10 trials) | 80% | 1.133x | 0% (timeout) | 100% | 1.000x |

**Sonnet 4.6 CODE_mental:** all 10 trials timed out (>27 min/trial, ~128K output tokens).
The full thinking trace of one trial is in `results/thinking_traces/`.

**Trace-fidelity failure (seed 5,003,000, Gemini 3 Flash):**
The model's BFS code auto-collects key `c` at (8,6) on cell entry. The mental trace
nevertheless backtracks 5 steps to "collect" `c` again — a discrepancy between the
written algorithm and the reported execution. Path: 53 steps vs. BFS-optimal 43.

---

## File Structure

```
.
├── README.md
├── requirements.txt
├── maze_keys_explained.md          # Full experimental design notes
├── maze_solver.py                  # Standalone BFS reference implementation
│
├── phase1_zone_maze/
│   ├── maze_keys_doors_test.py     # Claude experiment runner
│   ├── maze_keys_doors_test_gemini.py
│   └── results/
│       ├── claude_sonnet35_45trials.json
│       └── gemini25flash_20trials.json
│
└── phase2_adversarial_maze/
    ├── maze_adversarial_test.py    # Adversarial maze experiment runner
    └── results/
        ├── gemini3flash_10trials.jsonl
        ├── sonnet46_10trials.jsonl
        └── thinking_traces/
            └── sonnet46_code_mental_stream.jsonl
```

## Requirements

```bash
pip install -r requirements.txt
```

Requires `scipy`. For Claude experiments: [Claude Code CLI](https://github.com/anthropics/claude-code).
For Gemini experiments: [Gemini CLI](https://github.com/google-gemini/gemini-cli).

## Citation

```
[citation placeholder]
```

## License

MIT
