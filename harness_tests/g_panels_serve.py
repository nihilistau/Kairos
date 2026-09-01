"""G-PANELS-SERVE — every window in the room still answers. LIVE (gateway :8800).

WHAT THIS EXISTS FOR (2026-09-01, Stage 2 of the app.py split). Thirty-five read-only panel
producers moved out of `app.py` into `harness/server/panels.py`. The offline suite cannot
prove that landed: it reads source text and drives a handful of the producers directly,
while what the room actually does is ask the GATEWAY, over HTTP, through a route table that
names each function. A panel that lost a dependency in the move answers `{"ok": false}` —
or 500s — and every offline gate stays green.

So this is the census: hit every GET route the room polls and require a real answer.

  * `_swallowed` was exactly this bug, caught by driving the functions rather than reading
    them: `_room_pulse` used `harness.loud` and panels.py had not imported it, so the panel
    raised NameError while the sweep was green.
  * `NEVER RAISES` is most of these functions' contract, which is precisely why a broken
    one is quiet: it returns `{"ok": false, "error": …}` and the window shows a stale
    number instead of a stack trace. `ok is False` is a FAIL here, not a pass — unless the
    subject is genuinely absent (no persona yet on a fresh clone), which `_absent` splits
    off the same way this repo splits absent from unreadable everywhere else.

The route list is read from `api.js` — the room's own list of what it calls — rather than
retyped here, because a census that keeps its own copy of the routes is the two-copies bug
wearing a lab coat, and it would miss the panel added next week.

    python harness_tests/g_panels_serve.py      # gateway :8800
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, skip, utf8_stdout  # noqa: E402
import _src as _srcmod  # noqa: E402

utf8_stdout()
BASE = os.environ.get("SP_GATEWAY_URL", "http://127.0.0.1:8800")

print("0. EVERY PANEL ANSWERS WHEN CALLED — no gateway needed")
# ── THE HALF THAT RUNS IN THE SWEEP (2026-09-01) ─────────────────────────────────────
# The HTTP census below needs a gateway, so on its own this gate would be a LIVE one the
# offline suite never runs — and the bug the split actually produced was catchable without
# a socket: `panels.py` had not imported `harness.loud`, so `_room_pulse` raised
# NameError. Reading the file would not have found it and no offline gate covered it.
# Calling the functions did. So the driver is first, and it is unconditional.
import inspect  # noqa: E402

from harness.server import panels as _panels  # noqa: E402

def _absent(err) -> bool:
    """Is this `ok: false` an ABSENT SUBJECT rather than a broken panel?

    ── FOUND BY THE EXPORT'S OWN SUITE (2026-09-01) ─────────────────────────────────
    The first cut treated every `ok: false` as a failure, and went red inside
    `../Kairos` on `_persona_get`: a fresh public clone has no `persona/` (it is
    gitignored and never exported — `persona-template/` ships instead, for the adopter to
    copy). "No persona yet" is a real state of a real tree, and a gate that convicts it
    is a gate that cannot run on the thing it ships in.

    The same absent-vs-broken split this repo applies everywhere else, one layer up:
    a missing FILE is the world, a `NameError` is us. `harness/loud.py`'s `OURS` is the
    list. Note the primary net is unaffected — the bug that actually shipped
    (`_room_pulse` with no `_swallowed`) RAISED, and raising is a failure however absent
    anything is.
    """
    e = str(err or "").lower()
    if any(x in e for x in ("nameerror", "attributeerror", "typeerror", "importerror")):
        return False                                   # ours, and it never fixes itself
    return any(x in e for x in ("no such file", "not found", "errno 2",
                                "does not exist", "no persona", "not configured"))


_PANEL = [n for n in dir(_panels)
          if n.endswith("_json") or n in ("warm_state", "_setup_key", "_roleplay_status",
                                          "_voice_status", "_voice_corpus", "_engine_info",
                                          "_voice_record_status", "_room_pulse",
                                          "_avatar_rung_and_ceiling", "_persona_get",
                                          "_persona_state", "_persona_layers")]
_raised, _said_false, _driven = [], [], 0
for _n in sorted(set(_PANEL)):
    _fn = getattr(_panels, _n)
    if not callable(_fn):
        continue
    _sig = inspect.signature(_fn)
    if any(p.default is inspect._empty
           and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
           for p in _sig.parameters.values()):
        continue                                 # takes required args; not a bare panel
    _driven += 1
    try:
        _r = _fn()
    except Exception as exc:                     # noqa: BLE001
        _raised.append("%s -> %s: %s" % (_n, type(exc).__name__, str(exc)[:60]))
        continue
    if isinstance(_r, dict) and _r.get("ok") is False and not _absent(_r.get("error")):
        _said_false.append("%s -> %s" % (_n, str(_r.get("error"))[:60]))
check("there are panels to drive", _driven >= 25, _driven)
check("not one of them raises", not _raised, _raised[:6])
# `NEVER RAISES` is their contract, so a broken one is QUIET: it answers ok:false and the
# window shows a stale number. That is a FAIL here — unless the subject is genuinely
# absent; see `_absent`.
check("...and not one of them answers ok:false for a reason of its own",
      not _said_false, _said_false[:6])

try:
    with urllib.request.urlopen(BASE + "/health", timeout=5) as r:
        _h = json.loads(r.read().decode("utf-8"))
except Exception as exc:                                   # noqa: BLE001
    print("\n  --   no gateway at %s (%s) — the HTTP census below needs one; "
          "the driver above already ran" % (BASE, type(exc).__name__))
    finish("G-PANELS-SERVE")

# ── THE ROOM'S OWN LIST, not a second copy of it ────────────────────────────────────
_api = _srcmod.text("ui", "src", "api.js")
GETS = sorted(set(re.findall(r"get\('(/v1/[^']+)'\)", _api)))
# Routes that take a required query string are not a bare GET; the room always passes one.
SKIP_Q = {"/v1/files/read", "/v1/memory/why", "/v1/telemetry/history", "/v1/avatar/file",
          "/v1/wardrobe/outfit", "/v1/wardrobe/look", "/v1/wardrobe/file", "/v1/music/file"}
GETS = [g for g in GETS if g.split("?")[0] not in SKIP_Q and "${" not in g]

print("1. THE ROOM'S GET ROUTES ANSWER — %d of them, read out of api.js" % len(GETS))
check("api.js yielded a real route list", len(GETS) >= 25, len(GETS))

_bad, _false = [], []
for path in GETS:
    try:
        with urllib.request.urlopen(BASE + path, timeout=20) as r:
            code, raw = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        _bad.append("%s -> HTTP %s" % (path, exc.code))
        continue
    except Exception as exc:                               # noqa: BLE001
        _bad.append("%s -> %s" % (path, type(exc).__name__))
        continue
    if code != 200:
        _bad.append("%s -> HTTP %d" % (path, code))
        continue
    try:
        d = json.loads(raw)
    except Exception:
        continue                    # a bytes route (a poster, a wav) — 200 is the claim
    # A PANEL THAT LOST A DEPENDENCY SAYS ok:false AND THE WINDOW SHOWS A STALE NUMBER.
    if isinstance(d, dict) and d.get("ok") is False and not _absent(d.get("error")):
        _false.append("%s -> %s" % (path, str(d.get("error"))[:60]))

check("every route answers 200", not _bad, _bad[:8])
check("...and none answers ok:false for a reason of its own", not _false, _false[:8])

print("\n2. AND THE ONES THAT READ WHAT THE SPLIT MOVED")
# `_room_pulse` is the aggregator: it reads `state.WARM` and `state.LAST_TURN_AT` — the
# alias and the rebindable scalar — and calls a dozen of its neighbours. If Stage 1 or
# Stage 2 broke a seam, this is the payload it breaks in.
with urllib.request.urlopen(BASE + "/v1/room/pulse", timeout=20) as r:
    pulse = json.loads(r.read().decode("utf-8"))
check("the pulse is ok", pulse.get("ok") is True, pulse.get("error"))
_pres = pulse.get("presence") or {}
check("...it reports the warm gate (state.WARM, through the alias)",
      isinstance(_pres.get("warm"), bool), _pres)
# `since_last_turn_s` is None until the first turn of the process, which is a real state —
# so this asserts the KEY is served, not a particular number.
check("...and the last-turn clock (state.LAST_TURN_AT, through the module)",
      "since_last_turn_s" in _pres, sorted(_pres))
check("...and her live dials, which come from a different producer",
      isinstance(pulse.get("her"), dict) and "mood" in (pulse.get("her") or {}),
      pulse.get("her"))

print("\n3. THE MODULE BOUNDARY IS THE ONE THE SPLIT DECLARED")
_p = _srcmod.text("harness", "server", "panels.py")
check("panels.py imports state, not app, at module level",
      "from harness.server import state as _state" in _p
      and "\nfrom harness.server import app" not in _p)
check("...and reaches app only lazily, inside the four shims",
      _p.count("from harness.server import app as _app") >= 4)
# ── ASSERTED AS IDENTITY, NOT AS A LINE OF TEXT (2026-09-01) ────────────────────────
# The first cut read app.py's source for the re-export line — and G-SRC-TRAP convicted it
# on the spot, correctly: this gate would have been the fortieth file-scoped pin, in the
# commit that exists to remove them. It is also the weaker check. `app._room_pulse is
# panels._room_pulse` proves the re-export WORKS; the presence of an import line proves
# somebody typed one.
from harness.server import app as _app_mod  # noqa: E402

_drifted = [n for n in sorted(set(_PANEL))
            if getattr(_app_mod, n, None) is not getattr(_panels, n, object())]
check("every panel is the SAME object under app.<name> and panels.<name>",
      not _drifted, _drifted[:6])

finish("G-PANELS-SERVE")
