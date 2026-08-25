"""The HTTP client. Small on purpose: read states, say whether it is reachable, never raise.

Home Assistant has a large API and this uses four bytes of it. That is deliberate — every
endpoint added here is a thing that can fail mid-turn, and the only reason this framework
exists is to carry a handful of numbers that no local sensor can produce.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# The default is the stack in harness/homeassistant/stack, on this machine. Loopback,
# because that is where it runs; a remote instance is a decision and gets an explicit URL.
DEFAULT_URL = "http://localhost:8123"

# How long we are willing to make him wait. Home Assistant answers /api/states in
# milliseconds when healthy; if it does not, the right answer is to give up and say so
# rather than to hold a turn open.
TIMEOUT_S = 6.0


def url() -> str:
    """Where Home Assistant is. `SP_HA_URL`, else the local stack."""
    return (os.environ.get("SP_HA_URL") or DEFAULT_URL).rstrip("/")


def token() -> Optional[str]:
    """The long-lived access token, or None.

    THE CREDENTIAL IS NOT CONFIGURATION. It is read from the environment or from a file
    under `var/`, and it is never in a profile, never in the tree and never in a log,
    because everything in `profiles/` is committed and everything committed is exported.
    A token in a TOML file is a token in the public repository two weeks later.

    Order: SP_HA_TOKEN, then SP_HA_TOKEN_FILE, then var/ha_token."""
    t = (os.environ.get("SP_HA_TOKEN") or "").strip()
    if t:
        return t
    # `SP_HA_TOKEN_FILE` is set by serve.py from its own VAR, the way every other path in
    # this tree is. The literal is only the fallback for running outside serve.py -- an
    # earlier version invented an `SP_VAR_DIR` for this, which was a second spelling of
    # something serve.py already owns, and G-SEM-CONSERVE said so.
    path = os.environ.get("SP_HA_TOKEN_FILE") or os.path.join("var", "ha_token")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            t = fh.read().strip()
        return t or None
    except OSError:
        return None


def configured() -> bool:
    """Is there anything to talk to? A missing token means OFF, not broken.

    This is the switch. The framework does nothing at all until a token exists, so
    importing it, shipping it and defaulting it on costs nothing and surprises nobody."""
    return bool(token())


class HAClient:
    """One instance per caller; cheap to make. Holds no connection and no state worth
    losing, so a caller may build one per poll and throw it away."""

    def __init__(self, base: Optional[str] = None, tok: Optional[str] = None) -> None:
        self.base = (base or url()).rstrip("/")
        self.token = tok if tok is not None else token()

    # ── the one primitive ───────────────────────────────────────────────────────────
    def _get(self, path: str) -> Tuple[Optional[Any], str]:
        """(payload, why). `why` is empty on success and a SENTENCE on failure.

        NEVER RAISES. Home Assistant is a container that restarts on upgrade, and a
        companion that throws mid-turn because somebody's smart-home server is applying an
        update has confused a nice-to-have for a dependency."""
        if not self.token:
            return None, "no Home Assistant token — the framework is off"
        try:
            # BUILT INSIDE THE TRY, not above it. It was outside, and a mutant that removed
            # the guard above turned `"Bearer " + None` into an uncaught TypeError — which
            # means "never raises" was being held up by the guard rather than by the
            # handler. Two rules leaning on one check is how both fail at once.
            req = urllib.request.Request(
                self.base + path,
                headers={"Authorization": "Bearer " + str(self.token),
                         "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                return json.loads(r.read().decode("utf-8")), ""
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                # Worth its own sentence: a token that WAS working and now is not has
                # almost always been revoked by someone rotating credentials, and
                # "unauthorized" sends you looking at the network instead.
                return None, ("Home Assistant refused the token (HTTP %d) — it may have "
                              "been revoked; make a new long-lived token" % e.code)
            return None, "Home Assistant answered HTTP %d" % e.code
        except urllib.error.URLError as e:
            return None, "cannot reach Home Assistant at %s (%s)" % (self.base, e.reason)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            return None, "Home Assistant gave something unreadable (%s)" % type(e).__name__

    # ── what anyone actually needs ──────────────────────────────────────────────────
    def alive(self) -> Tuple[bool, str]:
        """Is it up and is the token good? One call, used by the panel and the gate."""
        d, why = self._get("/api/")
        if why:
            return False, why
        return bool(isinstance(d, dict) and d.get("message")), ""

    def states(self) -> Tuple[List[dict], str]:
        """Every entity and its current state. This is the whole read path.

        One call rather than one per entity, because the interesting entities are
        discovered by suffix (see bridge.MAPPINGS) and their ids depend on what he named
        his phone — so we cannot know them in advance, and asking for all of them once is
        cheaper than asking for the wrong ones repeatedly."""
        d, why = self._get("/api/states")
        if why:
            return [], why
        return (d if isinstance(d, list) else []), ""

    def state_of(self, entity_id: str) -> Tuple[Optional[dict], str]:
        return self._get("/api/states/" + entity_id)


def measured_at_of(state: dict) -> Optional[float]:
    """WHEN THE VALUE WAS ACTUALLY MEASURED — which is NOT `last_updated` (2026-08-26).

    Caught live, and it would have been a confident lie the first night it ran. His phone's
    sleep confidence read 79 with `last_updated` twenty-five minutes old, so the bridge
    would have recorded a fresh, high-confidence "asleep" while he sat here talking. Pulling
    twenty-six hours of history showed ONE data point, from the previous morning: the phone
    had not reported in over a day because the server was down.

    `last_updated` was the moment HOME ASSISTANT RESTARTED AND RESTORED THE STATE. It is the
    age of the row in Home Assistant's memory, not the age of the reading, and after any
    restart every stale sensor in the house looks brand new.

    So three sources, best first:

      1. `attributes.timestamp` — epoch MILLISECONDS, and what the Sleep API itself stamped
         the event with. Authoritative when present.
      2. `last_changed` — when the VALUE last moved. Survives an attribute-only update,
         which `last_updated` does not.
      3. `last_updated` — the fallback, and the one that lies after a restart.

    Whatever comes back is still bounded downstream: `bridge._MAX_AGE_S` refuses a reading
    too old to date honestly, and `ingest.MAX_BACKDATE_S` refuses to backdate it that far.
    Those two are why the twenty-six-hour reading is dropped rather than believed."""
    attrs = state.get("attributes") or {}
    ts = attrs.get("timestamp")
    if ts is not None:
        try:
            v = float(ts)
            # Epoch MILLISECONDS if it is far too large to be seconds. 1e11 seconds is the
            # year 5138; 1e11 milliseconds is 1973. Nothing real sits between them.
            if v > 1e11:
                v /= 1000.0
            if 1e9 < v < 4e9:                    # 2001..2096, i.e. a plausible epoch
                return v
        except (TypeError, ValueError):
            pass
    for key in ("last_changed", "last_updated"):
        t = parse_ha_time(str(state.get(key) or ""))
        if t is not None:
            return t
    return None


def parse_ha_time(s: str) -> Optional[float]:
    """Home Assistant's `last_updated` -> epoch seconds, or None.

    It emits ISO 8601 with a real offset ("2026-08-26T21:40:03.123456+00:00"). Python's
    fromisoformat handles it on 3.11+; the fallback exists because a timestamp we cannot
    parse must become None rather than now() — dating somebody else's reading to the
    moment we read it is how a stale number gets treated as fresh."""
    if not s:
        return None
    try:
        import datetime as _dt
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None
