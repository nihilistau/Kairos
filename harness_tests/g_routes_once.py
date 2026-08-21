"""G-ROUTES-ONCE — a route is declared once, or the winner is silent. OFFLINE.

THE BUG (2026-08-21). The settings window shipped a second "/v1/tuning" entry
into the gateway's GET-dispatch dict — a dict LITERAL, where Python keeps the
last duplicate key and warns about nothing. The older ok-less entry won, the
window froze on "reading the knobs…", and the fix that had been "verified" by
curl was verified against a process running different code. Two copies of one
truth, the repo's own named bug class, in a single expression.

This walks the AST of app.py and fails on ANY dict literal with a duplicated
constant key — routes are where it bit, but the class is the literal itself.

    python harness_tests/g_routes_once.py
"""
from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


print("1. NO DICT LITERAL IN THE GATEWAY DECLARES THE SAME KEY TWICE")
p = os.path.join(ROOT, "harness", "server", "app.py")
tree = ast.parse(open(p, encoding="utf-8").read())
dupes = []
for node in ast.walk(tree):
    if not isinstance(node, ast.Dict):
        continue
    seen = {}
    for k in node.keys:
        if k is None:                      # **spread — not a literal key
            continue
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            if k.value in seen:
                dupes.append("line %d: %r (first at line %d)"
                             % (k.lineno, k.value, seen[k.value]))
            else:
                seen[k.value] = k.lineno
check("app.py has no duplicated string key in any dict literal",
      not dupes, "; ".join(dupes[:4]))

print("\n2. THE ROUTE THAT FROZE THE WINDOW CARRIES ITS CONTRACT")
src = open(p, encoding="utf-8").read()
check("/v1/tuning is declared exactly once", src.count('"/v1/tuning": lambda') == 1,
      "count=%d" % src.count('"/v1/tuning": lambda'))
check("...and that one declaration ships ok:true",
      '"/v1/tuning": lambda: {"ok": True' in src)

print("\nG-ROUTES-ONCE  %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
