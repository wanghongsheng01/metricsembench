"""Compare regenerated result JSON against the shipped snapshot (numbers only, 1e-6 rel).

Usage: python -m msb.check_reproduction <expected_dir> <regenerated_dir> [file ...]
Exit 0 iff every listed file matches. Volatile keys (timestamps, paths) are ignored.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

IGNORE = {"generated_at", "timestamp", "wall_s", "elapsed_s", "db_path", "path", "created_at", "lower_better"}


def close(a, b, path="") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k in IGNORE:
                continue
            if k not in a or k not in b:
                out.append(f"{path}/{k}: missing on one side")
            else:
                out += close(a[k], b[k], f"{path}/{k}")
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: len {len(a)} != {len(b)}"]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += close(x, y, f"{path}[{i}]")
        return out
    if isinstance(a, bool) or isinstance(b, bool):
        return [] if a == b else [f"{path}: {a!r} != {b!r}"]
    if isinstance(a, float) and isinstance(b, float) and a != a and b != b:
        return []  # both NaN
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return [] if abs(a - b) <= 1e-6 * max(1.0, abs(b)) else [f"{path}: {a} != {b}"]
    return [] if a == b else [f"{path}: {str(a)[:60]!r} != {str(b)[:60]!r}"]


def main(argv: list[str]) -> int:
    exp, new = Path(argv[1]), Path(argv[2])
    files = argv[3:] or sorted(p.name for p in exp.glob("*.json"))
    bad = 0
    for f in files:
        d = close(json.loads((new / f).read_text()), json.loads((exp / f).read_text()))
        print(f"{'OK  ' if not d else 'DIFF'} {f}" + ("" if not d else f"  ({len(d)}) " + "; ".join(d[:3])))
        bad += bool(d)
    print("ALL MATCH" if not bad else f"{bad} file(s) differ")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
