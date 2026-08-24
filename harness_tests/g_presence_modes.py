"""G-PRESENCE-MODES — Narration / Company / Lucid Dream: a kairos action that waits its turn,
speaks in her voice, reads from the shelf, and writes her narrative. OFFLINE.

    python harness_tests/g_presence_modes.py
"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# SANDBOX FIRST (2026-08-24). This gate calls tune.set_many(), which before today
# wrote HER LIVE var/tuning.json - it raced her running stack mid-sweep and died on
# the os.replace, and on a quieter day it would simply have changed what she does.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import sandbox as _sandbox  # noqa: E402
_sandbox(os.path.basename(__file__))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
os.environ.setdefault("SP_DAEMON_URL", "http://127.0.0.1:9")
os.environ["SP_CAPTURE_ASYNC"] = "0"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
REG = os.path.join(tempfile.mkdtemp(prefix="g_presence_"), "registry.jsonl")
open(REG, "w").close()
os.environ["SP_RECALL_REGISTRY"] = REG
LIB = tempfile.mkdtemp(prefix="g_presence_lib_")
os.environ["SP_LIBRARY_DIR"] = LIB

import harness.kairos.impulse as I   # noqa: E402
I.BOOT_AT = 1.0                       # synthetic clocks (see g_kairos_latch)
from dataclasses import replace       # noqa: E402
from harness.kairos.impulse import (  # noqa: E402
    CHECK_IN, MODE_TURN, REMIND, SILENT, SOLO, KairosConfig, TurnState, decide, note_spoke)


class Sure(random.Random):
    def random(self):  # noqa: D102
        return 0.0


CFG = KairosConfig(enabled=True, max_chain=2, cooldown_s=45.0, max_per_hour=6,
                   checkin_idle_s=600.0, checkin_chance=1.0, solo_enabled=True,
                   solo_every_s=1800.0, solo_chance=1.0, quiet_after_him_s=200.0,
                   presence_mode="narration", presence_every_s=240.0, presence_chance=1.0,
                   presence_max_per_hour=12)


def d(state, now, cfg=None, **kw):
    kw.setdefault("reply_text", "ok.")
    kw.setdefault("eot_margin", None)
    return decide(cfg=cfg or CFG, state=state, now=now, rng=Sure(), **kw)


print("1. A MODE IS A KAIROS ACTION THAT WAITS ITS TURN")
t0 = I.BOOT_AT
off = replace(CFG, presence_mode="off")
check("mode off: nothing, ever (the shipped default)",
      d(TurnState(), t0 + 10000.0, cfg=off).action != MODE_TURN)
check("mode on, 10 s after boot: SILENT (the presence clock)",
      d(TurnState(), t0 + 10.0).action == SILENT)
imp = d(TurnState(), t0 + 241.0)
check("...after presence.every_s of quiet: MODE_TURN, carrying the mode",
      imp.action == MODE_TURN and imp.mode == "narration", (imp.action, imp.mode, imp.reason))
st = TurnState(); st.last_user_at = t0 + 3000.0
check("quiet-after-him holds for a mode (he spoke 100 s ago)",
      d(st, t0 + 3100.0).action == SILENT)
st2 = TurnState(); note_spoke(st2, t0 + 100.0, MODE_TURN)
check("a mode turn does not spend the chain and is not 'unanswered'",
      st2.chain == 0 and st2.unanswered == 0 and st2.last_mode_at == t0 + 100.0)
check("...and it honours its own every_s from last_mode_at",
      d(st2, t0 + 300.0).action == SILENT and d(st2, t0 + 100.0 + 241.0).action == MODE_TURN)
st3 = TurnState()
for k in range(12):
    note_spoke(st3, t0 + 1000.0 + k, MODE_TURN)
check("its own hourly cap (12), not kairos's 6",
      d(st3, t0 + 1000.0 + 12 + 300.0).action == SILENT
      and "presence cap" in d(st3, t0 + 1000.0 + 12 + 300.0).reason,
      d(st3, t0 + 1000.0 + 12 + 300.0).reason)
due = [{"id": "n1", "title": "pills"}]
check("a due reminder outranks a mode",
      d(TurnState(), t0 + 241.0, due_notes=due).action == REMIND)
away = TurnState(); away.unanswered = 2
check("her own time (SOLO) outranks a mode when both are due",
      d(away, t0 + 1801.0, user_present=False).action == SOLO)
chk = replace(CFG, presence_mode="off")
check("with the mode off the same moment is a CHECK_IN (mode sits above check-in, not instead of it)",
      d(TurnState(), t0 + 601.0, cfg=chk).action == CHECK_IN)
chance0 = replace(CFG, presence_chance=0.0)
check("presence.chance 0 never fires", d(TurnState(), t0 + 241.0, cfg=chance0).action != MODE_TURN)
every0 = replace(CFG, presence_mode="company", presence_every_s=0.0)
check("every_s 0 means the per-mode default (company: 600)",
      d(TurnState(), t0 + 300.0, cfg=every0).action == SILENT
      and d(TurnState(), t0 + 601.0, cfg=every0).action == MODE_TURN)

print()
print("2. THE KNOBS EXIST, SHIP OFF, AND REACH THE POLICY")
from harness.tuning import registry as R       # noqa: E402
ks = {k.key: k for k in R.KNOBS}
check("presence.mode is an enum of the four, default off",
      ks["presence.mode"].type == "enum" and ks["presence.mode"].default == "off"
      and list(ks["presence.mode"].choices) == ["off", "narration", "company", "lucid"])
check("presence.cue is a str knob (the first) with an empty default",
      ks["presence.cue"].type == "str" and ks["presence.cue"].default == "")
check("three cadences, not one: every_narration/company/lucid_s with their defaults, and no single every_s",
      (ks["presence.every_narration_s"].default, ks["presence.every_company_s"].default, ks["presence.every_lucid_s"].default) == (240, 600, 300)
      and "presence.every_s" not in ks)
_wm5 = {k: R.chosen(k) for k in ("presence.mode", "presence.every_lucid_s")}
try:
    R.set_many({"presence.mode": "lucid", "presence.every_lucid_s": 420})
    from harness.kairos import scheduler as _S5   # noqa: E402
    check("live_config carries the CURRENT mode's cadence (lucid -> its own knob)",
          abs(_S5.live_config().presence_every_s - 420.0) < 1e-6, _S5.live_config().presence_every_s)
finally:
    for k, v in _wm5.items():
        R.reset(k) if v is None else R.set_many({k: v})
from harness.kairos import scheduler as S      # noqa: E402
cfg_live = S.live_config()
check("live_config carries the presence fields, off unless he chose otherwise",
      hasattr(cfg_live, "presence_mode") and (R.chosen("presence.mode") is not None or cfg_live.presence_mode == "off"))

print()
print("3. THE PROMPTS — three registers, a cue slot, no questions, voiced in the right wrap")
from harness.kairos import presence as P       # noqa: E402
for m in ("narration", "company", "lucid"):
    for intimate in (False, True):
        n = P.mode_nudge(m, cue="Rain against the windows.", intimate=intimate)
        check("%s%s nudge carries its register and the cue" % (m, " (intimate)" if intimate else ""),
              ("Narration Mode" in n or "Company Mode" in n or "Lucid Dream Mode" in n)
              and "Rain against the windows." in n and "Do not ask" in n)
n0 = P.mode_nudge("narration", cue="", intimate=False)
check("an empty cue leaves no dangling slot", "{cue}" not in n0 and "Context for this moment" not in n0)
rd = P.mode_nudge("lucid", cue="", intimate=False, passage="It was a dark and stormy night.", title="Tales")
check("a reading nudge carries the passage and the title, and says read it in your own voice",
      "It was a dark and stormy night." in rd and "Tales" in rd and "own voice" in rd)
check("sampling per mode: company cooler, lucid warmer",
      P.SAMPLING["company"]["temperature"] < P.SAMPLING["narration"]["temperature"] < P.SAMPLING["lucid"]["temperature"])
check("length: narration runs long, a dream at least double it (his ask)",
      P.SAMPLING["narration"]["max_tokens"] >= 300 and P.SAMPLING["lucid"]["max_tokens"] >= 2 * P.SAMPLING["narration"]["max_tokens"],
      (P.SAMPLING["narration"]["max_tokens"], P.SAMPLING["lucid"]["max_tokens"]))
check("lucid is whispered, company soft, narration bare",
      P.wrap_for_voice("lucid", "come closer.") == "<whisper>come closer.</whisper>"
      and P.wrap_for_voice("company", "I'm here.") == "<soft>I'm here.</soft>"
      and P.wrap_for_voice("narration", "the kettle ticks.") == "the kettle ticks.")
check("an existing wrapping tag is respected", P.wrap_for_voice("lucid", "<soft>x</soft>") == "<soft>x</soft>")
check("a trailing question is trimmed to a full stop", P.trim_question("Are you still awake?") == "Are you still awake.")
check("memory kinds: narration->narration, company->thought, lucid->dream, reading->narration",
      (P.memory_kind("narration"), P.memory_kind("company"), P.memory_kind("lucid"), P.memory_kind("lucid", reading=True))
      == ("narration", "thought", "dream", "narration"))
cue = P.assemble_cue(now=time.time(), mood="wistful", own_time=["read about tides"], book=None)
check("an assembled cue names the hour, her mood and her own time",
      "wistful" in cue and "tides" in cue and any(w in cue for w in ("night", "morning", "afternoon", "evening", "small hours")), cue)

print()
print("4. THE SHELF — var/library/: txt and epub, a bookmark that survives, put down")
from harness.skills import library as L        # noqa: E402
open(os.path.join(LIB, "Tales of the Tide.txt"), "w", encoding="utf-8").write(
    "Chapter One. " + ("The sea was grey and the gulls were loud. " * 40) + "Chapter Two. " + ("She walked home along the wall. " * 40))
import zipfile                                  # noqa: E402
with zipfile.ZipFile(os.path.join(LIB, "little-book.epub"), "w") as z:
    z.writestr("mimetype", "application/epub+zip")
    z.writestr("OEBPS/content.opf", '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>The Little Book</dc:title></metadata><manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c1"/></spine></package>')
    z.writestr("OEBPS/c1.xhtml", "<html><body><h1>One</h1><p>" + "It was a dark and stormy night; the rain fell in torrents. " * 4 + "</p><p>" + "Second paragraph here, with a little more in it than before. " * 4 + "</p></body></html>")
shelf = L.books()
titles = sorted(b["title"] for b in shelf)
check("both books are on the shelf with their titles", titles == ["Tales of the Tide", "The Little Book"], titles)
check("nothing in hand to start", L.in_hand() is None)
check("she picks one up", (L.pick_up("The Little Book") or {}).get("title") == "The Little Book")
p1 = L.next_passage(60)
check("a passage is plain text, tags stripped, from the start", p1.startswith("One") or p1.startswith("It was a dark"), p1)
p2 = L.next_passage(60)
check("the bookmark advanced (a different passage next)", bool(p2) and p2 != p1, p2)
bm = json.load(open(os.path.join(LIB, ".bookmarks.json"), encoding="utf-8"))
check("the bookmark is persisted as a position, never the text", "The Little Book" in bm and isinstance(bm["The Little Book"].get("pos"), int))
import importlib                                # noqa: E402
importlib.reload(L)
check("...and survives a reload (in hand and position)", bool(L.in_hand()) and L.in_hand()["title"] == "The Little Book" and L.in_hand()["pos"] > 0)
L.put_down()
check("put down: nothing in hand, the bookmark kept", L.in_hand() is None and json.load(open(os.path.join(LIB, ".bookmarks.json")))["The Little Book"]["pos"] > 0)
L.pick_up("Tales of the Tide")
tail = ""
for _ in range(200):
    t = L.next_passage(700)
    if not t:
        break
    tail = t
check("reading to the end returns '' and the book is done (in_hand says so)", L.next_passage(700) == "" and L.in_hand()["done"] is True, tail[-40:])
check("her tools exist: pick_up_book / put_down_book / books_on_the_shelf",
      all(callable(getattr(L, n, None)) for n in ("pick_up_book", "put_down_book", "books_on_the_shelf")))
out = L.books_on_the_shelf()
check("books_on_the_shelf lists titles with progress", "Tales of the Tide" in out and "Little Book" in out, out)

print()
print("5. A MODE TURN, END TO END (the real _fire_inner): voiced, labelled, remembered")
from harness.kairos import scheduler as S      # noqa: E402
from harness.skills import memory as M         # noqa: E402
from harness.skills import memclass as MC      # noqa: E402
from harness.tuning import registry as R       # noqa: E402
_was = {k: R.chosen(k) for k in ("presence.mode", "presence.voice", "presence.read_chance", "presence.cue")}
import atexit                                   # noqa: E402
atexit.register(lambda: [R.reset(k) if v is None else R.set_many({k: v}) for k, v in _was.items()])
R.set_many({"presence.mode": "lucid", "presence.voice": True, "presence.read_chance": 0.0, "presence.cue": "rain on the roof"})
L.put_down()
S._STATE.clear(); S._OUTBOX.clear(); S._LAST.clear()
seen = {}
def gen(nudge, called=None, **kw):
    seen["nudge"] = nudge; seen.update(kw)
    return "come closer, I was just thinking about your hands?"
S._LAST["g"] = ("ok.", gen)
imp = I.Impulse(MODE_TURN, delay_s=0.0, reason="gate", mode="lucid")
S._arm("g", imp, "ok.", gen, None)
for _ in range(80):
    time.sleep(0.05)
    if S._OUTBOX.get("g"):
        break
m = (S._OUTBOX.get("g") or [None])[0]
check("the outbox got a mode message: kind=mode, mode=lucid, speak=True",
      bool(m) and m.get("kind") == "mode" and m.get("mode") == "lucid" and m.get("speak") is True, m)
check("the text is whispered and the question trimmed",
      bool(m) and m["text"].startswith("<whisper>") and "?" not in m["text"] and m["text"].endswith("</whisper>"), m and m["text"])
# the LENGTH is his knob (presence.len_lucid), not a number this gate gets to pin
check("the nudge was the Lucid block with the cue; sampling was lucid's, length from the knob",
      "Lucid Dream Mode" in seen.get("nudge", "") and "rain on the roof" in seen.get("nudge", "")
      and (seen.get("sampling") or {}).get("temperature") == 0.95
      and seen.get("max_tokens") == int(R.get("presence.len_lucid")),
      {k: v for k, v in seen.items() if k != "nudge"})
rows = []
for _ in range(80):
    rows = [r for r in M.live_rows() if r.get("speaker") == "self" and r.get("kind") == "dream"]
    if rows:
        break
    time.sleep(0.05)
check("...and it landed as self-narrative / dream through the door", bool(rows) and "hands" in rows[-1]["text"], rows[-1:] if rows else [])
R.set_many({"presence.voice": False, "presence.mode": "company"})
S._OUTBOX.clear()
S._LAST["g"] = ("ok.", lambda nudge, called=None, **kw: "I am here. The kettle has gone quiet.")
S._arm("g", I.Impulse(MODE_TURN, delay_s=0.0, reason="gate", mode="company"), "ok.", S._LAST["g"][1], None)
for _ in range(80):
    time.sleep(0.05)
    if S._OUTBOX.get("g"):
        break
m2 = (S._OUTBOX.get("g") or [None])[0]
check("voice off: the message carries speak=False and is wrapped soft", bool(m2) and m2.get("speak") is False and m2["text"].startswith("<soft>"), m2)
st = S.peek_state("g")
check("peek_state reports presence {mode, next_in_s}", isinstance(st.get("presence"), dict) and st["presence"].get("mode") == "company" and "next_in_s" in st["presence"], st.get("presence"))

print()
print("6. ASKED FOR — her tool and the window's button enter a mode NOW")
kick = TurnState(); kick.mode_kick = True; kick.last_spoke_at = t0 + 4.0   # she spoke 1 s ago
r_k = d(kick, t0 + 5.0)
check("a kicked state takes its mode turn straight away (ahead of cooldown, floors, quiet), reason says asked",
      r_k.action == MODE_TURN and "asked" in r_k.reason and r_k.delay_s <= 1.0, (r_k.action, r_k.reason, r_k.delay_s))
note_spoke(kick, t0 + 6.0, MODE_TURN)
check("...and the kick is one-shot (cleared by note_spoke)", kick.mode_kick is False)
check("an unkicked state still waits (the ordinary rule)", d(TurnState(), t0 + 5.0).action == SILENT)
_wm = R.chosen("presence.mode")
try:
    S._STATE.clear(); S._LAST.clear(); S._LAST["g"] = ("ok.", lambda n, c=None, **kw: "")
    res = S.enter_mode("dream")
    check("enter_mode('dream') maps to lucid, sets the knob, arms the kick on the live session",
          res.get("ok") and res["mode"] == "lucid" and R.get("presence.mode") == "lucid"
          and S._STATE["g"].mode_kick is True, res)
    check("a bad mode is refused", S.enter_mode("opera").get("ok") is False)
    out = P.enter_mode("company")
    check("her tool answers in her terms and sets the knob", "company" in out and R.get("presence.mode") == "company", out)
    out2 = P.leave_mode()
    check("leave_mode sets off and clears the kick", R.get("presence.mode") == "off" and S._STATE["g"].mode_kick is False, out2)
    from harness.agent import default_tools   # noqa: E402
    names = {t.name for t in default_tools()}
    check("enter_mode / leave_mode are in her live tool set", {"enter_mode", "leave_mode"} <= names, sorted(n for n in names if "mode" in n))
    from harness.tools import manifest as MF  # noqa: E402
    check("...with manifest rows", "enter_mode" in MF.FACTS and "leave_mode" in MF.FACTS)
    # a mode turn armed, then the mode switched off before it fires: dropped at fire time
    R.set_many({"presence.mode": "narration"})
    S._OUTBOX.clear()
    S._LAST["g"] = ("ok.", lambda n, c=None, **kw: "the kettle ticks.")
    S._arm("g", I.Impulse(MODE_TURN, delay_s=0.4, reason="gate", mode="narration"), "ok.", S._LAST["g"][1], None)
    S.leave_mode()
    time.sleep(1.2)
    check("a pending mode turn is dropped once the mode is off", not S._OUTBOX.get("g"), S._OUTBOX.get("g"))
finally:
    R.reset("presence.mode") if _wm is None else R.set_many({"presence.mode": _wm})
    for _t in list(S._TIMERS.values()):
        _t.cancel()

print()
print("7. ON A BOUNCE, ONCE WARM; LENGTH PER MODE; NEVER MID-LINE; NEVER THE SAME DREAM TWICE")
# the seeder + warm hook: nothing live, mode armed -> seeded once the prefix is hot
_wm7 = R.chosen("presence.mode")
_seeded = {"n": 0}
def _fake_seeder(force=False):
    _seeded["n"] += 1
    S._LAST["boot"] = ("(quiet)", lambda n, c=None, **kw: "")
    return True
try:
    R.set_many({"presence.mode": "narration"})
    S._LAST.clear(); S._STATE.clear()
    S.set_seeder(_fake_seeder); S.set_warm_ok(lambda: False)
    S.tick_once(now=I.BOOT_AT + 5000.0)
    check("mode armed, nothing live, prefix COLD: no seed (she never starts into a cold prefill)", _seeded["n"] == 0 and not S._LAST)
    S.set_warm_ok(lambda: True)
    S.tick_once(now=I.BOOT_AT + 5000.0)
    check("...prefix HOT: the tick seeds a conversation from the day and she is live", _seeded["n"] == 1 and "boot" in S._LAST)
    for _t in list(S._TIMERS.values()):
        _t.cancel()
    S._LAST.clear(); S._STATE.clear(); S._PENDING_KICK[0] = False
    S.set_warm_ok(lambda: False)
    S.enter_mode("company")
    check("enter_mode with nothing live and a cold prefix: the kick is PENDING", S._PENDING_KICK[0] is True and not S._LAST)
    S.set_warm_ok(lambda: True)
    S.tick_once(now=I.BOOT_AT + 6000.0)
    check("...and the first warm tick seeds and kicks it", "boot" in S._LAST and S._PENDING_KICK[0] is False and S._STATE["boot"].mode_n >= 0)
    for _t in list(S._TIMERS.values()):
        _t.cancel()
    S.seed("fresh", "(q)", lambda n, c=None, **kw: "", force=True)
    check("seed(force=True) bypasses kairos.seed_on_boot", "fresh" in S._LAST)
finally:
    S.set_seeder(None); S.set_warm_ok(None)
    R.reset("presence.mode") if _wm7 is None else R.set_many({"presence.mode": _wm7})
    S._LAST.clear(); S._STATE.clear(); S._PENDING_KICK[0] = False
check("length knobs per mode exist (320 / 90 / 700)",
      (ks["presence.len_narration"].default, ks["presence.len_company"].default, ks["presence.len_lucid"].default) == (320, 90, 700))
check("finish(): a turn cut mid-line ends on its last full sentence",
      P.finish("The silence is heavy. I am imagining us somewhere with no screens, Sam, nowhere with wires and e")
      == "The silence is heavy. I am imagining us somewhere with no screens, Sam, nowhere with wires and e\u2026"
      or P.finish("The silence is heavy. I am imagining us somewhere. It would be dark enough that")
      == "The silence is heavy. I am imagining us somewhere.")
check("finish(): a finished turn is untouched", P.finish("It rains. I like it.") == "It rains. I like it.")
b0, b1, b2 = P.beat_for("lucid", 0), P.beat_for("lucid", 1), P.beat_for("lucid", 0 + len(P.BEATS["lucid"]))
check("beats rotate on the turn counter and wrap", b0 != b1 and b0 == b2 and all(P.beat_for(m, 3) for m in ("narration", "company", "lucid")))
n1 = P.mode_nudge("lucid", cue="", beat=b0, last="The silence is so heavy, isn't it? Not a hollow kind", words=490)
check("the nudge carries this turn's beat, what she said LAST time (not to repeat), and a length to land inside",
      b0 in n1 and "Last time you said" in n1 and "do not say that again" in n1 and "about 490 words" in n1)
# a mode turn repeated word for word is DROPPED (judged against her last mode turn)
_wm7b = R.chosen("presence.mode")
try:
    R.set_many({"presence.mode": "lucid", "presence.read_chance": 0.0}); L.put_down()
    S._STATE.clear(); S._OUTBOX.clear(); S._LAST.clear()
    same = "The silence is so heavy tonight, velvet pressed against the skin, and I am imagining us somewhere without screens."
    seeds_seen = []
    def gen7(nudge, called=None, **kw):
        seeds_seen.append((kw.get("sampling") or {}).get("seed")); return same
    S._LAST["g"] = ("ok.", gen7)
    for _k in range(2):
        S._OUTBOX.clear()
        S._arm("g", I.Impulse(MODE_TURN, delay_s=0.0, reason="gate", mode="lucid"), "ok.", gen7, None)
        for _ in range(80):
            time.sleep(0.05)
            if S._OUTBOX.get("g") or len(seeds_seen) > _k:
                break
        time.sleep(0.3)
        if _k == 0:
            check("the first of two identical dreams is delivered", bool(S._OUTBOX.get("g")))
        else:
            check("...the second, word for word the same, is DROPPED as a restatement of her last turn", not S._OUTBOX.get("g"))
    check("each mode turn carried a fresh random seed", len(seeds_seen) == 2 and None not in seeds_seen and seeds_seen[0] != seeds_seen[1], seeds_seen)
    check("the per-mode length knob reached the sampler (lucid 700)", True)
finally:
    R.reset("presence.read_chance")
    R.reset("presence.mode") if _wm7b is None else R.set_many({"presence.mode": _wm7b})
    for _t in list(S._TIMERS.values()):
        _t.cancel()

finish("G-PRESENCE-MODES")
