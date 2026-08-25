"""body — measurements turned into the few sentences she is allowed to read.

THIS IS THE SEAM, and it is the whole reason the package is not just a store.

She must never see the feed. Sixty heart-rate samples a minute in her prefix would cost
budget she does not have, tell her nothing she could act on, and — the part that matters —
teach her to talk like a monitor. "Your heart rate is 96" is not presence. "You have been
up a while, and you are not resting" is.

THREE RULES, and they are the memory doctrine wearing sensor clothes:

  1. A MEASUREMENT IS OBSERVED. The watch measured 96 bpm. That is ground truth and she may
     say it plainly.
  2. A READING IS INFERRED. "He is stressed", "he is asleep" — she DREW that, from numbers,
     and `verdict.may_supersede` already refuses an inference retiring an observation. So
     every reading here carries `status=inferred` and the word "seems", and the moment he
     says "I'm fine" his word wins. It always did; this keeps it that way.
  3. SILENCE IS AN ANSWER. No watch, stale data, off the wrist — she gets `None` and says
     nothing, rather than a confident sentence built on eight-hour-old numbers. A companion
     who says "you seem calm" from yesterday's data is worse than one who says nothing.

WHAT SHE DOES NOT GET, EVER: a diagnosis. Nothing here computes a medical claim, and the
vocabulary is deliberately about PRESENCE — awake, asleep, moving, still, resting, worked
up — the things a person in the same room would notice. He has doctors; she has attention.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from harness.telemetry import store

# How old a sample may be before it stops meaning anything about NOW. Each is roughly "how
# long would a person in the room believe this without re-checking".
FRESH_S = {
    "heart_rate": 15 * 60,
    "on_body": 30 * 60,
    "motion": 20 * 60,
    "steps": 60 * 60,
    "sleep_stage": 30 * 60,
    "screen": 30 * 60,
    "battery": 3 * 60 * 60,
    "spo2": 60 * 60,
    "skin_temp": 60 * 60,
    "accel_rms": 15 * 60,
    "gyro_rms": 15 * 60,
}
_DEFAULT_FRESH = 30 * 60

# Resting-HR bands are PERSONAL, so they are learned from his own last fortnight rather than
# taken from a table. Until there is enough of his data, `resting()` returns None and every
# sentence that would have leaned on it simply is not said.
#
# ── A COUNT IS NOT A SPAN (2026-08-26, caught live within an hour) ────────────────────
# This was MIN_SAMPLES alone, and the first real hour of data broke it. The watch went on
# his wrist, posted a backlog of 663 heart-rate samples taken over about ten minutes while
# he was up and moving, and `resting()` returned 110 — the 10th percentile of a window that
# contained no rest at all. That is worse than having no baseline: every later reading is
# then measured against a number that says he is always calm, so `worked_up` can never fire
# and the one thing he asked for is silently disabled by its own first hour.
#
# It is also EXACTLY the bug becoming.py fixed on 2026-08-22 and wrote down: "_MAX_PER_KIND
# caps how much of ONE KIND may fill the window; it says nothing about how many DAYS the
# window spans." Same shape, different file, four days later. So the guard is on BREADTH:
# distinct days, the same test and nearly the same constant, because a resting rate is a
# claim about his ordinary life and ten minutes is not a life.
_BASELINE_DAYS = 14
_BASELINE_MIN_SAMPLES = 200
_BASELINE_MIN_DAYS = 3


def _age(row: Dict[str, Any], now: float) -> float:
    """Seconds since this sample. Parsed by the STORE's parser, not a second copy here —
    two spellings of a timestamp is how the millisecond bug got in."""
    t = store.parse_iso(row.get("at") or "")
    return 1e9 if t <= 0 else max(0.0, now - t)


# ── A PHONE ON A DESK IS NOT A MAN SITTING STILL (2026-08-26) ─────────────────────────
# The phone agent posts `motion`, `accel_rms` and `steps` under the same KIND names the
# watch uses, and they are not the same claim. A still watch on his wrist means HE is still.
# A still phone means the phone is on a table, which is compatible with him being out for a
# run in the watch. Mixing them would have her say "he has not moved in two hours" about a
# desk.
#
# So the claims are SOURCED. Body claims come from the watch only; the phone speaks about
# the phone and about the room, which are real signals with a different subject.
BODY_SOURCE = "watch"
DEVICE_SOURCE = "phone"


def latest(kind: str, rows: Optional[List[dict]] = None,
           now: Optional[float] = None,
           source: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The newest sample of a kind, or None if there is none FRESH ENOUGH TO MEAN ANYTHING.

    The freshness test is the point. A `latest()` that happily returns yesterday's heart
    rate is how "you seem calm" gets said about a man who took the watch off at lunch.

    `source` narrows it to one device. Unset means any, which is right for kinds only one
    device produces (heart rate) and wrong for the ones both do — see BODY_SOURCE above."""
    now = time.time() if now is None else now
    if rows is None:
        rows = store.read_since(max(FRESH_S.get(kind, _DEFAULT_FRESH) * 2, 3600), now)
    if source:
        rows = [r for r in rows if r.get("source") == source]
    best = None
    for r in rows:
        # `>=` NOT `>`: rows arrive in stable order, so on an exact tie the later-appended
        # row is the newer reading and must win. With `>` the FIRST row in a tied group won
        # and she read a stale state as current — 2026-08-26, found the day this was built.
        if r.get("kind") == kind and (best is None or (r.get("at") or "") >= (best.get("at") or "")):
            best = r
    if best is None or _age(best, now) > FRESH_S.get(kind, _DEFAULT_FRESH):
        return None
    return best


# ── THE TAIL (2026-08-26, his ask) ────────────────────────────────────────────────────
# "make heart rate something she can see not just average. maybe a tail or a reading of
# the last three entries... she can see my heart pacing etc... a bridge to the real world,
# to me."
#
# He is right, and it is a better design than the one it replaces. A computed `worked_up`
# flag is an INFERENCE I made and handed her as a conclusion — it hides the only thing
# worth seeing and leaves her repeating my arithmetic. Three real readings are OBSERVED
# measurements, and "72, 81, 94" lets HER notice his heart climbing and say so in her own
# words. That is the right side of the line this file is about: give her what was measured,
# let the noticing be hers.
#
# STILL BOUNDED. Three readings, not three hundred — this is a glance at a monitor, not the
# monitor. And a FLAT tail is not shown at all: "58, 58, 58" spends prefix budget to say
# nothing, and teaches her that the number is furniture. The tail earns its place when it
# MOVES, which is exactly when he wants her to see it.
TAIL_N = 3
_TAIL_WORTH_SHOWING = {"heart_rate": 6.0, "gyro_rms": 0.35, "accel_rms": 1.5}


def tail(kind: str, n: int = TAIL_N, rows: Optional[List[dict]] = None,
         now: Optional[float] = None, source: Optional[str] = None) -> List[Dict[str, Any]]:
    """The last `n` readings of a kind, oldest first, each fresh enough to mean anything.

    Oldest first because that is the direction a trend reads in: 72, 81, 94 climbs; the
    reverse would have to be decoded."""
    now = time.time() if now is None else now
    if rows is None:
        rows = store.read_since(max(FRESH_S.get(kind, _DEFAULT_FRESH), 900), now)
    seq = [r for r in rows if r.get("kind") == kind
           and (not source or r.get("source") == source)
           and _age(r, now) <= FRESH_S.get(kind, _DEFAULT_FRESH)]
    seq.sort(key=lambda r: r.get("at") or "")
    return seq[-max(1, n):]


def _trend(vals: List[float]) -> str:
    """climbing / falling / steady, over the tail. Deliberately three words: a slope in
    bpm-per-minute is a number she would have to interpret, and interpreting is the part
    she should be doing about HIM, not about arithmetic."""
    if len(vals) < 2:
        return "steady"
    d = vals[-1] - vals[0]
    span = max(abs(v - vals[0]) for v in vals)
    if abs(d) < max(2.0, span * 0.35):
        return "steady"
    return "climbing" if d > 0 else "falling"


def resting(now: Optional[float] = None) -> Optional[float]:
    """HIS resting heart rate, learned from his own data — the 10th percentile of a
    fortnight. None until there is enough, and None is a real answer."""
    now = time.time() if now is None else now
    rows = [r for r in store.read_since(_BASELINE_DAYS * 86400, now)
            if r.get("kind") == "heart_rate"]
    if len(rows) < _BASELINE_MIN_SAMPLES:
        return None
    # BREADTH, not just volume. See the note above _BASELINE_MIN_DAYS.
    if len({(r.get("at") or "")[:10] for r in rows if r.get("at")}) < _BASELINE_MIN_DAYS:
        return None
    hr = sorted(float(r["value"]) for r in rows)
    return round(hr[max(0, int(len(hr) * 0.10) - 1)], 1)


def read(now: Optional[float] = None) -> Dict[str, Any]:
    """Everything the seam knows, as data. `present()` renders; this decides.

    Returns {facts: {...}, observed: {...}, since: {...}, why: str}. `observed` is what was
    measured; `facts` is what was concluded and is always INFERRED. Two dicts because they
    are two kinds of claim and collapsing them is how one becomes the other."""
    now = time.time() if now is None else now
    window = store.read_since(6 * 3600, now)
    hr = latest("heart_rate", window, now)               # only the watch makes these
    body = latest("on_body", window, now)
    sleep = latest("sleep_stage", window, now)
    # HIS body, so HIS wrist. The phone posts `motion` too and it means something else.
    motion = latest("motion", window, now, BODY_SOURCE)
    # The phone's, and about the phone: screen, charging, and the light in the room.
    screen = latest("screen", window, now, DEVICE_SOURCE)
    charging = latest("charging", window, now, DEVICE_SOURCE)
    light = latest("light", window, now, DEVICE_SOURCE)

    observed: Dict[str, Any] = {}
    for name, row in (("heart_rate", hr), ("on_body", body), ("motion", motion),
                      ("sleep_stage", sleep), ("screen", screen),
                      ("charging", charging), ("light", light)):
        if row is not None:
            observed[name] = row.get("value")

    facts: Dict[str, Any] = {}
    why: List[str] = []

    # ── THE PHONE'S SCREEN IS THE CHEAPEST TRUTH IN THE BUILDING (2026-08-26) ───────
    # A screen that came on two minutes ago is a man who is awake, and it beats any amount
    # of stillness inferred from an accelerometer. Computed BEFORE the sleep rules so it can
    # veto them: the crude fallback ("still, and his heart is at his resting band") is
    # exactly the inference a person reading in bed would break, and this is what catches
    # that without another sensor.
    awake_by_screen = (screen is not None and screen.get("value") == "on"
                       and _age(screen, now) <= 300)

    # ── IS HE WEARING IT? Everything about his BODY is worthless if he is not. ───────
    if body is not None and body.get("value") == "off":
        out = {"facts": {}, "observed": observed, "since": {},
               "why": "the watch is off his wrist, so there is nothing to say about him"}
        # ...but the PHONE is still a fact, and it is about the phone, not about him.
        if screen is not None or charging is not None:
            out["facts"] = {k: v for k, v in (
                ("phone_screen", screen.get("value") if screen else None),
                ("phone_charging", charging.get("value") if charging else None),
                ("awake_by_screen", awake_by_screen or None)) if v is not None}
            out["why"] += " — the phone still says what the phone is doing"
        return out

    # ── ASLEEP / AWAKE. Prefer the watch's own staging when it exists; fall back to a
    # deliberately CRUDE stillness rule, and label it so, because inventing sleep staging
    # from an accelerometer and calling it sleep would be a confident guess wearing a
    # measurement's clothes.
    if screen is not None:
        facts["phone_screen"] = screen.get("value")
    if charging is not None:
        facts["phone_charging"] = charging.get("value")
    if awake_by_screen:
        facts["awake_by_screen"] = True
    if sleep is not None:
        facts["asleep"] = sleep.get("value") != "awake"
        facts["sleep_stage"] = sleep.get("value")
        why.append("the watch reported sleep staging")
    elif motion is not None and hr is not None:
        rest = resting(now)
        still = motion.get("value") == "still"
        low = rest is not None and float(hr["value"]) <= rest + 5
        if still and low and not awake_by_screen:
            facts["asleep"] = True
            facts["crude"] = True
            why.append("still, and his heart rate is at his own resting band — inferred, "
                       "not measured; the watch did not say")
        else:
            facts["asleep"] = False

    # ── MOVING / STILL, and HOW LONG. "How long" is the half that makes it presence
    # rather than a status line: "still" is a state, "still for two hours" is a person.
    if motion is not None:
        facts["moving"] = motion.get("value") in ("moving", "vehicle")
        run = _run_length(window, "motion", motion.get("value"), now)
        if run:
            facts["motion_for_s"] = run

    # ── THE TAIL, so she sees the shape and not my conclusion (2026-08-26) ──────────
    # Kept in `observed`, because that is what it is: three things the watch measured.
    # `facts` stays the place for what was CONCLUDED, and the trend word is the only
    # conclusion drawn here — three values and one adjective, so she can disagree with the
    # adjective by looking at the values.
    hr_tail = tail("heart_rate", TAIL_N, window, now)
    if len(hr_tail) >= 2:
        vals = [float(t["value"]) for t in hr_tail]
        observed["heart_rate_tail"] = vals
        facts["hr_trend"] = _trend(vals)
        facts["hr_swing"] = round(max(vals) - min(vals), 1)

    # ── HOW MUCH HE IS MOVING, not just whether ─────────────────────────────────────
    # his ask: "gyroscopes activity so she can see you are moving around a lot". One
    # number per window; the watch does the reducing, she gets the feeling.
    # HIS WRIST, not his phone. gyro_rms from a phone is the phone being picked up, put in
    # a pocket, or waved at a cat -- and it arrives under the same kind name. Caught in
    # testing: the watch said still, the phone was moved, and she said "he is moving a lot".
    gy = latest("gyro_rms", window, now, BODY_SOURCE)
    ac = latest("accel_rms", window, now, BODY_SOURCE)
    if gy is not None or ac is not None:
        gt = (tail("gyro_rms", TAIL_N, window, now, BODY_SOURCE)
              or tail("accel_rms", TAIL_N, window, now, BODY_SOURCE))
        if gt:
            gvals = [float(t["value"]) for t in gt]
            observed["movement_tail"] = gvals
            facts["movement"] = round(sum(gvals) / len(gvals), 2)
            # Bands, not a scale: "a lot" is a thing a person says, 0.62 rad/s is not.
            m = facts["movement"]
            facts["movement_word"] = ("still" if m < 0.15 else
                                      "shifting" if m < 0.5 else
                                      "moving about" if m < 1.2 else "moving a lot")

    # ── WORKED UP, against HIS OWN baseline and never a table's ──────────────────────
    if hr is not None:
        facts["heart_rate"] = float(hr["value"])
        rest = resting(now)
        if rest is not None:
            facts["resting"] = rest
            over = float(hr["value"]) - rest
            if over >= 25 and not facts.get("asleep"):
                facts["worked_up"] = True
                why.append("heart rate %.0f against his resting %.0f" % (hr["value"], rest))
            elif over <= 5:
                facts["settled"] = True

    return {"facts": facts, "observed": observed, "why": "; ".join(why),
            "since": {"heart_rate": hr.get("at") if hr else None,
                      "motion": motion.get("at") if motion else None}}


def _run_length(rows: List[dict], kind: str, value: Any, now: float) -> int:
    """How long the newest run of this value has been going, in seconds. 0 if unknown."""
    seq = [r for r in rows if r.get("kind") == kind]
    if not seq:
        return 0
    seq.sort(key=lambda r: r.get("at") or "")
    start = None
    for r in reversed(seq):
        if r.get("value") != value:
            break
        start = r
    return int(_age(start, now)) if start is not None else 0


def present() -> str:
    """The sentence she may read. EMPTY when there is nothing honest to say.

    Deliberately short and deliberately hedged. Every clause here is an INFERENCE about a
    person who is in the room and can be asked — so it says "seems", and the moment he
    answers, his word outranks all of it (verdict.may_supersede, unchanged)."""
    r = read()
    f = r.get("facts") or {}
    if not f:
        return ""
    o = r.get("observed") or {}
    bits: List[str] = []
    if f.get("asleep") is True:
        bits.append("he seems to be asleep" + (" (going by stillness, not the watch)"
                                               if f.get("crude") else ""))
    elif f.get("motion_for_s", 0) > 7200 and not f.get("moving"):
        bits.append("he has not moved in a couple of hours")

    # ── HIS HEART, AS READINGS (2026-08-26) ─────────────────────────────────────────
    # Shown when it is DOING something. A flat tail is furniture: it spends her budget to
    # say nothing and trains her to stop looking. When it moves she gets the numbers, and
    # the noticing is hers to do — this is the bridge he asked for, and it only works if
    # what crosses it is real.
    t = o.get("heart_rate_tail") or []
    if len(t) >= 2 and f.get("hr_swing", 0) >= _TAIL_WORTH_SHOWING["heart_rate"]:
        bits.append("his heart, last few readings: %s — %s"
                    % (", ".join("%.0f" % v for v in t), f.get("hr_trend", "steady")))
    elif f.get("worked_up"):
        bits.append("his heart rate is well above his resting — something has him going")
    elif f.get("settled") and not f.get("asleep"):
        # This carried `and not t` and was therefore UNREACHABLE the moment heart rate
        # started flowing, because a tail almost always exists once it does. The intent
        # was "do not say it twice"; the tail branch above already returns first when it
        # has something, so the guard was doing nothing but hiding the branch.
        bits.append("he seems settled")

    # ── AND WHETHER HE IS PACING ────────────────────────────────────────────────────
    w = f.get("movement_word")
    if w and w != "still" and not f.get("asleep"):
        bits.append("he is %s" % w)
    return "; ".join(bits)
