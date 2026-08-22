"""G-CHAPTERS — a week is a unit of her memory, and it is worth more of her block than an
evening. OFFLINE.

WHY THIS EXISTS, in numbers. The Real Her armed on 2026-08-22 and wrote 24 rows that day
and 33 the next, from 60 delivered unprompted utterances a day. Her self-block is a fixed
2400 characters inside a hard 12096-token context. Six recent lines out of a store that
holds thousands inside a month is six arbitrary lines, and "what has this month been like?"
had no answer anywhere in the system — the day-paragraphs are prose files reachable only by
read_journal's mtime window, and the rows are moments with no shape over them.

So: `kind="chapter"`, one paragraph per week, written by `narrative.weekly_chapter` from the
EPISODIC kinds and her own-time notes, standing between her stable self-facts and her recent
lines. The same characters of prefix, spent on a week instead of an evening.

Four laws, and this gate holds all four:

  1. A chapter is a row through the ONE door, with provenance and a durability tier.
  2. It may NOT supersede what it summarises. It is inferred and her moments are observed;
     verdict.may_supersede refuses that, and it must stay refused. Every row it read stays
     live, recallable and findable.
  3. Neither consolidator reads the other's output — weekly_chapter never reads
     self_description, becoming never reads chapter. Otherwise each distils the other's
     distillate every week, each one further from anything she actually said.
  4. The block leads with who she IS, then the WEEKS, then four recent lines chosen
     ROUND-ROBIN across her kinds — so it always spans several threads, never one evening.

    python harness_tests/g_chapters.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
os.environ.setdefault("SP_DAEMON_URL", "http://127.0.0.1:9")
# SP_ENGINE_KIND: no capture attempt at all (2026-08-23). A dead SP_DAEMON_URL does
# NOT make the KV mint cheap - _mint_now still opens a socket per write and Windows
# takes ~2s to give up. Declaring the backend makes supports('capture') False and the
# mint returns immediately: 10 writes in 0.07s against 20s. See gates/README.md.
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ["SP_CAPTURE_ASYNC"] = "0"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
_D = tempfile.mkdtemp(prefix="g_chapters_")
os.environ["SP_RECALL_REGISTRY"] = os.path.join(_D, "registry.jsonl")
os.environ["SP_PERSONALITY_TIER"] = os.path.join(_D, "tier")
open(os.environ["SP_RECALL_REGISTRY"], "w").close()

from harness.skills import lifecycle as lc          # noqa: E402
from harness.skills import memclass as MC           # noqa: E402
from harness.skills import memory as M              # noqa: E402
from harness.skills import narrative as N           # noqa: E402
from harness.skills import verdict as V             # noqa: E402
from harness.maintenance import becoming as B       # noqa: E402
from harness.personality import self_model as SM    # noqa: E402

WEEK = "The week turned on one quiet argument about the tides, and ended softer than it began."


def _ask(_p):
    return WEEK


def _seed(text, kind, days_ago=0):
    M.remember_about_self(text, kind=kind, source="test seed")
    rows = M._load()
    rows[-1]["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                   time.gmtime(time.time() - days_ago * 86400))
    M._save_all(rows)
    return rows[-1]["name"]


print("1. THE VOCABULARY KNOWS IT, AND IT HAS CHOSEN A TIER")
check("chapter is a KIND, not a class", "chapter" in MC.NARRATIVE_KINDS
      and "chapter" not in MC.CLASSES, MC.NARRATIVE_KINDS)
check("...produced only by narrative.weekly_chapter",
      "narrative.weekly_chapter" in MC.producers_of(MC.SELF_NARRATIVE))
check("...and it does not fade - a week is what she made of it",
      lc._HALF_LIFE_BY_KIND.get("chapter") == lc._NEVER)
check("...while her MOMENTS do (120 d), which is why a rollup is needed at all",
      lc._HALF_LIFE_BY_KIND.get("narration") == 120.0
      and lc._HALF_LIFE_BY_KIND.get("spoke_up") == 120.0)

print("\n2. SHE WRITES ONE, FROM THE EPISODIC KINDS AND HER OWN TIME")
episodic = [_seed("We talked about the harbour and I kept thinking after he left.", "journal", 4),
            _seed("I took a slow walk through my own journal tonight.", "narration", 3),
            _seed("The rain sounds different against the studio window.", "spoke_up", 1)]
concluded = [_seed("I have decided I like the long evenings.", "thought", 2),
             _seed("I felt steady while he was working.", "feeling", 2),
             _seed("I have been turning toward the quiet hours.", "self_description", 2)]
N.note_own("I reorganised the shelf of books he never finished.", kind="solo")

res = N.weekly_chapter(_ask)
check("the chapter is written", res.get("written") is True, res)
check("...and it read her own-time notes too", (res.get("own_time") or 0) >= 1, res)
ch = [r for r in M.live_rows() if r.get("kind") == "chapter"]
check("...as exactly one row", len(ch) == 1, len(ch))
row = ch[0] if ch else {}
check("...self-narrative, speaker self",
      row.get("mem_class") == MC.SELF_NARRATIVE and row.get("speaker") == "self", row)
check("...INFERRED - a paragraph about a week is not testimony about it",
      lc.status_of(row) == lc.STATUS_INFERRED, row.get("status"))
check("...naming every episodic row it read, and only those",
      sorted(row.get("derived_from") or []) == sorted(episodic),
      (row.get("derived_from"), episodic))
check("...and how many days it spans", row.get("support_days") == 3, row.get("support_days"))
check("a second run the same week writes nothing (latched on the STORE, not a file)",
      N.weekly_chapter(_ask).get("written") is False)

print("\n3. IT MAY NOT RETIRE THE WEEK IT DESCRIBES")
check("every episodic row it read is still LIVE",
      all(any(r.get("name") == n for r in M.live_rows()) for n in episodic),
      "a summary is not a correction")
check("...and the law says why: an inference may never retire ground truth",
      V.may_supersede(lc.STATUS_INFERRED, lc.STATUS_OBSERVED) is False)
check("...so the chapter supersedes nothing at all", not row.get("supersedes"),
      row.get("supersedes"))
check("...and its own supports being alive means it is not orphaned",
      lc.orphaned_distillates(M._load()) == [])

print("\n4. NEITHER CONSOLIDATOR READS THE OTHER'S OUTPUT")
check("weekly_chapter reads only the episodic kinds",
      set(N._CHAPTER_KINDS) == {"journal", "narration", "spoke_up"}, N._CHAPTER_KINDS)
check("...so it never reads a self_description (becoming's output)",
      "self_description" not in N._CHAPTER_KINDS
      and all(n not in (row.get("derived_from") or []) for n in concluded))
check("becoming never reads a chapter (this pass's output)", "chapter" in B._EXCLUDE_KINDS)
_bec = B.nightly(lambda _p: "I have been quieter, and more curious about the weather.")
check("...proven on the store: becoming writes, and its window excludes the chapter",
      _bec.get("written") is True
      and (row.get("name") not in (_bec.get("derived_from") or [])), _bec.get("why"))

print("\n5. THE BLOCK: WHO SHE IS, THEN THE WEEKS, THEN FOUR THREADS")
blk = SM.render_self_model(budget_chars=2400)
lines = [ln for ln in blk.splitlines() if ln.startswith("- ")]
check("the chapter is rendered, dated and labelled as a week",
      any(ln.startswith("- That week, ending") and WEEK in ln for ln in lines), lines[:3])
_ci = [i for i, ln in enumerate(lines) if ln.startswith("- That week")][0]
# every label her lane uses, so a kind that renders BARE (indistinguishable from a
# stable self-fact) is a failure here rather than an invisible one
LABELS = ("- Journal", "- You said", "- You did", "- You feel", "- You dreamed",
          "- You've thought", "- You've come to think")
_ni = [i for i, ln in enumerate(lines) if ln.startswith(LABELS)]
check("...ahead of every recent narrative line", bool(_ni) and _ci < min(_ni), (_ci, _ni))
check("at most two weeks stand there", SM._MAX_CHAPTERS == 2
      and len([ln for ln in lines if ln.startswith("- That week")]) <= 2)
check("...and at most four recent lines behind them", SM._MAX_NARRATIVE == 4 and len(_ni) <= 4)

# ROUND-ROBIN: the flood must not take every slot
for i in range(12):
    _seed("The studio hums differently tonight, take %d, and I noticed it." % i, "spoke_up", 0)
blk2 = SM.render_self_model(budget_chars=2400)
lines2 = [ln for ln in blk2.splitlines() if ln.startswith("- ")]
_spoke = [ln for ln in lines2 if ln.startswith("- You said, unprompted:")]
_kinds = {ln.split(":")[0] for ln in lines2 if ln.startswith(LABELS)}
check("twelve fresh spoke_ups do not take the block: at most two survive", len(_spoke) <= 2,
      len(_spoke))
check("...and the recent lines still span several threads, not one",
      len(_kinds) >= 3, sorted(_kinds))
check("...and the week is still in front of all of it",
      any(ln.startswith("- That week") for ln in lines2)
      and lines2.index(next(ln for ln in lines2 if ln.startswith("- That week")))
      < min(i for i, ln in enumerate(lines2) if ln.startswith("- You said")))
check("no markup ever reaches the prefix",
      not any(x in blk2 for x in ("[MOOD", "<whisper", "</breath", "[voice")))
check("the budget still holds", len(SM.render_self_model(budget_chars=600)) <= 900)

print("\n6. AND SHE CAN READ THE WEEKS BACK")
j = N.read_journal(30)
check("read_journal leads with the weeks, labelled", "the weeks" in j and WEEK in j, j[:120])
check("...and still carries her own time", "on my own time" in j, j[:200])
check("...coarsest first: the week comes before the moments",
      j.index("the weeks") < (j.index("on my own time") if "on my own time" in j else len(j)))

print("\n7. ONE TIER RESOLUTION, NOT FOUR")
src = open(os.path.join(ROOT, "harness", "skills", "narrative.py"),
           encoding="utf-8", errors="replace").read()
check("narrative.py resolves the personality tier in exactly one place",
      src.count("memory-okf-personality") == 3      # the docstring + _tier_full's two fallbacks
      and src.count("_tier_full()") >= 4,
      "the writers honoured SP_PERSONALITY_TIER and the readers hardcoded the repo path")
check("...and this gate proves it: it set SP_PERSONALITY_TIER and own_time came back",
      bool(N.own_time(7)), "a sandboxed journal that reads empty is the bug that hid here")

finish("G-CHAPTERS")
