"""G-STRIP-EQUIVALENCE — the two strippers, held equal over one leak corpus. OFFLINE.

THE CLAIM. Every leak shape measured in her real transcripts (SWEEP-2026-08-24 F2) is
REMOVED, and every pass-through control SURVIVES, on BOTH sides of the display/record
split: Python `strip_for_record` (what the day transcript, her journal and the restart
seed keep) and the room's `ui/src/room/tags.js::extractTags` (what he reads). The corpus
is `fixtures/strip_corpus.jsonl` — one vocabulary, two enforcement points, one contract.

WHY REMOVAL AND NOT MATCHING. `tags_mirror_check.js` builds a regex from tags.js's own
source and asserts it MATCHES — and it was green for three weeks while the callback's
`if (!kind) return _m` handed every matched mark straight back to his screen: 26% of 539
recorded turns still carried markup. A gate that asserts the pattern rather than the
output measures the wrong path. This one calls the real functions and reads what a real
caller would get.

WHY BOTH DIRECTIONS. g_control_surface asserts Python→JS vocabulary presence only, so
five widenings that landed in the browser never landed in the file that writes her
memory ([VOX:], the bracketed [thinking paragraph, </the_end, the orphan >, the [MO
stub). This corpus is the other direction too: a shape added to either side without the
other goes red the same day.

MUTANTS (both verified red at authoring):
  (1) delete "vox" from stream_processor._TAG_ALIAS  -> the [VOX:] row fails on Python;
  (2) re-introduce tags.js's `if (!kind) return _m`  -> the widened-spelling rows fail
      on JS. §mutant below runs (1) live via monkeypatch — the gate carries its own
      Python mutant so the alias cannot quietly stop being load-bearing; (2) is a JS
      source change and stays a documented manual mutant.

Exit: 0 pass, 1 fail, 2 skip (no node on PATH — the JS half cannot run; the Python half
alone is not the claim).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _gate import check, finish, skip, utf8_stdout  # noqa: E402

utf8_stdout()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CORPUS = os.path.join(ROOT, "harness_tests", "fixtures", "strip_corpus.jsonl")
TAGS_JS = os.path.join(ROOT, "ui", "src", "room", "tags.js")
RUNNER = os.path.join(ROOT, "harness_tests", "strip_equiv_check.mjs")

from harness.inference.stream_processor import strip_for_record  # noqa: E402


def _rows() -> list:
    out = []
    with open(CORPUS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("why"):
                continue
            out.append(row)
    return out


def _judge(side: str, row: dict, got: str) -> None:
    label = "%s %r" % (side, row["input"][:48])
    for pat in row.get("must_not_match", []):
        check("%s removes /%s/" % (label, pat),
              not re.search(pat, got), "output: %r" % got[:120])
    for sub in row.get("must_keep", []):
        check("%s keeps %r" % (label, sub[:40]),
              sub in got, "output: %r" % got[:120])


rows = _rows()

# ── §1 the Python record lane, through the real function ────────────────────────────
for row in rows:
    if row.get("lanes", "both") in ("both", "py"):
        _judge("py", row, strip_for_record(row["input"]))

# ── §2 the JS display lane, through the real extractTags ────────────────────────────
node = shutil.which("node")
if not node:
    skip("node is not on PATH — the JS half of the equivalence cannot run",
         "G-STRIP-EQUIVALENCE")
try:
    out = subprocess.run([node, RUNNER, TAGS_JS, CORPUS], capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
except Exception as exc:  # pragma: no cover
    check("node runner executed", False, str(exc))
    finish("G-STRIP-EQUIVALENCE")
check("node runner exits 0", out.returncode == 0,
      (out.stderr or out.stdout)[:300])
js_texts = json.loads(out.stdout) if out.returncode == 0 else []
check("runner covered every corpus row", len(js_texts) == len(rows),
      "%d of %d" % (len(js_texts), len(rows)))
for row, got in zip(rows, js_texts):
    if row.get("lanes", "both") in ("both", "js"):
        _judge("js", row, got)

# ── §mutant: the alias table is load-bearing ────────────────────────────────────────
# Delete "vox" from the live table and the [VOX:] row must FAIL — a guard whose removal
# changes nothing is a guard that was never firing (the inert-widening lesson, F2).
from harness.inference import stream_processor as _sp  # noqa: E402

_saved = dict(_sp._TAG_ALIAS)
try:
    _sp._TAG_ALIAS.pop("vox", None)
    _vox = next(r for r in rows if "[VOX" in r["input"])
    got = strip_for_record(_vox["input"])
    check("mutant(no vox alias) leaks the mark — the alias is load-bearing",
          re.search(r"(?i)\[\s*VOX", got) is not None, "output: %r" % got[:120])
finally:
    _sp._TAG_ALIAS.clear()
    _sp._TAG_ALIAS.update(_saved)

finish("G-STRIP-EQUIVALENCE")
