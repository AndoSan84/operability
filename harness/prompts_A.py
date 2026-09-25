"""Experiment A prompts: one user message of four blocks — problem, feedback, previous artifact,
instruction. Only the feedback block may differ between arms (spec §5)."""

from harness import asp_domain

BINARY_SEMANTIC = "It did not produce a valid schedule."
UNSAT_DIAGNOSIS = ("Clingo found no answer set, although the instance admits a valid schedule: "
                   "some constraint in your encoding is stronger than the specification.")
UNPARSABLE = "Your reply contained no clingo code block."
INSTRUCTION = "Return a corrected program, as exactly one ```clingo code block and nothing else."
TRUNCATE = 1500


def feedback_block(arm, prev, inst):
    """prev: the classified previous attempt (outcome, violations, solver_output)."""
    outcome, out = prev["outcome"], (prev.get("solver_output") or "")[:TRUNCATE]
    if outcome in ("syntax_error", "solver_timeout"):
        return out                                   # a precondition: identical in both arms
    if outcome == "unparsable":
        return UNPARSABLE
    if arm == "binary":
        return BINARY_SEMANTIC
    if outcome == "invalid_schedule":
        lines = "\n".join(asp_domain.describe(inst, v) for v in prev["violations"])
        return f"The schedule it produced violates:\n{lines}\nClingo output: {out}"
    if outcome == "unsat":
        return f"{UNSAT_DIAGNOSIS}\nClingo output: {out}"
    raise ValueError(f"no feedback for outcome {outcome}")


def blocks(inst, arm, prev, prev_artifact):
    return {
        "problem": asp_domain.attempt1_prompt(inst),         # spec §5: verbatim
        "feedback": "Your encoding was run with Clingo. " + feedback_block(arm, prev, inst),
        "previous_artifact": "Your previous encoding:\n" + (prev_artifact or "(none)"),
        "instruction": INSTRUCTION,
    }


def render(b):
    return "\n\n".join([b["problem"], b["feedback"], b["previous_artifact"], b["instruction"]])


def branch_identity(b1, b2):
    """The gate: every block but feedback byte-identical."""
    return all(b1[k] == b2[k] for k in ("problem", "previous_artifact", "instruction"))
