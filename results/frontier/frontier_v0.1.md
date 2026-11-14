# Frontier semantic profile — v0.1 (merged from per-system jsonl after parallel runs)

SHA `—` (v0.1 diagnostic fixture). n=85. Frozen extras as in 实验协议. Bootstrap CIs seed 20261112.
Paper-13 official TEST folds were not used. This file replaces a raced single-system write.

| System | n | spent | TA | Compute Acc | FAR | CRR | Missed | UCR | DSR | stop |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| tokens1688_2_claude-opus-5_semantic_max | 85 | $2.234 | 57.6% [47.1, 68.2] | 29.5% [15.9, 43.2] | 7.3% [0.0, 17.1] | 85.0% [70.0, 100.0] | 4.8% [0.0, 14.3] | 36.4% [22.7, 50.0] | 4.5% [0.0, 11.4] | None |
| tokens1688_2_claude-opus-5-5_semantic_high | 85 | $1.793 | 55.3% [44.7, 65.9] | 34.1% [20.5, 47.7] | 9.8% [2.4, 19.5] | 85.0% [70.0, 100.0] | 14.3% [0.0, 28.6] | 18.2% [6.8, 29.5] | 4.5% [0.0, 11.4] | None |
| tokens1688_2_gpt-6-luna_semantic | 85 | $0.019 | 42.4% [31.8, 52.9] | 18.2% [6.8, 29.5] | 0.0% [0.0, 0.0] | 40.0% [20.0, 60.0] | 0.0% [0.0, 0.0] | 77.3% [63.6, 88.6] | 0.0% [0.0, 0.0] | None |
