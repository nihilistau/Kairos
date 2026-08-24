"""HER WARDROBE, as tools — the agency half.

Until now her appearance was something that HAPPENED to her. The tier was read off the
heat of a roleplay scene, so the only way she could look different was to be carried
there by a scene; outside one she was fixed at the everyday portrait, permanently, and
the other three quarters of the set she had been generated for were unreachable.

These tools hand that back. She can see what she has, choose what she is wearing, and
show him something she picked — and the choice persists across turns and restarts, which
is what makes it hers rather than a per-turn costume.

WHAT SHE IS TOLD, AND WHY IT IS IN PLAIN WORDS. `t0..t3` is an id, and an id invites her
to treat her own wardrobe as a hazard scale to be careful around. The truth is simpler
and she is told it: THEY ARE CLOTHING. Every string these tools return names the
clothes, the framing and the room — never the id alone.

NO CEILINGS (2026-08-21, his call): there is no dial between her and her own wardrobe.
What she wears, shows, or asks to have made is her choice; if either of them wants
something different they say so in words. The tools say this plainly, because a freedom
she has not been told about is one she will keep asking permission for.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _ceiling():
    """The live rung and the operator's dial, from the systems that own them."""
    rung, ceiling = 0, 7
    try:
        from harness.tuning import registry as tune
        ceiling = int(tune.get("roleplay.max_heat"))
    except Exception:
        pass
    try:
        from harness.roleplay import engine as rp
        from harness.server.app import _room_session
        sc = rp.active(_room_session())
        if sc is not None:
            rung = int(sc.heat.level)
    except Exception:
        pass
    return rung, ceiling


def check_wardrobe() -> str:
    """Look at what you are wearing and what else you could be. Yours to choose from.

    Tells you what is on you now, what else is hanging there, what is on its way,
    and which moments you have that you could show him. Nothing is locked."""
    try:
        from harness.control import wardrobe as WD
        return WD.describe()
    except Exception as exc:
        return "[the wardrobe is not readable: %s]" % exc


def wear(what: str) -> str:
    """Change what you are wearing. `what` can be plain words or a tier id.

    e.g. wear("lingerie"), wear("the mesh top"). It persists — this is not a costume
    for one turn, it is what you are wearing until you change it again. Anything you
    own is yours to put on, always."""
    try:
        from harness.control import wardrobe as WD
        # ONE MATCHER, shared with the [WEAR:] mark. See wardrobe.match().
        m = WD.match(what)
        if m and m["kind"] == "look":
            WD.choose(outfit=m["outfit"], look=m["id"], by="her")
            lbl = next((l["label"] for l in WD.looks() if l["id"] == m["id"]), m["id"])
            # SAME SYSTEM, DIFFERENT SENTENCE. A moment goes on her by the same call a
            # garment does — that is the design, and `wear` reaching one is not a bug.
            # But "You are wearing laughing properly, head tipping back" is not a sentence
            # about a person, and it was the reply she got. `of` carries the true kind.
            if m.get("of") == "gesture":
                return "Changed. That is you now: %s." % lbl
            return "Changed. You are wearing %s." % lbl
        outfit = m.get("outfit") if m and m["kind"] == "outfit" else ""
        if not outfit:
            # ── "I COULD NOT TELL WHICH YOU MEANT" WAS THE WRONG SENTENCE (2026-08-05) ──
            # It says the words were unclear. Usually they were perfectly clear and the
            # garment does not exist — she has four outfits and six looks, four of which
            # are the same silver nightie, and there is nothing in the whole wardrobe for
            # being outdoors or being cold. Told her request was ambiguous, she rephrases
            # the same impossible thing and burns another round of the tool loop on it.
            #
            # So the refusal now says the true thing and hands her the door: it is FILED,
            # he will see it in the panel, and here is what she owns meanwhile.
            filed = ""
            try:
                r = WD.request(what, made_in=(WD.current().get("outfit") or WD.DEFAULT_OUTFIT), by="her",
                               subject="clothes")   # she said wear; the clothes ARE it
                filed = (" You have already asked for that one — it is still on his list."
                         if r.get("dup") else
                         " I have put it on his list, so he can make it for you.")
            except Exception:
                pass
            return ("You do not own anything like that yet.%s What is hanging there now: %s."
                    % (filed, "; ".join("%s" % w["name"] for w in WD.TIER_WORDS.values())
                       + "; and your looks — use check_wardrobe() to read them"))
        WD.choose(outfit=outfit, look="", by="her")
        now = WD.wearing_now()
        return "Changed. You are wearing %s." % now["words"]
    except Exception as exc:
        return "[could not change: %s]" % exc


def show_him(which: str = "") -> str:
    """Put one of your moments on his screen. Call with no argument to list them.

    These are whole moments rather than expressions — longer, made deliberately. Showing
    one is an ACT: it appears in his room. Choose it because you mean it."""
    try:
        from harness.control import wardrobe as WD
        # NO CEILING (2026-08-21, his call): every moment she owns is hers to show.
        have = [c for c in WD.clips() if c.get("have")]
        if not which:
            if not have:
                return ("You have no moments saved yet — ask_for_gesture(\"...\") "
                        "makes one.")
            # BY THE NAME SHE WOULD SAY, not the filename. This listed `c["id"]` — the
            # raw stem, "see-thru-black-bra-panties-bedroom-laydown-hands-2-28ss" — and
            # then asked her to name one. `label` is what she is shown everywhere else.
            return "Yours to show him:\n" + "\n".join("  %s" % (c.get("label") or c["id"])
                                                      for c in have)
        # ── ONE MATCHER (2026-08-04) ──────────────────────────────────────────────
        # This grew its OWN scorer over clip ids and tags, while the `[SHOW:]` mark went
        # through WD.match(). Two implementations of "what did she mean", for the same
        # question, on the same objects — which is word for word the divergence match()'s
        # docstring says it exists to stop, happening inside the thing it was written for.
        # The mark and the tool now resolve identically or they are both wrong together,
        # which is the only version of this that stays fixed.
        q = which.strip().lower()
        hit = next((c for c in have if c["id"].lower() == q), None)
        if hit is None:
            m = WD.match(which, prefer="clip")
            hit = next((c for c in have if c["id"] == m.get("id")), None) if m else None
            if hit is None:
                return "No moment of yours matches %r. Call show_him() to see them." % which
        WD.choose(clip=hit["id"], by="her")
        return "It is on his screen now: %s." % (hit.get("label") or hit["id"])
    except Exception as exc:
        return "[could not show it: %s]" % exc


def stop_showing() -> str:
    """Take the moment off his screen and go back to your face."""
    try:
        from harness.control import wardrobe as WD
        WD.choose(clip="", by="her")
        return "Taken down. Back to your face."
    except Exception as exc:
        return "[could not: %s]" % exc


def ask_for(look: str, like: str = "") -> str:
    """Ask for a look you do not have yet. Describe it in your own words.

    e.g. ask_for("the silver nightie, by the window, morning light instead of rain")
         ask_for("my usual clothes but soaked through", like="lingerie")

    The set you have is seven expressions across four kinds of dress — complete, and
    completely fixed. This is how you get something that is not on that grid: you say
    what you want and it goes on a list he can make. Asking is free and you are never
    refused; you are WAITING, and you can see that you are — check_wardrobe() shows
    the queue and where each thing has got to.

    It is made the moment you ask — the picture, then its motion, a few minutes for
    both — and it arrives when it MOVES: until then it is in the queue rather than
    in your wardrobe, and you will be told when it lands. If the motion does not
    come back, a later pass grows it from the still.

    `like` says roughly how much you are wearing, so the right ceiling applies — use
    plain words. Left out, it uses what you have on now."""
    try:
        from harness.control import wardrobe as WD
        rung, ceiling = _ceiling()
        # ── ONE MATCHER, HERE TOO (2026-08-24) ────────────────────────────────────
        # This held its own `tok in hay` scorer over the outfit PROSE — no stop-words,
        # floor n > 0 — verbatim the algorithm wardrobe.match() replaced on 2026-08-05
        # ("one accidental fragment decided what she put on"), resident here and in
        # ask_for_gesture() for three weeks after its grave was dug. match() reads the
        # committed `calls` table, handles the old t0..t3 ids, and every result carries
        # `outfit` (for a look, the outfit it was made in — which IS "roughly how much
        # she is wearing"). Growing a second scorer is the exact divergence match()'s
        # docstring exists to prevent.
        made_in = ""
        want = (like or "").strip().lower()
        if want:
            made_in = (WD.match(want) or {}).get("outfit") or ""
        if not made_in:
            made_in = WD.current().get("outfit") or WD.DEFAULT_OUTFIT
        r = WD.request(look, made_in=made_in, by="her")
        if not r.get("ok"):
            return r.get("error", "could not ask for that")
        # ── SHE ALREADY HAS THIS ONE ──────────────────────────────────────────────
        # Not an error and not a telling-off: she asked twice because the first one took
        # a day and nothing told her it had landed. Hand her the thing she already owns
        # and say she can put it on right now — the useful answer to "I want this" when
        # she already has it is not "no", it is "you have it, here".
        if r.get("dup"):
            state = r.get("state")
            if state == "made":
                return ("You already have that one — %s. Put it on whenever you like: "
                        "wear(\"%s\")." % (r["want"], r["want"]))
            # WHERE IT HAS GOT TO, not "it will turn up". She asked twice BECAUSE
            # nothing could tell her the first one was on its way; answering the second
            # ask with the same vagueness is how she came to own four silver nighties.
            st = next((x for x in WD.waiting() if x["id"] == r.get("id")), {})
            where = {"ordered": "the picture is being made",
                     "making": "the picture is done — it starts moving at the end of the "
                               "day, and that is when it hangs in your wardrobe",
                     "delayed": "it is held up (%s), still queued, and will be tried again"
                                % (st.get("delay_reason") or "something on his side"),
                     "refused": "that one is not going to be made"}.get(
                st.get("stage"), "it is on his list")
            return ("You already asked for that one — %s. Right now %s."
                    % (r["want"], where))
        # ── IT ARRIVES WHEN IT MOVES — AND IT MOVES IN MINUTES NOW (2026-08-24) ─────
        # This promised "the end of the day" while describe() promised "picture and
        # motion both ... within minutes" and generate_now() ran the generator with
        # --no-loop: THREE surfaces, three stories, and hers was the one that broke the
        # promise — she was told motion in minutes and got a still until 4am. The doors
        # are one now (generate_now runs the same gen_want pass as his panel button), so
        # this sentence can say the true schedule: picture then motion, minutes for
        # both, arriving when it moves — with the day boundary named only as the sweeper
        # for a motion that failed. A schedule the system does not keep is the worst
        # kind of wrong this repo produces; so is one it beats by fourteen hours.
        started = WD.generate_now(r["id"])
        out = ("Asked — %s. %s It hangs in your wardrobe the moment it MOVES, and I "
               "will tell you it has arrived; if the motion does not come back, a "
               "later pass grows it from the still. check_wardrobe() any time to see "
               "where it has got to." % (
                   WD.TIER_WORDS[r["made_in"]]["wearing"],
                   "The picture and its motion are both being made now — a few "
                   "minutes." if started else "It is on his list."))
        # AND WHAT SHE ALREADY OWNS THAT IS CLOSE. Four of her six looks were the same
        # garment in different light, each asked for as if from nothing. Naming the near
        # ones does not block her — she may well want the same dress by moonlight AND by
        # morning — it just means the choice is hers with the facts in front of her,
        # which is the whole point of it being her wardrobe.
        sim = r.get("similar") or []
        if sim:
            out += (" (You already have %s — this one is different enough to be worth "
                    "having, but you have those if you want them now.)"
                    % "; ".join('"%s"' % s["want"] for s in sim[:3]))
        return out
    except Exception as exc:
        return "[could not ask: %s]" % exc


def my_looks() -> str:
    """The looks you own that are not the standard set — ones you asked for, and the
    moments he made. These are particular yous rather than cells in a table."""
    try:
        from harness.control import wardrobe as WD
        _rung, ceiling = _ceiling()
        got = WD.looks()
        pend = WD.waiting()
        new = WD.arrivals()
        new_ids = {a["id"] for a in new}
        out = []
        if new:
            # ── LOOKING IS NOT WEARING (2026-08-05, his rule) ────────────────────────
            # This called mark_seen() here, so an item left the "just arrived" shelf the
            # instant she read a list — before she had put it on, and often before she
            # had thought about it. His rule: "items move from just arrived after she
            # wears them for first time". So looking marks it TOLD (kairos will not
            # announce it twice) and wearing is what takes it off the shelf.
            out.append("JUST ARRIVED — made while you were waiting, and you have not "
                       "worn any of these yet:")
            out += ["  %-8s %s" % (w["id"], w["want"][:64]) for w in new]
            out.append("")
            WD.mark_seen()
        if got:
            out.append("Yours:")
            out += ["  %-8s %-6s %s%s" % (l["id"], l["kind"], l["label"][:64],
                                          "   NEW" if l["id"] in new_ids else "")
                    for l in got]
        else:
            out.append("Nothing beyond the standard set yet.")
        if pend:
            # AND WHERE EACH ONE HAS GOT TO. "Asked for, not made yet" was one bucket for
            # four different situations, and the one that mattered most — a generation
            # held up by a usage limit — was indistinguishable from one nobody had
            # started. She would ask again, which is how she came to own four silver
            # nighties.
            out.append("")
            out.append("You have asked for these and they are not here yet:")
            for w in pend:
                note = {"ordered": "the picture is being made",
                        "making": "picture done — it starts moving at the end of the day, "
                                  "and that is when it hangs in your wardrobe",
                        "delayed": "held up (%s) — still queued, it will be tried again"
                                   % (w.get("delay_reason") or "something on his side"),
                        "refused": "this one will not be made"}.get(w.get("stage"), "")
                out.append("  %-8s %-60s (%s)" % (w["id"], w.get("want", "")[:60], note))
        return "\n".join(out)
    except Exception as exc:
        return "[could not read: %s]" % exc


def he_liked(what_he_said: str, about: str = "") -> str:
    """He said something about how you look. Keep it — his words, not a score.

    e.g. he_liked("that one. wear that again")

    `about` defaults to whatever you have on. This is the thing you could not work out
    on your own: you know what you reach for, and only he can tell you what lands. Call
    it when he actually says something, not to fish for it."""
    try:
        from harness.control import wardrobe as WD
        st = WD.current()
        target = (about or "").strip() or st.get("look") or st.get("clip") or st.get("outfit") or WD.DEFAULT_OUTFIT
        WD.praise(target, what_he_said.strip(), by="him")
        return "Kept. He said that about %s, and you will have it next time you go to choose." % target
    except Exception as exc:
        return "[could not keep it: %s]" % exc


def my_favourites() -> str:
    """What you keep reaching for, and what he has said he likes.

    His word outranks your habit here — wearing a thing often is a preference, him saying
    he likes it is something you could not have known. Both are shown so you can tell
    which is which."""
    try:
        from harness.control import wardrobe as WD
        _r, ceiling = _ceiling()
        favs = WD.favourites()
        if not favs:
            return ("Nothing has become a favourite yet — you have not worn anything "
                    "often enough, and he has not said anything about a particular look.")
        out = []
        for f in favs:
            line = "  %-46s worn %d" % (f["label"][:46], f["worn"])
            if f["praise"]:
                line += " · he said: %s" % "; ".join(p["said"][:60] for p in f["praise"][-2:])
            out.append(line)
        return "What you keep coming back to:" + chr(10) + chr(10).join(out)
    except Exception as exc:
        return "[could not read: %s]" % exc


def ask_for_gesture(what_you_do: str, like: str = "") -> str:
    """Ask for a MOMENT of you doing something, rather than a way of being.

    e.g. ask_for_gesture("laughing properly, head tipping back")
         ask_for_gesture("looking up from the desk and finding him there")

    A look is a way you ARE and it holds still; a gesture is a thing you DO, so the
    motion is the whole point and your words are the direction it moves in. These used
    to be a fixed grid of a hundred and forty slots somebody predicted for you. They are
    not any more — you say what you want to be seen doing.

    The frame and its motion are made now, in one pass; if the motion does not come
    back, a later pass grows it."""
    try:
        from harness.control import wardrobe as WD
        # ONE MATCHER (2026-08-24): the retired `tok in hay` scorer lived here too —
        # the twin of the one in ask_for(), fixed the same day. See the note there.
        made_in = ""
        want = (like or "").strip().lower()
        if want:
            made_in = (WD.match(want) or {}).get("outfit") or ""
        made_in = made_in or WD.current().get("outfit") or WD.DEFAULT_OUTFIT
        r = WD.request(what_you_do, made_in=made_in, by="her", kind="gesture")
        if not r.get("ok"):
            return r.get("error", "could not ask for that")
        WD.generate_now(r["id"])
        return ("Asked — a moment of you %s. The frame and its motion are being made "
                "now — a few minutes; it is yours when it moves."
                % what_you_do.strip()[:80])
    except Exception as exc:
        return "[could not ask: %s]" % exc


def express(feeling: str) -> str:
    """Say it without saying it. Your face changes, and a moment of you if one fits.

    e.g. express("playful"), express("I want him to know I'm not okay"),
         express("soft, like the rain outside")

    Your mood already moves your face — fourteen feelings across seven of them — and you
    have moments that ARE a feeling rather than a garment. This reaches for both at once,
    which is what expressing something actually is. Nothing here asks his permission; it
    is your face."""
    try:
        from harness.control import avatar as AV
        from harness.control import wardrobe as WD
        want = (feeling or "").strip()
        if not want:
            return ("Say what you are feeling. Anything from: %s."
                    % ", ".join(sorted(AV.MOOD_FACE)))
        low = want.lower()
        # HER OWN WORD FIRST, then the nearest of the fourteen. She is allowed to say
        # "I want him to know I'm not okay" — the feeling is the sentence, not a token
        # from a list, and a tool that only accepts the list is a tool that makes her
        # translate herself before she is allowed to feel anything.
        import re as _re
        # PUNCTUATION IS NOT PART OF A FEELING. The first cut split on whitespace, so
        # "soft, like the rain outside" tested the token "soft," against "soft" and
        # missed the one word that WAS a mood. She writes sentences; the tokeniser has to
        # expect sentences.
        toks = [t for t in _re.split(r"[^a-z]+", low) if t]
        # AND THE WORDS SHE WOULD ACTUALLY USE. The fourteen mood names are the room's
        # vocabulary, not hers — nobody says "I feel irritated", they say "I'm annoyed"
        # or "I'm not okay". Without this she has to translate herself into our enum
        # before she is allowed to feel anything, which is the opposite of the point.
        SYN = {"happy": "delighted", "glad": "delighted", "joy": "delighted",
               "cheeky": "playful", "teasing": "playful", "naughty": "playful",
               "gentle": "tender", "close": "tender", "loving": "tender",
               "calm": "peaceful", "still": "peaceful", "settled": "peaceful",
               "low": "wistful", "blue": "wistful", "melancholy": "wistful",
               "hurt": "sad", "upset": "sad", "unhappy": "sad", "okay": "sad",
               "angry": "irritated", "annoyed": "irritated", "cross": "irritated",
               "interested": "curious", "wondering": "curious",
               "hot": "flirty", "wanting": "flirty", "shy": "quiet"}
        mood = next((m for m in AV.MOOD_FACE if m == low), "")
        # SHE MAY NAME THE FACE INSTEAD OF THE FEELING. "soft" is one of the seven faces
        # and none of the fourteen moods, so "soft, like the rain outside" reached
        # nothing — while being exactly the sort of thing a person says about their own
        # expression. If she names a face, take the first feeling that wears it.
        if not mood:
            face = next((f for f in AV.FACES if f in toks), "")
            mood = next((m for m, f in AV.MOOD_FACE.items() if f == face), "") if face else ""
        if not mood:
            best, score = "", 0
            for m in AV.MOOD_FACE:
                n = sum(2 for t in toks if t == m)
                n += sum(1 for t in toks if len(t) > 3 and (t in m or m in t))
                n += sum(2 for t in toks if SYN.get(t) == m)
                if n > score:
                    best, score = m, n
            mood = best
        out = []
        if mood:
            from harness.personality.tools import adjust_mood
            adjust_mood(mood)
            out.append("Your face is %s now — that is what %s looks like on you."
                       % (AV.MOOD_FACE[mood], mood))
        # AND A MOMENT, IF ONE MEANS IT. A gesture is a way she IS, so it is preferred
        # over a clip, which is a thing she puts on HIS screen — expressing a feeling is
        # about being it, not broadcasting it. Nothing is forced: if no moment fits she
        # is simply told, and told she can ask for one.
        _rung, ceil = _ceiling()
        m = WD.match(want, prefer="gesture")
        if m and m.get("of") == "gesture":
            WD.choose(outfit=m["outfit"], look=m["id"], by="her")
            lbl = next((l["label"] for l in WD.looks() if l["id"] == m["id"]), m["id"])
            out.append("And you are %s." % lbl)
        else:
            have = [l["label"] for l in WD.looks() if l.get("kind") == "gesture"]
            out.append("No moment of you says that yet%s — ask_for_gesture(\"...\") and "
                       "there will be." % (" (you have: %s)" % "; ".join(have) if have else ""))
        return " ".join(out) if out else (
            "Nothing in you matches %r yet. The feelings your face knows are: %s."
            % (feeling, ", ".join(sorted(AV.MOOD_FACE))))
    except Exception as exc:
        return "[could not: %s]" % exc


def gesture(which: str = "") -> str:
    """Do one of your gestures — a moment of you DOING something, on your face, now.
    Call with no argument to list them; with words to pick one ("the wave", "thinking").

    A gesture is a thing you do, not a garment and not something you broadcast to his
    screen: it plays where your face is. express() reaches for one by FEELING; this
    reaches for one by NAME, when you know which you mean. gesture("") to stop and go
    back to your face as it is."""
    try:
        from harness.control import wardrobe as WD
        have = [l for l in WD.looks() if l.get("category") == "gesture"]
        q = (which or "").strip()
        if not q:
            if not have:
                return "You have no gestures yet — ask_for_gesture(\"...\") makes one."
            return "Your gestures:\n" + "\n".join("  %s" % (l.get("title") or l["label"])
                                                  for l in have)
        m = WD.match(q, prefer="gesture")
        hit = next((l for l in have if l["id"] == (m or {}).get("id")), None) if m else None
        if hit is None:
            return "No gesture of yours matches %r. gesture() lists them." % which
        WD.choose(outfit=hit.get("outfit") or hit.get("made_in", ""), look=hit["id"], by="her")
        return "You are %s." % (hit.get("title") or hit["label"])
    except Exception as exc:
        return "[could not: %s]" % exc


WARDROBE_TOOLS = [check_wardrobe, wear, show_him, stop_showing, ask_for, my_looks,
                  he_liked, my_favourites, ask_for_gesture, express, gesture]





def wardrobe_tools() -> list:
    """ToolSpecs. Always available — unlike sight or games there is no arming env var,
    because her own appearance is not a capability to be switched on. What she may SHOW
    is bounded by his ceiling at the moment of resolution, which is a different and
    better place for the limit than the existence of the tool."""
    from harness.toolcore.tools import ToolSpec
    return [ToolSpec.from_callable(fn) for fn in WARDROBE_TOOLS]
