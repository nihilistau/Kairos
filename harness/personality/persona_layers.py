"""persona_layers — the persona as composable FRAGMENTS, resolved once at session start.

WHY NOT ONE FILE, AND WHY NOT JINJA
───────────────────────────────────
`persona.md` was one monolithic prose file, so turning the thought channel on or off meant
HAND-EDITING it — and forgetting to is a real bug this project has already had: `thinking = false`
in the profile while the persona still taught her to open a channel and close it with
`<channel|>`, so she emitted markup the engine was no longer structuring. A coupling that lives
in a human's memory is a coupling that breaks.

The tempting fix is a template engine — LM Studio-style Jinja. It is the wrong tool HERE, and the
reason is specific rather than aesthetic: **the system prefix is snapshot-cached for the process
lifetime** (see `world.render_world`'s comment on the KV-prefix law). A prefix that changes
mid-session re-prefills the entire conversation, which is this system's cardinal sin — it is what
made every turn cost 25 seconds before the prefill work. A template engine at the prefix layer
invites per-turn rendering, and per-turn rendering silently costs a full re-prefill every turn.

Jinja belongs at the CHAT TEMPLATE layer — per-request role wrapping, which is the engine's job
and already lives there. This layer is a different job: assemble a prefix ONCE, from declared
parts, and prove it did not move.

THE FORMAT
──────────
A fragment is a markdown file in the persona directory with frontmatter:

    ---
    order: 30
    when: thinking
    ---
    ## Thinking before you speak
    ...prose...

`order` sorts (ties broken by filename, so composition is total and deterministic).
`when` is optional and is DELIBERATELY NOT AN EXPRESSION LANGUAGE: exactly one knob name,
optionally negated with `!`. That is the whole grammar.

A condition language in a prose file is logic nobody audits. If a fragment needs two conditions
it is two fragments, and that is a feature — the split is visible in the directory listing.

FAILS CLOSED, AND LOUDLY. An unknown knob name excludes the fragment and logs a warning; the gate
asserts no fragment names a knob that does not exist, so a typo cannot quietly ship a persona
section that was meant to be conditional. Silent inclusion is exactly how the thinking mismatch
happened.

BACKWARD COMPATIBLE BY CONSTRUCTION. If the persona directory is absent or empty, `compose()`
returns None and the caller keeps reading `persona.md` exactly as before. The operator's live file
is never a migration hostage.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── THE KNOB VOCABULARY, NAMED ONCE ──────────────────────────────────────────────────
# A fragment may only condition on a knob in this map. Short names because a prose file
# should not be full of SP_ screaming, and an explicit map because "resolve any SP_* the
# author types" is how a typo becomes a silently-included section.
KNOBS: Dict[str, str] = {
    "thinking": "SP_THINKING",
    "world": "SP_WORLD",
    "personality": "SP_PERSONALITY",
    "notes": "SP_NOTES",
    "delegate": "SP_DELEGATE",
    "task_bridge": "SP_TASK_BRIDGE",
    "silence": "SP_SILENCE_ANSWER",
    "mcp_tools": "SP_MCP_TOOLS",
    # her eyes — the 35-sight fragment only composes when the served model
    # actually has a vision path AND it is armed. Teaching her about a sense she
    # does not have is how "I looked and saw" becomes a confabulation.
    "sight": "SP_SIGHT",
    # the research tier — the honesty rule ships WITH the capability, never after it
    "research": "SP_RESEARCH",
}

_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


# ── EDITING A FRAGMENT COSTS A FULL RESTART, NOT A BOUNCE (2026-08-02) ────────────────
#
# The daemon captures the persona+tools prefix ONCE, on a cold prefill, and every later
# turn is a memcpy against that snapshot. Grow the prefix and the snapshot does not grow
# with it: everything past it re-prefills EVERY TURN.
#
# Measured the day two fragments were added and one was extended twice — prefix 3,092
# tokens snapshotted, prompt now 9,350:
#
#     PREFIX-SNAPSHOT: restored 3092 tokens; prefill suffix 6258 (full = ~561s)
#     TURN-PHASE: prefill 6052 tok in 345365 ms (57 ms/tok)
#
# Three hundred and forty-five seconds per turn. From outside it looks exactly like she
# has stopped answering, and a reply that does arrive is a cut-off one.
#
# `serve.py companion --gateway-only` does NOT rebuild the snapshot — it never touches
# the daemon. Only a full `serve.py companion` does, and it costs ~2 minutes of cold
# prefill. So: change anything in this directory, or persona.md, or the self-model, and
# restart the STACK. The panel's "bounce" button is for gateway code; "restart" is for
# this, and that is the difference the two buttons exist to express.
def persona_dir() -> str:
    """Where the fragments live. Beside persona.md, so the two are obviously siblings."""
    d = os.environ.get("SP_PERSONA_DIR")
    if d:
        return d
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "persona")


def knob_on(name: str, env: Optional[Dict[str, str]] = None) -> Optional[bool]:
    """Is a short knob name on? None when the name is not in the vocabulary."""
    var = KNOBS.get(name)
    if var is None:
        return None
    e = env if env is not None else os.environ
    return str(e.get(var, "0")).strip() == "1"


def parse_fragment(text: str) -> Tuple[Dict[str, str], str]:
    """(frontmatter, body). No frontmatter is legal — the fragment is then unconditional."""
    m = _FM.match(text or "")
    if not m:
        return {}, (text or "").strip()
    fm: Dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip().lower()] = v.strip()
    return fm, (text or "")[m.end():].strip()


def _included(fm: Dict[str, str], env, path: str) -> bool:
    cond = (fm.get("when") or "").strip()
    if not cond:
        return True
    neg = cond.startswith("!")
    name = cond[1:].strip() if neg else cond
    on = knob_on(name, env)
    if on is None:
        # FAIL CLOSED AND LOUDLY. A typo'd knob must not silently include a section that
        # was meant to be conditional — that is the exact shape of the thinking mismatch.
        logger.warning("[persona] %s: unknown knob %r in `when:` — fragment EXCLUDED. "
                       "Known: %s", os.path.basename(path), name, ", ".join(sorted(KNOBS)))
        return False
    return (not on) if neg else on


def plan(env: Optional[Dict[str, str]] = None,
         directory: Optional[str] = None) -> List[dict]:
    """What WOULD be composed, in order, with the include decision for each fragment.

    Exposed because the gate — and the operator — need to see why a section is missing without
    reading the composed prefix and guessing.
    """
    d = directory or persona_dir()
    out: List[dict] = []
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".md"):
            continue
        p = os.path.join(d, fn)
        try:
            with open(p, encoding="utf-8") as f:
                fm, body = parse_fragment(f.read())
        except Exception as exc:
            logger.warning("[persona] %s unreadable: %s", fn, exc)
            continue
        try:
            order = int(fm.get("order", "500"))
        except ValueError:
            order = 500
        out.append({"file": fn, "order": order, "when": fm.get("when", ""),
                    "included": _included(fm, env, p), "body": body,
                    "chars": len(body)})
    # order, then filename — a total order, so composition is deterministic and two
    # fragments claiming the same order cannot swap between machines.
    out.sort(key=lambda r: (r["order"], r["file"]))
    return out


def compose(env: Optional[Dict[str, str]] = None,
            directory: Optional[str] = None) -> Optional[str]:
    """The composed persona prose, or None when there are no fragments.

    None is the backward-compatible signal: the caller falls back to persona.md untouched.
    """
    rows = plan(env, directory)
    if not rows:
        return None
    kept = [r["body"] for r in rows if r["included"] and r["body"]]
    if not kept:
        return None
    return "\n\n".join(kept)


def describe(env: Optional[Dict[str, str]] = None,
             directory: Optional[str] = None) -> str:
    """Operator-facing: what composed, what did not, and why. Never used in a prompt."""
    rows = plan(env, directory)
    if not rows:
        return "no persona fragments at %s (falling back to persona.md)" % (
            directory or persona_dir())
    lines = []
    for r in rows:
        why = "" if not r["when"] else ("  [when: %s]" % r["when"])
        lines.append("  %-28s order=%-4d %-4s %5d chars%s"
                     % (r["file"], r["order"], "IN" if r["included"] else "out",
                        r["chars"], why))
    inc = sum(1 for r in rows if r["included"])
    lines.append("  -> %d of %d fragments, %d chars composed"
                 % (inc, len(rows), sum(r["chars"] for r in rows if r["included"])))
    return "\n".join(lines)
