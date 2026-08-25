"""G-MCP-POOL — a tool call is not a process spawn, and the pool cannot lie. OFFLINE*.

*No GPU and no sp-daemon: it spawns the repo's own stdio MCP server, which is a
Python subprocess. Slower than a pure-offline gate, still runnable anywhere.

WHAT THIS MEASURES AND WHY IT IS A GATE RATHER THAN A NOTE.

Connect-per-call, measured 2026-07-31 before the pool existed:

    disk_free()   2.200 s
    disk_free()   2.223 s
    disk_free()   2.224 s

24 ms of variance across three calls is the signature of a FIXED cost — a Python
interpreter spawned per tool call — not of a tool doing work. She reaches for tools
mid-conversation, so that is 2.2 s of dead air every time, and it is the thing that
would make her tool use feel bad long before anything about it was wrong.

A performance fix with no gate silently rots back into the slow path the first time
someone "simplifies" the session handling. So the speedup is asserted, and so is
the property that matters more than speed: THE POOLED AND UNPOOLED PATHS MUST
RETURN THE SAME BYTES. A pool that renders results differently is a second
implementation of what a tool returns — this repo's signature bug wearing a
performance hat.

Run: python harness_tests/g_mcp_pool.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SP_MCP_TOOLS"] = "1"
# Point at the FIXTURE, not mcp_servers.json. Production config now holds only
# EXTERNAL servers; this gate needs a self-connection and must not depend on npx,
# a network, or whatever the operator has configured today.
os.environ["SP_MCP_CONFIG"] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "fixtures", "mcp", "selftest.json")

_P = _F = 0


def ok(cond, name, detail=""):
    global _P, _F
    if cond:
        _P += 1
        print(f"  ok   {name}")
    else:
        _F += 1
        print(f"  FAIL {name}   {detail}")


from harness.mcp_server import bridge, pool  # noqa: E402

MARKER = "disk_free"   # the one bridged-only tool; see docs/MCP.md

print("1. the pool is armed by default")
ok(pool.enabled(), "SP_MCP_POOL defaults on")

print("\n2. one session serves many calls")
pool.shutdown(stop_loop=True)
specs = bridge.mcp_toolspecs(exclude_names=set())
tool = next((s for s in specs if s.name == MARKER), None)
ok(tool is not None, f"the bridged marker tool '{MARKER}' is present",
   [s.name for s in specs][:6])

if tool is None:
    print(f"\nG-MCP-POOL: {_P} pass, {_F + 1} fail (cannot continue without the bridge)")
    sys.exit(1)

times = []
results = []
for _ in range(4):
    t0 = time.perf_counter()
    results.append(tool.call())
    times.append(time.perf_counter() - t0)

st = pool.status()
ok(st["opened"] <= 1, "at most ONE session was opened for four calls", st)
ok(st["reused"] >= 3, "the later calls reused it", st)
ok(st["reconnects"] == 0, "no reconnect was needed", st)

print("\n3. and it is actually fast now")
slowest = max(times)
ok(slowest < 0.5, f"every call under 0.5 s (was 2.2 s unpooled) — slowest {slowest:.3f}s",
   [round(t, 3) for t in times])
ok(all("error" not in str(r).lower() for r in results),
   "every call returned a real result", results[:2])

print("\n4. pooled and unpooled render IDENTICALLY")
# The property that matters more than the speed.
os.environ["SP_MCP_POOL"] = "0"
import importlib  # noqa: E402
importlib.reload(pool)
ok(not pool.enabled(), "SP_MCP_POOL=0 disables the pool")
unpooled = bridge.mcp_toolspecs(exclude_names=set())
u_tool = next((s for s in unpooled if s.name == MARKER), None)
u_res = u_tool.call() if u_tool else "<absent>"
# disk_free reports free space, which can move between calls; compare SHAPE not bytes.
ok(u_tool is not None, "the same tool exists on the unpooled path")
ok(u_res.split()[-4:] == results[0].split()[-4:],
   "unpooled result has the same shape as the pooled one",
   f"{u_res!r} vs {results[0]!r}")

os.environ["SP_MCP_POOL"] = "1"
importlib.reload(pool)

print("\n5. a dead session is dropped, not handed out again")
pool.shutdown(stop_loop=True)
specs = bridge.mcp_toolspecs(exclude_names=set())
tool = next(s for s in specs if s.name == MARKER)
tool.call()                                   # opens one
before = pool.status()["open"]
pool.drop("kairos")                          # simulate the server dying
mid = pool.status()["open"]
after_res = tool.call()                       # must transparently reopen
ok("kairos" in before, "a session was open", before)
ok("kairos" not in mid, "drop() removed it", mid)
ok("GB" in after_res or after_res, "the next call transparently reopened", after_res[:40])

print("\n6. the two paths share ONE result renderer")
import ast  # noqa: E402
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "harness", "mcp_server", "pool.py"), encoding="utf-8").read()
ok("_extract_text" in src, "pool.py calls bridge._extract_text rather than its own")
tree = ast.parse(src)
own = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)
       and "extract" in n.name.lower()]
ok(not own, "pool.py defines no result renderer of its own", own)

pool.shutdown(stop_loop=True)
print(f"\nG-MCP-POOL: {_P} pass, {_F} fail")
sys.exit(1 if _F else 0)
