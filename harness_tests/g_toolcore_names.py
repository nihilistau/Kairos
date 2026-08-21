"""G-TOOLCORE-NAMES — the compatibility shim re-exports and NEVER re-defines. OFFLINE.

THE COLLISION THIS ENDED. Three directories named some variant of "mcp":

    harness/mcp/        the tool framework — NOT the protocol, despite the name
    harness/mcp_server/ the actual Model Context Protocol
    mcp/                an empty stub at the repo root containing one README

which is where the operator's complaint began — "i dont even know where they are
located". No amount of documentation fixes a directory that lies about its
contents. The framework is now `harness/toolcore/`, the root stub is deleted, and
the only "mcp" left in the tree is the one that speaks the protocol.

WHY THIS GATE EXISTS. `harness/mcp/` survives as a shim so external imports keep
working, and a compatibility shim is the single most tempting place in a codebase
to quietly grow a second implementation. That is AGENTS.md §0's bug class exactly:
"an invariant enforced in one of two paths is enforced in neither". So the shim is
asserted to be the SAME OBJECT, not merely an equivalent one — identity, not
equality, because equality would pass for a copy that had already drifted.

Run: python harness_tests/g_toolcore_names.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_P = _F = 0


def ok(cond, name, detail=""):
    global _P, _F
    if cond:
        _P += 1
        print(f"  ok   {name}")
    else:
        _F += 1
        print(f"  FAIL {name}   {detail}")


MODULES = ("tools", "grammar", "framework", "comms_framework")

print("1. the framework lives at harness.toolcore")
import harness.toolcore as tc  # noqa: E402
ok(os.path.isdir(os.path.join(ROOT, "harness", "toolcore")), "harness/toolcore/ exists")
for m in MODULES:
    ok(os.path.isfile(os.path.join(ROOT, "harness", "toolcore", f"{m}.py")),
       f"toolcore/{m}.py is present")

print("\n2. the shim is the SAME MODULE OBJECT, not a copy")
for m in MODULES:
    real = __import__(f"harness.toolcore.{m}", fromlist=["x"])
    shim = __import__(f"harness.mcp.{m}", fromlist=["x"])
    ok(real is shim, f"harness.mcp.{m} IS harness.toolcore.{m}",
       f"{real!r} vs {shim!r}")

print("\n3. the names that matter are identical objects")
from harness.toolcore.tools import ToolSpec as A_ToolSpec  # noqa: E402
from harness.mcp.tools import ToolSpec as B_ToolSpec       # noqa: E402
ok(A_ToolSpec is B_ToolSpec, "ToolSpec is one class, reachable by both paths")
for nm in ("run_with_tools", "build_tool_system", "_parse_tool_calls"):
    a = getattr(__import__("harness.toolcore.tools", fromlist=["x"]), nm, None)
    b = getattr(__import__("harness.mcp.tools", fromlist=["x"]), nm, None)
    ok(a is not None and a is b, f"{nm} is one function", f"{a} vs {b}")

print("\n4. the shim contains no logic of its own")
# A shim that grows a function body is a second implementation waiting to happen.
# Every file under harness/mcp/ must be re-export only: no def, no class.
import ast  # noqa: E402
for fn in sorted(os.listdir(os.path.join(ROOT, "harness", "mcp"))):
    if not fn.endswith(".py"):
        continue
    src = open(os.path.join(ROOT, "harness", "mcp", fn), encoding="utf-8").read()
    tree = ast.parse(src)
    defs = [n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    ok(not defs, f"harness/mcp/{fn} defines nothing of its own", defs)

print("\n5. nothing in the tree still imports the old path")
bad = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    if any(s in dirpath for s in ("__pycache__", ".git", "target", "node_modules",
                                  os.path.join("harness", "mcp"))):
        continue
    for f in filenames:
        # This gate necessarily imports the shim in order to test it — it is the
        # one legitimate importer in the tree.
        if not f.endswith(".py") or f == os.path.basename(__file__):
            continue
        p = os.path.join(dirpath, f)
        try:
            src = open(p, encoding="utf-8").read()
        except OSError:
            continue
        for ln, line in enumerate(src.splitlines(), 1):
            t = line.strip()
            if t.startswith("#"):
                continue
            if "harness.mcp." in t and "harness.mcp_server" not in t:
                bad.append(f"{os.path.relpath(p, ROOT)}:{ln}")
ok(not bad, "no live import of harness.mcp.* outside the shim", bad[:6])

print("\n6. the root mcp/ stub is gone")
ok(not os.path.exists(os.path.join(ROOT, "mcp")),
   "the empty root mcp/ directory no longer exists")

print("\n7. the ONLY thing still called mcp is the protocol")
ok(os.path.isfile(os.path.join(ROOT, "harness", "mcp_server", "bridge.py")),
   "harness/mcp_server/ is intact (the real MCP)")

print(f"\nG-TOOLCORE-NAMES: {_P} pass, {_F} fail")
sys.exit(1 if _F else 0)
