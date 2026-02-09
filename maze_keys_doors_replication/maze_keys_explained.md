# Maze Keys-and-Doors Test: Experimental Design and Results

## Motivation

Previous maze tests using simple BFS were **too easy** - a correct BFS algorithm always works, so CODE conditions won "by default" without testing actual reasoning capabilities. We needed a task that:

1. **Requires state tracking** - not just pathfinding
2. **Has temporal dependencies** - order matters
3. **Can expose reasoning failures** - even with correct algorithm structure

## The Keys-and-Doors Maze

### Complexity Added Over Simple BFS

| Aspect | Simple BFS | Keys-and-Doors |
|--------|-----------|----------------|
| State space | O(n²) | O(n² × 2^k) |
| State representation | `(row, col)` | `(row, col, keys_collected)` |
| Constraints | Walls only | Walls + door/key dependencies |
| Planning required | Greedy works | Must reason about key order |

### Maze Representation

```python
# 0 = free cell
# 1 = wall
# 'a','b','c' = keys (lowercase) - collect by stepping on them
# 'A','B','C' = doors (uppercase) - require corresponding key to pass
```

### Example Maze (8x8, 1 key)

```
Sa.#....    S = Start (0,0)
...#..#.    E = End (7,7)
...##...    a = key
........    A = door (requires key 'a')
###A....
..#.###.
.#.#....
#.....#E
```

To solve: Must collect key 'a' at (0,1) BEFORE passing through door 'A' at (4,3).

---

## Experimental Design

### Three Conditions

| Condition | Description | What It Tests |
|-----------|-------------|---------------|
| **NL** | Reason in natural language, output path | Pure reasoning ability |
| **CODE_mental** | Write BFS algorithm, mentally deduce result | Does code structure help reasoning? |
| **CODE_executed** | Write BFS algorithm, run with Python interpreter | Does execution feedback help? |

### Key Design Decisions

1. **Same representation for all conditions** - All use Python matrix format to avoid representation confounds

2. **Simplified CODE_mental** - Just asks to write algorithm and deduce result (no forced step-by-step trace, which added unfair cognitive load)

3. **Minimal feedback on errors** - Only "SBAGLIATO" (wrong), no details about where/why

### Difficulty Levels

| Level | Size | Keys | Trials |
|-------|------|------|--------|
| Easy | 8×8 | 1 | 15 |
| Medium | 10×10 | 2 | 15 |
| Hard | 12×12 | 3 | 15 |

### Hypotheses

- **H1 (Syntax Effect)**: CODE_mental > NL if formal structure aids reasoning
- **H2 (Execution Effect)**: CODE_executed > CODE_mental if interpreter feedback helps

---

## Code Structure

### Key Functions

```python
# Maze Generation
def generate_key_door_maze(size, n_keys, wall_density, seed):
    """
    Creates maze with horizontal zones separated by doors.
    Keys placed in zone N, corresponding door blocks access to zone N+1.
    Guarantees: solvable, all keys required.
    """

# Reference Solver
def solve_key_door_maze(maze):
    """
    BFS on expanded state (row, col, frozenset_of_keys).
    Collects keys when stepping on them.
    Only passes doors if corresponding key collected.
    """

# Validation
def validate_solution(maze, path):
    """
    Simulates path step-by-step:
    - Checks adjacency
    - Checks no wall collisions
    - Checks door access (key must be collected first)
    Returns: {valid, error, keys_collected}
    """
```

### Prompts

**NL Prompt:**
```
Maze with keys and doors. [Python matrix]
Find path from Start to End.
IMPORTANT: Collect keys BEFORE opening corresponding doors.
Reason step by step...
PERCORSO FINALE: [(r,c), ...]
```

**CODE_mental Prompt:**
```
Maze with keys and doors. [Python matrix]
Write find_path(maze, start, end) using BFS with state (row, col, keys).
Then, based on your algorithm's logic, tell me what path it would find.
PERCORSO FINALE: [(r,c), ...]
```

**CODE_executed Prompt:**
```
Maze with keys and doors. [Python matrix]
Write find_path(maze, start, end) using BFS with state (row, col, keys).
Your code will be EXECUTED.
```

---

## Results (45 trials)

### Success Rates

| Condition | Easy | Medium | Hard | **Total** |
|-----------|------|--------|------|-----------|
| **NL** | 87% | 93% | 33% | **71%** |
| **CODE_mental** | 100% | 40% | 27% | **56%** |
| **CODE_executed** | 100% | 100% | 100% | **100%** |

### Statistical Analysis

**Syntax Effect (CODE_mental vs NL):**
- NL: 71%, CODE_mental: 56%
- Odds ratio: 1.97 (NL better!)
- p-value: 0.189
- **Not significant**

**Execution Effect (CODE_executed vs CODE_mental):**
- CODE_mental: 56%, CODE_executed: 100%
- p-value: < 0.0001
- **Highly significant**

---

## Key Findings

### 1. NL Outperforms CODE_mental (71% vs 56%)

**Surprising result!** Writing code doesn't help and may actually hurt performance.

Possible explanations:
- Code adds cognitive overhead without execution feedback
- NL allows flexible reasoning; code forces rigid structure
- Model may be better at prose reasoning than mental code tracing

### 2. CODE_executed Achieves 100%

The interpreter provides:
- Immediate error detection
- Correct execution of algorithm logic
- Ability to iterate on bugs

This is the **epistemic provenance** effect: externalized computation via interpreter eliminates reasoning errors.

### 3. Difficulty Scaling Works

The test successfully discriminates:
- **Easy (1 key)**: All conditions perform well
- **Medium (2 keys)**: CODE_mental drops to 40%
- **Hard (3 keys)**: Both NL (33%) and CODE_mental (27%) struggle

### 4. Common Error Types

| Error | Description | Most Common In |
|-------|-------------|----------------|
| `wall_at_step_N` | Walked into a wall | All conditions |
| `non_adjacent_at_step_N` | Skipped cells | NL, CODE_mental |
| `door_X_without_key` | Tried to pass door without key | CODE_mental |
| `no_path` | Failed to produce valid path | CODE_mental |

---

## Interpretation for the Paper

### What This Shows

1. **Code syntax alone doesn't improve reasoning** - The formal structure of code doesn't inherently help the model think better about the problem

2. **Execution is the key advantage** - When code is actually run, the interpreter acts as an "oracle" that:
   - Validates each step
   - Provides ground truth feedback
   - Enables error correction

3. **LLMs struggle with mental simulation** - Tracking state through multiple steps (keys collected, current position) is error-prone for both NL and CODE_mental

### Implications

- The benefit of "coding" for LLMs comes from **execution feedback**, not from the code representation itself
- For tasks requiring precise state tracking, LLMs benefit from external tools (interpreters, calculators)
- Natural language reasoning may be preferable to pseudo-code reasoning when execution isn't available

---

## Files

- **Test script**: `maze_keys_doors_test.py`
- **Results**: `results/maze_keys_doors_sonnet.json`
- **This document**: `maze_keys_explained.md`

## Running the Experiment

```bash
cd /home/andrea/Desktop/articolo/experiment_hallucination_ablation/experiments/H_epistemic_provenance/

# Full experiment (45 trials, ~1 hour)
python3 maze_keys_doors_test.py 45 sonnet

# Quick validation (6 trials)
python3 maze_keys_doors_test.py 6 sonnet
```
