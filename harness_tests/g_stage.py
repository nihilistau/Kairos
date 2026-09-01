"""G-STAGE — the roleplay director, unlocked and no longer invisible.

The engine was always the good part: a system prompt is advice, so pacing and gating live
in Python where they are law. What it lacked was everything AROUND that.

  * `Scenario.opening` — a hand-written first line on all seven cards, READ BY NOTHING.
    She improvised her way in instead, on the one turn where improvising costs most.
  * `_SCENES` was a process global, so a gateway restart mid-scene lost the scenario, the
    rung, the beat count and which hooks had fired. "Who are you again?" is exactly the
    drift the director exists to prevent, delivered by the infrastructure.
  * `roleplay.dwell_scale` was declared, rendered with a slider, and read by NOTHING. Per
    docs/OFF-BY-DEFAULT.md a knob that visibly does nothing is a lie with a slider on it.
  * Nothing could ask "is a scene running, on which rung, how many beats" — so the ladder,
    which is the entire design, was invisible and a panel over it was impossible.
  * `offer()` promised "tell me a flavour and I'll build it" while `pick_from()` could only
    match seven hardcoded cards.

THE ORDERING IS THE SAFETY MODEL AND IT IS ASSERTED HERE, not assumed: HARD STOP beats
COOL beats HEAT. A stop wins at any rung, needs no gate, and never fails. This gate exists
partly so that ordering can never be refactored away quietly.

Offline. No GPU, no daemon.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import _src as _srcmod  # noqa: E402

SB = os.path.join(tempfile.gettempdir(), "_g_stage")
shutil.rmtree(SB, ignore_errors=True)
os.makedirs(os.path.join(SB, "scenes"))
os.makedirs(os.path.join(SB, "cards"))
os.environ["SP_SCENES_DIR"] = os.path.join(SB, "scenes")
os.environ["SP_SCENARIOS_DIR"] = os.path.join(SB, "cards")

from harness.roleplay import engine as rp      # noqa: E402
from harness.roleplay import ladder as L       # noqa: E402
from harness.roleplay import scenarios as SC   # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s %s" % (name, detail))


print("1. HER AUTHORED FIRST LINE, fired exactly once")
check("every built-in card HAS an opening",
      all(s.opening.strip() for s in SC.SCENARIOS),
      [s.id for s in SC.SCENARIOS if not s.opening.strip()])
rp.enter("s1", "penthouse")
first = rp.opening_for("s1")
check("the opening is returned on entry", bool(first))
check("...VERBATIM from the card, not paraphrased",
      first == SC.by_id("penthouse").opening)
check("...and exactly once — a second ask is None", rp.opening_for("s1") is None)

print("\n2. the scene SURVIVES a restart")
before = rp.active("s1")
before.heat = L.Heat(2, 1)
before.beats = 5
before.hooks_fired = [0, 1]
rp.touch("s1")
rp._SCENES.clear()                     # the process died
after = rp.active("s1")
check("scenario survives", after is not None and after.scenario.id == "penthouse")
check("rung survives", after.heat.level == 2)
check("beats-at-rung survives", after.heat.beats_at_level == 1)
check("beat count survives", after.beats == 5)
check("fired hooks survive", after.hooks_fired == [0, 1])
check("the opening does NOT fire again after a restart",
      after.opened and rp.opening_for("s1") is None)

print("\n3. leaving is final, and the file goes with it")
p = rp._path("s1")
rp.leave("s1")
check("no live scene", rp.active("s1") is None)
check("no orphan state on disk", not os.path.exists(p))

print("\n4. a session id is a FILENAME, so it is hashed not sanitised")
for evil in ("../../etc/passwd", "..\\..\\win.ini", ".hidden", "a" * 400, "a/b"):
    name = os.path.basename(rp._path(evil))
    inside = os.path.realpath(rp._path(evil)).startswith(
        os.path.realpath(rp.scenes_dir()) + os.sep)
    check("contained: %r" % evil[:18], inside and os.sep not in name and "/" not in name, name)

print("\n5. THE PACING DIAL IS CONNECTED (roleplay.dwell_scale)")
check("scale 2.0 doubles the beats a rung wants", L.dwell_for(1, 2.0) == 6)
check("scale 0.5 halves them", L.dwell_for(1, 0.5) == 2)
# The floor is the point: at zero every gate opens the instant he pushes, which is the
# lurch-to-explicit-on-turn-two failure the ladder exists to prevent.
check("it can never reach zero — the dial tunes the build, it cannot delete it",
      L.dwell_for(1, 0.0) >= 1 and L.dwell_for(3, -5) >= 1)
check("rung 7 is left alone (it is a wall, not a dwell)", L.dwell_for(7, 0.25) == 99)
h = L.Heat(1, 3)
check("and it CHANGES THE VERDICT, not just a number",
      L.gate_open(h, 7, 1.0)[0] is True and L.gate_open(h, 7, 2.0)[0] is False)
check("a garbage scale falls back to 1.0, it does not raise",
      L.dwell_for(1, "banana") == L.dwell_for(1, 1.0))

print("\n6. the ordering IS the safety model: STOP > COOL > HEAT")
hot = L.Heat(5, 9)
st, note = L.step(hot, "stop", 7)
check("a stop wins from rung 5", st.level == 0 and note.startswith("SCENE BROKEN"))
st, _ = L.step(hot, "stop, and kiss me harder", 7)
check("...even when the same line also pushes up", st.level == 0)
st, _ = L.step(hot, "slow down", 7)
check("cooling is never gated", st.level == 4)
st, _ = L.step(L.Heat(1, 0), "kiss me", 7)
check("escalation IS gated — no skipping on a fresh rung", st.level == 1)
st, _ = L.step(L.Heat(0, 0), "kiss me", 0)
check("the operator's ceiling holds at 0", st.level == 0)

print("\n7. the deck is a DIRECTORY, and a bad card cannot empty it")
n0 = len(SC.deck())
io.open(os.path.join(SB, "cards", "mine.json"), "w", encoding="utf-8").write(json.dumps({
    "id": "mine", "title": "A card he wrote", "premise": "p", "setting": "s",
    "role": "r", "voice": "v", "wants": "w", "friction": "f", "opening": "hello"}))
check("an authored card joins the deck", len(SC.deck()) == n0 + 1)
check("...and is reachable by id", SC.by_id("mine") is not None)
io.open(os.path.join(SB, "cards", "broken.json"), "w", encoding="utf-8").write("{ nope")
io.open(os.path.join(SB, "cards", "partial.json"), "w", encoding="utf-8").write(
    json.dumps({"id": "partial", "title": "no opening"}))
check("a malformed card is SKIPPED, not fatal", len(SC.deck()) == n0 + 1)
check("the built-in seven are the floor",
      all(SC.by_id(s.id) is not None for s in SC.SCENARIOS))
# A warning per read would be a log flood: the deck is re-read on every offer AND on
# every 5s poll of the stage panel, and a log that scrolls is a log nobody reads.
_before = len(SC._WARNED)
for _ in range(5):
    SC.deck()
check("a broken card warns ONCE, not once per read", len(SC._WARNED) == _before)
io.open(os.path.join(SB, "cards", "over.json"), "w", encoding="utf-8").write(json.dumps({
    "id": "penthouse", "title": "his own penthouse", "premise": "p", "setting": "s",
    "role": "r", "voice": "v", "wants": "w", "friction": "f", "opening": "his line"}))
check("an authored card REPLACES a built-in of the same id",
      SC.by_id("penthouse").opening == "his line")

print("\n8. introspection — what the stage panel reads")
os.remove(os.path.join(SB, "cards", "over.json"))
rp.enter("s2", "penthouse")
d = rp.status("s2")
check("the whole ladder is exposed", len(d["ladder"]) == len(L.LEVELS))
check("each rung carries its direction and dwell",
      all(r.get("direction") is not None and r.get("dwell") for r in d["ladder"]))
check("the live scene reports its rung and beats",
      d["scene"]["level_name"] == "none" and "beats" in d["scene"])
check("hooks and which have fired are visible",
      "hooks" in d["scene"] and "hooks_fired" in d["scene"])
check("the deck marks authored cards apart from built-ins",
      any(c["authored"] for c in d["deck"]) and any(not c["authored"] for c in d["deck"]))
# A stop you have to remember how to phrase is not a stop.
check("the stop words ship IN the payload", "stop" in (d.get("stop_words") or ""))
check("no scene -> scene is None, not a fake one", rp.status("nobody")["scene"] is None)

print("\n9. the gateway consults all of it")
app = _srcmod.pkg("harness", "server")
check("the opening is fired on entry", "rp.opening_for(" in app)
check("the pacing dial is read", 'tune.get("roleplay.dwell_scale")' in app)
check("the scene is persisted after the director moves it", "rp.touch(" in app)
check("the panel's session comes from _session_of, not a second rule",
      "_room_session" in app and "_session_of({})" in app)

rp.leave("s2")
shutil.rmtree(SB, ignore_errors=True)
print("\nG-STAGE: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_stage.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_stage", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
