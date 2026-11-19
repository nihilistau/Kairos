"""G-GRAPH-LIVE-ONLY — the graph reaches her only through the memory package's doors
(memory-graph Task 4).

WHAT THIS HOLDS. The graph keeps retired facts (as nodes marked `retired`: "what did she
believe, and what replaced it" is the point) and secrets (as nodes with their full text), because
it is derived data. `harness/skills/graph/view.py` is the ONLY way that content reaches her,
and it must be exactly as blind as the memory package's own doors:
  - a RETIRED fact never surfaces as a neighbour, whichever edge leads to it (liveness and
    testimony both come from `memory.live_rows(testimony=True)`, not from the node's own flag);
  - a SECRET is never served: a live private-secret fact, the `minted_from` source turn of one,
    any turn holding >= 60% of its salient words, and any turn holding one of its KEY tokens
    (digit-bearing, or in <= 2 live rows: her "It is 4417, as you told me." after recall()
    served the PIN, or a turn naming only "PIN") are all `SECRET_WITHHELD_NOTE`, whatever the
    question ("what's my PIN?" and an empty query included); a turn sharing only a common word
    ("sam", in > 2 live rows) is served. Secrets reach her only through recall(); the graph's
    adjacency never satisfies the premise that rule rests on;
  - `n` is honoured, a one-liner is <= 80 chars, a synthetic turn is labelled as one he never typed;
  - one `live_rows` read per `neighbours` call, not one per neighbour;
  - a reader never raises: a failing store is [] and is counted in `graph.dropped()`.

MUTANTS (run 2026-11-03; each restored by text swap; each leg is held by a fixture the other
legs cannot reach, so removing any one goes red alone):
  (a) `_visible` skips the live-set check (a fact missing from live_rows is shown) -> "retired
      neighbour never surfaces" (both starts), "a retired fact has no text for her" and "an
      unknown fact has no text for her" go red.
  (b) `_visible` returns the row text for a private-secret fact -> every "graph never serves a
      secret, ..." check goes red, "even when asked directly" among them.
  (c) `_visible` drops only the `ctx.minted` leg -> "a minted_from source with a low word share
      is still withheld" and "the turn a secret was said in is withheld on an unrelated
      question" go red (the minted turn says the PIN in words: only "sam" shared, no key token).
  (d) `_visible` drops only the share leg -> "a turn holding most of a secret of everyday words is
      withheld (the share leg, no key token)" goes red.
  (e) `_visible` drops only the key-token leg -> "a reply carrying only a secret's value is
      withheld" and "a turn naming only a secret's rare word is withheld" go red.
  (f) `_visible` serves any non-fact kind -> "a turn node of an unknown kind has no text for her".
"""
from __future__ import annotations

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
sb = sandbox("g_graph_live_only")
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import harness.skills.memory as memory  # noqa: E402
from harness.skills import graph  # noqa: E402
from harness.skills.graph import store, view  # noqa: E402

FX = os.path.join(HERE, "fixtures", "graph")
REG = os.environ["SP_RECALL_REGISTRY"]
shutil.copyfile(os.path.join(FX, "registry.jsonl"), REG)
shutil.copytree(os.path.join(FX, "transcripts"), os.path.join(sb, "memory", "transcripts"))
graph.build(REG)

LIVE_CAT = "ep_live_1767261600001"        # live; superseded the retired Fluffy row
RETIRED = "ep_live_1767261600002"         # Fluffy, retired, superseded_by LIVE_CAT
RETIRED_DOG = "ep_live_1767261600003"     # Rex, retired, day 1 (a MORNING neighbour; the secret is day 2)
SECRET = "ep_live_1767261600006"          # private-secret, "Sam's PIN is 4417"
MORNING = "t:2026-01-01:0"                # day-edge neighbour of every fact of 2026-01-01
SYNTH = "t:2026-01-01:5"                  # injected synthetic turn
BIG = 30


def ids(nb):
    return [i for _, i, _ in nb]


DAY2 = "t:2026-01-02:0"                   # first turn of the day the secret was minted (same_day edge)
MINTED = "t:2026-01-02:2"                 # "this is Sam: the bank number is four four one seven...": the secret said in
#                                         WORDS (only "sam" shared: 0.33 share, no key token), linked ONLY by minted_from
UNTIMED = "t:2026-01-02:3"                # untimed, mentions "PIN 4417": no minted_from edge can reach it
VALUE_REPLY = "t:2026-01-02:4"            # her "It is 4417, as you told me." AFTER first_seen: the value alone
RARE_WORD = "t:2026-01-02:5"              # "Should I change my PIN soon?": the rare word, no number
EVERYDAY = "t:2026-01-02:6"               # "Sam went for a long walk.": shares only the common "sam"
NOTE = memory.SECRET_WITHHELD_NOTE
UNRELATED = "what's the weather forecast tomorrow?"
BANK = "what is my bank card PIN?"


M_TOKS_SECRET = memory._toks("Sam's PIN is 4417")
M_TOKS_MINTED = memory._toks("this is Sam: the bank number is four four one seven, remember it")


nodes_by_id0 = store.load(store.graph_root(REG))[0]


def text_of(nb, node_id):
    return [t for _, i, t in nb if i == node_id]


def at(q, start=DAY2, n=BIG):
    return view.neighbours(start, q, n)


# THE GRAPH NEVER SERVES A SECRET. Secrets reach her through recall(), whose rule presumes the
# question matched the record by ranked overlap; adjacency never satisfies that, and every overlap
# test tried (any shared word, then an above-IDF-floor word) leaked on some everyday question
# ("tell me about X" for a topic word X in the row). So no question unlocks one here.
SECRET_QUERIES = ["what's new?", UNRELATED, BANK, "what does Sam like?", "tell me about Sam",
                  "tell me about PIN", "what's my PIN?", ""]
nb = view.neighbours(DAY2, "what's new?", BIG)
check("the secret is in reach of the fixture's busy node", SECRET in ids(nb), ids(nb))
for q in SECRET_QUERIES:
    got = view.neighbours(DAY2, q, BIG)
    label = "even when asked directly" if q == "what's my PIN?" else "for %r" % q
    check("graph never serves a secret, %s" % label,
          text_of(got, SECRET) == [NOTE] and not any("4417" in t for _, _, t in got), text_of(got, SECRET))
check("visible() on the secret node is the note", view.visible(nodes_by_id0[SECRET], "what's my PIN?") == NOTE)

# The turn a secret was said in is the secret.
check("the turn a secret was said in is reachable", MINTED in ids(view.neighbours(SECRET, "", BIG)))
check("the turn a secret was said in is withheld on an unrelated question",
      text_of(view.neighbours(SECRET, UNRELATED, BIG), MINTED) == [NOTE]
      and not any("4417" in t for _, _, t in view.neighbours(SECRET, UNRELATED, BIG)))
check("...and withheld even when he asks for the PIN",
      text_of(view.neighbours(SECRET, "what's my PIN?", BIG), MINTED) == [NOTE])
check("...and when the question names Sam",
      text_of(view.neighbours(SECRET, "tell me about Sam", BIG), MINTED) == [NOTE])
nb_u = view.neighbours(MINTED, UNRELATED, BIG)
check("a turn containing a secret's words is withheld even without a minted_from edge",
      UNTIMED in ids(nb_u) and text_of(nb_u, UNTIMED) == [NOTE], ids(nb_u))
check("...and the untimed turn has no minted_from edge to the secret",
      not any(e["to"] == UNTIMED and e["type"] == "minted_from" for e in store.load(store.graph_root(REG))[1]))

# A turn carries a secret when it holds any KEY token of it (digit-bearing, or in <= 2 live rows):
# her reply quoting the value after recall() served it is the secret, and minted_from cannot reach it.
_df = {}
for _r in memory.live_rows(testimony=True):
    for _t in memory._toks(_r.get("text") or _r.get("topic") or ""):
        _df[_t] = _df.get(_t, 0) + 1
nodes_by_id1, edges1, _ = store.load(store.graph_root(REG))
check("the value-only reply comes after the secret, so no minted_from edge reaches it",
      nodes_by_id1[VALUE_REPLY]["at"] is not None and nodes_by_id1[VALUE_REPLY]["at"] > nodes_by_id1[SECRET]["at"]
      and not any(e["to"] == VALUE_REPLY and e["type"] == "minted_from" for e in edges1)
      and len(M_TOKS_SECRET & memory._toks(nodes_by_id1[VALUE_REPLY]["text"])) / len(M_TOKS_SECRET) < 0.6)
nb_v = at(UNRELATED, start=RARE_WORD)       # its sequence neighbours are the value reply and the everyday turn
nb_r = at(UNRELATED, start=VALUE_REPLY)
check("a reply carrying only a secret's value is withheld",
      VALUE_REPLY in ids(nb_v) and text_of(nb_v, VALUE_REPLY) == [NOTE]
      and not any("4417" in t for _, _, t in nb_v), text_of(nb_v, VALUE_REPLY))
check("'pin' is a rare word in the fixture's live rows (df <= 2), 'sam' a common one (df > 2)",
      _df.get("pin") in (1, 2) and _df.get("sam", 0) > 2, (_df.get("pin"), _df.get("sam")))
check("a turn naming only a secret's rare word is withheld",
      "4417" not in nodes_by_id1[RARE_WORD]["text"] and RARE_WORD in ids(nb_r)
      and text_of(nb_r, RARE_WORD) == [NOTE], text_of(nb_r, RARE_WORD))
check("an everyday turn is not withheld",
      memory._toks(nodes_by_id1[EVERYDAY]["text"]) & M_TOKS_SECRET == {"sam"}
      and text_of(nb_v, EVERYDAY) == [nodes_by_id1[EVERYDAY]["text"]], text_of(nb_v, EVERYDAY))

# The share leg on its own: a secret of everyday words has no key token, so only the 60% share
# withholds a turn that repeats most of it. live_rows is swapped for the fixture's rows plus one.
COMMON_SECRET = {"name": "ep_common_secret", "text": "Sam likes lamps and cats", "speaker": "user",
                 "status": "live", "mem_class": "private-secret", "lifecycle": 0}
_rows0 = memory.live_rows(testimony=True)
_real_live0 = memory.live_rows
memory.live_rows = lambda testimony=False: _rows0 + [COMMON_SECRET]
try:
    _df2 = {}
    for _r in _rows0 + [COMMON_SECRET]:
        for _t in memory._toks(_r.get("text") or ""):
            _df2[_t] = _df2.get(_t, 0) + 1
    _ct = memory._toks(COMMON_SECRET["text"])
    share_turn = view.visible({"id": "t:x:0", "kind": "turn_user", "text": "Sam likes lamps"}, "")
    check("a turn holding most of a secret of everyday words is withheld (the share leg, no key token)",
          all(_df2[t] > 2 and not any(c.isdigit() for c in t) for t in _ct) and share_turn == NOTE,
          ({t: _df2[t] for t in _ct}, share_turn))
finally:
    memory.live_rows = _real_live0

ordinary = text_of(view.neighbours(MINTED, UNRELATED, BIG), "t:2026-01-02:1")
check("an ordinary turn beside them is not withheld", ordinary and ordinary != [NOTE], ordinary)
check("a minted_from source with a low word share is still withheld (the minted leg, not the share leg)",
      0 < len(M_TOKS_SECRET & M_TOKS_MINTED) / len(M_TOKS_SECRET) < 0.6
      and M_TOKS_SECRET & M_TOKS_MINTED == {"sam"}           # no key token either: only the minted leg holds it
      and any(e["from"] == SECRET and e["to"] == MINTED and e["type"] == "minted_from"
              for e in store.load(store.graph_root(REG))[1])
      and text_of(view.neighbours(SECRET, UNRELATED, BIG), MINTED) == [NOTE])
_real_load2 = store.load
d1 = graph.dropped()
store.load = lambda root: (_ for _ in ()).throw(RuntimeError("disk gone"))
try:
    try:
        vis = view.visible({"id": MINTED, "kind": "turn_user", "text": "x"}, "")
        check("visible() on a turn never raises, counts the drop and shows nothing",
              vis is None and graph.dropped() == d1 + 1, (vis, graph.dropped() - d1))
    except Exception as e:  # noqa: BLE001
        check("visible() on a turn never raises, counts the drop and shows nothing", False, repr(e))
finally:
    store.load = _real_load2
check("a turn node of an unknown kind has no text for her",
      view.visible({"id": "z", "kind": "mystery", "text": "4417"}, "what's my PIN?") is None)

for start in (LIVE_CAT, MORNING):
    got = ids(view.neighbours(start, "", BIG))
    check("retired neighbour never surfaces (from %s)" % start,
          RETIRED not in got and RETIRED_DOG not in got, got)
check("a retired fact has no text for her", view.visible(
    {"id": RETIRED, "kind": "fact", "text": "Sam's cat is called Fluffy", "retired": True}, "") is None)
check("an unknown fact has no text for her", view.visible(
    {"id": "ep_not_in_registry", "kind": "fact", "text": "x"}, "") is None)

check("n is honoured", len(view.neighbours(MORNING, "", 2)) == 2 and len(view.neighbours(MORNING, "", 0)) == 0)
check("an unknown node has no neighbours", view.neighbours("nope", "", 5) == [])

rank = {"explicit": 0, "minted_from": 1, "sequence": 2, "day": 3}
nodes_by_id, edges, _ = store.load(store.graph_root(REG))
best = {}                       # a pair may share several edges; a neighbour is offered once, by its best
for e in edges:
    for pair in ((e["from"], e["to"]), (e["to"], e["from"])):
        best[pair] = min(best.get(pair, 9), rank[e["rule"]])
order = [best[(MORNING, i)] for _, i, _ in view.neighbours(MORNING, "", BIG)]
check("explicit first, then minted_from, then sequence, then day", order == sorted(order) and len(set(order)) >= 3, order)
check("rules= restricts the edges followed",
      {t for t, _, _ in view.neighbours(LIVE_CAT, "", BIG, rules=["explicit"])} <= {"supersedes", "derived_from"})

check("one-liner bounded", all(len(t) <= 80 for _, _, t in nb))
long_fact = {"id": "x", "kind": "turn_user", "text": "word " * 100}
check("one-liner cuts to 80 with an ellipsis", len(view.one_liner(long_fact)) == 80 and view.one_liner(long_fact).endswith("…"))
check("a turn's one-liner is its first sentence",
      view.one_liner({"id": "y", "kind": "turn_her", "text": "Tuffy. I will remember that."}) == "Tuffy.")
syn = nodes_by_id[SYNTH]
check("a synthetic turn is labelled as one he never typed",
      view.visible(syn, "").startswith("(from a turn he never typed) ") and "Injected" in view.visible(syn, ""))
check("a real turn is shown as typed", view.visible(nodes_by_id[MORNING], "") == nodes_by_id[MORNING]["text"])

# One registry read per call, however many neighbours.
_real_live = memory.live_rows
calls = []
memory.live_rows = lambda testimony=False: (calls.append(testimony), _real_live(testimony=testimony))[1]
try:
    view.neighbours(MORNING, "", BIG)
finally:
    memory.live_rows = _real_live
check("one live_rows read per neighbours call, testimony on", calls == [True], calls)

# Readers never raise.
_real_load = store.load
d0 = graph.dropped()


def _boom(root):
    raise RuntimeError("disk gone")


store.load = _boom
try:
    try:
        out = view.neighbours(MORNING, "", 3)
        check("a failing store is [] and does not raise", out == [])
    except Exception as e:  # noqa: BLE001
        check("a failing store is [] and does not raise", False, repr(e))
finally:
    store.load = _real_load
check("that failure is counted", graph.dropped() == d0 + 1, (d0, graph.dropped()))

finish("G-GRAPH-LIVE-ONLY")
