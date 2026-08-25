"""HOME ASSISTANT — the house, as a source she can be present to.

A SEPARATE FRAMEWORK, deliberately. It sits beside `harness/telemetry/` rather than inside
it, because the two answer different questions and have different failure modes: the watch
agent is ours and posts to us, while Home Assistant is somebody else's server that we ask.
Folding this into telemetry would put a network client with credentials behind a door whose
whole design is "the only writer is the agent on his wrist".

WHAT IT IS FOR, in one line: Home Assistant knows things about him that no sensor we can
reach will tell us, and the first of them is whether he is asleep.

    Google's Sleep API produces a calibrated confidence every ten minutes. It is not a
    sensor — it is a classifier inside Play Services — so no amount of `SensorManager`
    reaches it, and every sleep-capable sensor on his watch is behind a Samsung signature
    permission (see docs/TELEMETRY.md). Home Assistant's companion app already computes it
    and calls it "Sleep Confidence". `harness/telemetry/store.py` has had a
    `sleep_confidence` kind and a reader waiting for it since 2026-08-26. This framework is
    the piece that carries one to the other.

THE RULES IT INHERITS, and they are not negotiable because they are what makes his body
safe to hand her at all:

  1. **It is not a second door.** Everything this framework learns is written through
     `telemetry.ingest.record()` — the existing writer, with its anon gate, its one clock
     and its shape rules. A framework that wrote to the store directly would be a second
     set of rules inside a month, and the anon gate is the one that must never be second.
  2. **Off until configured.** No URL and no token means every entry point returns
     empty. A companion that quietly starts talking to a server because a package exists
     is not a feature.
  3. **It never raises.** Home Assistant is a container that restarts, upgrades and falls
     over. None of that may cost him a turn, so every call answers with a value and a
     reason, never an exception.
  4. **The credential is not configuration.** The long-lived token lives in `var/` or the
     environment, never in a profile and never in the tree — see `client.token()`.
  5. **Measured, not asserted.** What was read, from which entity, and when, is on the
     record — because "she said I was asleep" needs an answer better than "the computer
     thought so".
"""

from __future__ import annotations

from .client import HAClient, configured, token, url          # noqa: F401
from .bridge import MAPPINGS, poll_once, discover, status     # noqa: F401
from .house import present, read                              # noqa: F401

__all__ = [
    "HAClient", "configured", "token", "url",
    "MAPPINGS", "poll_once", "discover", "status",
    "present", "read",
]
