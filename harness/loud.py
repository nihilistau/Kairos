"""loud — what a broad `except Exception` is about to discard, at the right volume.

THE FAILURE THIS ANSWERS (2026-08-28). `reflect_tick` wraps its body in `except Exception`
and returns None, which is also what it returns on a quiet night. A refactor left a name
unimported, every tick raised NameError, and the whole conclusion lane was dead for five and
a half hours while the suite stayed green. The operator noticed before any instrument did.

A broad handler is often right — Home Assistant restarts, the daemon goes away, a store is
mid-write — and none of that should cost her a turn. But NameError, AttributeError,
TypeError and ImportError are not the world being unreliable. They are the code being wrong,
they never fix themselves, and they must not be indistinguishable from "nothing happened".

SO THE SHAPE STAYS AND THE VOLUME CHANGES: environment at debug, our own bugs at warning,
with the type named so it is greppable.

IT LIVES HERE, not in `kairos`, BECAUSE IT HAPPENED TWICE. The recall lane's IDF table
swallowed a NameError the same way three days later and answered with an empty table, which
is also what it answers when there is nothing to say — the floor it computes silently became
zero and every measurement taken over it was of code that never ran. A rule enforced in one
package is not enforced in the other, which is AGENTS.md §0 with a different subject. One
copy, and the lane is a parameter.
"""

from __future__ import annotations

# Not the world being unreliable. Our own code being wrong.
OURS = (NameError, AttributeError, TypeError, ImportError)


def swallowed(logger, where: str, exc: BaseException, lane: str = "") -> None:
    """Log a discarded exception: programming errors LOUD, the world quiet."""
    tag = ("[%s] " % lane) if lane else ""
    if isinstance(exc, OURS):
        logger.warning("%s%s swallowed a %s: %s", tag, where, type(exc).__name__, exc)
    else:
        logger.debug("%s%s: %s: %s", tag, where, type(exc).__name__, exc)
