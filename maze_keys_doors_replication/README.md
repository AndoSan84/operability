# Maze Keys-and-Doors Experiment

This experiment tests whether LLMs benefit from code syntax vs. code execution when solving state-tracking problems.

## Requirements

### System Requirements
- Python 3.9+
- [Claude Code CLI](https://github.com/anthropics/claude-code) installed and authenticated

### Python Dependencies
```bash
pip install -r requirements.txt
```

Only dependency: `scipy` (for Fisher exact test statistics)

### Claude Code CLI

Install Claude Code CLI following instructions at: https://github.com/anthropics/claude-code

Verify installation:
```bash
claude --version
```

Make sure you're authenticated (the CLI will prompt you on first use).

## Running the Experiment

### Quick Test (6 trials, ~10 minutes)
```bash
python3 maze_keys_doors_test.py 6 sonnet
```

### Full Experiment (45 trials, ~1 hour)
```bash
python3 maze_keys_doors_test.py 45 sonnet
```

### Custom Configuration
```bash
python3 maze_keys_doors_test.py <n_trials> <model>
```

- `n_trials`: Total number of trials (divided equally among 3 difficulty levels)
- `model`: Claude model to use (`sonnet`, `opus`, `haiku`)

## Output

Results are saved to `results/maze_keys_doors_<model>.json` containing:
- Raw test data (mazes, paths attempted, validation results)
- Success rates by condition and difficulty
- Statistical comparisons (Fisher exact tests)
- Full reasoning text for qualitative analysis

## Experimental Design

### Three Conditions
1. **NL**: Natural language reasoning
2. **CODE_mental**: Write algorithm, mentally deduce result (no execution)
3. **CODE_executed**: Write algorithm, execute with Python interpreter

### Difficulty Levels
- **Easy**: 8x8 maze, 1 key
- **Medium**: 10x10 maze, 2 keys
- **Hard**: 12x12 maze, 3 keys

See `maze_keys_explained.md` for full experimental design and interpretation.

## File Structure

```
.
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── maze_keys_doors_test.py   # Main experiment script
├── maze_keys_explained.md    # Detailed documentation
└── results/                  # Output directory
    └── maze_keys_doors_sonnet.json
```

## Expected Results

From our 45-trial experiment with Claude Sonnet:

| Condition | Easy | Medium | Hard | Total |
|-----------|------|--------|------|-------|
| NL | 87% | 93% | 33% | 71% |
| CODE_mental | 100% | 40% | 27% | 56% |
| CODE_executed | 100% | 100% | 100% | 100% |

Key finding: Code execution (not code syntax) provides the advantage.

## Citation

If you use this experiment in your research, please cite:
```
[Your paper citation here]
```

## License

[Your license here]
