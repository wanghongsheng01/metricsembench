"""DEV-only sensitivity analysis: does stating the native-measure convention in the schema card
remove the frontier FX over-clarify / USD-substitution cluster?

Runs the three frontier systems on v0.1 (DEV, n=85) with ONE added card sentence (below);
everything else (instruction, extras, max_tokens, scorer, gold) is identical to the frozen
profile. Official folds are not touched and the frozen card of every official result is
unchanged. Checkpoints: results/frontier/card_native/v0.1__<system>.jsonl
"""
from __future__ import annotations

import argparse
import os
import sys

os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

from msb import run_frontier as RF
from msb.config import DB_PATH, RESULTS_DIR, TASKS_DIR

NATIVE_CLAUSE = (
    "\nMeasure convention (DEV sensitivity card): unless a question explicitly asks for USD or for a "
    "currency conversion, 'net sales' / 'net paid' means the native TPC-DS measure SUM(ss_net_paid) "
    "and needs no currency clarification. Only an explicit USD request uses net_paid_usd.\n"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True)
    ap.add_argument("--fold", default="v0.1", choices=["v0.1", "v2"],
                    help="v2 = post-hoc sensitivity on the already-evaluated held-out v2; official v2 rows are untouched")
    a = ap.parse_args()
    RF.SCHEMA_CARD = RF.SCHEMA_CARD + NATIVE_CLAUSE
    RF.CKPT_DIR = RESULTS_DIR / "frontier" / "card_native"
    RF.CKPT_DIR.mkdir(parents=True, exist_ok=True)
    if a.fold == "v2":
        payload, tasks = RF.load_fold(TASKS_DIR / "msb_p15_heldout_v2_tasks.json")
        fold, tag, cap = "p15_heldout_v2", RF.EXPERIMENT_V01 + "-cardnative-v2", 9.0
    else:
        payload, tasks = RF.load_fold(TASKS_DIR / "msb_v0.1_tasks.json")
        fold, tag, cap = "v0.1", RF.EXPERIMENT_V01 + "-cardnative", 6.0
    specs = [s for s in RF.SYSTEMS if a.system in s["name"]]
    assert len(specs) == 1, specs
    spec = dict(specs[0]); spec["soft_cap"] = cap
    r = RF.run_system(spec, tasks, fold, tag, DB_PATH)
    return 0 if r["n"] == len(tasks) else 2


if __name__ == "__main__":
    sys.exit(main())
