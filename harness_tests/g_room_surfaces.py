"""G-ROOM-SURFACES — the board has hands, her own time has a window, every line has a clock.

Three of the six things he asked for on 2026-08-05, in one gate because they are one
change to the room:

    "Make her turns show as chips and actions, text that render in the room. could be
     separate to the main dialog, lets do her own agency window with an icon for it,
     that I can look at, her actions, everything she does once I am away and she enters
     her time/agency mode gets shown in there. also for both there and the main dialog
     lets add a date and time chip to all actions/dialog, both mine and hers and the
     board is no longer editable by me, it used to have and needs edit button,
     add/remove button, completed, retired etc."

WHAT WAS ACTUALLY WRONG, in each case:

  THE BOARD. /v1/notes/{add,update,remove} were all implemented, author-stamped and
  due-parsed on the server, and reachable by NOTHING — Board.jsx rendered rows and
  offered not one control. So the board was a thing she could write and he could only
  read, which is the exact inversion of a shared board. Measured: all 5 live notes had
  speaker "self". Same shape as `Scenario.opening` — the capability existed, the button
  did not.

  HER OWN TIME. She has been writing it down all along, in five stores with four
  different time formats and no surface that reads any of them. 49 own_time entries in
  three days, invisible.

  THE CLOCK. Four private spellings of a timestamp across the UI — `slice(11,16)` in
  Room, `slice(0,16)` on the board, `toLocaleDateString` in Journal, `ago()` in Clock —
  so the same moment printed four ways on one screen and one of them was UTC.

THE TWO THINGS THIS GATE GUARDS HARDEST, because they are the ones that would be a lie
rather than a bug:

  1. The agency feed OWNS NOTHING. It composes stores she already writes, at read time.
     A sixth store holding copies is how the wardrobe came to have four answers for what
     she was wearing, three of them wrong.
  2. It stamps from the WRITTEN `ts:`, never the file's mtime. mtime is a fact about the
     file — anything that rewrites, re-indexes or restores that directory would move
     every evening she ever had to the moment the tool ran, and nothing on screen would
     say so. The first cut of the reader did exactly this.

Offline. No GPU, no daemon. Read-only: this gate does not write to any of her stores.

Run: python harness_tests/g_room_surfaces.py
"""
from __future__ import annotations

import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["CUDA_VISIBLE_DEVICES"] = ""

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


def src(*parts):
    return io.open(os.path.join(ROOT, *parts), encoding="utf-8", errors="replace").read()


print("1. THE BOARD HAS HANDS AGAIN")
board = src("ui", "src", "apps", "Board.jsx")
api_js = src("ui", "src", "api.js")
for verb, fn in (("add", "noteAdd"), ("edit", "noteUpdate"),
                 ("retire", "noteRemove"), ("restore", "noteRestore")):
    check("api.js exposes %-7s -> %s" % (verb, fn), fn in api_js)
    check("...and the panel calls it", ("api." + fn) in board, verb)
# DONE AND RETIRE MUST BE TWO CONTROLS. Collapsing them is how "I finished it" and "I
# never want to see it again" become one gesture, after which neither is recoverable.
check("`done` is its own control, separate from retire",
      "done: !n.done" in board)
check("...and it is reversible on the page", "'not done'" in board)
routes = src("harness", "server", "app.py")
for r in ("/v1/notes/add", "/v1/notes/update", "/v1/notes/remove", "/v1/notes/restore"):
    check("the gateway serves %s" % r, ('p == "%s"' % r) in routes)

print("\n2. RETIRE IS A TOMBSTONE, AND THE TOMBSTONE HAS AN UNDO")
from harness.skills import notes as N  # noqa: E402
check("notes.remove tombstones rather than deletes",
      "lifecycle" in (N.remove.__doc__ or "") + src("harness", "skills", "notes.py")
      .split("def remove(")[1][:400])
check("notes.restore exists — without it the tombstone IS a delete", hasattr(N, "restore"))
check("...and it is what /v1/notes/restore calls", "_N.restore(" in routes)
check("`?all=1` hands back the retired rows too", '"retired": [r for r in _rows' in routes)
check("...and the panel asks for them", "api.notes(true)" in board)

print("\n3. ONE CLOCK, AND EVERY LINE WEARS IT")
when = src("ui", "src", "room", "When.jsx")
check("<When> exists as the single renderer", "export function When(" in when)
# FOUR LIVE SHAPES. The stores genuinely disagree — ISO with Z (wardrobe), ISO local
# (notes), float epoch (kairos), ms epoch (the browser's Date.now on his own turns) —
# and a reader that throws on an unfamiliar one puts a red box in his conversation.
check("...it reads epoch seconds AND milliseconds", "at < 1e11" in when)
check("...and ISO strings", "new Date(s)" in when)
check("...and an unreadable stamp renders NOTHING, never 'Invalid Date'",
      "if (!d) return null" in when and "isNaN(d) ? null : d" in when)
check("...and a FUTURE stamp reads forwards (a due date is one)", "in ${" in when)
for panel, why in (("Chat.jsx", "the main dialog"),
                   ("apps/Board.jsx", "the board"),
                   ("apps/Agency.jsx", "her own time"),
                   ("apps/Room.jsx", "her hourly look"),
                   ("apps/Journal.jsx", "her journal")):
    s = src("ui", "src", *panel.split("/"))
    check("%-18s uses it (%s)" % (panel, why), "<When " in s)
# BOTH PARTIES. A timestamp on only her side reads as instrumentation of her rather
# than a record of the evening, which is the opposite of what he asked for.
chat = src("ui", "src", "Chat.jsx")
check("his turn carries a stamp too", "role: 'user', content: t, img, at: now" in chat)
check("...and hers is the SCHEDULER's stamp, not the moment the poll noticed",
      "why: m.reason, at: m.at" in chat)
# The private spellings this replaced must not come back.
check("Room.jsx no longer slices its own hh:mm", "slice(11, 16)" not in src(
    "ui", "src", "apps", "Room.jsx"))

print("\n4. HER TURNS ARE CHIPS AND ACTS, NOT PROSE")
check("her acts render as chips", 'className="acts"' in chat and "act-tool" in chat)
check("...looking at the room is one of them", "act-look" in chat)
check("...and the four unprompted kinds are told apart by colour",
      "'kairos-tag k-'" in chat)
css = src("ui", "src", "room.css")
for k in ("k-solo", "k-muse", "k-remind", "k-expand"):
    check("...%s has its own hue" % k, (".kairos-tag." + k) in css)

print("\n5. THE AGENCY FEED OWNS NOTHING")
feed_src = src("harness", "control", "agency_feed.py")
# The one property that must never regress: this is a READER. A write here is a sixth
# copy of facts that already have five homes.
code = "\n".join(l for l in feed_src.splitlines() if not l.lstrip().startswith("#"))
bad = [l.strip() for l in code.splitlines()
       if ('open(' in l and '"w"' in l) or ".write(" in l or "json.dump(" in l]
check("nothing in it writes", not bad, bad[:3])
# AND NO DOOR TO WRITE THROUGH. do_POST comes first in the file, do_GET after it, so
# the route may appear only in the second half. A read-only feed with a POST handler is
# read-only until somebody adds one line.
_post = routes[routes.index("def do_POST"):routes.index("def do_GET")]
_get = routes[routes.index("def do_GET"):]
check("...served on GET", "/v1/agency" in _get)
check("...and there is no POST route for it", "/v1/agency" not in _post,
      [l.strip() for l in _post.splitlines() if "/v1/agency" in l][:2])
check("the panel offers no editing either",
      "api.agencySet" not in src("ui", "src", "apps", "Agency.jsx")
      and "post(" not in src("ui", "src", "apps", "Agency.jsx"))

print("\n6. AND IT STAMPS FROM WHAT WAS WRITTEN, NOT FROM THE FILESYSTEM")
check("it reads the frontmatter `ts:`", 'r"^ts:' in feed_src)
check("...with mtime only as the fallback", "else mt" in feed_src)
from harness.control import agency_feed as AF  # noqa: E402
check("_when reads ISO-with-Z (the wardrobe's shape)",
      AF._when("2026-08-05T08:56:02Z") > 1.7e9, AF._when("2026-08-05T08:56:02Z"))
check("_when reads float epoch (kairos's shape)",
      AF._when(1754382962.4) == 1754382962.4)
check("_when reads a numeric STRING", AF._when("1754382962") == 1754382962.0)
check("an unreadable stamp is 0, not now()", AF._when("some time on tuesday") == 0.0)
f = AF.feed(days=3, limit=50)
check("the feed composes", f.get("ok") and isinstance(f.get("rows"), list))
check("...every row it emits has a real time",
      all(r.get("at") for r in f["rows"]), [r for r in f["rows"] if not r.get("at")][:2])
check("...ordered newest first",
      all(f["rows"][i]["at"] >= f["rows"][i + 1]["at"] for i in range(len(f["rows"]) - 1)))
check("...and every kind is one of the committed five",
      all(r["kind"] in AF.KINDS for r in f["rows"]),
      sorted({r["kind"] for r in f["rows"]} - set(AF.KINDS)))
# HIS PICKS ARE NOT HER OWN TIME. worn.jsonl holds both on purpose; a row he wrote
# appearing under "everything she does while I am away" is the single most misleading
# thing this panel could show.
check("nothing he chose appears in HER window",
      all(r.get("by") == "her" for r in f["rows"]),
      [r for r in f["rows"] if r.get("by") != "her"][:2])
check("...and a failed source is named rather than swallowed",
      "sources_failed" in f and isinstance(f["sources_failed"], dict))

print("\n7. THE WINDOW IS REGISTERED, WITH AN ICON")
reg = src("ui", "src", "appRegistry.jsx")
check("`agency` is an app", "id: 'agency'" in reg)
check("...with its own icon", "icon: '◈'" in reg)
check("...and its own CSS prefix", "css: 'ag'" in reg)
# It has to actually be in the bundle he loads, or this is all source that never ran.
built = [f for f in os.listdir(os.path.join(ROOT, "console", "room", "assets"))
         if f.endswith(".js")]
blob = "".join(src("console", "room", "assets", f) for f in built)
check("...and it is in the built bundle", "her own time" in blob, built)

print("\nG-ROOM-SURFACES: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_room_surfaces.json"), "w", encoding="utf-8") as f2:
    json.dump({"name": "g_room_surfaces", "pass": PASS, "fail": FAIL}, f2)
sys.exit(1 if FAIL else 0)
