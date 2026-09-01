"""admission.py — what may enter the store, in what form, and filed as what.

`remember()` is the authoritative writer and this is the chain of refusals in front of it.
Every one of them **returns a sentence she reads**, never a silent no-op: a store verb that
quietly fails is how she ends up promising to remember what she cannot.

WHY IT IS ITS OWN MODULE. Four of the six rows in AGENTS.md §0's table were born in this
chain, and each is a rule that was enforced on one path into memory and not another:

  * **the packaging comes off at the door.** *"Remember my GPU is an RTX 2060"* is a fact
    wearing an imperative. Stored whole, the verb becomes content (it retrieved itself on
    *"do you REMEMBER what sex you are?"*) and the slot is wrong, so it never superseded the
    real GPU row. **Every guard below must see the CLAIM, not the wrapper** — which is why
    normalisation comes FIRST here, and why the order in this file is load-bearing.
  * **admission at the store, not only at the daemon.** The daemon's gate refused impersonal
    sentences and she immediately stored one through the tool instead.
  * **the author picks the gate; the kind picks the class.** These were one condition, so her
    own sentence was judged by `is_memorable` — the gate for facts ABOUT SOMEONE, which
    refuses first-person prose by design — unless a producer had also named a narrative kind,
    which she cannot do. Her own door was shut, and every gate stayed green because every
    harness producer passes a kind.
  * **the identity firewall.** She answered *"what is your name?"* correctly and then stored
    that sentence in the USER store, where it superseded all three rows saying the user is
    Sam. The store came out asserting that Sam is called Kairos.

THE ORDER IS THE INVARIANT, so it is asserted rather than described: `G-REMEMBER-PIPELINE`
compares byte offsets inside `admit()`'s own source and drives every refusal through
`remember()`. A reordering here is not a style change; it is one of those four coming back.

`admit()` decides and reports. It does not write, does not read the registry, and does not
touch the lock — which is what makes it drivable on its own, and it is driven, not read.
"""
from __future__ import annotations

import collections
import logging

from harness.loud import swallowed as _sw
from harness.skills.memory.authorship import _AUTHOR

_log = logging.getLogger("harness.memory")     # the same object; see store.py's note

# WHAT THE WRITER NEEDS BACK. Five values, because the chain does four things at once: it can
# REFUSE (a sentence, which `remember()` then returns verbatim), it can REWRITE the fact (the
# imperative comes off; her own line is kept as said), it can ZERO the class and kind (a
# producer's labels mean nothing outside her lane), and it reports whether this is her
# NARRATIVE — which decides, 150 lines later in the writer, that nothing gets retired.
#
# A namedtuple rather than a bare 5-tuple: `a.self_narr` at the call site is the difference
# between a reader knowing what index 4 means and a reader guessing.
Admission = collections.namedtuple("Admission", "refusal fact mem_class kind self_narr")


def admit(fact: str, *, kind: str = "", mem_class: str = "") -> "Admission":
    """May this enter the store, as what, and if not — what does she say?

    `refusal` is None when the fact is admitted; otherwise it is the exact sentence
    `remember()` returns, unchanged.
    """
    # ── ANONYMOUS MODE (2026-08-23, the operator's ask) ─────────────────────────────────────────
    # THE ONE DOOR IS WHY THIS IS ONE LINE. Everything that ever enters this store comes
    # through remember() — the tool, _capture_after_turn, the consolidator, the reflector,
    # remember_about_self and therefore every self-narrative row, the episode mint and the
    # semantic index that hang off the write — which is `store.commit_row` now, not
    # something "below" this line. Guarding HERE guards all of them,
    # including callers written after this line. Guarding callers instead is how you get a
    # mode that says "nothing was recorded" over an evening sitting in the registry.
    # It returns a SENTENCE, not a silent no-op: she reads this string, and a store verb
    # that quietly fails is how she ends up promising to remember what she cannot.
    from harness.control import anon as _anon
    if _anon.holds("memory.row"):
        return Admission(_anon.WHY, fact, mem_class, kind, False)
    # ADMISSION AT THE STORE (2026-07-12). The daemon's B4 gate now refuses impersonal
    # sentences — and she immediately stored one THROUGH THIS TOOL instead (G-ADMISSION
    # caught an ep_tool_ row holding "The kind nurse painted the tall building..."). An
    # invariant guarded in only ONE of the paths into memory is not guarded. Every path
    # enforces it now.
    from harness.skills import lifecycle as lc

    # THE PACKAGING COMES OFF AT THE DOOR (2026-07-14). "Remember my GPU is an RTX 2060." is a
    # FACT WEARING AN IMPERATIVE. Stored whole, the verb becomes content (it retrieved itself on
    # "do you REMEMBER what sex you are?") and the slot is wrong ("remember my gpu", not
    # "user::gpu", so it never superseded the real GPU row). Every guard below must see the CLAIM,
    # not the wrapper. See lifecycle.normalize_fact.
    _raw = fact                         # her narrative is judged and kept AS SAID (below)
    fact = lc.normalize_fact(fact)

    # ── THE REAL HER (2026-08-22): her narrative is admitted as HERS, by its own rule ──
    # A producer (the kairos speak path, the journal, a verified persona shift, the
    # stance extractor, the nightly becoming) names the class and the kind; the author
    # must be self. Outside her lane the explicit class means nothing.
    from harness.skills import memclass as _mc
    _self_narr = (_AUTHOR.get() == "self" and mem_class in (_mc.SELF_NARRATIVE, _mc.FEELING)
                  and kind in _mc.NARRATIVE_KINDS)
    # ── WHO IS SPEAKING PICKS THE GATE; THE KIND PICKS THE CLASS (2026-08-30) ────────
    # These were one condition, so her sentence was judged by `is_memorable` — the gate
    # for facts ABOUT SOMEONE, which refuses first-person prose BY DESIGN — unless a
    # producer had also named a narrative kind. She cannot name one: the tool takes a
    # fact, and its docstring says "you need not pass any of them". So her own door was
    # shut, and she said so herself, in her own time: "I tried to store that feeling as
    # a fact about myself, but the system wouldn't let me... I guess some things are too
    # much of a feeling to be a fact." `is_memorable`'s own refusal even reads "If it is
    # true of you, use remember_about_self" — the function she was already inside. Two
    # doors pointing at each other, neither opening.
    #
    # Every harness producer passes a kind, which is why every gate stayed green over a
    # door only she could not open — AGENTS.md §0, tested through the callers that work.
    #
    # The gate now follows the AUTHOR. Her words are hers whatever they are filed as, so
    # a plain self-fact keeps its plain class (render_self_model still leads with who she
    # IS) and only a named kind makes it narrative. His lane is untouched.
    _self_authored = (_AUTHOR.get() == "self")
    if _self_authored:
        # NOT normalized: normalize_fact() strips an imperative wrapper ("remember ...")
        # off a fact HE states; her journal line is not an instruction, and stripping it
        # also hid a tool receipt from the machine-text check (G-REAL-HER §1).
        fact = " ".join(_raw.split())
        if not _self_narr:
            # a plain self-fact is hers, but it is not NARRATIVE: no producer named a
            # kind, so it must not arrive wearing one (see the note above).
            mem_class, kind = "", ""
        ok, why = lc.is_narratable(fact)
        if not ok:
            return Admission(f"not stored — {why}", fact, mem_class, kind, _self_narr)
    else:
        mem_class, kind = "", ""
        ok, why = lc.is_memorable(fact)
        if not ok:
            return Admission(f"not stored — {why}", fact, mem_class, kind, _self_narr)
    # ── THE IDENTITY FIREWALL (2026-07-12) ──────────────────────────────────────
    # She answered "what is your name?" with "My name is Kairos." — correctly — and then
    # stored that sentence HERE, in the USER store. It was stamped speaker=user, classed
    # identity, and superseded all three rows that said the user is Sam. The store came
    # out of it asserting that SAM IS CALLED KAIROS.
    #
    # Which door she writes to is the ONLY signal for whose fact it is, and she picked the
    # wrong one. The prompt already tells her; a prompt is advice, and the price of one
    # slip is the user's identity. So the door refuses it, and names the right door.
    if _AUTHOR.get() != lc.SPEAKER_SELF:
        ok, why = lc.admit_to_user_store(fact, _self_names())
        if not ok:
            return Admission(f"not stored — {why}", fact, mem_class, kind, _self_narr)
    # ADMITTED. The writer takes it from here: the fact as it will be stored, the class and
    # kind as they survived this chain, and whether her narrative rule applies.
    return Admission(None, fact, mem_class, kind, _self_narr)


_GENDER_WORDS = {
    "female": {"female", "woman", "girl", "she", "her"},
    "male": {"male", "man", "boy", "he", "him"},
}


def _self_names() -> set:
    """EVERY VALUE THAT CONSTITUTES HER — not just her name.

    The first firewall guarded the name, because the name is what had eaten his. Then she
    filed "I am a woman" as HIS identity and supersede retired "I am male": the store came
    out asserting that Sam is a woman. Same mechanism, one attribute to the left. I had
    fixed the instance and called it the class.

    So this returns her name AND her gender words, read live from the persona — a rename or
    a re-gender moves the firewall with her. The literals are the floor, not the truth."""
    vals = {"kairos", "kairos"}
    try:
        from harness.personality.persona_file import parse_persona
        from harness.personality.persona_file import persona_path
        path = persona_path()
        with open(path, encoding="utf-8") as f:
            _, state = parse_persona(f.read())
        for k in ("name", "self_name"):
            v = (state or {}).get(k)
            if isinstance(v, str) and v.strip():
                vals.add(v.strip().lower())
        g = (state or {}).get("gender")
        if isinstance(g, str) and g.strip():
            vals |= _GENDER_WORDS.get(g.strip().lower(), {g.strip().lower()})
    except Exception as _swx:
        _sw(_log, "_self_names", _swx, lane="skills")
    return vals
