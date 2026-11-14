# Pre-registration: Paper 15 second official held-out `p15_heldout_v2`

Registered 2026-11-13 (America/Los_Angeles), **before any score on this fold**.

## Why

Simulated PVLDB review of v6: the official held-out `p15_heldout_v1` (n=94; FAR
denominator 40) is small, so "no paired CI excludes 0" may be low power, and the
official TA leader depends on the compute fraction of the fold. v1 is already
`evaluated=true`; we do not add systems to it and do not retune it. Instead we freeze a
new, larger, more balanced fold with the same handbook, card, metrics and statistics.

## Fold

- Builder: `impl/msb/build_paper15_heldout_v2.py` (seed `paper15_msb_tpcds_heldout_v2_seed_20261113`).
- File: `impl/tasks/msb_p15_heldout_v2_tasks.json`, `evaluated=false`.
- **Freeze SHA-256: `abe30e25701882ef9ad3b9a53fefbe641b8c7aa2b0932b0cf8dab11d68c4db97`** (same canonical convention as v1).
- n=250: compute 132 / clarify 62 / refuse 56 (FAR denominator 118). 0 sign-flip triples (none left in the population).
- Disjoint from v0.1 and v1 by id and by question text (checked in the builder).
- Selection is hash-ordered within each stratum, never by gap and never by any model output.
- 8 of 62 clarify items have coinciding paired values (3 calendar months, four 2002 new-product shares at 0, one return-rate pair inside tolerance). They remain legally underspecified, as in v0.1/v1; not dropped.

## Systems (one shot each, all ids, no --limit)

1. Deterministic, gold-blind: naive_surface, dict_default, always_clarify, always_refuse.
2. Frontier (identical extras to v0.1/v1): tokens1688_2 claude-opus-5 (adaptive, effort max), claude-opus-5-5 (adaptive, output_config.effort=high), gpt-6-luna (reasoning_effort=high).
3. Mid-tier semantic (identical card and rules): ark deepseek-v4-pro, tokens1688 claude-sonnet-4-6, tokens1688 gpt-6-sol; plus gpt-6-sol direct (always-SQL ablation).
4. Published always-answer prompting on ark deepseek-v4-pro: DAIL-SQL, DIN-SQL.
5. CodeS-7B-Spider (official checkpoint, authors' zero-shot prompt, beam 4, first executable beam), **only if** its DEV (v0.1) run completes first with the frozen prompt builder; otherwise listed as not profiled on v2.

Not on v2: the dictionary reference protocol (a sister-paper artifact; template profile only), Qwen2.5-7B (its GPU server port is not ours to use).

## Metrics and statistics

- Official: TA (Eq. 2), Compute Acc, FAR, CRR, Missed clarify, UCR, DSR, Illegal YoY/Agg; Match tolerance abs 1e-4 / rel 1e-5.
- **Pre-registered secondary (new):** class-balanced TA = mean over gold behaviors of per-behavior TA (compute, clarify, refuse), which removes the dependence on the fold's behavior mix; and the mix crossover w* at which a system's expected TA equals naive's when the gold-compute share is w.
- Bootstrap 95% CIs, 10,000 resamples, seed 20261112. Paired bootstrap on per-item difference and McNemar mid-p vs naive_surface; W/T/L; Holm–Bonferroni across the family of system-vs-naive TA contrasts.
- Bold best / underline second including ties; lower-is-better columns marked.

## Spend

Estimated < $20 total (Opus ~$0.02/item). Per-system soft cap $15. Daily cap $50/model is not approached.

## After evaluation

Flip `evaluated=true` in a dedicated commit that touches no task or gold. Fold identity stays the freeze SHA.
