"""DEPRECATED: import `harness.toolcore.grammar` instead. Re-export only — see harness/mcp/__init__.py."""
from harness.toolcore.grammar import *  # noqa: F401,F403
from harness.toolcore import grammar as _real
import sys as _sys
_sys.modules[__name__] = _real   # SAME module object, so identity holds for private names too
