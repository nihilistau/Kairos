"""Operator-customizable MCP tools.

Drop plain Python functions here — each one becomes an MCP tool automatically
(the docstring's first line is the tool description; type hints become the
schema). Either list them in CUSTOM_TOOLS, or just define them at module top
level (every public function is picked up when CUSTOM_TOOLS is absent).

Example:

    def disk_free(drive: str = "") -> str:
        \"\"\"Report free space on a drive or path.\"\"\"
        import os, shutil
        du = shutil.disk_usage(drive or os.path.abspath(os.sep))
        return f"{du.free / 1e9:.1f} GB free of {du.total / 1e9:.1f} GB"

A TOOL YOU ADD HERE RUNS WHEREVER THE HARNESS RUNS. The example above used to default to
a drive letter and glue on a backslash, which read as harmless until the suite ran on
Linux and every call raised. If a tool touches the filesystem, reach for `os.sep` and
`os.path` rather than the shape of your own machine.
"""
from __future__ import annotations


def disk_free(drive: str = "") -> str:
    """Report free space on a drive or path (defaults to the filesystem root)."""
    # ── IT WAS WINDOWS-ONLY, IN A TOOL THAT SHIPS (2026-09-11) ───────────────────────
    # `drive: str = "D:"` with `shutil.disk_usage(drive + "\\")` is two Windows
    # assumptions in one line: the operator's drive letter as the default, and a
    # backslash as the separator. On Linux it raised `[Errno 2] No such file or
    # directory: 'C:\\'` — which is also why `g_mcp_pool` looked broken there: this is
    # its marker tool, and a tool that throws on every call made the session pool look
    # like it was failing to pool when it was faithfully reporting a failing tool.
    # Found the first time the suite ran off Windows.
    #
    # An EMPTY default rather than a portable literal: the answer to "how much space is
    # there" should be about the machine this is running on, and `abspath(os.sep)` is
    # that on both ("/" on POSIX, the current drive's root on Windows). A caller may
    # still name a drive or any path.
    import os
    import shutil

    target = drive or os.path.abspath(os.sep)
    if os.name == "nt" and len(target) == 2 and target.endswith(":"):
        target += os.sep          # "D:" is the CWD on D:, "D:\" is its root
    du = shutil.disk_usage(target)
    return f"{du.free / 1e9:.1f} GB free of {du.total / 1e9:.1f} GB"


CUSTOM_TOOLS = [disk_free]
