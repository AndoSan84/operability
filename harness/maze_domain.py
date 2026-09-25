"""Maze-with-keys-and-doors domain for Experiment A, module M2 (exploratory).

Generator, validator, reference solver and the three prompts (nl, code_mental, code_executed;
`standard` medium) are the vendored phase-2 adversarial maze, unchanged, so M2 re-establishes the
published contrast under the hardened protocol. The answer parser and the code runner are new:
the vendored parsers are among the components A1 excludes.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

VENDOR = (Path(__file__).resolve().parent.parent
          / "vendor/operability/maze_keys_doors_replication/phase2_adversarial_maze")
CELLS = {"m2_nl": "nl", "m2_mental": "code_mental", "m2_exec": "code_executed"}
PATH_LINE = re.compile(r"^[\s*_`>#-]*PATH[\s*_`]*:[\s*_`]*\[(.*?)\][\s*_`]*$", re.M)
COORD = re.compile(r"\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)")


def _vendor():
    if str(VENDOR) not in sys.path:
        sys.path.insert(0, str(VENDOR))
    import maze_adversarial_test
    return maze_adversarial_test


def generate(seed):
    inst = _vendor().generate_instance(seed)
    if inst is None:
        raise RuntimeError(f"no maze near seed {seed}")
    return inst


def prompt(inst, arm):
    return _vendor().build_prompt(inst, CELLS[arm], "standard")


def extract_path(text):
    """The last line of the form `PATH: [(r,c), ...]`, markdown decoration allowed; a PATH
    mentioned inside prose is not an answer. None when there is none."""
    matches = PATH_LINE.findall(text or "")
    if not matches:
        return None
    inner = matches[-1]
    if COORD.sub("", inner).replace(",", "").strip():
        return None                  # anything but numeric pairs: an echoed template, not a path
    coords = COORD.findall(inner)
    return [(int(r), int(c)) for r, c in coords] or None


def run_program(code, timeout_s=30):
    """Run a model-written program isolated (-I), in an empty temp dir. (stdout, error or None)."""
    with tempfile.TemporaryDirectory(prefix="expA-m2-") as d:
        f = Path(d) / "solution.py"
        f.write_text(code)
        try:
            p = subprocess.run([sys.executable, "-I", str(f)], capture_output=True, text=True,
                               timeout=timeout_s, cwd=d)
        except subprocess.TimeoutExpired:
            return "", f"timeout after {timeout_s} s"
    return p.stdout, (p.stderr.strip()[-500:] if p.returncode else None)


def classify(inst, arm, text):
    """valid | invalid_path | unparsable | exec_error, with the validator's reason."""
    from harness import parsers
    if arm == "m2_exec":
        code = parsers.extract_code(text, "python")
        if code is None:
            return {"outcome": "unparsable", "reason": "no python block", "artifact": None}
        stdout, err = run_program(code)
        path = extract_path(stdout)
        if path is None:
            return {"outcome": "exec_error" if err else "unparsable",
                    "reason": err or "no PATH line printed", "artifact": code}
    else:
        code = parsers.extract_code(text, "python") if arm == "m2_mental" else None
        path = extract_path(text)
        if path is None:
            return {"outcome": "unparsable", "reason": "no PATH line", "artifact": code}
    ok, reason = _vendor().validate_path(inst["maze"], inst["n_keys"], path)
    return {"outcome": "valid" if ok else "invalid_path", "reason": reason, "artifact": code,
            "path_length": len(path)}
