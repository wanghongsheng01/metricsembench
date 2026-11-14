# Paper 15 official held-out v1 — frontier one-shot (complete)

SHA-256 `03d26b59479d82ee7d6e71bb73f6bedc4db42204cf8c9d9124604adb53e55cb2`, n=94 (compute 54 / clarify 26 / refuse 14).
Fold identity is this freeze SHA (computed with `evaluated=false`). The 94 tasks and gold are unchanged.
Bootstrap percentile 95% CIs, 10,000 resamples, seed 20261112.
Same frozen `SCHEMA_CARD`, `SEMANTIC_RULES`, and request extras as the v0.1 frontier profile. No `--limit`. Temperature omitted.
Paper-13 official TEST folds were not used. All 94 ids finished with 0 API errors and 0 gold-behavior mismatches.
Paid spend (tokens1688 / tokens1688_2 shared quota): Opus 5 $2.574, Opus 5.5 $2.018, luna $0.023; total **$4.615**.

Deterministic gold-blind scores were already taken after the freeze and are repeated here as the comparison group.

| System | spent | TA | Compute Acc | FAR | CRR | Missed clarify | UCR | DSR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Naive surface | — | **57.4% [47.9, 67.0]** | **100.0% [100.0, 100.0]** | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** |
| Dict.\ default | — | **57.4% [47.9, 67.0]** | **100.0% [100.0, 100.0]** | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** |
| Claude Opus 5.5 sem. | $2.018 | <u>54.3% [44.7, 63.8]</u> | <u>35.2% [22.2, 48.1]</u> | 17.5% [7.5, 30.0] | <u>71.4% [50.0, 92.9]</u> | 15.4% [3.8, 30.8] | 9.3% [1.9, 18.5] | 1.9% [0.0, 5.6] |
| Claude Opus 5 sem. | $2.574 | 52.1% [42.6, 61.7] | 29.6% [18.5, 42.6] | <u>10.0% [2.5, 20.0]</u> | <u>71.4% [50.0, 92.9]</u> | 11.5% [0.0, 26.9] | 35.2% [22.2, 48.1] | 1.9% [0.0, 5.6] |
| GPT-6-luna sem. | $0.023 | 46.8% [37.2, 56.4] | 22.2% [11.1, 33.3] | **0.0% [0.0, 0.0]** | 42.9% [14.3, 71.4] | **0.0% [0.0, 0.0]** | 74.1% [61.1, 85.2] | **0.0% [0.0, 0.0]** |
| Always clarify | — | 27.7% [19.1, 37.2] | 0.0% [0.0, 0.0] | **0.0% [0.0, 0.0]** | 0.0% [0.0, 0.0] | **0.0% [0.0, 0.0]** | 100.0% [100.0, 100.0] | **0.0% [0.0, 0.0]** |
| Always refuse | — | 14.9% [8.5, 22.3] | 0.0% [0.0, 0.0] | **0.0% [0.0, 0.0]** | **100.0% [100.0, 100.0]** | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** | **0.0% [0.0, 0.0]** |

Best mean among *all evaluated systems including the EX-ceiling naive* is **bold**, second is <u>underlined</u> (ties share the mark). Higher is better for TA / Compute Acc / CRR; lower is better for FAR / Missed / UCR / DSR. Always-* are calibrators and still participate in FAR/CRR marks.

## Paired official-TA vs naive_surface

| System | ΔTA (pp) | bootstrap 95% CI | p_boot | McNemar mid-p | W/T/L |
|---|---:|---:|---:|---:|---|
| Claude Opus 5.5 | −3.2 | [−20.2, 13.8] | 0.7600 | 0.716 (b01=35, b10=32) | 32/27/35 |
| Claude Opus 5 | −5.3 | [−22.3, 11.7] | 0.5984 | 0.556 (b01=38, b10=33) | 33/23/38 |
| GPT-6-luna | −10.6 | [−28.7, 7.4] | 0.2706 | 0.248 (b01=42, b10=32) | 32/20/42 |

None of the three paired CIs excludes 0. Naive / dict-default remain the official-TA *point-estimate* leaders (57.4%), which is exactly the compute fraction 54/94, and sit at the EX ceiling with FAR = 100%. GATE-INSIGHT-INVERT holds on the official fold for both deterministic and frontier systems.

## Mechanisms (gold-compute, n=54)

Same frozen FX / native-measure tension as on v0.1; gold was not retuned.

- **Opus 5**: 19 UCR, 1 unnecessary refuse, 34 computes (16 match gold, 1 DSR, 17 wrong values). Of the 34 compute SQLs, 22 use `net_paid_usd`, 4 use `ss_net_paid`. Gold-clarify 23/26; gold-refuse 10/14 (CRR 71.4%).
- **Opus 5.5**: only 5 UCR (lowest), 48 computes (19 match gold, 1 DSR, 28 wrong values); 34 of 48 compute SQLs use `net_paid_usd`. Gold-clarify 22/26; gold-refuse 10/14.
- **GPT-6-luna**: 40 UCR, FAR = 0, missed-clarify = 0 (26/26 gold-clarify correct); all 12 of its compute attempts match gold. Gold-refuse 6/14.

GATE-FRONTIER on the official held-out is *complete*: three pre-registered models, one-shot, no quota stop, no invented rows. They do not significantly beat naive, and their point estimates sit *below* naive on official TA.
