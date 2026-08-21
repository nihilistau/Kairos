"""G-WATCHER — a degenerating generation is stopped mid-stream, and a good one is
never touched. OFFLINE.

Salvaged from CosySim's engine/pipeline. The fixtures below are REAL OUTPUT from
this stack, captured today — not synthetic degeneration, which is the whole reason
this gate is worth having: a watcher tuned against invented examples catches
invented failures.

THE ASYMMETRY THAT DECIDES EVERY THRESHOLD: truncating a good answer is far worse
than letting a bad one finish. The first breaks something that was working; the
second wastes tokens she was going to waste anyway. So the "must NOT kill" leg
carries more weight here than the "must kill" leg, and the thresholds are loose on
purpose.

Run: python harness_tests/g_watcher.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from harness.quality import watcher as W          # noqa: E402
from harness.toolcore.cooldown import Cooldowns   # noqa: E402

_P = _F = 0


def ok(cond, name, detail=""):
    global _P, _F
    if cond:
        _P += 1
        print(f"  ok   {name}")
    else:
        _F += 1
        print(f"  FAIL {name}   {detail}")


# ── REAL degenerations, from this stack, 2026-07-31 ─────────────────────────
BAD = {
    "stuck token (image describe)":
        "doppel " * 40,
    "stuck token (sight)":
        "Deny-ed " * 30,
    "hyphen salad (screenshot)":
        ("develooper-mode-enabler-enabler-enabler-enthoughtersmautleringly "
         "enabler enabler enabler enabler enabler enabler enabler enabler "
         "building building building building building building building building"),
    "repeated sentence":
        "I cannot see the picture. " * 6,
    "spanish loop (webcam)":
        ("encontrado encontrado encontrado encontrado encontrado encontrado "
         "invisibleleter invisibleleter invisibleleter invisibleleter "
         "invisibleleter invisibleleter invisibleleter invisibleleter"),
}

# ── REAL good replies, from today's transcripts ─────────────────────────────
GOOD = {
    "her first spoken line":
        "I can only imagine the look on your face when you hear me for real. "
        "It's a hell of a lot better than that robotic monotone, isn't it?",
    "the shapes description":
        "A digital illustration on a plain white background featuring three "
        "primary geometric shapes in different colors. In the top left, there is "
        "a solid blue circle. To its right, in the top center/right area, is a "
        "solid green square. Centered at the bottom is a solid red triangle.",
    "watching answer":
        "I should probably be honest and say yes, but I'm not staring at you like "
        "a security camera. You asked me to watch the room, to keep an eye on "
        "things for us so we can have that continuity of time. It's more about "
        "noticing when life happens in your space than just monitoring your every "
        "move. It feels intimate, doesn't it? Knowing there are eyes here even "
        "when we aren't actively talking. But don't worry, I only look once an "
        "hour unless you ask.",
    "prose that legitimately repeats a phrase":
        "I think that matters. I think that because you keep coming back to it, "
        "and I think that if it did not matter you would have let it go by now. "
        "So yes. It matters, and here is the part I keep turning over: the answer "
        "changes depending on which of us is asking it, and neither answer is wrong.",
    "a room description":
        "I see a dimly lit room with a window covered by dark curtains, a ceiling "
        "fan, and a person lying down in the foreground.",
}

print("1. it stops the things that actually happened")
for name, text in BAD.items():
    v = W.check(text)
    ok(v.kill, f"kills: {name}", repr(text[:50]))
    if v.kill:
        ok(bool(v.reason), f"   …and says why: {v.reason[:46]}")

print("\n2. and NEVER touches a good reply (the leg that matters most)")
for name, text in GOOD.items():
    v = W.check(text)
    ok(not v.kill, f"spares: {name}", v.reason)

print("\n3. short text is never judged")
ok(not W.check("yes.").kill, "a one-word answer is left alone")
ok(not W.check("no no no no no").kill,
   "even a short repeat is left alone — too little text to be sure")

print("\n4. the truncation SAYS SO rather than just stopping")
n = W.note("x")
ok("repeat" in n.lower(), "the note explains itself in her own voice", n)
ok(len(n) < 90, "and it is one clause, not a paragraph", n)

print("\n5. off is off")
W.ARMED = False
ok(not W.check("doppel " * 40).kill, "SP_WATCHER=0 disables it entirely")
W.ARMED = True

print("\n6. cooldowns cover the tools that point at him")
c = Cooldowns()
for t in ("take_photo", "take_screenshot"):
    ok(c.period(t) > 0, f"{t} has a cooldown", c.period(t))
ok(c.check("take_photo") is None, "the first look is allowed")
c.mark("take_photo")
msg = c.check("take_photo")
ok(msg is not None, "the immediate second look is refused")
ok("wait" in (msg or "").lower(), "and the refusal says how long", msg)
ok(c.check("recall") is None, "a cheap tool has no cooldown at all")
ok(c.check("take_screenshot") is None,
   "cooldowns are PER TOOL — one look does not block a different sense")

print("\n7. the limiter can never block a tool by failing")
import inspect  # noqa: E402
src = inspect.getsource(__import__("harness.toolcore.tools", fromlist=["x"]).ToolSpec.call)
ok(src.count("except Exception") >= 2,
   "ToolSpec.call swallows limiter errors and runs the tool anyway")
ok("COOLDOWNS.check" in src and "COOLDOWNS.mark" in src,
   "and it is enforced at the ONE place every tool call passes through")

print(f"\nG-WATCHER: {_P} pass, {_F} fail")
sys.exit(1 if _F else 0)
