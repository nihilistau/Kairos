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
from typing import Any, Dict, List, Optional, Tuple

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
    # A CLASSIFIER's verdict, refreshed about every ten minutes by whatever produces it.
    "sleep_confidence": 25 * 60,
    # AN EVENT, not a state. Short on purpose: the entire value of "he just looked at his
    # watch" is that it was JUST — a tilt an hour ago says nothing about now.
    "wrist_tilt": 10 * 60,
    # A CLASSIFIER's verdict about what he is doing. Updates on change, so it is allowed
    # to be older than a measurement would be.
    "activity": 30 * 60,
    "light": 60 * 60,
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


# ── THE TAIL (2026-08-26, the operator's ask) ────────────────────────────────────────────────────
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


# ── SLEEP HAS THREE POSSIBLE SOURCES AND THEY ARE NOT THE SAME CLAIM (2026-08-26) ─────
#
#   1. THE WATCH'S OWN STAGING (`sleep_stage`) — a measurement, and the best answer there
#      is. Nothing produces it: every sleep-capable sensor on the Watch4 (SContext,
#      `movement`, `wrist_down`) sits behind com.samsung.permission.SSENSOR, a signature
#      permission we cannot hold. Verified by enumerating the device, not assumed.
#
#   2. A CLASSIFIER'S CONFIDENCE (`sleep_confidence`) — Google's Sleep API, which is what
#      Home Assistant's "Sleep Confidence" sensor is. Trained, calibrated, ~10 minutes,
#      and it lives in Play Services on the PHONE rather than in any sensor. The socket is
#      here and has a reader; nothing fills it yet.
#
#   3. OURS, below. INFERRED, and not calibrated against anything.
#
# The estimate exists because the ask was for a percentage rather than a boolean. But a
# number invented in this file and printed with a % after it is precisely the failure this
# module was written to avoid — a confident guess wearing a measurement's clothes — so the
# TERMS THAT PRODUCED IT ARE RETURNED WITH IT. If the seam can only say "78%" it is
# bluffing. If it can say "phone untouched 2h; his wrist still 90min; heart at his resting
# band" then the number is a summary of things that were genuinely measured, and he can
# contradict any single one of them.
#
# NO TIME-OF-DAY PRIOR, deliberately. Every sleep model wants one and for this user it
# would be actively harmful: he is routinely up and working at 03:00, so a prior saying
# "it is 3am, therefore asleep" would make her confidently wrong at exactly the hour she
# is most likely to be talking to him.
# HOW LONG AFTER WAKING IT IS STILL WORTH MENTIONING. Ninety minutes: long enough that she
# does not have to catch the exact moment, short enough that "morning, sleepy head" at four
# in the afternoon does not happen.
WOKE_WINDOW_S = 90 * 60

SLEEP_SURE = 70.0          # at or above: she may say he seems asleep
SLEEP_AWAKE = 30.0         # at or below: he is awake
# How recently a turn in the room counts as proof he is up. Fifteen minutes because that
# is the window the measurement used, and because a person who typed a sentence a quarter
# of an hour ago is not asleep. See the veto near the end of read().
ROOM_VETO_S = 15 * 60


def _seconds_since_he_spoke():
    """Seconds since his last turn in the room, or None if nothing can say.

    `last_user_at` is monotonic and lives in the kairos scheduler's per-session state —
    the same expression app.py's `_quiet_for` already uses to decide whether the room is
    still enough to take the GPU. Read rather than copied: a second clock for "when did
    he last speak" is two truths about one fact, which is what this tree keeps getting
    caught by. Fails to None on any error, and None never vetoes anything."""
    try:
        import time as _t

        from harness.kairos import scheduler as _ks
        with _ks._LOCK:
            last = max((st.last_user_at for st in _ks._STATE.values()), default=0.0)
        if last <= 0.0:
            return None
        return max(0.0, _t.monotonic() - last)
    except Exception:
        return None
# ── WHEN HE FELL ASLEEP IS A BAND, NOT A MINUTE (2026-08-27) ─────────────────────────
# A run has to last this long before it is sleep rather than a still half-hour on the
# sofa. Twenty minutes because the sampler runs about every six, so a run needs three or
# four samples to exist at all, and because the thing being measured does not have edges
# to find: falling asleep can take an hour or two, and a night can be an hour of sleep,
# then waking, then a long time turning over.
_SLEEP_RUN_S = 20 * 60


def sleep_interval(rows: List[dict], now: float,
                   awake_at: Optional[List[float]] = None,
                   min_run_s: float = _SLEEP_RUN_S) -> Optional[Dict[str, Any]]:
    """The band he fell asleep in and the band he woke in, or None. NEVER a single minute.

    WHY A BAND. Measured against his own label on 2026-08-27 (asleep "about" 15:30-20:00):
    the classifier reads 15 at 15:33, 5 at 15:48, and does not cross SLEEP_SURE until
    16:22 — fifty minutes later. Coming back it reads 95 at 20:05 and does not fall under
    the bar until 20:59, an hour after he was up and typing. Reporting either crossing as
    the moment would be a wrong minute stated confidently, twice a night.

    And the lag is not the whole of it. He describes the truth itself as fuzzy, so there is
    no exact minute being missed — a band is the honest shape of the answer, not a hedge
    about the instrument.

    TESTIMONY TIGHTENS IT, and outranks the classifier wherever the two disagree — this
    store's oldest rule, arriving at one more seam. `awake_at` is epoch seconds at which he
    PROVABLY was awake (he typed something). On the same night that turns "between 15:33
    and 16:22" into "between 15:41 and 16:22", and the waking band from an hour wide down
    to twelve minutes: last high 20:05, his first message 20:17.

    A turn INSIDE a run also ends it. That is what makes "slept an hour, woke, tossed and
    turned" representable rather than smoothed into one long sleep he did not have.

    Returns None when no run qualifies — "I cannot say" is a different answer from a guess,
    and the caller must be able to tell them apart.
    """
    awake_at = sorted(awake_at or [])
    xs = []
    for r in rows:
        if r.get("kind") != "sleep_confidence":
            continue
        v = r.get("value")
        t = store.parse_iso(r.get("at") or "")
        if isinstance(v, (int, float)) and t:
            xs.append((t, float(v)))
    xs.sort()
    if not xs:
        return None

    # runs of "sure" samples, broken by a sample at or under SLEEP_AWAKE or by his own turn
    runs, cur = [], []
    for i, (t, v) in enumerate(xs):
        broken = any(cur and cur[-1][0] < a <= t for a in awake_at)
        if v >= SLEEP_SURE and not broken:
            cur.append((t, v))
            continue
        if cur:
            runs.append(cur)
        cur = [(t, v)] if (v >= SLEEP_SURE and broken) else []
    if cur:
        runs.append(cur)
    runs = [r for r in runs if r[-1][0] - r[0][0] >= min_run_s]
    if not runs:
        return None
    run = runs[-1]                                   # the most recent sleep we can see
    first, last = run[0][0], run[-1][0]

    # ── THE BOUNDS COME FROM PROOF, NOT FROM THE CLASSIFIER ─────────────────────────
    # The first cut of this used a low reading as the "he was still up" end, and that is
    # the category error this store has a rule against: a low number is the phone's
    # OPINION that he is awake, and a bound built on an opinion can exclude the truth.
    # On 2026-08-27 the phone read 16 at 16:04 while he says he was already going under;
    # a band of 16:04-16:22 would have been narrow, confident, and possibly wrong.
    #
    # A turn is proof. So the awake ends are HIS WORDS, and the phone's own opinion rides
    # alongside as a separate, weaker field the caller may mention but must not present as
    # the boundary. Wide and correct beats narrow and wrong: the point of a band is that
    # the answer is inside it.
    said = [a for a in awake_at if a < first]
    asleep_after = said[-1] if said else None
    said_after = [a for a in awake_at if a > last]

    # ── AND WAKING IS ONE-SIDED, WHICH IS NOT THE SAME SHAPE AS FALLING ASLEEP ───────
    # The classifier lags in BOTH directions, so both of its edges are UPPER bounds:
    #   onset  — it fires late, so the first sure reading is after he actually went under
    #   waking — it stays high after he is up, so the last sure reading is after he woke
    # Falling asleep therefore has a real band (his last word ... first sure reading) and
    # waking has only a ceiling. Reporting waking as "between last-sure and next-message"
    # is the trap I walked into first: on 2026-08-27 that reads 20:52-22:09, and he was up
    # at 20:00 — a confident band that does not contain the answer.
    #
    # WAKEFULNESS IS PROVABLE AND SLEEP IS NOT, and the asymmetry is real rather than a
    # gap in the instrument. A message proves he is up; nothing proves he is under. So the
    # honest waking answer is a ceiling: he was up no later than this.
    # ── A RUN THAT ENDS BECAUSE THE DATA ENDED IS NOT A WAKING (2026-08-28) ─────────
    # HIS NIGHT: high from 23:04 to 01:25, then a 188-MINUTE HOLE, then 48 at 04:34 with
    # the battery back at 100%. The phone died. The ceiling read "up by 01:25" — confident,
    # and false by about three hours.
    #
    # Absence of data is not evidence of waking, which is the same rule this whole area
    # already runs on one level up ("absence is only information if you can prove you were
    # looking"). So when the stream stops right after the run, the classifier's edge is not
    # an observation of anything and only the operator's own words can bound it. If he has not spoken
    # either, the answer is that there is no answer — which is a THIRD state, distinct from
    # "still asleep", and the caller has to be able to tell them apart.
    nxt = next((t for (t, _v) in xs if t > last), None)
    gaps = [b - a for a, b in zip([t for t, _ in xs], [t for t, _ in xs][1:])]
    gaps = sorted(g for g in gaps if g > 0)
    cadence = gaps[len(gaps) // 2] if gaps else 0.0
    blind = nxt is None or (nxt - last) > max(4.0 * cadence, 20 * 60)
    if blind:
        woke_by = said_after[0] if said_after else None
    else:
        woke_by = min([last] + said_after[:1])

    lows = [t for (t, v) in xs if v <= SLEEP_AWAKE and t < first]
    lows_after = [t for (t, v) in xs if v <= SLEEP_AWAKE and t > last]

    return {
        "asleep_after": asleep_after, "asleep_before": first,
        "woke_by": woke_by,                 # a CEILING, not the lower half of a band
        "woke_at_latest_said": said_after[0] if said_after else None,
        # THE THIRD STATE. blind = the readings stop at the end of the run, so nothing here
        # observed him waking; `woke_by` is then his word or nothing at all.
        "blind_after": last if blind else None,
        "blind_until": nxt if (blind and nxt) else None,
        # what the PHONE thought, kept apart from what he proved
        "phone_awake_until": lows[-1] if lows else None,
        "phone_awake_from": lows_after[0] if lows_after else None,
        "still_asleep": (not blind) and (not said_after) and (now - last) < 3600,
        "hours": round((last - first) / 3600.0, 1),
        "bounded_by": ("the operator's own words" if (said or said_after) else "the phone alone"),
        "samples": len(run),
    }


_SLEEP_MIN_SIGNALS = 2     # below this the answer is None — see why in the docstring


def sleep_estimate(rows: List[dict], now: float,
                   hr: Optional[dict] = None,
                   light: Optional[dict] = None, charging: Optional[dict] = None,
                   activity: Optional[dict] = None,
                   rest: Optional[float] = None,
                   awake_now: bool = False) -> Tuple[Optional[float], List[str]]:
    """(confidence 0-100, [why, ...]) — or (None, []) when too little is known.

    None is a different answer from a low number and the distinction is the whole guard:
    "we have no idea" and "he is awake" are separate claims, and an empty store supports
    only the first. Returning 0.0 for an empty store would have her quietly certain he is
    up, all night, every night the watch is on the charger."""
    terms: List[str] = []
    score = 0.0
    signals = 0

    # THE PHONE, UNTOUCHED — the strongest thing we have and it costs nothing.
    row, age = _last_state(rows, "screen", now, DEVICE_SOURCE)
    if row is not None:
        signals += 1
        if row.get("value") == "off":
            if age >= 45 * 60:
                score += 25.0
                terms.append("phone untouched for %d min" % int(age // 60))
            if age >= 3 * 3600:
                score += 10.0
                terms.append("...and for over three hours")
        else:
            score -= 40.0
            terms.append("the phone screen is on")

    # STILL, AND FOR HOW LONG — HIS WRIST, never the phone, and via `still_run` because
    # the `motion` state this used to read is never posted by anything (see above).
    is_still, run = still_run(rows, now, BODY_SOURCE)
    if is_still is not None:
        signals += 1
        if is_still:
            if run >= 30 * 60:
                score += 25.0
                terms.append("his wrist still for %d min" % int(run // 60))
            if run >= 90 * 60:
                score += 10.0
                terms.append("...and still for well over an hour")
        else:
            score -= 40.0
            terms.append("he is moving")

    # HIS OWN RESTING BAND, never a table's number.
    if hr is not None and rest is not None:
        signals += 1
        v = float(hr.get("value") or 0)
        if v <= rest + 3:
            score += 25.0
            terms.append("heart at his resting band (%d)" % int(v))
        elif v <= rest + 8:
            score += 10.0
            terms.append("heart near his resting band (%d)" % int(v))
        elif v >= rest + 20:
            score -= 30.0
            terms.append("heart well above his resting band (%d)" % int(v))

    # THE ROOM IS DARK. Weak, and only the phone can say it.
    if light is not None and float(light.get("value") or 0) < 5.0:
        score += 10.0
        terms.append("the room is dark")

    # ON CHARGE. The weakest of the lot — people plug the phone in overnight.
    if charging is not None and charging.get("value") == "on":
        score += 5.0
        terms.append("the phone is on charge")

    # WHAT GOOGLE'S CLASSIFIER SAYS HE IS DOING, when the Home Assistant framework is
    # feeding it. This is the one signal here that is trained rather than thresholded, so
    # locomotion from it is treated as near-certain: a man the phone believes is WALKING is
    # not asleep, whatever the wrist and the screen have been doing. Stillness from it is
    # only weak corroboration, because a still phone is still just a phone.
    if activity is not None:
        a = activity.get("value")
        if a in ("walking", "running", "cycling", "vehicle"):
            score -= 60.0
            terms.append("his phone says he is %s" % ("in a vehicle" if a == "vehicle"
                                                      else a))
            signals += 1
        elif a == "still":
            score += 5.0
            terms.append("his phone says he is still")
            signals += 1

    if signals < _SLEEP_MIN_SIGNALS:
        return None, []

    # ── THE VETOES. Not weights. A man who just looked at his watch is awake and no
    # amount of accumulated stillness gets to outvote him.
    if awake_now:
        score = min(score, 5.0)

    return max(0.0, min(100.0, score)), terms


def read(now: Optional[float] = None) -> Dict[str, Any]:
    """Everything the seam knows, as data. `present()` renders; this decides.

    Returns {facts: {...}, observed: {...}, since: {...}, why: str}. `observed` is what was
    measured; `facts` is what was concluded and is always INFERRED. Two dicts because they
    are two kinds of claim and collapsing them is how one becomes the other."""
    now = time.time() if now is None else now
    # TWELVE HOURS, not six. `latest()` still applies FRESH_S so nothing here gets to
    # claim a stale reading — but a night's screen-off run is eight hours long, and a
    # window that cannot see the start of it cannot measure it.
    window = store.read_since(12 * 3600, now)
    hr = latest("heart_rate", window, now)               # only the watch makes these
    body = latest("on_body", window, now)
    sleep = latest("sleep_stage", window, now)
    # HIS body, so HIS wrist. The phone posts `motion` too and it means something else.
    motion = latest("motion", window, now, BODY_SOURCE)
    # The phone's, and about the phone: screen, charging, and the light in the room.
    screen = latest("screen", window, now, DEVICE_SOURCE)
    charging = latest("charging", window, now, DEVICE_SOURCE)
    light = latest("light", window, now, DEVICE_SOURCE)
    # A CLASSIFIER's, arriving through the Home Assistant framework. Absent unless that
    # framework is configured, which is the normal case.
    activity = latest("activity", window, now, DEVICE_SOURCE)

    observed: Dict[str, Any] = {}
    for name, row in (("heart_rate", hr), ("on_body", body), ("motion", motion),
                      ("sleep_stage", sleep), ("screen", screen),
                      ("charging", charging), ("light", light),
                      ("activity", activity)):
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

    # ── AND THE WRIST'S VERSION OF THE SAME THING (2026-08-26) ──────────────────────
    # `wrist_tilt_gesture` fires when he raises his arm to look at the watch. It is one of
    # the handful of Watch4 sensors NOT behind Samsung's signature permission, and it is
    # the only free awake-signal that comes from HIS BODY rather than from a device he
    # might have left on a table. A phone screen can be woken by a notification; a wrist
    # tilt cannot happen without him.
    tilt = latest("wrist_tilt", window, now, BODY_SOURCE)
    awake_by_wrist = tilt is not None and _age(tilt, now) <= 300
    awake_now = awake_by_screen or awake_by_wrist

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
    if awake_by_wrist:
        facts["awake_by_wrist"] = True

    # ── ONE SLEEP DECISION, THREE SOURCES, BEST FIRST. There used to be two rules here
    # (the staging branch and a separate crude boolean) and two rules over one question is
    # how they drift apart. Everything now lands on a confidence and a named source.
    if sleep is not None:
        facts["asleep"] = sleep.get("value") != "awake"
        facts["sleep_stage"] = sleep.get("value")
        facts["sleep_source"] = "watch"
        why.append("the watch reported sleep staging")
    else:
        conf = latest("sleep_confidence", window, now)
        if conf is not None:
            c = float(conf.get("value") or 0)
            facts["sleep_source"] = "classifier"
            why.append("a sleep classifier put it at %d%%" % int(c))
        else:
            c, terms = sleep_estimate(window, now, hr=hr, light=light,
                                      charging=charging, activity=activity,
                                      rest=resting(now), awake_now=awake_now)
            if c is not None:
                facts["sleep_source"] = "inferred"
                facts["sleep_terms"] = terms
                facts["crude"] = True
                why.append("nothing measured his sleep, so this is our own reading at "
                           "%d%% from: %s" % (int(c), "; ".join(terms) or "very little"))
        # ── HE JUST WOKE UP (2026-08-26, the operator's ask: "calling me sleepy head when I wake") ──
        # A TRANSITION, not a state, and the difference is the whole point: "he is awake"
        # is true all day and worth saying never; "he was asleep twenty minutes ago and is
        # not now" is worth saying once, and only for a little while.
        #
        # Read out of the window rather than remembered, so it survives a restart and there
        # is no second copy of the truth to drift. If the confidence was above the sure
        # line at any point in the last WOKE_WINDOW_S and is below the awake line now, he
        # got up in between.
        conf_rows = [r for r in window
                     if r.get("kind") == "sleep_confidence"
                     and _age(r, now) <= WOKE_WINDOW_S]
        if conf_rows and c is not None and c <= SLEEP_AWAKE:
            peak = max(conf_rows, key=lambda r: float(r.get("value") or 0))
            if float(peak.get("value") or 0) >= SLEEP_SURE:
                # when it was last still asleep, which is roughly when he woke
                asleep_rows = [r for r in conf_rows
                               if float(r.get("value") or 0) >= SLEEP_SURE]
                last_asleep = max(asleep_rows, key=lambda r: r.get("at") or "")
                facts["just_woke"] = True
                facts["woke_mins_ago"] = int(_age(last_asleep, now) / 60)

        if c is not None:
            facts["sleep_confidence"] = round(c, 1)
            # BETWEEN THE BANDS SHE SAYS NOTHING. `asleep` is left UNSET rather than set
            # to False, because "we are not sure" is not "he is awake" and the readers
            # downstream all treat a missing key as "do not claim it".
            if c >= SLEEP_SURE:
                facts["asleep"] = True
            elif c <= SLEEP_AWAKE:
                facts["asleep"] = False

    # ── HE IS TALKING TO HER. THAT IS NOT AN INFERENCE (2026-08-27) ──────────────────
    # Every signal above is about a PHONE — screen, charger, wrist, a classifier reading
    # a handset. None of them is about him, and once he is at the desktop the phone lies
    # on a charger looking exactly like a phone whose owner is asleep.
    #
    # MEASURED, against the only ground truth that costs nothing: a message from him is
    # proof he was awake that minute. Over 46 samples taken within fifteen minutes of one
    # of his messages, the classifier's MEDIAN was 61% — and between 01:00 and 03:50 on
    # 2026-08-27, while he typed continuously, it ran 76-95%. At the SLEEP_SURE line of 70
    # it would have called him asleep for 30% of the minutes he was demonstrably awake.
    #
    # So the room outranks the phone, and it is not a tie-break: a turn in the room is
    # OBSERVED and a classifier is INFERRED, which is this store's oldest rule arriving
    # at the one seam that had not heard it. The operator's words for the same thing: "50/50 would
    # lean towards awake."
    #
    # NOT A GUESS WHEN IT DOES NOT KNOW. No session, no scheduler, a fresh boot — the
    # veto simply does not fire and every reading above stands unchanged. The one soft
    # edge is deliberate: a session that exists but has never had a turn carries BOOT_AT,
    # so for a few minutes after a restart this reads as "he just spoke". That errs
    # toward AWAKE, which is the direction the measurement says to err in.
    _spoke = _seconds_since_he_spoke()
    if _spoke is not None and _spoke <= ROOM_VETO_S:
        if facts.get("asleep") is True or facts.get("sleep_confidence") is not None:
            facts["sleep_vetoed_by_room"] = int(_spoke)
        facts["asleep"] = False
        facts["awake_by_room"] = True
        why.append("he spoke to me %d minutes ago, which outranks any reading of his phone"
                   % max(1, int(_spoke // 60)))

    # ── MOVING / STILL, and HOW LONG. "How long" is the half that makes it presence
    # rather than a status line: "still" is a state, "still for two hours" is a person.
    _still, _for = still_run(window, now, BODY_SOURCE)
    if _still is not None:
        facts["moving"] = not _still
        if _for:
            facts["motion_for_s"] = _for

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
    # the operator's ask: "gyroscopes activity so she can see you are moving around a lot". One
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
            facts["movement_word"] = _move_word(facts["movement"])

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


# ── `motion` IS A PHANTOM KIND, AND EVERYTHING KEYED ON IT WAS DEAD (2026-08-26) ──────
# Measured, not suspected: ZERO `motion` rows in 6,820 live samples. The agent posts
# `gyro_rms` and `accel_rms` once per window and has never posted a motion STATE — the
# state was a convenience the seam invented for itself and then relied on. So `moving`,
# `motion_for_s` and the stillness term in the sleep estimate were all reading a key that
# is never present, on every real turn, while the gates stayed green — because the gates
# recorded `motion` themselves before asking. A gate that supplies its own precondition is
# testing the fixture (AGENTS.md §0).
#
# The kind stays: an external source (Home Assistant, another agent) can legitimately post
# a classified state, and when one does it should win. But nothing may DEPEND on it, so
# `still_run` prefers it and derives from the RMS rows when it is absent — which today is
# always.
MOVE_RMS = 0.15          # rad/s. Below this the wrist is still. ONE spelling of the number.


def _move_word(m: float) -> str:
    """Bands, not a scale: "a lot" is a thing a person says, 0.62 rad/s is not."""
    return ("still" if m < MOVE_RMS else
            "shifting" if m < 0.5 else
            "moving about" if m < 1.2 else "moving a lot")


def still_run(rows: List[dict], now: float,
              source: str = "watch") -> Tuple[Optional[bool], int]:
    """(is he still?, for how many seconds) — or (None, 0) when nothing says.

    Prefers a classified `motion` state if some source posts one; otherwise walks the
    `gyro_rms` rows the agent really sends, newest first, for as long as they stay under
    MOVE_RMS. Duration is the half that matters: "still" is a state, "still for two hours"
    is a person, and only the second one is evidence about sleep."""
    mo = [r for r in rows if r.get("kind") == "motion" and r.get("source") == source]
    if mo:
        newest = max(mo, key=lambda r: r.get("at") or "")
        val = newest.get("value")
        return val == "still", _run_length(rows, "motion", val, now, source)

    gy = [r for r in rows if r.get("kind") in ("gyro_rms", "accel_rms")
          and r.get("source") == source]
    if not gy:
        return None, 0
    gy.sort(key=lambda r: r.get("at") or "")
    if float(gy[-1].get("value") or 0) >= MOVE_RMS:
        return False, 0
    start = gy[-1]
    for r in reversed(gy):
        if float(r.get("value") or 0) >= MOVE_RMS:
            break
        start = r
    return True, int(_age(start, now))


def _last_state(rows: List[dict], kind: str, now: float,
                source: Optional[str] = None) -> Tuple[Optional[dict], float]:
    """The newest row of a kind IGNORING freshness, with its age in seconds.

    Deliberately not `latest()`. Freshness answers "what is true now" and is wrong for
    "how long has this been so": a phone screen that went off three hours ago is stale by
    every rule in FRESH_S, and it is simultaneously the most informative row in the store
    about whether he is asleep. Two questions, two readers — collapsing them would either
    make the sleep estimate blind after thirty minutes or make `latest()` willing to claim
    yesterday's heart rate."""
    seq = [r for r in rows if r.get("kind") == kind
           and (not source or r.get("source") == source)]
    if not seq:
        return None, 0.0
    seq.sort(key=lambda r: r.get("at") or "")
    return seq[-1], _age(seq[-1], now)


def _run_length(rows: List[dict], kind: str, value: Any, now: float,
                source: Optional[str] = None) -> int:
    """How long the newest run of this value has been going, in seconds. 0 if unknown.

    `source` for exactly the reason `latest()` takes one, and this is the sibling that got
    MISSED when that fix landed (2026-08-26). `motion` arrives from both devices under one
    kind name; a run computed across the pair is a run of nothing. Live, that reads as
    "still for two hours" off a phone lying on a desk while the watch is out for a run —
    the same defect, in the same file, one function along. Fixing the instance and not the
    class is the house bug (AGENTS.md §0) and this is what it looks like in miniature."""
    seq = [r for r in rows if r.get("kind") == kind
           and (not source or r.get("source") == source)]
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
    # THE ONE THING WORTH SAYING UNPROMPTED ABOUT SLEEP, and it is not "you are asleep" --
    # he knows. It is that he has just stopped being.
    if f.get("just_woke"):
        m = f.get("woke_mins_ago")
        bits.append("he was asleep until about %s"
                    % ("a few minutes ago" if not m or m < 10 else "%d minutes ago" % m))
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
