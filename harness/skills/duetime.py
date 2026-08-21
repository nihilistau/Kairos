"""WHEN. Turning the words a person actually says into a timestamp.

A reminder whose time failed to parse is worse than no reminder: she says "I'll remind you
Friday", the store holds due_at="", nothing ever comes due, and he finds out by missing the
thing. So this parser has exactly one rule — IF IT CANNOT READ THE TIME, IT SAYS SO, and
the tool refuses the note rather than pinning a promise it cannot keep.

Why not make the model emit ISO8601? Because asking a 12B for "2026-07-17T09:00:00Z" is
asking for an off-by-one year, a dropped timezone, or a plausible-looking string that is
silently wrong — and there is no way to tell the difference downstream. The model is good
at hearing "friday"; a computer is good at knowing what date Friday is. Let each do its
own job.

Deliberately no dateutil: this runs in the harness, on a machine that must boot offline.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone

_WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}

_UNITS = {
    "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
    "day": 86400, "days": 86400,
    "week": 604800, "weeks": 604800,
}

_ISO = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{1,2}):(\d{2}))?")
_IN_N = re.compile(r"\bin\s+(\d+)\s*(min|mins|minute|minutes|hour|hours|hr|hrs|day|days|week|weeks)\b", re.I)
_CLOCK = re.compile(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I)


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _say(dt: datetime, lead: str = "") -> str:
    """What she SAYS BACK — and it always names the weekday and the date.

    LIVE, FIRST TRY. He said "remind me to defrost the freezer tomorrow at 8am". The store
    got it exactly right (Mon 13 Jul, 08:00). The tool handed her the phrase "tomorrow at
    08:00" — and she told him "I'll remind you on TUESDAY at 8am". She had no weekday in
    front of her, so she inferred one, and inferred it wrong.

    Saying the time back exists to catch a misheard time in the same breath it is made. It
    cannot do that if the confirmation itself leaves a blank for her to fill in. So there
    are no blanks: every confirmation carries the weekday AND the date, and she has nothing
    left to guess at."""
    stamp = dt.strftime("%A %d %b at %H:%M")          # "Monday 13 Jul at 08:00"
    return f"{lead} ({stamp})" if lead else stamp


def _clock_on(day: datetime, text: str, default_hour: int = 9) -> datetime:
    """Attach a time of day. Default 9am — a reminder with no hour means 'that morning',
    not 'that instant at midnight', which is when nobody is looking."""
    m = _CLOCK.search(text)
    hour, minute = default_hour, 0
    if m:
        h = int(m.group(1))
        minute = int(m.group(2) or 0)
        ap = (m.group(3) or "").lower()
        if ap == "pm" and h < 12:
            h += 12
        elif ap == "am" and h == 12:
            h = 0
        elif not ap and h <= 7:      # "at 5" on its own almost always means the evening
            h += 12
        if 0 <= h <= 23:
            hour = h
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def parse_due(text: str, now: datetime | None = None) -> tuple[str, str]:
    """('2026-07-17T09:00:00Z', 'on Friday at 09:00')  — or ('', '') if unreadable.

    The second value is what she SAYS BACK ("I'll remind you on Friday at 09:00"), so a
    misparse is caught by the human in the same breath it is made, instead of six days
    later when the reminder does not arrive."""
    t = (text or "").strip().lower()
    if not t:
        return "", ""
    now = now or datetime.now(timezone.utc)

    # 1. an explicit date, however it got here
    m = _ISO.match(t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            day = datetime(y, mo, d, tzinfo=timezone.utc)
        except ValueError:
            return "", ""
        if m.group(4):
            day = day.replace(hour=int(m.group(4)), minute=int(m.group(5) or 0))
        else:
            # LOOK FOR THE TIME IN WHAT IS LEFT, NOT IN THE DATE. "2026-07-17" parsed to
            # 19:00, because the clock regex found the "07" of the month, read it as seven
            # o'clock, and helpfully assumed the evening. A date is not a time; strip it
            # before looking for one.
            rest = t[m.end():]
            day = _clock_on(day, rest)
        return _fmt(day), _say(day)

    # 2. "in 2 hours" / "in 30 mins"
    m = _IN_N.search(t)
    if m:
        dt = now + timedelta(seconds=int(m.group(1)) * _UNITS[m.group(2).lower()])
        return _fmt(dt), _say(dt, f"in {m.group(1)} {m.group(2)}")

    # 3. today / tonight / tomorrow
    if "tonight" in t:
        dt = _clock_on(now, t, default_hour=20)
        return _fmt(dt), _say(dt, "tonight")
    if "tomorrow" in t:
        dt = _clock_on(now + timedelta(days=1), t)
        return _fmt(dt), _say(dt, "tomorrow")
    if "today" in t:
        dt = _clock_on(now, t)
        return _fmt(dt), _say(dt, "today")

    # 4. a weekday — "friday", "next monday". Always the NEXT one: nobody sets a reminder
    #    for a day that has already gone.
    for name, idx in _WEEKDAYS.items():
        if re.search(rf"\b{name}\b", t):
            ahead = (idx - now.weekday()) % 7
            if ahead == 0:
                ahead = 7                     # "friday" said ON a Friday means the next one
            if "next" in t and ahead < 7:
                ahead += 7
            dt = _clock_on(now + timedelta(days=ahead), t)
            return _fmt(dt), _say(dt)

    # 5. a bare clock time — "at 6pm" — means today if it is still ahead, else tomorrow
    if _CLOCK.search(t):
        dt = _clock_on(now, t)
        if dt <= now:
            dt = _clock_on(now + timedelta(days=1), t)
            return _fmt(dt), _say(dt, "tomorrow")
        return _fmt(dt), _say(dt, "today")

    return "", ""      # unreadable — and the caller REFUSES rather than promising
