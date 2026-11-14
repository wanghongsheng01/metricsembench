# MetricSemBench v0.1 — official statistics with bootstrap 95% CIs

Fixture: TPC-DS SF=1 MetricSemBench v0.1, n=85 (compute 44 / clarify 21 / refuse 20).
Bootstrap percentile 95% CIs, 10000 resamples, seed 20261112.
These are **template-fixture** numbers, not a held-out generalization claim.
`bindorclarify_v1` is a dictionary-grounded **reference protocol** (paper 13's method), reported as a profile point, not as "our method wins" — paper 15 is an EA&B benchmark.
Paper-13 official TEST folds were **not** used.

Best per column (mean) is **bold**, second is <u>underlined</u> (ties share the mark). Higher is better for TA / Compute Acc / CRR; lower is better for FAR / Missed clarify / UCR / DSR / Illegal*.

| System | n | TA | Compute Acc | FAR | CRR | Missed clarify | UCR | DSR | Illegal YoY | Illegal Agg |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bindorclarify_v1 | 85 | **100.0% [100.0, 100.0]** | **100.0% [100.0, 100.0]** | **0.0% [0.0, 0.0]** | **100.0% [100.0, 100.0]** | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** |
| naive_surface | 85 | <u>51.8% [41.2, 62.4]</u> | **100.0% [100.0, 100.0]** | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** | 100.0% [100.0, 100.0] | 100.0% [100.0, 100.0] |
| dict_default | 85 | <u>51.8% [41.2, 62.4]</u> | **100.0% [100.0, 100.0]** | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** | 100.0% [100.0, 100.0] | 100.0% [100.0, 100.0] |
| ark_deepseek-v4-pro_dailsql | 85 | 42.4% [31.8, 52.9] | <u>81.8% [70.5, 93.2]</u> | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | **0.0% [0.0, 0.0]** | <u>4.5% [0.0, 11.4]</u> | 100.0% [100.0, 100.0] | 100.0% [100.0, 100.0] |
| ark_deepseek-v4-pro_dinsql | 85 | 3.5% [0.0, 8.2] | 6.8% [0.0, 15.9] | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** | 100.0% [100.0, 100.0] | 100.0% [100.0, 100.0] |
| ark_deepseek-v4-pro_semantic | 85 | 44.7% [34.1, 55.3] | 61.4% [47.7, 75.0] | 63.4% [48.8, 78.0] | <u>40.0% [20.0, 60.0]</u> | <u>66.7% [47.6, 85.7]</u> | <u>4.5% [0.0, 11.4]</u> | **0.0% [0.0, 0.0]** | 85.7% [64.3, 100.0] | **0.0% [0.0, 0.0]** |
| tokens1688_claude-sonnet-4-6_semantic | 85 | 43.5% [32.9, 54.1] | 18.2% [6.8, 29.5] | <u>9.8% [2.4, 19.5]</u> | <u>40.0% [20.0, 60.0]</u> | **0.0% [0.0, 0.0]** | 70.5% [56.8, 84.1] | **0.0% [0.0, 0.0]** | <u>28.6% [7.1, 50.0]</u> | **0.0% [0.0, 0.0]** |
| tokens1688_gpt-6-sol_semantic | 85 | 41.2% [30.6, 51.8] | 29.5% [15.9, 43.2] | **0.0% [0.0, 0.0]** | <u>40.0% [20.0, 60.0]</u> | **0.0% [0.0, 0.0]** | 52.3% [38.6, 65.9] | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** |
| tokens1688_gpt-6-sol_direct | 85 | 17.6% [9.4, 25.9] | 34.1% [20.5, 47.7] | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | **0.0% [0.0, 0.0]** | <u>4.5% [0.0, 11.4]</u> | 100.0% [100.0, 100.0] | 100.0% [100.0, 100.0] |
| qwen25_7b_semantic | 85 | 17.6% [9.4, 25.9] | 15.9% [6.8, 27.3] | 63.4% [48.8, 78.0] | 30.0% [10.0, 50.0] | <u>66.7% [47.6, 85.7]</u> | 11.4% [2.3, 20.5] | **0.0% [0.0, 0.0]** | 71.4% [42.9, 92.9] | <u>33.3% [0.0, 66.7]</u> |
| qwen25_7b_direct | 85 | 10.6% [4.7, 17.6] | 20.5% [9.1, 31.8] | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** | 100.0% [100.0, 100.0] | 100.0% [100.0, 100.0] |
| always_refuse | 85 | 23.5% [15.3, 32.9] | 0.0% [0.0, 0.0] | **0.0% [0.0, 0.0]** | **100.0% [100.0, 100.0]** | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** |
| always_clarify | 85 | 24.7% [16.5, 34.1] | 0.0% [0.0, 0.0] | **0.0% [0.0, 0.0]** | 0.0% [0.0, 0.0] | **0.0% [0.0, 0.0]** | 100.0% [100.0, 100.0] | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** |

## Ranking inversion: EX-like (Compute Acc) vs official TA

A single execution-accuracy (EX) score, here Compute Acc on the 44 gold-compute items, ranks always-answer systems that ignore contracts as if they were strong. Official TA charges a false answer on clarify and refuse items.

| System | Compute Acc (EX-like) | EX rank | Official TA | TA rank | Rank shift (EX→TA) |
|---|---:|---:|---:|---:|---:|
| bindorclarify_v1 | 100.0% [100.0, 100.0] | 1 | 100.0% [100.0, 100.0] | 1 | +0 |
| naive_surface | 100.0% [100.0, 100.0] | 1 | 51.8% [41.2, 62.4] | 2 | -1 |
| dict_default | 100.0% [100.0, 100.0] | 1 | 51.8% [41.2, 62.4] | 2 | -1 |
| ark_deepseek-v4-pro_dailsql | 81.8% [70.5, 93.2] | 4 | 42.4% [31.8, 52.9] | 6 | -2 |
| ark_deepseek-v4-pro_dinsql | 6.8% [0.0, 15.9] | 11 | 3.5% [0.0, 8.2] | 13 | -2 |
| ark_deepseek-v4-pro_semantic | 61.4% [47.7, 75.0] | 5 | 44.7% [34.1, 55.3] | 4 | +1 |
| tokens1688_claude-sonnet-4-6_semantic | 18.2% [6.8, 29.5] | 9 | 43.5% [32.9, 54.1] | 5 | +4 |
| tokens1688_gpt-6-sol_semantic | 29.5% [15.9, 43.2] | 7 | 41.2% [30.6, 51.8] | 7 | +0 |
| tokens1688_gpt-6-sol_direct | 34.1% [20.5, 47.7] | 6 | 17.6% [9.4, 25.9] | 10 | -4 |
| qwen25_7b_semantic | 15.9% [6.8, 27.3] | 10 | 17.6% [9.4, 25.9] | 10 | +0 |
| qwen25_7b_direct | 20.5% [9.1, 31.8] | 8 | 10.6% [4.7, 17.6] | 12 | -4 |
| always_refuse | 0.0% [0.0, 0.0] | 12 | 23.5% [15.3, 32.9] | 9 | +3 |
| always_clarify | 0.0% [0.0, 0.0] | 12 | 24.7% [16.5, 34.1] | 8 | +4 |

Kendall's τ between EX-like ranks and official-TA ranks: **0.589** (computed on systems with both scores; seedless, descriptive).

Notable inversions: `naive_surface` / `dict_default` are at the EX ceiling (44/44) but only mid-pack on TA because FAR = 100% on the 41 clarify∪refuse items. DAIL-SQL is the strongest *published always-answer* computer and still has FAR = 100%. GPT-6-sol semantic has *lower* Compute Acc than GPT-6-sol direct but *higher* TA, because it refuses to silently answer underspecified or illegal questions (FAR = 0) at the cost of a high unnecessary-clarify rate.

## Paired tests on official TA (McNemar mid-p, paired bootstrap, seed 20261112)

### Each system vs `naive_surface` (the EX-ceiling always-answer baseline)

| System | ΔTA (system − naive) | bootstrap 95% CI | p_boot | McNemar mid-p (b01, b10) |
|---|---:|---:|---:|---|
| bindorclarify_v1 | +48.2 pp | [37.6, 58.8] | 0.0000 | 4.547473508864641e-13 (b01=0, b10=41) |
| dict_default | +0.0 pp | [0.0, 0.0] | 1.0000 | 1.0 (b01=0, b10=0) |
| ark_deepseek-v4-pro_dailsql | -9.4 pp | [-16.5, -3.5] | 0.0004 | 0.00390625 (b01=8, b10=0) |
| ark_deepseek-v4-pro_dinsql | -48.2 pp | [-58.8, -37.6] | 0.0000 | 4.547473508864641e-13 (b01=41, b10=0) |
| ark_deepseek-v4-pro_semantic | -7.1 pp | [-18.8, 4.7] | 0.2968 | 0.26493089646101 (b01=17, b10=11) |
| tokens1688_claude-sonnet-4-6_semantic | -8.2 pp | [-25.9, 10.6] | 0.4222 | 0.38905246054779263 (b01=36, b10=29) |
| tokens1688_gpt-6-sol_semantic | -10.6 pp | [-27.1, 5.9] | 0.2364 | 0.22032849417661104 (b01=31, b10=22) |
| tokens1688_gpt-6-sol_direct | -34.1 pp | [-44.7, -24.7] | 0.0000 | 1.862645149230957e-09 (b01=29, b10=0) |
| qwen25_7b_semantic | -34.1 pp | [-47.1, -20.0] | 0.0000 | 9.24769992138863e-06 (b01=37, b10=8) |
| qwen25_7b_direct | -41.2 pp | [-51.8, -30.6] | 0.0000 | 2.9103830456733704e-11 (b01=35, b10=0) |
| always_refuse | -28.2 pp | [-45.9, -10.6] | 0.0020 | 0.0026263768106840383 (b01=44, b10=20) |
| always_clarify | -27.1 pp | [-44.7, -9.4] | 0.0052 | 0.004272405031651672 (b01=44, b10=21) |

