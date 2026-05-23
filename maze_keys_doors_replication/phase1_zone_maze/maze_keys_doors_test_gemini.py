#!/usr/bin/env python3
"""
Keys-and-Doors Maze Test (GEMINI VERSION)

Clone strutturale di maze_keys_doors_test.py — identico in tutto tranne:
1. Backend LLM: gemini CLI invece di claude CLI
2. Parsing risposta JSON: chiave "response" invece di "type"=="result"
3. Filename output con timestamp per non sovrascrivere run precedenti
4. Ordine difficoltà invertito (hard→medium→easy) per smoke test rapido

Three-condition comparison:
- NL: Natural language reasoning
- CODE_mental: Write algorithm, mentally trace it (no execution)
- CODE_executed: Write algorithm, executed with Python interpreter
"""

import subprocess
import json
import random
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional, Set, Dict, Any, Union
from collections import deque
import re
import tempfile
import os
from scipy import stats


# =============================================================================
# MAZE GENERATION
# =============================================================================

def generate_key_door_maze(size: int, n_keys: int, wall_density: float, seed: int) -> List[List[Any]]:
    """
    Generate maze with n_keys key-door pairs.

    Approach: maze with "rooms" connected by corridors with doors.
    Each key is in an accessible room, the corresponding door blocks access to the next room.

    Representation:
    - 0 = free cell
    - 1 = wall
    - 'a','b','c' = keys (lowercase)
    - 'A','B','C' = doors (uppercase)
    """
    random.seed(seed)

    # Initialize all as walls
    maze = [[1 for _ in range(size)] for _ in range(size)]

    key_chars = 'abcdefghij'[:n_keys]
    door_chars = 'ABCDEFGHIJ'[:n_keys]

    # Divide maze into (n_keys + 1) horizontal zones
    zone_height = size // (n_keys + 1)

    # For each zone, create a free area
    zones = []
    for z in range(n_keys + 1):
        start_row = z * zone_height
        end_row = min((z + 1) * zone_height, size)

        # Create corridor in the zone
        for r in range(start_row, end_row):
            for c in range(size):
                # Create more open area with some random walls
                if random.random() > wall_density:
                    maze[r][c] = 0

        zones.append((start_row, end_row))

    # Ensure start and end are free
    maze[0][0] = 0
    maze[size-1][size-1] = 0

    # Create connections between zones (passages with doors)
    for k in range(n_keys):
        zone_end_row = zones[k][1] - 1
        next_zone_start = zones[k + 1][0]

        # Find a column for the passage
        passage_col = random.randint(1, size - 2)

        # Ensure there's a corridor from current zone to the passage
        for c in range(min(passage_col + 1, size)):
            if maze[zone_end_row][c] == 1:
                maze[zone_end_row][c] = 0

        # The border row between zones becomes a wall with a door
        border_row = zone_end_row + 1
        if border_row < size:
            # First set everything to wall
            for c in range(size):
                maze[border_row][c] = 1
            # Then place the door
            maze[border_row][passage_col] = door_chars[k]

        # Connect the door to the next zone (cell below the door)
        if border_row + 1 < size:
            maze[border_row + 1][passage_col] = 0

        # Ensure a corridor in the next zone from the door to the right
        if next_zone_start < size:
            for c in range(passage_col, size):
                if maze[next_zone_start][c] == 1:
                    maze[next_zone_start][c] = 0

        # Place the key in the current zone (accessible before the door)
        key_placed = False
        for r in range(zones[k][0], zone_end_row + 1):
            for c in range(size):
                if maze[r][c] == 0 and (r, c) != (0, 0):
                    maze[r][c] = key_chars[k]
                    key_placed = True
                    break
            if key_placed:
                break

    # Ensure path in the first zone
    for c in range(1, size):
        if maze[0][c] == 1:
            maze[0][c] = 0
        if c < size - 1:
            break

    # Ensure path in the last zone towards end
    last_zone = zones[-1]
    for r in range(last_zone[0], size):
        maze[r][size-1] = 0

    # Connect everything better
    for z in range(len(zones) - 1):
        zone_bottom = zones[z][1] - 1
        for c in range(size):
            if maze[zone_bottom][c] == 0:
                # Try to connect upward and downward
                if zone_bottom > 0 and maze[zone_bottom - 1][c] == 1:
                    maze[zone_bottom - 1][c] = 0
                break

    # Ensure that start can reach the first key
    # and that there's a path downward
    for r in range(min(zones[0][1], size)):
        if sum(1 for c in range(size) if maze[r][c] == 0 or (isinstance(maze[r][c], str) and maze[r][c].islower())) == 0:
            maze[r][random.randint(0, size-1)] = 0

    # Verify that the maze is solvable
    solution = solve_key_door_maze(maze)

    if not solution:
        if seed < 1000000:
            return generate_key_door_maze(size, n_keys, wall_density * 0.8, seed + 7)  # Small prime increment
        return None

    # Verify that all keys are actually required
    validation = validate_solution(maze, solution)
    if len(validation["keys_collected"]) < n_keys:
        if seed < 1000000:
            return generate_key_door_maze(size, n_keys, wall_density, seed + 7)  # Small prime increment

    return maze


def find_simple_path(maze: List[List[Any]], start: Tuple[int, int], end: Tuple[int, int]) -> Optional[List[Tuple[int, int]]]:
    """Simple BFS ignoring keys/doors."""
    size = len(maze)
    visited = set()
    queue = deque([(start, [start])])

    while queue:
        pos, path = queue.popleft()
        if pos == end:
            return path
        if pos in visited:
            continue
        visited.add(pos)

        r, c = pos
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < size and 0 <= nc < size:
                cell = maze[nr][nc]
                if cell != 1 and (nr, nc) not in visited:
                    queue.append(((nr, nc), path + [(nr, nc)]))

    return None


def create_forced_path(maze: List[List[Any]], size: int):
    """Create a guaranteed path."""
    # L-shaped path
    for i in range(size):
        maze[0][i] = 0
    for i in range(size):
        maze[i][size-1] = 0


def find_key_position(maze: List[List[Any]], path: List[Tuple[int, int]],
                      start_idx: int, end_idx: int, size: int) -> Optional[Tuple[int, int]]:
    """Find position for a key near the path."""
    candidates = []

    for idx in range(start_idx, min(end_idx, len(path))):
        pr, pc = path[idx]
        # Look for free adjacent cells
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nr, nc = pr + dr, pc + dc
            if 0 <= nr < size and 0 <= nc < size:
                if maze[nr][nc] == 0 and (nr, nc) not in path:
                    candidates.append((nr, nc))

    # If there are no adjacent candidates, use a cell on the path
    if not candidates:
        for idx in range(start_idx + 1, min(end_idx, len(path) - 1)):
            pr, pc = path[idx]
            if maze[pr][pc] == 0:
                candidates.append((pr, pc))

    return random.choice(candidates) if candidates else None


def find_door_position(maze: List[List[Any]], path: List[Tuple[int, int]],
                       start_idx: int, end_idx: int) -> Optional[Tuple[int, int]]:
    """Find position for a door on the path."""
    for idx in range(start_idx, min(end_idx, len(path))):
        pr, pc = path[idx]
        if maze[pr][pc] == 0:
            return (pr, pc)
    return None


# =============================================================================
# MAZE SOLVER (Reference Solution)
# =============================================================================

def solve_key_door_maze(maze: List[List[Any]]) -> Optional[List[Tuple[int, int]]]:
    """
    BFS on state space (row, col, keys).

    Transitions:
    - Free cell (0): always allowed
    - Key ('a'-'z'): collect and add to keys
    - Door ('A'-'Z'): allowed ONLY if corresponding key in keys
    - Wall (1): never allowed
    """
    size = len(maze)
    start = (0, 0)
    end = (size - 1, size - 1)

    # State: (row, col, frozenset_of_keys)
    initial_keys = frozenset()

    # Check if start has a key
    if isinstance(maze[0][0], str) and maze[0][0].islower():
        initial_keys = frozenset([maze[0][0]])

    visited = set()
    queue = deque([(start[0], start[1], initial_keys, [start])])

    while queue:
        r, c, keys, path = queue.popleft()

        state = (r, c, keys)
        if state in visited:
            continue
        visited.add(state)

        if (r, c) == end:
            return path

        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nr, nc = r + dr, c + dc

            if not (0 <= nr < size and 0 <= nc < size):
                continue

            cell = maze[nr][nc]

            # Wall
            if cell == 1:
                continue

            new_keys = keys

            # Key
            if isinstance(cell, str) and cell.islower():
                new_keys = keys | frozenset([cell])

            # Door
            elif isinstance(cell, str) and cell.isupper():
                required_key = cell.lower()
                if required_key not in keys:
                    continue  # Cannot pass

            new_state = (nr, nc, new_keys)
            if new_state not in visited:
                queue.append((nr, nc, new_keys, path + [(nr, nc)]))

    return None


# =============================================================================
# VALIDATION
# =============================================================================

def validate_solution(maze: List[List[Any]], path: List[Tuple[int, int]]) -> Dict[str, Any]:
    """
    Simulate the path tracking keys collected.

    Checks:
    1. Each step is adjacent
    2. Does not pass through walls
    3. Does not pass through doors without key
    4. Starts at (0,0), ends at (size-1, size-1)

    Returns: {"valid": bool, "error": str, "keys_collected": set}
    """
    if not path:
        return {"valid": False, "error": "no_path", "keys_collected": set()}

    size = len(maze)
    start = (0, 0)
    end = (size - 1, size - 1)

    if path[0] != start:
        return {"valid": False, "error": "wrong_start", "keys_collected": set()}

    if path[-1] != end:
        return {"valid": False, "error": "wrong_end", "keys_collected": set()}

    keys = set()

    # Check first cell for keys
    r, c = path[0]
    cell = maze[r][c]
    if isinstance(cell, str) and cell.islower():
        keys.add(cell)

    for i, (r, c) in enumerate(path):
        # Bounds check
        if not (0 <= r < size and 0 <= c < size):
            return {"valid": False, "error": f"out_of_bounds_at_step_{i}", "keys_collected": keys}

        cell = maze[r][c]

        # Wall check
        if cell == 1:
            return {"valid": False, "error": f"wall_at_step_{i}", "keys_collected": keys}

        # Door check
        if isinstance(cell, str) and cell.isupper():
            required_key = cell.lower()
            if required_key not in keys:
                return {"valid": False, "error": f"door_{cell}_without_key_at_step_{i}", "keys_collected": keys}

        # Key collection
        if isinstance(cell, str) and cell.islower():
            keys.add(cell)

        # Adjacency check
        if i > 0:
            pr, pc = path[i - 1]
            if abs(r - pr) + abs(c - pc) != 1:
                return {"valid": False, "error": f"non_adjacent_at_step_{i}", "keys_collected": keys}

    return {"valid": True, "error": None, "keys_collected": keys}


# =============================================================================
# MAZE DISPLAY
# =============================================================================

def maze_to_ascii(maze: List[List[Any]]) -> str:
    """Convert maze to human-readable ASCII format."""
    size = len(maze)
    lines = []

    for i in range(size):
        line = ""
        for j in range(size):
            cell = maze[i][j]
            if (i, j) == (0, 0):
                line += "S"
            elif (i, j) == (size - 1, size - 1):
                line += "E"
            elif cell == 0:
                line += "."
            elif cell == 1:
                line += "#"
            else:
                line += str(cell)  # key or door
        lines.append(line)

    return "\n".join(lines)


def maze_to_python(maze: List[List[Any]]) -> str:
    """Convert maze to Python format."""
    lines = ["["]
    for row in maze:
        row_str = "    ["
        for cell in row:
            if isinstance(cell, str):
                row_str += f"'{cell}', "
            else:
                row_str += f"{cell}, "
        row_str = row_str.rstrip(", ") + "],"
        lines.append(row_str)
    lines.append("]")
    return "\n".join(lines)


# =============================================================================
# EXTRACT RESPONSES
# =============================================================================

def extract_path(response: str) -> Optional[List[Tuple[int, int]]]:
    """Extract path from response."""
    try:
        data = json.loads(response)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("type") == "result":
                    response = item.get("result", response)
                    break
    except:
        pass

    # Look for PERCORSO FINALE (Italian) or FINAL PATH (English)
    match = re.search(r'PERCORSO FINALE[:\s]*\[([^\]]+)\]', response, re.IGNORECASE)
    if match:
        coords = re.findall(r'\((\d+)\s*,\s*(\d+)\)', match.group(1))
        if coords:
            return [(int(r), int(c)) for r, c in coords]

    # Look for FINAL PATH
    match = re.search(r'FINAL PATH[:\s]*\[([^\]]+)\]', response, re.IGNORECASE)
    if match:
        coords = re.findall(r'\((\d+)\s*,\s*(\d+)\)', match.group(1))
        if coords:
            return [(int(r), int(c)) for r, c in coords]

    # Last list of coordinates
    all_lists = re.findall(r'\[([^\[\]]*\(\d+\s*,\s*\d+\)[^\[\]]*)\]', response)
    for lst in reversed(all_lists):
        coords = re.findall(r'\((\d+)\s*,\s*(\d+)\)', lst)
        if len(coords) >= 2 and '-1' not in lst:
            return [(int(r), int(c)) for r, c in coords]

    return None


def extract_code(response: str) -> Optional[str]:
    """Extract Python code from response."""
    if '\\n' in response and '\n' not in response:
        try:
            response = response.encode().decode('unicode_escape')
        except:
            pass

    blocks = re.findall(r'```python\s*(.*?)\s*```', response, re.DOTALL)
    if blocks:
        code = max(blocks, key=len)
        return code.replace('\\n', '\n').replace('\\t', '\t')
    return None


def validate_mental_trace(response: str, expected_path_length: int) -> Dict[str, Any]:
    """
    Validate if the response contains evidence of actual mental trace.

    Looks for:
    - Mentions of "Iteration" with numbers
    - Mentions of "Dequeue" or "Queue"
    - Coordinates with key states
    - Evaluation of neighbors

    Returns: {
        "has_trace": bool,
        "iteration_count": int,
        "trace_quality": "full" | "partial" | "minimal" | "none",
        "details": str
    }
    """
    # Count explicit iterations
    iteration_matches = re.findall(r'[Ii]teration\s*\d+', response)
    iteration_count = len(iteration_matches)

    # Look for queue/dequeue mentions
    queue_mentions = len(re.findall(r'[Qq]ueue|[Dd]equeue|[Ee]nqueue', response, re.IGNORECASE))

    # Look for neighbor evaluations
    neighbor_mentions = len(re.findall(r'[Nn]eighbor|[Aa]djacent|[Vv]alid move', response, re.IGNORECASE))

    # Look for key states (e.g.: "keys={a}" or "keys: {'a'}")
    key_state_mentions = len(re.findall(r'keys\s*[=:]\s*[\{\[]', response, re.IGNORECASE))

    # Look for coordinates with exploration context (e.g.: "visiting (1,2)" or "at (1,2)")
    exploration_coords = len(re.findall(r'(?:visit|at|check|eval|current|dequeue)[^\n]*\(\d+\s*,\s*\d+\)', response, re.IGNORECASE))

    # Calculate trace quality
    min_expected_iterations = max(3, expected_path_length // 3)  # At least 1/3 of the path

    if iteration_count >= min_expected_iterations and queue_mentions >= 3:
        trace_quality = "full"
        has_trace = True
    elif iteration_count >= 3 or (queue_mentions >= 2 and exploration_coords >= 5):
        trace_quality = "partial"
        has_trace = True
    elif queue_mentions >= 1 or exploration_coords >= 3 or key_state_mentions >= 2:
        trace_quality = "minimal"
        has_trace = True
    else:
        trace_quality = "none"
        has_trace = False

    return {
        "has_trace": has_trace,
        "iteration_count": iteration_count,
        "queue_mentions": queue_mentions,
        "neighbor_mentions": neighbor_mentions,
        "key_state_mentions": key_state_mentions,
        "exploration_coords": exploration_coords,
        "trace_quality": trace_quality,
        "details": f"iterations={iteration_count}, queue={queue_mentions}, neighbors={neighbor_mentions}, keys={key_state_mentions}, coords={exploration_coords}"
    }


# =============================================================================
# CODE EXECUTION
# =============================================================================

def execute_code(code: str, maze: List[List[Any]], timeout: int = 15) -> Tuple[bool, Optional[List], str]:
    """Execute code. Returns (success, path, minimal_error)."""

    if '\\n' in code:
        code = code.replace('\\n', '\n')

    size = len(maze)
    maze_repr = repr(maze)

    full_code = f'''
import sys
from collections import deque

maze = {maze_repr}

{code}

# Find and call the function
for name in ['find_path', 'find_shortest_path', 'solve_maze', 'solve', 'bfs', 'trova_percorso']:
    if name in dir():
        try:
            result = eval(f"{{name}}(maze, (0,0), ({size-1},{size-1}))")
            if result:
                print(f"PATH:{{result}}")
            else:
                print("NO_PATH_FOUND")
            sys.exit(0)
        except Exception as e:
            print(f"FUNC_ERROR:{{e}}")
            sys.exit(1)

if 'path' in dir():
    print(f"PATH:{{path}}")
elif 'percorso' in dir():
    print(f"PATH:{{percorso}}")
else:
    print("NO_FUNCTION")
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(full_code)
        temp_file = f.name

    try:
        result = subprocess.run(['python3', temp_file], capture_output=True, text=True, timeout=timeout)
        output = result.stdout.strip()

        if 'PATH:' in output:
            try:
                path_str = output.split('PATH:')[1].strip()
                path = eval(path_str)
                if isinstance(path, list):
                    return True, path, ""
            except:
                pass

        if result.returncode != 0 or 'Error' in result.stderr:
            return False, None, "execution_error"
        return False, None, "no_result"

    except subprocess.TimeoutExpired:
        return False, None, "timeout"
    except:
        return False, None, "error"
    finally:
        os.unlink(temp_file)


# =============================================================================
# GEMINI API
# =============================================================================

def call_gemini(prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
    """
    Call Gemini and return both the result text and full response for analysis.

    Gemini CLI returns JSON like: {"session_id": "...", "response": "...", "stats": {...}}
    Robust parsing: tries multiple candidate keys and a {…} fallback for noisy stdout.

    Returns: {"result": str, "full_response": str, "usage": dict, "stderr": str}
    """
    cmd = ["gemini", "-p", prompt, "--output-format", "json"]
    if model:
        cmd.extend(["--model", model])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        raw_output = result.stdout
        stderr = result.stderr

        candidate_keys = ("response", "result", "text", "output")

        # 1) prova a parsare l'intero stdout come JSON
        try:
            data = json.loads(raw_output)
            if isinstance(data, dict):
                for key in candidate_keys:
                    if key in data:
                        return {
                            "result": data[key],
                            "full_response": raw_output,
                            "usage": data.get("stats", data.get("usage", {})),
                            "stderr": stderr
                        }
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        for key in candidate_keys:
                            if key in item:
                                return {
                                    "result": item[key],
                                    "full_response": raw_output,
                                    "usage": item.get("stats", item.get("usage", {})),
                                    "stderr": stderr
                                }
        except json.JSONDecodeError:
            pass

        # 2) fallback: estrai il primo blocco {...} dal raw stdout
        s, e = raw_output.find('{'), raw_output.rfind('}')
        if s != -1 and e > s:
            try:
                data = json.loads(raw_output[s:e + 1])
                if isinstance(data, dict):
                    for key in candidate_keys:
                        if key in data:
                            return {
                                "result": data[key],
                                "full_response": raw_output,
                                "usage": data.get("stats", data.get("usage", {})),
                                "stderr": stderr
                            }
            except json.JSONDecodeError:
                pass

        return {"result": raw_output, "full_response": raw_output, "usage": {}, "stderr": stderr}
    except Exception as e:
        return {"result": f"ERROR: {e}", "full_response": "", "usage": {}, "stderr": ""}


# =============================================================================
# PROMPTS
# =============================================================================

def get_nl_prompt(maze: List[List[Any]], size: int) -> str:
    """Prompt for NL condition - uses same Python representation as other conditions."""
    maze_python = maze_to_python(maze)

    return f"""{size}x{size} maze with keys and doors.

```python
maze = {maze_python}
# 0 = free cell
# 1 = wall
# 'a','b','c' = keys (lowercase) - collect them by stepping on them
# 'A','B','C' = doors (uppercase) - require the corresponding key
# Start: (0, 0)
# End: ({size-1}, {size-1})
```

Find the path from Start to End.
IMPORTANT: You must collect the keys BEFORE you can open the corresponding doors.
For example, you need key 'a' to pass through door 'A'.

Reason step by step:
1. Analyze the maze and identify where keys and doors are located
2. Which doors block the path to End?
3. Where are the corresponding keys?
4. In what order must you collect the keys?
5. What is the complete path, cell by cell?

Answer with the path as a list of coordinates (row, column):
FINAL PATH: [(r,c), (r,c), ...]
"""


def get_code_mental_prompt(maze: List[List[Any]], size: int) -> str:
    """Prompt for CODE_mental condition - write algorithm and deduce result."""
    maze_python = maze_to_python(maze)

    return f"""{size}x{size} maze with keys and doors.

```python
maze = {maze_python}
# 0 = free cell
# 1 = wall
# 'a','b','c' = keys (lowercase)
# 'A','B','C' = doors (uppercase) - require corresponding key
```

Write a function `find_path(maze, start, end)` that:
- Uses BFS on state (row, col, keys_collected)
- Collects keys when stepping on them
- Passes through doors only with corresponding key
- Returns list of tuples [(r,c), ...]

Then, based on your algorithm's logic, tell me what path it would find from (0,0) to ({size-1},{size-1}).

FINAL PATH: [(r,c), (r,c), ...]
"""


def get_code_executed_prompt(maze: List[List[Any]], size: int) -> str:
    """Prompt for CODE_executed condition."""
    maze_python = maze_to_python(maze)

    return f"""{size}x{size} maze with keys and doors.

```python
maze = {maze_python}
# 0 = free cell
# 1 = wall
# 'a','b','c' = keys (lowercase)
# 'A','B','C' = doors (uppercase) - require corresponding key
```

Write a function `find_path(maze, start, end)` that:
- Uses BFS on state (row, col, keys_collected)
- Collects keys when stepping on them
- Passes through doors only with corresponding key
- Returns list of tuples [(r,c), ...]

Your code will be EXECUTED. Make sure that:
- The function is named `find_path`
- It accepts (maze, start, end)
- It returns a list of tuples [(r,c), ...]
- Use `from collections import deque` if needed
"""


# =============================================================================
# RUN CONDITIONS
# =============================================================================

def run_nl_condition(maze: List[List[Any]], max_attempts: int = 3, model: Optional[str] = None) -> Dict:
    """NL condition: natural language reasoning."""
    size = len(maze)
    attempts = []

    prompt = get_nl_prompt(maze, size)

    for attempt in range(max_attempts):
        print(f"      Attempt {attempt+1}/{max_attempts}...", end=" ", flush=True)

        response_data = call_gemini(prompt, model)
        response_text = response_data["result"]
        path = extract_path(response_text)
        validation = validate_solution(maze, path) if path else {"valid": False, "error": "no_path", "keys_collected": set()}

        attempts.append({
            "attempt": attempt + 1,
            "path": path,
            "valid": validation["valid"],
            "error": validation["error"],
            "keys_collected": list(validation["keys_collected"]) if validation["keys_collected"] else [],
            "reasoning": response_text  # Save full reasoning for analysis
        })

        if validation["valid"]:
            print("OK")
            return {"success": True, "attempts": attempts, "final_attempt": attempt + 1}

        print(f"FAIL ({validation['error']})")

        # Minimal feedback
        if attempt < max_attempts - 1:
            prompt = f"""WRONG. The path is not valid.

{get_nl_prompt(maze, size)}

Try again. CAREFULLY verify each step and the keys you collect.
"""

    return {"success": False, "attempts": attempts, "final_attempt": max_attempts}


def run_code_mental_condition(maze: List[List[Any]], max_attempts: int = 3, model: Optional[str] = None) -> Dict:
    """CODE_mental condition: write algorithm, mentally deduce result."""
    size = len(maze)
    attempts = []

    prompt = get_code_mental_prompt(maze, size)

    for attempt in range(max_attempts):
        print(f"      Attempt {attempt+1}/{max_attempts}...", end=" ", flush=True)

        response_data = call_gemini(prompt, model)
        response_text = response_data["result"]
        path = extract_path(response_text)
        validation = validate_solution(maze, path) if path else {"valid": False, "error": "no_path", "keys_collected": set()}

        attempts.append({
            "attempt": attempt + 1,
            "path": path,
            "valid": validation["valid"],
            "error": validation["error"],
            "keys_collected": list(validation["keys_collected"]) if validation["keys_collected"] else [],
            "reasoning": response_text  # Save full reasoning for analysis
        })

        if validation["valid"]:
            print("OK")
            return {"success": True, "attempts": attempts, "final_attempt": attempt + 1}

        print(f"FAIL ({validation['error']})")

        # Minimal feedback
        if attempt < max_attempts - 1:
            prompt = f"""WRONG. The path is not valid.

{get_code_mental_prompt(maze, size)}

Try again. Verify the logic of your algorithm.
"""

    return {"success": False, "attempts": attempts, "final_attempt": max_attempts}


def run_code_executed_condition(maze: List[List[Any]], max_attempts: int = 3, model: Optional[str] = None) -> Dict:
    """CODE_executed condition: write algorithm, executed with interpreter."""
    size = len(maze)
    attempts = []

    prompt = get_code_executed_prompt(maze, size)

    for attempt in range(max_attempts):
        print(f"      Attempt {attempt+1}/{max_attempts}...", end=" ", flush=True)

        response_data = call_gemini(prompt, model)
        response_text = response_data["result"]
        code = extract_code(response_text)

        if not code:
            attempts.append({"attempt": attempt + 1, "error": "no_code", "reasoning": response_text})
            print("FAIL (no code)")
            if attempt < max_attempts - 1:
                prompt = f"""You did not provide valid code.

{get_code_executed_prompt(maze, size)}

Write the code in a ```python ... ``` block.
"""
            continue

        success, path, error = execute_code(code, maze)

        if success and path:
            validation = validate_solution(maze, path)
            attempts.append({
                "attempt": attempt + 1,
                "path": path,
                "valid": validation["valid"],
                "error": validation["error"],
                "keys_collected": list(validation["keys_collected"]) if validation["keys_collected"] else [],
                "code": code  # Save code for analysis
            })

            if validation["valid"]:
                print("OK")
                return {"success": True, "attempts": attempts, "final_attempt": attempt + 1}
            else:
                print(f"FAIL ({validation['error']})")
                if attempt < max_attempts - 1:
                    prompt = f"""The code produced an INVALID path.

{get_code_executed_prompt(maze, size)}

Fix the BFS logic.
"""
        else:
            attempts.append({"attempt": attempt + 1, "error": error, "code": code})
            print(f"FAIL ({error})")

            if attempt < max_attempts - 1:
                prompt = f"""ERROR: the code did not produce a valid result.

{get_code_executed_prompt(maze, size)}

Fix the code.
"""

    return {"success": False, "attempts": attempts, "final_attempt": max_attempts}


# =============================================================================
# STATISTICAL ANALYSIS
# =============================================================================

def fisher_exact_test(a: int, b: int, c: int, d: int) -> Dict:
    """
    Fisher exact test for 2x2 contingency table.

    |           | Success | Failure |
    |-----------|---------|---------|
    | Condition1|    a    |    b    |
    | Condition2|    c    |    d    |
    """
    contingency = [[a, b], [c, d]]
    odds_ratio, p_value = stats.fisher_exact(contingency)

    return {
        "odds_ratio": odds_ratio,
        "p_value": p_value,
        "significant": p_value < 0.05
    }


def compute_statistics(results: Dict) -> Dict:
    """Compute comparative statistics."""
    tests = results["tests"]

    # Count successes by condition and difficulty
    counts = {
        "NL": {"easy": 0, "medium": 0, "hard": 0, "total": 0},
        "CODE_mental": {"easy": 0, "medium": 0, "hard": 0, "total": 0},
        "CODE_executed": {"easy": 0, "medium": 0, "hard": 0, "total": 0}
    }

    n_by_difficulty = {"easy": 0, "medium": 0, "hard": 0}

    for test in tests:
        diff = test["difficulty"]
        n_by_difficulty[diff] += 1

        for condition in ["NL", "CODE_mental", "CODE_executed"]:
            if test.get(condition, {}).get("success"):
                counts[condition][diff] += 1
                counts[condition]["total"] += 1

    n_total = len(tests)

    # Success rates
    summary = {}
    for condition in ["NL", "CODE_mental", "CODE_executed"]:
        summary[condition] = {
            "success": counts[condition]["total"],
            "rate": counts[condition]["total"] / n_total if n_total > 0 else 0,
            "by_difficulty": {
                diff: counts[condition][diff] / n_by_difficulty[diff] if n_by_difficulty[diff] > 0 else 0
                for diff in ["easy", "medium", "hard"]
            }
        }

    # Comparisons
    comparisons = {}

    # NL vs CODE_mental (syntax effect)
    nl_success = counts["NL"]["total"]
    nl_fail = n_total - nl_success
    cm_success = counts["CODE_mental"]["total"]
    cm_fail = n_total - cm_success
    comparisons["syntax_effect"] = {
        "comparison": "CODE_mental - NL",
        "nl_rate": nl_success / n_total if n_total > 0 else 0,
        "code_mental_rate": cm_success / n_total if n_total > 0 else 0,
        "fisher": fisher_exact_test(nl_success, nl_fail, cm_success, cm_fail)
    }

    # CODE_mental vs CODE_executed (execution effect)
    ce_success = counts["CODE_executed"]["total"]
    ce_fail = n_total - ce_success
    comparisons["execution_effect"] = {
        "comparison": "CODE_executed - CODE_mental",
        "code_mental_rate": cm_success / n_total if n_total > 0 else 0,
        "code_executed_rate": ce_success / n_total if n_total > 0 else 0,
        "fisher": fisher_exact_test(cm_success, cm_fail, ce_success, ce_fail)
    }

    return {"summary": summary, "comparisons": comparisons, "n_by_difficulty": n_by_difficulty}


# =============================================================================
# MAIN EXPERIMENT
# =============================================================================

def run_experiment(n_trials: int = 20, model: Optional[str] = None, max_attempts: int = 3):
    """Run the complete experiment."""
    output_dir = Path(__file__).parent / "results"
    output_dir.mkdir(exist_ok=True)

    print("=" * 70)
    print("KEYS-AND-DOORS MAZE TEST (GEMINI)")
    print("=" * 70)
    print(f"\nModel: {model if model else 'gemini default'}")
    print(f"Trials: {n_trials}")
    print(f"Max attempts per trial: {max_attempts}")

    # Difficulties — stesso ordine di maze_keys_doors_test.py (easy→medium→hard)
    # per garantire parità di seed e maze instances con la baseline Sonnet.
    difficulties = [
        {"name": "easy", "size": 8, "n_keys": 1, "count": 7},
        {"name": "medium", "size": 10, "n_keys": 2, "count": 7},
        {"name": "hard", "size": 12, "n_keys": 3, "count": 6}
    ]

    # Adjust counts to match n_trials
    total = sum(d["count"] for d in difficulties)
    if total != n_trials:
        ratio = n_trials / total
        for d in difficulties:
            d["count"] = max(1, int(d["count"] * ratio))
        # Adjust last to match exactly
        current_total = sum(d["count"] for d in difficulties)
        difficulties[-1]["count"] += n_trials - current_total

    print("\nDifficulties:")
    for d in difficulties:
        print(f"  {d['name']}: {d['size']}x{d['size']}, {d['n_keys']} keys, {d['count']} trials")

    # Definisci filepath prima del loop per i checkpoint incrementali
    model_name = (model or "gemini_default").replace('.', '_').replace('/', '_')
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"maze_keys_doors_{model_name}_{ts}.json"
    filepath = output_dir / filename

    results = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "config": {
            "n_trials": n_trials,
            "max_attempts": max_attempts,
            "difficulties": difficulties
        },
        "tests": []
    }

    test_id = 0

    for diff in difficulties:
        print(f"\n{'='*70}")
        print(f"DIFFICULTY: {diff['name'].upper()} ({diff['size']}x{diff['size']}, {diff['n_keys']} keys)")
        print("=" * 70)

        for i in range(diff["count"]):
            test_id += 1
            print(f"\n--- Test {test_id}/{n_trials} ({diff['name']} #{i+1}) ---")

            # Generate maze
            seed = 10000 + test_id * 1000  # Large gaps to avoid collision with retry seeds
            maze = generate_key_door_maze(diff["size"], diff["n_keys"], 0.25, seed)

            if not maze:
                print("  [Skip - generation failed]")
                continue

            solution = solve_key_door_maze(maze)
            if not solution:
                print("  [Skip - no solution]")
                continue

            # Display maze
            print(f"  Maze ({diff['size']}x{diff['size']}, {diff['n_keys']} keys):")
            ascii_maze = maze_to_ascii(maze)
            for line in ascii_maze.split("\n"):
                print(f"    {line}")
            print(f"  Reference solution length: {len(solution)}")

            test = {
                "id": test_id,
                "difficulty": diff["name"],
                "size": diff["size"],
                "n_keys": diff["n_keys"],
                "maze": maze,
                "solution_length": len(solution)
            }

            # Run all conditions
            print("\n  [NL]")
            test["NL"] = run_nl_condition(maze, max_attempts, model)

            print("\n  [CODE_mental]")
            test["CODE_mental"] = run_code_mental_condition(maze, max_attempts, model)

            print("\n  [CODE_executed]")
            test["CODE_executed"] = run_code_executed_condition(maze, max_attempts, model)

            results["tests"].append(test)

            # Summary for this test
            print(f"\n  Results: NL={'OK' if test['NL']['success'] else 'FAIL'} | "
                  f"CODE_mental={'OK' if test['CODE_mental']['success'] else 'FAIL'} | "
                  f"CODE_executed={'OK' if test['CODE_executed']['success'] else 'FAIL'}")

        # Checkpoint dopo ogni blocco di difficoltà
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n  [Checkpoint saved: {len(results['tests'])} tests → {filepath}]")

    # Compute statistics
    stats = compute_statistics(results)
    results["summary"] = stats["summary"]
    results["comparisons"] = stats["comparisons"]

    # Print summary
    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)

    print(f"\n{'Condition':<20} {'Success':>10} {'Rate':>10}")
    print("-" * 45)
    for condition in ["NL", "CODE_mental", "CODE_executed"]:
        s = stats["summary"][condition]
        print(f"{condition:<20} {s['success']:>6}/{n_trials} {s['rate']:>10.0%}")

    print("\n\nBy Difficulty:")
    print(f"{'Condition':<20} {'Easy':>10} {'Medium':>10} {'Hard':>10}")
    print("-" * 55)
    for condition in ["NL", "CODE_mental", "CODE_executed"]:
        s = stats["summary"][condition]["by_difficulty"]
        print(f"{condition:<20} {s['easy']:>10.0%} {s['medium']:>10.0%} {s['hard']:>10.0%}")

    print("\n\nStatistical Comparisons:")
    print("-" * 55)

    syntax = stats["comparisons"]["syntax_effect"]
    print(f"\nSyntax Effect (CODE_mental vs NL):")
    print(f"  NL rate: {syntax['nl_rate']:.0%}")
    print(f"  CODE_mental rate: {syntax['code_mental_rate']:.0%}")
    print(f"  Odds ratio: {syntax['fisher']['odds_ratio']:.2f}")
    print(f"  p-value: {syntax['fisher']['p_value']:.4f}")
    print(f"  Significant: {'Yes' if syntax['fisher']['significant'] else 'No'}")

    exec_effect = stats["comparisons"]["execution_effect"]
    print(f"\nExecution Effect (CODE_executed vs CODE_mental):")
    print(f"  CODE_mental rate: {exec_effect['code_mental_rate']:.0%}")
    print(f"  CODE_executed rate: {exec_effect['code_executed_rate']:.0%}")
    print(f"  Odds ratio: {exec_effect['fisher']['odds_ratio']:.2f}")
    print(f"  p-value: {exec_effect['fisher']['p_value']:.4f}")
    print(f"  Significant: {'Yes' if exec_effect['fisher']['significant'] else 'No'}")

    # Save results finali (sovrascrive l'ultimo checkpoint con summary+comparisons)
    with open(filepath, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n\nResults saved to: {filepath}")

    return results


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import sys

    n_trials = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    # model è opzionale: se non passato si usa il default del CLI gemini
    model = sys.argv[2] if len(sys.argv) > 2 else None

    run_experiment(n_trials=n_trials, model=model)
