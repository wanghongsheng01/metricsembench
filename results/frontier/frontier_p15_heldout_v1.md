# Frontier semantic profile — p15_heldout_v1 (merged from jsonl after parallel one-shot)

SHA `03d26b59479d82ee7d6e71bb73f6bedc4db42204cf8c9d9124604adb53e55cb2`. n=94. Frozen extras. Bootstrap CIs seed 20261112.
Paper-13 official TEST folds were not used. Replaces a raced single-system write.

| System | n | spent | TA | Compute Acc | FAR | CRR | Missed | UCR | DSR | stop |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| tokens1688_2_claude-opus-5_semantic_max | 94 | $2.574 | 52.1% [42.6, 61.7] | 29.6% [18.5, 42.6] | 10.0% [2.5, 20.0] | 71.4% [50.0, 92.9] | 11.5% [0.0, 26.9] | 35.2% [22.2, 48.1] | 1.9% [0.0, 5.6] | None |
| tokens1688_2_claude-opus-5-5_semantic_high | 94 | $2.018 | 54.3% [44.7, 63.8] | 35.2% [22.2, 48.1] | 17.5% [7.5, 30.0] | 71.4% [50.0, 92.9] | 15.4% [3.8, 30.8] | 9.3% [1.9, 18.5] | 1.9% [0.0, 5.6] | None |
| tokens1688_2_gpt-6-luna_semantic | 94 | $0.023 | 46.8% [37.2, 56.4] | 22.2% [11.1, 33.3] | 0.0% [0.0, 0.0] | 42.9% [14.3, 71.4] | 0.0% [0.0, 0.0] | 74.1% [61.1, 85.2] | 0.0% [0.0, 0.0] | None |
