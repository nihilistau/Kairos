"""G-PEOPLE — she knows the people, pets and places in their lives; more than one person can
talk to her; what one of them tells her in confidence stays with them. OFFLINE.
(harness/people.py, harness/skills/people_tools.py, lifecycle._stamp_people, design §2, §7a)

  1. the store: add, update, retire, confirm; names, aliases, kinds; nothing removed; a
     malformed line skipped; the current row is the last version
  2. users: handles user1, user2…; one active; only a live user can be active; the active
     user cannot be retired
  3. the launch: the home's active user wins over the profile's [user]; a home with no users
     is seeded from [user] once, as user1
  4. the stamp: a fact he tells her carries `said_by` (who) and `about` (whom), through
     remember(); old-shape rows are untouched
  5. PRIVATE STAYS WITH ITS TELLER (ruling 9.1): another user's private-secret row is absent
     from live_rows, ranked recall, the person model and the room's Memory panel; his own is
     not; a row with no said_by is never hidden by this
  6. her tools: meet() only PROPOSES (and writes nothing off the record); note_about() goes
     through remember() and links the person; who_is()
  7. the routes and the flow's "you" steps

Run: python harness_tests/g_people.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_people")
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"

from harness import people as PP  # noqa: E402


def _err(f):
    try:
        f()
        return ""
    except PP.PeopleError as e:
        return str(e) or "refused"


def lines():
    with open(os.environ["SP_PEOPLE"], encoding="utf-8") as f:
        return f.read().splitlines()


print("1. the store")
t = PP.add("Tuffy", kind="pet", relation="his cat")
s = PP.add("Theo", relation="his brother", pronouns="he/him/his", aliases=["Teddy"])
c = PP.add("the cabin", kind="place", relation="where they go in summer")
check("ids are given in order", [t["id"], s["id"], c["id"]] == ["p1", "p2", "p3"])
check("a duplicate of the same kind is refused", "already" in _err(lambda: PP.add("tuffy", kind="pet")))
check("an unknown kind is refused", bool(_err(lambda: PP.add("x", kind="robot"))))
PP.update(s["id"], relation="his older brother")
check("the current row is the last version", PP.get(s["id"])["relation"] == "his older brother")
check("find by alias, case-insensitive", PP.find("teddy")["id"] == s["id"])
n0 = len(lines())
PP.retire(c["id"], "they sold it")
check("retired: kept, marked, with the reason", PP.get(c["id"])["status"] == "retired"
      and "sold it" in PP.get(c["id"])["notes"] and len(lines()) == n0 + 1)
check("…and gone from everyone() unless asked", c["id"] not in [r["id"] for r in PP.everyone()]
      and c["id"] in [r["id"] for r in PP.everyone(include_retired=True)])
with open(os.environ["SP_PEOPLE"], "a", encoding="utf-8") as f:
    f.write("{not json\n")
check("a malformed line is skipped, never fatal", PP.get(t["id"])["names"] == ["Tuffy"])

print("\n2. users")
k = PP.add_user("Sam", "he/him/his")
r2 = PP.add_user("Robin", "she/her/her")
check("handles user1, user2", (k["handle"], r2["handle"]) == ("user1", "user2"))
PP.set_active(k["id"])
check("one active user", PP.active()["id"] == k["id"])
check("a pet cannot be the user", bool(_err(lambda: PP.set_active(t["id"]))))
check("the active user cannot be retired", "switch user first" in _err(lambda: PP.retire(k["id"])))

print("\n3. the launch")
import serve  # noqa: E402
home = os.path.join(SB, "companions", "ivy")
from harness import home as H  # noqa: E402
H.COMPANIONS_DIR = os.path.join(SB, "companions")
H.create("ivy", "Ivy")
c0 = serve.load_profile("companion")
c0["paths"] = {k_: v for k_, v in c0["paths"].items() if k_ != "registry"}
c0["paths"]["companions_dir"] = os.path.join(SB, "companions")
c0["_companion"] = "ivy"
c0["user"] = {"name": "Sam", "pronouns": "he/him/his"}
_env_before = dict(os.environ)
serve.seed_people_home(c0)
os.environ.clear()
os.environ.update(_env_before)
pp = H.resolve(home)["people"]
check("a home with no users is seeded from [user] as user1",
      serve.active_user(pp) and serve.active_user(pp)["names"][0] == "Sam")
saved = os.environ.get("SP_PEOPLE")
os.environ["SP_PEOPLE"] = pp
rob = PP.add_user("Robin", "she/her/her")
PP.set_active(rob["id"])
os.environ["SP_PEOPLE"] = saved
_env_before = dict(os.environ)              # build_env strips inherited SP_* (the one door)
e = serve.build_env(c0)
os.environ.clear()
os.environ.update(_env_before)
check("the home's active user wins over the profile's [user]",
      e.get("SP_USER_NAME") == "Robin" and e.get("SP_USER_PRONOUNS") == "she/her/her" and e.get("SP_USER_ID") == rob["id"],
      (e.get("SP_USER_NAME"), e.get("SP_USER_ID")))
serve.seed_people_home(c0)
os.environ["SP_PEOPLE"] = pp
check("seeding is once: a second launch adds no one", len(PP.users()) == 2)
os.environ["SP_PEOPLE"] = saved

print("\n4. the stamp")
os.environ["SP_USER_ID"] = k["id"]
from harness.skills import memory as M  # noqa: E402
from harness.skills import lifecycle as lc  # noqa: E402
M.remember("Tuffy hates the vacuum cleaner")
row = [r for r in M.all_rows() if "vacuum" in r.get("text", "")][-1]
check("said_by is the active user", row.get("said_by") == k["id"], row.get("said_by"))
check("about names the cat", row.get("about") == [t["id"]], row.get("about"))
M.remember("I prefer tea in the morning")
row = [r for r in M.all_rows() if "tea in the morning" in r.get("text", "")][-1]
check("a fact about no one carries no about", "about" not in row)

print("\n5. private stays with its teller")
M.remember("My PIN is 4417, keep it secret")
os.environ["SP_USER_ID"] = r2["id"]
M.remember("My bank password is swordfish88")
sec = [r for r in M.all_rows() if r.get("mem_class") == "private-secret"]
check("both secrets were classified private and stamped", len(sec) >= 2 and all(r.get("said_by") for r in sec),
      [(r.get("text")[:30], r.get("mem_class"), r.get("said_by")) for r in M.all_rows()][-3:])
os.environ["SP_USER_ID"] = k["id"]
live = [r.get("text") for r in M.live_rows()]
check("talking to Sam: his secret is there, Robin's is not",
      any("4417" in x for x in live) and not any("swordfish88" in x for x in live))
ranked = [r.get("text") for _s, r in M.search_memories_ranked_rows("bank password swordfish88", k=10)] \
    if hasattr(M, "search_memories_ranked_rows") else []
check("ranked recall does not find Robin's secret either", not any("swordfish88" in x for x in ranked), ranked[:3])
os.environ["SP_USER_ID"] = r2["id"]
check("talking to Robin: hers is there, his is not",
      any("swordfish88" in x for x in [r.get("text") for r in M.live_rows()])
      and not any("4417" in x for x in [r.get("text") for r in M.live_rows()]))
old = {"text": "an old secret", "mem_class": "private-secret"}
check("a row with no said_by is never hidden by this", not lc.other_users_secret(old))
from harness.server import panels  # noqa: E402
mem = panels._memory_json()
check("the room's Memory panel hides the other user's secret",
      not any("4417" in f.get("text", "") for f in mem.get("facts", [])), mem.get("error"))
os.environ["SP_USER_ID"] = k["id"]

print("\n6. her tools")
from harness.skills import people_tools as PT  # noqa: E402
out = PT.meet("Mara", "person", "his best friend")
m = PP.find("Mara")
check("meet() only proposes", m and m["status"] == "proposed" and m["proposed_by"] == "her" and "waits" in out, out)
check("…and a proposal links nothing yet", m["id"] not in PP.mentioned("Mara called today"))
check("meet() on someone known says so", "already know" in PT.meet("Tuffy", "pet"))
from harness.control import anon  # noqa: E402
anon.enter()
try:
    held = PT.meet("Zed", "person")
finally:
    anon.leave()
check("off the record, meet() writes nothing", held == anon.WHY and PP.find("Zed") is None, held)
r = PT.note_about("Theo", "loves sailing")
row = [x for x in M.all_rows() if "sailing" in x.get("text", "")][-1]
check("note_about() remembers through remember(), linked to him", row.get("about") == [s["id"]] and "Theo" in row["text"], (r, row.get("about")))
check("note_about() on a stranger says so", "do not know" in PT.note_about("Nobody", "x"))
check("who_is()", "his older brother" in PT.who_is("Theo") and "pet" in PT.who_is("tuffy"))

print("\n7. the routes and the flow")
from harness.server import people_routes as PR  # noqa: E402
code, st = PR.get_people()
check("GET lists users first and flags proposals", code == 200 and st["people"][0]["user"]
      and any(p["id"] == m["id"] for p in st["proposed"]))
check("confirm", PR.post_people({"op": "confirm", "id": m["id"]})[0] == 200 and PP.get(m["id"])["status"] == "live")
z = PP.add("Zara", status="proposed", proposed_by="her")
PR.post_people({"op": "reject", "id": z["id"], "why": "not a real person"})
check("reject keeps the row, retired with the reason", PP.get(z["id"])["status"] == "retired"
      and "not confirmed" in PP.get(z["id"])["notes"])
code, sw = PR.post_people({"op": "switch", "id": r2["id"]})
check("switch records the choice and says it needs a restart", code == 200 and sw["restart"] and "restart" in sw["note"])
check("an unknown op is refused", PR.post_people({"op": "delete", "id": t["id"]})[0] == 400)
from harness.personality import character as C  # noqa: E402
check("the flow parses 'name — who they are', guessing pets and places",
      C.people_lines("Tuffy — my cat\nthe cabin: where we go\nSam, my brother") ==
      [("Tuffy", "pet", "my cat"), ("the cabin", "place", "where we go"), ("Sam", "person", "my brother")])
rc = C.create({"name": "Juno", "you": {"name": "Ray", "pronouns": "he/him/his"},
               "your_people": "Pip — my dog\nLou — my sister"}, "juno")
os.environ["SP_PEOPLE"] = H.resolve(rc["home"])["people"]
check("create(): you are her user1, active, and she knows your people",
      rc["user"] == "user1" and PP.active()["names"][0] == "Ray"
      and {"Pip", "Lou"} <= {p["names"][0] for p in PP.everyone()} and PP.find("Pip")["kind"] == "pet", rc)

finish("G-PEOPLE")
