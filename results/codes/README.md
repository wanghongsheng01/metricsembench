# CodeS-7B profile (published always-answer baseline)

- Checkpoint: official CodeS-7B Spider-SFT release (`seeklhy/codes-7b-spider`), loaded in 4-bit NF4 (bitsandbytes) on one 24 GB A10.
- Prompt: the authors' zero-shot prompt and schema sequence (`msb/codes_prompt.py`); beam search, beam 4; the first executable SQL is the prediction. No compute/clarify/refuse wrapper (always answers).
- Runner: `msb/run_codes_gpu.py` (writes beams JSONL; resumable). Scoring: `msb/score_codes.py` (v0.1), `msb/score_codes_v2.py` (held-out v2) re-execute the stored SQL on the regenerated warehouse.
- Stored beams: `v0.1_codes_beams.jsonl` (85/85), `p15_heldout_v2_codes_beams.jsonl` (250/250); prompts: `p15_heldout_v2_codes_prompts.json`.
- Results: v0.1 TA 3.5% [0.0, 8.2], Compute Acc 6.8%; held-out v2 TA 6.4% [3.6, 9.6], Compute Acc 12.1%. 48 of 85 v0.1 queries join the fact view to `item` on the business key `i_item_id` instead of the surrogate key.
