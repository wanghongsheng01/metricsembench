# Public overlay v1 (n=167) — official statistics with bootstrap 95% CIs

Parent freeze SHA-256 `4d8bd8fadab86a0222f0a6ff5eb090f5da7b248f98a8f56723397e79758f3c12`, n=167, official TA denominator 148 (12 clarify + 136 compute with official numeric gold). Behavior-only compute (19) is excluded from official TA.
Bootstrap percentile 95% CIs, 10000 resamples, seed 20261112.
Predictions reused from the already-finished `metricsembench-public-v1` run; **no second paid evaluation**.
This is a *transfer* study (official BIRD/Spider questions + our behavior overlay). It is **not** a rescore of paper-13 v2/v3/v4/v5 official TEST folds.
`bindorclarify_v1` is a TPC-DS dictionary binder; transfer failure is an honest expected result.

| System | TA | Compute Acc | FAR | Missed clarify | UCR |
|---|---:|---:|---:|---:|---:|
| ark_deepseek-v4-pro_semantic | 62.2% [54.1, 70.3] | 60.3% [52.2, 68.4] | 16.7% [0.0, 41.7] | 16.7% [0.0, 41.7] | 22.6% [16.1, 29.0] |
| tokens1688_claude-sonnet-4-6_semantic | 60.8% [52.7, 68.9] | 62.5% [54.4, 70.6] | 58.3% [33.3, 83.3] | 58.3% [33.3, 83.3] | 11.0% [6.5, 16.1] |
| ark_deepseek-v4-pro_dailsql | 56.1% [48.0, 64.2] | 61.0% [52.9, 69.1] | 100.0% [100.0, 100.0] | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] |
| tokens1688_gpt-6-sol_semantic | 58.1% [50.0, 66.2] | 58.8% [50.7, 66.9] | 50.0% [25.0, 75.0] | 50.0% [25.0, 75.0] | 16.8% [11.0, 22.6] |
| bindorclarify_v1 | 2.0% [0.0, 4.7] | 0.0% [0.0, 0.0] | 75.0% [50.0, 100.0] | 75.0% [50.0, 100.0] | 3.9% [1.3, 7.1] |
| always_clarify | 8.1% [4.1, 12.8] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] |
| always_compute | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] |
| always_refuse | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] |

## Paired contrasts vs DeepSeek-v4-pro semantic (current public-TA lead)

| System | metric | Δ (system − DeepSeek) | bootstrap 95% CI | p_boot | McNemar mid-p |
|---|---|---:|---:|---:|---|
| tokens1688_claude-sonnet-4-6_semantic | TA | -1.4 pp | [-9.5, 6.8] | 0.8240 | 0.755228657504631 |
| tokens1688_claude-sonnet-4-6_semantic | compute_accuracy | +2.2 pp | [-6.6, 10.3] | 0.6760 | 0.6177193170296961 |
| tokens1688_claude-sonnet-4-6_semantic | FAR_on_clarify_or_refuse | +41.7 pp | [16.7, 66.7] | 0.0030 | — |
| tokens1688_claude-sonnet-4-6_semantic | missed_clarify | +41.7 pp | [16.7, 66.7] | 0.0030 | — |
| ark_deepseek-v4-pro_dailsql | TA | -6.1 pp | [-13.5, 2.0] | 0.1414 | 0.13249816396273678 |
| ark_deepseek-v4-pro_dailsql | compute_accuracy | +0.7 pp | [-6.6, 8.1] | 0.9244 | 0.8450189828872681 |
| ark_deepseek-v4-pro_dailsql | FAR_on_clarify_or_refuse | +83.3 pp | [58.3, 100.0] | 0.0000 | — |
| ark_deepseek-v4-pro_dailsql | missed_clarify | +83.3 pp | [58.3, 100.0] | 0.0000 | — |
| tokens1688_gpt-6-sol_semantic | TA | -4.1 pp | [-12.2, 4.1] | 0.3560 | 0.32400860008783644 |
| tokens1688_gpt-6-sol_semantic | compute_accuracy | -1.5 pp | [-9.6, 6.6] | 0.7970 | 0.7283324808813632 |
| tokens1688_gpt-6-sol_semantic | FAR_on_clarify_or_refuse | +33.3 pp | [8.3, 58.3] | 0.0150 | — |
| tokens1688_gpt-6-sol_semantic | missed_clarify | +33.3 pp | [8.3, 58.3] | 0.0150 | — |
| bindorclarify_v1 | TA | -60.1 pp | [-68.2, -52.0] | 0.0000 | 1.6155871338926322e-27 |
| bindorclarify_v1 | compute_accuracy | -60.3 pp | [-68.4, -52.2] | 0.0000 | 2.0679515313825692e-25 |
| bindorclarify_v1 | FAR_on_clarify_or_refuse | +58.3 pp | [33.3, 83.3] | 0.0000 | — |
| bindorclarify_v1 | missed_clarify | +58.3 pp | [33.3, 83.3] | 0.0000 | — |
| always_clarify | TA | -54.1 pp | [-62.2, -45.3] | 0.0000 | 1.8901076996836682e-22 |
| always_clarify | compute_accuracy | -60.3 pp | [-68.4, -52.2] | 0.0000 | 2.0679515313825692e-25 |
| always_clarify | FAR_on_clarify_or_refuse | -16.7 pp | [-41.7, 0.0] | 0.2306 | — |
| always_clarify | missed_clarify | -16.7 pp | [-41.7, 0.0] | 0.2306 | — |
| always_compute | TA | -62.2 pp | [-70.3, -54.1] | 0.0000 | 2.0194839173657902e-28 |
| always_compute | compute_accuracy | -60.3 pp | [-68.4, -52.2] | 0.0000 | 2.0679515313825692e-25 |
| always_compute | FAR_on_clarify_or_refuse | +83.3 pp | [58.3, 100.0] | 0.0000 | — |
| always_compute | missed_clarify | +83.3 pp | [58.3, 100.0] | 0.0000 | — |
| always_refuse | TA | -62.2 pp | [-70.3, -54.1] | 0.0000 | 2.0194839173657902e-28 |
| always_refuse | compute_accuracy | -60.3 pp | [-68.4, -52.2] | 0.0000 | 2.0679515313825692e-25 |
| always_refuse | FAR_on_clarify_or_refuse | -16.7 pp | [-41.7, 0.0] | 0.2306 | — |
| always_refuse | missed_clarify | -16.7 pp | [-41.7, 0.0] | 0.2306 | — |
