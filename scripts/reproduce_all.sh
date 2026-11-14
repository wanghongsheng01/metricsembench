#!/usr/bin/env bash
# One-click reproduction of every MetricSemBench table from the frozen folds and stored predictions.
# No paid API call is made. Needs Python >= 3.10, ~2 GB RAM, ~1.5 GB disk, network for pip + DuckDB extension.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD; export PYTHONPATH=$ROOT
PY=${PY:-python3}
step(){ echo; echo "=== $* ==="; }
step "0. integrity of the shipped package (MANIFEST.sha256)"
sha256sum -c --quiet MANIFEST.sha256 && echo "manifest OK"
step "1. environment"
[ -x .venv/bin/python ] || $PY -m venv .venv
.venv/bin/pip install -q -r requirements.txt
P=.venv/bin/python
rm -rf _expected _shipped_tasks && mkdir -p _expected && cp results/paper15_official/*.json _expected/ && cp -r tasks _shipped_tasks
step "2. regenerate official TPC-DS SF=1 warehouse + SHA-pinned extension (dsdgen; a few minutes)"
$P -m msb.generate_db
step "3. fold identity: freeze SHA-256 of every shipped fold"
$P - <<'PY'
import json, hashlib, pathlib
def freeze(d):
    p = {k: v for k, v in d.items() if k != "sha256"}
    if "evaluated" in p: p["evaluated"] = False
    return hashlib.sha256((json.dumps(p, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n").encode()).hexdigest()
exp = {"tasks/msb_p15_heldout_v1_tasks.json": "03d26b59479d82ee7d6e71bb73f6bedc4db42204cf8c9d9124604adb53e55cb2",
       "tasks/msb_p15_heldout_v2_tasks.json": "abe30e25701882ef9ad3b9a53fefbe641b8c7aa2b0932b0cf8dab11d68c4db97",
       "data/public_bench/msb_public_overlay_v1_150.json": "4d8bd8fadab86a0222f0a6ff5eb090f5da7b248f98a8f56723397e79758f3c12"}
bad = 0
for f, h in exp.items():
    got = freeze(json.loads(pathlib.Path(f).read_text()))
    print(("OK  " if got == h else "FAIL"), f, got[:16]); bad += got != h
raise SystemExit(bad)
PY
step "4. regenerate folds from the generator and compare to the frozen payloads"
$P -m msb.build_tasks >/dev/null
$P -m msb.build_paper15_heldout >/dev/null
$P -m msb.build_paper15_heldout_v2 >/dev/null
$P - <<'PY'
import json, hashlib, pathlib
def body(d):
    p = {k: v for k, v in d.items() if k not in ("sha256", "evaluated", "evaluated_at", "evaluated_commit")}
    return p["tasks"]
bad = 0
for f in ("msb_v0.1_tasks.json", "msb_p15_heldout_v1_tasks.json", "msb_p15_heldout_v2_tasks.json"):
    a = json.loads(pathlib.Path("tasks", f).read_text()); b = json.loads(pathlib.Path("_shipped_tasks", f).read_text())
    same = body(a) == body(b)
    print(("OK  " if same else "FAIL"), f, "regenerated tasks (ids, questions, gold, paired gold) identical to frozen"); bad += not same
raise SystemExit(bad)
PY
rm -rf tasks && mv _shipped_tasks tasks   # always evaluate the frozen payloads
step "5. mechanical gold audit (re-execute every gold and paired SQL)"
$P -m msb.audit_gold | tail -6
$P -m msb.audit_gold_v2 | tail -4
step "6. recompute every table from stored predictions"
$P -m msb.paper15_stats >/dev/null
$P -m msb.eval_heldout_deterministic >/dev/null
$P -m msb.frontier_stats >/dev/null
$P -m msb.prevalence_atlas >/dev/null
if [ -f results/codes/v0.1_codes_beams.jsonl ]; then $P -m msb.score_codes >/dev/null; fi
if [ -f results/codes/p15_heldout_v2_codes_beams.jsonl ]; then $P -m msb.score_codes_v2 >/dev/null; fi
$P -m msb.paper15_v2_stats >/dev/null
$P -m msb.paper15_mix_analysis >/dev/null
$P -m msb.paper15_v2_axis >/dev/null
$P -m msb.card_ablation_stats >/dev/null
step "7. compare regenerated numbers with the shipped snapshot"
$P -m msb.check_reproduction _expected results/paper15_official
step "8. companion-fold guard"
$P - <<'PY'
from pathlib import Path
from msb.forbidden_folds import assert_allowed_task_path
try:
    assert_allowed_task_path(Path("msb_public_overlay_v4_test.json")); print("FAIL guard did not refuse")
except Exception as e:
    print("OK   guard refuses companion TEST folds:", type(e).__name__)
PY
echo; echo "DONE"
