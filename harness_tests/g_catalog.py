"""G-CATALOG — everything she can wear, do or show is ONE list, and his edits rule it. OFFLINE.

His overhaul, 2026-08-21: remove / hide / unhide clothing, gestures and moments; import
his own videos through the same tooling a made look passes through; edit title,
description and category; and tell HER what she owns by kind. This gate drives the
real seams — harness/control/catalog.py over wardrobe.looks()/clips() — in a sandbox
closet, so nothing real is touched and the store it measures is the one it made.

    python harness_tests/g_catalog.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SB = tempfile.mkdtemp(prefix="g-catalog-")
os.environ["SP_AVATAR_DIR"] = SB          # avatar.root() / wardrobe.root() -> the sandbox

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


from harness.control import avatar as AV        # noqa: E402
from harness.control import wardrobe as WD      # noqa: E402
from harness.control import catalog as C        # noqa: E402

# ── A CLOSET TO WORK IN: two made looks (one a gesture), one clip ────────────────────
os.makedirs(os.path.join(SB, "looks"), exist_ok=True)
os.makedirs(os.path.join(SB, "clips"), exist_ok=True)
r1 = WD.request("the silver nightie by the window", tier="t0", by="her", kind="look")
r2 = WD.request("laughing properly, head back", tier="t0", by="her", kind="gesture")
for r in (r1, r2):
    open(os.path.join(SB, "looks", r["id"] + ".png"), "wb").write(b"\x89PNG\r\n\x1a\n")
    open(os.path.join(SB, "looks", r["id"] + ".webm"), "wb").write(b"\x1aE\xdf\xa3")
    WD.fulfil(r["id"], file=r["id"] + ".png", state="made", loop=r["id"] + ".webm")
open(os.path.join(SB, "clips", "silver-nightie-bedroom.mp4"), "wb").write(b"\x00" * 64)
clip = WD.import_clip(os.path.join(SB, "clips", "silver-nightie-bedroom.mp4"))
LOOK, GEST, CLIP = r1["id"], r2["id"], clip["id"]

print("1. ONE SHAPE, THREE STORES, DEFAULT CATEGORIES")
rows = C.rows()
ids = {r["id"]: r for r in rows}
check("the grid outfits, her looks and his clips are all rows",
      all(k in ids for k in list(AV.OUTFIT_IDS) + [LOOK, GEST, CLIP]), sorted(ids))
check("a look defaults to clothing", ids[LOOK]["category"] == "clothing")
check("a gesture want defaults to gesture", ids[GEST]["category"] == "gesture")
check("a clip defaults to moment", ids[CLIP]["category"] == "moment")
check("every row carries the panel's media urls",
      all("still_url" in r and "loop_url" in r for r in rows))
check("by_category groups them", set(C.by_category()) == set(C.CATEGORIES))

print("\n2. HIS EDITS RULE — title, description, category, tags — everywhere at once")
e = C.edit(LOOK, title="the window nightie", description="morning light, her favourite",
           category="moment", tags=["nightie", "window"])
check("edit is accepted", e.get("ok"), e)
row = {r["id"]: r for r in C.rows()}[LOOK]
check("the title he typed beats the want text", row["title"] == "the window nightie", row["title"])
check("...and reaches wardrobe.looks(), the reader every consumer uses",
      any(l["id"] == LOOK and l["label"] == "the window nightie" for l in WD.looks()))
check("...and the base label is kept beside it", row["base_label"].startswith("the silver"))
check("category moved to moment", row["category"] == "moment")
# ── THE PROPERTY IS "HIS TITLE REACHES HER", NOT "IN THE BY-KIND BLOCK" (2026-08-28).
# for_her() slimmed to counts + verbs — measured, it was re-listing by name what
# describe() had just enumerated above it (16 of 26 items appeared twice; 5,451 chars).
# His title flows to her through looks()' labels now — the reader every consumer uses,
# asserted two checks up — so the surface to hold is the WHOLE of what she reads.
check("what she reads carries his title for it",
      "the window nightie" in WD.describe())
bad = C.edit(LOOK, category="costume")
check("an unknown category is refused, not stored", not bad.get("ok"))
check("an unknown id is refused", not C.edit("nope", title="x").get("ok"))

print("\n3. HIDE IS SOFT, REMOVE IS A TOMBSTONE, BOTH LEAVE THE FILE AND THE ROW")
WD.choose(tier="t0", look=GEST, by="her")
h = C.hide(GEST)
check("hide is accepted", h.get("ok"))
check("a hidden row leaves looks() — her tools cannot reach it",
      not any(l["id"] == GEST for l in WD.looks()))
check("...but looks(all=True) still has it, flagged",
      any(l["id"] == GEST and l["hidden"] for l in WD.looks(all=True)))
check("hiding what she has ON takes it off her", WD.current().get("look") != GEST)
check("rows() hides it by default, rows(include_hidden) offers it back",
      not any(r["id"] == GEST for r in C.rows())
      and any(r["id"] == GEST for r in C.rows(include_hidden=True)))
check("nothing she reads names it any more", "laughing properly" not in WD.describe())
C.unhide(GEST)
check("unhide brings it back", any(l["id"] == GEST for l in WD.looks()))
rm = C.remove(CLIP)
check("remove is accepted", rm.get("ok"))
check("a removed clip leaves clips() and looks()",
      not any(c["id"] == CLIP for c in WD.clips())
      and not any(l["id"] == CLIP for l in WD.looks()))
check("...the FILE is still on disk — nothing deleted",
      os.path.exists(os.path.join(SB, "clips", "silver-nightie-bedroom.mp4")))
check("...the row is still in clips.json",
      any(c["id"] == CLIP for c in json.load(open(os.path.join(SB, "clips", "clips.json")))))
check("...and rows(include_removed) shows it with removed_at",
      any(r["id"] == CLIP and r["removed_at"] for r in C.rows(include_removed=True)))
check("the standard set cannot be removed, only hidden", not C.remove("t0").get("ok"))
C.restore(CLIP)
check("restore undoes the tombstone", any(c["id"] == CLIP for c in WD.clips()))

print("\n4. IMPORT: his file, through the same tooling, registered as hers")
inbox = C.inbox_dir()
os.makedirs(inbox, exist_ok=True)
have_ffmpeg = shutil.which("ffmpeg") is not None
if have_ffmpeg:
    # a real 1-second mp4 so the encoder path is the real encoder path
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc=duration=1:size=64x64:rate=10",
                    os.path.join(inbox, "wave-hello.mp4")], timeout=120)
    check("the inbox lists what he dropped in",
          any(f["file"] == "wave-hello.mp4" for f in C.inbox()))
    imp = C.import_file("wave-hello.mp4", "gesture", title="a small wave",
                        description="fingers only", tags=["wave", "hello"], loop=True)
    check("the import is accepted", imp.get("ok"), imp)
    wid = imp.get("id")
    check("it became a MADE want by him", any(w["id"] == wid and w["state"] == "made"
                                             and w["by"] == "him" for w in WD.wants()))
    check("...with a webm loop and a poster still in looks/",
          os.path.exists(os.path.join(SB, "looks", wid + ".webm"))
          and os.path.exists(os.path.join(SB, "looks", wid + ".png")))
    check("...his file stays in the inbox (copied, never moved)",
          os.path.exists(os.path.join(inbox, "wave-hello.mp4")))
    row = {r["id"]: r for r in C.rows()}.get(wid) or {}
    check("it is a gesture with his title, moving, source imported",
          row.get("category") == "gesture" and row.get("title") == "a small wave"
          and row.get("moves") and row.get("source") == "imported", row)
    check("her matcher finds it by his words",
          (WD.match("wave hello", prefer="gesture") or {}).get("id") == wid)
    # a still image imports as a still-only look — motion to be grown later
    open(os.path.join(inbox, "red-dress.png"), "wb").write(b"\x89PNG\r\n\x1a\n")
    imp2 = C.import_file("red-dress.png", "clothing", title="the red dress")
    check("a still imports as a still-only look", imp2.get("ok") and not imp2.get("moves"), imp2)
    check("...that says the motion can be grown", "make it now" in (imp2.get("note") or ""))
    imp3 = C.import_file("wave-hello.mp4", "moment", title="the wave, on his screen")
    check("a moment import lands in the clips store",
          imp3.get("ok") and any(c["id"] == imp3["id"] for c in WD.clips()), imp3)
else:
    print("  skip ffmpeg not on PATH — import leg not run")
check("an unknown file is refused", not C.import_file("nope.mp4", "gesture").get("ok"))
check("an unknown category is refused", not C.import_file("wave-hello.mp4", "thing").get("ok"))

print("\n5. SHE IS TOLD, BY KIND, WITH THE ACT FOR EACH")
t = C.for_her()
for cat, act in (("CLOTHING", "wear("), ("GESTURE", "express("), ("MOMENT", "show_him(")):
    check("for_her names %s and its act" % cat, cat in t and act in t)
check("describe() — what check_wardrobe hands her — ends with the by-kind block",
      "BY KIND" in WD.describe())
src = open(os.path.join(ROOT, "harness", "skills", "wardrobe.py"), encoding="utf-8").read()
check("she has gesture() beside express()", "def gesture(" in src and "gesture]" in src)

print("\nG-CATALOG  %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
