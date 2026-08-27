"""G-REFLECT — she thinks about him when the room is quiet. She rarely mentions it.

THINKING IS NOT SPEAKING, and this gate exists to keep them apart.

She reflects silently on an idle clock: reads what she knows about him, writes down what she
has come to believe. That happens whether or not he ever hears about it — it is how the model
of him gets built, and MOST of what she concludes should simply become part of what she knows,
unremarked. A person who told you every single thing they had ever noticed about you would be
unbearable to live with.

Only a genuinely SURPRISING conclusion earns an interruption. The bar is not "did she think of
something" — she thinks on a clock; she will always have thought of something. The bar is
whether it stays within the way HE talks — measured in bits of self-information over his own
vocabulary. (Until 2026-08-02 the bar was the opposite, a FLOOR on novelty, and it was removed
rather than retuned: the estimator behind it correlated 0.75 with sentence length and separated
invented claims from grounded ones at AUC 0.31. See G-REFLECTION-LOOP §7.) This is the one property of
a conclusion that cannot be faked.

    An unprompted "I've been thinking about you" that lands on something obvious is worse than
    silence: it teaches him to ignore the channel, and then the good one never gets heard.
"""
from __future__ import annotations

import os
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

_TMP = tempfile.mkdtemp()
os.environ["SP_RECALL_REGISTRY"] = os.path.join(_TMP, "registry.jsonl")
import json as _json
import time as _time

# ── A TRANSCRIPT STORE, because a silence is now CORROBORATED against his own turns ──
# `person.silences()` refutes any claim he has spoken to since its row was minted, and it
# FAILS CLOSED when there is no record to check ("absence is only information if you can
# prove you were looking" — its own thesis). This fixture therefore has to say what he
# actually said, and what he said is: nothing about any of these claims. That makes the
# assertions below stronger than they were, not weaker. See G-SILENCE-CORROBORATE.
_TDIR = os.path.join(os.path.dirname(os.environ["SP_RECALL_REGISTRY"]), "transcripts")
os.makedirs(_TDIR, exist_ok=True)
with open(os.path.join(_TDIR, "%s.jsonl" % _time.strftime(
        "%Y-%m-%d", _time.gmtime(_time.time() - 86400.0)), ), "w", encoding="utf-8") as _f:
    _f.write(_json.dumps({"role": "user", "at": (_time.time() - 86400.0) * 1000.0,
                          "content": "nothing here bears on the fixtures"}) + chr(10))


# ── A GATE THAT NEEDS A LIVE DAEMON IS NOT A GATE (2026-07-14) ──────────────────────────
# remember() makes a SYNCHRONOUS call to the daemon's /v1/capture to mint the episode —
# `urlopen(..., timeout=120)` — on EVERY memory write. With the daemon up, this gate hung: the
# episode mint is a model forward and it grinds. With the daemon down it degrades gracefully
# (the fact is still recorded), which is the behaviour the gate actually wants to test.
#
# So point it at a closed port. Connection-refused fails in microseconds; a LIVE daemon fails in
# up to two minutes, per write. A test whose runtime depends on whether a GPU service happens to
# be running is a test that will be quietly disabled the first week it annoys someone.
#
# (The 120s inline capture on the memory-write hot path is a real finding and has its own task.
# It is not this gate's job to work around it — it is this gate's job not to DEPEND on it.)
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"   # discard port: always refused, instantly
# SP_ENGINE_KIND: no capture attempt at all (2026-08-23). A dead SP_DAEMON_URL does
# NOT make the KV mint cheap - _mint_now still opens a socket per write and Windows
# takes ~2s to give up. Declaring the backend makes supports('capture') False and the
# mint returns immediately: 10 writes in 0.07s against 20s. See gates/README.md.
os.environ["SP_ENGINE_KIND"] = "openai"

# SYNTHETIC CLOCKS (2026-08-22): a fresh TurnState's clocks default to impulse.BOOT_AT, the
# real monotonic boot time, which would sit in this gate's small fixture times' FUTURE.
# Pin the boot to t=1.0 here — non-zero, before every `now` below.
import harness.kairos.impulse as _imp_pin  # noqa: E402
_imp_pin.BOOT_AT = 1.0
from harness.kairos import impulse as I        # noqa: E402
from harness.kairos import scheduler as S      # noqa: E402
from harness.model.person import PersonModel   # noqa: E402
from harness.skills import memory as M         # noqa: E402
from harness.tuning import registry as tune    # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def main() -> int:
    print("G-REFLECT - she thinks when it is quiet, and rarely mentions it.\n")

    tune.STORE = os.path.join(_TMP, "tuning.json")
    tune.set_many({"kairos.enabled": True, "kairos.cooldown_s": 0.0,
                   "reflect.enabled": True, "reflect.idle_s": 600.0,
                   "reflect.cooldown_s": 1800.0, "reflect.speak_pct": 0.9})
    cfg = S.live_config()

    # ── 1. A MUSING IS NOT A PROMISE ────────────────────────────────────────────
    # A due reminder outranks the chain limit and the never-interrupt-a-question rule,
    # because it is a promise he asked her to keep. A musing does NOT. It is just something
    # she noticed, and a thought that interrupts him is worse than a thought he never hears.
    insight = {"text": "Sam builds things to be companions, not tools", "bits": 4.2}

    st = I.TurnState()
    I.note_user(st, 1000.0)
    # (2026-08-22: a musing waits for the room to be quiet — checkin_idle_s — like every
    #  other unprompted word; "a reason to speak" is judged after that floor)
    imp = I.decide(cfg=cfg, state=st, now=1000.0 + cfg.checkin_idle_s + 1.0, reply_text="Sure.",
                   eot_margin=None, insight=insight)
    check("a surprising conclusion IS a reason to speak",
          imp.speaks and imp.action == I.MUSE, imp.reason)

    # NB: note_user() RESETS the chain — his turn ending her chain is the entire point of a
    # conversation. Setting chain=1 and THEN calling note_user wipes it, and the first cut
    # of this check did exactly that and "failed" the code for being right. Speak first,
    # then chain.
    st_chained = I.TurnState()
    I.note_user(st_chained, 1000.0)
    I.note_spoke(st_chained, 1000.05)          # she has now spoken unprompted once
    imp = I.decide(cfg=cfg, state=st_chained, now=1000.1, reply_text="Sure.",
                   eot_margin=None, insight=insight)
    check("...but the CHAIN LIMIT still silences it (a reminder would have overridden this)",
          imp.action == I.SILENT, imp.reason)

    imp = I.decide(cfg=cfg, state=st, now=1000.1,
                   reply_text="So what did you decide about the NUC?",   # she asked HIM
                   eot_margin=None, insight=insight)
    check("...and so does 'she asked him a question' — she does not talk over him",
          imp.action == I.SILENT, imp.reason)

    # ── 2. SHE MOSTLY KEEPS IT TO HERSELF ───────────────────────────────────────
    imp = I.decide(cfg=cfg, state=st, now=1000.1, reply_text="Sure.",
                   eot_margin=None, insight=None)
    check("having concluded NOTHING new, she says nothing",
          not imp.speaks, imp.reason)

    # ── 3. THE NUDGE: A THOUGHT, NOT A LOOKUP, AND NOT PUT IN HIS MOUTH ─────────
    n = I.muse_nudge(insight)
    check("the nudge hands her the CONCLUSION to say in her own voice",
          insight["text"] in n and "your own voice" in n)
    check("...and forbids telling him he said it (he never did)",
          "he never actually said it" in n or "do not tell him that he did" in n)
    check("...and still lets her drop it if it sounds hollow out loud",
          "say nothing at all" in n)

    # ── 4. THE NEIGHBOUR WHO DID NOT WAVE ──────────────────────────────────────
    now = time.time()

    def iso(d):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - d * 86400))

    pm = PersonModel()
    pm.absorb({"text": "I am training for the marathon", "mem_class": "preference",
               "mentions": 8, "first_seen": iso(44), "last_seen": iso(30)})

    # ── SHE MUST HAVE BEEN LOOKING (2026-07-14) ──────────────────────────────────────────
    # This setup used to just assert `bool(sil)`. It passed, and it was asserting a bug: a
    # silence computed from CALENDAR days, with no evidence he was ever present. Now silences()
    # measures ATTENDED days, so the gate has to supply the attention it was silently assuming.
    #
    # AND THAT IS THE POINT. He talked to her every day for the last 45 and never once mentioned
    # the marathon he used to bring up constantly. THAT is the dog that did not bark. Without
    # these 45 receipts she is a system that has been asleep and is claiming to have seen nothing.
    from harness.model import presence
    for d in range(46):
        presence.note_turn(now - d * 86400)

    sil = pm.silences(now=now)
    check("(setup) a thing he has gone quiet on IS detected — WHEN SHE WAS THERE THE WHOLE TIME",
          bool(sil), "the attention ledger is what makes this a real silence")

    nudge = I.muse_nudge({"text": sil[0]["claim"], "bits": sil[0]["bits"], "silence": sil[0]})
    check("a SILENCE becomes a gentle question, not an announcement",
          "ASK him" in nudge and "has not mentioned it" in nudge)
    check("...and she is told not to reveal that she was analysing him",
          "Do not announce that you were analysing him" in nudge)
    check("...and to shut up if it feels like prying rather than caring",
          "prying rather than caring" in nudge)

    # ── 5. NO NEW EVIDENCE, NO NEW THINKING ────────────────────────────────────
    # Re-reading the same facts just re-derives the same conclusion and calls it a
    # discovery. Harmless in the STORE (reinforcement makes a re-derived belief stronger,
    # not duplicated) — deadly in the CHANNEL, where the same thought arriving twice is how
    # a companion becomes a bore.
    S._STATE.clear(); S._LAST.clear()
    S._LAST_REFLECT_AT = 0.0
    S._LAST_EVIDENCE = -1

    t0 = time.monotonic()
    st2 = S._STATE["s"]
    I.note_user(st2, t0 - 5.0)                 # he spoke 5 seconds ago: the room is NOT quiet
    check("she does not reflect while he is still talking (idle floor)",
          S.reflect_tick(t0) is None, "reflection is a whole model turn — never race him")

    I.note_user(st2, t0 - 1200.0)              # 20 minutes of quiet
    S._LAST_EVIDENCE = S._evidence_count()     # ...but nothing new has been said
    check("she does not re-think the same evidence and call it a discovery",
          S.reflect_tick(t0) is None, "no new evidence, no new thinking")

    # ── A REFLECTION IS A CONCLUSION, NOT AN OBSERVATION ─────────────────────────────────
    # THE CHECK ABOVE PASSED FOR WEEKS WHILE THE BUG WAS LIVE, because it SETS _LAST_EVIDENCE
    # by hand and then asserts she does not reflect. It tested THE GUARD. It never tested THE
    # THING THE GUARD PROTECTS: that her own output does not bump the count that opens the gate.
    #
    # The bug: _evidence_count() was len(_load()) — every row, including src=reflection. And
    # insight() WRITES ROWS. So she reflected, the store grew, "new evidence" appeared, and she
    # reflected on her own reflections. Bounded only by the 30-minute cooldown, so it never
    # spun — it DRIFTED, which from outside reads as "the model got weird lately" and gets
    # blamed on the weights.
    #
    # DERIVING A BELIEF FROM EVIDENCE MUST NOT CREATE EVIDENCE. A system whose inferences
    # re-enter its own input is not learning, it is compounding its own certainty.
    # Written through the SAME call insight() uses — M.remember(line, source="reflection") —
    # so the gate tests the real path and not a convenient stand-in.
    before = S._evidence_count()
    M.remember("Sam is deeply curious about how things work", source="reflection")
    after_infer = S._evidence_count()
    check("HER OWN CONCLUSION IS NOT NEW EVIDENCE",
          after_infer == before,
          f"evidence {before} -> {after_infer} after she concluded something — the loop is open")

    # ...and `src` is FREE-TEXT PROSE that maintenance passes APPEND to. A cleanup that stamps a
    # reflection row turns src into "reflection | cleanup: ..." — so an EXACT-match test would
    # silently start counting it as evidence again, months later, because of a housekeeping
    # script, and nothing would error. Substring, not equality.
    M.remember("Sam values play for its own sake",
               source="reflection | cleanup: stamped speaker=user (2026-07-14)")
    check("...even after a maintenance pass has scribbled on its provenance",
          S._evidence_count() == before,
          "a src that is a PARAGRAPH is not a field you can branch on")

    # But the world must still be able to tell her something.
    M.remember("My father was a cartographer", source="user turn")
    check("but something HE said is still evidence",
          S._evidence_count() == before + 1,
          "if nothing counts as evidence, she never thinks again")

    # ── A CRASH IN HERE LOOKS EXACTLY LIKE HAVING NOTHING TO SAY (2026-08-28) ────────
    # `reflect_tick` wraps its whole body in `except Exception`, so when a refactor left
    # `PersonModel` imported in one function and USED in the one split out of it, every
    # tick raised NameError, logged a single warning line, and returned None — which is
    # what it also returns on a quiet night. The conclusion lane was dead for five hours,
    # the operator noticed before any gate did, and every check in this file stayed green
    # because None was the expected answer.
    #
    # So the steps are driven DIRECTLY, where an exception is an exception rather than a
    # verdict. Not "did it return None" but "can it run at all" — the cheapest possible
    # guard against a broad `except` turning a broken function into a quiet one.
    for _name, _call in (("_reflect_insight",
                          lambda: S._reflect_insight(
                              {"wrote": [{"claim": "Sam likes building things",
                                          "result": "stored ep_x"}]})),
                         ("ambient_silence", S.ambient_silence)):
        try:
            _call()
            _ok, _why = True, ""
        except (NameError, AttributeError, TypeError) as exc:
            _ok, _why = False, "%s: %s" % (type(exc).__name__, exc)
        except Exception:
            _ok, _why = True, ""   # an environmental failure is not this check's subject
        check("%s resolves its own names" % _name, _ok, _why)

    total = len(PASS) + len(FAIL)
    print(f"\nG-REFLECT: {'PASS' if not FAIL else 'FAIL'} ({len(PASS)}/{total})")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
