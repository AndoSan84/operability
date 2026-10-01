"""Answer extraction. A parse failure is an outcome of its own, never a wrong answer."""

import re

LANG_ALIASES = {"clingo": {"clingo", "asp", "prolog", "lp"}, "python": {"python", "py"}}
FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\n(.*?)```", re.S)


def extract_code(text, lang):
    """The last fenced block labelled with `lang` or one of its aliases; None if there is none."""
    if not text:
        return None
    names = LANG_ALIASES.get(lang, {lang})
    blocks = [body for label, body in FENCE.findall(text) if label.lower() in names]
    return blocks[-1] if blocks else None


SCHEDULE_LINE = re.compile(r"^[\s*_`>#-]*SCHEDULE[\s*_`]*:[\s*_`]*\{(.*?)\}[\s*_`.]*$", re.M)
PAIR = re.compile(r"(-?\d+)\s*:\s*(-?\d+)")


def extract_schedule_pairs(text):
    """The last line of the form `SCHEDULE: {1: t1, 2: t2, ...}`, markdown decoration allowed, as
    a list of (job, time) pairs in order — duplicates kept, so the validator can see them. Prose
    is never mined, and an echoed template (`{1: t1, ...}`) is not an answer. None if absent."""
    matches = SCHEDULE_LINE.findall(text or "")
    if not matches:
        return None
    inner = matches[-1]
    if PAIR.sub("", inner).replace(",", "").strip():
        return None
    pairs = [(int(j), int(t)) for j, t in PAIR.findall(inner)]
    return pairs or None


def extract_schedule(text):
    pairs = extract_schedule_pairs(text)
    return dict(pairs) if pairs is not None else None
