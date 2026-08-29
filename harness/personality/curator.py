"""PF-B5 — NIGHTSHIFT personality curation. The system curates the personality the way it curates
memory (mirrors consolidate_conversation): between turns / on idle it (1) EXTRACTS the personality
shifts the model expressed in the transcript, (2) PRUNES stale/duplicate traits, and (3) SNAPSHOTS
the personality into a content-addressed memory-okf-personality tier — so personality is
SYSTEM-curatable and recoverable, not only self-modifiable.

Deterministic (no model call): reuses PF-B3 tag extraction on the assistant turns + a dedup/cap
prune + an OKF snapshot. ADR-002: the curated state is a clean symbolic artifact.
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from harness.personality.persona_file import parse_persona, write_state, render_state
from harness.personality.interceptor import apply_personality_tags, _persona_path

HARNESS_ROOT = Path(__file__).resolve().parents[2]
MAX_TRAITS = 8


def _tier_root(root=None) -> Path:
    return Path(root) if root else Path(
        os.environ.get("SP_PERSONALITY_OKF_ROOT") or (HARNESS_ROOT / "memory-okf-personality"))


def _dedup(items: List[str]) -> List[str]:
    """ONE DEDUPER, and it is the writer's (2026-08-03).

    This had its own: lowercase-key, first-wins, no cap, no normalisation. The writer in
    `interceptor` grew a stricter one the day her live state came back reading
    "flirty, +flirty, ... deeply_connected, deeply\\_connected" — a captured sign and a
    markdown escape, both stored as traits she then read back as her own character. Two
    implementations of "is this the same trait" is how one of them ends up seeing a
    duplicate the other does not; this one now calls that one.

    The visible consequence is that `pruned` usually reports 0 on the live path, because
    the writer has already cleaned what it would have caught. That is the correct number,
    not a regression: this pass still earns its keep against the CAP and against a persona
    file edited by hand, neither of which the writer ever sees.
    """
    from harness.personality.interceptor import _dedupe_traits, _norm, _ok
    return _dedupe_traits([t for t in (_norm(x) for x in items) if _ok(t)], cap=MAX_TRAITS)


def consolidate_personality(messages: Optional[List[dict]] = None,
                            persona_path: str = "", tier_root=None) -> Dict:
    """Curate the personality: extract shifts from the transcript, prune traits, snapshot to the
    memory-okf-personality tier. Returns {state, pruned, snapshot_addr}."""
    path = persona_path or _persona_path()

    # 1) THE REPLAY IS RETIRED (2026-08-29 audit, M8). This re-applied every mark in
    # the day's assistant turns, last-mark-wins — from a RECORDING. Every mark is
    # applied LIVE now on all three mouths and her unprompted turns (_settle_turn →
    # run_post_turn, the 08-24 A4 fix), so the only thing the replay could do is
    # overwrite a LATER state change that did not come from a mark: she calls
    # adjust_mood("quiet") at midnight, or he sets a mood from ops.html, and at 04:00
    # the transcript's last [MOOD:flirty] wrote over it — she woke in a mood a
    # recording chose. The docstring above already concedes the live path leaves this
    # pass nothing to extract; its keep is the CAP and the hand-edited file (below).
    # `messages` stays in the signature: the callers still pass it, and a future
    # missed-mark reconciler would want it — but it must reconcile, never replay.

    # 2) PRUNE: dedup + cap traits (drift-control)
    text = Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""
    _, state = parse_persona(text)
    traits = _dedup([t for t in state.get("traits", "").split(",")])
    pruned = len([t for t in state.get("traits", "").split(",") if t.strip()]) - len(traits)
    if len(traits) > MAX_TRAITS:
        pruned += len(traits) - MAX_TRAITS
        traits = traits[:MAX_TRAITS]
    if traits:
        state["traits"] = ", ".join(traits)
    write_state(path, state)

    # 3) SNAPSHOT: store the personality as a content-addressed OKF concept (versioned, recoverable)
    body = render_state(state) or "personality: (empty)"
    root = _tier_root(tier_root)
    full = root / "full"
    full.mkdir(parents=True, exist_ok=True)
    addr = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    fm = ["---", "type: mem-concept", "title: personality snapshot", f"addr: {addr}",
          "mem_class: persona", "mem_owner: self", "mem_delivery: system",
          f"ts: {int(time.time())}", "---", "", body, ""]
    (full / f"{addr}.md").write_text("\n".join(fm), encoding="utf-8")

    return {"state": {k: state.get(k, "") for k in ("voice", "mood", "traits")},
            "pruned": pruned, "snapshot_addr": addr}
