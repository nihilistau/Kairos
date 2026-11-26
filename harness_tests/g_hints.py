"""G-HINTS — first-run hints show on a clean setup only, go away when you DO the thing, and
one switch turns them off. OFFLINE. (harness/hints.py, config/hints.json, room/Hints.jsx)

  1. the catalogue is well-formed: ids unique, every hint has a title and a body, every
     `open` and `open:<window>` names a real window in the room's registry
  2. a clean home (empty registry) shows them, in order; a home that knows you does not
  3. opening a window marks its hint done; dismiss and done take one hint away
  4. off hides them all; on / reset bring them back even on a home that is not new
  5. her real home is not a clean setup (she would never be lectured)
  6. the room mounts the card and reports every window it opens

Run: python harness_tests/g_hints.py
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from _gate import check, finish, real_store, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_hints")

from harness import hints as HN  # noqa: E402


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


print("1. the catalogue")
cat = HN.catalogue()
ids = [h["id"] for h in cat["hints"]]
check("ids are unique", len(ids) == len(set(ids)))
check("every hint has a title and a body", all(h.get("title") and h.get("body") for h in cat["hints"]))
reg = read("ui", "src", "appRegistry.jsx")
apps = set(re.findall(r"\{ id: '([a-z]+)'", reg))
named = {h["open"] for h in cat["hints"] if h.get("open")} | \
        {h["done_when"][5:] for h in cat["hints"] if h.get("done_when", "").startswith("open:")}
check("every window a hint names is a real window", named <= apps, sorted(named - apps))
check("…and every hint can end (a window to open, or manual)",
      all(h.get("done_when", "").startswith("open:") or h.get("done_when") == "manual" for h in cat["hints"]))
check("the hints cover clothing, the journal, memory and backups",
      {"wardrobe", "journal", "memory", "companion"} <= set(ids))

print("\n2. clean homes only")
v = HN.view()
check("an empty registry is a clean setup: hints show", v["active"] and v["pending"][0]["id"] == ids[0], v["why"])
with open(os.environ["SP_RECALL_REGISTRY"], "w", encoding="utf-8") as f:
    f.write("{}\n" * int(cat["clean_below_rows"]))
check("a home that knows you shows none", not HN.view()["active"] and "already knows" in HN.view()["why"])
open(os.environ["SP_RECALL_REGISTRY"], "w").close()

print("\n3. done when done")
v = HN.op({"op": "opened", "window": "wardrobe"})
check("opening Wardrobe marks the clothing hint done", "wardrobe" in v["state"]["done"]
      and "wardrobe" not in [h["id"] for h in v["pending"]])
v = HN.op({"op": "dismiss", "id": "welcome"})
check("dismiss takes one away", v["pending"][0]["id"] != "welcome")


def _refused(f):
    try:
        f()
        return False
    except ValueError:
        return True


check("an unknown hint is refused", _refused(lambda: HN.op({"op": "done", "id": "nope"})))
check("an unknown op is refused", _refused(lambda: HN.op({"op": "explode"})))
check("progress is stored in the home's hints store", os.path.isfile(os.environ["SP_HINTS_STATE"]))

print("\n4. off and back on")
v = HN.op({"op": "off"})
check("off hides them", not v["active"] and v["why"] == "off")
with open(os.environ["SP_RECALL_REGISTRY"], "w", encoding="utf-8") as f:
    f.write("{}\n" * 100)
v = HN.op({"op": "reset"})
check("reset brings them all back, even on a home that is not new", v["active"] and len(v["pending"]) == len(ids))

print("\n5. her home")
her = real_store("SP_RECALL_REGISTRY") or os.path.join(ROOT, "var", "memory", "registry.jsonl")
if os.path.isfile(her) and os.path.isfile(os.path.join(ROOT, "companions", "kairos", "companion.toml")):
    with open(her, "rb") as f:
        n = sum(1 for _ in f)
    check("her registry is far past a clean setup", n >= int(cat["clean_below_rows"]), n)
else:
    print("  omitted  §5: her home is not in this tree (the public export)")

print("\n6. the room")
main = read("ui", "src", "main.jsx")
hn = read("ui", "src", "room", "Hints.jsx")
check("the shell mounts the hint card", "<Hints />" in main)
check("every opened window is reported", "op: 'opened'" in hn and "wm.subscribe" in hn)
check("the card has Show me, Got it and No more hints", all(w in hn for w in ("Show me", "Got it", "No more hints")))

finish("G-HINTS")
