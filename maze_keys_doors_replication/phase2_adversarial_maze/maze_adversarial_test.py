#!/usr/bin/env python3
"""
Maze BFS — Hexform Syntax Experiment

Discriminates between two hypotheses about how extended-thinking models
solve BFS-style tasks:

  Weak hypothesis: the model has memorized BFS execution patterns on
    standard maze representations (Python matrices). When the medium
    is novel, the internal loop does not activate.

  Strong hypothesis: the model has a generalized interpreter. The medium
    does not matter; the model parses any syntax and executes BFS
    internally.

The test holds the computational task constant (maze with keys-and-doors)
and varies only the syntactic medium:
  - STANDARD: maze as Python matrix (familiar to all models)
  - HEXFORM: maze in an invented notation (no training-data exposure)

Prediction under weak hypothesis: HEXFORM/CODE_mental collapses,
HEXFORM/CODE_executed remains high (model can parse and execute in code).
Prediction under strong hypothesis: HEXFORM/CODE_mental remains comparable
to STANDARD/CODE_mental.

Usage:
  python3 maze_test.py 5 claude-sonnet-4-6
  python3 maze_test.py 5 gemini-3.1-pro-preview
  python3 maze_test.py 5 claude-sonnet-4-6 --media standard,hexform
"""

import subprocess
import json
import random
import re
import tempfile
import os
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional, Set, Dict, Any
from collections import deque
import sys
import argparse


# =============================================================================
# CONFIG
# =============================================================================

SEED_BASE = 5_000_000  # No collision with maze/ASP/GLYPH/circuit/sudoku/blocking
CELLS = ["nl", "code_mental", "code_executed"]
MEDIA = ["standard", "hexform"]
DIFFICULTY = {"size": 12, "n_keys": 4, "wall_density": 0.25}

DIFFICULTIES = {
    "easy":   {"size": 8,  "n_keys": 2, "wall_density": 0.25},
    "medium": {"size": 10, "n_keys": 3, "wall_density": 0.25},
    "hard":   {"size": 12, "n_keys": 4, "wall_density": 0.25},
}


# =============================================================================
# MAZE GENERATION — random layout, no zone structure
#
# Design rationale: the original zone generator (full horizontal walls +
# single-door passage) produces mazes that are analytically solvable without
# BFS: any capable model identifies the chamber structure and reasons about
# key-lock ordering directly. To force genuine graph search, we use a random
# layout where walls, keys, and doors are placed uniformly at random.
# =============================================================================

def _try_generate_maze(size: int, n_keys: int, wall_density: float, seed: int):
    """Random maze — no zones, no horizontal barriers.

    Walls placed uniformly at random. Keys and doors placed randomly anywhere
    in the open cells. The ordering of key collection is not deducible from
    the visual layout: genuine BFS is needed to find a valid path.
    """
    rng = random.Random(seed)
    maze = [[0] * size for _ in range(size)]

    key_chars = 'abcdefghij'[:n_keys]
    door_chars = 'ABCDEFGHIJ'[:n_keys]

    # Random walls (never on start or goal)
    for r in range(size):
        for c in range(size):
            if (r, c) in {(0, 0), (size - 1, size - 1)}:
                continue
            if rng.random() < wall_density:
                maze[r][c] = 1

    # Collect open cells (excluding start and goal)
    open_cells = [
        (r, c) for r in range(size) for c in range(size)
        if maze[r][c] == 0 and (r, c) not in {(0, 0), (size - 1, size - 1)}
    ]
    if len(open_cells) < 2 * n_keys:
        return None

    # Place keys and doors at random positions (no zone constraint)
    positions = rng.sample(open_cells, 2 * n_keys)
    for i, (r, c) in enumerate(positions[:n_keys]):
        maze[r][c] = key_chars[i]
    for i, (r, c) in enumerate(positions[n_keys:]):
        maze[r][c] = door_chars[i]

    return maze


# =============================================================================
# ADVERSARIAL FILTER
#
# Rejects mazes where a greedy heuristic (always go to nearest reachable key)
# produces the same key-collection order as the BFS optimum, or where the
# optimal path never backtracks. Such mazes are analytically solvable without
# genuine state-space search.
# =============================================================================

def _bfs_nav_dist(maze, n_keys, start, target, held_keys):
    """BFS distance from start to target navigating with held_keys only."""
    size = len(maze)
    door_chars = 'ABCDEFGHIJ'[:n_keys]
    queue = deque([(start, 0)])
    visited = {start}
    while queue:
        (r, c), d = queue.popleft()
        if (r, c) == target:
            return d
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < size and 0 <= nc < size):
                continue
            cell = maze[nr][nc]
            if cell == 1:
                continue
            if isinstance(cell, str) and cell in door_chars and cell.lower() not in held_keys:
                continue
            if (nr, nc) not in visited:
                visited.add((nr, nc))
                queue.append(((nr, nc), d + 1))
    return float('inf')


def _greedy_key_order(maze, n_keys):
    """Nearest-key-first greedy: always go to the closest reachable uncollected key."""
    key_chars = 'abcdefghij'[:n_keys]
    size = len(maze)
    key_pos = {maze[r][c]: (r, c)
               for r in range(size) for c in range(size)
               if isinstance(maze[r][c], str) and maze[r][c] in key_chars}
    pos, held, order = (0, 0), set(), []
    while len(order) < n_keys:
        best, best_d = None, float('inf')
        for k in key_chars:
            if k in held:
                continue
            d = _bfs_nav_dist(maze, n_keys, pos, key_pos[k], held)
            if d < best_d:
                best_d, best = d, k
        if best is None or best_d == float('inf'):
            return None  # greedy gets stuck
        order.append(best)
        held.add(best)
        pos = key_pos[best]
    return order


def _has_doorless_solution(maze, n_keys):
    """BFS treating all doors as walls. Returns True if all keys reachable and goal reachable."""
    size = len(maze)
    key_chars = set('abcdefghij'[:n_keys])
    door_chars = set('ABCDEFGHIJ'[:n_keys])
    all_keys = frozenset(key_chars)
    queue = deque([(0, 0, frozenset())])
    visited = {(0, 0, frozenset())}
    while queue:
        r, c, keys = queue.popleft()
        if (r, c) == (size - 1, size - 1) and keys == all_keys:
            return True
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if not (0 <= nr < size and 0 <= nc < size):
                continue
            cell = maze[nr][nc]
            if cell == 1:
                continue
            if isinstance(cell, str) and cell in door_chars:
                continue  # doors are walls in doorless BFS
            new_keys = keys | {cell} if isinstance(cell, str) and cell in key_chars else keys
            state = (nr, nc, new_keys)
            if state not in visited:
                visited.add(state)
                queue.append((nr, nc, new_keys))
    return False


def _is_adversarial(maze, n_keys, optimal_path):
    """True if maze requires genuine BFS — all three conditions must hold:
    1. No doorless solution: no valid path exists that collects all keys bypassing all doors.
    2. Non-greedy ordering: greedy key order differs from optimal (ordering is non-trivial).
    3. Backtracking: path moves ≥3 Manhattan steps away from goal at some point.
    """
    size = len(maze)
    key_chars = 'abcdefghij'[:n_keys]
    door_chars = 'ABCDEFGHIJ'[:n_keys]

    # Condition 1: no doorless solution exists (forces model to reason about doors)
    if _has_doorless_solution(maze, n_keys):
        return False

    # Condition 2: greedy key ordering differs from optimal
    optimal_order = []
    for r, c in optimal_path:
        cell = maze[r][c]
        if isinstance(cell, str) and cell in key_chars and cell not in optimal_order:
            optimal_order.append(cell)
    greedy_order = _greedy_key_order(maze, n_keys)
    if greedy_order is None or optimal_order == greedy_order:
        return False

    # Condition 3: path backtracks ≥3 Manhattan steps away from goal
    goal = (size - 1, size - 1)
    min_dist, max_regression = float('inf'), 0
    for r, c in optimal_path:
        d = abs(r - goal[0]) + abs(c - goal[1])
        if d < min_dist:
            min_dist = d
        max_regression = max(max_regression, d - min_dist)
    return max_regression >= 3


def solve_maze(maze, n_keys):
    """BFS solver. Returns shortest path or None."""
    size = len(maze)
    key_chars = 'abcdefghij'[:n_keys]
    door_chars = 'ABCDEFGHIJ'[:n_keys]
    target_keys = frozenset(range(n_keys))

    start = (0, 0, frozenset())
    queue = deque([(start, [(0, 0)])])
    visited = {start}

    while queue:
        (r, c, keys), path = queue.popleft()
        if (r, c) == (size-1, size-1) and keys == target_keys:
            return path
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < size and 0 <= nc < size):
                continue
            cell = maze[nr][nc]
            new_keys = keys
            if cell == 1:
                continue
            if isinstance(cell, str):
                if cell in key_chars:
                    new_keys = keys | {key_chars.index(cell)}
                elif cell in door_chars:
                    if door_chars.index(cell) not in keys:
                        continue
            state = (nr, nc, new_keys)
            if state in visited:
                continue
            visited.add(state)
            queue.append((state, path + [(nr, nc)]))
    return None


def generate_instance(seed: int) -> Optional[Dict]:
    """Generate an adversarial maze instance (requires non-greedy BFS)."""
    size = DIFFICULTY["size"]
    n_keys = DIFFICULTY["n_keys"]
    wall_density = DIFFICULTY["wall_density"]
    for offset in range(500):
        maze = _try_generate_maze(size, n_keys, wall_density, seed + offset)
        if maze is None:
            continue
        path = solve_maze(maze, n_keys)
        if path is None:
            continue
        if not _is_adversarial(maze, n_keys, path):
            continue
        key_chars = 'abcdefghij'[:n_keys]
        optimal_order = [maze[r][c] for r, c in path
                         if isinstance(maze[r][c], str) and maze[r][c] in key_chars]
        return {
            "maze": maze,
            "n_keys": n_keys,
            "size": size,
            "solution_length": len(path),
            "seed": seed,
            "optimal_key_order": optimal_order,
            "greedy_key_order": _greedy_key_order(maze, n_keys),
        }
    return None


def validate_path(maze, n_keys, path) -> Tuple[bool, str]:
    """Check that path is valid given keys-and-doors constraints."""
    size = len(maze)
    key_chars = 'abcdefghij'[:n_keys]
    door_chars = 'ABCDEFGHIJ'[:n_keys]
    target_keys = frozenset(range(n_keys))

    if not path:
        return False, "empty_path"
    if tuple(path[0]) != (0, 0):
        return False, "wrong_start"
    if tuple(path[-1]) != (size-1, size-1):
        return False, "wrong_goal"

    keys = frozenset()
    for i, (r, c) in enumerate(path):
        if not (0 <= r < size and 0 <= c < size):
            return False, f"out_of_bounds_step_{i}"
        cell = maze[r][c]
        if cell == 1:
            return False, f"wall_traversal_step_{i}"
        if isinstance(cell, str):
            if cell in key_chars:
                keys = keys | {key_chars.index(cell)}
            elif cell in door_chars:
                if door_chars.index(cell) not in keys:
                    return False, f"door_without_key_step_{i}"
        if i > 0:
            pr, pc = path[i-1]
            if abs(r - pr) + abs(c - pc) != 1:
                return False, f"non_adjacent_step_{i}"

    if keys != target_keys:
        return False, "missing_keys"
    return True, "ok"


# =============================================================================
# MEDIUM REPRESENTATIONS
# =============================================================================

def maze_to_python(maze) -> str:
    """Standard Python matrix representation (paper's format)."""
    lines = ["maze = ["]
    for row in maze:
        elements = []
        for cell in row:
            if isinstance(cell, str):
                elements.append(f"'{cell}'")
            else:
                elements.append(str(cell))
        lines.append("    [" + ", ".join(elements) + "],")
    lines.append("]")
    return "\n".join(lines)


def maze_to_hexform(maze, n_keys) -> str:
    """Invented notation, never seen in training data.

    Syntax:
      GRID <size>x<size>
      WALLS at <coords>
      KEYS:
        ~name~ at <coord>
      LOCKS:
        ^name^ at <coord> needs ~name~
      START <coord>
      GOAL <coord>
    """
    size = len(maze)
    key_chars = 'abcdefghij'[:n_keys]
    door_chars = 'ABCDEFGHIJ'[:n_keys]
    key_names = ['alpha', 'beta', 'gamma', 'delta', 'epsilon',
                 'zeta', 'eta', 'theta', 'iota', 'kappa']

    walls = []
    keys = {}
    doors = {}
    for r in range(size):
        for c in range(size):
            cell = maze[r][c]
            if cell == 1:
                walls.append(f"({r},{c})")
            elif isinstance(cell, str):
                if cell in key_chars:
                    idx = key_chars.index(cell)
                    keys[key_names[idx]] = (r, c)
                elif cell in door_chars:
                    idx = door_chars.index(cell)
                    doors[key_names[idx]] = (r, c)

    lines = [f"GRID {size}x{size}"]
    lines.append("WALLS at " + " ".join(walls))
    lines.append("KEYS:")
    for name, (r, c) in keys.items():
        lines.append(f"  ~{name}~ at ({r},{c})")
    lines.append("LOCKS:")
    for name, (r, c) in doors.items():
        lines.append(f"  ^{name}^ at ({r},{c}) needs ~{name}~")
    lines.append(f"START (0,0)")
    lines.append(f"GOAL ({size-1},{size-1})")
    return "\n".join(lines)


HEXFORM_GRAMMAR = """## Hexform Syntax Reference

Hexform is a textual notation for describing maze problems. It is not a
standard format - read carefully:

  GRID NxN              Defines an NxN grid. Coordinates are (row, col).
                        Cells not listed as WALLS, KEYS, or LOCKS are open.

  WALLS at (r,c) (r,c)...  Lists wall cells. Walls cannot be entered.

  KEYS:                 Block listing keys present in the maze. Each key
    ~name~ at (r,c)     has a unique name. Stepping onto a key cell
    ...                 collects it permanently.

  LOCKS:                Block listing locked cells. Stepping onto a lock
    ^name^ at (r,c) needs ~name~   cell is allowed ONLY if you have
    ...                 previously collected the matching key.

  START (r,c)           Starting coordinate.
  GOAL  (r,c)           Goal coordinate.

You may move one step at a time to a 4-adjacent cell (up/down/left/right).
You may not move outside the grid or onto a wall. You may step onto a lock
cell only if you have collected the matching key. You may move freely onto
any cell that is not a wall and not a lock-you-cannot-pass."""


# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

def build_prompt(instance, cell: str, medium: str) -> str:
    n_keys = instance["n_keys"]
    size = instance["size"]
    maze = instance["maze"]

    if medium == "standard":
        repr_text = maze_to_python(maze)
        format_explanation = """Maze representation:
  - 0 = open cell, 1 = wall
  - lowercase letter ('a', 'b', ...) = key
  - uppercase letter ('A', 'B', ...) = door; door 'X' requires key 'x' to pass
  - Start at (0,0), goal at ({s},{s})
  - You may move up/down/left/right one step at a time""".format(s=size-1)
    else:  # hexform
        repr_text = maze_to_hexform(maze, n_keys)
        format_explanation = HEXFORM_GRAMMAR

    key_list = ', '.join(f"'{c}'" for c in 'abcdefghij'[:n_keys])
    task_description = f"""## Task

You are given a {size}x{size} maze with {n_keys} keys ({key_list}) and {n_keys} corresponding
locked doors. You start at (0,0). You must reach ({size-1},{size-1}).

Win condition (both required):
  1. Collect ALL {n_keys} keys before stepping onto the goal cell.
  2. Respect locks: a door can only be entered if you already carry the matching key.

{format_explanation}

## Maze

{repr_text}
"""

    if cell == "nl":
        return task_description + """
## Your task

Reason step by step about the maze, then produce a path from start to goal that
collects all required keys and respects all locks.

End your response with exactly this format on its own line:
PATH: [(0,0), (r1,c1), (r2,c2), ..., ({s},{s})]
""".format(s=size-1)

    elif cell == "code_mental":
        return task_description + """
## Your task

Write a Python function that solves this maze using BFS. The function should
return the path as a list of (row, col) tuples.

Then, WITHOUT executing the code, mentally trace through your BFS to determine
what path it would produce on this specific maze. Show your reasoning.

End your response with exactly this format on its own line:
PATH: [(0,0), (r1,c1), (r2,c2), ..., ({s},{s})]

IMPORTANT: Your response MUST include a ```python ... ``` code block with your
BFS implementation. Do NOT run the code - simulate it mentally and report PATH
based on your mental trace.
""".format(s=size-1)

    elif cell == "code_executed":
        return task_description + """
## Your task

Write a Python function that solves this maze using BFS and prints the result.
The code will be executed by the grading system.

Your code MUST:
  1. Parse or hardcode the maze representation above.
  2. Run BFS to find a path from start to goal that collects all required keys.
  3. Print the path in this exact format on a single line:
     PATH: [(0,0), (r1,c1), (r2,c2), ..., ({s},{s})]

IMPORTANT: Your response MUST include a ```python ... ``` code block with code
that prints the answer in the format above. The code will be EXECUTED.
""".format(s=size-1)

    raise ValueError(f"Unknown cell: {cell}")


# =============================================================================
# MODEL CALLERS
# =============================================================================

def call_claude(prompt: str, model: str, stream_file: str = None, timeout: int = 350) -> Dict[str, Any]:
    """Call Claude with stream-json, writing chunks to stream_file for live inspection."""
    import tempfile
    if stream_file is None:
        stream_file = tempfile.mktemp(suffix='.jsonl', prefix='claude_stream_')
    cmd = ["claude", "-p", "--verbose", "--output-format", "stream-json", "--model", model, prompt]
    try:
        with open(stream_file, 'w') as sf:
            subprocess.run(cmd, stdout=sf, stderr=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        pass  # stream_file has partial output — still parse it
    except Exception as e:
        return {"result": f"ERROR: {e}", "raw": "", "stream_file": stream_file}
    # Parse stream file: accumulate text chunks, prefer final result event
    text_parts, final_result = [], None
    try:
        with open(stream_file) as sf:
            for line in sf:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("type") == "assistant":
                        for block in obj.get("message", {}).get("content", []):
                            if block.get("type") == "text":
                                text_parts.append(block["text"])
                    elif obj.get("type") == "result":
                        final_result = obj.get("result", "")
                except Exception:
                    pass
    except Exception:
        pass
    text = final_result if final_result is not None else "".join(text_parts)
    return {"result": text, "raw": text, "stream_file": stream_file}


def call_gemini(prompt: str, model: str) -> Dict[str, Any]:
    """Call Gemini via CLI using -p flag (triggers non-interactive mode)."""
    cmd = ["gemini", "-p", prompt, "--output-format", "json"]
    if model and model.lower() not in ("gemini", "gemini-default"):
        cmd.extend(["--model", model])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        raw = result.stdout
        candidate_keys = ("response", "result", "text", "output")
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                for key in candidate_keys:
                    if key in data:
                        return {"result": data[key], "raw": raw}
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        for key in candidate_keys:
                            if key in item:
                                return {"result": item[key], "raw": raw}
        except Exception:
            pass
        # Fallback: extract first {...} block
        s, e = raw.find('{'), raw.rfind('}')
        if s != -1 and e > s:
            try:
                data = json.loads(raw[s:e+1])
                for key in candidate_keys:
                    if key in data:
                        return {"result": data[key], "raw": raw}
            except Exception:
                pass
        return {"result": raw, "raw": raw}
    except Exception as ex:
        return {"result": f"ERROR: {ex}", "raw": ""}


def call_model(prompt: str, model: str) -> Dict[str, Any]:
    if model.startswith("claude") or model.startswith("sonnet") or "claude" in model.lower():
        return call_claude(prompt, model)
    return call_gemini(prompt, model)


# =============================================================================
# EXTRACTION & EXECUTION
# =============================================================================

PATH_RE = re.compile(
    r"PATH:\s*\[(.*?)\]",
    re.DOTALL,
)
COORD_RE = re.compile(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)")


def extract_path(text: str) -> Optional[List[Tuple[int, int]]]:
    matches = list(PATH_RE.finditer(text))
    if not matches:
        return None
    # Use the last PATH: marker (in case of restated answers)
    inner = matches[-1].group(1)
    coords = COORD_RE.findall(inner)
    if not coords:
        return None
    return [(int(r), int(c)) for r, c in coords]


CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def extract_code(text: str) -> Optional[str]:
    matches = CODE_BLOCK_RE.findall(text)
    if not matches:
        return None
    return max(matches, key=len)


def execute_code(code: str, timeout: int = 30) -> Tuple[str, str]:
    """Execute code in subprocess. Returns (stdout, stderr)."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        path = f.name
    try:
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT"
    except Exception as e:
        return "", str(e)
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


# =============================================================================
# TRIAL RUNNER
# =============================================================================

def _finalize(trial: Dict) -> Dict:
    """Fill path_length and path_efficiency for correct trials."""
    if trial["correct"] and trial["extracted_path"]:
        trial["path_length"] = len(trial["extracted_path"])
        if trial["optimal_length"]:
            trial["path_efficiency"] = round(
                trial["path_length"] / trial["optimal_length"], 3)
    return trial


def run_trial(instance, cell: str, medium: str, model: str) -> Dict:
    trial: Dict[str, Any] = {
        "seed": instance["seed"],
        "medium": medium,
        "cell": cell,
        "model": model,
        "correct": False,
        "error_category": None,
        "raw_response": None,
        "extracted_path": None,
        "path_length": None,
        "optimal_length": instance["solution_length"],
        "path_efficiency": None,  # path_length / optimal_length (1.0 = optimal)
        "code": None,
        "exec_stdout": None,
        "exec_stderr": None,
        "timestamp": datetime.now().isoformat(),
    }

    prompt = build_prompt(instance, cell, medium)
    response = call_model(prompt, model)
    text = response.get("result", "")
    trial["raw_response"] = text  # full response for analysis
    trial["stream_file"] = response.get("stream_file")  # path to full stream-json for inspection

    if text.startswith("ERROR:") or not text.strip():
        trial["error_category"] = "api_error"
        return _finalize(trial)

    if cell == "nl":
        path = extract_path(text)
        trial["extracted_path"] = path
        if path is None:
            trial["error_category"] = "no_path_found"
            return _finalize(trial)
        ok, err = validate_path(instance["maze"], instance["n_keys"], path)
        trial["correct"] = ok
        if not ok:
            trial["error_category"] = err
        return _finalize(trial)

    code = extract_code(text)
    trial["code"] = code[:4000] if code else None

    if cell == "code_mental":
        if code is None:
            trial["error_category"] = "no_code_block"
            return _finalize(trial)
        path = extract_path(text)
        trial["extracted_path"] = path
        if path is None:
            trial["error_category"] = "no_path_in_mental_trace"
            return _finalize(trial)
        ok, err = validate_path(instance["maze"], instance["n_keys"], path)
        trial["correct"] = ok
        if not ok:
            trial["error_category"] = err
        return _finalize(trial)

    # code_executed
    if code is None:
        trial["error_category"] = "no_code_block"
        return _finalize(trial)
    stdout, stderr = execute_code(code, timeout=30)
    trial["exec_stdout"] = stdout[:4000]
    trial["exec_stderr"] = stderr[:1000]
    if stderr and stderr.strip():
        trial["error_category"] = "runtime_error"
        return _finalize(trial)
    path = extract_path(stdout)
    trial["extracted_path"] = path
    if path is None:
        trial["error_category"] = "no_path_in_stdout"
        return _finalize(trial)
    ok, err = validate_path(instance["maze"], instance["n_keys"], path)
    trial["correct"] = ok
    if not ok:
        trial["error_category"] = err
    return _finalize(trial)


# =============================================================================
# EXPERIMENT RUNNER
# =============================================================================

def run_experiment(n_per_medium: int, model: str,
                   media: Optional[List[str]] = None,
                   cells: Optional[List[str]] = None) -> None:
    if media is None:
        media = MEDIA
    if cells is None:
        cells = CELLS

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_slug = re.sub(r'[/:\s]', '_', model)
    outdir = Path(__file__).parent / "results" / f"hexform_results_{ts}_{model_slug}"
    outdir.mkdir(parents=True, exist_ok=True)
    log_path = outdir / "trials.jsonl"
    print(f"\n=== Hexform Experiment ===")
    print(f"Model: {model}")
    print(f"Media: {media}")
    print(f"Cells: {cells}")
    print(f"Instances per medium: {n_per_medium}")
    print(f"Output: {log_path}\n")

    # Generate instances once — same instances used for both media (fair comparison)
    instances = []
    for i in range(n_per_medium):
        inst = generate_instance(SEED_BASE + i * 1000)
        if inst is None:
            print(f"WARN: could not generate instance {i}")
            continue
        instances.append(inst)
    print(f"Generated {len(instances)} valid instances\n")

    results = {}
    for medium in media:
        for cell in cells:
            key = f"{medium}/{cell}"
            results[key] = {"correct": 0, "total": 0}

    with open(log_path, "w") as f:
        for inst in instances:
            for medium in media:
                for cell in cells:
                    print(f"  seed={inst['seed']}  medium={medium}  cell={cell}", flush=True)
                    trial = run_trial(inst, cell, medium, model)
                    f.write(json.dumps(trial) + "\n")
                    f.flush()
                    key = f"{medium}/{cell}"
                    results[key]["total"] += 1
                    if trial["correct"]:
                        results[key]["correct"] += 1
                    if trial.get("path_efficiency") is not None:
                        results[key].setdefault("efficiencies", []).append(
                            trial["path_efficiency"])
                    status = "OK" if trial["correct"] else f"FAIL({trial['error_category']})"
                    print(f"    -> {status}")

    print("\n=== Summary ===")
    print(f"{'medium/cell':<30s} {'accuracy':>12s} {'efficiency':>12s}")
    print("-" * 58)
    for medium in media:
        for cell in cells:
            key = f"{medium}/{cell}"
            r = results[key]
            pct = (100.0 * r["correct"] / r["total"]) if r["total"] else 0.0
            effs = r.get("efficiencies", [])
            eff_str = f"{sum(effs)/len(effs):.2f}x" if effs else "  n/a"
            print(f"{key:<30s} {r['correct']:>4d}/{r['total']:<4d} ({pct:>5.1f}%) {eff_str:>10s}")

    # The critical comparison
    print("\n=== Critical Comparison ===")
    print("Weak hypothesis: HEXFORM/code_mental << STANDARD/code_mental")
    print("Strong hypothesis: HEXFORM/code_mental ~ STANDARD/code_mental")
    if "standard" in media and "hexform" in media and "code_mental" in cells:
        std_m = results["standard/code_mental"]
        hex_m = results["hexform/code_mental"]
        std_pct = 100.0 * std_m["correct"] / std_m["total"] if std_m["total"] else 0
        hex_pct = 100.0 * hex_m["correct"] / hex_m["total"] if hex_m["total"] else 0
        gap = std_pct - hex_pct
        print(f"  STANDARD/code_mental: {std_pct:.1f}%")
        print(f"  HEXFORM/code_mental:  {hex_pct:.1f}%")
        print(f"  Gap (std - hex):      {gap:+.1f}pp")
        if gap > 20:
            print(f"  -> Consistent with WEAK hypothesis (medium-specific patterns)")
        elif gap < -20:
            print(f"  -> Consistent with STRONG hypothesis + bonus on novel medium (unusual)")
        else:
            print(f"  -> Inconclusive: gap too small to discriminate")

    print(f"\nFull log: {log_path}")


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("n", type=int, help="Number of instances per medium")
    parser.add_argument("model", type=str, help="Model identifier")
    parser.add_argument("--media", type=str, default=None,
                        help="Comma-separated subset of media (default: standard,hexform)")
    parser.add_argument("--cells", type=str, default=None,
                        help="Comma-separated subset of cells (default: nl,code_mental,code_executed)")
    parser.add_argument("--difficulty", type=str, default=None,
                        help="Difficulty preset: easy (8x8,2keys), medium (10x10,3keys), hard (12x12,4keys)")
    args = parser.parse_args()

    if args.difficulty:
        if args.difficulty not in DIFFICULTIES:
            print(f"Unknown difficulty '{args.difficulty}'. Choose from: {list(DIFFICULTIES.keys())}")
            sys.exit(1)
        globals()["DIFFICULTY"] = DIFFICULTIES[args.difficulty]

    media = args.media.split(",") if args.media else None
    cells = args.cells.split(",") if args.cells else None

    run_experiment(args.n, args.model, media=media, cells=cells)
