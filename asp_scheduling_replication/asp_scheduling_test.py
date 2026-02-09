#!/usr/bin/env python3
"""
ASP Scheduling Test — Cross-Domain Validation of Operability

Three-condition comparison on job-shop scheduling:
- NL: Natural language reasoning
- ASP_mental: Write ASP rules, mentally deduce the answer set (no execution)
- ASP_executed: Write ASP rules, executed with Clingo solver

Parallels the maze keys-and-doors experiment:
- State tracking (machine availability) <-> key collection
- Precedence constraints (job ordering) <-> key-before-door
- Resource contention (machine conflicts) <-> wall constraints
- Greedy failure (contention forces non-obvious ordering) <-> detour for keys
"""

import subprocess
import json
import random
import re
import tempfile
import os
import clingo
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
from scipy import stats


# =============================================================================
# INSTANCE GENERATION
# =============================================================================

def generate_scheduling_instance(n_jobs: int, n_machines: int, n_precedences: int,
                                  seed: int) -> Optional[Dict[str, Any]]:
    """
    Generate a job-shop scheduling instance with guaranteed solution.

    Returns: {
        "jobs": {1: {"duration": d, "machine": "A"}, ...},
        "precedences": [(j1, j2), ...],
        "deadline": int,
        "reference_solution": {1: t1, 2: t2, ...}
    }
    """
    random.seed(seed)
    machine_names = [chr(ord('A') + i) for i in range(n_machines)]

    # Generate jobs with random durations and machine assignments
    jobs = {}
    for j in range(1, n_jobs + 1):
        duration = random.randint(1, 4)
        machine = machine_names[(j - 1) % n_machines]  # Round-robin base
        # Shuffle some assignments for variety
        if random.random() < 0.3 and n_machines > 1:
            machine = random.choice(machine_names)
        jobs[j] = {"duration": duration, "machine": machine}

    # Generate precedence constraints (DAG — no cycles)
    # Strategy: only allow edges from lower-numbered to higher-numbered jobs
    possible_edges = [(i, j) for i in range(1, n_jobs + 1)
                      for j in range(i + 1, n_jobs + 1)]
    random.shuffle(possible_edges)
    precedences = possible_edges[:n_precedences]

    # Find a feasible solution with generous horizon
    total_dur = sum(info["duration"] for info in jobs.values())
    lower_bound = (total_dur + n_machines - 1) // n_machines
    initial_horizon = lower_bound + n_jobs
    solution = solve_with_clingo_internal(jobs, precedences, initial_horizon)
    if not solution:
        solution = solve_with_clingo_internal(jobs, precedences, initial_horizon + n_jobs)
        if not solution:
            return None

    # Binary search for the minimum feasible deadline (optimal makespan)
    upper = max(solution[j] + jobs[j]["duration"] for j in jobs)
    lo, hi = 1, upper
    best_solution = solution
    while lo < hi:
        mid = (lo + hi) // 2
        sol = solve_with_clingo_internal(jobs, precedences, mid)
        if sol:
            hi = mid
            best_solution = sol
        else:
            lo = mid + 1
    deadline = lo
    # Final verification
    tight_solution = solve_with_clingo_internal(jobs, precedences, deadline)
    if not tight_solution:
        return None

    return {
        "jobs": jobs,
        "precedences": precedences,
        "deadline": deadline,
        "n_machines": n_machines,
        "machine_names": machine_names,
        "reference_solution": tight_solution
    }


def solve_with_clingo_internal(jobs: Dict, precedences: List[Tuple[int, int]],
                                deadline: int) -> Optional[Dict[int, int]]:
    """
    Solve scheduling instance with Clingo (feasibility only, no optimization).
    Returns {job_id: start_time} or None.
    """
    asp_program = generate_reference_asp(jobs, precedences, deadline)

    ctl = clingo.Control(["1"])  # Find 1 model, no optimization
    try:
        ctl.add("base", [], asp_program)
        ctl.ground([("base", [])])
    except RuntimeError:
        return None

    best_solution = None

    def on_model(model):
        nonlocal best_solution
        atoms = model.symbols(shown=True)
        solution = {}
        for atom in atoms:
            if atom.name == "start" and len(atom.arguments) == 2:
                job_id = atom.arguments[0].number
                start_time = atom.arguments[1].number
                solution[job_id] = start_time
        if len(solution) == len(jobs):
            best_solution = solution

    ctl.solve(on_model=on_model)
    return best_solution


def generate_reference_asp(jobs: Dict, precedences: List[Tuple[int, int]],
                            deadline: int) -> str:
    """Generate the reference ASP program for solving."""
    lines = []

    # Facts
    for j, info in jobs.items():
        lines.append(f"job({j}).")
        lines.append(f"duration({j}, {info['duration']}).")
        machine_id = ord(info['machine'].lower()) - ord('a') + 1
        lines.append(f"on_machine({j}, {machine_id}).")

    for j1, j2 in precedences:
        lines.append(f"before({j1}, {j2}).")

    lines.append(f"time(0..{deadline}).")
    lines.append(f"deadline({deadline}).")

    # Choice rule: assign exactly one start time per job
    lines.append("1 { start(J, T) : time(T) } 1 :- job(J).")

    # Precedence constraint
    lines.append(":- before(J1, J2), start(J1, T1), start(J2, T2), "
                 "duration(J1, D), T2 < T1 + D.")

    # No overlap on same machine
    lines.append(":- on_machine(J1, M), on_machine(J2, M), J1 < J2, "
                 "start(J1, T1), start(J2, T2), duration(J1, D1), duration(J2, D2), "
                 "T1 <= T2, T2 < T1 + D1.")
    lines.append(":- on_machine(J1, M), on_machine(J2, M), J1 < J2, "
                 "start(J1, T1), start(J2, T2), duration(J1, D1), duration(J2, D2), "
                 "T2 <= T1, T1 < T2 + D2.")

    # Deadline constraint
    lines.append(":- start(J, T), duration(J, D), deadline(DL), T + D > DL.")

    lines.append("#show start/2.")

    return "\n".join(lines)


# =============================================================================
# VALIDATION
# =============================================================================

def validate_schedule(instance: Dict, schedule: Dict[int, int]) -> Dict[str, Any]:
    """
    Validate a proposed schedule.

    Checks:
    1. All jobs have start times
    2. No overlap on same machine
    3. All precedence constraints satisfied
    4. All jobs complete by deadline
    """
    if not schedule:
        return {"valid": False, "error": "no_schedule"}

    jobs = instance["jobs"]
    precedences = instance["precedences"]
    deadline = instance["deadline"]

    # Check all jobs assigned
    for j in jobs:
        if j not in schedule:
            return {"valid": False, "error": f"missing_job_{j}"}

    # Check no negative start times
    for j, t in schedule.items():
        if t < 0:
            return {"valid": False, "error": f"negative_start_job_{j}"}

    # Check deadline
    for j, t in schedule.items():
        if j in jobs:
            end_time = t + jobs[j]["duration"]
            if end_time > deadline:
                return {"valid": False, "error": f"deadline_violated_job_{j}_ends_at_{end_time}_deadline_{deadline}"}

    # Check precedence constraints
    for j1, j2 in precedences:
        if j1 in schedule and j2 in schedule:
            end_j1 = schedule[j1] + jobs[j1]["duration"]
            if schedule[j2] < end_j1:
                return {"valid": False, "error": f"precedence_violated_{j1}_before_{j2}"}

    # Check no overlap on same machine
    by_machine = {}
    for j, info in jobs.items():
        m = info["machine"]
        if m not in by_machine:
            by_machine[m] = []
        by_machine[m].append((j, schedule.get(j, 0), info["duration"]))

    for m, job_list in by_machine.items():
        for i in range(len(job_list)):
            for k in range(i + 1, len(job_list)):
                j1, s1, d1 = job_list[i]
                j2, s2, d2 = job_list[k]
                # Check overlap: [s1, s1+d1) and [s2, s2+d2) must not intersect
                if s1 < s2 + d2 and s2 < s1 + d1:
                    return {"valid": False, "error": f"overlap_machine_{m}_jobs_{j1}_{j2}"}

    return {"valid": True, "error": None}


# =============================================================================
# INSTANCE DISPLAY
# =============================================================================

def instance_to_text(instance: Dict) -> str:
    """Convert instance to structured text description."""
    jobs = instance["jobs"]
    precedences = instance["precedences"]
    deadline = instance["deadline"]

    lines = [f"Jobs: {len(jobs)}"]
    lines.append(f"Machines: {', '.join(instance['machine_names'][:instance['n_machines']])}")
    lines.append("")

    for j in sorted(jobs.keys()):
        info = jobs[j]
        lines.append(f"  Job {j}: duration {info['duration']}, machine {info['machine']}")

    if precedences:
        lines.append("")
        lines.append("Precedence constraints:")
        for j1, j2 in precedences:
            lines.append(f"  Job {j1} must finish before Job {j2} starts")

    lines.append("")
    lines.append(f"Deadline: all jobs must complete by time {deadline}")

    return "\n".join(lines)


def instance_summary(instance: Dict) -> str:
    """One-line summary of instance."""
    n_jobs = len(instance["jobs"])
    n_prec = len(instance["precedences"])
    dl = instance["deadline"]
    return f"{n_jobs} jobs, {instance['n_machines']} machines, {n_prec} precedences, deadline={dl}"


# =============================================================================
# EXTRACT RESPONSES
# =============================================================================

def extract_schedule_from_text(response: str) -> Optional[Dict[int, int]]:
    """Parse schedule from NL/ASP_mental response."""
    # Look for SCHEDULE: {1: 0, 2: 3, ...}
    match = re.search(r'SCHEDULE[:\s]*\{([^}]+)\}', response, re.IGNORECASE)
    if match:
        content = match.group(1)
        schedule = {}
        # Parse key: value pairs
        pairs = re.findall(r'(\d+)\s*:\s*(\d+)', content)
        for job_str, time_str in pairs:
            schedule[int(job_str)] = int(time_str)
        if schedule:
            return schedule

    # Try alternative format: SCHEDULE: job1=t1, job2=t2
    match = re.search(r'SCHEDULE[:\s]*(.*?)(?:\n|$)', response, re.IGNORECASE)
    if match:
        content = match.group(1)
        pairs = re.findall(r'[Jj]ob\s*(\d+)\s*(?::|=|starts?\s*at)\s*(\d+)', content)
        if pairs:
            return {int(j): int(t) for j, t in pairs}

    # Look for start(J, T) format (from ASP output)
    start_atoms = re.findall(r'start\((\d+)\s*,\s*(\d+)\)', response)
    if start_atoms:
        return {int(j): int(t) for j, t in start_atoms}

    # Last resort: look for any table-like format
    # "Job 1: start at 0" or "Job 1 -> 0"
    pairs = re.findall(r'[Jj]ob\s*(\d+)[^0-9]*?(?:start|begin|time)[^0-9]*?(\d+)', response)
    if pairs:
        return {int(j): int(t) for j, t in pairs}

    return None


def extract_asp_code(response: str) -> Optional[str]:
    """Extract ASP code block from response."""
    # Try ```asp or ```clingo or ```prolog blocks first
    blocks = re.findall(r'```(?:asp|clingo|prolog|lp)\s*(.*?)\s*```', response, re.DOTALL)
    if blocks:
        return max(blocks, key=len)

    # Try generic code blocks that look like ASP
    blocks = re.findall(r'```\s*(.*?)\s*```', response, re.DOTALL)
    for block in blocks:
        # Check if it looks like ASP (has :- or #show or choice rules)
        if any(kw in block for kw in [':-', '#show', '#minimize', '#maximize', '{ ']):
            return block

    # Try to find ASP-like content without code fences
    lines = response.split('\n')
    asp_lines = []
    in_asp = False
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(kw) for kw in ['job(', 'duration(', 'on_machine(',
               'before(', 'time(', 'deadline(', '1 {', ':- ', '#show', '#minimize']):
            in_asp = True
        if in_asp and stripped and not stripped.startswith(('>', '*', '-', '#')):
            if stripped.endswith('.') or stripped.startswith((':-', '#', '%', '1 {')):
                asp_lines.append(stripped)
            elif any(kw in stripped for kw in [':-', '#show', '#minimize']):
                asp_lines.append(stripped)

    if len(asp_lines) >= 3:
        return '\n'.join(asp_lines)

    return None


def parse_clingo_output(output: str) -> Optional[Dict[int, int]]:
    """Parse Clingo output to extract schedule."""
    # Look for answer set with start/2 atoms
    start_atoms = re.findall(r'start\((\d+),(\d+)\)', output)
    if start_atoms:
        return {int(j): int(t) for j, t in start_atoms}
    return None


# =============================================================================
# ASP EXECUTION
# =============================================================================

def execute_asp_code(asp_code: str, timeout: int = 30) -> Tuple[bool, Optional[Dict[int, int]], str]:
    """
    Execute ASP code with Clingo.

    Returns: (success, schedule_or_none, feedback_message)
    - success: True if a model was found
    - schedule: {job_id: start_time} if success
    - feedback: error message or raw output for the LLM
    """
    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.lp', delete=False) as f:
        f.write(asp_code)
        temp_file = f.name

    try:
        result = subprocess.run(
            ['clingo', temp_file, '--opt-mode=optN', '1'],
            capture_output=True, text=True, timeout=timeout
        )

        output = result.stdout + result.stderr

        # Check for syntax errors
        if 'error' in output.lower() and 'SATISFIABLE' not in output:
            # Extract meaningful error
            error_lines = [l for l in output.split('\n')
                          if 'error' in l.lower() or 'warning' in l.lower()]
            error_msg = '\n'.join(error_lines[:5]) if error_lines else output[:500]
            return False, None, f"SYNTAX ERROR:\n{error_msg}"

        # Check for UNSATISFIABLE
        if 'UNSATISFIABLE' in output:
            return False, None, "UNSATISFIABLE: No valid schedule exists with these constraints. Check your encoding."

        # Check for SATISFIABLE
        if 'SATISFIABLE' in output or 'Answer' in output:
            schedule = parse_clingo_output(output)
            if schedule:
                return True, schedule, output
            else:
                return False, None, f"Model found but no start/2 atoms in output. Raw output:\n{output[:500]}"

        return False, None, f"Unexpected Clingo output:\n{output[:500]}"

    except subprocess.TimeoutExpired:
        return False, None, "TIMEOUT: Clingo did not terminate within the time limit."
    except FileNotFoundError:
        # Try with Python clingo module
        return execute_asp_code_python(asp_code)
    except Exception as e:
        return False, None, f"EXECUTION ERROR: {str(e)}"
    finally:
        os.unlink(temp_file)


def execute_asp_code_python(asp_code: str) -> Tuple[bool, Optional[Dict[int, int]], str]:
    """Fallback: execute ASP using Python clingo module."""
    try:
        ctl = clingo.Control(["--opt-mode=optN", "1"])
        ctl.add("base", [], asp_code)
        ctl.ground([("base", [])])

        best_schedule = None
        raw_atoms = None

        def on_model(model):
            nonlocal best_schedule, raw_atoms
            atoms = model.symbols(shown=True)
            raw_atoms = str(model)
            schedule = {}
            for atom in atoms:
                if atom.name == "start" and len(atom.arguments) == 2:
                    job_id = atom.arguments[0].number
                    start_time = atom.arguments[1].number
                    schedule[job_id] = start_time
            if schedule:
                best_schedule = schedule

        result = ctl.solve(on_model=on_model)

        if result.satisfiable and best_schedule:
            return True, best_schedule, f"Answer: {raw_atoms}"
        elif result.unsatisfiable:
            return False, None, "UNSATISFIABLE: No valid schedule exists with these constraints."
        else:
            return False, None, "No model found."

    except RuntimeError as e:
        error_msg = str(e)
        return False, None, f"ASP SYNTAX ERROR:\n{error_msg}"
    except Exception as e:
        return False, None, f"EXECUTION ERROR: {str(e)}"


# =============================================================================
# CLAUDE API
# =============================================================================

def call_claude(prompt: str, model: str = "sonnet") -> Dict[str, Any]:
    """Call Claude and return result."""
    cmd = ["claude", "-p", "--output-format", "json", "--model", model, prompt]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        raw_output = result.stdout

        try:
            data = json.loads(raw_output)
            if isinstance(data, dict) and data.get("type") == "result":
                return {
                    "result": data.get("result", ""),
                    "full_response": raw_output,
                    "usage": data.get("usage", {})
                }
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("type") == "result":
                        return {
                            "result": item.get("result", raw_output),
                            "full_response": raw_output,
                            "usage": item.get("usage", {})
                        }
            return {"result": raw_output, "full_response": raw_output, "usage": {}}
        except:
            return {"result": raw_output, "full_response": raw_output, "usage": {}}
    except Exception as e:
        return {"result": f"ERROR: {e}", "full_response": "", "usage": {}}


# =============================================================================
# PROMPTS
# =============================================================================

def get_nl_prompt(instance: Dict) -> str:
    """Prompt for NL condition."""
    desc = instance_to_text(instance)

    return f"""Job-shop scheduling problem.

{desc}

Find a valid schedule (start time for each job) respecting ALL constraints:
1. Each machine handles one job at a time (no overlap)
2. Precedence constraints must be satisfied (predecessor must finish before successor starts)
3. All jobs must complete by the deadline

Reason step by step:
1. Identify which jobs share machines (resource conflicts)
2. Identify precedence chains (which jobs must go first)
3. Assign start times avoiding overlaps and respecting precedences
4. Verify all jobs complete by the deadline

Answer with the schedule as a dictionary:
SCHEDULE: {{job_id: start_time, job_id: start_time, ...}}
"""


def get_asp_mental_prompt(instance: Dict) -> str:
    """Prompt for ASP_mental condition."""
    desc = instance_to_text(instance)

    return f"""Job-shop scheduling problem.

{desc}

Write a Clingo ASP program that solves this scheduling problem:
- Define facts for jobs, durations, machines, and precedences
- Use a choice rule to assign exactly one start time per job
- Add integrity constraints for: no machine overlap, precedence ordering, deadline
- Use #show start/2.

Then, based on your program's logic, deduce what answer set Clingo would produce
for this specific instance.

Answer with the schedule as a dictionary:
SCHEDULE: {{job_id: start_time, job_id: start_time, ...}}
"""


def get_asp_executed_prompt(instance: Dict) -> str:
    """Prompt for ASP_executed condition."""
    desc = instance_to_text(instance)

    return f"""Job-shop scheduling problem.

{desc}

Write a Clingo ASP program that solves this scheduling problem:
- Define facts for jobs, durations, machines, and precedences
- Use a choice rule to assign exactly one start time per job
- Add integrity constraints for: no machine overlap, precedence ordering, deadline
- Use #show start/2.

Your code will be EXECUTED with Clingo. Write it in an ```asp code block.
Make sure it is valid ASP/Clingo syntax.
"""


# =============================================================================
# RUN CONDITIONS
# =============================================================================

def run_nl_condition(instance: Dict, max_attempts: int = 1, model: str = "sonnet") -> Dict:
    """NL condition: natural language reasoning. SINGLE SHOT — no feedback, no retries."""
    prompt = get_nl_prompt(instance)

    print(f"      Attempt 1/1...", end=" ", flush=True)

    response_data = call_claude(prompt, model)
    response_text = response_data["result"]
    schedule = extract_schedule_from_text(response_text)
    validation = validate_schedule(instance, schedule) if schedule else {"valid": False, "error": "no_schedule"}

    attempt_data = {
        "attempt": 1,
        "schedule": schedule,
        "valid": validation["valid"],
        "error": validation["error"],
        "reasoning": response_text
    }

    if validation["valid"]:
        print("OK")
        return {"success": True, "attempts": [attempt_data], "final_attempt": 1}

    print(f"FAIL ({validation['error']})")
    return {"success": False, "attempts": [attempt_data], "final_attempt": 1}


def run_asp_mental_condition(instance: Dict, max_attempts: int = 1, model: str = "sonnet") -> Dict:
    """ASP_mental condition: write ASP rules, mentally deduce result. SINGLE SHOT."""
    prompt = get_asp_mental_prompt(instance)

    print(f"      Attempt 1/1...", end=" ", flush=True)

    response_data = call_claude(prompt, model)
    response_text = response_data["result"]
    schedule = extract_schedule_from_text(response_text)
    asp_code = extract_asp_code(response_text)
    validation = validate_schedule(instance, schedule) if schedule else {"valid": False, "error": "no_schedule"}

    attempt_data = {
        "attempt": 1,
        "schedule": schedule,
        "valid": validation["valid"],
        "error": validation["error"],
        "has_asp_code": asp_code is not None,
        "asp_code": asp_code,
        "reasoning": response_text
    }

    if validation["valid"]:
        print("OK")
        return {"success": True, "attempts": [attempt_data], "final_attempt": 1}

    print(f"FAIL ({validation['error']})")
    return {"success": False, "attempts": [attempt_data], "final_attempt": 1}


def run_asp_executed_condition(instance: Dict, max_attempts: int = 3, model: str = "sonnet") -> Dict:
    """ASP_executed condition: write ASP rules, executed with Clingo."""
    attempts = []
    prompt = get_asp_executed_prompt(instance)

    for attempt in range(max_attempts):
        print(f"      Attempt {attempt+1}/{max_attempts}...", end=" ", flush=True)

        response_data = call_claude(prompt, model)
        response_text = response_data["result"]
        asp_code = extract_asp_code(response_text)

        if not asp_code:
            attempts.append({
                "attempt": attempt + 1,
                "error": "no_asp_code",
                "error_type": "no_code",
                "reasoning": response_text
            })
            print("FAIL (no ASP code)")
            if attempt < max_attempts - 1:
                prompt = f"""You did not provide valid ASP code.

{get_asp_executed_prompt(instance)}

Write the ASP program in an ```asp code block.
"""
            continue

        # Execute with Clingo
        success, schedule, feedback = execute_asp_code(asp_code)

        if success and schedule:
            validation = validate_schedule(instance, schedule)
            attempts.append({
                "attempt": attempt + 1,
                "schedule": schedule,
                "valid": validation["valid"],
                "error": validation["error"],
                "error_type": None if validation["valid"] else "wrong_answer",
                "asp_code": asp_code,
                "clingo_output": feedback
            })

            if validation["valid"]:
                print("OK")
                return {"success": True, "attempts": attempts, "final_attempt": attempt + 1}
            else:
                print(f"FAIL ({validation['error']})")
                if attempt < max_attempts - 1:
                    prompt = f"""The ASP code produced an INVALID schedule. Error: {validation['error']}

Clingo output: {feedback[:300]}

{get_asp_executed_prompt(instance)}

Fix your ASP encoding.
"""
        else:
            # Classify error type
            if "SYNTAX ERROR" in feedback or "ASP SYNTAX ERROR" in feedback:
                error_type = "syntax_error"
            elif "UNSATISFIABLE" in feedback:
                error_type = "unsatisfiable"
            elif "TIMEOUT" in feedback:
                error_type = "timeout"
            else:
                error_type = "execution_error"

            attempts.append({
                "attempt": attempt + 1,
                "error": feedback[:200],
                "error_type": error_type,
                "asp_code": asp_code
            })
            print(f"FAIL ({error_type})")

            if attempt < max_attempts - 1:
                prompt = f"""ERROR executing your ASP code with Clingo:

{feedback[:400]}

{get_asp_executed_prompt(instance)}

Fix the ASP code.
"""

    return {"success": False, "attempts": attempts, "final_attempt": max_attempts}


# =============================================================================
# STATISTICAL ANALYSIS
# =============================================================================

def fisher_exact_test(a: int, b: int, c: int, d: int) -> Dict:
    """Fisher exact test for 2x2 contingency table."""
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

    # Discover difficulty levels dynamically
    diff_levels = sorted(set(test["difficulty"] for test in tests))

    counts = {cond: {d: 0 for d in diff_levels + ["total"]}
              for cond in ["NL", "ASP_mental", "ASP_executed"]}
    n_by_difficulty = {d: 0 for d in diff_levels}

    for test in tests:
        diff = test["difficulty"]
        n_by_difficulty[diff] += 1
        for condition in ["NL", "ASP_mental", "ASP_executed"]:
            if test.get(condition, {}).get("success"):
                counts[condition][diff] += 1
                counts[condition]["total"] += 1

    n_total = len(tests)

    summary = {}
    for condition in ["NL", "ASP_mental", "ASP_executed"]:
        summary[condition] = {
            "success": counts[condition]["total"],
            "rate": counts[condition]["total"] / n_total if n_total > 0 else 0,
            "by_difficulty": {
                diff: counts[condition][diff] / n_by_difficulty[diff] if n_by_difficulty[diff] > 0 else 0
                for diff in diff_levels
            }
        }

    # Comparisons
    comparisons = {}

    # NL vs ASP_mental (syntax effect)
    nl_s = counts["NL"]["total"]
    nl_f = n_total - nl_s
    am_s = counts["ASP_mental"]["total"]
    am_f = n_total - am_s
    comparisons["syntax_effect"] = {
        "comparison": "ASP_mental vs NL",
        "nl_rate": nl_s / n_total if n_total > 0 else 0,
        "asp_mental_rate": am_s / n_total if n_total > 0 else 0,
        "fisher": fisher_exact_test(nl_s, nl_f, am_s, am_f)
    }

    # ASP_mental vs ASP_executed (execution effect)
    ae_s = counts["ASP_executed"]["total"]
    ae_f = n_total - ae_s
    comparisons["execution_effect"] = {
        "comparison": "ASP_executed vs ASP_mental",
        "asp_mental_rate": am_s / n_total if n_total > 0 else 0,
        "asp_executed_rate": ae_s / n_total if n_total > 0 else 0,
        "fisher": fisher_exact_test(am_s, am_f, ae_s, ae_f)
    }

    # ASP error type analysis (Symbolic Bottleneck metrics)
    asp_error_types = {"syntax_error": 0, "unsatisfiable": 0, "wrong_answer": 0,
                       "no_code": 0, "timeout": 0, "execution_error": 0}
    asp_first_attempt_valid = 0
    asp_eventually_valid = 0
    asp_total = 0

    for test in tests:
        asp_data = test.get("ASP_executed", {})
        asp_total += 1
        if asp_data.get("success"):
            asp_eventually_valid += 1
            if asp_data.get("final_attempt") == 1:
                asp_first_attempt_valid += 1
        # Count error types from all attempts
        for att in asp_data.get("attempts", []):
            etype = att.get("error_type")
            if etype and etype in asp_error_types:
                asp_error_types[etype] += 1

    bottleneck = {
        "first_attempt_valid_rate": asp_first_attempt_valid / asp_total if asp_total > 0 else 0,
        "eventually_valid_rate": asp_eventually_valid / asp_total if asp_total > 0 else 0,
        "error_type_distribution": asp_error_types,
        "total_trials": asp_total
    }

    return {
        "summary": summary,
        "comparisons": comparisons,
        "n_by_difficulty": n_by_difficulty,
        "symbolic_bottleneck": bottleneck
    }


# =============================================================================
# MAIN EXPERIMENT
# =============================================================================

def run_experiment(n_trials: int = 20, model: str = "sonnet", max_attempts: int = 3):
    """Run the complete experiment."""
    output_dir = Path(__file__).parent / "results"
    output_dir.mkdir(exist_ok=True)

    print("=" * 70)
    print("ASP SCHEDULING TEST — Cross-Domain Operability Validation")
    print("=" * 70)
    print(f"\nModel: {model}")
    print(f"Trials: {n_trials}")
    print(f"Max attempts per trial: {max_attempts}")

    difficulties = [
        {"name": "medium", "n_jobs": 10, "n_machines": 3, "n_precedences": 10, "count": 5},
        {"name": "hard", "n_jobs": 14, "n_machines": 4, "n_precedences": 14, "count": 25}
    ]

    # Adjust counts to match n_trials
    total = sum(d["count"] for d in difficulties)
    if total != n_trials:
        ratio = n_trials / total
        for d in difficulties:
            d["count"] = max(1, int(d["count"] * ratio))
        current_total = sum(d["count"] for d in difficulties)
        difficulties[-1]["count"] += n_trials - current_total

    print("\nDifficulties:")
    for d in difficulties:
        print(f"  {d['name']}: {d['n_jobs']} jobs, {d['n_machines']} machines, "
              f"{d['n_precedences']} precedences, {d['count']} trials")

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
        print(f"DIFFICULTY: {diff['name'].upper()} "
              f"({diff['n_jobs']} jobs, {diff['n_machines']} machines, "
              f"{diff['n_precedences']} precedences)")
        print("=" * 70)

        for i in range(diff["count"]):
            test_id += 1
            print(f"\n--- Test {test_id}/{n_trials} ({diff['name']} #{i+1}) ---")

            # Generate instance
            seed = 20000 + test_id * 1000
            instance = generate_scheduling_instance(
                diff["n_jobs"], diff["n_machines"], diff["n_precedences"], seed
            )

            # Retry with different seeds if generation fails
            retry = 0
            while instance is None and retry < 20:
                retry += 1
                seed += 7
                instance = generate_scheduling_instance(
                    diff["n_jobs"], diff["n_machines"], diff["n_precedences"], seed
                )

            if not instance:
                print("  [Skip - generation failed]")
                continue

            # Display instance
            print(f"  Instance: {instance_summary(instance)}")
            ref = instance["reference_solution"]
            ref_str = ", ".join(f"J{j}@t{ref[j]}" for j in sorted(ref.keys()))
            print(f"  Reference: {ref_str}")

            test = {
                "id": test_id,
                "difficulty": diff["name"],
                "n_jobs": diff["n_jobs"],
                "n_machines": diff["n_machines"],
                "n_precedences": diff["n_precedences"],
                "instance": {
                    "jobs": {str(k): v for k, v in instance["jobs"].items()},
                    "precedences": instance["precedences"],
                    "deadline": instance["deadline"]
                },
                "reference_solution": {str(k): v for k, v in instance["reference_solution"].items()}
            }

            # Run all conditions
            # NL and ASP_mental: SINGLE SHOT (no retries, no feedback)
            # ASP_executed: up to max_attempts with Clingo feedback loop
            print("\n  [NL] (single-shot)")
            test["NL"] = run_nl_condition(instance, model=model)

            print("\n  [ASP_mental] (single-shot)")
            test["ASP_mental"] = run_asp_mental_condition(instance, model=model)

            print("\n  [ASP_executed] (up to 3 attempts)")
            test["ASP_executed"] = run_asp_executed_condition(instance, max_attempts, model)

            results["tests"].append(test)

            # Summary for this test
            print(f"\n  Results: NL={'OK' if test['NL']['success'] else 'FAIL'} | "
                  f"ASP_mental={'OK' if test['ASP_mental']['success'] else 'FAIL'} | "
                  f"ASP_executed={'OK' if test['ASP_executed']['success'] else 'FAIL'}")

    # Compute statistics
    statistics = compute_statistics(results)
    results["summary"] = statistics["summary"]
    results["comparisons"] = statistics["comparisons"]
    results["symbolic_bottleneck"] = statistics["symbolic_bottleneck"]

    # Print summary
    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)

    print(f"\n{'Condition':<20} {'Success':>10} {'Rate':>10}")
    print("-" * 45)
    for condition in ["NL", "ASP_mental", "ASP_executed"]:
        s = statistics["summary"][condition]
        print(f"{condition:<20} {s['success']:>6}/{n_trials} {s['rate']:>10.0%}")

    diff_levels = sorted(set(t["difficulty"] for t in results["tests"]))
    print("\n\nBy Difficulty:")
    header = f"{'Condition':<20}" + "".join(f" {d.capitalize():>10}" for d in diff_levels)
    print(header)
    print("-" * (20 + 11 * len(diff_levels)))
    for condition in ["NL", "ASP_mental", "ASP_executed"]:
        s = statistics["summary"][condition]["by_difficulty"]
        row = f"{condition:<20}"
        for d in diff_levels:
            row += f" {s.get(d, 0):>10.0%}"
        print(row)

    print("\n\nStatistical Comparisons:")
    print("-" * 55)

    syntax = statistics["comparisons"]["syntax_effect"]
    print(f"\nSyntax Effect (ASP_mental vs NL):")
    print(f"  NL rate: {syntax['nl_rate']:.0%}")
    print(f"  ASP_mental rate: {syntax['asp_mental_rate']:.0%}")
    print(f"  Odds ratio: {syntax['fisher']['odds_ratio']:.2f}")
    print(f"  p-value: {syntax['fisher']['p_value']:.4f}")
    print(f"  Significant: {'Yes' if syntax['fisher']['significant'] else 'No'}")

    exec_effect = statistics["comparisons"]["execution_effect"]
    print(f"\nExecution Effect (ASP_executed vs ASP_mental):")
    print(f"  ASP_mental rate: {exec_effect['asp_mental_rate']:.0%}")
    print(f"  ASP_executed rate: {exec_effect['asp_executed_rate']:.0%}")
    print(f"  Odds ratio: {exec_effect['fisher']['odds_ratio']:.2f}")
    print(f"  p-value: {exec_effect['fisher']['p_value']:.4f}")
    print(f"  Significant: {'Yes' if exec_effect['fisher']['significant'] else 'No'}")

    # Symbolic Bottleneck analysis
    bn = statistics["symbolic_bottleneck"]
    print(f"\n\nSymbolic Bottleneck Analysis:")
    print("-" * 55)
    print(f"  ASP valid on first attempt: {bn['first_attempt_valid_rate']:.0%}")
    print(f"  ASP valid within {max_attempts} attempts: {bn['eventually_valid_rate']:.0%}")
    print(f"  Error distribution:")
    for etype, count in bn["error_type_distribution"].items():
        if count > 0:
            print(f"    {etype}: {count}")

    # Save results
    filename = f"asp_scheduling_{model}.json"
    filepath = output_dir / filename
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
    model = sys.argv[2] if len(sys.argv) > 2 else "sonnet"

    run_experiment(n_trials=n_trials, model=model)
