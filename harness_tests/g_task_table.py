#!/usr/bin/env python
"""G-TASK-TABLE — who may do what to a task, walked cell by cell.

`harness/control/task_table.step()` is pure and total, so its domain booleanizes exactly:

    status(6) x event(6) x actor(3) x owner(2) = 216 cells

all through the REAL function. Committed: `fixtures/tasks/task-table.json`. A diff in that
file is an unreviewed policy change and this gate is the tripwire — the same discipline as
`ladder-table.json` and `verdict-table.json`.

THE THEOREMS, over every cell and not a sample:

    FORALL cells:                 an outcome exists, in STATES, with a non-empty reason —
                                  nothing is silently dropped
    FORALL refusals:              the status is UNCHANGED, and the reason says so out loud
    FORALL non-refusals:          the status actually MOVED — no no-op that reads as success
    FORALL close -> closed:       may_close(actor, owner) — she may close what she set,
                                  never what he asked for
    FORALL reopen:                only the operator, and never from `done`
    FORALL cells:                 no outcome is absence — terminal is a TOMBSTONE, not a
                                  deletion; the row and its whole step history survive
    FORALL terminal x report:     refused — a finished task cannot be re-finished

Run:  python harness_tests/g_task_table.py            (gate)
      python harness_tests/g_task_table.py --freeze   (commit the artifact)

OFFLINE. No GPU, no daemon, no store.
"""
import itertools
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ.setdefault("SP_DAEMON_URL", "http://127.0.0.1:9")

from harness.control import task_table as T  # noqa: E402

TABLE_PATH = os.path.join(HERE, "fixtures", "tasks", "task-table.json")

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


def enumerate_table():
    table = {}
    for status, event, actor, owner in itertools.product(
            T.STATES, T.EVENTS, T.ACTORS, T.OWNERS):
        new, reason = T.step(status, event, actor, owner)
        key = "%s|%s|by=%s|owner=%s" % (status, event, actor, owner)
        table[key] = {"status": new, "refused": T.is_refusal(reason), "reason": reason}
    return table


CELLS = enumerate_table()

if "--freeze" in sys.argv:
    os.makedirs(os.path.dirname(TABLE_PATH), exist_ok=True)
    with open(TABLE_PATH, "w", encoding="utf-8") as f:
        json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "states": list(T.STATES), "events": list(T.EVENTS),
                   "actors": list(T.ACTORS), "owners": list(T.OWNERS),
                   "cells": CELLS}, f, indent=2, sort_keys=True)
    print("froze %d cells -> %s" % (len(CELLS), TABLE_PATH))
    sys.exit(0)

print("1. the board is total")
check("216 cells (6 x 6 x 3 x 2)", len(CELLS) == 216, len(CELLS))
check("every outcome is a real status",
      all(c["status"] in T.STATES for c in CELLS.values()))
check("every cell carries a reason", all(c["reason"] for c in CELLS.values()))
check("no outcome is absence — terminal is a tombstone, never a deletion",
      all(c["status"] is not None for c in CELLS.values()))

print("\n2. refusals are explicit and inert")
refused = {k: v for k, v in CELLS.items() if v["refused"]}
moved = {k: v for k, v in CELLS.items() if not v["refused"]}
check("a refusal leaves the status UNCHANGED",
      all(v["status"] == k.split("|")[0] for k, v in refused.items()),
      [k for k, v in refused.items() if v["status"] != k.split("|")[0]][:3])
check("a non-refusal actually MOVES the task (no no-op that reads as success)",
      all(v["status"] != k.split("|")[0] for k, v in moved.items()),
      [k for k, v in moved.items() if v["status"] == k.split("|")[0]][:3])
check("both outcomes are reachable (the test is not vacuous)", refused and moved,
      (len(refused), len(moved)))

print("\n3. only the owner or the operator may close")
closes = {k: v for k, v in CELLS.items() if k.split("|")[1] == "close"}
check("every close that SUCCEEDED was permitted by may_close",
      all(T.may_close(k.split("|")[2][3:], k.split("|")[3][6:])
          for k, v in closes.items() if not v["refused"]))
check("every close that was permitted from a live state SUCCEEDED",
      all(v["status"] == T.CLOSED
          for k, v in closes.items()
          if T.may_close(k.split("|")[2][3:], k.split("|")[3][6:])
          and k.split("|")[0] not in T.TERMINAL))
check("SHE MAY NOT CLOSE WHAT HE ASKED FOR",
      all(CELLS["%s|close|by=self|owner=operator" % s]["status"] == s for s in T.STATES))
check("...but she may close what she set herself",
      all(CELLS["%s|close|by=self|owner=self" % s]["status"] == T.CLOSED
          for s in T.STATES if s not in T.TERMINAL))
check("the machinery may close nothing at all",
      all(v["status"] == k.split("|")[0]
          for k, v in closes.items() if k.split("|")[2] == "by=system"))

print("\n4. a closed task never reopens itself")
reopens = {k: v for k, v in CELLS.items() if k.split("|")[1] == "reopen"}
check("no actor but the operator ever reopens anything",
      all(v["status"] == k.split("|")[0]
          for k, v in reopens.items() if k.split("|")[2] != "by=operator"))
check("nothing reopens a DONE task — not even him",
      all(v["status"] == T.DONE for k, v in reopens.items() if k.split("|")[0] == T.DONE))
check("he MAY reopen failed / exhausted / closed",
      all(CELLS["%s|reopen|by=operator|owner=%s" % (s, o)]["status"] == T.PENDING
          for s in (T.FAILED, T.EXHAUSTED, T.CLOSED) for o in T.OWNERS))
check("a reopened task lands in PENDING, at the back of the queue",
      all(v["status"] == T.PENDING
          for k, v in reopens.items() if not v["refused"]))

print("\n5. terminal means terminal")
absorbing = [(s, ev, a, o) for s in T.TERMINAL
             for ev in ("start", "succeed", "fail", "exhaust")
             for a in T.ACTORS for o in T.OWNERS
             if CELLS["%s|%s|by=%s|owner=%s" % (s, ev, a, o)]["status"] != s]
check("every terminal state is absorbing under every report event, for every actor",
      not absorbing, absorbing[:3])
check("only PENDING may start",
      all(CELLS["%s|start|by=self|owner=self" % s]["status"] == s
          for s in T.STATES if s != T.PENDING))
check("a report against a non-running task is refused",
      all(CELLS["%s|succeed|by=self|owner=self" % s]["refused"]
          for s in T.STATES if s != T.RUNNING))

print("\n6. the committed board still matches")
if not os.path.exists(TABLE_PATH):
    check("fixtures/tasks/task-table.json exists (run --freeze once)", False, TABLE_PATH)
else:
    with open(TABLE_PATH, encoding="utf-8") as f:
        frozen = json.load(f)
    check("the domain has not changed",
          (frozen["states"], frozen["events"], frozen["actors"], frozen["owners"]) ==
          (list(T.STATES), list(T.EVENTS), list(T.ACTORS), list(T.OWNERS)))
    diffs = [k for k in set(frozen["cells"]) | set(CELLS)
             if frozen["cells"].get(k) != CELLS.get(k)]
    check("every one of the %d cells reproduces the committed board" % len(CELLS),
          not diffs, diffs[:4])

print("\n7. the store side: tombstone, never delete")
# The table can only rule; this is the half that could still lose a row on disk.
import inspect  # noqa: E402

from harness.control import task_loop as TL  # noqa: E402

src = inspect.getsource(TL)
check("task_loop never unlinks a state file",
      "os.remove" not in src and "os.unlink" not in src and "shutil.rmtree" not in src)
check("close_task exists and goes through the table",
      "_apply(st, \"close\"" in src)
# PARSED, NOT GREPPED. The first cut counted the string ".status = " and failed on the COMMENT
# above _apply that quotes the old bad line. Same lesson as g_narrative §6b: a check that reads
# prose reports on prose. Count real assignment NODES whose target is `<something>.status`.
import ast  # noqa: E402

_assigns = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Assign)
            for t in n.targets
            if isinstance(t, ast.Attribute) and t.attr == "status"]
check("every status change in task_loop goes through _apply — none assigns .status directly",
      len(_assigns) == 1,                  # the one inside _apply itself
      [getattr(a.targets[0], "attr", "?") + " @line " + str(a.lineno) for a in _assigns])
_tree = ast.parse(src)
_owner_fn = {}
for _fn in ast.walk(_tree):
    if isinstance(_fn, ast.FunctionDef):
        for _n in ast.walk(_fn):
            if isinstance(_n, ast.Assign):
                for _t in _n.targets:
                    if isinstance(_t, ast.Attribute) and _t.attr == "status":
                        _owner_fn[_n.lineno] = _fn.name
check("...and that one assignment lives inside _apply, the single door",
      set(_owner_fn.values()) == {"_apply"}, _owner_fn)

print("\nG-TASK-TABLE: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_task_table.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_task_table", "pass": PASS, "fail": FAIL, "cells": len(CELLS),
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
