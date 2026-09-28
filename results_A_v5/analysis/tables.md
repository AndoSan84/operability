# Experiment A — results

## M1 — asp

Attempt 1 (shared): single-shot success —; syntactic failure —; eligible (runnable, semantically failing) —, of which UNSAT 0.
Branched: 0 (target 30, NOT reached); complete in both arms: 0; incomplete (pending or infrastructure): 0. Attempt-1 calls lost to infrastructure: 0.

- **runnable attempt 1 that failed semantically**: untestable: no branched instances
- **invalid schedule only (UNSAT excluded)**: untestable: no branched instances

Success within 3: binary —, diagnostic —, McNemar p = 1.0000.
Uptake: binary —, diagnostic —. Regression: binary —, diagnostic —.
Contamination: shared —, binary —, diagnostic —

## M4 — asp (descriptive)

Attempt 1 (shared): single-shot success —; syntactic failure —; eligible (runnable, semantically failing) —, of which UNSAT 0.
Branched: 0 (target 6, NOT reached); complete in both arms: 0; incomplete (pending or infrastructure): 0. Attempt-1 calls lost to infrastructure: 0.

- **runnable attempt 1 that failed semantically**: untestable: no branched instances
- **invalid schedule only (UNSAT excluded)**: untestable: no branched instances

Success within 3: binary —, diagnostic —, McNemar p = 1.0000.
Uptake: binary —, diagnostic —. Regression: binary —, diagnostic —.
Contamination: shared —, binary —, diagnostic —

## M3 — medium under an identical loop (v5)

Paired instances (both arms finished): 200; incomplete: 0.
**Primary** — success within 3: ASP 78%, NL 20%, difference +0.590 (95% CI [+0.515, +0.665]; 90% CI [+0.525, +0.650]), McNemar p = 0.0000 → **ASP advantage**
Attempt 1: ASP 82/200 (41%, CI 34%–48%), NL 9/200 (4%, CI 2%–8%), McNemar p = 0.0000.
Repair among doubly failed (n=113): ASP 71/113 (63%, CI 54%–71%), NL 16/113 (14%, CI 9%–22%), McNemar p = 0.0000.
Attempts to success: Hodges-Lehmann (NL - ASP) +1.50, two-sided p = 0.0000.
Uptake: ASP 120/192 (62%, CI 55%–69%), NL 359/362 (99%, CI 98%–100%). Regression: ASP 5/32 (16%, CI 7%–32%), NL 88/170 (52%, CI 44%–59%).
Contamination: ASP 0/392 (0%, CI 0%–1%), NL 0/562 (0%, CI 0%–1%).
