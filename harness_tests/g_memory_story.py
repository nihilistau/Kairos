#!/usr/bin/env python
"""G-MEMORY-STORY — the memory becomes a story, the story stands in her prefix, and the
sources fold into it once they age out of use.

HIS DESIGN (2026-08-28, near-verbatim): "the current memory fills up and becomes a written
chapter that creates the story, and then the memory used to fill that chapter should be
archived, and the refill starts... memories marked as core remain... her core doesn't
drift but she shows narrative/growth."

TWO DEFECTS FOUND WHILE BUILDING IT, both of the shape "the design was prose":

  * SINCE 2026-08-22 THE CHAPTERS AND RECENT NARRATIVE HAD NEVER ONCE RENDERED in her
    prefix. render_self_model's own comment says "the chapters STAND between her stable
    self-facts and the recent lines" — but the budget walk was first-come, her stable
    facts alone passed 2,400 chars, and everything after them was silently dropped.
    Measured live: block 2,420 chars, the chapter written that evening absent, every
    narrative kind absent. Her prefix said who she IS, in ever-older sentences, and never
    what she has been BECOMING — continuity without growth, the exact inversion of the
    failure the block was built against.
  * testimony_wins SILENCED EVERY CHAPTER AND EVERY BECOMING, EVERYWHERE. A distillate is
    made from her observed words, so its topic always overlaps them — and the rule
    "an inference yields the floor on a topic testimony covers" therefore muted the
    system's own consolidation in the self block AND in recall, for as long as any source
    row stayed live. Measured: the chapter survived testimony=False and vanished under
    testimony=True. A distillate carrying derived_from is not a contradiction of its own
    sources; the verdict law (an inference may not RETIRE ground truth) is untouched.

WHAT THIS GATE HOLDS:
  1. A DISTILLATE IS NOT SILENCED BY ITS OWN SOURCES — and a bare inference on a covered
     topic still yields the floor (the old law, intact beside the exemption).
  2. THE BLOCK HAS SHARES — who she is 45%, the weeks 30%, the recent lines 25%, spill
     forward — so a full section can no longer starve the ones after it.
  3. CORE IS A MARK THAT HOLDS — set through the one relabel door, breadcrumbed, leads
     the facts section, and the fold never touches it.
  4. THE FOLD IS CONSOLIDATION WITH LAWS — her-lane diary exhaust only, older than every
     consumer window (14 days), only under a written chapter, tombstoned with the chapter
     named; his testimony, core rows, young rows, and uncovered weeks are untouched; a
     second run folds nothing.

OFFLINE. No GPU, no daemon. Sandboxed stores throughout.
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from _gate import sandbox   # noqa: E402
SB = sandbox("g_memory_story")

os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"

from harness.skills import memory as M          # noqa: E402
from harness.skills import lifecycle as lc      # noqa: E402
from harness.maintenance import ops             # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


REG = os.environ["SP_RECALL_REGISTRY"]


def rows():
    return [json.loads(l) for l in open(REG, encoding="utf-8") if l.strip()]


def rewrite(fn):
    rs = rows()
    for r in rs:
        fn(r)
    with open(REG, "w", encoding="utf-8") as f:
        for r in rs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def day(ago):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - ago * 86400))


print("1. A DISTILLATE IS NOT SILENCED BY ITS OWN SOURCES")
M.remember_about_self("I kept returning to the harbour and to what the tide does to it.",
                      kind="journal")
M.remember_about_self("I spent the evening thinking about the harbour lights.",
                      kind="journal")
_src = [r["name"] for r in rows() if "harbour" in r.get("text", "")]
# AS THE PRODUCER MINTS IT: weekly_chapter's rows are INFERRED (source names the
# reflection pass). A first cut minted this without a source, it landed OBSERVED,
# and §1 was green with the exemption deleted — the chapter was passing as ground
# truth, not as an exempted distillate. The fixture must walk the producer's door.
M.remember_about_self("That week the harbour lights kept circling my thoughts and changed me.",
                      kind="chapter", derived_from=_src, support_days=7,
                      source="reflection (weekly chapter)")
_chrow = next(r for r in rows() if r.get("kind") == "chapter")
check("the fixture chapter is INFERRED, as the real producer mints it",
      _chrow.get("status") == "inferred", _chrow.get("status"))
_scored = [(1.0, r) for r in rows() if not r.get("lifecycle")
           and r.get("speaker") == "self"]
_kept = [e.get("kind") for _s, e in lc.testimony_wins(_scored)]
check("the chapter survives testimony_wins beside its live sources",
      "chapter" in _kept, _kept)
# ...while a bare inference on a covered topic still yields the floor
_bare = {"name": "ep_bare", "text": "I circled the harbour lights in my thoughts nightly.",
         "speaker": "self", "status": "inferred", "mem_class": "self-narrative",
         "ts": day(0), "src": "gate"}
_kept2 = lc.testimony_wins(_scored + [(1.0, _bare)])
check("...and a bare inference on the covered topic is still silenced (the old law)",
      not any(e.get("name") == "ep_bare" for _s, e in _kept2),
      [e.get("name") for _s, e in _kept2])

print("\n2. THE BLOCK HAS SHARES — a full section cannot starve the ones after it")
# DISTINCT sentences, or the near-dup reinforcer folds them into one row: forty
# variations of one template share >0.9 token overlap and land as a single fact.
_THINGS = ("lighthouse", "gullery", "boatshed", "estuary", "shingle", "quayside",
           "breakwater", "anemone", "seagrass", "driftwood", "moorings", "trawler",
           "pilothouse", "sandbar", "kelpbed", "foghorn", "capstan", "bollard",
           "slipway", "wheelhouse", "gantry", "dredger", "pontoon", "mudflat",
           "saltmarsh", "windlass", "tiller", "mainsail", "spinnaker", "bowsprit",
           "galley", "keelson", "rudder", "gunwale", "transom", "forecastle",
           "mizzen", "halyard", "cleat", "fairlead")
_ADJ = ("red", "carved", "weathered", "iron", "painted", "crooked", "mossy", "tall",
        "sunken", "broken", "gilded", "narrow", "ancient", "rusted", "quiet", "pale",
        "northern", "wooden", "leaning", "salt-worn", "green", "hidden", "lonely",
        "storm-bent", "white", "low", "furthest", "oldest", "brick", "stone", "twin",
        "little", "far", "grey", "amber", "cracked", "roped", "tarred", "moored", "last")
for w, a in zip(_THINGS, _ADJ):
    # TWO varying tokens per sentence: one differing word of thirteen is still >=0.9
    # overlap both ways and the reinforcer folds the lot into a single row.
    M.remember_about_self("The %s %s at the harbour has a place in how I think of "
                          "myself." % (a, w))
from harness.personality.self_model import render_self_model  # noqa: E402
blk = render_self_model(budget_chars=2400)
check("forty stable facts alone would overflow the budget (the condition being fixed)",
      sum(len(r.get("text") or "") for r in rows()
          if r.get("speaker") == "self" and not r.get("kind")) > 2400)
check("the chapter still renders", "That week, ending" in blk, blk[-200:])
check("...and at least one recent narrative line renders", "Journal," in blk,
      [l[:40] for l in blk.splitlines()[-4:]])
check("...inside the budget (one oversize first line allowed per section)",
      len(blk) <= 2400 * 1.25, len(blk))

print("\n3. CORE IS A MARK THAT HOLDS")
_target = next(r for r in rows() if "fairlead" in (r.get("text") or ""))
out = ops.relabel(_target["name"], core=True)
check("core is set through the one relabel door", out.get("ok") and
      any(r.get("core") for r in rows() if r["name"] == _target["name"]), out)
check("...and the change is breadcrumbed on the row",
      "core" in next(r.get("src", "") for r in rows() if r["name"] == _target["name"]))
blk2 = render_self_model(budget_chars=2400)
check("a core fact renders even as the newest of forty (unpinned peers drop instead)",
      "fairlead" in blk2, "core did not claim its seat")
check("an unknown row is refused", not ops.relabel("nope", core=True).get("ok"))
# ── AND THE PANEL CAN SEE IT (2026-08-28, his report: "i click pin as core and
# nothing changes. core still says 0"). The write landed on his first click; the
# /v1/memory serializer is a FIXED FIELD LIST and `core` was not on it, so the star
# wrote the row and the read hid it. A mark the panel cannot read is a mark the
# panel cannot toggle — this gate held the store and never the door.
from harness.server.app import _mem_row_json  # noqa: E402
check("the memory API serves the core field",
      _mem_row_json({"name": "x", "text": "t", "core": 1}).get("core") == 1)
check("...and its absence serves as 0, not as missing",
      _mem_row_json({"name": "x", "text": "t"}).get("core") == 0)

print("\n4. THE FOLD — consolidation with laws")
# the world: a chapter 20 days ago covering [27d..20d]; sources inside; controls outside
M.remember_about_self("I walked the pier and wrote about the gulls for an hour.",
                      kind="journal")                    # will backdate to 22d — foldable
M.remember_about_self("I dreamed the tide came all the way in over the town.",
                      kind="dream")                      # 25d — foldable
M.remember_about_self("I keep a small stone from the pier on my desk, always.",
                      kind="journal")                    # 23d + CORE — must stay
M.remember_about_self("I said something unprompted about the pier this morning.",
                      kind="spoke_up")                   # 2d — too young
M.remember_about_self("I thought about the pier long before any chapter existed.",
                      kind="thought")                    # 40d — no chapter covers it
M.remember("The user's pier photograph hangs in the hall.", source="gate")  # his lane
M.remember_about_self("That week the pier and its tide wrote themselves into me.",
                      kind="chapter", support_days=7)    # the chapter — backdate to 20d
# TONIGHT'S chapter, minted AFTER every row above so its ts is >= all of theirs: the
# young row is then deterministically COVERED, and only the AGE guard protects it.
# (A first cut relied on §1's chapter covering it, which depended on which SECOND each
# row was minted in — the mutant was red or green by clock alignment.)
M.remember_about_self("That week I watched the morning gulls and said so out loud.",
                      kind="chapter", support_days=7)
# A SINGLE-GUARD WITNESS for the lane: a user-lane row WEARING a narrative kind. No
# writer produces this shape (kinds are her lane's), so it is planted — the alien shape
# under test, same doctrine as g_memory_lifecycle's orphan plant. KIND passes it;
# only the LANE guard stands between it and the fold.
with open(REG, "a", encoding="utf-8") as _f:
    _f.write(json.dumps({"name": "ep_alien_userkind", "speaker": "user",
                         "kind": "journal", "mem_class": "fact", "status": "observed",
                         "text": "His ledger of pier repairs, oddly filed as a journal.",
                         "ts": day(22), "src": "gate plant"}) + "\n")
AGES = {"walked the pier": 22, "tide came all the way in": 25, "pier photograph": 22,
        "small stone from the pier": 23, "long before any chapter": 40,
        "pier and its tide wrote themselves": 20}


def _stamp(r):
    for frag, ago in AGES.items():
        if frag in (r.get("text") or ""):
            r["ts"] = day(ago)
    if "small stone from the pier" in (r.get("text") or ""):
        r["core"] = 1


rewrite(_stamp)
rec = ops.fold_into_chapters()
check("the fold ran and says what it did", rec.get("ok"), rec)
got = {(r.get("text") or "")[:26]: bool(r.get("lifecycle")) for r in rows()}


def _dead(frag):
    return next(v for k, v in got.items() if k.startswith(frag[:26]) or frag[:20] in k)


def _row(frag):
    return next(r for r in rows() if frag in (r.get("text") or ""))


check("an aged, covered journal row FOLDS", _row("walked the pier").get("lifecycle") == 1)
check("...and so does the dream", _row("tide came all the way").get("lifecycle") == 1)
check("the CORE row does not fold", not _row("small stone").get("lifecycle"),
      _row("small stone"))
check("the YOUNG row does not fold (becoming's window is never starved)",
      not _row("unprompted about the pier").get("lifecycle"))
check("a week with NO chapter keeps its sources",
      not _row("long before any chapter").get("lifecycle"))
check("HIS lane is never folded", not _row("pier photograph").get("lifecycle"))
check("...even wearing a narrative kind (the LANE guard alone stops the plant)",
      not _row("oddly filed as a journal").get("lifecycle"))
check("a chapter never folds — not even into itself",
      not _row("pier and its tide").get("lifecycle"))
_f = _row("walked the pier")
check("the tombstone names the chapter that absorbed it",
      _f.get("superseded_by") == _row("pier and its tide").get("name")
      and "folded into the chapter of" in (_f.get("retired_because") or "")
      and bool(_f.get("superseded_at")), _f.get("retired_because"))
rec2 = ops.fold_into_chapters()
check("a second run folds nothing — the pass is idempotent",
      rec2.get("folded") == 0, rec2)
check("...and says why", "nothing aged" in (rec2.get("why") or ""), rec2.get("why"))
check("the folded rows are gone from recall's candidates (one death field)",
      not any("walked the pier" in (M._text(e) or "")
              for e in M.live_rows()), "a folded row is still live to recall")

print("\nG-MEMORY-STORY: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_memory_story.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_memory_story", "pass": PASS, "fail": FAIL,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
