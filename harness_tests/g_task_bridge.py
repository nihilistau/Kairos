#!/usr/bin/env python
"""G-TASK-BRIDGE — the board and the queue are joined, and the RULING survives the join.

There were two task systems in this repo and they had never met: `notes.jsonl` (both authors
write, she has tools, the console renders it, and it can DO nothing) and `_task_state/`
(bounded, resumable, receipted, drained by the day boundary — and `post_task()` had no caller
anywhere in the tree, so the drain spent its life draining an empty queue).

`harness/skills/task_bridge.py` is the join. This gate holds the thing most likely to be lost
in a join: **ownership**. A note carries `speaker`; a task is ruled on by `owner`; if promotion
dropped that, connecting the two systems would have silently handed her closing rights over
everything he ever asked for.

    FORALL promotions:      his note -> operator-owned task, hers -> self-owned
    FORALL promotions:      idempotent, and the note is NOT consumed
    FORALL closes:          she may not close his task, AFTER promotion as before
    FORALL writebacks:      the note's original text survives; the result is appended
    FORALL terminals:       the state file, the row, and the whole step history remain
    FORALL reopens:         the operator alone
    FORALL knob-off:        promote and writeback are no-ops — but the world slot still READS

FULLY SANDBOXED, and it refuses to run otherwise: it writes notes and task states, so it points
SP_RECALL_REGISTRY and SP_TASK_ROOT at a temp dir and asserts both landed there before touching
anything. A gate that can write to his real board is not a gate.

OFFLINE. No GPU, no daemon.
"""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

SB = tempfile.mkdtemp(prefix="g-task-bridge-")
os.environ["SP_RECALL_REGISTRY"] = os.path.join(SB, "registry.jsonl")
os.environ["SP_TASK_ROOT"] = os.path.join(SB, "_task_state")
os.environ["SP_TASK_BRIDGE"] = "1"
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"

from harness.control import task_loop as TL  # noqa: E402
from harness.skills import notes as N  # noqa: E402
from harness.skills import task_bridge as B  # noqa: E402

# THE GUARD, before a single write. If either store resolved outside the sandbox this gate
# would edit his real board, and a gate that does that has done more harm than the bug.
if SB not in N._store() or SB not in TL._task_root():
    print("REFUSING TO RUN: stores are not sandboxed\n  notes: %s\n  tasks: %s"
          % (N._store(), TL._task_root()))
    shutil.rmtree(SB, ignore_errors=True)
    sys.exit(2)

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


print("1. the board sees what is open")
N.set_author("user")
his = N.add("fix the recall filter", body="it drops tombstones", category="task")
N.set_author("self")
hers = N.add("tidy my own duplicate rows", category="task")
N.add("Tuffy likes the warm spot", category="note")
check("only task-category notes count as open work", len(B.open_task_notes()) == 2,
      [r["title"] for r in B.open_task_notes()])
check("the world slot renders them", "recall filter" in B.summary(), B.summary())

print("\n2. promotion carries the owner across")
posted = B.promote()
check("both promoted", len(posted) == 2, posted)
owners = {p["title"][:12]: p["owner"] for p in posted}
check("HIS note becomes an OPERATOR-owned task", owners.get("fix the reca") == "operator", owners)
check("HERS becomes a SELF-owned task", owners.get("tidy my own ") == "self", owners)
check("promotion is idempotent", B.promote() == [])
check("the note carries the link and the status",
      bool(N.get(his["id"]).get("task_id")) and N.get(his["id"])["task_status"] == "pending")
check("the note is NOT consumed", N.get(his["id"])["title"] == his["title"])
check("an unknown speaker defaults to OPERATOR — less authority for her, never more",
      B.owner_of({"speaker": "someone-else"}) == "operator")
check("a missing speaker likewise", B.owner_of({}) == "operator")

print("\n3. the ruling survives the join")
his_tid = N.get(his["id"])["task_id"]
hers_tid = N.get(hers["id"])["task_id"]
check("SHE MAY NOT CLOSE HIS TASK, after promotion exactly as before",
      TL.close_task(his_tid, actor="self").status == "pending")
check("she may close her own", TL.close_task(hers_tid, actor="self").status == "closed")
check("he may close his", TL.close_task(his_tid, actor="operator").status == "closed")

print("\n4. writeback reports; it never decides")
wrote = B.writeback()
check("both notes got their verdict back", len(wrote) == 2, wrote)
check("the note is ticked done", N.get(his["id"])["done"] is True)
body = N.get(his["id"])["body"]
check("the ORIGINAL text survives", "it drops tombstones" in body, body)
check("the task verdict is appended, with its id", ("[task %s: closed]" % his_tid) in body, body)
check("nothing is left open", B.open_task_notes() == [])
check("...so the world slot goes quiet", B.summary() == "", B.summary())

print("\n5. nothing is deleted on either side")
check("the state file remains (tombstone, not delete)",
      os.path.exists(os.path.join(TL._task_root(), his_tid + ".json")))
check("list_tasks still returns it", his_tid in [t.task_id for t in TL.list_tasks()])
check("its step history still loads", TL.TaskState.load(his_tid) is not None)
check("the note row is still on the board", N.get(his["id"]) is not None)

print("\n6. reopening is his alone")
check("she cannot reopen", TL.reopen_task(his_tid, actor="self").status == "closed")
check("he can, and it lands in pending",
      TL.reopen_task(his_tid, actor="operator").status == "pending")

print("\n7. the knob")
os.environ["SP_TASK_BRIDGE"] = "0"
check("off: promote is a no-op", B.promote() == [])
check("off: writeback is a no-op", B.writeback() == [])
check("off: reading the board still works — the world slot must not need the knob",
      isinstance(B.open_task_notes(), list))
os.environ["SP_TASK_BRIDGE"] = "1"

print("\n8. a forward-compatible state file")
# The day `owner` was added, every task file on disk predated it. A load that raised would
# have emptied the queue; a load that defaulted to "self" would have handed her his tasks.
p = os.path.join(TL._task_root(), "legacyaaaa01.json")
with open(p, "w", encoding="utf-8") as f:
    json.dump({"task_id": "legacyaaaa01", "goal": "an old task", "status": "pending",
               "steps": [], "result": "", "created": 1.0, "updated": 1.0,
               "a_field_from_the_future": True}, f)
old = TL.TaskState.load("legacyaaaa01")
check("a state file with no `owner` still loads", old is not None)
check("...and defaults to OPERATOR, not self", old and old.owner == "operator", old and old.owner)
check("an unknown future field does not break the load", old is not None)
check("she cannot close a legacy task",
      TL.close_task("legacyaaaa01", actor="self").status == "pending")

print("\nG-TASK-BRIDGE: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_task_bridge.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_task_bridge", "pass": PASS, "fail": FAIL,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
shutil.rmtree(SB, ignore_errors=True)
sys.exit(1 if FAIL else 0)
