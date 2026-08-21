"""G-LEDGER — the standing list keeps what it is told, and never loses a row.

The ledger is the only place the plan, the parked items and the noticed-and-not-touched
are written down. It is WRITABLE FROM THE ROOM, which puts it in the same category as the
memory registry rather than the same category as a panel: a write path that can lose a row
is a write path that will.

So the asserted invariants are the store's, not the UI's:

  1. THERE IS NO DELETE. `drop()` tombstones — status becomes `dropped` and the row is still
     there, still readable, still restorable. The module exposes no function that shortens
     the entries list, and this gate greps for one, because the room's "remove" button is
     exactly the affordance that invites one to be added later.
  2. KIND, STATUS and OWNER are committed finite tables. An unknown value is REFUSED, not
     coerced to a default — the free-text-status failure is `done`/`Done`/`complete` all
     meaning one thing and none of them countable.
  3. A row's `created` never moves. Edit it ten times; it is still the day it was raised.
  4. A missing or corrupt file is an EMPTY ledger, never an exception. The room must render
     on a fresh clone, and a panel that throws takes its neighbours down with it — the
     lesson from /v1/maintenance/stats 404ing and blanking the whole memory pane.
  5. The write is ATOMIC. A torn ledger is worse than a stale one.
  6. Gate health reports AGE alongside the verdict. A green with no timestamp is precisely
     the lie G-PF-PERSONA was telling for weeks.

Offline. No GPU, no daemon.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SB = os.path.join(tempfile.gettempdir(), "_g_ledger")
shutil.rmtree(SB, ignore_errors=True)
os.makedirs(SB)
os.environ["SP_LEDGER_FILE"] = os.path.join(SB, "ledger.json")

from harness.control import ledger as L  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s %s" % (name, detail))


print("1. an absent ledger is empty, not an exception")
check("no file -> no entries", L.all_entries() == [])
check("no file -> counts still answer", L.counts()["total"] == 0)

print("\n2. finite tables refuse rather than coerce")
for bad in ({"kind": "wishlist", "title": "x"},
            {"kind": "plan", "status": "finished", "title": "x"},
            {"kind": "plan", "owner": "grok", "title": "x"},
            {"kind": "plan", "title": "   "}):
    try:
        L.add(**bad)
        check("refused %r" % sorted(bad.items())[:1], False, "it was ACCEPTED")
    except ValueError:
        check("refused %s" % (bad.get("kind") if bad.get("kind") != "plan"
                              else bad.get("status") or bad.get("owner") or "empty title"), True)
check("nothing was written by the refusals", L.counts()["total"] == 0)

print("\n3. add / edit / created never moves")
a = L.add(kind="noticed", title="a thing", body="why", owner="sam", refs=["x.py"])
b = L.add(kind="plan", title="another", owner="claude")
check("two rows", L.counts()["total"] == 2)
check("owner is kept as given", a["owner"] == "sam" and b["owner"] == "claude")
born = a["created"]
e1 = L.edit(a["id"], title="a renamed thing", status="doing")
check("edit applied", e1 and e1["title"] == "a renamed thing" and e1["status"] == "doing")
check("created never moves", e1["created"] == born)
check("edit of an unknown id is None, not a new row",
      L.edit("nope-not-an-id", title="x") is None and L.counts()["total"] == 2)
try:
    L.edit(a["id"], status="finished")
    check("edit refuses an unknown status", False, "it was ACCEPTED")
except ValueError:
    check("edit refuses an unknown status", True)

print("\n4. REMOVE IS A TOMBSTONE — there is no delete")
d = L.drop(a["id"])
check("drop returns the row", d is not None and d["status"] == "dropped")
check("the row is STILL THERE", any(r["id"] == a["id"] for r in L.all_entries()))
check("...and its text is intact", next(r for r in L.all_entries() if r["id"] == a["id"])["body"] == "why")
check("hidden by default from the live view",
      not any(r["id"] == a["id"] for r in L.all_entries(include_dropped=False)))
check("restorable", L.edit(a["id"], status="open")["status"] == "open")
L.drop(a["id"])
raw = io.open(L.path(), encoding="utf-8").read()
check("the dropped row is on disk, not merely hidden by the reader", a["id"] in raw)
src = io.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "harness", "control", "ledger.py"), encoding="utf-8").read()
check("the module offers no delete/remove/purge function",
      not any(("def %s(" % n) in src for n in ("delete", "remove", "purge", "clear")))
check("nothing in the module shortens the entries list",
      ".pop(" not in src and ".remove(" not in src and "del d[" not in src)

print("\n5. a corrupt file degrades to empty, it does not raise")
io.open(L.path(), "w", encoding="utf-8").write("{ this is not json")
check("garbage -> empty", L.all_entries() == [])
io.open(L.path(), "w", encoding="utf-8").write('{"version":1,"entries":"not a list"}')
check("wrong shape -> empty", L.all_entries() == [])
io.open(L.path(), "w", encoding="utf-8").write(
    '{"version":1,"entries":[{"kind":"nope","title":"bad"},{"kind":"plan","title":"good"}]}')
rows = L.all_entries()
check("one malformed row is skipped, the good one survives",
      len(rows) == 1 and rows[0]["title"] == "good")

print("\n6. the write is atomic and leaves no temp behind")
L.add(kind="idea", title="atomic?")
check("no .tmp left in place", not os.path.exists(L.path() + ".tmp"))
json.loads(io.open(L.path(), encoding="utf-8").read())     # raises if torn
check("file parses after a write", True)

print("\n7. gate health carries AGE, not just a verdict")
h = L.gate_health()
check("receipts is a list", isinstance(h.get("receipts"), list))
check("every receipt reports its age", all("age_h" in r for r in h["receipts"]))
check("every receipt reports staleness", all("stale" in r for r in h["receipts"]))
check("the payload says out loud that it is not live",
      "not a live verdict" in (h.get("note") or ""))
check("health runs NOTHING — no subprocess in the module",
      "subprocess" not in src and "os.system" not in src)

shutil.rmtree(SB, ignore_errors=True)
print("\nG-LEDGER: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_ledger.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_ledger", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
