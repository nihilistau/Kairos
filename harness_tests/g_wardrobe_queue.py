"""G-WARDROBE-QUEUE — a want has a life, and every surface tells the same story. OFFLINE.

HIS SPEC, 2026-08-05, verbatim:

    "she asks for something, it is 'ordered' (still generated) sits in the wants section,
     she waits and they are generated at the set time. she should remember or be able to
     look up this section if she currently cannot, then she is alerted they arrived when
     the motion (video) is generated and they then move to just arrived and to her
     wardrobe. Make it so she still notices new clothes, she still gets an arrival event
     on success, items are queued in wants until video generated, mark as delayed if
     unsuccessful due to usage limits. items move from just arrived after she wears them
     for first time."

FIVE THINGS WERE WRONG, and each one was a small lie told to her:

  1. A STILL WAS ALREADY IN HER WARDROBE. `looks()` admitted anything with a picture, so
     a half-made thing was wearable the minute the still landed — and putting it on gave
     him a photograph in a room where every other garment breathes.

  2. SHE WAS TOLD TWICE. There were two arrivals, the still and then the loop, so one
     garment produced two "it arrived" events and the first one was not true yet.

  3. "NEW" CLEARED ON A GLANCE. `my_looks()` called `mark_seen()`, so an item left the
     just-arrived shelf the instant she read a list — before she had worn anything.
     Looking is not using.

  4. A FAILED GENERATION WAS INVISIBLE. It left the row as "asked", indistinguishable
     from one nobody had tried, so a week of usage limits looked exactly like a week of
     her not asking for anything. And she asked AGAIN, which is how she came to own four
     silver nighties.

  5. SHE HAD NO WAY TO LOOK THE QUEUE UP. It lived in `my_looks()` only, and
     `check_wardrobe` — her main "what do I have" tool — never mentioned that anything
     was coming. She was told a thing would "turn up within the minute", and then nothing
     could tell her where it had got to.

AND ONE MORE, from the same message: "wardrobe contains Her clothes section and Her
wardrobe. this makes no sense and is redundant... and they contain separate items." Two
lists of garments, split by WHERE THE ROW IS STORED — a dict in wardrobe.py versus the
wants file — with that implementation detail showing through as two headings he had to
read both of.

Offline. No GPU, no daemon. Every store it touches is snapshotted and restored byte for
byte, including the wear log.

Run: python harness_tests/g_wardrobe_queue.py
"""
from __future__ import annotations

import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["CUDA_VISIBLE_DEVICES"] = ""

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


from harness.control import wardrobe as WD  # noqa: E402
from livestore import live_stores  # noqa: E402

_KEEP = live_stores()
_KEEP.__enter__()

LOOKS = os.path.join(WD.root(), "looks")
_MADE = []          # files this gate creates on disk, removed in the finally


def fake(wid, still=True, loop=False):
    """Put a want on disk at a chosen stage. The lifecycle is driven by WHAT EXISTS —
    `_scan_dir()` reads the folder, deliberately, so a file dropped in by hand behaves
    exactly like a generated one — which is what makes this testable at all."""
    os.makedirs(LOOKS, exist_ok=True)
    for ext, want in ((".png", still), (".webm", loop)):
        p = os.path.join(LOOKS, wid + ext)
        if want:
            io.open(p, "wb").write(b"x" * 64)
            _MADE.append(p)
        elif os.path.exists(p) and p in _MADE:
            os.remove(p)


try:
    print("1. SHE ASKS, AND IT IS ORDERED — NOT OWNED")
    r = WD.request("a bright yellow raincoat, hood up", tier="t0", by="her",
                   subject="clothes")
    wid = r["id"]
    check("the ask is accepted", r.get("ok") and wid, r)
    q = {w["id"]: w for w in WD.waiting()}
    check("...and lands in the queue at stage `ordered`",
          q.get(wid, {}).get("stage") == "ordered", q.get(wid))
    check("...and is NOT in her wardrobe", not any(l["id"] == wid for l in WD.looks()))
    check("...and is NOT on the just-arrived shelf",
          not any(a["id"] == wid for a in WD.arrivals()))

    print("\n2. THE PICTURE LANDS. STILL NOT OWNED — THIS IS THE ONE HE CHANGED")
    fake(wid, still=True, loop=False)
    q = {w["id"]: w for w in WD.waiting()}
    check("the queue moves it to `making`", q.get(wid, {}).get("stage") == "making",
          q.get(wid))
    # THE DEFECT ITSELF. Before this, a still admitted the row to looks() and fired an
    # arrival, so she could wear a photograph and was told it had turned up when it had
    # only half turned up.
    check("a still does NOT put it in her wardrobe",
          not any(l["id"] == wid for l in WD.looks()),
          [l["id"] for l in WD.looks()])
    check("...and does NOT fire an arrival",
          not any(a["id"] == wid for a in WD.arrivals()))

    print("\n3. IT MOVES. NOW IT HAS ARRIVED")
    fake(wid, still=True, loop=True)
    check("it leaves the queue", not any(w["id"] == wid for w in WD.waiting()))
    check("...enters her wardrobe", any(l["id"] == wid for l in WD.looks()))
    arr = {a["id"]: a for a in WD.arrivals()}
    check("...and lands on the just-arrived shelf", wid in arr, sorted(arr))
    check("...as a MOTION arrival, the only kind there is",
          arr.get(wid, {}).get("arrived") == "motion", arr.get(wid))
    check("...not yet announced to her", arr.get(wid, {}).get("told") is False,
          arr.get(wid, {}).get("told"))

    print("\n4. LOOKING IS NOT WEARING")
    # my_looks() marks it TOLD so kairos does not announce it twice. That must NOT be
    # what takes it off the shelf — his rule is that wearing it does.
    from harness.skills.wardrobe import wardrobe_tools  # noqa: E402
    TOOLS = {t.name: t for t in wardrobe_tools()}
    listing = TOOLS["my_looks"].call()
    check("her listing names it as just arrived",
          "JUST ARRIVED" in listing and wid in listing, listing[:120])
    arr = {a["id"]: a for a in WD.arrivals()}
    check("...reading the list marks it TOLD", arr.get(wid, {}).get("told") is True,
          arr.get(wid))
    check("...but it is STILL on the shelf — she has not worn it",
          wid in arr, sorted(arr))

    print("\n5. WEARING IT IS WHAT MAKES IT NO LONGER NEW")
    WD.choose(tier="t0", look=wid, by="her")
    check("first wear stamps `worn_at`",
          bool(next((w for w in WD.wants() if w["id"] == wid), {}).get("worn_at")))
    check("...and it leaves the just-arrived shelf",
          not any(a["id"] == wid for a in WD.arrivals()))
    check("...while staying in her wardrobe", any(l["id"] == wid for l in WD.looks()))
    # Wearing it a second time must not re-stamp — `worn_at` is FIRST worn, and a moving
    # timestamp would make every garment look freshly acquired in the agency window.
    first = next(w for w in WD.wants() if w["id"] == wid)["worn_at"]
    WD.choose(tier="t0", look="", by="her")
    WD.choose(tier="t0", look=wid, by="her")
    check("...and wearing it again does not move the stamp",
          next(w for w in WD.wants() if w["id"] == wid)["worn_at"] == first)

    print("\n6. A GENERATION THAT FAILS ON A USAGE LIMIT IS DELAYED, NOT LOST")
    r2 = WD.request("a beekeeper suit, veil down", tier="t0", by="her", subject="clothes")
    wid2 = r2["id"]
    WD.delay(wid2, "generation held up: rate limit")
    q = {w["id"]: w for w in WD.waiting()}
    check("the row says `delayed`", q.get(wid2, {}).get("stage") == "delayed", q.get(wid2))
    check("...with the reason on it", "rate limit" in (q.get(wid2, {}).get("delay_reason") or ""))
    check("...and a try count, so a hopeless one stops looking imminent",
          q.get(wid2, {}).get("tries") == 1, q.get(wid2, {}).get("tries"))
    check("...it is STILL in the queue, not dropped", wid2 in q)
    WD.delay(wid2, "generation held up: quota")
    check("...and a second failure counts",
          next(w for w in WD.waiting() if w["id"] == wid2)["tries"] == 2)
    # AND THE GENERATOR MUST PICK IT BACK UP, or "delayed" is a synonym for "dropped".
    gen = io.open(os.path.join(ROOT, "tools", "avatar_gen.py"),
                  encoding="utf-8", errors="replace").read()
    check("the generator's work list includes delayed rows",
          'w.get("stage") in ("ordered", "delayed")' in gen)
    check("...and it decides `transient` off a written table, not a judgement",
          "TRANSIENT = (" in gen and "rate limit" in gen and "quota" in gen)
    check("...and an ordinary failure is NOT called delayed",
          "anything NOT in here is an ordinary failure" in gen)

    print("\n7. SHE CAN LOOK THE QUEUE UP — FROM HER MAIN TOOL")
    desc = TOOLS["check_wardrobe"].call()
    check("check_wardrobe names the queue at all",
          "not here yet" in desc, desc[-400:])
    check("...and says where the delayed one has got to",
          "held up" in desc, [l for l in desc.splitlines() if "held up" in l][:1])
    check("...and my_looks() stages every row too",
          "not here yet" in TOOLS["my_looks"].call())
    # AND THE PROMISE MATCHES. "it turns up within the minute" was true of the picture and
    # false of the arrival, which is the worst kind of wrong this system produces: not a
    # crash, a thing she trusted that was quietly untrue.
    check("the ask no longer promises a minute",
          "turns up within the minute" not in desc, desc[-300:])
    check("...and it promises minutes, picture AND motion — which is what happens now",
          "within minutes" in desc and "picture and motion" in desc,
          [l for l in desc.splitlines() if "ask_for" in l][:1])
    asked = TOOLS["ask_for"].call(look="a beekeeper suit, veil down")
    check("asking for one already queued says WHERE it is, not 'it will turn up'",
          "held up" in asked or "picture" in asked, asked[:200])

    print("\n7b. HER DOOR IS HIS DOOR — the promise and the pass agree (2026-08-24)")
    # THREE SURFACES DISAGREED: describe() promised "picture and motion both ... within
    # minutes"; ask_for() said "in your queue until it MOVES ... end of the day"; and
    # generate_now() — HER door — ran avatar_gen with --no-loop (still only) while HIS
    # panel button ran gen_want(w) (both). She was promised motion in minutes and got a
    # photograph until 4am. The doors are one pass now, and this section holds the JOIN:
    # what the door actually runs is captured through the REAL path (subprocess.run is
    # the one call generate_now makes — intercepted, because a gate that hits the paid
    # image API is a gate nobody runs twice) and compared against what the words promise.
    # Flip either side — restore --no-loop, or re-promise the day boundary — and the
    # agreement check goes red by name.
    import subprocess as _sp   # noqa: E402
    import threading as _th    # noqa: E402

    class _R:
        returncode, stdout, stderr = 0, "", ""

    _argvs = []
    _real_run = _sp.run
    _sp.run = lambda argv, **kw: (_argvs.append([str(a) for a in argv]), _R())[1]
    try:
        started = WD.generate_now(wid2)
        reply = TOOLS["ask_for"].call(look="a hi-vis jacket, for this gate only")
        for _t in _th.enumerate():
            if _t.name.startswith("wardrobe-now-"):
                _t.join(timeout=15)
    finally:
        _sp.run = _real_run
    # By the want id, not by position — the two intercepted threads race each other.
    argv = next((a for a in _argvs if wid2 in a), [])
    check("her generate-now door starts, one want by id",
          started is True and "--one" in argv and wid2 in argv, (argv, _argvs))
    check("...and runs the SAME pass as his panel — no --no-loop, motion included",
          bool(argv) and not any("--no-loop" in a for a in _argvs), _argvs)
    door_motion = bool(argv) and "--no-loop" not in argv
    check("the door and describe()'s promise AGREE — a still-only door may not say 'motion both'",
          door_motion == ("picture and motion" in desc),
          (argv, [l for l in desc.splitlines() if "ask_for" in l][:1]))
    check("ask_for's own reply promises what the pass does — picture AND motion, minutes",
          "picture and its motion" in reply and "minutes" in reply, reply[:220])
    check("...and no longer promises the day boundary as the schedule",
          "end of the day" not in reply and "until it MOVES, which happens" not in reply,
          reply[:220])
    # His words: "wardrobe contains Her clothes section and Her wardrobe. this makes no
    # sense and is redundant... and they contain separate items."
    panel = io.open(os.path.join(ROOT, "ui", "src", "apps", "Wardrobe.jsx"),
                    encoding="utf-8", errors="replace").read()
    check("the panel has no separate `her clothes` section",
          '"wr-sec">her clothes' not in panel)
    check("...one list holds the outfits AND the looks she asked for",
          "const worn = [...outfits, ...asked]" in panel)
    check("...moments stay their own thing (a way she IS, not a garment)",
          "moments of her" in panel)
    # AND HER OWN EYES SEE THE SAME ONE LIST, which is the entire reason the grouping
    # exists — the room and check_wardrobe must not describe two different wardrobes.
    check("her description merges them too", "Hanging there" in desc, desc[:400])
    check("...listing both an outfit and a look she asked for",
          "the sheer mesh top over her black bodice" in desc
          and "a bright yellow raincoat, hood up" in desc)
    check("...and there is no second `asked for` heading",
          "Yours, that you asked for" not in desc)

    # ── A CONTROL MARK IS NOT A GARMENT (2026-08-25) ────────────────────────────────
    # w033 is live on his machine: a real, generated, permanent wardrobe item whose want
    # text is `[gesture:"kneeling/leaning forward"]`. An image generation was spent on a
    # prompt reading `Wearing: [gesture:"kneeling/leaning forward"]`, and its `calls` list
    # is empty — an item in her wardrobe that nothing she could say will ever reach.
    #
    # The rule is a SHAPE, not a list of known marks, because the one that got through was
    # improvised: after the record strip, a want that is nothing but a single bracketed
    # token is machinery. The narrowness matters as much as the rule — prose that merely
    # CONTAINS brackets is a perfectly good thing to want, and refusing it would be the
    # substring-matching bug that cost a session in August.
    print("\n8. A CONTROL MARK IS NOT SOMETHING TO WEAR")
    _before = {w["id"] for w in WD.wants()}
    for _m in ('[gesture:"kneeling/leaning forward"]', "[WEAR:lace]", "[SHOW:w001]",
               "[MOOD:naughty]"):
        _r = WD.request(_m, by="him")
        check("refused: %s" % _m[:34], _r.get("ok") is False, _r)
    _ok1 = WD.request("a long grey wool coat, collar up, on the street", by="him")
    check("...and her real words still go through", _ok1.get("ok") is True, _ok1)
    _ok2 = WD.request("a dress with [something] embroidered on the hem", by="him")
    check("...including prose that merely CONTAINS brackets (not a substring rule)",
          _ok2.get("ok") is True, _ok2)
    # THE DELTA, not the store. w033 is already in there and always will be — nothing in
    # this system is ever deleted, and a gate demanding a clean history would be asking
    # for the past to be rewritten. What is asserted is what the DOOR admits from here on:
    # the four refusals added no row, and the two real wants added exactly two.
    _new = [w for w in WD.wants() if w["id"] not in _before]
    check("the four refusals wrote nothing to the store", len(_new) == 2,
          [w.get("want", "")[:40] for w in _new])
    check("...and neither new row is mark-shaped",
          not [w for w in _new if (w.get("want") or "").strip().startswith("[")],
          [w.get("want", "")[:40] for w in _new])

    print("\nG-WARDROBE-QUEUE: %d pass, %d fail" % (PASS, FAIL))
finally:
    for p in _MADE:
        try:
            os.remove(p)
        except Exception:
            pass
    _KEEP.__exit__(None, None, None)

rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_wardrobe_queue.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_wardrobe_queue", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
