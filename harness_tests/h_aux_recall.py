"""H-AUX-RECALL — do the librarians find HER moment? LIVE (the embed sidecar up), skip 2 otherwise.
(The set lives under fixtures/librarians/ — not fixtures/aux/: `aux` is a Windows reserved device name.)

A committed set of deep-memory prompts (harness_tests/fixtures/librarians/recall_set.json: question ->
the day that should come back, written by hand from real "do you remember" moments) scored four
ways — bare vs soft-prompted query, cosine vs spine rerank — as hit@1 / hit@4. The receipt lands
in gates/AUX-RECALL-<date>.md. This gate MEASURES; it does not assert a threshold until the set
has enough rows to mean something (>= 8), and even then only that the shipped configuration
(prefix + spine rerank) is not worse than bare cosine.

    python harness_tests/h_aux_recall.py
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# SANDBOX FIRST (2026-08-24). This gate calls tune.set_many(), which before today
# wrote HER LIVE var/tuning.json - it raced her running stack mid-sweep and died on
# the os.replace, and on a quieter day it would simply have changed what she does.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import sandbox as _sandbox  # noqa: E402
_sandbox(os.path.basename(__file__))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, skip, utf8_stdout  # noqa: E402

utf8_stdout()
SET = os.path.join(ROOT, "harness_tests", "fixtures", "librarians", "recall_set.json")

from harness.sidecar import client as C, archive as A   # noqa: E402
from harness.tuning import registry as R                # noqa: E402

if not C.available() or not C.reachable("embed"):
    skip("the aux embed sidecar is not up (SP_AUX=1 and :8811 answering) — this gate measures the live librarians", "H-AUX-RECALL")
try:
    rows = json.load(open(SET, encoding="utf-8"))
except Exception:
    rows = []
rows = [r for r in rows if isinstance(r, dict) and r.get("q") and r.get("day")]
if not rows:
    skip("recall_set is empty — fill harness_tests/fixtures/librarians/recall_set.json from real 'do you remember' moments", "H-AUX-RECALL")

print("1. THE SET, FOUR WAYS")
A.build_index()
_wq, _ws = R.chosen("aux.query_prefix"), R.chosen("aux.spine_rerank")


def _run(prefix_on: bool, spine_on: bool):
    if prefix_on:
        R.reset("aux.query_prefix") if _wq is None else R.set_many({"aux.query_prefix": _wq})
    else:
        R.set_many({"aux.query_prefix": ""})
    R.set_many({"aux.spine_rerank": bool(spine_on)})
    h1 = h4 = 0
    for r in rows:
        hits = A.search(r["q"], k=4, refresh=False)
        days = [h["day"][:10] for h in hits]
        if days and days[0] == r["day"][:10]:
            h1 += 1
        if r["day"][:10] in days:
            h4 += 1
    return h1, h4


try:
    res = {}
    for name, (p, s) in {"bare cosine": (False, False), "prefixed cosine": (True, False),
                         "bare + spine": (False, True), "prefixed + spine (shipped)": (True, True)}.items():
        res[name] = _run(p, s)
        print("   %-28s hit@1 %2d/%d  hit@4 %2d/%d" % (name, res[name][0], len(rows), res[name][1], len(rows)))
finally:
    R.reset("aux.query_prefix") if _wq is None else R.set_many({"aux.query_prefix": _wq})
    R.reset("aux.spine_rerank") if _ws is None else R.set_many({"aux.spine_rerank": _ws})

shipped, bare = res["prefixed + spine (shipped)"], res["bare cosine"]
check("the set has rows", len(rows) >= 1, len(rows))
if len(rows) >= 8:
    check("the shipped configuration is not worse than bare cosine at hit@4", shipped[1] >= bare[1], (shipped, bare))
else:
    print("   (fewer than 8 rows — measured, not asserted)")

day = time.strftime("%Y-%m-%d")
rp = os.path.join(ROOT, "gates", "AUX-RECALL-%s.md" % day)
with open(rp, "w", encoding="utf-8") as f:
    f.write("# AUX-RECALL receipt — %s\n\nembed model: `%s` · chat model: `%s` · rows: %d\n\n| configuration | hit@1 | hit@4 |\n|---|---|---|\n"
            % (day, os.path.basename(os.environ.get("SP_AUX_EMBED_GGUF", "?")), C.chat_model(), len(rows)))
    for k, (a, b) in res.items():
        f.write("| %s | %d/%d | %d/%d |\n" % (k, a, len(rows), b, len(rows)))
    f.write("\nquery soft-prompt: `%s`\n" % A.query_prefix())
print("   receipt -> gates/AUX-RECALL-%s.md" % day)

finish("H-AUX-RECALL")
