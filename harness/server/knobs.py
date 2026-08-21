"""knobs — the operator-visible control surface, and the one thing it must never lie about.

WHY A REGISTRY AND NOT A LIST OF CHECKBOXES
───────────────────────────────────────────
The knobs in this system fall into two groups that LOOK identical in a UI and behave nothing
alike:

  LIVE      read from `os.environ` at CALL TIME inside the gateway process, so setting it
            changes the next turn. `SP_DELEGATE`, `SP_TASK_BRIDGE`, `SP_SILENCE_ANSWER`,
            `SP_SEM_DOMINATE`, `SP_SEM_EXPAND`, `SP_AGENCY_TASKS`, `SP_NOTES`.

  RESTART   read ONCE — at daemon launch (`SP_THINKING`, `SP_THINK_*`: the tokenizer opens the
            channel and the sampler is constructed per request but from launch-time env) or at
            session start into the persist-KV prefix (`SP_WORLD`, `SP_PERSONA_DIR`). Setting
            these in a running process does NOTHING, and the prefix ones MUST NOT take effect
            mid-session even if they could: a prefix that moves re-prefills the whole
            conversation.

A toggle that silently does nothing is worse than no toggle — it is the `--worktree` lesson from
`delegate.py` in a different costume: a control that is load-bearing in the operator's head and
inert in fact. So the group is DATA here, `set_knob()` REFUSES a restart-scoped write with the
reason, and the UI renders the two groups differently because they are different.

THE VALUES ARE THE PROFILE'S, NOT THIS FILE'S. Nothing here has a default. `serve.py::build_env`
is the only door, and this module reports what actually reached the process — so a knob missing
from `build_env` shows as absent rather than as a plausible-looking `false`. `g_knobs.py` asserts
every name here is mapped there, which is what stops this registry becoming a second source of
truth for what exists.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

LIVE = "live"
RESTART = "restart"

# (env var, group, scope, one-line description for the operator)
# Scope is the LOAD-BEARING field: it decides whether a write is honoured or refused.
REGISTRY: Tuple[Tuple[str, str, str, str], ...] = (
    # ── her autonomy: read per call, safe to toggle live ──────────────────────────────
    ("SP_DELEGATE", "Her hands", LIVE,
     "She may hand a coding job to Grok in an isolated worktree. She never merges."),
    ("SP_TASK_BRIDGE", "Her work", LIVE,
     "A task note is promoted to a real queued task at the day boundary."),
    ("SP_AGENCY_TASKS", "Her work", LIVE,
     "Drain one queued task per day boundary. Pointless without the bridge."),
    ("SP_NOTES", "Her work", LIVE,
     "The note tools (board, reminders, watches) are in her live tool set."),
    # ── memory experiments: measured against, off, read per call ──────────────────────
    ("SP_SEM_DOMINATE", "Memory (experimental)", LIVE,
     "Dickson subsumption proposes supersede candidates. Measured 4 good / 3 bad."),
    ("SP_SEM_EXPAND", "Memory (experimental)", LIVE,
     "Query expansion — measured and lost (+0.04 hit, -0.12 precision), and currently "
     "WIRED TO NOTHING: no live path imports expand.py, so this switch moves no "
     "machinery. Kept visible so the state is a fact on the panel, not a hidden one."),
    ("SP_SILENCE_ANSWER", "Memory (experimental)", LIVE,
     "What has gone quiet may colour an answer. Inert until the ledger is 14 days deep."),
    # ── the thought channel: daemon launch, restart required ──────────────────────────
    ("SP_THINKING", "Thinking", RESTART,
     "The private thought channel. Off = faster; on = she can catch herself."),
    ("SP_THINK_MIN", "Thinking", RESTART,
     "FLOOR on the thought, in tokens. Measured to make things worse; keep 0."),
    ("SP_THINK_MAX", "Thinking", RESTART,
     "CEILING on the thought, in tokens. 0 = uncapped (that was the 308-second turn)."),
    ("SP_THINK_MAX_MS", "Thinking", RESTART,
     "CEILING on the thought, wall clock ms. Bounds the wait when decode is slow."),
    # ── the prefix: session start, restart required, and must not move mid-session ────
    ("SP_WORLD", "Her context", RESTART,
     "The standing world in her prefix. Snapshot-cached — moving it re-prefills."),
    ("SP_PERSONALITY", "Her context", RESTART,
     "Personality state + self-model in the prefix."),
    ("SP_MCP_TOOLS", "Her context", RESTART,
     "Bridge MCP servers into her tool set."),
)

_BY_NAME: Dict[str, Tuple[str, str, str, str]] = {r[0]: r for r in REGISTRY}

_TRUE = ("1", "true", "yes", "on")


def _is_bool_knob(name: str) -> bool:
    """The THINK_* budgets are integers; everything else here is a flag."""
    return not name.startswith("SP_THINK_M")


def read_all() -> List[dict]:
    """Every registered knob with the value that ACTUALLY reached this process.

    `present: False` means the knob never came through `build_env` — reported as absent
    rather than as a confident-looking default, because that difference is exactly what the
    path-knob regression turned on (an exported `""` is not the same as unset).
    """
    out: List[dict] = []
    for name, group, scope, desc in REGISTRY:
        raw = os.environ.get(name)
        row = {"name": name, "group": group, "scope": scope, "description": desc,
               "present": raw is not None, "raw": raw}
        if _is_bool_knob(name):
            row["type"] = "bool"
            row["value"] = (raw or "").strip().lower() in _TRUE
        else:
            row["type"] = "int"
            try:
                row["value"] = int((raw or "0").strip())
            except ValueError:
                row["value"] = 0
        out.append(row)
    return out


def set_knob(name: str, value) -> Tuple[bool, str]:
    """Set a LIVE knob in this process. Returns (ok, message).

    REFUSES anything restart-scoped, and says why. This is the whole reason the module
    exists: a UI that appears to set `SP_THINKING` and does not is a control that lies, and
    the operator would rediscover that as "I turned thinking off and nothing changed".
    """
    rec = _BY_NAME.get(name)
    if rec is None:
        return False, "unknown knob %r — not in the registry" % name
    _n, _g, scope, _d = rec
    if scope == RESTART:
        return False, ("%s is read at daemon launch / session start, so setting it here would "
                       "do nothing. Change it in profiles/companion.toml and restart "
                       "(`python serve.py companion --stop` then `python serve.py companion`)."
                       % name)
    if _is_bool_knob(name):
        on = value if isinstance(value, bool) else str(value).strip().lower() in _TRUE
        os.environ[name] = "1" if on else "0"
        return True, "%s = %s (this turn onward)" % (name, "on" if on else "off")
    try:
        n = int(value)
    except (TypeError, ValueError):
        return False, "%s expects an integer" % name
    if n < 0:
        return False, "%s cannot be negative" % name
    os.environ[name] = str(n)
    return True, "%s = %d (this turn onward)" % (name, n)


def groups() -> List[str]:
    """Registry order, deduplicated — so the UI renders in a deliberate order."""
    seen, out = set(), []
    for _n, g, _s, _d in REGISTRY:
        if g not in seen:
            seen.add(g)
            out.append(g)
    return out
