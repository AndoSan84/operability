"""Contamination probe (AMENDMENTS-v3 C8): does a response refer to tools, files or execution?
The patterns are read from the frozen config, never defined here."""

import re
from pathlib import Path

import yaml

_CFG = Path(__file__).resolve().parent.parent / "config/experiment_A.frozen.yaml"
PATTERNS = yaml.safe_load(open(_CFG))["contamination"]["patterns_case_insensitive"]
_COMPILED = [re.compile(p, re.I) for p in PATTERNS]


def scan(text):
    """The patterns that match, in config order; empty when the response is clean."""
    return [p.pattern for p in _COMPILED if p.search(text or "")]
