"""Operator-customizable MCP tools.

Drop plain Python functions here — each one becomes an MCP tool automatically
(the docstring's first line is the tool description; type hints become the
schema). Either list them in CUSTOM_TOOLS, or just define them at module top
level (every public function is picked up when CUSTOM_TOOLS is absent).

Example:

    def disk_free(drive: str = "D:") -> str:
        \"\"\"Report free space on a drive.\"\"\"
        import shutil
        du = shutil.disk_usage(drive + "\\\\")
        return f"{du.free / 1e9:.1f} GB free of {du.total / 1e9:.1f} GB"
"""
from __future__ import annotations


def disk_free(drive: str = "D:") -> str:
    """Report free space on a drive."""
    import shutil

    du = shutil.disk_usage(drive + "\\")
    return f"{du.free / 1e9:.1f} GB free of {du.total / 1e9:.1f} GB"


CUSTOM_TOOLS = [disk_free]
