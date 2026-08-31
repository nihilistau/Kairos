#!/usr/bin/env python
"""G-KAIROS-LOUD — a broad `except` in her own time may not swallow OUR bug silently.

WHAT THIS ANSWERS. `reflect_tick` wraps its body in `except Exception` and returns None —
which is also what it returns on a quiet night. On 2026-08-27 a refactor left `PersonModel`
imported in one function and used in the one split out of it; every tick raised NameError,
the handler ate it, and the whole conclusion lane was dead for five and a half hours while
149 gates stayed green. The operator noticed before any instrument did.

THE HANDLERS ARE MOSTLY RIGHT. Home Assistant restarts, the daemon goes away, a store is
mid-write — none of that should cost her a turn, and a companion that raises out of the
scheduler because somebody's smart-home server is upgrading has confused a nice-to-have for
a dependency. The shape stays.

WHAT CHANGES IS THE VOLUME. NameError, AttributeError, TypeError and ImportError are not
the world being unreliable; they are the code being wrong, they never fix themselves, and
they must not be indistinguishable from "nothing happened". `kairos.swallowed` logs those
at WARNING with the type named, and everything else at debug.

  1. THE HELPER TELLS THEM APART, and is loud about ours.
  2. EVERY LARGE HANDLER IN harness/kairos USES IT — a big `except Exception` that logs
     nothing at all is the exact shape that hid this one, so it fails the gate.
  3. SMALL GUARDS ARE LEFT ALONE. A three-line try around one import is not this bug and
     making it noisy would bury the signal in the thing meant to carry it.

OFFLINE. No GPU, no daemon.
"""
import ast
import io
import json
import logging
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from _gate import sandbox   # noqa: E402
sandbox("g_kairos_loud")

os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"

from harness.kairos import swallowed   # noqa: E402

PASS = FAIL = 0

# A handler bigger than this is covering real work, not guarding one lookup. Chosen so the
# incident's own handler (37 lines) is well inside and the many 3-6 line import guards are
# well outside; there is nothing between 6 and 10 in the tree today.
BIG = 8


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


class Cap(logging.Handler):
    def __init__(self):
        super().__init__()
        self.rows = []

    def emit(self, r):
        self.rows.append((r.levelno, r.getMessage()))


print("1. THE HELPER TELLS OUR BUGS FROM THE WORLD'S")
log = logging.getLogger("g_kairos_loud")
log.setLevel(logging.DEBUG)
cap = Cap()
log.addHandler(cap)

for exc in (NameError("name 'PersonModel' is not defined"),
            AttributeError("no attribute 'foo'"), TypeError("bad arg"),
            ImportError("no module")):
    cap.rows[:] = []
    swallowed(log, "somewhere", exc)
    lvl, msg = cap.rows[-1]
    check("%-14s is WARNING and names the type" % type(exc).__name__,
          lvl >= logging.WARNING and type(exc).__name__ in msg, (lvl, msg))

for exc in (OSError("connection reset"), ValueError("bad json"),
            KeyError("missing"), RuntimeError("busy")):
    cap.rows[:] = []
    swallowed(log, "somewhere", exc)
    lvl, _msg = cap.rows[-1]
    check("%-14s stays quiet — the world is allowed to be unreliable"
          % type(exc).__name__, lvl < logging.WARNING, lvl)

# THE INCIDENT ITSELF: the message must be greppable, because that is how it would have
# been found on the night rather than by him noticing the silence.
cap.rows[:] = []
swallowed(log, "ambient_silence", NameError("name 'PersonModel' is not defined"))
check("...and the incident's own line is greppable",
      "PersonModel" in cap.rows[-1][1] and "ambient_silence" in cap.rows[-1][1],
      cap.rows[-1][1])

print("\n2. EVERY LARGE HANDLER IN harness/kairos IS AUDIBLE")
bad = []
checked = 0
for fn in sorted(os.listdir(os.path.join(ROOT, "harness", "kairos"))):
    if not fn.endswith(".py"):
        continue
    p = os.path.join(ROOT, "harness", "kairos", fn)
    src = io.open(p, encoding="utf-8", errors="replace").read()
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Try):
            continue
        for h in node.handlers:
            if h.type is None or getattr(h.type, "id", "") != "Exception":
                continue
            if any(isinstance(n, ast.Raise) for n in ast.walk(h)):
                continue                      # it re-raises: not swallowing anything
            span = getattr(node, "end_lineno", node.lineno) - node.lineno
            if span < BIG:
                continue                      # a small guard around one lookup
            checked += 1
            audible = any(
                # ── THE ALIAS IS NOT THE BEHAVIOUR (2026-08-31) ──────────────────
                # This listed two spellings, and the tree-wide adoption imports the
                # helper as `_swallowed` in 87 files — so an audible handler read as a
                # silent one because of the name it was imported under. Same shape as
                # G-SUGGEST grading `w.id` when the row variable was renamed: a gate
                # that pins a spelling goes red on correct code and teaches its reader
                # to ignore it. Any local alias of loud.swallowed counts.
                (isinstance(n, ast.Name)
                 and (n.id in ("swallowed", "_sw", "_swallowed")
                      or n.id.endswith("swallowed")))
                or (isinstance(n, ast.Attribute)
                    and n.attr in ("warning", "error", "exception", "info"))
                for n in ast.walk(h))
            if not audible:
                bad.append("%s:%d (covers %d lines)" % (fn, node.lineno, span))
check("there are large handlers to check at all", checked >= 5, checked)
check("...and not one of them fails silently", not bad, bad)

print("\n3. SMALL GUARDS ARE LEFT ALONE")
# The rule must not have become "log everything". If it had, the 3-line import guards
# would all be noise and the one line that matters would be lost in them.
small_silent = 0
for fn in sorted(os.listdir(os.path.join(ROOT, "harness", "kairos"))):
    if not fn.endswith(".py"):
        continue
    src = io.open(os.path.join(ROOT, "harness", "kairos", fn),
                  encoding="utf-8", errors="replace").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Try) and (
                getattr(node, "end_lineno", node.lineno) - node.lineno) < BIG:
            for h in node.handlers:
                if h.type is not None and getattr(h.type, "id", "") == "Exception" \
                        and not any(isinstance(n, ast.Attribute) and n.attr in
                                    ("warning", "error", "exception", "info")
                                    for n in ast.walk(h)):
                    small_silent += 1
check("small guards are still allowed to be quiet", small_silent > 10, small_silent)

print("\nG-KAIROS-LOUD: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_kairos_loud.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_kairos_loud", "pass": PASS, "fail": FAIL,
               "big_handlers_checked": checked, "big_span": BIG,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
