"""G-GRAPH-ACTIVITY — what he did in another app is a graph node, never a fact, never private.

WHAT THIS HOLDS (2026-11-08). Apps Kairos controls (Primer first) append what he did to
`activity/<app>/<day>.jsonl` beside the registry (`harness/model/activity.py` is the contract
and the one reader). The graph turns each kept row into an `app_event` node and the `activity`
rule links it in. The invariants:

  §1 THE READER. `activity.all_rows` keeps rows with an `event` and a `title`, drops PRIVATE
     rows before anything else sees them, skips malformed lines without renumbering, and skips
     an app directory or a file name it cannot use as part of an ID. `record` writes a row the
     reader reads back, and refuses a bad app name.
  §2 THE NODES. `a:<app>:<day>:<physical line>`, kind `app_event`, `at` in seconds; the private
     row and the malformed line are absent and nothing after them shifts.
  §3 THE RULE. `next` within an app-day file, `during` to the nearest timed turn within the
     window (weight falls with distance), `same_day` to the day's first turn. An untimed event
     gets no `during`. THE OLD RULES SEE TURNS ONLY: `sequence` and `day` edges are identical
     with and without the activity files, so an event can never be her `answer_to` or his `next`.
  §4 THE VIEW. An event reaches her labelled as an app event; one whose title carries a live
     secret's key token is the withheld note, as a turn is; an unknown kind still fails closed.
     A built graph offers the event as a neighbour of the turn it happened during.
  §5 DERIVED. Building leaves the activity files byte-identical; the summary counts events and
     the private rows it skipped.

FIXTURE: harness_tests/fixtures/graph/ plus its `activity/` (primer/2026-01-02.jsonl: 0 timed
"Kookaburra", 1 PRIVATE, 2 MALFORMED, 3 untimed "owls", 4 timed "Notes on PIN 4417", 5 no event;
`Bad App/` is not a valid app name; `primer/notes.jsonl` is not a day). Hand-computed: event 0
at 09:01:00 is 56 s after her reply t:2026-01-02:1 (60 s after his Tuffy turn), event 4 at
09:04:10 is 10 s after his turn t:2026-01-02:2.

MUTANTS (run by hand 2026-11-08, each restored):
  (a) the reader keeps private rows -> "a private row is never read" goes red.
  (b) `_turns_by_day` takes every non-fact node again -> an event becomes its own "nearest turn",
      so "during reaches the NEAREST timed turn" goes red and the gate stops there.
  (c) `_visible` skips the secret test for app events -> "an event carrying a secret's key token
      is withheld" goes red.

    python harness_tests/g_graph_activity.py
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
sb = sandbox("g_graph_activity")
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import harness.skills.memory as memory  # noqa: E402
from harness.model import activity  # noqa: E402
from harness.skills import graph  # noqa: E402
from harness.skills.graph import rules, view  # noqa: E402

FX = os.path.join(HERE, "fixtures", "graph")
REG = os.environ["SP_RECALL_REGISTRY"]
shutil.copyfile(os.path.join(FX, "registry.jsonl"), REG)
shutil.copytree(os.path.join(FX, "transcripts"), os.path.join(sb, "memory", "transcripts"))

ALL = ["explicit", "sequence", "day", "minted_from", "activity"]
nodes0 = graph.nodes.collect(REG)                              # BEFORE any activity exists
edges0, _ = rules.apply(nodes0, ALL)
shutil.copytree(os.path.join(FX, "activity"), os.path.join(sb, "memory", "activity"))

KOOK, OWLS, PIN = "a:primer:2026-01-02:0", "a:primer:2026-01-02:3", "a:primer:2026-01-02:4"
TUFFY, HER_REPLY, BANK = "t:2026-01-02:0", "t:2026-01-02:1", "t:2026-01-02:2"

print("1. THE READER")
rows = activity.all_rows(REG)
check("§1 kept rows are primer lines 0, 3, 4 only", [(a, d, i) for a, d, i, _ in rows] ==
      [("primer", "2026-01-02", 0), ("primer", "2026-01-02", 3), ("primer", "2026-01-02", 4)], rows)
check("§1 a private row is never read", not any("private" in r[3].get("title", "") for r in rows))
check("§1 ...and is counted, not silent", activity.private_count(REG) == 1, activity.private_count(REG))
check("§1 an app dir that is not a valid name is skipped", not any(a != "primer" for a, _, _, _ in rows))
check("§1 a file whose name is not a day is skipped", not any("not a day" in r[3]["title"] for r in rows))
check("§1 record() refuses a bad app name", activity.record("Bad App", "open", "x", registry=REG) is False)
_rec = activity.record("clockwork", "start_story", "The Brass Lantern", at_ms=1767344460000, registry=REG)
_back = [r for r in activity.all_rows(REG) if r[0] == "clockwork"]
check("§1 record() writes a row the reader reads back",
      _rec and len(_back) == 1 and _back[0][3]["title"] == "The Brass Lantern", _back)
_saved = os.environ.pop("SP_RECALL_REGISTRY")
try:
    check("§1 no store configured: no write and no raise", activity.record("primer", "x", "y") is False
          and activity.all_rows() == [])
finally:
    os.environ["SP_RECALL_REGISTRY"] = _saved
shutil.rmtree(os.path.join(sb, "memory", "activity", "clockwork"))

print("\n2. THE NODES")
nodes = graph.nodes.collect(REG)
ev = {n["id"]: n for n in nodes if n["kind"] == "app_event"}
check("§2 three app_event nodes with physical-line IDs", sorted(ev) == sorted([KOOK, OWLS, PIN]), sorted(ev))
check("§2 at is seconds, title is the text, app and event carried",
      ev[KOOK]["at"] == 1767344460.0 and ev[KOOK]["text"] == "Kookaburra"
      and ev[KOOK]["app"] == "primer" and ev[KOOK]["event"] == "open_page", ev.get(KOOK))
check("§2 the untimed event is a node with at None", ev[OWLS]["at"] is None)
check("§2 turns and facts are the same nodes as before", [n for n in nodes if n["kind"] != "app_event"] == nodes0)

print("\n3. THE RULE")
edges, dropped = rules.apply(nodes, ALL)
E = {(e["type"], e["from"], e["to"]): e for e in edges if e["rule"] == "activity"}
check("§3 next runs in file order, over the skipped lines", ("next", KOOK, OWLS) in E and ("next", OWLS, PIN) in E)
check("§3 during reaches the NEAREST timed turn (her reply, 56 s, not his turn at 60 s)",
      ("during", KOOK, HER_REPLY) in E and ("during", KOOK, TUFFY) not in E, sorted(k for k in E if k[0] == "during"))
check("§3 ...weighted by distance", abs(E[("during", KOOK, HER_REPLY)]["weight"] - (1 - 56 / 600)) < 1e-3)
check("§3 the PIN event happened during his bank-number turn", ("during", PIN, BANK) in E)
check("§3 an untimed event gets no during", not any(k[0] == "during" and k[1] == OWLS for k in E))
check("§3 every event joins the first turn of its day", all(("same_day", i, TUFFY) in E for i in (KOOK, OWLS, PIN)))
check("§3 the activity rule is versioned", all(e["rule_version"] == 1 for e in E.values()))
_seq = lambda es: sorted((e["type"], e["from"], e["to"]) for e in es if e["rule"] in ("sequence", "day"))
check("§3 sequence edges are identical with and without app events", _seq(edges) == _seq(edges0))
check("§3 no old rule touches an app event",
      not any(e["rule"] != "activity" and (e["from"].startswith("a:") or e["to"].startswith("a:")) for e in edges))
check("§3 the five rules are registered", set(rules.RULES) == set(ALL) and graph.DEFAULT_RULES == ALL)

print("\n4. THE VIEW")
check("§4 an event reaches her labelled as an app event",
      view.visible(ev[KOOK], "") == "(in primer, open_page) Kookaburra", view.visible(ev[KOOK], ""))
check("§4 an event carrying a secret's key token is withheld",
      view.visible(ev[PIN], "what was I reading?") == memory.SECRET_WITHHELD_NOTE, view.visible(ev[PIN], ""))
check("§4 an unknown kind still fails closed", view.visible({"id": "x", "kind": "idea", "text": "hi"}, "") is None)
check("§4 one_liner is the labelled title", view.one_liner(ev[OWLS]) == "(in primer, open_page) An untimed page about owls")

def _digest():
    h = hashlib.sha256()
    d = os.path.join(sb, "memory", "activity")
    for base, _dirs, files in sorted(os.walk(d)):
        for f in sorted(files):
            with open(os.path.join(base, f), "rb") as fh:
                h.update(f.encode() + fh.read())
    return h.hexdigest()

before = _digest()
summary = graph.build(REG)
check("§5 building leaves the activity files byte-identical", _digest() == before)
check("§5 the summary counts events and the private rows skipped",
      summary.get("app_events") == 3 and summary.get("app_events_private_skipped") == 1, summary)
nb = view.neighbours(HER_REPLY, "", 30)
check("§4 a built graph offers the event as a neighbour of the turn it happened during",
      ("during", KOOK, "(in primer, open_page) Kookaburra") in nb, nb)
check("§4 ...and never the secret-carrying event's title",
      not any("4417" in line for _, _, line in view.neighbours(BANK, "", 30)))

finish("G-GRAPH-ACTIVITY")
