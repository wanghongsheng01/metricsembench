# Public metric-ambiguity overlay v1 (≥150 official-grounded items)

**Date:** 2026-11-12, America/Los_Angeles. **Hashed before evaluation.** SHA-256 `4d8bd8fadab86a0222f0a6ff5eb090f5da7b248f98a8f56723397e79758f3c12`. `evaluated=false` at freeze. n=167 (compute_numeric 136, compute_behavior_only 19, clarify 12). Official TA denominator = 148.

## Composition

See `msb_public_overlay_v1_150.json`. The set includes:

- The v0 26-item cut (16 Spider 2.0-lite + 10 BIRD Mini-Dev HF questions, of which 6 have official scalar gold, 1 multi-column behavior-only, 8 clarify, 11 Spider compute behavior-only).
- An expansion from the **official 2024 BIRD Mini-Dev zip** (questions + evidence + gold SQL + SQLite in one package): metric-like items whose official SQL executed to a **single numeric scalar** on the official DB (15s timeout; 2 queries timed out and were dropped). Selection is deterministic (prefer rate/percentage/average/growth, then `question_id`, per-DB caps).

## Scoring (labelled tracks)

- **Official TA**: clarify/refuse (behavior) **plus** compute items with official numeric gold (value must match, rel/abs tolerance as in MetricSemBench).
- **Compute Acc**: only the numeric-gold compute slice.
- **Behavior-only compute** (Spider without a local DB; multi-column official results): **excluded** from official TA so an always-answer system cannot inflate TA. Reported separately as `behavior_match`.
- **FAR / missed clarify / UCR**: as usual. DSR / Illegal* are undefined on this overlay (no paired definitions / refuse slice) and shown as — .

## What this is not

- Not official Spider EX or BIRD EX as the *behavior* label. Numeric gold *is* official BIRD SQL execution, reused, never invented.
- `bindorclarify_v1` is a TPC-DS dictionary binder; transfer failure on public DBs is an honest expected result.

## Databases

Official SQLite files live in `bird_minidev/databases/` (gitignored, ~1.4GB). Install from `https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip`, extract `*.sqlite` only.
