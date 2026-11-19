"""G-GRAPH-IDS — the transcript door sees EVERY row, so a turn's ID is stable (memory-graph Task 1).

WHAT THIS HOLDS. `transcript.all_rows` is the graph's only reader of the day files. Turn IDs
are `oid` or `t:<day>:<line index>`; the index is only stable if it counts every physical line
(blank and malformed ones too) and if untimed / synthetic rows are returned rather than
skipped the way `his_turns` skips them. `his_turns` must stay exactly as it was.

THE FIXTURE (harness_tests/fixtures/graph/, shared by every later graph gate; synthetic text).
  day 2026-01-01: 0 timed user turn; 1 her timed answer with an oid; 2-3 an UNTIMED user/assistant
    pair; 4 a MALFORMED line; 5 a synthetic:true user turn; 6-7 two rows with identical
    role+content+at.
  day 2026-01-02: 0 timed user "my cat is called Tuffy"; 1 her answer; 2 his timed turn saying the
    PIN in words; 3 an untimed "PIN 4417" turn; 4 her timed reply quoting the value; 5 an untimed
    turn naming only "PIN"; 6 an untimed everyday turn (the secret turns are G-GRAPH-LIVE-ONLY's).
  registry: live "Sam's cat is called Tuffy" (first_seen 2 min after the day-2 user turn);
    a retired row superseded_by that fact; a retired row superseded_by a name NOT in the
    registry; a distillate derived_from two live rows; a private-secret row; a live self row.

MUTANT (run 2026-11-03): enumerate only parsed lines in all_rows -> "line index counts the
malformed line" goes red.

NODE IDS (memory-graph Task 2): `nodes.collect` gives each turn its `oid` or `t:<day>:<line>`
and each fact its registry name; IDs are unique, stable across collects, and appending a row
never renumbers an older one. MUTANT (run 2026-11-03): ignore `oid` in `turn_id` -> "oid wins
when present" goes red.
"""
from __future__ import annotations

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
sb = sandbox("g_graph_ids")
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from harness.model import transcript  # noqa: E402
from harness.skills import graph  # noqa: E402

FX = os.path.join(HERE, "fixtures", "graph")
REG = os.path.join(sb, "memory", "registry.jsonl")
shutil.copyfile(os.path.join(FX, "registry.jsonl"), REG)
shutil.copytree(os.path.join(FX, "transcripts"), os.path.join(sb, "memory", "transcripts"))

N_PARSEABLE = 14                                  # 7 on day 1 (8 lines minus the malformed one) + 7
EXPECTED_DAY1_INDICES = [0, 1, 2, 3, 5, 6, 7]     # 4 is the malformed line and is skipped, not renumbered
# Hand-computed from the fixture: timed, non-synthetic user turns, newest first.
HIS_TURNS_BEFORE = [
    (1767344640.0, {"remember", "number", "bank", "sam", "four", "one", "seven"}),
    (1767344400.0, {"tuffy", "called", "cat"}),
    (1767268800.0, {"after", "repeat"}),
    (1767268800.0, {"after", "repeat"}),
    (1767261600.0, {"morning", "speaking", "fixture", "synthetic"}),
]

rows = transcript.all_rows(REG)
check("all_rows reads the fixture", rows is not None)
rows = rows or []
check("every parseable row is returned, untimed included", len(rows) == N_PARSEABLE, len(rows))
check("untimed rows are present", any("at" not in r for _, _, r in rows))
check("synthetic rows are present", any(r.get("synthetic") for _, _, r in rows))
check("line index counts the malformed line",
      [i for d, i, _ in rows if d == "2026-01-01"] == EXPECTED_DAY1_INDICES)
check("oldest day first, file order", [d for d, _, _ in rows] == ["2026-01-01"] * 7 + ["2026-01-02"] * 7)
check("his_turns unchanged", transcript.his_turns(REG) == HIS_TURNS_BEFORE)
check("unreadable directory is None", transcript.all_rows(os.path.join(sb, "nowhere", "registry.jsonl")) is None)

# --- node IDs (Task 2) -------------------------------------------------------------------
HER_OID = "o-fx-answer-1"
ID_AFTER_MALFORMED = "t:2026-01-01:5"             # the synthetic turn sits after the malformed line 4
ns = graph.nodes.collect(REG)
ids = [n["id"] for n in ns]
check("ids unique even for identical turns", len(ids) == len(set(ids)))
check("the identical pair gets two positional ids", "t:2026-01-01:6" in ids and "t:2026-01-01:7" in ids)
check("oid wins when present", HER_OID in ids and "t:2026-01-01:1" not in ids)
check("positional id for the rest", "t:2026-01-01:0" in ids)
check("malformed line keeps later ids", ID_AFTER_MALFORMED in ids)
check("facts keep their registry name", "ep_live_1767261600001" in ids)
check("stable across two collects", ids == [n["id"] for n in graph.nodes.collect(REG)])
# The retired flag follows lifecycle (1 = retired). A fixture with the flags inverted once made
# every "live" row retired and graded nothing; pin both sides so a re-inversion fails by name.
by_id = {n["id"]: n for n in ns}
check("the superseded cat row is flagged retired", by_id["ep_live_1767261600002"].get("retired") is True)
check("the live cat row is not flagged retired", not by_id["ep_live_1767261600001"].get("retired"))
day1 = os.path.join(sb, "memory", "transcripts", "2026-01-01.jsonl")
with open(day1, "a", encoding="utf-8") as f:
    f.write('{"role": "user", "content": "Appended later.", "at": 1767272400000}\n')
after_append_ids = [n["id"] for n in graph.nodes.collect(REG)]
check("appending a row changes no existing id", set(ids) <= set(after_append_ids))
check("the appended row got the next index", "t:2026-01-01:8" in after_append_ids)

finish("G-GRAPH-IDS")
