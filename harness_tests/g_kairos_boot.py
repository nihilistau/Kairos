"""G-KAIROS-BOOT — the engine-agnostic stack boots against ANY OpenAI endpoint and holds a
conversation with memory and the room. LIVE (any backend): needs a running gateway that was
started with an [engine] kind="openai" profile (profiles/companion.toml) and an endpoint
that answers /v1/models. Skips (exit 2) when neither is reachable.

    set SP_BOOT_GATEWAY=http://127.0.0.1:8810   (default 8800)
    python harness_tests/g_kairos_boot.py

The acceptance run for the Kairos export (2026-08-21 plan, Phase 4): /health says the
engine kind and warm; the room serves; a turn streams at least one delta and ends; a fact
remembered is listed live and recalled after a gateway-only bounce is NOT part of this
gate (it needs the operator's bounce) — it checks the fact is in the registry and that
/v1/memory shows it; the kairos outbox polls; /v1/speak/status answers; /v1/system names
the external engine and refuses a full restart politely.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, skip, utf8_stdout  # noqa: E402

utf8_stdout()
GW = os.environ.get("SP_BOOT_GATEWAY", "http://127.0.0.1:8800").rstrip("/")


def get(path, timeout=10):
    with urllib.request.urlopen(GW + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def post(path, body, timeout=300):
    req = urllib.request.Request(GW + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        # a polite refusal travels as JSON on a 400 (/v1/system); the body IS the answer
        return e.read().decode("utf-8", "replace")


try:
    h = get("/health", 5)
except Exception as exc:
    skip("no gateway at %s (%s)" % (GW, exc), "G-KAIROS-BOOT")
eng = (h or {}).get("engine") or {}
if eng.get("kind") != "openai":
    skip("the gateway at %s is on the '%s' backend, not openai — start it with "
         "profiles/companion.toml" % (GW, eng.get("kind")), "G-KAIROS-BOOT")

print("1. THE STACK IS UP ON AN EXTERNAL ENGINE, AND SAYS SO")
check("/health is ok and warm (nothing to warm on a foreign endpoint)", h.get("ok") and h.get("warm"), h)
check("/health names the engine kind and base_url", eng.get("kind") == "openai" and eng.get("base_url"), eng)
sysj = get("/v1/system")
check("/v1/system says the engine is external and a full restart is off the table",
      sysj.get("engine", {}).get("kind") == "openai" and sysj.get("restartable") is False
      and sysj.get("gateway_bounce") is True, sysj)
req = urllib.request.Request(GW + "/room/")
with urllib.request.urlopen(req, timeout=10) as r:
    room = r.read().decode("utf-8", "replace")
check("the room serves", "assets/" in room and r.status == 200)

print("\n2. A TURN STREAMS, AND IS REMEMBERED")
sess = "gkb%d" % (int(time.time()) % 100000)
fact = "My favourite tea is lapsang souchong, gate %s" % sess
deltas = 0
raw = post("/v1/chat", {"messages": [{"role": "user", "content":
                                      "Remember this and reply in one short sentence: " + fact}],
                        "session_id": sess, "max_tokens": 96}, timeout=600)
for line in raw.splitlines():
    if line.startswith("data:") and '"delta"' in line:
        deltas += 1
errs = [l for l in raw.splitlines() if l.startswith("data:") and '"error"' in l]
check("at least one delta streamed and the stream ended", deltas >= 1 and "[DONE]" in raw, deltas)
check("...and the engine answered (no error event in the stream — a 401 is not a turn)", not errs, errs[:2])
time.sleep(2.0)
mem = get("/v1/memory")
rows = mem.get("facts") or mem.get("rows") or mem.get("memories") or mem.get("live") or []   # /v1/memory -> {count, facts, health}
hit = any("lapsang" in json.dumps(r).lower() for r in rows) if isinstance(rows, list) else ("lapsang" in json.dumps(mem).lower())
check("the fact landed in her memory (listed live by /v1/memory)", hit,
      "rows=%d" % (len(rows) if isinstance(rows, list) else -1))

print("\n3. THE REST OF THE ROOM ANSWERS")
ob = get("/v1/kairos/outbox?session=" + sess)
check("the kairos outbox polls without error", isinstance(ob.get("messages"), list))
sp = get("/v1/speak/status")
check("/v1/speak/status answers with the live voice resolution", isinstance(sp.get("live"), dict), sp)
cat = get("/v1/catalog")
check("/v1/catalog answers", cat.get("ok") is True)
tun = get("/v1/tuning")
check("/v1/tuning answers with the eot_bias knob tagged sp-only",
      any(k.get("key") == "decode.eot_bias" and k.get("engine") == "sp" for k in tun.get("knobs", [])))
try:
    st = json.loads(post("/v1/system", {"op": "restart"}, timeout=30))
    check("a full restart is refused politely (external engine)", st.get("ok") is False and "external" in json.dumps(st).lower(), st)
except Exception as exc:
    check("a full restart is refused politely (external engine)", False, str(exc))

finish("G-KAIROS-BOOT")
