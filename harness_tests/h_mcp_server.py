"""G-MCP-SERVER — the FastMCP layer works end-to-end, offline.

Legs:
  A  server:   in-process FastMCP client lists tools + calls get_time /
               disk_free / run_python (real subprocess) — the server exposes
               the harness's hands correctly.
  B  bridge:   mcp_toolspecs() over mcp_servers.json (stdio spawn of the same
               server) yields callable ToolSpecs; a bridged call round-trips.
  C  wiring:   SP_MCP_TOOLS=1 makes all_tools() include bridged extras while
               native names win on collision.

Run: python tests/h_mcp_server.py   (no daemon needed)
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.pop("SP_RECALL_REGISTRY", None)  # keep the server leg registry-free
# ...AND UNSETTING IT WAS THE BUG (2026-08-24). Popping SP_RECALL_REGISTRY does not
# make the leg registry-free: every reader FALLS BACK to the repo path, so this wrote
# a .bak- file into her real store. Registry-free is not reachable; a temp one is.
# SANDBOX FIRST (2026-08-24). One of nine gates the sandbox audit caught writing into
# her REAL stores; `_gate.sandbox` points every root at a temp dir and must run BEFORE
# any harness import, because a module resolves its root once, at import.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import sandbox as _sandbox  # noqa: E402
_sandbox(os.path.basename(__file__))
# THE FIXTURE, NOT THE PRODUCTION CONFIG (2026-07-31). mcp_servers.json used to hold
# this repo's own server, which is what leg B connected to. That entry was a loop —
# every tool it exposes is already native and got shadowed — so production now holds
# only EXTERNAL servers. This gate still needs a self-connection, and it must not
# depend on npx, a network, or whatever the operator has configured today.
os.environ["SP_MCP_CONFIG"] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "fixtures", "mcp", "selftest.json")


def leg_a_server() -> bool:
    # BOTH SURFACES, through build_server (2026-08-19). The default surface is
    # SANDBOXED-FIRST: the bare file names resolve to the workspace-rooted coding
    # tools and the shell/python executors DO NOT EXIST; SP_MCP_UNSANDBOXED=1 arms
    # them (ledgered, with its arming condition). The old server registered the
    # unsandboxed set under bare names — same names, two toolsets, no guard.
    from fastmcp import Client
    from harness.mcp_server.server import build_server

    async def _go():
        async with Client(build_server(unsandboxed=False)) as c:
            names = {t.name for t in await c.list_tools()}
            base_need = {"get_time", "read_file", "write_file", "list_dir",
                         "web_search", "web_fetch", "disk_free"}
            missing = base_need - names
            armed_leak = {"run_python", "run_powershell", "run_shell"} & names
            t = await c.call_tool("get_time", {})
            time_txt = t.content[0].text
            d = await c.call_tool("disk_free", {"drive": "C:"})
            disk_txt = d.content[0].text
        async with Client(build_server(unsandboxed=True)) as c2:
            names2 = {t.name for t in await c2.list_tools()}
            armed_missing = {"run_python", "run_powershell"} - names2
            r = await c2.call_tool("run_python", {"code": "6*7"})
            py_txt = r.content[0].text
        return missing, armed_leak, armed_missing, time_txt, py_txt, disk_txt

    missing, armed_leak, armed_missing, time_txt, py_txt, disk_txt = asyncio.run(_go())
    # "2026" not "20": any timestamp contains "20"; an assertion any answer passes
    # asserts nothing (the exit-code lesson, in miniature).
    import datetime
    yr = str(datetime.date.today().year)
    ok = (not missing and not armed_leak and not armed_missing
          and (yr in time_txt) and (py_txt.strip() == "42") and ("GB free" in disk_txt))
    print(f"[A server] missing={missing or 'none'} leak={armed_leak or 'none'} "
          f"armed_missing={armed_missing or 'none'} time={time_txt!r} "
          f"py={py_txt.strip()!r} disk={disk_txt!r} -> {ok}")
    return ok


def leg_b_bridge() -> bool:
    from harness.mcp_server.bridge import mcp_toolspecs, list_bridged_tools

    tools = list_bridged_tools(refresh=True)
    names = {t["name"] for t in tools}
    specs = mcp_toolspecs()
    by_name = {s.name: s for s in specs}
    if "get_time" not in by_name:
        print(f"[B bridge] get_time missing from bridged set ({sorted(names)[:8]}...) -> False")
        return False
    out = by_name["get_time"].call()
    ok = "20" in out and "error" not in out.lower()
    print(f"[B bridge] {len(tools)} tools bridged; get_time()={out!r} -> {ok}")
    return ok


def leg_c_wiring() -> bool:
    os.environ["SP_MCP_TOOLS"] = "1"
    from harness.agent import all_tools

    specs = all_tools()
    names = [s.name for s in specs]
    dup = len(names) != len(set(names))
    has_bridged_extra = "disk_free" in names   # exists only on the MCP side
    has_native = "run_python" in names
    ok = has_bridged_extra and has_native and not dup
    print(f"[C wiring] n={len(names)} disk_free={has_bridged_extra} run_python={has_native} dups={dup} -> {ok}")
    os.environ["SP_MCP_TOOLS"] = "0"
    return ok


def leg_d_her() -> bool:
    """THE DOC'S CLAIM, MADE TRUE AND HELD TRUE (2026-08-25).

    docs/MCP.md said since 2026-07-31 that this server "exposes her memory, her board and
    her skills". It exposed a filesystem, web, a clock, and five memory tools — a client
    could read her FILES and knew nothing about HER. The sentence was not deleted; the
    capability was built. So this leg is the doc's claim as a test: the six read-only
    tools about her appear when there is a store to answer from, one of them really
    answers out of a real registry, and NONE of them widens the write surface.
    """
    import tempfile
    from fastmcp import Client
    from harness.mcp_server.server import build_server
    from harness.mcp_server.her_tools import HER_TOOLS

    want = {f.__name__ for f in HER_TOOLS}
    reg = os.path.join(tempfile.mkdtemp(prefix="h_mcp_her_"), "registry.jsonl")
    open(reg, "w").close()

    async def _go(registry: str):
        old = os.environ.get("SP_RECALL_REGISTRY")
        if registry:
            os.environ["SP_RECALL_REGISTRY"] = registry
        else:
            os.environ.pop("SP_RECALL_REGISTRY", None)
        try:
            async with Client(build_server(unsandboxed=False)) as c:
                names = {t.name for t in await c.list_tools()}
                said = ""
                if registry:
                    r = await c.call_tool("what_she_is_wearing", {})
                    said = r.content[0].text
                return names, said
        finally:
            if old is None:
                os.environ.pop("SP_RECALL_REGISTRY", None)
            else:
                os.environ["SP_RECALL_REGISTRY"] = old

    with_store, said = asyncio.run(_go(reg))
    without, _ = asyncio.run(_go(""))
    missing = sorted(want - with_store)
    # ...and the OTHER half, which is what makes it a claim and not a wish: without a
    # store they are absent rather than present-and-answering-out-of-nothing.
    leaked = sorted(want & without)
    # READ-ONLY IS THE DECISION, so it is the assertion. A tool added to her_tools.py
    # whose name says it writes fails here before it reaches a socket.
    writes = sorted(n for n in want
                    if any(v in n for v in ("set_", "write", "forget", "remember",
                                            "add_", "delete", "change", "update")))
    ok = not missing and not leaked and not writes and bool(said.strip())
    print(f"[D her] missing={missing or 'none'} leak_without_store={leaked or 'none'} "
          f"write_shaped={writes or 'none'} wearing={said.strip()[:48]!r} -> {ok}")
    return ok


def main() -> int:
    a = leg_a_server()
    b = leg_b_bridge()
    c = leg_c_wiring()
    d = leg_d_her()
    verdict = a and b and c and d
    print(f"RESULT mcp-server: {'PASS' if verdict else 'FAIL'} "
          f"(server={a} bridge={b} wiring={c} her={d})")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
