"""Per-axis official TA on p15_heldout_v2 from stored per-item predictions (no model is re-queried)."""
from __future__ import annotations

import collections
import json

from msb.config import RESULTS_DIR

SYSTEMS = ["tokens1688_2_claude-opus-5_semantic_max", "tokens1688_2_claude-opus-5-5_semantic_high",
           "tokens1688_gpt-6-sol_semantic", "ark_deepseek-v4-pro_semantic", "tokens1688_claude-sonnet-4-6_semantic",
           "tokens1688_2_gpt-6-luna_semantic", "ark_deepseek-v4-pro_dailsql", "naive_surface"]
AXES = ["calendar", "currency", "non_additive", "denominator", "lifecycle", "sparse_completeness"]


def main() -> None:
    d = RESULTS_DIR / "paper15_official" / "v2"
    out = {}
    for s in SYSTEMS:
        rows = {}
        for line in (d / f"p15_heldout_v2__{s}.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("id") and not r.get("error"):
                    rows[r["id"]] = r
        assert len(rows) == 250, (s, len(rows))
        c = collections.defaultdict(list)
        for r in rows.values():
            c[r["type"]].append(r["TA"])
        out[s] = {a: 100.0 * sum(c[a]) / len(c[a]) for a in AXES}
    p = RESULTS_DIR / "paper15_official" / "v2_per_axis_ta.json"
    p.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print("wrote", p)


if __name__ == "__main__":
    main()
