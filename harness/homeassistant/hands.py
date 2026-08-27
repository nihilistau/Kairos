"""The other seam: what she is allowed to DO to the house.

SEPARATE FROM house.py ON PURPOSE, and the separation is the design. That module's
docstring promises, in as many words, that it does not act — "giving a companion the light
switches is a genuinely different product with genuinely different failure modes, and it is
not something to arrive at by accident while wiring up a sleep sensor. When it is wanted it
gets its own design, its own gate and its own row in OFF-BY-DEFAULT." This is that.

FOUR GUARDS, AND THEY ARE NOT THE SAME GUARD FOUR TIMES
────────────────────────────────────────────────────────
1. A KNOB, off by default (`SP_HOUSE_HANDS`). Nothing here can move a thing in his house
   until he arms it, and the arming is a decision he makes once rather than a default that
   drifted on.

2. A CLOSED SET OF DOMAINS she may touch: lights and fans. This is the guard that cannot be
   widened by an edit to a list, and it exists because of what the list would otherwise
   reach. His `switch.*` entities include a KETTLE, a 3D-printer plug and a fingerbot.
   "All lights and fans" must not become "and the kettle" because a filter was one line too
   generous, and a typo in the allowlist must not be able to boil water.

3. AN ALLOWLIST HE WRITES, and it is empty until he does. Same doctrine as house.WATCH:
   which lights matter is not something this file can know. It lives in `var/`, NOT in the
   profile and NOT in this module, because everything committed is exported and his entity
   ids are his house's floor plan.

4. ON REQUEST ONLY. She may act in a turn he is present for, and not otherwise. This is his
   call — "on-request only with autonomous action as a separate, later, off-by-default
   arming" — and it is enforced structurally rather than by hoping the autonomous lanes
   never reach for the tool: the same `_seconds_since_he_spoke()` clock the room veto reads,
   because a second "when did he last speak" would be two truths about one fact.

WHY AN ALLOWLIST AT ALL, when today's lesson was that a hand-written list is a bad guard.
Because the alternative is worse. Home Assistant's own Assist exposure looked like the
better boundary — it lives where the house lives and the owner edits it in a UI — until it
was read: `expose_new` defaults ON, so 44 entities were already exposed that nobody chose,
including `switch.kettle_start`. A boundary that admits new things by default is not a
boundary. Guard 2 is the structural one; the list is what makes it specific, and guard 3
means an empty list denies everything rather than allowing it.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from . import client as _client

# ── THE DOMAINS, AND NOTHING ELSE EVER ───────────────────────────────────────────────
# Not configurable, on purpose. Every other guard here is something a person can widen;
# this one is the floor under all of them. Adding a domain is a code change with a gate to
# argue with, which is the correct amount of friction for "she can now operate the locks".
ACTABLE_DOMAINS: Tuple[str, ...] = ("light", "fan")

# What a light may be asked to be. Colours are named rather than free-form RGB because she
# speaks in words and because "red" is checkable where a triple is not.
COLOURS: Dict[str, Tuple[int, int, int]] = {
    "red": (255, 0, 0), "orange": (255, 140, 0), "amber": (255, 191, 0),
    "yellow": (255, 235, 60), "green": (0, 200, 60), "teal": (0, 190, 170),
    "blue": (30, 90, 255), "indigo": (75, 0, 200), "purple": (150, 40, 220),
    "pink": (255, 90, 170), "warm": (255, 180, 110), "white": (255, 255, 255),
}

def present_window() -> Optional[float]:
    """How recently he must have spoken for an act to count as ON REQUEST.

    READ from telemetry.body.ROOM_VETO_S rather than restated. The first cut kept a
    fallback `15 * 60` for when the import failed, and G-HOUSE-HANDS refused it: a second
    copy of a number is a second truth about one fact, and this one decides whether she may
    operate his house. If the module that owns it cannot be read, this returns None and the
    act refuses — the safe direction, and one fewer number to keep in step.
    """
    try:
        from harness.telemetry.body import ROOM_VETO_S
        return float(ROOM_VETO_S)
    except Exception:
        return None


def armed() -> bool:
    """SP_HOUSE_HANDS — mapped in serve.py, DEFAULT OFF. See docs/OFF-BY-DEFAULT.md."""
    return os.environ.get("SP_HOUSE_HANDS", "0") == "1"


def _allow_path() -> str:
    return os.environ.get("SP_HOUSE_ALLOW", "")


def allow() -> Dict[str, str]:
    """{spoken name: entity_id}. EMPTY when unset, unreadable or malformed.

    Empty means nothing is actable, which is the safe direction and the only one a file
    that may not exist can be read in. A name is what he would SAY — "the lamp" — because
    she talks to him in words and an entity id is not one.
    """
    p = _allow_path()
    if not p or not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for name, eid in raw.items():
        if isinstance(name, str) and isinstance(eid, str) and "." in eid:
            out[name.strip().lower()] = eid.strip()
    return out


def _domain(entity_id: str) -> str:
    return (entity_id or "").split(".", 1)[0]


def resolve(what: str) -> Tuple[str, str]:
    """(entity_id, why). `why` is a SENTENCE when it refuses and "" when it does not.

    BOTH GUARDS, ALWAYS. The name has to be in his list AND the id has to be in an actable
    domain — the second is not redundant, it is what stops a mistyped or mischosen row in
    the list from reaching a kettle.
    """
    a = allow()
    if not a:
        return "", "nothing in the house is set up for me to touch yet"
    key = (what or "").strip().lower()
    eid = a.get(key)
    if not eid:
        for k, v in a.items():                  # a forgiving second pass, still list-bound
            if key and (key in k or k in key):
                eid, key = v, k
                break
    if not eid:
        return "", ("I do not have anything called %r — I can reach: %s"
                    % (what, ", ".join(sorted(a)) or "nothing"))
    if _domain(eid) not in ACTABLE_DOMAINS:
        # Not reachable even though he listed it: the domain floor is not negotiable.
        return "", ("%s is not something I am allowed to operate — only %s"
                    % (what, " and ".join(ACTABLE_DOMAINS)))
    return eid, ""


def _present_now() -> Optional[float]:
    """Seconds since his last turn, via the ONE clock that already answers this."""
    try:
        from harness.telemetry.body import _seconds_since_he_spoke
        return _seconds_since_he_spoke()
    except Exception:
        return None


def _call(service: str, entity_id: str, data: Optional[dict] = None) -> Tuple[bool, str]:
    """POST to HA. NEVER RAISES — same contract as client._get, for the same reason."""
    c = _client.HA()
    if not c.token:
        return False, "no Home Assistant token — the framework is off"
    domain = _domain(entity_id)
    body = dict(data or {})
    body["entity_id"] = entity_id
    try:
        req = urllib.request.Request(
            c.base + "/api/services/%s/%s" % (domain, service),
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": "Bearer " + str(c.token),
                     "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=_client.TIMEOUT_S) as r:
            r.read()
        return True, ""
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, ("Home Assistant refused the token (HTTP %d) — it may have been "
                           "revoked" % e.code)
        return False, "Home Assistant answered HTTP %d" % e.code
    except urllib.error.URLError as e:
        return False, "cannot reach Home Assistant at %s (%s)" % (c.base, e.reason)
    except (OSError, ValueError) as e:
        return False, "Home Assistant gave something unreadable (%s)" % type(e).__name__


def act(what: str, on: Optional[bool] = None, colour: str = "",
        brightness: Optional[int] = None, _present: Optional[float] = None
        ) -> Dict[str, Any]:
    """Do one thing to one allowed entity. The single door — every guard is checked here.

    Returns {"ok", "why", ...}. `why` is a sentence she can say. Never raises.
    """
    out: Dict[str, Any] = {"ok": False, "what": what, "why": ""}
    if not armed():
        out["why"] = "I am not set up to touch anything in the house"
        return out
    window = present_window()
    seen = _present if _present is not None else _present_now()
    if window is None or seen is None or seen > window:
        # ON REQUEST ONLY. Not a policy about politeness — an autonomous lane reaching this
        # tool is a different product, and it gets its own arming when it is wanted.
        out["why"] = "I only do that while you are here and asking"
        out["not_present"] = True
        return out
    eid, why = resolve(what)
    if not eid:
        out["why"] = why
        return out
    out["entity_id"] = eid
    data: Dict[str, Any] = {}
    if colour:
        rgb = COLOURS.get(colour.strip().lower())
        if not rgb:
            out["why"] = ("I do not know the colour %r — I know: %s"
                          % (colour, ", ".join(sorted(COLOURS))))
            return out
        if _domain(eid) != "light":
            out["why"] = "%s is not a light, so it has no colour" % what
            return out
        data["rgb_color"] = list(rgb)
        on = True if on is None else on
    if brightness is not None:
        try:
            b = max(1, min(100, int(brightness)))
        except (TypeError, ValueError):
            out["why"] = "brightness wants a number from 1 to 100"
            return out
        if _domain(eid) != "light":
            out["why"] = "%s is not a light, so it has no brightness" % what
            return out
        data["brightness_pct"] = b
        on = True if on is None else on
    if on is None:
        out["why"] = "on or off?"
        return out
    ok, why = _call("turn_on" if on else "turn_off", eid, data if on else None)
    out["ok"], out["why"], out["on"] = ok, why, bool(on)
    if ok:
        out["did"] = ("turned %s on" % what) if on else ("turned %s off" % what)
        if colour:
            out["did"] += " (%s)" % colour
        if brightness is not None:
            out["did"] += " at %d%%" % data["brightness_pct"]
    return out


def reachable() -> List[str]:
    """The names he has actually allowed, for telling him what she can reach."""
    return sorted(allow()) if armed() else []
