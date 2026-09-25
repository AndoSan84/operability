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
