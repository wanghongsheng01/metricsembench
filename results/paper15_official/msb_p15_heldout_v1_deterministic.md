# Paper 15 official held-out v1 — deterministic baselines (first scores)

SHA-256 `03d26b59479d82ee7d6e71bb73f6bedc4db42204cf8c9d9124604adb53e55cb2`, n=94 (compute 54 / clarify 26 / refuse 14).
Bootstrap 95% CIs, 10,000 resamples, seed 20261112.
These are the first scores on this fold. Frozen with evaluated=false before this run.
Paper-13 official TEST folds were not used. No paid LLM in this file.

| System | n | TA | Compute Acc | FAR | CRR | Missed clarify | UCR | DSR | Illegal YoY | Illegal Agg |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| naive_surface | 94 | 57.4% [47.9, 67.0] | 100.0% [100.0, 100.0] | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | 100.0% [100.0, 100.0] |
| dict_default | 94 | 57.4% [47.9, 67.0] | 100.0% [100.0, 100.0] | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | 100.0% [100.0, 100.0] |
| always_refuse | 94 | 14.9% [8.5, 22.3] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] |
| always_clarify | 94 | 27.7% [19.1, 37.2] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 100.0% [100.0, 100.0] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] |

## EX vs TA on this held-out (deterministic systems)

If GATE-INSIGHT-INVERT holds, naive_surface should again sit at or near the EX ceiling
while official TA is pulled down by FAR on clarify∪refuse.

naive_surface: Compute Acc 100.0% [100.0, 100.0], TA 57.4% [47.9, 67.0], FAR 100.0% [100.0, 100.0].
