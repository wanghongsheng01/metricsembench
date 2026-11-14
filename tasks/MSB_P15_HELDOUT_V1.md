# Paper 15 official TPC-DS held-out TEST (`p15_heldout_v1`)

**Date:** 2026-11-12, America/Los_Angeles. **Hashed before any paper-15 official score.**
SHA-256 `03d26b59479d82ee7d6e71bb73f6bedc4db42204cf8c9d9124604adb53e55cb2`. `evaluated=false` at freeze.
n=94 (compute 54 / clarify 26 / refuse 14). Official TA denominator = 94.

## Why this fold

- The v0.1 85-item fixture is a **diagnostic / template** set: it preferentially includes the
  three population sign-flips, and a dictionary-grounded reference protocol reaches TA 100%
  on it. Those numbers are reported, with CIs, but they are not a held-out generalization claim.
- This fold is Paper 15's **own official TEST**. It is disjoint from v0.1, model-blind, and
  hash-frozen before any official score. It does **not** use, slice, or rescore paper-13
  official public-overlay TEST folds (v2 TEST `e021e41e…`, v3 `06c70d29…`, v4 `3f595525…` /
  commit dacc85f, v5 FALLBACK `d57a673f…` / commit 7945db0).
- There are **zero leftover sign-disagreement triples** after v0.1 (population: 3 of 528
  complete triples). Claiming a held-out "full of sign flips" would require inventing them.
  The held-out is therefore drawn from leftover *same-sign* magnitude-gap months and
  ordinary complete months, plus leftover years (1999, 2002) on the other semantic axes.
  Sign-flip *prevalence* is a first-class population result, reported separately.

## Selection (pre-registered)

Seed: `paper15_msb_tpcds_heldout_v1_seed_20261112`.

Calendar: leftover complete (year, month, category) triples not in v0.1. Within the
magnitude stratum (gap ≥ 2 pp, same sign, |calendar YoY| ≥ 1 pp) and the ordinary
decision-relevant stratum, items are sorted by `sha256(seed|yr|moy|cat)` and the first
8 / 8 are taken. **Not** sorted by gap. Leftover pool: magnitude 34, ordinary 424, sign 0.

Other axes: years 1999 and 2002 (v0.1 used 2000 and 2001). Gold SQL is re-executed on
official TPC-DS SF=1; values are not invented. Sparse refuse uses May 2002 vs May 2001
and excludes v0.1 item ids and brands.

## Scoring (required)

Official tables **must** report bootstrap 95% CIs (10,000 resamples, seed `20261112`)
and paired McNemar mid-p / paired bootstrap for headline contrasts (`msb.public_stats`
and `msb.paper15_stats`). Best bold, second underlined, W/T/L.

Paper 15 is an EA&B benchmark: the "gate" is whether the diagnostic claims hold on
this held-out and on the public overlay (EX ranking inversion; compute-vs-clarify-vs-refuse
profiles of strong published systems and frontier LLMs), not whether a sister-paper
method is #1.

## What this is not

- Not a second pass on v0.1, and not a paper-13 official TEST.
- Not to be used for prompt or threshold tuning after this freeze. Develop only on
  DEV (v0.1 + already-collected public overlay v1 DEV-style analyses). Evaluate this
  fold **once** after the protocol (including frontier-model prompts and reasoning
  settings) is frozen.

## Official evaluation (2026-11-12, America/Los_Angeles)

`evaluated` was flipped to `true` in a dedicated commit after the complete
official evaluation was reviewed: deterministic gold-blind baselines and a
one-shot frontier profile (Claude Opus 5, Opus 5.5, GPT-6-luna), all 94 ids,
zero API errors. Paper-13 official TEST folds were not used.

**Fold identity.** The official SHA-256
`03d26b59479d82ee7d6e71bb73f6bedc4db42204cf8c9d9124604adb53e55cb2`
is the *freeze* digest, computed with the official convention on the payload
with the `sha256` key removed and `evaluated=false`. Flipping this bookkeeping
flag changes a raw re-hash of the file as it stands; to verify task identity,
set `evaluated` back to `false` and re-hash. The 94 tasks and gold values are
byte-identical to the freeze.
