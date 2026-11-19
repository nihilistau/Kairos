"""G-GRAPH-RULES — the four edge rules over the shared graph fixture (memory-graph Task 2).

WHAT THIS HOLDS. `rules.apply` turns nodes into edges by four versioned rules (explicit,
sequence, day, minted_from). An edge is kept only if BOTH ends are nodes, and every dropped
edge is counted against its rule — so a dangling `superseded_by` is a number, not a silence.
Untimed turns take part in `sequence` and `day` but never in `minted_from` (no timestamp, no
honest "just before"). Every edge names its rule and version.

FIXTURE: harness_tests/fixtures/graph/ (see g_graph_ids.py). Hand-computed expectations:
the cat fact (first_seen 09:02) was minted by the 09:00 Tuffy turn, 2 minutes earlier.

MUTANTS (run 2026-11-03):
  (a) `apply` keeps edges with a missing end -> "dangling superseded_by is dropped and
      counted" and "an edge is only written between nodes" go red.
  (b) `_minted_from` admits untimed turns (drop the `at is not None` filter and skip the
      window test when a turn has no `at`) -> "untimed turns never get minted_from" goes red.
"""
from __future__ import annotations

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
sb = sandbox("g_graph_rules")
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from harness.skills import graph  # noqa: E402

FX = os.path.join(HERE, "fixtures", "graph")
REG = os.path.join(sb, "memory", "registry.jsonl")
shutil.copyfile(os.path.join(FX, "registry.jsonl"), REG)
shutil.copytree(os.path.join(FX, "transcripts"), os.path.join(sb, "memory", "transcripts"))

LIVE_CAT = "ep_live_1767261600001"
RETIRED = "ep_live_1767261600002"
LAMPS = "ep_live_1767261600004"
DISTILLATE = "ep_live_1767261600005"
HER_REPLY = "t:2026-01-02:1"
HIS_TURN = "t:2026-01-02:0"
TUFFY_TURN = HIS_TURN
CAT_FACT = LIVE_CAT
UNTIMED_ID = "t:2026-01-01:2"
ALL = ["explicit", "sequence", "day", "minted_from"]

nodes = graph.nodes.collect(REG)
edges, dropped = graph.rules.apply(nodes, ALL)
E = {(e["type"], e["from"], e["to"]) for e in edges}
ids = {n["id"] for n in nodes}

check("the five rules are registered at version 1 (activity: G-GRAPH-ACTIVITY)",
      {k: r.version for k, r in graph.RULES.items()} == {k: 1 for k in ALL + ["activity"]})
check("supersedes edge from live to retired", ("supersedes", LIVE_CAT, RETIRED) in E)
check("dangling superseded_by is dropped and counted", dropped["explicit"] == 1, dropped)
check("an edge is only written between nodes", all(e["from"] in ids and e["to"] in ids for e in edges))
check("derived_from yields two edges",
      len([e for e in edges if e["type"] == "derived_from"]) == 2)
check("derived_from runs distillate to support",
      ("derived_from", DISTILLATE, LIVE_CAT) in E and ("derived_from", DISTILLATE, LAMPS) in E)
check("answer_to links her reply to his turn", ("answer_to", HER_REPLY, HIS_TURN) in E)
check("answer_to reaches the nearest earlier user turn",
      ("answer_to", "o-fx-answer-1", "t:2026-01-01:0") in E
      and ("answer_to", "t:2026-01-01:3", UNTIMED_ID) in E)
check("next links consecutive turns in file order",
      ("next", "t:2026-01-01:0", "o-fx-answer-1") in E
      and ("next", "t:2026-01-01:3", "t:2026-01-01:5") in E)
check("next never crosses a day file", ("next", "t:2026-01-01:7", HIS_TURN) not in E)
check("untimed turns get sequence edges",
      any(e["from"] == UNTIMED_ID for e in edges if e["rule"] == "sequence"))
check("next_day links first turns of consecutive days",
      ("next_day", "t:2026-01-01:0", HIS_TURN) in E)
check("a fact joins the first turn of its day",
      ("same_day", CAT_FACT, HIS_TURN) in E and ("same_day", RETIRED, "t:2026-01-01:0") in E)
check("same_day is linear, one edge per fact",
      len([e for e in edges if e["type"] == "same_day"]) == len([n for n in nodes if n["kind"] == "fact"]))
check("untimed turns never get minted_from",
      not any(UNTIMED_ID in (e["from"], e["to"]) for e in edges if e["rule"] == "minted_from"))
check("the cat fact is minted from the Tuffy turn", ("minted_from", CAT_FACT, TUFFY_TURN) in E)
check("minted_from weight is overlap over fact tokens, above the floor",
      all(0.3 <= e["weight"] <= 1.0 for e in edges if e["rule"] == "minted_from"))
check("a synthetic turn is never a mint source",
      not any(e["to"] == "t:2026-01-01:5" for e in edges if e["rule"] == "minted_from"))
check("every edge names its rule and version",
      bool(edges) and all(e["rule"] and e["rule_version"] for e in edges))
check("apply is deterministic", (edges, dropped) == graph.rules.apply(graph.nodes.collect(REG), ALL))
only, d2 = graph.rules.apply(nodes, ["sequence"])
check("only the named rules run", {e["rule"] for e in only} == {"sequence"} and list(d2) == ["sequence"])
try:
    graph.rules.apply(nodes, ["nope"])
    check("an unknown rule name is loud", False)
except KeyError:
    check("an unknown rule name is loud", True)

# A fact first seen on a day with no transcript file: no same_day edge, counted under "day".
with open(REG, "a", encoding="utf-8") as f:
    f.write('{"name": "ep_live_1800000000001", "text": "Sam mentioned a ferry", "speaker": "user", '
            '"status": "live", "mem_class": "fact", "lifecycle": 0, "superseded_by": null, '
            '"derived_from": [], "first_seen": "2026-03-01T08:00:00Z", "last_seen": "2026-03-01T08:00:00Z", '
            '"ts": "2026-03-01T08:00:00Z", "kind": "fact", "src": "fixture"}\n')
e3, d3 = graph.rules.apply(graph.nodes.collect(REG), ["day"])
check("a fact on a day with no transcript gets no same_day edge",
      not any(e["from"] == "ep_live_1800000000001" for e in e3))
check("...and is counted in dropped_by_rule['day']", d3["day"] == 1, d3)

finish("G-GRAPH-RULES")
