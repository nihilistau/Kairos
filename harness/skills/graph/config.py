"""The graph's switches, read from the environment. Every one defaults OFF.

`serve.py::build_env` is the only thing that sets `SP_GRAPH_*` (it strips inherited ones, and a
profile without a `[graph]` table leaves them absent), and it writes booleans as "1"/"0". So a
switch is on only when it is exactly "1"; nothing else a shell might spell ("true", "yes") counts.
`harness/control/spine.py` tests `SP_GRAPH_ANNOTATE == "1"` inline, BEFORE importing this package:
with the switch off the turn executes no graph code (the import sits behind the test). Keep the two spellings in step.
"""
from __future__ import annotations

import os

DEFAULT_ANNOTATE_N = 2
DEFAULT_FOLLOW_CAP = 3
DEFAULT_RULES = ["explicit", "sequence", "day", "minted_from", "activity"]
DEFAULT_REBUILD_MIN_S = 600
DEFAULT_KEEP = 3
MIN_KEEP = 2          # the live generation plus the one a reader may still be loading


def _int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


def switches() -> dict:
    rules = [r.strip() for r in os.environ.get("SP_GRAPH_RULES", "").split(",") if r.strip()]
    return {
        "build": os.environ.get("SP_GRAPH_BUILD") == "1",
        "annotate": os.environ.get("SP_GRAPH_ANNOTATE") == "1",
        "annotate_n": _int("SP_GRAPH_ANNOTATE_N", DEFAULT_ANNOTATE_N),
        "follow": os.environ.get("SP_GRAPH_FOLLOW") == "1",
        "follow_cap": _int("SP_GRAPH_FOLLOW_CAP", DEFAULT_FOLLOW_CAP),
        "rules": rules or list(DEFAULT_RULES),
        "dir": os.environ.get("SP_GRAPH_DIR", ""),
    }


def rebuild_min_s() -> int:
    """Seconds between background rebuilds (and between staleness checks). 0 means no floor."""
    return _int("SP_GRAPH_REBUILD_MIN_S", DEFAULT_REBUILD_MIN_S)


def keep() -> int:
    """Generations `graph.build` leaves on disk. Never below 2."""
    return max(MIN_KEEP, _int("SP_GRAPH_KEEP", DEFAULT_KEEP))
