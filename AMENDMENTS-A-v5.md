# Experiment A, config version 5 — M3, application notes

The design is `experiment-A-v5-M3.md`, committed with this file before any M3 call. These notes
record how it was applied and what the implementation had to decide.

## H1 — The analysis script is a merge, not the supplied v5

The supplied v5 script was built on the v3 script *as originally supplied*, not on the frozen v1
script (sha256 `69443d8b…`). It therefore lacked the corrections of AMENDMENTS-A-v1 D9: an arm
left pending by an interrupted batch scored as censored, and an `api_error` scored as a model
failure. Its new `medium_contrast` repeated the first defect for M3. With about 700 calls and
several subscription pauses, that is the routine case.

`analysis/analyze_experiment_A_v5.py` is the frozen v1 script plus the v5 additions: M3 with both
media looped inside the module, the corrected regression denominator, `MEI_MEDIUM = 0.15`, and the
M3 report. The D9 rule extends to M3: an instance is paired only when both arms are finished
(`arm_finished_own`), and unfinished instances are counted. The v1 script is untouched, so the
v1–v4 configs still match their recorded sha256 and the v3/v4 outputs stay reproducible.

Verified on the real data: on `results_A_v3` the v5 script reproduces every v3 number except the
diagnostic arm's regression, which becomes 3/9 instead of 3/4 — the intended correction (binary
unchanged at 6/11). On `results_A_v4` it reproduces M2 exactly.

## H2 — Implementation decisions the spec left open

- **Prompt composition.** Every call is one user message: the medium's attempt-1 prompt verbatim,
  a blank line, then the medium's retry block (spec §4), as in M1.
- **NL, parse failure:** the NL retry keeps its first line ("Your schedule is not valid."), then the
  unparsable message; the previous-schedule block is omitted, as the spec says.
- **ASP, UNSAT:** the fixed sentence only, without solver output, as in the spec's table (M1 also
  appended the solver output; M3 does not).
- **ASP, cases not in the table:** a solver timeout returns Clingo's timeout message, like a syntax
  error; a reply without a ```clingo block gets "Your reply contained no clingo code block." with
  "(none)" as previous encoding.
- **Validator message:** one line per violation from `asp_domain.describe`, identical in both
  media.
- **NL schedule parser:** the last line of the form `SCHEDULE: {...}`, markdown allowed; pairs kept
  in order with duplicates, so the validator sees them; an echoed template is not an answer.
- **Order within an instance:** the arm order is drawn per instance; attempts are interleaved
  (attempt 1 of both arms, then attempt 2, then attempt 3), so both media of an instance stay close
  in time.
- **Seeds:** main instance i uses 8,000,000 + 1000·i, pilot instance i 8,500,000 + 1000·i.
- **Floor rule:** fallback point [16, 4, 16]. After the one move, the second pilot is run and the
  main run proceeds at the new point whatever it shows; no other adjustment.
- **Timeout:** 600 s in the pilot, then max(180, 2 × pilot p99), as in C8.
- **Caps:** 100 calls per pilot point, 1,300 for the main run.

## H3 — Other changes in this commit

- `~/.claude/settings.json` now sets `DISABLE_AUTOUPDATER=1` for every Claude Code process, as the
  v5 spec requires for a run spread over several subscription pauses.
- Every result row now records `thinking` next to `effort`.
