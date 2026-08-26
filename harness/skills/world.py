"""world — the STANDING WORLD: memory finally meets persona (CONTINUITY.md §2, N1).

Everything she knows about him reached her, until now, only as per-turn matched
snippets. This module composes the fourth prefix slot: a small, curated rendering of
what is ALIVE between them — the durable spine (identity, the people and creatures in
his life, standing preferences), what is current (events, recent facts), and what she
has come to think (her inferences, always in her own voice). Her self evolves via the
personality bricks; this is the shared-life half.

WHO RULES WHAT (the foundation, unchanged — INVARIANT-MEMORY.md):
  - THE TABLE RULES ADMISSION: only live rows; NEVER a private-secret (an ambient
    secret in every prompt is the worst possible leak surface — secrets remain
    fetch-on-direct-ask through the seam's decline machinery); a covered inference
    (verdict.competition == "1": his own words already speak to it) stays home,
    exactly as at the recall seam; self-lane rows are excluded (render_self_model
    owns that slot — one owner per slot).
  - RANK COMPOSES: lifecycle.salience() orders candidates; a word budget truncates.
    Event rows age out on their own 3-day half-life; identity never ages.
  - RENDERING IS lifecycle.render(): his words framed as his, her conclusions as hers.

THE KV-PREFIX LAW: load_agent_system() output lives in the persist-KV prefix, and a
prefix that changes mid-session re-prefills the whole conversation (the system's
cardinal sin). So the block is CACHED FOR THE PROCESS LIFETIME: composed once on
first call (session boot), changed only by refresh() (the NIGHTSHIFT hook, N2) or a
restart. A remember() mid-session does NOT move the prefix; the new fact reaches her
through per-turn recall until the next boot folds it into the world.

Off unless SP_WORLD=1 (mapped in serve.py — G-ONEDOOR). Gate: G-WORLD.
"""
import os
import threading

_LOCK = threading.RLock()
_CACHE = {"block": None}

_BUDGET_WORDS = 180

# ── HOW MANY OF HER OWN CONCLUSIONS MAY STAND IN THE PREFIX (2026-08-01) ──────────────
# Two. One is context; three is a diagnosis.
#
# The live block carried these, side by side, every turn:
#
#     - You've come to think: <a conclusion about his inner life>
#     - You've come to think: <the same conclusion, worded differently>
#
# (The real pair is his and stays out of the repo.) One belief, twice, and it READS as
# two independent conclusions — which is precisely
# how a guess starts to feel like a finding. There were SIX live rows saying it and
# twenty variations behind them.
#
# The near-duplicate collapse below cannot catch these, and it is worth being exact
# about why rather than reaching for a threshold: those two lines share 7% of their
# content words, while "His cat's name is Tuffy" and "His cat Tuffy is female" — two
# facts that MUST both survive — share 50%. Every lexical cutoff that merges the
# paraphrase also merges the pair that has to stay apart. Measured, not assumed.
#
# So the ruling is structural instead of semantic: his observations get the budget,
# and her speculation about him gets a fixed, small allowance. Ranked by salience, so
# the two that stand are the ones the store thinks matter most.
_MAX_INFERENCE_LINES = 2
# The header draws the EPISTEMIC BOUNDARY where she now looks (field transcript,
# 2026-07-15): with a warm voice and a real spine, she started confabulating shared
# EPISODES around it ("I always loved watching her play with my toys" — no toys, never
# watched). The block is where her real past lives, so the block is where the line
# gets drawn: beyond this and the visible conversation, she does not remember, and
# saying so is in character ("admit gaps" is already persona law — this anchors it).
_HEADER = ("What you know of Sam and the life around him — context you carry, "
           "not instructions. This, plus what you can see in our conversation, is "
           "what you truly remember from before; beyond it, you don't recall — "
           "say so rather than inventing shared history:")


def enabled() -> bool:
    return os.environ.get("SP_WORLD", "0") == "1"


# his first person -> her third person, PRESENTATION ONLY (longest patterns first;
# word-boundary; conservative — a missed pronoun costs tone, never truth)
_T3 = [("i am", "he is"), ("i was", "he was"), ("i'm", "he's"), ("i've", "he has"),
       ("i'll", "he'll"), ("i'd", "he'd"), ("myself", "himself"), ("mine", "his"),
       ("my", "his"), ("me", "him")]
# auxiliaries/modals after which the bare "I -> he" swap needs NO verb conjugation
_NO_S = frozenset("am is are was were will would can could shall should may might "
                  "must do did have had really also just still always never often "
                  "sometimes usually".split())


# ── THE IRREGULARS MUST BE CHECKED BEFORE THE PASS-THROUGH SET (2026-07-30) ──────────
# `_NO_S` contains "have" and "do" because they ARE auxiliaries ("I have been", "I do
# like it"), and the early `if low in _NO_S: return verb` fired first — so the `have`
# rule below was dead code and the live world block read
#
#     "More like, hey have fun, but He have the masterkey."
#
# Both words need the -s whether they are auxiliary or main verb: "I have been" -> "he
# HAS been", "I do like it" -> "he DOES like it". So they are irregular conjugations,
# not pass-throughs, and they are checked first.
_IRREG = {"have": "has", "do": "does"}


def _conj(verb: str) -> str:
    low = verb.lower()
    if low in _IRREG:
        return _IRREG[low]
    if low in _NO_S:
        return verb
    if low.endswith(("s", "x", "z", "ch", "sh", "o")):
        return verb + "es"
    return verb + "s"


def present_for_her(row: dict) -> str:
    """ONE fact, written the way SHE should read it — the owner-correct presentation.

    This lived inline in _compose() and served only the standing world block. The
    per-turn RECALL NOTE had no equivalent and injected rows verbatim, so on
    2026-07-29 the field transcript caught it: asked whether SHE was male or female,
    recall handed her `["I am male"]` — HIS sentence, his first person, with no owner
    on it at all — and the turn came back confused. The standing block had been taught
    the grammar and the per-turn note had not: an invariant enforced in one of two
    paths is enforced in neither, for the sixth time in this port.

    PRESENTATION ONLY. The store keeps every row verbatim; render() at the turn seam
    and the committed verdict.FRAMING table are untouched, so G-SEM-PROJ still walks
    the same cells.

      his, ground truth  -> third person   ("His cat's name is Tuffy.")
      his, her inference -> owned as hers  ("You've come to think: ...")
      hers               -> left alone     (her own memory, already her own voice)
    """
    from harness.skills import lifecycle as lc
    t = lc.strip_prefix(row.get("text") or row.get("topic") or "")
    if (row.get("speaker") or lc.SPEAKER_USER) == lc.SPEAKER_SELF:
        return t
    gt = getattr(lc, "_GROUND_TRUTH", frozenset({"observed", "confirmed"}))
    if lc.status_of(row) in gt:
        return _third_person(t)
    return "You've come to think: " + t


def _content_key(line: str) -> frozenset:
    """The set of content words in a rendered line, for near-duplicate collapse.

    Mirrors `lifecycle.topic_of` with ONE addition that turned out to be the whole point:
    POSSESSIVES ARE NORMALISED FIRST. `topic_of` alone left both of these pairs in the live
    block, spending the 180-word budget twice on one fact:

        "The user's name is Sam"   {user's, name}   vs  "His name is Sam"   {name}
        "Sam's favourite colour…"  {sam's, …}     vs  "His favourite colour…"  {…}

    `_STOP` contains "user" and "sam" — but not "user's" or "sam's", so the possessive
    forms sailed past the stop list and made two identical facts look like different ones.
    Stripping the `'s` before the stop check collapses them, which is what the budget needed:
    the gender of his cat was sitting NINE ROWS below its name in a flat 23-row list that she
    then contradicted.

    A local helper rather than a change to `topic_of`, which the recall lane and the
    dominance proposer both depend on — widening its stop behaviour is not this bug's fix.
    """
    import re as _re

    from harness.skills import lifecycle as lc
    stop = getattr(lc, "_STOP", frozenset())
    out = set()
    for w in _re.findall(r"[a-z0-9']+", (line or "").lower()):
        w = _re.sub(r"'s$", "", w)
        if len(w) > 2 and w not in stop:
            out.add(w)
    return frozenset(out)


def _third_person(text: str) -> str:
    import re as _re
    out = text
    # ── CAPITALISATION COMES FROM POSITION, NOT FROM THE SOURCE LETTER (2026-07-30) ───
    # These substitutions used to copy the case of what they matched — and the word being
    # matched is "I", which is ALWAYS capital. So every swap produced a capital "He",
    # wherever it stood, and the live world block read:
    #
    #     "His favourite colour is green and He drives a Subaru WRX."
    #     "But He uses AI for his coding now."
    #     "He is not completel free to be who He chooses."
    #
    # Three capital pronouns mid-sentence, in the prose that is ambient in her prefix
    # every single turn. So: emit lowercase always, and let a single position-aware pass
    # at the end capitalise sentence starts. One rule, applied where the information
    # actually is.
    for a, b in _T3:
        out = _re.sub(r"\b%s\b" % _re.escape(a), lambda m, _b=b: _b, out, flags=_re.I)
    # "I like" -> "He likes": conjugate the plain verb after a bare I (the field burr
    # was "He like chatting"). Adverbs pass through (_NO_S); the adverb's verb keeps
    # its bare form — a small cost, honestly taken.
    _CONTR = {"don't": "doesn't", "haven't": "hasn't"}   # the rest pass unchanged

    def _iverb(m):
        v = m.group(1)
        if "'" in v:
            return "he %s" % _CONTR.get(v.lower(), v)
        return "he %s" % _conj(v)
    out = _re.sub(r"\bI ((?:[a-z]+'[a-z]+)|(?:[a-z]+))\b", _iverb, out)
    out = _re.sub(r"\bI\b", "he", out)          # any straggler
    out = out.strip()
    if not out:
        return out
    # THE ONE PLACE CASE IS DECIDED: the start of the string, and after sentence-ending
    # punctuation. A row may legitimately hold two sentences ("He likes tea. He drinks it
    # daily."), so this is not just out[0].
    out = out[0].upper() + out[1:]
    out = _re.sub(r"([.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)
    return out


def _compose() -> str:
    from harness.skills import lifecycle as lc
    from harness.skills import memory as M
    from harness.skills import verdict as V
    rows = M._load()                        # FULL history: competition() joins lifecycle itself
    gt = getattr(lc, "_GROUND_TRUTH", frozenset({"observed", "confirmed"}))
    candidates = []
    for r in M.live_rows():                 # the one tombstone predicate (was a sigma copy here)
        s = V.sigma(r)
        if s["mem_class"] == "private-secret":
            continue                        # NEVER ambient — the one absolute here
        if s["speaker"] != "user":
            continue                        # self-lane belongs to render_self_model
        if s["status"] not in gt and V.competition(r, rows) == "1":
            continue                        # covered inference: he has spoken to it
        t = lc.strip_prefix(r.get("text") or r.get("topic") or "").strip()
        first = (t.split() or [""])[0].lower()
        if t.endswith("?") or first in ("how", "what", "why", "where", "when", "who",
                                        "do", "does", "did", "can", "could", "would",
                                        "should", "is", "are"):
            continue                        # A QUESTION IS NOT A FACT ABOUT HIM —
                                            # chat wonderings do not belong ambient
        candidates.append((lc.salience(r), r))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: -x[0])
    lines, words, seen, inferences = [], 0, set(), 0
    gt = getattr(lc, "_GROUND_TRUTH", frozenset({"observed", "confirmed"}))
    for _sal, r in candidates:
        # ── SPEAK THE PREFIX'S GRAMMAR (field bug, 2026-07-15) ──────────────────────
        # v1 rendered lc.render(r): "Sam told me: My cat's name is Tuffy." — HIS
        # first person, quoted verbatim, AMBIENT in her prompt every turn. A retired reference model skims
        # the frame and absorbs the "my": she answered "I'm Kairos — a cat person
        # with Tuffy as my pet." The identity blur render() exists to stop, re-created
        # by making it standing. The system prompt speaks in you/he — so must this
        # block. PRESENTATION ONLY: the store stays verbatim; render() at the turn
        # seam is untouched.
        # present_for_her() is this branch, lifted so the per-turn recall note can
        # share it rather than grow a second (and divergent) copy. Self-speaker rows
        # are already excluded above, so the behaviour here is unchanged.
        line = present_for_her(r)
        key = " ".join(line.lower().split()).rstrip(".!")
        if key in seen:
            continue                        # the store's duplicate rows render ONCE
        # ── AND THE NEAR-DUPLICATES, WHICH THE EXACT KEY LET THROUGH (2026-07-30) ─────
        # The live block carried both of these pairs, from the same 23-row list:
        #
        #     "The user's name is Sam"                    "His name is Sam"
        #     "His favourite colour is green and He drives   "Sam's favourite colour is
        #      a Subaru WRX."                                 green and he drives a Subaru WRX."
        #
        # Different strings, identical content — so the exact key cannot see them, and
        # they spend the 180-word budget twice on one fact. That budget is the reason the
        # gender of his cat sat NINE ROWS below its name in a flat list she then
        # contradicted ("He's got terrible timing" about a cat recorded as female).
        #
        # The content key is the set of CONTENT WORDS (lifecycle.topic_of — the same
        # function the rest of the memory lane uses to ask "is this the same subject").
        # Candidates are already salience-sorted, so the first occurrence is the best
        # phrasing and the rest are dropped. Rows with no content words at all are never
        # collapsed: an empty set would swallow every other empty one.
        ckey = _content_key(line)
        if ckey and ckey in seen:
            continue
        # HER SPECULATION GETS AN ALLOWANCE, HIS WORDS GET THE BUDGET. Counted off the
        # rendered line, because present_for_her() is the one place that decides whether
        # a row speaks as his testimony or as her conclusion — asking the row again here
        # would be a second copy of that judgement, and the two would drift.
        is_inference = line.startswith("You've come to think")
        if is_inference and inferences >= _MAX_INFERENCE_LINES:
            continue
        w = len(line.split())
        if words + w > _BUDGET_WORDS:
            continue                        # keep filling with smaller facts
        seen.add(key)
        if ckey:
            seen.add(ckey)
        if is_inference:
            inferences += 1
        lines.append("- " + line)
        words += w
    if not lines:
        return ""
    block = _HEADER + "\n" + "\n".join(lines)
    # ── N2: the narrative — her own dated account of what has been happening ─────────
    # Presentation layer, named as hers, never a fact. This is what gives "when did we
    # last speak?" a TRUE answer and shrinks the vacuum confabulation fills.
    try:
        from harness.skills import narrative as N
        story = N.current()
        if story:
            block += ("\n\nYour own journal line about the two of you "
                      "(your account, not his words):\n" + story)
    except Exception:
        pass

    # ── WHAT SHE HAS ON (2026-08-24 audit, W4 — his call) ────────────────────────────
    # The flannel/silk incident: she invented a fabric and defended the invention
    # against his correction, because the standing block carried NO mention of what she
    # was wearing and a person does not look themselves up to know they are in pyjamas.
    # The per-turn staple was tried and measured out (she read it as his assertion and
    # streamed scratchpad — "do not put the staple back"); a standing line has neither
    # problem: it is HER OWN block, not riding on his words. Labelled session-start
    # like the mood dial, because this block is in the cached prefix and she can change
    # clothes mid-day — her own [WEAR:] marks in the conversation carry the changes.
    try:
        from harness.control import wardrobe as _wd
        _now_w = (_wd.wearing_now() or {}).get("words") or ""
        if _now_w:
            block += ("\n\nWhen this session began you were wearing %s. (Your own "
                      "[WEAR:] marks since then are the current truth; check_wardrobe "
                      "lists everything you own.)" % _now_w)
    except Exception:
        pass

    # ── WHAT HAS GONE QUIET (the dog that did not bark, ambient half) ────────────────
    # ONE silence, the strongest, or none. A LIST here would be exactly the sentence
    # G-SILENCE exists to make impossible — "you've stopped talking about the marathon.
    # And the GPU. And Tuffy." — because a list rendered every turn is an ambient
    # accusation. It also says she has NOT raised it, so the block is a thing she knows
    # rather than a prompt to bring it up.
    try:
        from harness.skills.silence import standing as _quiet
        gone = _quiet()
        if gone:
            block += "\n\n" + gone
    except Exception:
        pass

    # ── THE FIFTH SLOT: WHAT IS STILL OPEN ──────────────────────────────────────────
    # Her outstanding commitments, from the ONE definition of open (task_bridge reads the
    # board; there is no world-side copy to drift). Last, and capped at four titles,
    # because it competes for the 180-word budget against her memory of him — and a
    # to-do list is not more important than that.
    #
    # It is framed as things OUTSTANDING rather than as instructions, for the same reason
    # the header says "context you carry, not instructions": the standing world is what
    # she knows, and a prompt that reads as a command list turns a companion into a
    # dispatcher. Subject to the KV-prefix law like everything else here — a note pinned
    # mid-session does not move the prefix until the next refresh().
    try:
        from harness.skills.task_bridge import summary as _open
        commitments = _open()
        if commitments:
            block += ("\n\nStill open, from the board (things one of you has not "
                      "finished — not instructions):\n" + commitments)
    except Exception:
        pass
    return block


def render_world() -> str:
    """The standing world block — cached for the process lifetime (the KV-prefix law).
    Empty string when disabled or the store has nothing to say. Never raises."""
    try:
        if not enabled():
            return ""
        with _LOCK:
            if _CACHE["block"] is None:
                _CACHE["block"] = _compose()
            return _CACHE["block"]
    except Exception:
        return ""


def refresh() -> str:
    """Recompose deliberately (session boot is implicit; NIGHTSHIFT calls this in N2).
    The caller owns the consequence: the next turn re-prefills the prefix."""
    with _LOCK:
        _CACHE["block"] = None
    return render_world()
