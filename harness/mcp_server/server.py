"""Kairos FastMCP server — the system's capabilities over MCP.

Exposes the harness skills as a standard MCP server. Run:
    python -m harness.mcp_server              # stdio (for MCP clients / the bridge)
    python -m harness.mcp_server --http 8765  # streamable-HTTP on a port

Customizing: add plain functions to harness/mcp_server/custom_tools.py —
anything in its CUSTOM_TOOLS list (or any public function if the list is
absent) is auto-registered. No FastMCP knowledge needed.

SANDBOXED-FIRST (2026-08-19, operator's call). This used to register ALL of
SYSTEM_TOOLS under bare names: the unsandboxed read_file/write_file/list_dir (no path
restriction; write_file overwrites silently) and run_shell/run_powershell/run_python.
agent.all_tools() goes to deliberate trouble to order the sandboxed CODING_TOOLS first
so their names WIN — and this surface had no such ordering: same names, two toolsets,
one lacked the guard. Now the sandboxed file tools (HARNESS_WORKSPACE-rooted) own the
bare names, and the shell/python executors exist only when SP_MCP_UNSANDBOXED=1 —
mapped in serve.py, ledgered in docs/OFF-BY-DEFAULT.md with its arming condition.
"""
from __future__ import annotations

import inspect
import os
import sys

from fastmcp import FastMCP


def build_server(unsandboxed: bool | None = None) -> FastMCP:
    """Construct the server with its tool surface. `unsandboxed=None` reads the knob —
    a parameter so the gate can assert BOTH surfaces without re-importing the module."""
    if unsandboxed is None:
        unsandboxed = os.environ.get("SP_MCP_UNSANDBOXED") == "1"
    m = FastMCP(
        "kairos",
        instructions=(
            "Kairos system server: workspace filesystem (sandboxed), web "
            "search/fetch, clock, and the persistent fact memory of the local model."
            + (" Shell/Python execution is armed." if unsandboxed else "")
        ),
    )

    def reg(fn, name: str | None = None) -> None:
        m.tool(fn, name=name or fn.__name__)

    from harness.skills.builtin.coding import list_dir, read_file, write_file
    from harness.skills.system_tools import (CODE_TOOLS, SHELL_TOOLS, TIME_TOOLS,
                                             WEB_TOOLS)
    for fn in (list_dir, read_file, write_file):
        reg(fn)                                   # the sandboxed three own the bare names
    for fn in WEB_TOOLS + TIME_TOOLS:
        reg(fn)
    if unsandboxed:
        for fn in SHELL_TOOLS + CODE_TOOLS:
            reg(fn)

    # Memory tools are optional: they need SP_RECALL_REGISTRY to point at the
    # daemon's production registry. Skipped silently when unset.
    if os.environ.get("SP_RECALL_REGISTRY"):
        try:
            from harness.skills.memory import MEMORY_TOOLS
            for fn in MEMORY_TOOLS:
                reg(fn)
        except Exception as exc:  # pragma: no cover
            print(f"[mcp_server] memory tools skipped: {exc}", file=sys.stderr)

    # Operator-defined tools from custom_tools.py (easily customizable).
    try:
        from harness.mcp_server import custom_tools
        fns = getattr(custom_tools, "CUSTOM_TOOLS", None)
        if fns is None:
            fns = [f for n, f in vars(custom_tools).items()
                   if inspect.isfunction(f) and not n.startswith("_")]
        for fn in fns:
            reg(fn)
    except ImportError:
        pass
    return m


mcp = build_server()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--http" in args:
        i = args.index("--http")
        port = int(args[i + 1]) if len(args) > i + 1 and args[i + 1].isdigit() else 8765
        mcp.run(transport="http", host="127.0.0.1", port=port)
    else:
        mcp.run()  # stdio
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
