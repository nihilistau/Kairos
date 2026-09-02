"""G-CONTINUATION-MARGIN — the continuation lane, DRIVEN, not read.

CONTINUE and EXPAND are the two impulses that need the native engine: both sit behind
`if eot_margin is not None`, and `eot_margin` is in SP_CAPS and not in OPENAI_CAPS. That
makes this lane the honest answer to "what do I lose on a foreign endpoint?", and it is
published in kairos-engine's README — so it had better be measured rather than described.

Measuring it (2026-09-02) found two defects in it, both of the same shape: ARITHMETIC
WRITTEN FOR A POSITIVE THRESHOLD, still running against a negative one.

  §2  SP_ENGINE_MARGIN_APPROX=1 set eot_margin = 0.0 to mean "cut off". CONTINUE fires on
      `margin < cfg.continue_margin` = -18.50. 0.0 is above it — above the FINISHED median
      band, even — so the documented opt-in fired nothing, ever, on either calibration.

  §3  `urgency = (continue_margin - margin) / max(continue_margin, 1e-6)`. The guard is a
      divide-by-zero guard for a POSITIVE threshold. This threshold has never been
      positive, so the denominator was always 1e-6, urgency always clamped to 1.0, and the
      1.5-4.0s gradient always returned 1.5s.

Neither would be caught by reading the source: both lines look exactly like what they were
meant to do. So every leg here CALLS `decide()` and asserts the Impulse it returns.

Lane: OFFLINE (pure policy + one fake backend response; no daemon, no GPU).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness_tests._gate import sandbox, check, finish  # noqa: E402

sandbox()  # FIRST, before any harness. import

from harness.kairos import impulse as I  # noqa: E402
from harness.inference.backends import OPENAI_CAPS, SP_CAPS  # noqa: E402


def _state(now, spoke_ago=3600.0, user_ago=20.0, unanswered=0):
    """A turn she may speak on: cooldown long expired, he is present and just spoke."""
    st = I.TurnState()
    st.last_spoke_at = now - spoke_ago
    st.last_user_at = now - user_ago
    st.last_conv_at = now - user_ago
    st.unanswered = unanswered
    return st


def _decide(cfg, now, margin, **kw):
    return I.decide(cfg=cfg, state=_state(now, **kw), now=now,
                    reply_text="I was in the middle of saying that the thing about it is",
                    eot_margin=margin, due_notes=[])


now = time.monotonic()
# continue_enabled=True: CONTINUE/EXPAND are OFF by default since 2026-09-02 (the operator), and the legs below are ABOUT that lane — a gate that needs a feature turns it on rather than inheriting it
cfg = I.KairosConfig(enabled=True, continue_enabled=True)   # quiet_after_him_s = 0

# ── §1  THE CAPABILITY IS THE ENGINE'S, AND THE LANE IS BEHIND IT ────────────────────
print("1. EOT_MARGIN IS ENGINE-ONLY, AND CONTINUE/EXPAND ARE BEHIND IT")

check("eot_margin is an sp-daemon capability", "eot_margin" in SP_CAPS)
check("a generic OpenAI endpoint does NOT have it", "eot_margin" not in OPENAI_CAPS)

# The claim published in kairos-engine's README: without a margin the two lanes are dark.
d_none = _decide(cfg, now, None)
check("with NO margin, CONTINUE does not fire", d_none.action != I.CONTINUE, d_none.reason)
check("with NO margin, EXPAND does not fire", d_none.action != I.EXPAND, d_none.reason)

# ...and WITH one, CONTINUE does. Without this leg the one above is satisfied by the lane
# being broken outright, which is exactly the failure §2 turned out to be.
d_cut = _decide(cfg, now, -28.43)          # the model's measured CUT OFF median
check("with a genuine cut-off margin, CONTINUE FIRES", d_cut.action == I.CONTINUE, d_cut.reason)
check("a finished turn stays silent", _decide(cfg, now, 13.10).action != I.CONTINUE)

# ── §2  THE APPROXIMATION MUST ACTUALLY CROSS THE THRESHOLD ──────────────────────────
print("\n2. SP_ENGINE_MARGIN_APPROX REACHES THE LANE IT CLAIMS TO REACH")

# The value the backend used to send. It is not a cut-off by this policy's own numbers.
d_zero = _decide(cfg, now, 0.0)
check("margin 0.0 is NOT a cut-off (the old approximation's value)",
      d_zero.action != I.CONTINUE,
      "0.0 sits above continue_margin=%.2f — it reads as a finished turn" % cfg.continue_margin)

# The backend now states the FACT and leaves the arithmetic to the policy.
from harness.inference.backends import openai as _oai  # noqa: E402
_src = __import__("inspect").getsource(_oai.OpenAIClient.chat_stream)
check("the backend no longer fabricates a margin",
      '"eot_margin": None' in _src or "'eot_margin': None" in _src,
      "it must not invent a number it cannot measure")
check("the backend flags the `length` finish instead", "approx_cutoff" in _src)

# ...and the scheduler translates that flag into a margin the policy actually acts on.
from harness.kairos import scheduler as _ks  # noqa: E402
_ssrc = __import__("inspect").getsource(_ks.on_reply)
check("the scheduler translates approx_cutoff", "approx_cutoff" in _ssrc)

# THE BEHAVIOURAL LEG: the translated value must fire CONTINUE. This is the one that was
# red before the fix and is the whole point of the section.
_translated = float(cfg.continue_margin) - 1.0
d_approx = _decide(cfg, now, _translated)
check("the translated approximation FIRES CONTINUE",
      d_approx.action == I.CONTINUE,
      "margin %.2f -> %s (%s)" % (_translated, d_approx.action, d_approx.reason))

# ── §2b  THE WIRING ITSELF, END TO END ───────────────────────────────────────────────
# The leg above proves the POLICY acts on the translated value; it computes that value
# itself, so it would stay green with the backend and the scheduler disconnected. (The
# mutant proved exactly that: restoring `margin = 0.0` left it passing.) This section runs
# a real OpenAIClient against a real endpoint and pushes its real payload through the real
# on_reply, so the only thing asserted is the wire.
print("\n2b. THE WIRING, DRIVEN — real OpenAIClient -> real on_reply -> the policy")

import json as _json  # noqa: E402
import threading as _threading  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402


class _Fake(BaseHTTPRequestHandler):
    """Stops on `length` when asked for very few tokens — the one condition the knob is
    about. Any real endpoint reports that finish_reason; none report a logit gap."""

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = _json.loads(self.rfile.read(n) or b"{}")
        cut = body.get("max_tokens", 999) < 8
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for piece in ("I was about to say", " the thing"):
            self.wfile.write(("data: " + _json.dumps(
                {"choices": [{"delta": {"content": piece}, "finish_reason": None}]}) + "\n\n").encode())
        self.wfile.write(("data: " + _json.dumps(
            {"choices": [{"delta": {}, "finish_reason": "length" if cut else "stop"}]}) + "\n\n").encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


_srv = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
_threading.Thread(target=_srv.serve_forever, daemon=True).start()
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ["SP_ENGINE_BASE_URL"] = "http://127.0.0.1:%d" % _srv.server_address[1]
os.environ["SP_ENGINE_MODEL"] = "fake-1"
os.environ["SP_ENGINE_MARGIN_APPROX"] = "1"

from harness.inference import client as C  # noqa: E402
from harness.inference.inference_config import InferenceConfig  # noqa: E402

C._CLIENT = None
_cl = C.get_client()
check("the fake endpoint is behind the OpenAI backend", getattr(_cl, "kind", "") == "openai",
      type(_cl).__name__)
check("...and it does not claim the capability", "eot_margin" not in _cl.supports)

_gen = _cl.chat_stream(messages=[{"role": "user", "content": "go on"}],
                       config=InferenceConfig(max_tokens=4, temperature=0.2))
_resp = None
try:
    while True:
        next(_gen)
except StopIteration as _stop:
    _resp = _stop.value
check("the stream completed and returned a response", _resp is not None)
check("a `length` finish is reported as a FLAG, not as a fabricated number",
      _resp.kairos.get("eot_margin") is None and _resp.kairos.get("approx_cutoff") is True,
      repr(_resp.kairos))

# on_reply is the payload's only consumer. Patch the MODULE ATTRIBUTES — never a by-name
# import: installing a mutant rebinds the name and a snapshot taken at import would miss
# it, which is how a gate in this tree once printed 6/6 with the code under test deleted.
# `decide` is stubbed to SILENT so capturing the margin cannot also fire a continuation.
_seen = {}
_real_decide, _real_cfg = _ks.decide, _ks.live_config
_ks.live_config = lambda: cfg
_ks.decide = lambda **kw: (_seen.update(kw), I.Impulse(I.SILENT, reason="captured"))[1]
try:
    _ks.on_reply("g-cont-margin", "I was about to say the thing", _resp.kairos, lambda nudge: "")
finally:
    _ks.decide, _ks.live_config = _real_decide, _real_cfg
    os.environ.pop("SP_ENGINE_MARGIN_APPROX", None)
    C._CLIENT = None

check("the scheduler translated the flag into a margin at all",
      isinstance(_seen.get("eot_margin"), float),
      "decide() saw eot_margin=%r" % (_seen.get("eot_margin"),))
check("...and it is BELOW the threshold, so the lane actually opens",
      isinstance(_seen.get("eot_margin"), float) and _seen["eot_margin"] < cfg.continue_margin,
      "%r vs threshold %.2f" % (_seen.get("eot_margin"), cfg.continue_margin))

# ── §3  THE URGENCY GRADIENT VARIES ──────────────────────────────────────────────────
print("\n3. THE CONTINUATION DELAY IS A GRADIENT, NOT A CONSTANT")

lo, hi = cfg.continue_delay
shallow = _decide(cfg, now, cfg.continue_margin - 0.1)     # a hair under the line
deep = _decide(cfg, now, cfg.continue_margin * 2.5)        # far below it

check("both depths fire CONTINUE",
      shallow.action == I.CONTINUE and deep.action == I.CONTINUE,
      "%s / %s" % (shallow.action, deep.action))
check("a DEEP cut-off is resumed faster than a shallow one",
      deep.delay_s < shallow.delay_s,
      "deep %.2fs vs shallow %.2fs — if these are equal the denominator has collapsed again"
      % (deep.delay_s, shallow.delay_s))
check("a shallow cut-off waits near the long end of continue_delay",
      shallow.delay_s > lo + (hi - lo) * 0.5,
      "shallow %.2fs, band %.1f-%.1fs" % (shallow.delay_s, lo, hi))
check("a deep cut-off waits at the short end",
      abs(deep.delay_s - lo) < 0.01,
      "deep %.2fs, floor %.1fs" % (deep.delay_s, lo))
check("every delay stays inside the configured band",
      all(lo - 1e-9 <= d.delay_s <= hi + 1e-9 for d in (shallow, deep)),
      "%.2f / %.2f not in %.1f-%.1f" % (shallow.delay_s, deep.delay_s, lo, hi))

# The reason text distinguished nothing before: `eot_margin <= 0.0` was true on every path
# through this branch, so "edge of a thought" had never once printed.
check("a shallow cut-off is NOT described as a hard cut-off",
      "edge of a thought" in shallow.reason,
      shallow.reason)
check("a deep cut-off IS described as one", "CUT OFF" in deep.reason, deep.reason)

# ── §4  THE LANES THAT DO NOT NEED THE ENGINE STILL DO NOT ───────────────────────────
print("\n4. THE UNPROMPTED LANES ARE UNAFFECTED BY THE MARGIN'S ABSENCE")

# Published claim: spoke-up (CHECK_IN / MUSE / REMIND) and her own-time acts (SOLO) run on
# any backend. They live BELOW the margin block, so a None margin must not shortcut them.
_src_dec = __import__("inspect").getsource(I._decide)
# The guard gained `cfg.continue_enabled and` in front of it when the lane was turned
# off by default (2026-09-02), so anchor on the part that is ABOUT the margin.
_guard = _src_dec.find("eot_margin is not None")
check("the margin block exists and is bounded", _guard > 0)
for lane in ("REMIND", "SOLO", "MUSE"):
    at = _src_dec.find("%s," % lane)
    check("%s is decided BEFORE the margin block (so a None margin cannot suppress it)" % lane,
          0 < at < _guard,
          "%s at %d, margin block at %d" % (lane, at, _guard))

# CHECK_IN sits after it, so the margin block must not return early on a live margin when
# the quiet gate is open — the failure that would silence her check-ins on the sp stack.
_after = _src_dec[_guard:]
_ci = _after.find("CHECK_IN,")
check("CHECK_IN is reachable past the margin block", _ci > 0)
d_ci = _decide(cfg, now, 13.10, user_ago=cfg.checkin_idle_s + 60.0, spoke_ago=7200.0)
check("a finished turn falls THROUGH the margin block, it does not return from inside it",
      d_ci.action != I.CONTINUE and "continuation" not in d_ci.reason,
      "%s (%s)" % (d_ci.action, d_ci.reason))

finish("G-CONTINUATION-MARGIN")
