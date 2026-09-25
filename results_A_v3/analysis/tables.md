# Experiment A — results

## M1 — asp

Attempt 1 (shared): single-shot success 36/86 (42%, CI 32%–52%); syntactic failure 20/86 (23%, CI 16%–33%); eligible (runnable, semantically failing) 30/86 (35%, CI 26%–45%), of which UNSAT 1.
Branched: 30 (target 30, reached); complete in both arms: 30; incomplete (pending or infrastructure): 0. Attempt-1 calls lost to infrastructure: 0.

- **runnable attempt 1 that failed semantically** (n=30): Hodges-Lehmann +0.50 attempts, 95% CI [+0.00, +1.00], one-sided p = 0.0016, tied pairs 50% → **supported**
- **invalid schedule only (UNSAT excluded)** (n=29): Hodges-Lehmann +0.50 attempts, 95% CI [+0.00, +1.00], one-sided p = 0.0016, tied pairs 48% → **supported**

Success within 3: binary 8/30 (27%, CI 14%–44%), diagnostic 18/30 (60%, CI 42%–75%), McNemar p = 0.0129.
Uptake: binary 28/56 (50%, CI 37%–63%), diagnostic 31/48 (65%, CI 50%–77%). Regression: binary 6/11 (55%, CI 28%–79%), diagnostic 3/4 (75%, CI 30%–95%).
Contamination: shared 0/86 (0%, CI 0%–4%), binary 0/56 (0%, CI 0%–6%), diagnostic 0/48 (0%, CI 0%–7%)

## M4 — asp (descriptive)

Attempt 1 (shared): single-shot success —; syntactic failure —; eligible (runnable, semantically failing) —, of which UNSAT 0.
Branched: 0 (target 6, NOT reached); complete in both arms: 0; incomplete (pending or infrastructure): 0. Attempt-1 calls lost to infrastructure: 0.

- **runnable attempt 1 that failed semantically**: untestable: no branched instances
- **invalid schedule only (UNSAT excluded)**: untestable: no branched instances

Success within 3: binary —, diagnostic —, McNemar p = 1.0000.
Uptake: binary —, diagnostic —. Regression: binary —, diagnostic —.
Contamination: shared —, binary —, diagnostic —
