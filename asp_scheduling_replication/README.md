# ASP Scheduling Experiment — Cross-Domain Operability Validation

This experiment tests whether the Operability pattern (demonstrated for Python in the maze experiment) replicates with a genuine KR formalism: Answer Set Programming with Clingo.

## Requirements

### System Requirements
- Python 3.9+
- [Claude Code CLI](https://github.com/anthropics/claude-code) installed and authenticated

### Python Dependencies
```bash
pip install -r requirements.txt
```

Dependencies: `clingo` (ASP solver), `scipy` (Fisher exact test)

### Claude Code CLI

Install Claude Code CLI following instructions at: https://github.com/anthropics/claude-code

Verify installation:
```bash
claude --version
```

## Running the Experiment

### Quick Test (3 trials, ~15 minutes)
```bash
python3 asp_scheduling_test.py 3 sonnet
```

### Full Experiment (30 trials, ~90 minutes)
```bash
python3 asp_scheduling_test.py 30 sonnet
```

### Custom Configuration
```bash
python3 asp_scheduling_test.py <n_trials> <model>
```

- `n_trials`: Total number of trials (divided among 2 difficulty levels: 5/6 medium, rest hard)
- `model`: Claude model to use (`sonnet`, `opus`, `haiku`)

## Output

Results are saved to `results/asp_scheduling_<model>.json` containing:
- Instance data (jobs, precedences, deadlines, reference solutions)
- Success rates by condition and difficulty
- Statistical comparisons (Fisher exact tests)
- Symbolic Bottleneck analysis (ASP error type distribution)
- Full reasoning text and ASP code for qualitative analysis

## Experimental Design

### Task: Job-Shop Scheduling with Precedence Constraints

N jobs must be scheduled on M machines. Each job has a duration and an assigned machine. Precedence constraints require certain jobs to finish before others start. No two jobs on the same machine can overlap. All jobs must complete by a deadline set to the optimal makespan (zero slack).

### Three Conditions
1. **NL**: Natural language reasoning — describe schedule in prose. **Single-shot** (1 attempt, no feedback).
2. **ASP_mental**: Write Clingo ASP rules, mentally deduce the answer set (no execution). **Single-shot** (1 attempt, no feedback).
3. **ASP_executed**: Write Clingo ASP rules, executed with Clingo solver. **Up to 3 attempts** with Clingo error feedback.

Only ASP_executed has the verification-feedback loop — this is the direct test of Operability.

### Difficulty Levels
- **Medium**: 10 jobs, 3 machines, 10 precedences (sanity check, 5 trials)
- **Hard**: 14 jobs, 4 machines, 14 precedences (main comparison, 25 trials)

### Parallel to Maze Experiment
| Scheduling | Maze |
|---|---|
| Machine availability (state tracking) | Key collection |
| Precedence constraints | Key-before-door |
| Resource contention | Wall constraints |
| Greedy failure (contention) | Detour for keys |

## File Structure

```
.
├── README.md                    # This file
├── requirements.txt             # Python dependencies (clingo, scipy)
├── asp_scheduling_test.py       # Main experiment script
└── results/                     # Output directory
    └── asp_scheduling_sonnet.json
```

## Results (30 trials with Claude Sonnet)

| Condition | Medium | Hard | Total |
|-----------|--------|------|-------|
| NL | 40% | 20% | **23%** |
| ASP_mental | 40% | 8% | **13%** |
| ASP_executed | 100% | 96% | **97%** |

### Statistical Significance

| Comparison | p-value | Significant |
|------------|---------|-------------|
| Execution Effect (ASP_executed vs ASP_mental) | **< 0.0001** | Yes |
| Syntax Effect (ASP_mental vs NL) | 0.506 | No |

### Key Findings

1. **Operability replicates with ASP** (p < 0.0001): ASP_executed (97%) massively outperforms both NL (23%) and ASP_mental (13%). The Clingo feedback loop confirms the Operability pattern across a genuine KR formalism.

2. **Syntax fallacy confirmed**: ASP_mental (13%) trends below NL (23%), though the difference is not statistically significant. Writing ASP without execution adds cognitive overhead without benefit — the formalism itself does not help unless it can be verified.

3. **Symbolic Bottleneck documented**: Only 47% of ASP code is valid on first attempt (vs. ~80% for Python in the maze experiment). 97% succeed within 3 attempts. All errors are semantic (incorrect overlap/precedence handling), not syntactic — the model can write ASP syntax but produces incomplete constraint encodings.

4. **Clean experimental design**: NL and ASP_mental are single-shot (no feedback, no retries). Only ASP_executed has the verification-feedback loop. This isolates the Operability effect from general retry benefits.
