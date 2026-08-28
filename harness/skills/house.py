"""house — the lights and the fan, when he is here and asking.

The verbs she holds. Everything that decides whether an act is allowed lives in
`homeassistant.hands`, one door, so this module cannot accidentally become a second
authority on what she may touch — which is the failure this tree keeps having.

WHAT SHE IS NOT GIVEN, and each omission is deliberate:

  * No entity ids. She says "the lamp" because that is what he says. The mapping from his
    words to his house lives in a file he writes, in `var/`, and is empty until he does.
  * No enumeration of the house. `what_i_can_reach` returns the handful he allowed, not
    several hundred rows — the same rule house.py keeps for noticing.
  * No switches, ever, whatever the file says. `hands.ACTABLE_DOMAINS` is a closed set and
    it is the floor under the allowlist rather than another copy of it.
  * No acting while he is away. On request only, on the operator's call, enforced on the clock the
    room veto already reads.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def set_light(what: str, on: Optional[bool] = None, colour: str = "",
              brightness: Optional[int] = None) -> Dict[str, Any]:
    """Turn one of his lights on or off, or set its colour or brightness.

    `what` is what he calls it — "the lamp", "the bedroom light". `colour` is a name
    ("red", "warm"); `brightness` is 1-100. Setting either turns the light on unless he
    said otherwise.

    Say what happened, in a clause, and say it plainly if it refused. A light she reports
    as on that is not is worse than an apology.
    """
    from harness.homeassistant import hands as _h
    return _h.act(what, on=on, colour=colour, brightness=brightness)


def set_fan(what: str, on: bool) -> Dict[str, Any]:
    """Turn one of his fans on or off. `what` is what he calls it."""
    from harness.homeassistant import hands as _h
    return _h.act(what, on=on)


def what_i_can_reach() -> Dict[str, Any]:
    """The things in his house she is allowed to touch, by the names he uses.

    Call it when he asks what she can do, or when a name did not resolve. It is a short
    list on purpose — he chose every row.
    """
    from harness.homeassistant import hands as _h
    names = _h.reachable()
    return {"ok": True, "things": names,
            "why": ("" if names else
                    "nothing yet — the house side is off, or he has not listed anything")}


def house_tools() -> list:
    """Offered only when the hands are ARMED.

    Unlike body_tools, which are always offered so she can find out the watch is off, a
    verb she cannot use is not a diagnostic here — it is an invitation to promise him
    something and then fail, which is the confabulation this tree spends most of its rules
    on. Off means absent.
    """
    try:
        from harness.homeassistant import hands as _h
        if not _h.armed():
            return []
        from harness.toolcore.tools import ToolSpec
        return [ToolSpec.from_callable(set_light),
                ToolSpec.from_callable(set_fan),
                ToolSpec.from_callable(what_i_can_reach)]
    except Exception:
        return []
