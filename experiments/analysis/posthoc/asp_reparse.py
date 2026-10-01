"""Post hoc: the answer-parsing defect of the earlier ASP run (submitted Table 5).

The original parser (asp_scheduling_replication/asp_scheduling_test.py, extract_schedule_from_text)
reads the FIRST "schedule {...}" in a response, which is often a partial draft written before the
final answer. This script re-validates the single-attempt NL and ASP_mental answers with the original
parser and with the final SCHEDULE line, using the original validator. Run from experiments/.
"""
import importlib.util, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "asp_scheduling_replication"
spec = importlib.util.spec_from_file_location("asp", ROOT / "asp_scheduling_test.py")
asp = importlib.util.module_from_spec(spec); spec.loader.exec_module(asp)
data = json.load(open(ROOT / "results/asp_scheduling_sonnet.json"))


def instance(test):
    inst = dict(test["instance"])
    inst["jobs"] = {int(k): v for k, v in inst["jobs"].items()}   # JSON stores the keys as strings
    return inst


def last_schedule(text):
    found = list(re.finditer(r"SCHEDULE[:\s*]*\{([^}]+)\}", text, re.I))
    if not found:
        return None
    return {int(a): int(b) for a, b in re.findall(r"(\d+)\s*:\s*(\d+)", found[-1].group(1))} or None


for cond in ("NL", "ASP_mental"):
    first = last = missing = 0
    for t in data["tests"]:
        text = t[cond]["attempts"][0].get("reasoning") or ""
        v1 = asp.validate_schedule(instance(t), asp.extract_schedule_from_text(text) or {})
        v2 = asp.validate_schedule(instance(t), last_schedule(text) or {})
        first += bool(v1["valid"]); last += bool(v2["valid"])
        missing += str(v1.get("error", "")).startswith("missing_job")
    n = len(data["tests"])
    print(f"{cond}: original parser {first}/{n}; final SCHEDULE {last}/{n}; "
          f"'missing job' failures under the original parser {missing}")
