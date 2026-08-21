"""DEPRECATED: import `harness.toolcore.tools` instead. Re-export only — see harness/mcp/__init__.py."""
from harness.toolcore.tools import *  # noqa: F401,F403
from harness.toolcore import tools as _real
import sys as _sys
_sys.modules[__name__] = _real   # SAME module object, so identity holds for private names too
