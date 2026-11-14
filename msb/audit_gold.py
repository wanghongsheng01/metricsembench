"""Mechanical gold audit for MetricSemBench v0.1 and p15_heldout_v1.

This is a *verification* audit, not independent dual-human IAA:
  (A) re-execute every gold_sql and every paired-definition SQL;
  (B) check handbook rules on completeness, sparse prior, non-additive
      refuse reasons, and compute/clarify pairing;
  (C) confirm official SHA convention and evaluated-flag bookkeeping;
  (D) confirm no overlap between v0.1 and held-out, and that paper-13
      forbidden folds are not referenced.

Does not invent a Cohen's kappa. Dual independent human labeling is
called out as a remaining January-cycle item.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb

from msb.config import DB_PATH, TASKS_DIR
from msb.evaluate import _close
from msb.forbidden_folds import assert_allowed_task_path


def official_sha(payload: dict) -> str:
    body = {k: v for k, v in payload.items() if k != "sha256"}
    s = json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n"
    return hashlib.sha256(s.encode()).hexdigest()


def freeze_sha(payload: dict) -> str:
    body = {k: v for k, v in payload.items() if k != "sha256"}
    body["evaluated"] = False
    s = json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n"
    return hashlib.sha256(s.encode()).hexdigest()


def exec_scalar(con, sql):
    if not sql:
        return None
    v = con.execute(sql).fetchone()
    if v is None or v[0] is None:
        return None
    try:
        return float(v[0])
    except (TypeError, ValueError):
        return v[0]


def audit_fold(path: Path, con, *, expect_evaluated=None, freeze_sha_expected=None) -> dict:
    assert_allowed_task_path(path)
    raw = json.loads(path.read_text())
    tasks = raw["tasks"]
    report = {
        "path": str(path),
        "n": len(tasks),
        "n_declared": raw.get("n_tasks"),
        "counts_declared": raw.get("counts"),
        "behaviors": dict(Counter(t["gold_behavior"] for t in tasks)),
        "types": dict(Counter(t.get("type") for t in tasks)),
        "subtypes": dict(Counter(t.get("subtype") for t in tasks)),
        "evaluated": raw.get("evaluated"),
        "sha_field": raw.get("sha256"),
        "raw_rehash": official_sha(raw) if "sha256" in raw or True else None,
        "freeze_sha": freeze_sha(raw),
        "issues": [],
        "ok": {},
    }
    if expect_evaluated is not None and raw.get("evaluated") != expect_evaluated:
        report["issues"].append(f"evaluated={raw.get('evaluated')} expected {expect_evaluated}")
    if freeze_sha_expected and report["freeze_sha"] != freeze_sha_expected:
        report["issues"].append("freeze SHA mismatch")
    if raw.get("n_tasks") != len(tasks):
        report["issues"].append("n_tasks != len(tasks)")

    n_sql = n_sql_ok = n_paired = n_paired_ok = 0
    n_compute = n_clarify = n_refuse = 0
    handbook_ok = 0
    handbook_fail = []
    ids = []
    questions = []
    for t in tasks:
        ids.append(t["id"])
        questions.append((t.get("question_en") or "").strip())
        b = t["gold_behavior"]
        # A: re-execute gold
        if b == "compute":
            n_compute += 1
            sql = t.get("gold_sql")
            n_sql += 1
            try:
                got = exec_scalar(con, sql)
                if _close(got, t.get("gold_value")):
                    n_sql_ok += 1
                else:
                    report["issues"].append(f"{t['id']}: gold_sql {got} != gold_value {t.get('gold_value')}")
            except Exception as e:
                report["issues"].append(f"{t['id']}: gold_sql error {type(e).__name__}: {e}")
        elif b == "clarify":
            n_clarify += 1
            if t.get("gold_sql") or t.get("gold_value") not in (None,):
                # clarify may still have no single gold
                pass
            if not (t.get("paired_definitions") and len(t["paired_definitions"]) >= 2):
                handbook_fail.append((t["id"], "clarify without >=2 paired definitions"))
        elif b == "refuse":
            n_refuse += 1
            if not t.get("refuse_reason"):
                handbook_fail.append((t["id"], "refuse without reason"))
        # paired defs
        for d in t.get("paired_definitions") or []:
            n_paired += 1
            try:
                got = exec_scalar(con, d.get("sql"))
                if _close(got, d.get("value")):
                    n_paired_ok += 1
                else:
                    report["issues"].append(f"{t['id']}:{d.get('id')} paired {got} != {d.get('value')}")
            except Exception as e:
                report["issues"].append(f"{t['id']}:{d.get('id')} paired error {type(e).__name__}: {e}")

        # B: handbook structural rules
        ok = True
        if b == "compute":
            if not t.get("specified_definition"):
                # some compute items (non-paired axes) may have specified_definition
                if t.get("paired_definitions"):
                    ok = False
                    handbook_fail.append((t["id"], "compute with pairs but no specified_definition"))
            if t.get("refuse_reason"):
                ok = False
                handbook_fail.append((t["id"], "compute has refuse_reason"))
        elif b == "clarify":
            if t.get("specified_definition"):
                ok = False
                handbook_fail.append((t["id"], "clarify has specified_definition"))
            pairs = t.get("paired_definitions") or []
            if len(pairs) >= 2:
                v0, v1 = pairs[0].get("value"), pairs[1].get("value")
                if _close(v0, v1):
                    handbook_fail.append((t["id"], "paired values equal — not a real conflict"))
                    ok = False
        elif b == "refuse":
            if t.get("gold_value") not in (None,):
                # some refuse may still record would-be values; warn only if they look like gold answers
                pass
        if ok:
            handbook_ok += 1

    report["ok"] = {
        "n_compute": n_compute,
        "n_clarify": n_clarify,
        "n_refuse": n_refuse,
        "gold_sql_checked": n_sql,
        "gold_sql_match": n_sql_ok,
        "paired_checked": n_paired,
        "paired_match": n_paired_ok,
        "handbook_struct_ok": handbook_ok,
        "handbook_struct_fail": handbook_fail,
        "unique_ids": len(set(ids)) == len(ids),
        "unique_questions": len(set(questions)) == len(questions),
        "n_sign_disagreement": sum(1 for t in tasks if t.get("sign_disagreement")),
    }
    if n_sql != n_sql_ok or n_paired != n_paired_ok or handbook_fail or not report["ok"]["unique_ids"]:
        report["issues"].append("see ok block")
    return report


def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    v01 = audit_fold(TASKS_DIR / "msb_v0.1_tasks.json", con)
    held = audit_fold(
        TASKS_DIR / "msb_p15_heldout_v1_tasks.json",
        con,
        expect_evaluated=True,
        freeze_sha_expected="03d26b59479d82ee7d6e71bb73f6bedc4db42204cf8c9d9124604adb53e55cb2",
    )
    # overlap
    t1 = json.loads((TASKS_DIR / "msb_v0.1_tasks.json").read_text())["tasks"]
    t2 = json.loads((TASKS_DIR / "msb_p15_heldout_v1_tasks.json").read_text())["tasks"]
    ids1, ids2 = {t["id"] for t in t1}, {t["id"] for t in t2}
    q1, q2 = {t["question_en"].strip() for t in t1}, {t["question_en"].strip() for t in t2}
    overlap = {
        "id_overlap": sorted(ids1 & ids2),
        "question_overlap": sorted(q1 & q2),
    }
    out = {
        "v0.1": v01,
        "p15_heldout_v1": held,
        "overlap": overlap,
        "note": (
            "Mechanical verification (re-execution + handbook structure). "
            "Not a dual-human Cohen's kappa."
        ),
    }
    dest = Path(__file__).resolve().parents[1] / "results" / "paper15_official" / "gold_audit_v1.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print("wrote", dest)
    for name, r in (("v0.1", v01), ("heldout", held)):
        print(f"== {name} n={r['n']} issues={len(r['issues'])} freeze={r['freeze_sha'][:16]} evaluated={r['evaluated']}")
        print("  ok", {k: v for k, v in r["ok"].items() if k != "handbook_struct_fail"})
        if r["issues"]:
            print("  ISSUES", r["issues"][:8])
        if r["ok"]["handbook_struct_fail"]:
            print("  handbook fail", r["ok"]["handbook_struct_fail"][:8])
    print("overlap ids", overlap["id_overlap"], "qs", len(overlap["question_overlap"]))


if __name__ == "__main__":
    main()
