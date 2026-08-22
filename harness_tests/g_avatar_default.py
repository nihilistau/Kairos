"""G-AVATAR-DEFAULT — the shipped face: complete, anonymous, and unable to eat a wardrobe.

THE CLASS. Seeding is the shape of bug this repo keeps paying for: a convenience that
runs at boot, writes into state somebody made, and is indistinguishable from working
until the thing it overwrote is missed. The re-export that once wiped a live stack's
token and persona is the same shape. So the seeder has three rules and this gate is
those three rules, plus the two properties of the SET itself that cannot be checked by
reading the code:

  1. IT ONLY FILLS GAPS      — a destination that exists is never touched.
  2. IT RUNS ONCE PER SET    — delete a bundled gesture and it stays deleted.
  3. IT NEVER FAILS THE BOOT — every path returns a dict; nothing raises.

  4. THE SET IS COMPLETE     — every face MOODS can reach has a cell, or the room shows
                               the SVG for exactly the mood she is in most.
  5. THE SET IS ANONYMOUS    — no receipt carries a `prompt`. The images ship; the
                               writing that made them does not, and "we meant to strip
                               that" is not a thing you can say after a push.

  6. THE IDS CANNOT COLLIDE  — wardrobe.request() mints from the high-water mark of
                               `w(\\d+)`. A bundled id matching that pattern would put a
                               user's first want on top of a bundled file, on disk.

SKIP where there is no bundled set — the source repo does not carry one (the export
overlay does). Vacuous there, real in Kairos, and the exit code says which.

    python harness_tests/g_avatar_default.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, skip, utf8_stdout  # noqa: E402

utf8_stdout()

from harness.control import avatar as AV  # noqa: E402
from harness.control import avatar_seed as SEED  # noqa: E402

SRC = SEED.assets_dir()
if not os.path.isdir(SRC) or not os.path.isfile(os.path.join(SRC, "SET.json")):
    skip("no bundled set at %s (the source repo ships it through the export overlay)" % SRC,
         "G-AVATAR-DEFAULT")

print("\n1. THE SET IS COMPLETE — every face MOODS can reach has a cell")
meta = json.load(open(os.path.join(SRC, "SET.json"), encoding="utf-8"))
outfit = meta.get("outfit") or AV.DEFAULT_OUTFIT
check("SET.json names a set id", bool(meta.get("set")), meta)
check("the bundled outfit is the default outfit", outfit == AV.DEFAULT_OUTFIT,
      "%r vs %r" % (outfit, AV.DEFAULT_OUTFIT))
for face in AV.FACES:
    for kind, ext in (("still", ".png"), ("loop", ".webm")):
        p = os.path.join(SRC, face, outfit, kind + ext)
        check("%s/%s/%s%s ships" % (face, outfit, kind, ext),
              os.path.isfile(p) and os.path.getsize(p) > 0, p)
# EVERY MOOD, NOT EVERY FACE THAT HAPPENS TO BE THERE. FACES is the table; MOOD_FACE is
# what her marks actually reach. A face in FACES that no mood points at would be dead
# weight, and a mood pointing at a face with no cell is the SVG appearing mid-sentence.
check("every mood reaches a face that has art",
      set(AV.MOOD_FACE.values()) <= set(AV.FACES),
      sorted(set(AV.MOOD_FACE.values()) - set(AV.FACES)))

print("\n2. THE GESTURES ARE WEARABLE AND CANNOT COLLIDE")
rows = [json.loads(l) for l in open(os.path.join(SRC, "wants.jsonl"), encoding="utf-8")
        if l.strip()]
check("six gestures ship", len(rows) == 6, len(rows))
for r in rows:
    wid = str(r.get("id") or "")
    # THE COLLISION CHECK. `w003` would be minted again the moment a user's wants file
    # reaches three rows, and looks/w003.png is one path with two owners.
    check("%s cannot be re-minted by request()" % wid, not re.match(r"w(\d+)$", wid), wid)
    check("%s is a gesture" % wid, r.get("kind") == "gesture", r.get("kind"))
    # `looks()` drops a want with no loop (a still is not in her wardrobe yet) and the
    # /v1/wardrobe/look route 404s a made want with no `file`. Both keys are load-bearing.
    check("%s is made, with both files named" % wid,
          r.get("state") == "made" and r.get("file") and r.get("loop"), r)
    for key in ("file", "loop"):
        p = os.path.join(SRC, "looks", str(r.get(key)))
        check("%s %s is on disk" % (wid, key), os.path.isfile(p) and os.path.getsize(p) > 0, p)
    # Without a written vocabulary she owns six gestures she cannot name — the matcher
    # scores against `calls`, and inferring them from the label is the prose-rules-code
    # failure AGENTS.md §5 forbids.
    check("%s carries words she can reach it by" % wid, len(r.get("calls") or []) >= 2, r.get("calls"))

print("\n3. THE SET IS ANONYMOUS — the images ship, the prompts do not")
leaked = []
for base, _d, files in os.walk(SRC):
    for fn in files:
        if not fn.endswith(".json"):
            continue
        try:
            d = json.load(open(os.path.join(base, fn), encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and d.get("prompt"):
            leaked.append(os.path.relpath(os.path.join(base, fn), SRC))
check("no receipt carries a prompt", not leaked, leaked)
ch = open(os.path.join(SRC, "character.txt"), encoding="utf-8").read()
check("character.txt says out loud that it is a template",
      "TEMPLATE" in ch.upper(), ch[:80])
check("the reference ships beside it",
      os.path.isfile(os.path.join(SRC, "_reference.png")), SRC)

print("\n4. THE SEEDER — gaps only, once per set, never raises")
tmp = tempfile.mkdtemp(prefix="g_avdefault_")
old = os.environ.get("SP_AVATAR_DIR")
try:
    os.environ["SP_AVATAR_DIR"] = tmp
    # A file the "user" already has, with contents nothing may replace.
    face0 = AV.FACES[0]
    keep = os.path.join(tmp, face0, outfit, "still.png")
    os.makedirs(os.path.dirname(keep), exist_ok=True)
    with open(keep, "wb") as f:
        f.write(b"MINE")
    # And a want row they already carry, so the append cannot double it.
    with open(os.path.join(tmp, "wants.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps(rows[0]) + "\n")

    r1 = SEED.seed()
    check("first seed reports it laid the set down", r1.get("seeded") is True, r1)
    check("it did not overwrite a file that was already there",
          open(keep, "rb").read() == b"MINE", keep)
    laid = [os.path.join(tmp, f, outfit, "still.png") for f in AV.FACES[1:]]
    check("every other face landed", all(os.path.isfile(p) for p in laid),
          [p for p in laid if not os.path.isfile(p)])
    got = [json.loads(l) for l in open(os.path.join(tmp, "wants.jsonl"), encoding="utf-8")
           if l.strip()]
    check("six gesture rows, not seven", len(got) == 6, len(got))
    check("no id appears twice", len({r["id"] for r in got}) == len(got),
          [r["id"] for r in got])

    r2 = SEED.seed()
    check("a second seed is a no-op", r2.get("seeded") is False and r2.get("files") == 0, r2)

    # RULE 2, THE ONE THAT MATTERS MOST. Deleting a bundled gesture is a decision, and a
    # seeder that hands it back every boot has quietly overruled it forever.
    gone = os.path.join(tmp, "looks", rows[1]["file"])
    os.remove(gone)
    SEED.seed()
    check("a deleted asset is not handed back", not os.path.exists(gone), gone)

    st = SEED.status()
    check("status reports the set as seeded", st.get("seeded") is True, st)
    check("status counts the faces that actually have art",
          st.get("faces_with_art") == len(AV.FACES), st)

    # RULE 3. A missing bundle is a room with the SVG in it, not a failed boot.
    os.environ["SP_AVATAR_DEFAULTS"] = os.path.join(tmp, "does-not-exist")
    r3 = SEED.seed()
    check("an absent bundle is a clean no-op", r3.get("ok") is True and not r3.get("seeded"), r3)
finally:
    os.environ.pop("SP_AVATAR_DEFAULTS", None)
    if old is None:
        os.environ.pop("SP_AVATAR_DIR", None)
    else:
        os.environ["SP_AVATAR_DIR"] = old
    shutil.rmtree(tmp, ignore_errors=True)

finish("G-AVATAR-DEFAULT")
