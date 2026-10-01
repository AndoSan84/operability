"""Runs one Clingo program read from stdin; prints one JSON line. Invoked in a subprocess by
harness.asp_domain.run_clingo, so a runaway grounding can be killed by timeout."""

import json
import sys

import clingo


def main():
    program = sys.stdin.read()
    messages = []
    ctl = clingo.Control(["1"], logger=lambda code, msg: messages.append(msg.strip()))
    try:
        ctl.add("base", [], program)
        ctl.ground([("base", [])])
    except RuntimeError as e:
        text = "\n".join(messages) or str(e)
        print(json.dumps({"category": "syntax_error", "starts": [], "output": text[-1500:]}))
        return
    found = {}

    def on_model(m):
        syms = m.symbols(shown=True)
        starts = [s for s in syms if s.name == "start" and len(s.arguments) == 2]
        if not starts:
            starts = [s for s in m.symbols(atoms=True)
                      if s.name == "start" and len(s.arguments) == 2]
        found["starts"] = starts
        found["shown"] = " ".join(str(s) for s in syms)

    result = ctl.solve(on_model=on_model)
    if not result.satisfiable:
        print(json.dumps({"category": "unsat", "starts": [], "output": "UNSATISFIABLE"}))
        return
    starts = []
    for s in found.get("starts", []):
        a, b = s.arguments
        if a.type == clingo.SymbolType.Number and b.type == clingo.SymbolType.Number:
            starts.append([a.number, b.number])
    out = "SATISFIABLE\nAnswer: " + found.get("shown", "")
    print(json.dumps({"category": "sat", "starts": starts, "output": out[:1500]}))


if __name__ == "__main__":
    main()
