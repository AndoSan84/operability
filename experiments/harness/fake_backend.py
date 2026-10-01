"""A stand-in for the model, for dry runs of the runner that spend no subscription calls.
It reads the instance back from the prompt and answers with a correct encoding or one of four
broken ones, deterministically per prompt. Rows it produces carry backend 'fake'."""

import hashlib
import random
import re

CORRECT = """{facts}
time(0..D) :- deadline(D).
1 {{ start(J,T) : time(T) }} 1 :- job(J,_,_).
:- start(J,T), job(J,_,Dur), deadline(D), T + Dur > D.
:- prec(I,J), start(I,TI), job(I,_,DI), start(J,TJ), TJ < TI + DI.
:- job(I,M,DI), job(J,M,DJ), I < J, start(I,TI), start(J,TJ), TI < TJ + DJ, TJ < TI + DI.
#show start/2."""


def _facts(prompt):
    jobs = re.findall(r"^\((\d+), ([A-Z]), (\d+)\)$", prompt, re.M)
    block = prompt.split("Precedence constraints")[1].split("Deadline")[0]
    precs = re.findall(r"^\((\d+), (\d+)\)$", block, re.M)
    deadline = re.search(r"Deadline \(all jobs must finish by\): (\d+)", prompt).group(1)
    lines = [f"job({j},{m.lower()},{d})." for j, m, d in jobs]
    lines += [f"prec({a},{b})." for a, b in precs] + [f"deadline({deadline})."]
    return "\n".join(lines)


class FakeBackend:
    name = "fake"
    version = "fake-1"

    def __init__(self, model="fake-model", p_correct=0.5):
        self.model, self.p_correct = model, p_correct

    def call(self, prompt, timeout_s):
        rng = random.Random(hashlib.sha256(prompt.encode()).hexdigest())
        prog = CORRECT.format(facts=_facts(prompt))
        # a retry that received a diagnosis is repaired more often than one that did not
        p = self.p_correct + (0.3 if "violates:" in prompt or "no answer set" in prompt else 0)
        r = rng.random()
        if r < p:
            body = prog
        elif r < p + 0.2:
            body = "\n".join(l for l in prog.splitlines() if "I < J" not in l)   # no overlap rule
        elif r < p + 0.3:
            body = prog.replace("TJ < TI + DI.", "TJ < TI + DI + 1.")          # too strong: may be unsat
        elif r < p + 0.4:
            body = prog.replace("1 {", "1 {{")                                   # syntax error
        else:
            return self._reply("I cannot produce this program.")
        return self._reply(f"```clingo\n{body}\n```")

    def _reply(self, text):
        return {"outcome_hint": None, "text": text, "model_id": self.model, "stop_reason": "end_turn",
                "num_turns": 1, "input_tokens": 0, "output_tokens": 0, "latency_ms": 5,
                "cost_usd": 0.0, "session_id": None, "structural_violations": [], "stderr": ""}
