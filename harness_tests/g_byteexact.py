#!/usr/bin/env python
"""G-BYTEEXACT — an unconfigured caller gets OUTPUT, not silence.

THE BUG, TWICE IN ONE DAY
─────────────────────────
`byteexact` defaults to None, which means "don't send the key", which means the DAEMON decides —
and the daemon's default is ON. On your model the MoE FFN seam REFUSES byteexact outright and
answers with an **empty 200**. Not an error. A successful, empty reply.

Round one (2026-07-30 morning): two lanes in `harness/server/app.py` passed `byteexact=False`;
five did not — the kairos continuation, reflection, agency, task_loop and the CLI coder all got
silence. Round one's fix moved the resolution into `to_sp_chat()` so every lane passes through it.

Round two (2026-07-30 evening): that fix read `SP_GATEWAY_BYTEEXACT` — **a variable only serve.py
sets**. So it held for the gateway and for nothing else. Any process started by hand inherited no
such variable, `eff_bx` stayed None, the key was omitted, and the MoE answered empty again.

MEASURED: `voice_score.py 26b` ran twenty turns at ~32 s each, EVERY REPLY EMPTY, exit code 0,
and reported `len_median: 0.0` as a finding about her voice. That is the worst failure shape this
system produces — not a crash, a confident zero.

So the last resort is a VALUE, not a shrug: an unconfigured caller sends `byteexact=False`,
because sending nothing means silence and silence looks like she had nothing to say.

    FORALL configs with byteexact unset and no env: the key is PRESENT and False
    FORALL explicit values:                         the caller still wins, both ways
    FORALL env values:                              the profile's answer is honoured
    FORALL cases:                                   the key is never OMITTED

OFFLINE. No GPU, no daemon — this is about the request body, not the reply.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ.setdefault("SP_DAEMON_URL", "http://127.0.0.1:9")

from harness.inference.inference_config import InferenceConfig  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


MSGS = [{"role": "user", "content": "hello"}]


def body(cfg):
    return cfg.to_sp_chat(messages=list(MSGS))


def with_env(val):
    """Set/clear SP_GATEWAY_BYTEEXACT and return the resulting body."""
    if val is None:
        os.environ.pop("SP_GATEWAY_BYTEEXACT", None)
    else:
        os.environ["SP_GATEWAY_BYTEEXACT"] = val
    return body(InferenceConfig())


print("1. an unconfigured caller is never silent")
b = with_env(None)
check("the key is PRESENT even with nothing configured", "byteexact" in b, sorted(b))
check("...and it is False — the only value an MoE seam answers", b.get("byteexact") is False,
      b.get("byteexact"))
check("THE KEY IS NEVER OMITTED (omission is what produced the empty 200)",
      "byteexact" in b)

print("\n2. the profile's answer is honoured when serve.py set it")
check("env '1' -> True", with_env("1").get("byteexact") is True)
check("env '0' -> False", with_env("0").get("byteexact") is False)
check("env ' 1 ' (whitespace) -> True", with_env(" 1 ").get("byteexact") is True)
check("env garbage -> False, not a crash and not omitted",
      with_env("banana").get("byteexact") is False)

print("\n3. an explicit caller always wins")
for env in (None, "0", "1", "banana"):
    if env is None:
        os.environ.pop("SP_GATEWAY_BYTEEXACT", None)
    else:
        os.environ["SP_GATEWAY_BYTEEXACT"] = env
    check("explicit True beats env=%r" % env,
          body(InferenceConfig(byteexact=True)).get("byteexact") is True)
    check("explicit False beats env=%r" % env,
          body(InferenceConfig(byteexact=False)).get("byteexact") is False)
os.environ.pop("SP_GATEWAY_BYTEEXACT", None)

print("\n4. the warning fires, once, and only when nothing was configured")
import harness.inference.inference_config as IC  # noqa: E402

IC._WARNED["bx"] = False
records = []
import logging  # noqa: E402


class Grab(logging.Handler):
    def emit(self, r):
        records.append(r.getMessage())


h = Grab()
IC._log.addHandler(h)
IC._log.setLevel(logging.WARNING)
with_env(None)
n_after_first = len(records)
with_env(None)
with_env(None)
check("it warns when nothing is configured", n_after_first == 1, records)
check("...and NOT once per call (noise is how 20 empty turns went unnoticed)",
      len(records) == 1, len(records))
check("the warning names the cause", records and "SP_GATEWAY_BYTEEXACT" in records[0])
IC._WARNED["bx"] = False
records.clear()
with_env("0")
check("no warning when the profile DID answer", records == [], records)
IC._log.removeHandler(h)

print("\n5. every lane goes through this one door")
# The round-one fix was "resolve it where every lane must pass". Assert that no lane builds a
# request body of its own — to_sp_chat is the only builder, so there is nowhere else to forget.
import inspect  # noqa: E402
import re  # noqa: E402

offenders = []
for base, _dirs, files in os.walk(os.path.join(ROOT, "harness")):
    for fn in files:
        if not fn.endswith(".py"):
            continue
        p = os.path.join(base, fn)
        with open(p, encoding="utf-8") as f:
            src = f.read()
        # a lane that posts to /v1/chat must not hand-build the body dict
        if "/v1/chat" in src and re.search(r'"messages"\s*:\s*\[', src) \
                and "to_sp_chat" not in src and "inference_config" not in fn:
            offenders.append(os.path.relpath(p, ROOT))
check("no module hand-builds a /v1/chat body outside to_sp_chat", not offenders, offenders)
check("to_sp_chat is the builder", "byteexact" in inspect.getsource(InferenceConfig.to_sp_chat))

print("\nG-BYTEEXACT: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_byteexact.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_byteexact", "pass": PASS, "fail": FAIL,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
