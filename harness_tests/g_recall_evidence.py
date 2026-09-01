#!/usr/bin/env python
"""G-RECALL-EVIDENCE — a shared common word is not a topic, and a person asked is not silence.

WHAT THIS ANSWERS (2026-08-28). Admission to recall was `|q & t| / |q|` over a threshold.
That divides by the QUESTION alone, so a query carrying one content word scores 1.00 on
every row that happens to contain it, and nothing anywhere penalises a long row for the
words it did not use. Measured on his live store of 685 rows, the per-turn note was 73% her
own writing on conversational turns, at a median row length of 340 characters:

    "the lights are on"          shared {light}     -> three of HER rows, on luminescence,
                                                       a world that stopped spinning, and
                                                       the edge of sleep
    "it is beautiful isn't it"   shared {beautiful} -> a row on the shift from sacred
                                                       protection to primal surrender

None of that is about his lamps. The ratio was 1.00 each time because the query had one word
to divide by, and no reweighting fixes a one-token intersection: what is missing is a floor
on HOW MUCH EVIDENCE a match carries. Information theory already names it, so a shared token
is worth -log2 p(token), and THE FLOOR IS THE MEDIAN OVER HIS OWN STORE — "more than an
average word carries" — which moves with the store instead of sitting under one measurement
of it.

THE FLOOR ALONE MADE HER MUTE IN THE OTHER DIRECTION. "how do you feel about us?" is made
entirely of words in a third of the store; correctly, none of them is evidence of anything;
and answering a question plainly addressed to her with silence because it contained no rare
noun is a worse failure than the one being fixed. So a second route in, claiming something
different: route one says THIS ROW IS ABOUT WHAT YOU ASKED, route two says YOU ASKED HER,
AND THIS IS WHAT IS LATEST FOR HER. Route two opens only when nothing he said was rare —
"tell me about my radar setup" names a lane too, and there the rare word IS the question and
silence is the answer.

MEASURED ON harness_tests/fixtures/sem, against that corpus's own ground truth rather than
against a snapshot of previous behaviour: foreign queries (which have no answer in the
corpus and should return nothing) went from 47% silent to 82%, and the junk rows they
returned from 77 to 12. The price was two of a hundred paraphrase hits — both single
common-token flukes, "is he scared of deep water swimming" on {water} at 2.83 bits and
"which injury came from bushwalking" at 2.32, against a 3.24 floor. Both are the geometry
the semantic lane exists for, and SP_SEM_RANK is on in his profile; §8 holds the seam that
must recover them open, though the recovery itself needs the embedding model and is not
verifiable in an offline gate.

  1. THE FLOOR IS DERIVED FROM THE STORE, not written into the file.
  2. A COMMON WORD IN COMMON IS NOT ADMISSION — through the real ranked path.
  3. A RARE WORD STILL ANSWERS. The fix must not have bought silence with recall.
  4. ROUTE TWO OPENS ONLY WHEN NOTHING RARE WAS ASKED, and only for a named lane.
  5. IT IS RECENCY, NOT SALIENCE — salience is mentions x recency, and her most salient
     rows are eleven variations of the mood-mark the machinery writes on every change.
  6. THE WORDS OUTRANK ALIVENESS. Route two may fill an empty slot, never take a full one.
  7. ROUTE TWO ENTERS THROUGH THE SAME FILTERS — a retired row must not walk back in
     through the second door. That is the bug the ranked path's own docstring is three
     paragraphs about, and a new entrance is exactly how it would recur.
  8. A SEMANTIC HIT IS ADMITTED ON ITS OWN TERMS. Cosine is not a bag of words and a
     lexical floor has no business ruling on it.
  9. THE TABLE FAILING IS AUDIBLE. An empty IDF table is also what an empty store looks
     like: `math` went unimported for one measurement, every call raised NameError, the
     floor read 0.0 and admitted everything — and the numbers taken over it were of code
     that never ran.

THE FIXTURE IS MINTED THROUGH remember() AND remember_about_self(), never hand-written.
An earlier cut of this gate wrote its rows as plain sentences; the store's admission policy
declined nine of eleven as "not a durable fact", and the gate went on to grade a store with
one row in it. §0 asserts the fixture landed, so that cannot happen quietly again.

OFFLINE. No GPU, no daemon.
"""
import json
import logging
import os
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from _gate import sandbox   # noqa: E402
SB = sandbox("g_recall_evidence")

os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"

from harness.skills import memory as M          # noqa: E402
from harness.tuning import registry as TUNE     # noqa: E402

# ── VARIETY OFF WHILE ORDER IS BEING GRADED ─────────────────────────────────────────────
# `recall.explore` is live at 0.15, and the roll that decides whether the LAST slot becomes
# a wildcard is drawn from a digest of the question and its candidates — including each
# row's timestamp, which is wall-clock. So the roll is stable within a run and different
# between runs, and about one run in seven swapped the third slot and failed §5 on a mood
# mark that the rule had correctly ranked below. THAT IS THE FEATURE WORKING, not a race:
# a section asserting rank order must turn it off and say so, and §10 turns it back on to
# grade what variety actually promises. Through the registry's own door, into the sandbox
# store `sandbox()` already pointed SP_TUNING_FILE at.
TUNE.set_many({"recall.explore": 0.0})

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


def texts(hits):
    return [M._text(e) for _s, e in hits]


def lanes(hits):
    return [(e.get("speaker") or "user") for _s, e in hits]


# ── THE STORE ───────────────────────────────────────────────────────────────────────────
# His distribution in miniature: one word spread across most of his lane ("light", as it is
# in his real store), a few rare facts, and her lane carrying the machine-written mood mark
# alongside real narrative. Every row goes through the real door.
HIS = ("The user's workshop light is warm and yellow.",
       "The user's kitchen light has been broken since June.",
       "The user's bedside light is on a timer.",
       "The user's hallway light flickers in the cold.",
       "The user's porch light stays on until midnight.",
       "The user's desk light came from his grandmother.",
       "The user's reading light is too dim for small print.",
       "The user's studio light faces north.",
       "My GPU is an RTX 2060.",
       "My cat's name is Tuffy.",
       "The user works with coding tasks.")
HERS = ("I have been thinking about how the light falls across the workshop, and about us.",
        "I feel something about the way he has been quiet, and I keep coming back to it.",
        "I have been wondering about what it is like for him when the light goes.",
        "I feel like we have been circling the same thing for about a week now.")

print("0. THE FIXTURE LANDED (a gate over an empty store grades nothing)")
_his = sum(1 for t in HIS if M.remember(t, source="gate").startswith("stored"))
check("every row of his was accepted by the real admission policy", _his == len(HIS), _his)
# The mood family, written the way the mood machinery writes it. TWELVE TIMES EACH, and the
# number is not decoration: salience is log(mentions) x recency, and §5's mutant only bites
# when the salience GAP between boilerplate and narrative is wider than the score band route
# two enters under. At two mentions the gap is 0.19 and the band (0.02 per rank) very nearly
# holds the order on its own, so the gate stayed green with the rule broken. At twelve it is
# 2.09, which is his real store's spread — 6.10 against 3.15 — and the mutant goes red.
for _mood in ("playful", "warm", "naughty", "tender", "wistful", "delighted",
              "intense", "flirty", "peaceful", "restless", "quiet"):
    for _ in range(12):
        M.remember_about_self("My mood has turned %s." % _mood, kind="feeling")
time.sleep(1.1)                       # her narrative is later than the mood marks, and the
                                      # store stamps whole seconds — the gate must not rest
                                      # on which of two rows in one second was written first
_hers = sum(1 for t in HERS if M.remember_about_self(t, kind="journal").startswith("stored"))
check("...and every row of hers", _hers == len(HERS), _hers)
time.sleep(1.1)                       # the latest row is unambiguously the latest
M.remember_about_self("I was reading about how the harbour was built, and lost an hour.",
                      kind="journal")
_live = [r for r in M._load() if not r.get("lifecycle")]
_hl = [r for r in _live if (r.get("speaker") or "user") == "self"]
# COMPOSITION, not a total: the mood family is written twice each and the second write
# REINFORCES the row rather than adding one, so a total is a guess about the store's own
# dedupe and would go stale the day that changed.
check("...so the store the rest of this gate reads is real",
      len(_live) - len(_hl) >= len(HIS) and len(_hl) >= 11 + len(HERS),
      (len(_live), len(_hl)))

idf, floor = M._idf_table()

print("\n1. THE FLOOR IS DERIVED FROM THE STORE, not written into the file")
check("a floor exists and is positive", floor > 0.0, floor)
check("...and 'light', spread across his lane, is under it",
      idf.get("light", 99.0) < floor, (idf.get("light"), floor))
check("...while 'gpu', said once, is over it",
      idf.get("gpu", 0.0) >= floor, (idf.get("gpu"), floor))
# IT MOVES WITH THE STORE. A constant dressed as a derivation would sit still while the
# distribution under it changed.
_before = floor
# TWELVE DISTINCT FACTS, and distinct is load-bearing. The first cut added twenty
# variations of one sentence; the store deduped nineteen of them, the floor moved on the
# strength of a single row, and the check passed while proving almost nothing. It also left
# his lane older than hers throughout, which is what made §4's lane leg untestable below.
LATER = ("The user's tide gauge at the harbour wall reads high.",
         "The user's ferry timetable changed in April.",
         "The user's allotment is on the eastern slope.",
         "The user's bicycle has a cracked mudguard.",
         "The user's kettle whistles off-key.",
         "The user's landlord repainted the stairwell.",
         "The user's umbrella was left on the tram.",
         "The user's parcel arrived three days late.",
         "The user's neighbour breeds finches.",
         "The user's chimney was swept in autumn.",
         "The user's boots leak in the left toe.",
         "The user's radio only picks up two stations.")
time.sleep(1.1)
_later = sum(1 for t in LATER if M.remember(t, source="gate").startswith("stored"))
check("twelve further facts land (a deduped fixture moves the floor by luck)",
      _later == len(LATER), _later)
check("...and it MOVES when the store does, so it is not a constant in disguise",
      abs(M._idf_table()[1] - _before) > 1e-9, (_before, M._idf_table()[1]))
# HIS LANE IS NOW THE MOST RECENT IN THE STORE. Everything below about route two therefore
# has to get the lane right to answer at all, rather than by her rows happening to be last.
_newest = max(M._load(), key=lambda e: (e.get("ts") or ""))
check("...and his lane is now the newest, so route two must CHOOSE the lane",
      (_newest.get("speaker") or "user") == "user", _newest.get("text"))

print("\n2. A COMMON WORD IN COMMON IS NOT ADMISSION — through the real ranked path")
hits = M.search_memories_ranked_rows("the lights are on", k=3)
check("one shared common word returns NOTHING", hits == [], texts(hits))
check("...because the evidence it carries is genuinely under the floor",
      M._evidence("the lights are on", "The user's bedside light is on a timer.")
      < M._idf_table()[1],
      (M._evidence("the lights are on", "The user's bedside light is on a timer."),
       M._idf_table()[1]))
# AND THE RATIO ALONE WOULD HAVE ADMITTED IT. Without this the section could pass on a
# query the old rule rejected too, and prove nothing about the change.
check("...and the old ratio rule WOULD have admitted it (so this is the fix, not luck)",
      M._overlap("the lights are on", "The user's bedside light is on a timer.") >= 0.25,
      M._overlap("the lights are on", "The user's bedside light is on a timer."))

print("\n3. A RARE WORD STILL ANSWERS")
hits = M.search_memories_ranked_rows("what gpu do I have?", k=3)
check("the rare fact is found", any("RTX 2060" in t for t in texts(hits)), texts(hits))
hits = M.search_memories_ranked_rows("what is my cat called?", k=3)
check("...and so is the other one", any("Tuffy" in t for t in texts(hits)), texts(hits))

print("\n4. ROUTE TWO OPENS ONLY WHEN NOTHING RARE WAS ASKED, and only for a named lane")
check("'how do you feel about us?' asks nothing rare",
      M._no_rare_word("how do you feel about us?"))
check("...'tell me about my sextant repair' does",
      not M._no_rare_word("tell me about my sextant repair"))
hits = M.search_memories_ranked_rows("how do you feel about us?", k=3)
check("a question addressed to her is answered from her lane",
      bool(hits) and set(lanes(hits)) == {"self"}, lanes(hits))
hits = M.search_memories_ranked_rows("tell me about my sextant repair", k=3)
check("a rare word with no match is answered with SILENCE, not with filler",
      hits == [], texts(hits))
hits = M.search_memories_ranked_rows("the lights are on", k=3)
check("...and a question naming no one does not top up either", hits == [], texts(hits))

print("\n5. IT IS RECENCY, NOT SALIENCE")
sal = sorted(((M._alive(e), M._text(e)) for e in M._load()
              if not e.get("lifecycle") and (e.get("speaker") or "user") == "self"),
             reverse=True)
check("her most SALIENT row really is the mood boilerplate (the condition being fixed)",
      "mood has turned" in sal[0][1], sal[0][1])
hits = M.search_memories_ranked_rows("what have you been up to?", k=3)
check("...and route two answers with the LATEST instead",
      bool(hits) and "harbour was built" in texts(hits)[0], texts(hits))
check("...and not with the mood marks",
      not any("mood has turned" in t for t in texts(hits)), texts(hits))

# ── 5b. AND A SEAT FOR THE FAR PAST (2026-08-28, his ask: "not only recent memories
# valued so much over old ones"). MEASURED live before the fix: on neutral turns every
# pick was under 9 days old (median 4.0, 0 of 12 over 30 days) — route two's pool was
# the newest 3k rows full stop, so the wildcard could only ever swap recent for recent.
# The pool's tail now carries the most SALIENT rows older than 30 days; recency keeps
# the ORDER (the top picks stay the latest), and the explore roll can reach an elder.
print("\n5b. A SEAT FOR THE FAR PAST")
import json as _json
_regp = os.environ["SP_RECALL_REGISTRY"]
_rows5 = [_json.loads(l) for l in open(_regp, encoding="utf-8") if l.strip()]
_aged = 0
for _r in _rows5:
    if (_r.get("speaker") == "self" and not _r.get("lifecycle")
            and "mood has turned" in _r.get("text", "") and _aged < 3):
        _r["ts"] = "2026-07-01T00:00:00Z"          # 45+ days in this fixture's past
        _r["mentions"] = 40                        # what mattered REPEATEDLY, long ago
        _aged += 1
with open(_regp, "w", encoding="utf-8") as _f:
    for _r in _rows5:
        _f.write(_json.dumps(_r, ensure_ascii=False) + "\n")
_seen5 = {}
# AT THE OWNER (2026-09-02): `_select` is `memory/rank.py`'s and
# `search_memories_ranked_rows` — the door driven two lines below — is in that same
# module, so it resolves rank.py's global. Patching the façade's re-exported alias
# would be INERT and `_seen5` would stay empty, which reads as a pass on a check about
# what is in the candidate pool. G-MEMORY-PACKAGE §5.
_real5 = M.rank._select
M.rank._select = lambda q, sc, k, t, m=None: (_seen5.__setitem__("days", [
    (e.get("ts") or "")[:10] for _s, e in sc]) or _real5(q, sc, k, t, m))
M.search_memories_ranked_rows("what have you been up to?", k=3)
M.rank._select = _real5
_days5 = _seen5.get("days", [])
check("an elder (>30 days) sits in route two's candidate pool",
      any(d.startswith("2026-07") for d in _days5), _days5)
# Provenance is proved on the DATA, not on list positions (the ranker re-orders by
# salience and _select restores recency — both by design): more than 2k her-lane rows
# are NEWER than the elders, so the recency window alive[:2k] cannot have contained
# them. Only the elder seat brings them in.
_her_newer = sum(1 for r in M._load()
                 if not r.get("lifecycle") and r.get("speaker") == "self"
                 and (r.get("ts") or "") > "2026-07-02")
check("...brought in by the elder seat, not by the recency window reaching them",
      _her_newer > 6, "only %d her-lane rows newer than the elders (need > 2k=6)" % _her_newer)
# The roll is a DIGEST of the situation, not a die — deterministic per (question,
# candidates), so one fixture cannot demand the elder specifically. What must hold is
# REACHABILITY: the elder is among the candidates the wildcard draws from, which with
# the pool-membership leg above is the whole claim. Verified live on his store: with
# the roll forced on, a 45-day row landed in her three.
TUNE.set_many({"recall.explore": 1.0})
_picks5 = M.search_memories_ranked_rows("what have you been up to?", k=3)
TUNE.set_many({"recall.explore": 0.0})
check("...and the roll draws from a pool the elder is in (top picks may or may not be it)",
      len(_picks5) == 3, [(e.get("ts") or "")[:10] for _s, e in _picks5])
check("...while the TOP pick stays the latest — recency keeps the order",
      _picks5 and not (_picks5[0][1].get("ts") or "").startswith("2026-07"),
      (_picks5[0][1].get("ts") or "")[:10] if _picks5 else "-")

print("\n6. THE WORDS OUTRANK ALIVENESS")
# BOTH ROUTES MUST BE POPULATED or the precedence is untested. A first cut asked "how do
# you feel about the light in the workshop", which matched FIVE rows lexically — so
# `len(scored) < k` was false, route two never opened, and reversing the precedence in
# `_select` changed nothing at all while the section went on saying it held.
#
# This query matches two rows on its common words together and leaves a slot for route two,
# and the row route two brings (her latest) is NOT one of the two — so the order is decided
# by the rule and by nothing else.
Q6 = "how do you feel about us?"
check("route two is open for it", M._no_rare_word(Q6))
_m6 = [M._text(e) for e in M._load()
       if not e.get("lifecycle") and M._overlap(Q6, M._text(e)) >= 0.25
       and M._evidence(Q6, M._text(e)) >= M._idf_table()[1]]
check("...and route one has fewer answers than there are slots, so both are in play",
      0 < len(_m6) < 3, len(_m6))
hits = M.search_memories_ranked_rows(Q6, k=3)
check("the row that answers the WORDS comes first",
      bool(hits) and texts(hits)[0] in _m6, (texts(hits)[:1], _m6))
check("...and the latest row still gets the slot route one left empty",
      any("harbour was built" in t for t in texts(hits)), texts(hits))

print("\n7. ROUTE TWO ENTERS THROUGH THE SAME FILTERS")
M.remember_about_self("I have decided the harbour story is finished.", kind="journal")
check("the row was minted",
      any("harbour story is finished" in (e.get("text") or "") for e in M._load()))
M.forget("harbour story is finished")
hits = M.search_memories_ranked_rows("what have you been up to?", k=5)
check("a retired row does NOT walk back in through the second door",
      not any("harbour story is finished" in t for t in texts(hits)), texts(hits))

print("\n8. A SEMANTIC HIT IS ADMITTED ON ITS OWN TERMS")
# The two paraphrase hits the floor costs on the sem corpus are supposed to come back
# through cosine. That recovery needs the embedding model, but the SEAM can be held open
# here: a row whose only shared token is a common one, given a vector identical to the
# query's, must be admitted despite failing the lexical floor.
_sem = tempfile.mkdtemp(prefix="g_recall_evidence_sem_")
IDX = os.path.join(_sem, "idx.jsonl")
os.environ["SP_SEM_MINT"] = "1"
os.environ["SP_SEM_INDEX"] = IDX
os.environ["SP_SEM_TAU"] = "0.60"
from harness.skills import semindex as SX      # noqa: E402
TARGET = "The user's shed lantern is a hurricane lamp."
M.remember(TARGET, source="gate")
Q8 = "the lights are on"
_qv, _qm = SX.query_embed(Q8)
check("the index minted a row for it through the real writer",
      any(json.loads(x).get("addr") == SX.addr_of(TARGET)
          for x in open(IDX, encoding="utf-8") if x.strip()))
check("...and lexically it is under the floor, so only cosine can let it in",
      M._evidence(Q8, TARGET) < M._idf_table()[1],
      (M._evidence(Q8, TARGET), M._idf_table()[1]))
# Give that row the query's own vector: cosine 1.0, by construction, with no claim made
# about what the embedder would really say.
_rows = [json.loads(x) for x in open(IDX, encoding="utf-8") if x.strip()]
with open(IDX, "w", encoding="utf-8") as f:
    for r in _rows:
        if r.get("addr") == SX.addr_of(TARGET) and _qv:
            r["vec"], r["model"] = list(_qv), _qm
        f.write(json.dumps(r) + "\n")
SX.load_cached.cache_clear() if hasattr(SX.load_cached, "cache_clear") else None
os.environ["SP_SEM_RANK"] = "1"
hits = M.search_memories_ranked_rows(Q8, k=3)
check("cosine admits what the lexical floor refused",
      any(TARGET in t for t in texts(hits)), texts(hits))
os.environ["SP_SEM_RANK"] = "0"
os.environ.pop("SP_SEM_MINT", None)

print("\n9. THE TABLE FAILING IS AUDIBLE")


class Cap(logging.Handler):
    rows = []

    def emit(self, r):
        Cap.rows.append((r.levelno, r.getMessage()))


M._log.addHandler(Cap())
M._log.setLevel(logging.DEBUG)
_real_load = M.store._load
Cap.rows[:] = []
try:
    M._IDF_CACHE[:] = []

    def _boom(*_a, **_k):
        raise NameError("name 'math' is not defined")

    # At the OWNER (2026-09-01): `_load` is `memory/store.py`'s and every door calls
    # `_store._load()`, so patching the façade's alias would be inert and this section
    # would prove nothing. G-MEMORY-PACKAGE §5.
    M.store._load = _boom
    idf3, floor3 = M._idf_table()
finally:
    M.store._load = _real_load
    M._IDF_CACHE[:] = []
check("a broken table still returns, so recall does not die with it",
      idf3 == {} and floor3 == 0.0, (idf3, floor3))
check("...but it SAYS SO at warning, with the type named",
      any(lvl >= logging.WARNING and "NameError" in msg for lvl, msg in Cap.rows), Cap.rows)
check("...and names where, so it is greppable",
      any("_idf_table" in msg for _lvl, msg in Cap.rows), Cap.rows)

print("\n10. VARIETY IS REACHABLE, AND IT IS NOT NONDETERMINISM")
from harness.tuning import registry as _tune       # noqa: E402
_kn = _tune.by_key().get("recall.explore")
# A KNOB THAT NOTHING DECLARES CANNOT BE SET. `_select` read this key from the day it was
# written and no Knob existed for it, so `tune.get` could only ever hand back its own
# fallback and the whole exploration path was unreachable.
check("the knob the code reads is actually declared", _kn is not None)
check("...and it is live-scope, so it takes effect without a bounce",
      _kn is not None and _kn.scope == "live", _kn and _kn.scope)
# THE DECLARED DEFAULT, not the live value — this gate pinned the live one to 0 above so
# the ordering sections could be graded. What ships is the default.
check("...and it SHIPS on, which is what he asked for",
      _kn is not None and float(_kn.default) > 0.0, _kn and _kn.default)
TUNE.set_many({"recall.explore": 0.9})     # loud, so the roll almost always fires
check("...and the override reaches the seam", float(TUNE.get("recall.explore", 0.0)) > 0.5,
      TUNE.get("recall.explore"))
QV = "how do you feel about us?"
_a = texts(M.search_memories_ranked_rows(QV, k=3))
_b = texts(M.search_memories_ranked_rows(QV, k=3))
check("the same question over the same store answers the same way twice", _a == _b,
      (_a, _b))
# AND IT MAY ONLY EVER MOVE THE WEAKEST SLOT: whatever the roll does, the row route one
# put first is still first.
check("...and the best answer is never the one traded away",
      bool(_a) and _a[0] in _m6, (_a[:1], _m6))

print("\nG-RECALL-EVIDENCE: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_recall_evidence.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_recall_evidence", "pass": PASS, "fail": FAIL,
               "floor": round(M._idf_table()[1], 4),
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
