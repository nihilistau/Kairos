"""HIS BODY, as something she can ASK about rather than only be told.

WHY THIS EXISTS, and it is a gap found the hard way. The telemetry framework hands her a
per-turn system row — but only when `body.present()` has something to say, which is
deliberately rare: silence is the default, because a companion narrating a heart rate every
turn is a monitor. The consequence nobody noticed until he asked her directly was that when
NOTHING is happening she has no way to find out that nothing is happening. Told "I've set it
up under body", she ran `list_dir body`, got "not a directory", and said so — because a
directory was the only mental model available to her.

So: a tool. Two of them, and the split matters.

  `how_is_he()`   — what his body is doing NOW. The thing to call when she wonders.
  `his_day()`     — the shape of the last few hours, for "have you slept at all?"

WHAT THESE DO NOT DO. They do not hand her the feed. `read()` already separates what was
MEASURED from what was CONCLUDED and these keep that separation, because the whole doctrine
of the telemetry package is that "his heart is 96" and "he is stressed" are different kinds
of claim. Everything here is also allowed to answer "I do not know", and says so in words,
because the alternative is her inventing a number and it is his body.
"""

from __future__ import annotations

from typing import Any, Dict, List


def _fresh_words(age_s: float) -> str:
    """How old a reading is, in the way a person would say it."""
    if age_s < 90:
        return "just now"
    if age_s < 3600:
        return "%d minutes ago" % int(age_s / 60)
    if age_s < 7200:
        return "an hour ago"
    return "%d hours ago" % int(age_s / 3600)


def how_is_he() -> Dict[str, Any]:
    """What his body is doing right now — heart, movement, whether he seems awake.

    Call this when you want to know how he is and he has not said. It answers from his
    watch and his phone, and it will tell you plainly when it does not know: the watch
    comes off, the phone gets left on a desk, and a guess about his body dressed up as a
    reading is worse than nothing.

    `observed` is what was MEASURED. `reading` is what was INFERRED from it and is always
    hedged — his word outranks all of it the moment he says otherwise.
    """
    try:
        from harness.telemetry import body as _b
    except Exception as exc:                       # pragma: no cover - import guard
        return {"ok": False, "why": "the telemetry framework is not loaded (%s)"
                                    % type(exc).__name__}
    try:
        r = _b.read()
    except Exception as exc:                       # never raises at her
        return {"ok": False, "why": "could not read his body just now (%s)"
                                    % type(exc).__name__}

    facts = r.get("facts") or {}
    obs = r.get("observed") or {}
    out: Dict[str, Any] = {
        "ok": True,
        "observed": obs,
        "reading": facts,
        "she_may_say": _b.present(),
        "why": r.get("why") or "",
    }

    # THE SENTENCE FIRST, because a dict of numbers is not an answer to "how is he".
    bits: List[str] = []
    if not obs and not facts:
        bits.append("nothing is reporting — the watch is off him and the phone is quiet")
    else:
        hr = obs.get("heart_rate")
        tail = obs.get("heart_rate_tail")
        if tail and len(tail) >= 2:
            bits.append("his heart, last few readings: %s"
                        % ", ".join(str(int(v)) for v in tail))
        elif hr:
            bits.append("his heart is %d" % int(hr))
        rest = None
        try:
            rest = _b.resting()
        except Exception:
            pass
        if rest is None:
            bits.append("his resting rate is not learned yet, so I have nothing to "
                        "compare a number against")
        if facts.get("movement_word"):
            bits.append("he is %s" % facts["movement_word"])
        conf = facts.get("sleep_confidence")
        if conf is not None:
            src = facts.get("sleep_source")
            where = ("his watch measured it" if src == "watch"
                     else "a sleep classifier says so" if src == "classifier"
                     else "that is my own reading, not a measurement")
            if facts.get("sleep_vetoed_by_room"):
                # ── HE IS HERE. SAY NOTHING ABOUT SLEEP (2026-08-27, his words) ─────
                # "it's kind of silly that she is constantly told I am awake or asleep
                # ... she shouldn't need to comment constantly that I am asleep and
                # never to me obviously."
                #
                # This file already knew the principle — telemetry/body.py's own
                # comment says "'he is awake' is true all day and worth saying never" —
                # and then said it anyway, every time she read the body.
                #
                # The first cut of the veto only fixed the WRONGNESS: it replaced a
                # false claim ("he seems to be asleep, 82%") with a true but pointless
                # one ("his phone's reading is about the phone"). Both are noise to a
                # woman mid-sentence with the man in question. If the room vetoed it,
                # he is DEMONSTRABLY here and there is nothing to report.
                #
                # The facts are untouched in the data — `asleep: False`,
                # `sleep_vetoed_by_room`, `awake_by_room` — for anything that wants to
                # reason about it. This is only about what she is TOLD.
                pass
            elif facts.get("asleep") is True:
                bits.append("he seems to be asleep — %d%%, and %s" % (int(conf), where))
            elif facts.get("asleep") is False:
                bits.append("he is awake — sleep confidence only %d%%" % int(conf))
            else:
                bits.append("whether he is asleep is genuinely unclear — %d%%, which is "
                            "between the two answers" % int(conf))
        if facts.get("awake_by_wrist"):
            bits.append("he just looked at his watch")
        elif facts.get("awake_by_screen"):
            bits.append("his phone screen is on")
    out["in_a_sentence"] = "; ".join(bits) if bits else "I cannot tell you anything about him right now"
    return out


def his_day(hours: float = 8.0) -> Dict[str, Any]:
    """The shape of the last few hours of his body — for "have you slept at all?".

    Counts rather than a feed: how much was recorded, from which device, and how long ago
    the last reading of each kind was. Enough to tell whether he has been wearing the watch
    at all, which is the question behind most of the others.
    """
    try:
        import time as _t

        from harness.telemetry import body as _b
        from harness.telemetry import store as _s
    except Exception as exc:                       # pragma: no cover
        return {"ok": False, "why": "the telemetry framework is not loaded (%s)"
                                    % type(exc).__name__}
    try:
        now = _t.time()
        rows = _s.read_since(float(hours) * 3600, now)
    except Exception as exc:
        return {"ok": False, "why": "could not read his history (%s)" % type(exc).__name__}

    newest: Dict[str, dict] = {}
    counts: Dict[str, int] = {}
    for r in rows:
        k = str(r.get("kind") or "")
        counts[k] = counts.get(k, 0) + 1
        if k not in newest or (r.get("at") or "") > (newest[k].get("at") or ""):
            newest[k] = r

    last_seen = {}
    for k, r in newest.items():
        try:
            last_seen[k] = _fresh_words(now - _s.parse_iso(r.get("at") or ""))
        except Exception:
            pass

    on_wrist = None
    try:
        ob = _b.latest("on_body", rows, now)
        if ob is not None:
            on_wrist = ob.get("value") == "on"
    except Exception:
        pass

    return {
        "ok": True,
        "hours": float(hours),
        "samples": len(rows),
        "counts": counts,
        "last_reading": last_seen,
        "watch_on_his_wrist": on_wrist,
        "in_a_sentence": (
            "nothing at all in the last %g hours — he has not been wearing it"
            % float(hours) if not rows else
            "%d readings in the last %g hours; the watch is %s"
            % (len(rows), float(hours),
               "on him" if on_wrist else "off him" if on_wrist is False else "not saying")),
    }


def when_he_slept(hours: float = 24.0) -> Dict[str, Any]:
    """When he fell asleep and when he was up — AS BOUNDS, because that is the honest shape.

    For "what time did I fall asleep?" and "when did I wake up?". It does not answer with a
    minute, and the reason is not modesty about the instrument.

    MEASURED on 2026-08-27 against his own account (asleep "about" 15:30-20:00). The
    classifier read 15 at 15:33 and did not cross the sure bar until 16:22 — fifty minutes
    late — then held 95 at 20:05 and did not drop until 20:59, an hour after he was up. Any
    single minute taken off that curve is wrong twice a night, stated confidently.

    The truth itself is fuzzy too: falling asleep can take an hour or two, and a night can
    be an hour of sleep, then waking, then a long time turning over. There is no exact
    moment being missed, so a band is the right answer rather than a hedge.

    THE BOUNDS ARE HIS WORDS WHERE THERE ARE ANY. A turn he typed is proof he was awake;
    the phone's low reading is only its opinion, and a bound built on an opinion can put
    the truth outside the band. And waking gets a CEILING rather than a band, because
    wakefulness is provable and sleep is not — see sleep_interval().
    """
    try:
        import time as _t

        from harness.model import transcript as _tr
        from harness.telemetry import body as _b
        from harness.telemetry import store as _s
    except Exception as exc:                       # pragma: no cover
        return {"ok": False, "why": "the telemetry framework is not loaded (%s)"
                                    % type(exc).__name__}
    now = _t.time()
    rows = _s.read_since(float(hours) * 3600.0, now)
    turns = _tr.his_turns() or []
    awake = [t for (t, _w) in turns if now - t <= float(hours) * 3600.0]
    v = _b.sleep_interval(rows, now, awake_at=awake)
    if not v:
        # ABSTAIN. "I cannot see a stretch of sleep" is not "you did not sleep", and the
        # caller has to be able to tell those apart — the rule sleep_estimate already keeps.
        return {"ok": True, "found": False,
                "why": "no stretch long enough to call sleep in the last %g h" % hours}
    out = dict(v)
    out["ok"] = True
    out["found"] = True
    # LOCAL clock in the words, because he asks in his own. The store is UTC with a Z and
    # mixing the two has cost this repo two wrong analyses in one session.
    def _clock(t):
        return _t.strftime("%H:%M", _t.localtime(t)) if t else None
    out["asleep_between"] = [_clock(v["asleep_after"]), _clock(v["asleep_before"])]
    out["up_by"] = _clock(v["woke_by"])
    # SAY WHEN THE THREAD IS LOST rather than let the ceiling stand for it. His phone died
    # at 01:25 on 2026-08-28 and came back at 04:34; without this the answer was a
    # confident "up by 01:25", wrong by about three hours.
    if v.get("blind_after"):
        out["lost_the_thread_at"] = _clock(v["blind_after"])
        out["readings_back_at"] = _clock(v.get("blind_until"))
        out["why"] = ("the readings stop at %s and do not come back until %s, so I cannot "
                      "say when you woke" % (out["lost_the_thread_at"],
                                             out["readings_back_at"] or "later"))
    return out

def body_tools() -> list:
    """Always offered. A tool that vanishes when the watch is off is a tool she cannot use
    to find out that the watch is off."""
    try:
        from harness.toolcore.tools import ToolSpec
        return [ToolSpec.from_callable(how_is_he), ToolSpec.from_callable(his_day),
                ToolSpec.from_callable(when_he_slept)]
    except Exception:
        return []
