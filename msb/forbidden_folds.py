"""Paper-13 official TEST folds that Paper 15 must NEVER load or evaluate.

These folds were hash-frozen for BindOrClarify (paper 13) one-shot official
scoring. Evaluating them here would burn or contaminate paper 13's official
TEST. All paper-15 runners must call `assert_allowed_task_path` before load.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# SHA-256 of the frozen JSON as stored in the file's `sha256` field
# (computed over the payload with the sha256 key itself removed, indent=2,
# sort_keys=True — see the v4/v5 builders). We also refuse these filenames.
FORBIDDEN_SHA256 = {
    "3f595525578b47a5a7efe1019875e84361b79b40cbea2d290295d943307e54f3": (
        "paper-13 official v4 TEST (commit dacc85f, n=471)"
    ),
    "d57a673f0f52cfa419fdc563901e72c2f97b33e4ff11fea5d6ab848568add3bf": (
        "paper-13 FALLBACK v5 TEST (commit 7945db0, n=162)"
    ),
    "06c70d29c73088cb1434af5d782c60f3d66acd6b4810be1872fbbcd68fcd8837": (
        "paper-13 leftover v3 TEST (commit 3b0ef11, n=87)"
    ),
    "e021e41ed1840f3e5a12f944c7b5c8ca579216e93df45711a6855d91c0b4b18f": (
        "paper-13 v2 TEST (commit 5b3e6fa, n=83)"
    ),
}

FORBIDDEN_FILENAMES = {
    "msb_public_overlay_v4_test.json",
    "msb_public_overlay_v5_fallback_test.json",
    "msb_public_overlay_v3_test.json",
    "msb_public_overlay_v2_test.json",
}


def _file_sha_field(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        return payload.get("sha256")
    return None


def assert_allowed_task_path(path: Path | str) -> Path:
    p = Path(path).resolve()
    name = p.name
    if name in FORBIDDEN_FILENAMES:
        raise RuntimeError(
            f"REFUSED: {name} is a paper-13 official/fallback TEST fold and "
            f"must not be loaded or evaluated by paper 15. "
            f"({FORBIDDEN_SHA256.get(_file_sha_field(p) or '', 'see forbidden_folds.py')})"
        )
    sha = _file_sha_field(p)
    if sha and sha in FORBIDDEN_SHA256:
        raise RuntimeError(
            f"REFUSED: {p} has frozen sha256 {sha} ({FORBIDDEN_SHA256[sha]}). "
            "Paper 15 must not evaluate paper-13 official TEST folds."
        )
    return p


def is_forbidden(path: Path | str) -> bool:
    try:
        assert_allowed_task_path(path)
    except RuntimeError:
        return True
    return False
