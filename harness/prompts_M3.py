"""Experiment A v5, module M3: the same loop in two media (spec experiment-A-v5-M3.md §4).

Every call is one user message: the medium's attempt-1 prompt verbatim, then — from attempt 2 —
a blank line and the medium's retry block. Attempt 3 carries the attempt-2 object and feedback
only. FEEDBACK is the same validator text in both media whenever a schedule exists.
"""

from harness import asp_domain

NL_ATTEMPT1 = """{problem}

Produce a schedule: an integer start time for every job.
Reason in prose. Do not write code.
End your reply with exactly one line, and write nothing after it:
SCHEDULE: {{1: t1, 2: t2, ...}}"""

NL_RETRY = """Your schedule is not valid.
{feedback}
{previous}
Provide a corrected schedule. Reason in prose. Do not write code.
End your reply with exactly one line, and write nothing after it:
SCHEDULE: {{1: t1, 2: t2, ...}}"""

ASP_RETRY = """Your encoding was run with Clingo. The result is not a valid schedule.
{feedback}

Your previous encoding:
{artifact}

Return a corrected program, as exactly one ```clingo code block and nothing else."""

NL_UNPARSABLE = "No schedule could be read from your reply; the final line must be `SCHEDULE: {...}`."
UNSAT = ("Clingo found no answer set, although the instance admits a valid schedule: some "
         "constraint in your encoding is stronger than the specification.")
ASP_UNPARSABLE = "Your reply contained no clingo code block."
TRUNCATE = 1500


def attempt1(inst, arm):
    if arm == "m3_nl":
        return NL_ATTEMPT1.format(problem=asp_domain.problem_block(inst))
    return asp_domain.attempt1_prompt(inst)


def validator_text(inst, violations):
    return "\n".join(asp_domain.describe(inst, v) for v in violations)


def schedule_line(pairs):
    return "SCHEDULE: {" + ", ".join(f"{j}: {t}" for j, t in pairs) + "}"


def retry(inst, arm, prev):
    """prev: the previous row (outcome, violations, solver_output, artifact)."""
    out = prev["outcome"]
    if arm == "m3_nl":
        if out == "unparsable":
            block = NL_RETRY.format(feedback=NL_UNPARSABLE, previous="")
        else:
            block = NL_RETRY.format(feedback=validator_text(inst, prev["violations"]),
                                    previous="\nYour previous schedule:\n" + prev["artifact"] + "\n")
    else:
        so = (prev.get("solver_output") or "")[:TRUNCATE]
        if out == "invalid_schedule":
            fb = validator_text(inst, prev["violations"]) + "\nClingo output: " + so
        elif out == "unsat":
            fb = UNSAT
        elif out in ("syntax_error", "solver_timeout"):
            fb = so
        elif out == "unparsable":
            fb = ASP_UNPARSABLE
        else:
            raise ValueError(out)
        block = ASP_RETRY.format(feedback=fb, artifact=prev.get("artifact") or "(none)")
    return attempt1(inst, arm) + "\n\n" + block


def classify_nl(inst, text):
    from harness import parsers
    pairs = parsers.extract_schedule_pairs(text)
    if pairs is None:
        return {"outcome": "unparsable", "violations": [], "solver_output": "", "artifact": None}
    v = asp_domain.violations(inst, pairs)
    return {"outcome": "valid" if not v else "invalid_schedule", "violations": v,
            "solver_output": "", "artifact": schedule_line(pairs)}
