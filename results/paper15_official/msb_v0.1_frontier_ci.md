# MetricSemBench v0.1 — frontier semantic profile (official CIs)

Fixture: TPC-DS SF=1 MetricSemBench v0.1, n=85 (compute 44 / clarify 21 / refuse 20).
Bootstrap percentile 95% CIs, 10,000 resamples, seed 20261112.
Same frozen `SCHEMA_CARD` + `SEMANTIC_RULES` as the mid-tier runs. Temperature omitted (these models reject it).
Frozen extras, after a 2-item DEV probe used only to freeze request parameters (the probe is not a result):

- Claude Opus 5: `thinking.type=adaptive` + `reasoning_effort=max`.
- Claude Opus 5.5: `thinking.type=adaptive` + `output_config.effort=high` (combining `reasoning_effort` with adaptive returned HTTP 400).
- GPT-6-luna: `reasoning_effort=high`.

Paper-13 official TEST folds were not used. This is a DEV / diagnostic profile, not a held-out generalization claim.
The dictionary-grounded reference protocol is a template-fit profile point and is not in this table.

Paid spend on this full v0.1 run (tokens1688 / tokens1688_2 shared quota): Opus 5 $2.234, Opus 5.5 $1.793, luna $0.019; total $4.045. Probe spend was about $0.10 earlier.

| System | spent | TA | Compute Acc | FAR | CRR | Missed clarify | UCR | DSR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Claude Opus 5 sem. (max, adaptive) | $2.234 | **57.6% [47.1, 68.2]** | 29.5% [15.9, 43.2] | 7.3% [0.0, 17.1] | **85.0% [70.0, 100.0]** | 4.8% [0.0, 14.3] | 36.4% [22.7, 50.0] | 4.5% [0.0, 11.4] |
| Claude Opus 5.5 sem. (adaptive, effort high) | $1.793 | <u>55.3% [44.7, 65.9]</u> | **34.1% [20.5, 47.7]** | 9.8% [2.4, 19.5] | **85.0% [70.0, 100.0]** | 14.3% [0.0, 28.6] | <u>18.2% [6.8, 29.5]</u> | 4.5% [0.0, 11.4] |
| GPT-6-luna sem. (effort high) | $0.019 | 42.4% [31.8, 52.9] | 18.2% [6.8, 29.5] | **0.0% [0.0, 0.0]** | 40.0% [20.0, 60.0] | **0.0% [0.0, 0.0]** | 77.3% [63.6, 88.6] | **0.0% [0.0, 0.0]** |
| Naive surface (EX ceiling, for reference) | — | 51.8% [41.2, 62.4] | 100.0% [100.0, 100.0] | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] |

Best mean among the three frontier systems is **bold**, second is <u>underlined</u>. Naive is a reference row, not part of that ranking. Higher is better for TA / Compute Acc / CRR; lower is better for FAR / Missed / UCR / DSR.

## Paired official-TA vs naive_surface

| System | ΔTA (pp) | bootstrap 95% CI | p_boot | McNemar mid-p | W/T/L |
|---|---:|---:|---:|---:|---|
| Claude Opus 5 | +5.9 | [−12.9, 24.7] | 0.5656 | 0.545 (b01=31, b10=36) | 36/18/31 |
| Claude Opus 5.5 | +3.5 | [−14.1, 21.2] | 0.7384 | 0.704 (b01=29, b10=32) | 32/24/29 |
| GPT-6-luna | −9.4 | [−28.2, 9.4] | 0.3430 | 0.321 (b01=36, b10=28) | 28/21/36 |

None of the three paired CIs excludes 0. Opus 5 has the highest *point* estimate among evaluated (non-reference) systems on this fixture, and is not a significant winner over naive.

## EX vs TA ranks after adding the frontier systems

On the original mid-tier + deterministic set of 13 systems, Kendall τ(EX ranks, TA ranks) = **0.589**. After adding the three frontier systems (16 systems), τ = **0.495**. Opus 5 sits at EX rank 8 (Compute Acc 29.5%) and TA rank 2 (a +6 shift). Naive remains at the EX ceiling and falls to TA rank 4.

## Mechanisms (gold-compute, n=44)

The schema card documents an FX overlay; calendar gold executes `SUM(ss_net_paid)` (the native TPC-DS measure). This tension is frozen, not retuned.

- **Opus 5**: 16 unnecessary clarifies, 2 unnecessary refuses, 26 computes of which 13 match gold, 2 are definition-swaps (lifecycle), 11 are wrong values not matching a known paired definition. Of the 26 compute SQLs, 16 use `net_paid_usd`, 4 use `ss_net_paid`.
- **Opus 5.5**: only 8 unnecessary clarifies (the lowest UCR of the three), 33 computes, 15 match gold, 2 DSR, 16 wrong values; 22 of 33 compute SQLs use `net_paid_usd`, 5 use `ss_net_paid`.
- **GPT-6-luna**: 34 unnecessary clarifies (UCR 77.3%), FAR = 0, missed-clarify = 0; all 8 of its compute attempts match gold. It almost never false-answers and almost never computes.

On gold-refuse (n=20), both Opus models reach CRR 85.0% [70.0, 100.0], against 40.0% for luna and 40.0% for mid-tier DeepSeek / Claude / GPT-6-sol semantic. Frontier refusal is a real strength; frontier computation under the frozen native-measure gold is not.

GATE-FRONTIER on DEV is *complete*: the three pre-registered strongest models finished all 85 items with no quota stop and no invented rows. They do not significantly beat naive on official TA. Official held-out LLM scores are a separate one-shot, after this freeze, and are not in this file.
