"""G-ROOM-CSS — one class name, one owner.

THE BUG THIS EXISTS FOR. The ledger's first cut named a row `.led`. `ui/src/room.css`
has used `.led` since the shell was built — it is the 8px status dot beside "warm" in
the header (`width: 8px; height: 8px; border-radius: 50%`). So every ledger row was an
8x8 circle with `overflow: hidden`, clipping its own contents to nothing. The titles
were in the DOM the whole time, laid out 20px wide and 89px tall inside a box eight
pixels square. One name, two meanings, and the one that ran was the other one — the
same shape as the bridged `take_screenshot` overwriting the native one, and the same
shape as AGENTS.md §0.

THE RULE. A class an app uses must be one of:
  * SHARED — the committed list below. Furniture: `pad`, `muted`, `on`, `chips`, `err`.
    These are deliberately common and deliberately few.
  * ITS OWN PREFIX — the `css:` field each app declares in `ui/src/appRegistry.jsx`,
    either bare (`lgr`) or hyphenated (`lgr-title`).
  * GRANDFATHERED — names that predate this gate. A RATCHET: the table may shrink and
    may never grow, and an entry that is no longer used anywhere is a stale excuse and
    fails. A baseline that only grows is not a baseline, it is a permission slip.

And the direct check: **a class used by two owners, blessed by neither list, is a
collision.** That is the one that would have caught `.led` on the day it was written.

Offline. Reads sources only — no build, no browser, no daemon.
"""
from __future__ import annotations

import collections
import glob
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "ui", "src")

# ── SHARED FURNITURE ─────────────────────────────────────────────────────────────
# Any app may use these. Keep the list SHORT: every addition is a name that can no
# longer collide, which is also a name that no longer means anything specific.
SHARED = frozenset({
    "pad", "muted", "on", "err", "chips", "row", "k", "v", "note", "r-off",
    "meta", "who", "sal", "cls", "gone",
    # TONE. Presentational only — they say how a thing reads, never what it is, which
    # is what makes them safe to share where `t` or `now` are not. Added 2026-08-01
    # when this gate caught its own author: Stage used `warn`, Ledger already did, and
    # the collision check fired on the day after it landed. Blessing the whole family
    # rather than the one name, so `bad` does not repeat the same failure next month.
    "good", "bad", "warn",
    # TIME. `<When>` (ui/src/room/When.jsx) is the ONE renderer of a timestamp, and it is
    # meant to appear on every line either of them produces — the board, the chat, her
    # agency window. Shared furniture in the literal sense: one component, one pair of
    # names, no app owns it. Blessed 2026-08-05 with the chip itself, rather than letting
    # four panels grow four spellings of the same fact, which is what it replaced.
    "when", "when-ago",
    # SHUTTING HER DOWN. Shell furniture, not an app: the dock button and the down state
    # both live outside any panel, and there is no app that could own them.
    "sd-wrap", "sd-btn", "sd-confirm", "sd-opt", "sd-kill", "sd-cancel",
    "sd-down", "sd-down-mark", "sd-down-t", "sd-down-b",
    # OFF THE RECORD (2026-08-23). Shell furniture for the same reason the shutdown
    # button is: the switch appears in the DOCK, in the TASKBAR and on the room element
    # itself, three owners and no app that could hold it. `an-on` is a modifier on
    # `.room` rather than a class of its own, which is the point — the mode has to be
    # visible on every frame without a window being open.
    "an-wrap", "an-btn", "an-receipt", "an-chip", "an-held", "an-on",
    # HER CLOTHES CHANGING, from the tool as well as the mark (2026-08-24).
    # Chat furniture, beside act-look and act-notice, which are already here.
    "act-wear",
})

# ── SHARED FAMILIES (2026-08-21, the panel-framework session) ────────────────────
# A whole PREFIX family whose rows are rendered by exactly ONE shared module — the
# panel.jsx idea grown up. knobs.jsx renders every `st-` control row (settings, the
# voice panel, the search panel's engine section — one renderer, one stylesheet
# section, so the two-stylesheets ambiguity this gate exists for cannot arise);
# looks.jsx renders every `rsc-` ledger row for the search and research windows;
# titleChips.jsx renders every `tc` window-bar chip. The family's HOME app (the
# registry row that declares the prefix) is recorded; the renderer module is the
# only file allowed to define NEW names in the family, which §4b enforces.
SHARED_FAMILIES = {
    "st":  "shared:knobs",        # home app: settings
    "rsc": "shared:looks",        # home app: research
    "tc":  "shared:titlechips",   # no home app — window chrome furniture
}
SHARED_MODULES = {"panel", "knobs", "looks", "titlechips"}


def family_of(c: str):
    head = c.split("-", 1)[0]
    return head if head in SHARED_FAMILIES else None

# ── GRANDFATHERED ────────────────────────────────────────────────────────────────
# Cross-owner names that predate the rule. RATCHET: shrink only. Each is a real
# ambiguity, listed so it is visible rather than tolerated in silence.
GRANDFATHERED = frozenset({
    "dragging",   # shell drags a window; Files drags a file onto a dropzone
    "now",        # Journal "today"; Music "now playing"
    "t",          # Board note text; Memory row text; Music track title
})
GRANDFATHERED_MAX = len(GRANDFATHERED)   # frozen. Lowering this is the only edit allowed.

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s %s" % (name, detail))


def classes_in(src: str):
    """Every class literal in a JSX file. Deliberately over-collects from expressions:
    a missed class is a missed collision, and a false positive is one line to bless."""
    out = set()
    for m in re.finditer(r'className=(?:"([^"]*)"|\{([^}]*)\})', src, re.S):
        if m.group(1):
            out.update(w for w in m.group(1).split() if w)
        else:
            for lit in re.findall(r"['\"]([^'\"]*)['\"]", m.group(2) or ""):
                out.update(w for w in lit.replace("+", " ").split()
                           if re.fullmatch(r"[a-z][\w-]*", w))
    return out


print("1. every app declares a CSS prefix, and no two share one")
reg = io.open(os.path.join(UI, "appRegistry.jsx"), encoding="utf-8").read()
apps = re.findall(r"id: '(\w+)'.*?Component: (\w+), css: '([\w-]+)'", reg)
declared = {a[0]: a[2] for a in apps}
ids = re.findall(r"\{ id: '(\w+)'", reg)
check("every app in APPS has a css prefix", sorted(declared) == sorted(ids),
      "missing: %s" % sorted(set(ids) - set(declared)))
dupe = [p for p, n in collections.Counter(declared.values()).items() if n > 1]
check("prefixes are unique", not dupe, dupe)
check("no prefix is a SHARED name", not (set(declared.values()) & SHARED))

print("\n2. mapping every class to its owner")
owners = {}
for p in sorted(glob.glob(os.path.join(UI, "apps", "*.jsx"))):
    base = os.path.basename(p)[:-4]
    # panel.jsx IS the shared furniture module (Body, Row, usePoll), so it is an
    # owner named `shared` rather than an app. Excluding it made `row` look unused
    # by anyone and tripped the stale-SHARED check — the gate was right, the input
    # was wrong.
    key = ("shared:" + base.lower()) if base.lower() in SHARED_MODULES \
        else "app:" + base.lower()
    owners[key] = classes_in(io.open(p, encoding="utf-8").read())
shell = set()
for p in [os.path.join(UI, "main.jsx"), os.path.join(UI, "Chat.jsx")] + \
         sorted(glob.glob(os.path.join(UI, "room", "*.jsx"))):
    shell |= classes_in(io.open(p, encoding="utf-8").read())
owners["shell"] = shell
used_by = collections.defaultdict(set)
for o, cs in owners.items():
    for c in cs:
        used_by[c].add(o)
print("   %d owners, %d distinct classes" % (len(owners), len(used_by)))

print("\n3. NO CLASS HAS TWO OWNERS unless it is shared furniture")
collisions = sorted(c for c, o in used_by.items()
                    if len(o) > 1 and c not in SHARED and c not in GRANDFATHERED
                    and not family_of(c))
for c in collisions:
    print("       %s used by %s" % (c, sorted(used_by[c])))
check("no unblessed cross-owner class", not collisions, collisions)

print("\n4. an app's own classes carry its own prefix")
# THE FORWARD-LOOKING HALF. Bare legacy names are grandfathered by §5; what this
# refuses is a NEW hyphenated family homed under someone else's prefix — `mus-track`
# inside Files, which is how two apps end up sharing a stylesheet section.
# A SHARED FAMILY is exempt here (any window may mount the shared renderer or its
# status bar); §4b below is what keeps those families from sprawling.
famililes_bad = []
for o, cs in owners.items():
    if not o.startswith("app:"):
        continue
    mine = declared.get(o[4:], None)
    for c in cs:
        if "-" not in c or c in SHARED or c in GRANDFATHERED or family_of(c):
            continue
        head = c.split("-", 1)[0]
        if head in declared.values() and head != mine:
            famililes_bad.append((o, c, head))
check("no app uses another app's prefix family", not famililes_bad, famililes_bad)

print("\n4b. a shared family grows only in its one renderer module")
# The exemption above is safe ONLY while each family has a single renderer: a NEW
# st- name minted inside some app would be a second stylesheet author, which is
# the original .led ambiguity wearing a prefix. Apps may USE what the renderer
# and the family's home app define; they may not coin names.
# RATCHET, same terms as GRANDFATHERED: the shell's taskbar "looked up" chip
# coined rsc-chip (2026-08-0x) before the family rule existed. Shrink only.
FAMILY_GRANDFATHER = {("shell", "rsc-chip")}
grown = []
for fam, mod in SHARED_FAMILIES.items():
    home = next((aid for aid, pref in declared.items() if pref == fam), None)
    allowed = owners.get(mod, set()) | (owners.get("app:" + home, set()) if home else set())
    for o, cs in owners.items():
        if o == mod or (home and o == "app:" + home):
            continue
        for c in cs:
            if family_of(c) == fam and c not in allowed \
                    and (o, c) not in FAMILY_GRANDFATHER:
                grown.append((o, c))
check("no app coins a new name in a shared family", not grown, grown)

print("\n5. the grandfather table is a ratchet, not a permission slip")
check("it has not grown", len(GRANDFATHERED) <= GRANDFATHERED_MAX,
      "%d > %d" % (len(GRANDFATHERED), GRANDFATHERED_MAX))
stale = sorted(c for c in GRANDFATHERED if len(used_by.get(c, ())) < 2)
check("no stale entries — every excuse is still load-bearing", not stale, stale)
unused_shared = sorted(c for c in SHARED if c not in used_by)
check("SHARED lists nothing that nobody uses", not unused_shared, unused_shared)

print("\n6. the collision that started this cannot come back")
# `.led` is the shell's status dot. If any app ever claims it again, this fails.
led_owners = sorted(used_by.get("led", ()))
check("`led` belongs to the shell alone", led_owners in ([], ["shell"]), led_owners)
css = re.sub(r"/\*.*?\*/", "", io.open(os.path.join(UI, "room.css"), encoding="utf-8").read(),
             flags=re.S)
check("room.css still defines `.led` as the 8px dot",
      re.search(r"\.led\s*\{[^}]*width:\s*8px", css) is not None)
check("the ledger's rows are NOT `.led`", ".lgr" in css and "lgr" == declared.get("ledger"))

print("\nG-ROOM-CSS: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_room_css.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_room_css", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
