"""harness.launch — the Launch window's back end: edit her profile, keep saved setups,
record what she was launched with. Every module here resolves the var root through
`var_dir()`, so a gate can point the lot at a sandbox with one variable."""
from __future__ import annotations

import os

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def var_dir() -> str:
    """`SP_LAUNCH_VAR` if set (gates), else `<repo>/var`."""
    return os.environ.get("SP_LAUNCH_VAR") or os.path.join(_REPO, "var")
