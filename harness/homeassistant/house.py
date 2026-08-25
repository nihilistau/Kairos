"""The seam: what the house is allowed to tell her.

SEPARATE FROM THE BRIDGE ON PURPOSE. The bridge carries measurements into his body's
history, where the telemetry doctrine already governs them. This is the other direction of
the same question — what she may *say* about the house — and it needs its own answer,
because a light being on is not a fact about him and must never be spoken as one.

WHAT IT DOES NOT DO, and the omission is the design:

  * It does not enumerate his house. Home Assistant will happily list several hundred
    entities. Handing her that is the "she never sees the feed" rule from telemetry with
    the labels changed: it would cost budget, tell her nothing she could act on, and teach
    her to talk like a status page.
  * It does not act. Nothing here turns anything on or off. Giving a companion the light
    switches is a genuinely different product with genuinely different failure modes, and
    it is not something to arrive at by accident while wiring up a sleep sensor. When it is
    wanted it gets its own design, its own gate and its own row in OFF-BY-DEFAULT.
  * It claims nothing by default. `WATCH` is empty until he puts entities in it, and an
    empty `WATCH` means `present()` returns "" forever. Silence is an answer here too.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from . import bridge as _bridge
from . import client as _client

# ── WHAT SHE MAY NOTICE ──────────────────────────────────────────────────────────────
# Entity ids, chosen by him, one line each. Deliberately a committed table rather than a
# pattern or a whole domain: "every light" is a hundred rows the day he adds a strip, and
# the point of this list is that a person decided each one was worth her attention.
#
# Empty by default. Nothing here is a good guess — which lights matter is not something
# this file can know, and a default that guessed would be wrong in his house specifically.
WATCH: tuple = ()

# How stale a reading may be before it is not worth saying. Same reasoning as
# telemetry.body.FRESH_S: a companion who says "the kitchen light is on" about a light
# switched off an hour ago is worse than one who says nothing.
FRESH_S = 15 * 60


def read(now: Optional[float] = None) -> Dict[str, Any]:
    """Everything this seam knows, as data. NEVER RAISES.

    Mirrors `telemetry.body.read()` deliberately, down to the shape of the return, so a
    reader who understands one understands the other."""
    now = time.time() if now is None else now
    out: Dict[str, Any] = {"observed": {}, "facts": {}, "why": "", "watching": list(WATCH)}

    if not _client.configured():
        out["why"] = "Home Assistant is not configured"
        return out
    if not WATCH:
        # The honest empty: connected, and told to care about nothing.
        out["why"] = "nothing in the watch list — she is told nothing about the house"
        return out

    cl = _client.HAClient()
    states, why = cl.states()
    if why:
        out["why"] = why
        return out

    by_id = {str(s.get("entity_id") or ""): s for s in states}
    for eid in WATCH:
        st = by_id.get(eid)
        if st is None:
            continue
        age = None
        t = _client.parse_ha_time(str(st.get("last_updated") or ""))
        if t is not None:
            age = now - t
            if age > FRESH_S:
                continue
        name = (st.get("attributes") or {}).get("friendly_name") or eid
        out["observed"][name] = st.get("state")
    return out


def present(now: Optional[float] = None) -> str:
    """The sentence she may read. EMPTY when there is nothing honest to say.

    Empty is the normal case and that is intended: `WATCH` ships empty, so this framework
    adds nothing to her prefix until he decides it should."""
    r = read(now)
    obs = r.get("observed") or {}
    if not obs:
        return ""
    on = [k for k, v in obs.items() if str(v).lower() in ("on", "open", "home", "detected")]
    if not on:
        return ""
    # Named, never counted. "Three lights are on" is a status line; "the kitchen light is
    # on" is a thing somebody in the house would actually say.
    if len(on) == 1:
        return "the %s is on" % on[0].lower()
    return "%s and %s are on" % (", ".join(x.lower() for x in on[:-1]), on[-1].lower())


def status() -> Dict[str, Any]:
    """Convenience for the panel: the bridge's view plus this seam's."""
    s = _bridge.status()
    s["watching"] = list(WATCH)
    s["house"] = read()
    return s
