"""The bridge: Home Assistant entities -> the telemetry store, through the existing door.

WHAT CROSSES, AND WHY IT IS A SHORT LIST. Home Assistant knows hundreds of things and
almost none of them belong in his body's history. The rule for adding a row here is that
**no sensor we can reach produces it**. Battery, steps and charging are already posted by
our own agent, so mapping them would give every reading two spellings and leave the seam
picking between them — the two-copies bug this codebase keeps paying for.

That leaves the things that are computed rather than measured, which is exactly what a
smart-home server has and a wrist does not.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from harness.telemetry import ingest
from . import client as _client

# ── THE TABLE. Matched by SUFFIX, never by whole entity id ────────────────────────────
# The Home Assistant companion app names its entities after the device, so his phone's
# sleep sensor is `sensor.sm_s908e_sleep_confidence` and a different phone would be
# something else entirely. Hard-coding the id would mean the integration silently stopped
# working the day he changed handsets — and "silently" is the part that matters, because
# a missing row looks exactly like a man who is awake.
#
#   (entity suffix, kairos kind, source, converter)
MAPPINGS: Tuple[Tuple[str, str, str, str], ...] = (
    # THE WHOLE REASON THIS FRAMEWORK EXISTS. Google's Sleep API, ~10 minute cadence,
    # calibrated against rather more sleeping people than we have.
    ("_sleep_confidence", "sleep_confidence", "phone", "percent"),
    # Google's Activity Recognition. Recorded under its OWN kind rather than mapped onto
    # `motion`, because `motion` from the phone is deliberately not a claim about HIM
    # (harness/telemetry/body.py: a phone on a desk is not a man sitting still) and reusing
    # the name would smuggle a phone's opinion into a body fact.
    ("_detected_activity", "activity", "phone", "activity"),
    ("_activity", "activity", "phone", "activity"),
)

# HA's Android activity vocabulary -> ours. `tilting` is the phone being picked up, which
# is not locomotion; `unknown` is dropped entirely, because a sensor saying "I do not know"
# must not become a row that reads as knowledge.
_ACTIVITY = {
    "still": "still", "tilting": "still",
    "walking": "walking", "on_foot": "walking",
    "running": "running", "on_bicycle": "cycling",
    "in_vehicle": "vehicle",
}

# How stale a Home Assistant reading may be before we stop dating it honestly. See
# `poll_once`: the reading is recorded with ITS OWN timestamp, so this is not about
# freshness (the seam decides that) but about the backdating bound in ingest.record.
_MAX_AGE_S = 2 * 3600

# entity_id -> the `last_updated` we last wrote. Deliberately in memory and deliberately
# not persisted: a gateway restart costs at most one duplicated reading, where a state file
# would be one more thing that can disagree with the store it describes.
_SEEN: Dict[str, str] = {}


def _convert(kind_conv: str, raw: Any) -> Tuple[Optional[Any], str]:
    """(value, why-not). Returns (None, reason) for anything that should not be recorded."""
    s = str(raw).strip().lower()
    if s in ("", "unknown", "unavailable", "none"):
        # HA says this for a sensor that has not reported yet or whose integration is down.
        # It is not a value and it must never become one.
        return None, "the entity has no value yet (%s)" % (s or "empty")
    if kind_conv == "percent":
        try:
            v = float(s)
        except ValueError:
            return None, "not a number: %r" % raw
        return (v, "") if 0.0 <= v <= 100.0 else (None, "%s is outside 0..100" % v)
    if kind_conv == "activity":
        v = _ACTIVITY.get(s)
        return (v, "") if v else (None, "activity %r is not one we record" % s)
    return None, "no converter named %r" % kind_conv


def discover(states: List[dict]) -> List[dict]:
    """Which entities this framework would read, and what each becomes.

    Separate from the poll so the panel and the gate can ask "what would you take?" without
    writing anything. An integration that can only be understood by letting it run is one
    nobody audits."""
    found: List[dict] = []
    claimed = set()
    for suffix, kind, source, conv in MAPPINGS:
        for st in states or ():
            eid = str(st.get("entity_id") or "")
            if not eid.endswith(suffix) or eid in claimed:
                continue
            claimed.add(eid)
            value, why = _convert(conv, st.get("state"))
            measured = _client.measured_at_of(st)
            found.append({
                "entity_id": eid, "kind": kind, "source": source,
                "raw": st.get("state"), "value": value, "why": why,
                # NOT `last_updated` -- see client.measured_at_of. That field is the age of
                # the row in Home Assistant's memory, and after a restart every stale sensor
                # in the house looks brand new.
                "measured_at": measured,
                "last_updated": st.get("last_updated") or "",
                "friendly": (st.get("attributes") or {}).get("friendly_name") or eid,
            })
    return found


def poll_once(cl: Optional[_client.HAClient] = None,
              now: Optional[float] = None) -> Dict[str, Any]:
    """Read Home Assistant once and write anything new. NEVER RAISES.

    Returns a report rather than a count, because "nothing was written" has several very
    different causes — off, unreachable, nothing new, nothing mapped — and a caller that
    cannot tell them apart will read a healthy quiet poll as a failure."""
    now = time.time() if now is None else now
    out: Dict[str, Any] = {"ok": False, "stored": 0, "seen": 0, "skipped": [], "why": ""}

    if not _client.configured():
        out["why"] = "no Home Assistant token — the framework is off"
        return out

    cl = cl or _client.HAClient()
    states, why = cl.states()
    if why:
        out["why"] = why
        return out

    out["ok"] = True
    for f in discover(states):
        out["seen"] += 1
        eid = f["entity_id"]
        if f["value"] is None:
            out["skipped"].append({"entity_id": eid, "why": f["why"]})
            continue
        # ONLY ON CHANGE. Sleep confidence refreshes every ten minutes; polling faster than
        # that is right (it bounds how late we notice) but re-recording the same reading
        # each time would turn one measurement into a dozen and make the history lie about
        # how much was actually observed.
        #
        # Keyed on the MEASUREMENT time and the value, not on `last_updated` -- otherwise a
        # Home Assistant restart re-stamps every entity and the next poll writes the whole
        # house again as if it had all just been measured.
        stamp = "%s@%s" % (f["value"], f.get("measured_at"))
        if _SEEN.get(eid) == stamp:
            continue

        measured = f.get("measured_at")
        if measured is None:
            # No usable clock anywhere on the entity. Recording it would date somebody
            # else's reading to this instant, which is the whole defect this guards.
            out["skipped"].append({"entity_id": eid,
                                   "why": "no measurement time on the entity"})
            continue
        if now - measured > _MAX_AGE_S:
            out["skipped"].append({"entity_id": eid,
                                   "why": "the reading is %d min old — too stale to date "
                                          "honestly" % int((now - measured) / 60)})
            _SEEN[eid] = stamp
            continue

        # HOME ASSISTANT'S OWN CLOCK, not ours. A nine-minute-old sleep confidence stamped
        # on arrival would be treated as fresh for nine minutes longer than it deserves,
        # and every freshness decision downstream would be made against the wrong number.
        r = ingest.record([{"kind": f["kind"], "value": f["value"]}],
                          source=f["source"], measured_at=measured)
        out["stored"] += int(r.get("stored") or 0)
        if r.get("held"):
            out["skipped"].append({"entity_id": eid, "why": "held: off the record"})
            # NOT marked seen. Anon mode holds rather than queues, but the next poll after
            # he comes back on the record should still be allowed to write the CURRENT
            # value — held is not the same as handled.
            continue
        for rej in (r.get("rejected") or ()):
            out["skipped"].append({"entity_id": eid, "why": rej.get("why")})
        _SEEN[eid] = stamp

    return out


def status() -> Dict[str, Any]:
    """What the panel and the gate need, in one call. NEVER RAISES."""
    out: Dict[str, Any] = {"configured": _client.configured(), "url": _client.url(),
                           "alive": False, "why": "", "entities": []}
    if not out["configured"]:
        out["why"] = "no token — Home Assistant is off"
        return out
    cl = _client.HAClient()
    ok, why = cl.alive()
    out["alive"], out["why"] = ok, why
    if not ok:
        return out
    states, why2 = cl.states()
    if why2:
        out["why"] = why2
        return out
    out["entities"] = discover(states)
    out["total_entities"] = len(states)
    return out
