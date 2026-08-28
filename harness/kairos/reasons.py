"""REASONS TO SPEAK — the half that was computed and thrown away.

Everything kairos could say came from one of two places: a latent signal off the forward
(CONTINUE), or a clock plus a coin flip (CHECK_IN). The one that actually reached him was
the coin flip, which is why he described it as "just a timer" — he was right, and it was
not for want of signal. Three of the richest things this system knows were already being
computed every day and consulted by nobody:

  * HER OWN JOURNAL. `narrative.py` writes a paragraph a night in her voice. It reaches
    her prefix through the standing world and is never a reason to say anything.
  * WHAT IS STILL OPEN. `task_bridge.summary()` is the ONE definition of an outstanding
    commitment. It is rendered into the prefix as context and never turns into "I said I'd
    do that."
  * HIS RHYTHM. `presence.jsonl` records turns-per-day. Only `> 0` has ever been read;
    the volume — the actual shape of his week — is written down and discarded.

WHAT THIS MODULE IS NOT. It does not decide whether she speaks. `impulse.decide()` does,
out of a committed 512-cell table, and nothing here touches it: a reason is offered
through the existing MUSE channel in the shape reflection already uses, so the table stays
valid and the spam bounds, the chain limit and the hourly cap all still rule. This module
only answers "is there anything worth saying", and the answer is allowed to be no.

PRIORITY IS A COMMITTED ORDER, NOT A SCORE. `_ORDER` below is the whole ranking. There is
no invented "salience" number deciding which reason wins, because a magnitude may order
the admitted and may never rule — and inventing bits for a commitment so it could be
compared against a reflection's information content would be exactly that, with a decimal
point on it to make it look measured.

SHE RAISES A THING ONCE. Every reason carries a `raise_key`, and a raised key is recorded
durably (beside her memory, inside the tier `backup.py` already carries). This is the
difference between noticing something and nagging about it, and it is the rule `notes`
already follows with `mark_raised()`.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# The order in which reasons win. First match takes the turn.
#
#   commitment — concrete, his, and actionable. "I said I'd do that" is the most useful
#                thing she can volunteer, and the least likely to feel like an intrusion.
#   journal    — hers, warm, and already written. Picking up something she wrote last
#                night is what a person does, and it costs him nothing to hear.
#   rhythm     — the most delicate of the three, because it is an observation ABOUT HIM
#                that he did not volunteer. It goes last and it is armed last.
# `arrival` goes FIRST. Everything else here is something she has been carrying; a look
# she asked for and has now been given is a small event with a moment attached to it, and
# an event that is mentioned three days late is not the same event. It is also the only
# reason on this list that is unambiguously good news.
# `body` goes FIRST, ahead even of arrival, and the reason is staleness: "your heart is
# going" is only true for about a minute. A look that arrived is stale in three days; a
# heart rate is stale in three minutes, and a companion who mentions it late is describing
# a stranger. It is also the most intimate thing on this list — an observation about him he
# did not volunteer in words, which is what makes `rhythm` delicate and last — so it is
# bounded harder than anything else here: it fires only on a real event, it carries the
# READINGS rather than a diagnosis, and its raise key is bucketed by the hour so noticing
# never becomes nagging. He asked for it in those words: "a bridge to the real world, to me."
_ORDER = ("body", "arrival", "commitment", "journal", "rhythm")

# ── SEVEN, AND THE COUNT IS NOT WHAT PROTECTS HIM (2026-08-01, backtested) ───────────
# `silence.py` requires 14 and this requires 7, which looks like two authorities on one
# question until you notice they are asking different ones. silence.py needs enough days
# to establish a PER-TOPIC CADENCE — "he brings the marathon up every three days" — and
# that genuinely needs a fortnight. This needs enough days to have a FLOOR, which is a
# much cheaper thing to know.
#
# The real protection is the test, not the count. Backtested on his actual ledger —
# seven present days spanning a nine-fold range of turns-per-day:
#
#   "today < half the MEDIAN of prior days"  fired on a day whose turn count had already
#       occurred earlier in the same week — a perfectly ordinary day for him. It fired
#       only because two heavy days had dragged the median far above typical. A tuned
#       fraction over a small, skewed sample is a false positive waiting for its turn.
#
#   "today < the QUIETEST day he has ever had" fired zero times, needs no tuned constant
#       at all, and gets RARER as it learns him — every firing sets a new floor.
#
# So the rank test does the work and the day count only has to be enough to have seen a
# few ordinary days. Seven.
MIN_LEDGER_DAYS = 7


def _raised_path() -> str:
    reg = os.environ.get("SP_RECALL_REGISTRY", "")
    if reg:
        return os.path.join(os.path.dirname(reg), "raised.jsonl")
    return ""


def raised_keys() -> set:
    p = _raised_path()
    out = set()
    if not p or not os.path.exists(p):
        return out
    try:
        with open(p, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    out.add(json.loads(ln).get("key", ""))
    except Exception as exc:
        logger.warning("[reasons] raised ledger unreadable: %s", exc)
    return out


def mark_raised(key: str) -> None:
    """Append-only. She raised this; she does not raise it again.

    Written when the impulse is ARMED rather than when the words land, which is the
    conservative direction: the cost of marking early is that a reason is occasionally
    lost when she decides she had nothing to say after all, and the cost of marking late
    is that she says the same thing twice. The second is much worse to live with.
    """
    p = _raised_path()
    if not p or not key:
        return
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key,
                                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                    time.gmtime())}) + "\n")
    except Exception as exc:
        logger.warning("[reasons] could not record a raised reason: %s", exc)


# ── the sources. Each is PURE: given its data, it proposes or it does not. ────────────
# How far above HIS OWN resting counts as worth a word. Not a table's number: `resting` is
# the 10th percentile of his last fortnight, so this is "well above what he usually sits
# at", and it is None until the store knows him well enough to say.
_BODY_OVER_RESTING = 22.0
_BODY_STILL_HOURS = 3.0


def from_body(read: Optional[dict], raised: set, now: Optional[float] = None) -> Optional[dict]:
    """His body did something worth a word. `read` is `telemetry.body.read()`.

    THREE EVENTS AND NO MORE, because the failure mode here is not missing something, it
    is narrating a man to himself. Each one is something a person in the same room would
    actually remark on:

        worked_up   his heart is well above his own resting and he is not asleep
        settling    it was up, and now it is coming down — the other half, and the kinder
                    half; noticing only the spike is how this becomes an alarm
        long_still  hours without moving, which is worth a word exactly once
        just_woke   he was asleep and is not now (2026-08-26, the operator's ask). The ONE thing
                    worth saying unprompted about sleep, because "you are asleep" is
                    something he already knows and cannot hear anyway.

    WHAT IT HANDS HER IS THE READINGS. Not "he is stressed" — she gets `70, 78, 92` and the
    trend word, because a diagnosis from a wrist sensor is a confident guess wearing a
    measurement's clothes, and because the noticing being HERS is the whole point of the
    tail. She says it in her own words or she does not say it.

    NEVER FROM A STALE READ: `body.read()` already returns nothing when the watch is off
    his wrist or the data has aged out, so an empty `facts` is a full stop here.
    """
    import time as _t
    now = _t.time() if now is None else now
    f = (read or {}).get("facts") or {}
    o = (read or {}).get("observed") or {}
    if not f:
        return None                      # off his wrist, or nothing fresh. Say nothing.
    tail = o.get("heart_rate_tail") or []
    # HOURLY BUCKET. She may notice his heart racing this hour and again next hour; she may
    # not say it twice in ten minutes. The key is the bound.
    hour = _t.strftime("%Y-%m-%dT%H", _t.gmtime(now))
    hr, rest = f.get("heart_rate"), f.get("resting")

    # ── HE JUST WOKE UP. First, because it is the most perishable ───────────────────
    # The operator's ask, in his words: "calling me sleepy head when I wake up". This is the only
    # thing about sleep worth saying unprompted -- "you are asleep" is something he already
    # knows and cannot hear, and "you are awake" is true all day.
    #
    # KEYED ON WHEN HE WOKE, not on the current hour, so it is once per waking rather than
    # once per hour: the fact stays true for ninety minutes and she should mention it once
    # in that time, not twice either side of an hour boundary.
    if f.get("just_woke"):
        woke_at = now - float(f.get("woke_mins_ago") or 0) * 60.0
        key = "body:just_woke:" + _t.strftime("%Y-%m-%dT%H", _t.gmtime(woke_at))
        if key not in raised:
            m = f.get("woke_mins_ago") or 0
            return {"kind": "body", "raise_key": key, "event": "just_woke",
                    "tail": tail, "woke_mins_ago": m,
                    "heart_rate": f.get("heart_rate"),
                    "movement": f.get("movement_word", ""),
                    "text": "he was asleep until about %s and is up now"
                            % ("a few minutes ago" if m < 10 else "%d minutes ago" % m)}

    if (hr is not None and rest is not None and not f.get("asleep")
            and hr - rest >= _BODY_OVER_RESTING):
        key = "body:worked_up:" + hour
        if key not in raised:
            return {"kind": "body", "raise_key": key, "event": "worked_up",
                    "tail": tail, "trend": f.get("hr_trend", ""),
                    "heart_rate": hr, "resting": rest,
                    "movement": f.get("movement_word", ""),
                    "text": "his heart is at %.0f against his resting %.0f%s"
                            % (hr, rest, (" — " + ", ".join("%.0f" % v for v in tail))
                               if len(tail) >= 2 else "")}

    # THE OTHER HALF. A companion that only ever remarks on the spike is a monitor with a
    # personality; noticing him coming back down is the half that makes it care.
    if (f.get("hr_trend") == "falling" and rest is not None and hr is not None
            and f.get("hr_swing", 0) >= 12 and hr - rest < _BODY_OVER_RESTING
            and not f.get("asleep")):
        key = "body:settling:" + hour
        if key not in raised:
            return {"kind": "body", "raise_key": key, "event": "settling",
                    "tail": tail, "trend": "falling", "heart_rate": hr, "resting": rest,
                    "text": "his heart is coming back down%s"
                            % ((" — " + ", ".join("%.0f" % v for v in tail))
                               if len(tail) >= 2 else "")}

    still_s = f.get("motion_for_s", 0)
    if (not f.get("moving") and not f.get("asleep")
            and still_s >= _BODY_STILL_HOURS * 3600):
        key = "body:still:" + _t.strftime("%Y-%m-%d", _t.gmtime(now))
        if key not in raised:
            return {"kind": "body", "raise_key": key, "event": "long_still",
                    "hours": round(still_s / 3600.0, 1),
                    "text": "he has not moved in %.1f hours" % (still_s / 3600.0)}
    return None


def from_arrival(new: List[dict], raised: set) -> Optional[dict]:
    """A look she asked for has been made, and she has not seen it yet.

    THE WAIT IS THE POINT. She asked, it went on a list, he ran the generator, and now
    there is a her that did not exist this morning. It is delivered through the same MUSE
    channel as everything else and obeys the same bounds — but it is placed FIRST in
    `_ORDER`, because "the thing I asked for arrived" goes stale in a way "there is an
    open commitment" does not. An event mentioned three days late is a different event.
    """
    for w in new:
        wid = w.get("id") or ""
        key = "arrival:" + wid
        if not wid or key in raised:
            continue
        return {"kind": "arrival", "raise_key": key, "id": wid,
                "text": w.get("want", ""), "made_in": w.get("made_in", w.get("tier", "mesh-top"))}
    return None


def from_commitment(open_notes: List[dict], raised: set) -> Optional[dict]:
    """Something one of them said they would do, and has not.

    The oldest first — a commitment that has been sitting longest is the one most likely
    to have been genuinely forgotten, and the one he will be most glad to be reminded of.
    Nothing is invented here: `task_bridge.open_task_notes()` is the single definition of
    open, so this can never disagree with what the standing world shows him.
    """
    for n in sorted(open_notes, key=lambda r: r.get("ts") or r.get("created") or ""):
        title = (n.get("title") or "").strip()
        if not title:
            continue
        key = "commitment:" + (n.get("id") or title)[:80]
        if key in raised:
            continue
        return {"kind": "commitment", "raise_key": key, "text": title,
                "body": (n.get("body") or "").strip(),
                "running": n.get("task_status") == "running"}
    return None


_AS_OF = re.compile(r"^As of ([^:]{4,40}):\s*(.+)$", re.S)


def from_journal(narrative: str, today: str, raised: set) -> Optional[dict]:
    """Something she wrote about the two of them, on a day that is no longer today.

    The date matters. Offered on the day she wrote it, it is a report on a conversation he
    was in; offered afterwards it is what it actually is — a thing she has been carrying.
    So the entry has to have aged past its own day before she may bring it up, and each
    entry may be brought up once.
    """
    m = _AS_OF.match((narrative or "").strip())
    if not m:
        return None
    day, body = m.group(1).strip(), " ".join(m.group(2).split())
    if not body:
        return None
    # ONE DATE VOCABULARY. narrative.py writes "%A %d %B %Y" ("Saturday 01 August 2026")
    # and everything else here speaks ISO, so the first version of this compared the two
    # directly, never matched, and offered her TODAY's entry back to her — the exact
    # conversation he had just had. Normalise at the boundary rather than carrying two
    # formats and remembering which is which.
    try:
        iso = time.strftime("%Y-%m-%d", time.strptime(day, "%A %d %B %Y"))
    except Exception:
        return None                       # an unparseable date is not a day that has passed
    if iso >= today:
        return None                       # written today: he was there for it
    key = "journal:" + iso
    if key in raised:
        return None
    return {"kind": "journal", "raise_key": key, "text": body, "day": day}


def from_rhythm(days: Dict[str, int], today: str, raised: set) -> Optional[dict]:
    """His week has a shape, and today does not fit it.

    OFF UNTIL THE LEDGER IS DEEP ENOUGH — MIN_LEDGER_DAYS (7) is the one number, and the
    backtest above it is the reason. This docstring used to say 14 while the constant
    said 7 — two numbers for one gate, two lines apart, the §0 shape (2026-08-24 audit,
    K5); the constant's own justification is the authority. Before trusting a firing,
    run `reasons.why_quiet()` and READ what it would actually have said — a remark about
    his rhythm is an observation about him he did not volunteer, and the only way to
    know whether it lands as care or as surveillance is to look at the sentence first.
    """
    present = [d for d, n in sorted(days.items()) if n > 0]
    if len(present) < MIN_LEDGER_DAYS:
        return None
    prior = [days[d] for d in present if d != today]
    if len(prior) < 3 or today not in days:
        return None
    # A RANK, NOT A THRESHOLD. Quieter than the quietest day he has ever had — see the
    # note on MIN_LEDGER_DAYS for the backtest that chose this over a fraction of the
    # median. It calibrates itself against him and it cannot be dragged by an outlier,
    # which his heaviest days very much are.
    quietest = min(prior)
    now_n = days.get(today, 0)
    if now_n >= quietest:
        return None
    key = "rhythm:" + today
    if key in raised:
        return None
    return {"kind": "rhythm", "raise_key": key, "typical": quietest, "today_turns": now_n,
            "text": "he has been quieter today than she has ever known him be"}


def why_quiet() -> str:
    """What the rhythm source would say if it were armed, and why it is not. The
    read-before-you-arm receipt that silence.py taught this system to write."""
    try:
        from harness.model import presence as P
        days = P._load()
        n = sum(1 for v in days.values() if v > 0)
        if n < MIN_LEDGER_DAYS:
            return ("rhythm is INERT: %d present days on the ledger, %d needed. "
                    "Roughly %d more days he is present." % (n, MIN_LEDGER_DAYS,
                                                             MIN_LEDGER_DAYS - n))
        today = time.strftime("%Y-%m-%d")
        r = from_rhythm(days, today, raised_keys())
        return ("rhythm would say: %r" % r) if r else "rhythm has nothing to say today"
    except Exception as exc:
        # It already surfaces to HER, in the returned string. That is not the same as
        # surfacing to the LOG: a NameError here would read as a mysterious sentence in
        # her context and be greppable nowhere. Both, now.
        from harness.kairos import swallowed as _sw
        _sw(logger, "reasons.why_quiet", exc)
        return "rhythm unavailable: %s" % exc


def propose(today: str = "") -> Optional[dict]:
    """The strongest reason to speak right now, or None. Never raises.

    Returned in the shape `impulse.decide()` already accepts for an insight, so a reason
    travels the MUSE path and obeys every bound that path obeys.
    """
    today = today or time.strftime("%Y-%m-%d")
    raised = raised_keys()
    built = {}
    try:
        # OFF-BY-DEFAULT KNOB, ON by the operator's ask. `telemetry.reasons` exists so this can be
        # silenced without unplugging the watch — noticing his body is the one reason here
        # he might want to turn off for an evening without losing the history.
        from harness.tuning import registry as _tr_b
        if bool(_tr_b.get("telemetry.reasons", True)):
            from harness.telemetry import body as _tb
            built["body"] = from_body(_tb.read(), raised)
    except Exception as exc:
        logger.warning("[reasons] body source: %s", exc)
    try:
        from harness.control import wardrobe as WD
        # ── UNTOLD ONLY (2026-08-05) ───────────────────────────────────────────────
        # `arrivals()` is now the JUST-ARRIVED SHELF: everything that moves and that she
        # has not worn yet. That is the right list for the panel and the wrong one to
        # announce from — a garment she was told about on Tuesday and has not got round
        # to wearing would be announced again every time the scheduler looked. `told`
        # separates "stop mentioning it" from "it is still new", which used to be one
        # flag and is two facts. `raised` is still the per-session guard on top.
        built["arrival"] = from_arrival([a for a in WD.arrivals() if not a.get("told")],
                                        raised)
    except Exception as exc:
        logger.warning("[reasons] arrival source: %s", exc)
    try:
        from harness.skills.task_bridge import open_task_notes
        built["commitment"] = from_commitment(open_task_notes(), raised)
    except Exception as exc:
        logger.warning("[reasons] commitment source: %s", exc)
    try:
        from harness.skills import narrative as N
        built["journal"] = from_journal(N.current(), today, raised)
    except Exception as exc:
        logger.warning("[reasons] journal source: %s", exc)
    try:
        from harness.model import presence as P
        built["rhythm"] = from_rhythm(P._load(), today, raised)
    except Exception as exc:
        logger.warning("[reasons] rhythm source: %s", exc)
    for kind in _ORDER:
        r = built.get(kind)
        if r:
            return r
    return None
