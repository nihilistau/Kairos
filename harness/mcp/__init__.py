"""harness.mcp — DEPRECATED SHIM. The real module is `harness.toolcore`.

THIS PACKAGE WAS NEVER MODEL CONTEXT PROTOCOL. It held ToolSpec, the tool-call
grammar, and the agent framework — and it sat next to `harness/mcp_server/`, which
IS the protocol, plus an empty `mcp/` stub at the repo root. Three directories
named some variant of "mcp", one of them the actual thing, and the operator's
complaint about this system began exactly there:

    "i dont even know where they are located"

No amount of documentation fixes a directory that lies about its contents, so the
framework moved to `harness/toolcore/` and the only "mcp" left in the tree is the
one that speaks the protocol.

EVERY NAME HERE IS RE-EXPORTED, NEVER RE-DEFINED. `harness.mcp.tools.ToolSpec` and
`harness.toolcore.tools.ToolSpec` are THE SAME OBJECT, asserted by identity in
g_toolcore_names.py. A shim that re-implements is two copies of one truth, which is
the bug class this repo is organised against and precisely what a compatibility
layer is most tempted to become.

Delete this package once nothing outside the repo imports it.
"""
from harness.toolcore import *  # noqa: F401,F403
