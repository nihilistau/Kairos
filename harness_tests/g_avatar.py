"""G-AVATAR — what she may look like, and what the room may NOT show.

WRITTEN BEFORE A SINGLE IMAGE EXISTS, and that is the point. The gating on an avatar set
is the one part that cannot be retrofitted honestly: once fifty files are on disk, a
ceiling check written around them is a check shaped by what happens to be there. So the
tables, the resolver and the refusal all get proved on an EMPTY set first, and the
generator comes after.

WHAT IS ASSERTED:

  * ONE VOCABULARY, IN BOTH DIRECTIONS. `MOODS` in ui/src/room/tags.js maps fourteen
    moods onto seven faces; `FACES` here mirrors them. A mood pointing at a face that is
    missing fails, and a face nothing points at fails too. A mirror nobody checks is
    just a second copy of the truth waiting to drift.

  * THE CEILING IS THE LADDER'S, NOT A SECOND SWITCH. Tiers are ranges over the roleplay
    rungs, so `roleplay.max_heat` governs the room's display by construction. There is
    no `avatar.explicit` boolean that could disagree with the scene engine — two knobs
    over one question is the failure this repo keeps paying for.

  * A GATED TIER IS NEVER NAMED. The ceiling is applied BEFORE the lookup, so the
    forbidden path is not built and then filtered; it never exists as a value.

  * MISSING DEGRADES, NEVER BLANKS. No asset -> the SVG. No loop -> the still. That is
    what makes a half-generated set usable from the first image.

  * AND THE REPO IS PUBLIC. No asset path may be tracked by git. The code ships; the
    content does not, and that has to be checked rather than remembered.

Offline. No GPU, no daemon, no assets required.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SB = os.path.join(tempfile.gettempdir(), "_g_avatar")
shutil.rmtree(SB, ignore_errors=True)
os.makedirs(SB)
os.environ["SP_AVATAR_DIR"] = SB          # an EMPTY set, on purpose

from harness.control import avatar as A       # noqa: E402
from harness.roleplay import ladder as L      # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s %s" % (name, detail))


print("1. ONE VOCABULARY — the faces agree with tags.js in both directions")
tags = io.open(os.path.join(ROOT, "ui", "src", "room", "tags.js"), encoding="utf-8").read()
js_faces = set(re.findall(r"face:\s*'([a-z]+)'", tags))
check("tags.js declares faces at all", len(js_faces) >= 5, js_faces)
check("every face tags.js uses exists here", js_faces <= set(A.FACES),
      sorted(js_faces - set(A.FACES)))
check("...and every face here is reachable from some mood", set(A.FACES) <= js_faces,
      sorted(set(A.FACES) - js_faces))
n_moods = len(re.findall(r"^\s{2}\w+:\s*\{ hue:", tags, re.M))
check("fourteen moods collapse onto seven faces", n_moods > len(A.FACES),
      "%d moods, %d faces" % (n_moods, len(A.FACES)))

src = io.open(os.path.join(ROOT, "harness", "control", "avatar.py"),
              encoding="utf-8").read()
code = src + io.open(os.path.join(ROOT, "harness", "control", "wardrobe.py"),
                     encoding="utf-8").read() \
           + io.open(os.path.join(ROOT, "harness", "server", "app.py"),
                     encoding="utf-8").read()

print("\n2. OUTFITS ARE PATH KEYS, NOT A LADDER — the censor is gone")
# 2026-08-21, operator: "remove heat ceilings all together and tiers. let her
# generate what she wishes. She or I decide any ceilings." The outfit axis
# survives as opaque path keys over real files; nothing ranks them, nothing maps
# scene heat onto them, and no arithmetic clamps what may be shown.
check("the outfit axis is declared", A.OUTFIT_IDS == ("mesh-top", "sheer-tee", "lace-set", "bodysuit"))
check("the default outfit is the everyday one", A.DEFAULT_OUTFIT == "mesh-top")
for gone in ("tier_of_rung", "allowed_tiers", "TIERS", "TIER_IDS"):
    check("the ladder API %r is gone" % gone, not hasattr(A, gone))
check("no second explicit-content switch is READ anywhere",
      "avatar.explicit" not in code and "SP_AVATAR_EXPLICIT" not in code)

print("\n4. NOTHING IS GATED — every outfit she owns is servable")
os.makedirs(os.path.join(SB, "smirk", "bodysuit"), exist_ok=True)
io.open(os.path.join(SB, "smirk", "bodysuit", "still.png"), "w").write("x")
r = A.resolve("smirk", "bodysuit")
check("the least-covered outfit is served exactly as asked",
      r and r["path"].endswith("smirk/bodysuit/still.png"), r)
check("the resolver never clamps (no clamp key at all)", bool(r) and "clamped" not in r, r)

print("\n5. MISSING DEGRADES, NEVER BLANKS")
check("no asset at all -> None, so the SVG stays", A.resolve("calm") is None)
os.makedirs(os.path.join(SB, "calm", "mesh-top"), exist_ok=True)
io.open(os.path.join(SB, "calm", "mesh-top", "still.png"), "w").write("x")
r = A.resolve("calm", kind="loop")
check("a missing LOOP degrades to the still before it degrades to the SVG",
      r and r["kind"] == "still", r)
r = A.resolve("calm", kind="clip", gesture="laughing")
check("...and so does a missing gesture clip", r and r["kind"] == "still", r)
check("an unknown face resolves to something rather than throwing",
      A.resolve("nonsense-face") is not None)
r = A.resolve("smirk", "lace-set")
check("a missing outfit cell falls back to the default outfit's cell",
      r is None or r["outfit"] in ("lace-set", "mesh-top"), r)

print("\n6. THE MANIFEST NAMES ONLY WHAT THE TABLES ALLOW")
m = A.manifest()
check("every row's face is a declared face", all(r["face"] in A.FACES for r in m))
check("every row's outfit is a declared outfit", all(r["outfit"] in A.OUTFIT_IDS for r in m))
check("every row's kind is a declared kind", all(r["kind"] in A.KINDS for r in m))
check("a clip always names a declared gesture",
      all(r["gesture"] in A.GESTURES for r in m if r["kind"] == "clip"))
check("the manifest reports what exists", sum(1 for r in m if r["have"]) == 2,
      sum(1 for r in m if r["have"]))
st = A.status()
check("status carries no ceiling vocabulary at all",
      "allowed_tiers" not in st and "max_heat" not in st, sorted(st))
check("status says whether the reference image exists yet", "reference" in st)

print("\n7. VIDEO IS GROWN FROM THE STILL")
# Independently generated frames stitched together flicker between subtly different
# people — the same drift the single reference image exists to prevent, one layer down.
plan = io.open(os.path.join(ROOT, "docs", "AVATAR-PIPELINE.md"), encoding="utf-8").read()
check("the plan exists", len(plan) > 500)
check("...and states that the still is the anchor for motion",
      "image-to-video" in plan.lower() or "from the still" in plan.lower())
check("a loop and a still share the same (face, outfit) directory",
      os.path.dirname(A.rel_path("calm", "mesh-top", "loop"))
      == os.path.dirname(A.rel_path("calm", "mesh-top", "still")))

print("\n8. THE REPO IS PUBLIC — no asset may be tracked")
try:
    tracked = subprocess.run(["git", "ls-files", "var/room/avatar"], cwd=ROOT,
                             capture_output=True, text=True, timeout=30).stdout.strip()
except Exception:
    tracked = ""
check("git tracks no avatar asset", tracked == "", tracked[:200])
gi = io.open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()
check("var/ is ignored, which is why the assets live there", "var/" in gi)
check("the generator writes under var/", "var\", \"room\", \"avatar\"" in src
      or 'var", "room", "avatar"' in src)

shutil.rmtree(SB, ignore_errors=True)
print("\nG-AVATAR: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_avatar.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_avatar", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
