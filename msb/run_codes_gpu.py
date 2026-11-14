#!/usr/bin/env python3
"""DEV-only CodeS-7B-Spider profile on MetricSemBench v0.1.

Always-answer Text-to-SQL: official seeklhy/codes-7b-spider checkpoint,
official prompt (schema_sequence + content_sequence + question + newline),
generation num_beams=4, num_return_sequences=4, max_new_tokens=256, as in
RUCKBReasoning/codes text2sql_zero_shot.py.

Loads in 4-bit (bitsandbytes NF4) and caps CUDA at 16 GiB (a 24 GB A10 shared with
another resident process in our runs).

Does NOT wrap CodeS in compute/clarify/refuse instructions.
Does NOT load paper-13 folds. DEV (v0.1) only.

Writes a JSONL of the four beam SQLs per id. Execution and official scoring
happen on the box against the local DuckDB (first executable beam wins).
Resume: skip ids already present with a non-error row.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Isolated caches
ROOT = Path(os.environ.get("MSB_CODES_ROOT", "codes_run"))
os.environ.setdefault("HF_HOME", str(ROOT / "hf"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(ROOT / "hf" / "hub"))


def load_done(path: Path) -> set[str]:
    done = set()
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("id") and not r.get("error"):
            done.add(r["id"])
    return done


def post_process(sql: str) -> str:
    sql = (sql or "").replace("\n", " ").strip()
    if sql.endswith(";"):
        sql = sql[:-1].strip() + ";"
    # take first statement
    if ";" in sql[:-1]:
        sql = sql.split(";", 1)[0].strip() + ";"
    return sql


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "models" / "codes-7b-spider"))
    ap.add_argument("--prompts", default=str(ROOT / "work" / "v0.1_codes_prompts.json"))
    ap.add_argument("--out", default=str(ROOT / "preds" / "v0.1_codes_beams.jsonl"))
    ap.add_argument("--max-new-tokens", type=int, default=256)
    ap.add_argument("--max-prefix", type=int, default=4096 - 256)
    ap.add_argument("--limit", type=int, default=0, help="DEV smoke limit; 0 = all 85")
    ap.add_argument("--max-memory-gib", type=float, default=16.0)
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    prompts = json.loads(Path(args.prompts).read_text())["rows"]
    if args.limit:
        prompts = prompts[: args.limit]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(out)
    todo = [r for r in prompts if r["id"] not in done]
    print(f"prompts={len(prompts)} done={len(done)} todo={len(todo)} model={args.model}", flush=True)
    if not todo:
        print("nothing to do")
        return 0

    # Confirm we are not the co-resident service
    print("cuda", torch.cuda.is_available(), "mem_alloc", torch.cuda.memory_allocated() if torch.cuda.is_available() else 0, flush=True)
    if torch.cuda.is_available():
        free, total = torch.cuda.mem_get_info()
        print(f"cuda free={free/1e9:.2f}G total={total/1e9:.2f}G", flush=True)

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )
    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tok.pad_token_id is None:
        tok.pad_token_id = tok.eos_token_id
    max_mem = {0: f"{args.max_memory_gib:.0f}GiB"}
    print("loading 4-bit with max_memory", max_mem, flush=True)
    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=bnb,
        device_map="auto",
        max_memory=max_mem,
        torch_dtype=torch.float16,
        trust_remote_code=True,
        low_cpu_mem_usage=True,
    )
    model.eval()
    print(f"loaded in {time.time()-t0:.1f}s", flush=True)

    with out.open("a", encoding="utf-8") as fp:
        for i, row in enumerate(todo, 1):
            prefix = row["prefix"]
            ids = [tok.bos_token_id] + tok(prefix, truncation=False)["input_ids"]
            if len(ids) > args.max_prefix:
                ids = [tok.bos_token_id] + ids[-(args.max_prefix - 1) :]
            inputs = {
                "input_ids": torch.tensor([ids], dtype=torch.int64).to(model.device),
                "attention_mask": torch.tensor([[1] * len(ids)], dtype=torch.int64).to(model.device),
            }
            t1 = time.time()
            rec = {"id": row["id"], "n_prefix": len(ids)}
            try:
                with torch.no_grad():
                    gen = model.generate(
                        **inputs,
                        max_new_tokens=args.max_new_tokens,
                        num_beams=4,
                        num_return_sequences=4,
                        pad_token_id=tok.pad_token_id,
                    )
                texts = tok.batch_decode(gen[:, len(ids) :], skip_special_tokens=True, clean_up_tokenization_spaces=False)
                sqls = [post_process(s) for s in texts]
                rec.update({"sqls": sqls, "raws": texts, "elapsed_s": round(time.time() - t1, 2), "error": None})
            except Exception as e:
                rec.update({"sqls": [], "error": type(e).__name__, "err": str(e)[:400], "elapsed_s": round(time.time() - t1, 2)})
                print(f"ERROR {row['id']} {rec['error']} {rec.get('err','')[:200]}", flush=True)
                fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fp.flush()
                # API/runtime errors: stop this system, do not keep going as if scored
                return 2
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fp.flush()
            print(f"{i}/{len(todo)} {row['id']} {rec['elapsed_s']}s sql0={sqls[0][:120] if sqls else ''}", flush=True)
    print("DONE", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
