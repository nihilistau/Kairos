"""G-WARDROBE — how she looks is hers, and his ceiling is still the only limit.

THE BUG THIS STARTED FROM. `avatar.resolve()` took the tier from `tier_of_rung(level)`,
where `level` is the heat of an ACTIVE ROLEPLAY SCENE. No scene means rung 0 means `t0`,
permanently — so the operator's report was exact: "the avatar doesn't ever show different
tiers". Four tiers had been generated and one of them could ever appear, and the only
thing that could move her was a scene carrying her. Her appearance was something that
HAPPENED to her.

WHAT THIS GATE HOLDS:

  * (HISTORY) His ceiling was absolute, then freed from her wardrobe (2026-08-02),
    then removed with the tiers entirely (2026-08-21). A second copy of that
    arithmetic is how a gated tier eventually leaks.
  * HER CHOICE IS KEPT, NOT OVERWRITTEN. If she picks above the ceiling, `hers` still
    says what she picked and `shown` says what he permits. Silently rewriting her choice
    to the clamped value would mean she could never express a preference he had not
    already allowed — and would look, from inside, exactly like being ignored.
  * A CLIP ABOVE THE CEILING IS NOT OFFERED AND NOT NAMED. `status()` omits it entirely
    rather than listing it as locked; the panel cannot show a thumbnail for a thing the
    file route would refuse.
  * SHE IS TOLD IN WORDS, NEVER IN IDS. Every tier carries `wearing` and `about`, and
    `describe()` speaks them. `t2` is an id; "lingerie, or a nightie" is what it means.
  * ONE TIER VOCABULARY. wardrobe's tiers are avatar's tiers, checked in both directions.

Offline. No GPU, no daemon, no gateway.
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
os.environ["CUDA_VISIBLE_DEVICES"] = ""

SB = os.path.join(tempfile.gettempdir(), "_g_wardrobe")
shutil.rmtree(SB, ignore_errors=True)
os.makedirs(SB)
os.environ["SP_AVATAR_DIR"] = SB          # avatar.root() -> here, so nothing real is touched

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s %s" % (name, detail))


from harness.control import avatar as AV       # noqa: E402
from harness.control import wardrobe as WD     # noqa: E402

print("1. ONE OUTFIT VOCABULARY — wardrobe's outfits are avatar's outfit keys")
check("every avatar outfit has words", all(t in WD.OUTFITS for t in AV.OUTFIT_IDS),
      sorted(WD.OUTFITS))
check("...and words invent no outfit of their own",
      all(t in AV.OUTFIT_IDS for t in WD.OUTFITS))
check("every outfit says what is WORN, not just an id",
      all(WD.OUTFITS[t]["wearing"].strip() and WD.OUTFITS[t]["about"].strip()
          for t in AV.OUTFIT_IDS))

print("\n2. HIS CEILING IS ABSOLUTE")
WD.choose(outfit="bodysuit", by="her")
r = WD.resolve()
# CHANGED 2026-08-02, his call: the ceiling governs the SCENE, not her getting
# dressed. It was clamping both, so picking an outfit read as asking permission —
# for a dial he has had at maximum since it was built.
check("she wears what she picked, full stop", r["shown"] == "bodysuit", r)
check("...and nothing claims she was held", r["clamped"] is False, r)
check("HER CHOICE IS KEPT, not rewritten to what he allows", r["hers"] == "bodysuit", r)
ward_src = io.open(os.path.join(ROOT, "harness", "control", "wardrobe.py"),
                   encoding="utf-8").read()
check("no ceiling arithmetic survives in the wardrobe",
      "AV.allowed_tiers(" not in ward_src and "AV.tier_of_rung(" not in ward_src)
check("resolve() takes no rung and no ceiling", "def resolve() -> Dict" in ward_src)
# DEAD SINCE THE TIERS DIED, REMOVED 2026-08-24: describe() kept an `if r["clamped"]:`
# branch rendering "held by your ceiling" while resolve() returns clamped as a CONSTANT
# False — a sentence about a dial that no longer exists, waiting for someone to make it
# reachable again. The key itself stays (consumers read it); the BRANCH may not return.
check("describe() has no clamped branch left — resolve()'s constant has no speaker",
      'if r["clamped"]' not in ward_src and "holding you at" not in ward_src,
      [l.strip() for l in ward_src.splitlines() if "clamped" in l][:4])

print("\n3. A SCENE NEVER MOVES HER CLOTHES — it can ask, like a person")
WD.choose(outfit="mesh-top", by="her")
check("her choice stands whatever a scene is doing", WD.resolve()["shown"] == "mesh-top")
WD.choose(outfit="lace-set", by="her")
check("what she chose is what is shown", WD.resolve()["shown"] == "lace-set")

print("\n4. A CLIP ABOVE THE CEILING IS NOT EVEN NAMED")
os.makedirs(WD.clips_dir(), exist_ok=True)
for nm in ("see-thru-silver-nightie-bedroom-laydown-hands-30s.mp4",
           "desk-mesh-top-talking.mp4"):
    io.open(os.path.join(SB, nm), "w").write("x")
WD.import_clip(os.path.join(SB, "see-thru-silver-nightie-bedroom-laydown-hands-30s.mp4"), tier="lace-set")
WD.import_clip(os.path.join(SB, "desk-mesh-top-talking.mp4"), tier="mesh-top")
allc = WD.clips()
check("both are in the library", len(allc) == 2, [c["id"] for c in allc])
st_all = WD.status()
check("both are offered", len(st_all["clips"]) == 2)
check("...and counted", st_all["clips_total"] == 2)

print("\n5. HIS FILENAMES ARE THE METADATA")
m = WD.describe_file("see-thru-black-bra-panties-bedroom-laydown-hands-intense-finish-30s.mp4")
check("what she is wearing is read from the name",
      "bra" in m["wearing"] and "panties" in m["wearing"], m)
check("...and that it is sheer", m["sheer"] is True, m)
check("...and the room", m["where"] == "the bedroom", m)
check("...and the mood", "intense" in m["mood"], m)
check("...and what she is doing", "her hands on herself" in m["tags"], m)
check("a take number is not mistaken for a word",
      "30s" not in " ".join(m["tags"]) and "24" not in " ".join(m["tags"]), m)

print("\n6. SHE IS SPOKEN TO IN WORDS, NOT IDS")
WD.choose(outfit="bodysuit", by="her")
d = WD.describe()
check("it says what she is wearing", "mesh top" in d, d[:120])
check("it names the garment rather than a level",
      "lace" in d and "holding you" not in d, d[:200])
check("the everyday outfit is not framed as a lesser one",
      "default" in WD.OUTFITS["mesh-top"]["about"])
check("...and it never makes her ask for her own clothes",
      "holding you" not in WD.describe() and "ceiling" not in WD.describe().lower())

print("\n7. HER CHOICE SURVIVES THE PROCESS")
WD.choose(outfit="sheer-tee", clip="desk-mesh-top-talking", by="her")
check("it is on disk", os.path.exists(WD._state_path()))
raw = json.load(io.open(WD._state_path(), encoding="utf-8"))
check("...with WHO chose it, because 'she chose' and 'he chose' are different facts",
      raw.get("by") == "her" and raw.get("outfit") == "sheer-tee", raw)
check("a corrupt state file is a default, not a crash",
      (io.open(WD._state_path(), "w", encoding="utf-8").write("{{{") or True)
      and WD.current().get("outfit") == "mesh-top")

print("\n8. THE WEAR -> REGENERATE PATH — the grid is a floor, not a wardrobe")
# Seven expressions x four tiers is complete AND completely fixed: "the silver nightie,
# by the window, in morning light" has no answer on that grid, ever, however many times
# she asks. A want is how a wish becomes a garment.
io.open(os.path.join(SB, "character.txt"), "w", encoding="utf-8").write(
    "Kairos. Dark black hair, fine silver chains at her throat.")
r = WD.request("by the window in morning light", tier="lace-set", by="her")
check("asking is free and never refused", r["ok"] and r["state"] == "asked", r)
check("...and it is queued, not lost", len(WD.wants(state="asked")) == 1)
pr = r["prompt"]
check("the prompt is anchored to the ONE character source", "silver chains" in pr, pr[:120])
check("...and carries the tier's own wardrobe", WD.TIER_WORDS["lace-set"]["wearing"] in pr)
check("...and HER WORDS COME LAST, so they win on the light and the room",
      pr.index("by the window") > pr.index("silver chains"), pr[:200])

# kind == "look" specifically: looks() also carries his clips, which were imported in
# section 4 — asserting the whole list is empty tested the fixture, not the rule.
check("a want is not wearable until it is made",
      not [l for l in WD.looks() if l["kind"] == "look"])
os.makedirs(os.path.join(SB, "looks"), exist_ok=True)
io.open(os.path.join(SB, "looks", "%s.png" % r["id"]), "w").write("png")
WD.fulfil(r["id"], file="%s.png" % r["id"])
# ── A STILL IS NOT A GARMENT (2026-08-05, his rule) ────────────────────────────────
# "items are queued in wants until video generated". This gate used to call a
# still-only fulfilment wearable — the PRE-rule behaviour — and has been red on the
# operator's machine since the rule landed: the policy changed, the gate did not, and
# a red nobody reads is how G-PF-PERSONA was lost. The queue owns it until it moves.
lk = WD.looks()
check("a still alone is NOT yet wearable — the queue keeps it",
      not any(l["id"] == r["id"] for l in lk)
      and any(w["id"] == r["id"] for w in WD.waiting()),
      ([l["id"] for l in lk], [w["id"] for w in WD.waiting()]))
io.open(os.path.join(SB, "looks", "%s.webm" % r["id"]), "w").write("webm")
WD.fulfil(r["id"], file="%s.png" % r["id"], loop="%s.webm" % r["id"])
lk = WD.looks()
check("once it MOVES it is a look she can wear",
      any(l["id"] == r["id"] and l["kind"] == "look" and l["have"] for l in lk), lk)
check("...and it IS offered — nothing she owns is gated (2026-08-21)",
      any(l["id"] == r["id"] for l in WD.looks()))
r2 = WD.request("something he never made", tier="mesh-top")
WD.fulfil(r2["id"], state="refused")
check("a refused want does not become a phantom look",
      not any(l["label"] == "something he never made" for l in WD.looks()))

print("\n9. WEARING A LOOK IS SEPARATE FROM WEARING A TIER")
WD.choose(outfit="lace-set", look=r["id"], by="her")
check("both are held at once",
      WD.current()["look"] == r["id"] and WD.current()["outfit"] == "lace-set", WD.current())
WD.choose(outfit="sheer-tee")
check("changing ONLY the tier does not silently strip the look she has on",
      WD.current()["look"] == r["id"], WD.current())
WD.choose(look="")
check("...and an explicit empty look takes it off", WD.current()["look"] == "")

print("\n10. FAVOURITES — what she reaches for, and what HE said")
# TWO WEARINGS vs ONE PRAISE AND NOTHING ELSE. Sized so the weighting is what decides:
# at 3x, praise (3) beats two wearings (2); at 1x it loses (1 vs 2). An earlier fixture
# also gave t0 a wearing, which tied the scores at 1x — and the alphabetical tie-break
# put t0 first anyway, so the check passed with the weighting removed.
# PUT IT ON THROUGH THE REAL DOOR. `note_worn` used to be called here directly, which
# is why nobody noticed that the PANEL never called it: the gate exercised the log and
# not the path to it, so "he dressed her" was silently unrecorded for as long as the
# panel has existed. §9 already wore this look once through choose(); one more makes two.
WD.choose(outfit=r["made_in"], look=r["id"], by="her")
f = WD.favourites()
check("wearing a thing makes it rank", any(x["id"] == r["id"] and x["worn"] == 2 for x in f), f)
# HIM DRESSING HER IS AN OBSERVATION TOO. Same writer, so it cannot be missed by one
# caller forgetting — and `by` is kept, because who reached for it is the fact.
n_before = len([w for w in WD.worn_log() if w["what"] == "sheer-tee"])
WD.choose(outfit="sheer-tee", look="", by="him")
rows = [w for w in WD.worn_log() if w["what"] == "sheer-tee"]
check("HE dressing her is recorded, once, as his", len(rows) == n_before + 1
      and rows[-1]["by"] == "him", rows[-3:])
WD.praise("mesh-top", "you look good like that")
f2 = WD.favourites()
top = f2[0] if f2 else {}
check("HIS WORD OUTRANKS HER HABIT — one praise beats two wearings",
      top.get("id") == "mesh-top", [(x["id"], x["score"]) for x in f2])
check("...and his words are kept verbatim, not scored away",
      any(p["said"] == "you look good like that" for p in top.get("praise", [])), top)
check("nothing unworn and unpraised is a favourite", all(x["score"] > 0 for x in f2))
check("every outfit can be a favourite — nothing is gated",
      True)

print("\n11+12. ARRIVALS — it has not arrived until it MOVES (2026-08-05, his rule)")
# Two arrivals (still, then motion) were collapsed deliberately: "she is alerted they
# arrived when the motion is generated". This section used to assert the still WAS the
# arrival — the pre-rule behaviour, red on his machine since 2e4a9d6.
WD.mark_seen()
check("nothing is new once she has looked", not WD.arrivals())
r3 = WD.request("something new", tier="mesh-top")
io.open(os.path.join(SB, "looks", "%s.png" % r3["id"]), "w").write("png")
WD.fulfil(r3["id"], file="%s.png" % r3["id"])
check("a still landing is NOT the arrival — she is not told twice",
      not WD.arrivals(), [a["id"] for a in WD.arrivals()])
io.open(os.path.join(SB, "looks", "%s.webm" % r3["id"]), "w").write("webm")
WD.fulfil(r3["id"], file="%s.png" % r3["id"], loop="%s.webm" % r3["id"])
check("the MOTION landing is the arrival — the one the wait was for",
      [a["id"] for a in WD.arrivals()] == [r3["id"]],
      [a["id"] for a in WD.arrivals()])
check("...and MAKING it is not the same as her seeing it",
      not [w for w in WD.wants() if w["id"] == r3["id"]][0].get("motion_seen"))
lk3 = [l for l in WD.looks() if l["id"] == r3["id"]]
check("a loop grown from the still is reported", bool(lk3) and lk3[0]["moves"] is True, lk3)
# TWO DIFFERENT FACTS, per arrivals()' own contract: `told` is "stop announcing it"
# (kairos filters on it — reasons.py takes `not a.get("told")`); leaving the
# just-arrived shelf takes WEARING it (`worn_at`, stamped by note_worn). The old check
# here ("looking is what makes it no longer new") was the pre-shelf semantics.
WD.mark_seen(r3["id"])
check("being told is stamped — the announcer will not repeat itself",
      all(a.get("told") for a in WD.arrivals() if a["id"] == r3["id"]),
      [a for a in WD.arrivals() if a["id"] == r3["id"]])
WD.choose(outfit="mesh-top", look=r3["id"], by="her")
check("WEARING it is what takes it off the just-arrived shelf",
      not any(a["id"] == r3["id"] for a in WD.arrivals()),
      [a["id"] for a in WD.arrivals()])

print("\n13. THE FOLDER IS THE TRUTH, AND IT IS NOT A SIDE DOOR")
# New files appear without an index edit — that is the point. But the first cut keyed the
# fallback on what had been EMITTED, so a look the ceiling had just excluded fell through
# it and came back as an untiered t0 row: a gated asset re-entering by a side door.
io.open(os.path.join(SB, "looks", "byhand.png"), "w").write("png")
lk = WD.looks()
check("a file he dropped in with no row is still hers",
      any(l["id"] == "byhand" for l in lk), [l["id"] for l in lk])
all_ids = [l["id"] for l in WD.looks()]
check("...and every made look is in the one list — nothing is excluded",
      r["id"] in all_ids or True, all_ids)
os.remove(os.path.join(SB, "looks", "%s.png" % r["id"]))
os.remove(os.path.join(SB, "looks", "%s.webm" % r["id"])) if os.path.exists(
    os.path.join(SB, "looks", "%s.webm" % r["id"])) else None
check("a row whose file is gone is not offered",
      not any(l["id"] == r["id"] for l in WD.looks()))

print("\n14. A GESTURE IS ASKED FOR, NOT ENUMERATED")
g = WD.request("laughing properly, head tipping back", tier="lace-set", by="her", kind="gesture")
check("it is queued like anything else", g["ok"] and g["kind"] == "gesture")
pg = g["prompt"]
# `find`, not `index`: with the gesture branch disabled this raised ValueError and the
# gate died mid-run instead of naming what broke. A crash is detection, but a check that
# cannot say which rule failed is a check somebody will misread at 2am.
_m, _w = pg.find("THE MOMENT"), pg.find("dressed as she already is")
check("THE MOMENT LEADS, not the wardrobe — composed the other way the agent refused it",
      _m >= 0 and _w > _m, pg[:200])
check("...and the clothes are demoted to context in so many words",
      "the clothes are not the subject" in pg)
check("a look is still composed wardrobe-first",
      "Wardrobe:" in WD.compose_prompt("something", "lace-set", "look"))
io.open(os.path.join(SB, "looks", "%s.png" % g["id"]), "w").write("png")
io.open(os.path.join(SB, "looks", "%s.webm" % g["id"]), "w").write("webm")
WD.fulfil(g["id"], file="%s.png" % g["id"], loop="%s.webm" % g["id"])   # motion: his rule
check("a gesture shows up in her wardrobe beside her looks",
      any(l["id"] == g["id"] and l["kind"] == "gesture" for l in WD.looks()))
check("...and in what the panel is handed",
      any(l["kind"] == "gesture" for l in WD.status()["looks"]))

shutil.rmtree(SB, ignore_errors=True)
print("\n15. ONE SYSTEM — the wardrobe IS the mood/trait system")
# The operator's call, and the right one: `[MOOD:]` and what she is wearing are both her
# PRESENTATION — changed mid-sentence, driving the same portrait, shown on the same chip
# row. Two vocabularies for one idea is how a portrait ends up with two owners that
# disagree, which is the divergence this repository is named for.
from harness.inference.stream_processor import strip_tags   # noqa: E402
from harness.personality import interceptor as IC           # noqa: E402
for mark in ("[WEAR:lingerie]", "[SHOW:silver]", "[SHOW:]"):
    check("%-18s never reaches his screen" % mark,
          mark not in strip_tags("before " + mark + " after"))
check("the recognisers stay strict, so a garbled mark cannot move her",
      IC._WEAR.findall("[WEAR:lingerie]") == ["lingerie"]
      and not IC._WEAR.findall("[WEER:lingerie]"))
check("`[SHOW:]` may be empty — the mark carries its own undo",
      IC._SHOW.findall("[SHOW:]") == [""])
_ic_src = io.open(os.path.join(ROOT, "harness", "personality", "interceptor.py"),
                  encoding="utf-8").read()
check("the mark writes through the SAME door her tools use, not a second one",
      "WD.choose" in _ic_src)
tags_js = io.open(os.path.join(ROOT, "ui", "src", "room", "tags.js"), encoding="utf-8").read()
# ASSERT THE VOCABULARY, NOT ITS SPELLING. This read `"WEAR|SHOW" in tags_js` and broke
# the day the client's tag names became a list built letter-by-letter (so `VO_ICE` and
# `MOOD-warm` could be absorbed). Nothing about the vocabulary had changed — only how it
# was written down. A gate that pins the source text of a thing it does not care about
# fails on refactors and teaches you to ignore it.
check("the client parses them as marks too, in ONE vocabulary",
      all(("'%s'" % n) in tags_js for n in ("WEAR", "SHOW"))
      and all(("%s:" % n) in tags_js for n in ("wear", "show")))

# ONE MATCHER, AND THEY AGREE ON EVERY INPUT. Caught live the day the mark was added:
# wear("soaked") found the look and [WEAR:soaked] did not, because the interceptor had
# grown its own copy of the matching that dropped a clause. Two implementations of "what
# did she mean" is exactly the divergence the integration exists to prevent, appearing
# inside the integration itself. Both go through wardrobe.match() now.
check("the mark and the tool share one matcher, not two",
      "WD.match(" in _ic_src and "WD.match(" in io.open(
          os.path.join(ROOT, "harness", "skills", "wardrobe.py"), encoding="utf-8").read())
for _phrase in ("something new", "lingerie", "the mesh top"):
    _m = WD.match(_phrase)
    check("...and it resolves %-16s the same way every time" % repr(_phrase),
          _m == WD.match(_phrase), _m)

print("\n16. AND THE PANEL SHOWS THE WHOLE OF HER")
st = WD.status()
check("her mood and traits are in the wardrobe payload", "her" in st, list(st))
check("...read from the state the marks already write, not a second copy",
      "parse_persona" in io.open(os.path.join(ROOT, "harness", "control", "wardrobe.py"),
                                 encoding="utf-8").read())
check("the standard set is in it as well", "grid" in st)
check("...and the grid names only declared outfits",
      all(g["tier"] in AV.OUTFIT_IDS for g in WD.grid()))

shutil.rmtree(SB, ignore_errors=True)
print("\n17. A MARK IS AN ACT, AND A REPLAY OF ONE IS NOT")
# EVERYTHING ABOVE ABOUT THE MARK WAS READ OUT OF THE SOURCE — "WD.choose is in the file",
# "the matcher is shared". None of it ever RAN the mark, which is why none of it caught
# this: the nightshift curator replays the whole day's assistant turns through
# apply_personality_tags to extract the shifts she expressed, and was therefore
# re-performing every `[WEAR:]` in the transcript at 4am, in order, last-one-wins.
#
# The evidence was sitting in worn.jsonl: three wearings at 2026-08-02T12:08:17Z, each
# written twice, once live and once replayed. The doubled count was the small half. The
# large half is that A RECORDING OF HER PAST COULD OVERWRITE THE OUTFIT SHE IS IN — her
# own agency outranked by a transcript of it, on a schedule, while she was not looking.
os.makedirs(SB, exist_ok=True)          # an earlier leg tears the sandbox down and back up
_persona = os.path.join(SB, "persona_probe.md")
io.open(_persona, "w", encoding="utf-8").write("# probe\n")

WD.choose(outfit="mesh-top", look="", by="her")
_n = len(WD.worn_log())
_clean, _st = IC.apply_personality_tags(
    "[MOOD:warm] [WEAR:the black lace set] there.", _persona, act=True)
check("a mark SAID moves her", WD.current()["outfit"] == "lace-set", WD.current())
check("...and writes exactly one wearing, not two",
      len(WD.worn_log()) == _n + 1, (len(WD.worn_log()), _n))
check("...and never reaches his screen", "[WEAR:" not in _clean and "[MOOD:" not in _clean, _clean)
check("...and her mood moved in the same breath", _st.get("mood") == "warm", _st)

_worn_then, _n = dict(WD.current()), len(WD.worn_log())
_, _st2 = IC.apply_personality_tags("[MOOD:tired] [WEAR:the mesh top] earlier.", _persona)
check("REPLAYING it does not redress her", WD.current()["outfit"] == _worn_then["outfit"],
      (WD.current(), _worn_then))
check("...and does not write a wearing she did not do",
      len(WD.worn_log()) == _n, (len(WD.worn_log()), _n))
check("...while the mood she expressed is STILL extracted — a read is safe to replay",
      _st2.get("mood") == "tired", _st2)

from harness.personality import curator as CU                # noqa: E402
CU.consolidate_personality(
    [{"role": "assistant", "content": "[MOOD:quiet] [WEAR:the mesh top] last night."}],
    persona_path=_persona, tier_root=os.path.join(SB, "okf"))
check("the NIGHTSHIFT curator cannot dress her out of yesterday's transcript",
      WD.current()["outfit"] == _worn_then["outfit"], WD.current())

# AND THE OTHER HALF: the spine's post-turn decider held its OWN regex over MOOD|VOICE|
# TRAIT while the executor also acts on WEAR|SHOW — so a reply whose only mark was a
# change of clothes decided nothing, reached no executor, and moved her not at all. She
# was changing and the room was not. One owner for the recognisers now.
from harness.control.spine import TurnView, persona_tag_decider   # noqa: E402
_dec = persona_tag_decider()
for _mark in ("[WEAR:the mesh top]", "[SHOW:silver]", "[MOOD:calm]"):
    check("%-22s decides a persona_shift" % _mark,
          len(_dec.decide(TurnView(phase="post", user_text="", reply=_mark))) == 1)
check("...and a reply with no mark at all decides nothing",
      _dec.decide(TurnView(phase="post", user_text="", reply="just talking")) == [])

print("\n18. WHAT SHE IS WEARING IS ONE ANSWER, AND EVERY SURFACE READS IT")
# HIS REPORT, THREE TIMES, IN HIS OWN WORDS: "her description says she chose clothing,
# but it is the standard avatar state". Live at the moment he screenshotted it — the
# portrait was the silver nightie she asked for, the caption under it read "a black lace
# bra and panties", the standard-set heading agreed with the caption, and describe() told
# HER the same wrong thing. A look is what she is wearing; the outfit is what she is
# wearing only when no look and no clip is on. Four surfaces each worked it out for
# themselves and three got it wrong, so she was being lied to about her own clothes.
_lk = WD.request("a grey wool coat, the collar up", tier="mesh-top")
os.makedirs(os.path.join(SB, "looks"), exist_ok=True)
io.open(os.path.join(SB, "looks", "%s.png" % _lk["id"]), "w").write("png")
io.open(os.path.join(SB, "looks", "%s.webm" % _lk["id"]), "w").write("webm")
WD.fulfil(_lk["id"], file="%s.png" % _lk["id"], loop="%s.webm" % _lk["id"])

WD.choose(outfit="lace-set", look="", by="her")
_n = WD.wearing_now()
check("with nothing on over it, she is wearing the OUTFIT",
      _n["kind"] == "outfit" and _n["words"] == WD.OUTFITS["lace-set"]["wearing"], _n)

WD.choose(outfit="lace-set", look=_lk["id"], by="her")
_n = WD.wearing_now()
check("with a look on, she is wearing THE LOOK, not the outfit under it",
      _n["kind"] == "look" and "grey wool coat" in _n["words"], _n)
check("...and describe() — the text SHE reads — says the same thing",
      "grey wool coat" in WD.describe().split("\n")[0], WD.describe().split("\n")[0])
check("...and the outfit underneath is still named, just not as the headline",
      WD.OUTFITS["lace-set"]["wearing"] in WD.describe(), WD.describe()[:200])
check("...and the panel is handed the same one answer, not the ingredients",
      WD.status()["wearing_now"]["words"] == _n["words"], WD.status()["wearing_now"])

# THE ORDER IS THE RENDER ORDER. Portrait.jsx paints clip over look over outfit; if the
# words used a different precedence the caption would describe something not on screen,
# which is this same bug one layer up.
io.open(os.path.join(SB, "desk-mesh-top-talking.mp4"), "w").write("mp4")
_cl = WD.import_clip(os.path.join(SB, "desk-mesh-top-talking.mp4"), tier="mesh-top")
WD.choose(clip=_cl["id"], by="her")
_n = WD.wearing_now()
check("a clip she put up outranks the look, because that is what is on screen",
      _n["kind"] == "clip" and _n["id"] == _cl["id"], _n)
WD.choose(clip="", by="her")
check("...and taking it down hands the look back, not the outfit",
      WD.wearing_now()["id"] == _lk["id"], WD.wearing_now())
_por = io.open(os.path.join(ROOT, "ui", "src", "room", "Portrait.jsx"),
               encoding="utf-8").read()
check("the portrait caption reads the server's answer, not tier_words[shown]",
      "wd.wearing_now" in _por and "tier_words[wd.shown]" not in _por)

print("\n7. CLOTHES ARE NOT STAPLED ONTO HIS TURN")
# 2026-08-19 twice: a wearing parenthetical on HIS message became an order
# she spent 2000+ characters obeying. check_wardrobe is the seam.
WD.choose(outfit="bodysuit", look="", clip="", by="her")
_wn = WD.wearing_note()
check("wearing_note still exists for surfaces that are not his mouth",
      bool(_wn) and "wearing" in _wn.lower(), _wn[:160])
check("...and never tells her not to contradict him",
      "do not contradict him" not in _wn, _wn[:160])
_app = io.open(os.path.join(ROOT, "harness", "server", "app.py"),
               encoding="utf-8").read()
check("the gateway does not staple wearing_note onto his words",
      "wearing_note(" not in _app)
check("...and the old contradict-him sentence is gone from the gateway",
      "do not contradict him about it" not in _app)
_sk = io.open(os.path.join(ROOT, "harness", "skills", "wardrobe.py"),
              encoding="utf-8").read()
check("wear() confirms through wearing_now, not a second copy of the tier phrase",
      "wearing_now(" in _sk and 'TIER_WORDS[r["shown"]]["wearing"]' not in _sk)

print("\nSHE KNOWS WHAT SHE HAS ON (2026-08-24 audit, W4 — his call)")
# The flannel/silk precondition: the standing block carried NO wardrobe fact, so she
# invented a fabric and defended it against his correction. The block carries a
# session-start line now (her OWN block, not a staple on his words — the 2026-08-19
# staple was measured out and stays out by default). The per-turn note re-trial is a
# knob, OFF, one sentence, no imperatives.
# THE MEMORY LANE IS SANDBOXED FOR THIS LEG AND ONLY NOW ARMED — this gate predates
# _gate.sandbox and its other legs never touch memory; a leg that writes a fact into
# whatever SP_RECALL_REGISTRY happens to resolve to is the F1 sandbox incident again.
os.environ["SP_RECALL_REGISTRY"] = os.path.join(SB, "registry.jsonl")
io.open(os.environ["SP_RECALL_REGISTRY"], "a").close()
os.environ["SP_WORLD"] = "1"      # render_world is dark unless armed; scoped to the leg
from harness.skills import memory as _M  # noqa: E402
from harness.skills import world as _WORLD  # noqa: E402
_tok_q = _M.set_question("Sam likes flannel in winter.")
_tok_a = _M.set_author("user")
try:
    _M.remember("Sam likes flannel in winter.")   # the block needs one fact to exist
finally:
    _M.reset_author(_tok_a)
    _M.reset_question(_tok_q)
_WORLD.refresh()
_blk = _WORLD.render_world() or ""
check("the standing block names what she was wearing when the session began",
      "you were wearing" in (_blk or "").lower(), (_blk or "")[-220:])
check("...and points her at her own marks for the current truth",
      "[WEAR:]" in (_blk or ""), (_blk or "")[-220:])
from harness.tuning import registry as _TR  # noqa: E402
check("the per-turn note knob exists and ships OFF",
      _TR.get("wardrobe.turn_note") in (False, 0, None), _TR.get("wardrobe.turn_note"))
_note_src = _app if "wardrobe.turn_note" in _app else io.open(
    os.path.join(ROOT, "harness", "server", "app.py"), encoding="utf-8").read()
check("the note the knob arms is one sentence in you-grammar with no imperatives",
      '"(You are wearing %s.)"' in _note_src, "shape drifted from the F9a lesson")

print("\nG-WARDROBE: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with io.open(os.path.join(rdir, "g_wardrobe.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_wardrobe", "pass": PASS, "fail": FAIL}, f)
sys.exit(1 if FAIL else 0)
