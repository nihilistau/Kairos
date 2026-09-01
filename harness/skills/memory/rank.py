"""rank.py — the recall seam: which rows a question is allowed to see, and in what order.

`search_memories_ranked_rows()` is THE seam. Every reader that ranks goes through it and the
tools are projections of it — *"if you need a new view, project; do not write a second
walker"* (docs/MEMORY-AND-RECALL.md). That sentence exists because the second walker was
already written once: `search_memories_ranked()` did not filter retired rows while
`search_memories_ranked_rows()`, **the next function in the file**, did — so the search tool,
live in two toolsets, served tombstones. AGENTS.md §0's second row.

That is the whole argument for this module. The two functions are adjacent again, but now
they are adjacent inside a boundary a gate can name: `_src.pkg("harness","skills","memory")`
counts across the package, and G-MEMORY-PACKAGE §3 refuses a second door into it.

WHAT IS IN HERE, in the order the pipeline uses it:

  * **the question's owner** — `_query_target`, `_unframe`, `_ASKS_SELF/_ASKS_USER`,
    `_ASK_FRAME`, `_REL_NOUN`. Read from HIS sentence, never from her paraphrase; the trace
    that forced it is in the comment above `_ASKS_SELF`.
  * **the evidence floor** — `_no_rare_word`, `_idf_table`, `_evidence`. A shared token is
    worth -log2 p(token), and the floor is the MEDIAN IDF over her own store rather than a
    constant somebody chose.
  * **the selection** — `_select`, `_target_and_rank`, `_surprisal_of`, `_person_model`,
    `_alive`, `_row_key`, and the three caches.

`_select` is rebound by `harness_tests/g_recall_evidence.py`, so it is called as
`_rank._select` by the doors: a by-name binding would snapshot and the mutant would grade a
subset. See `store.py`'s header for the version of that trap which produced a silent green.

Extracted from `memory.py` on 2026-09-02, byte-identical.
"""
from __future__ import annotations

import logging
import math
import os
import re
import time

from harness.loud import swallowed as _sw
from harness.skills.memory import store as _store
from harness.skills.memory.authorship import _QUESTION
from harness.skills.memory.words import _text, _depluralise, _toks, _overlap

_log = logging.getLogger("harness.memory")     # the same object; see store.py's note


def search_memories_ranked_rows(query: str, k: int = 5, min_overlap: float = 0.25,
                                include_retired: bool = False):
    """Like search_memories_ranked but returns (score, ROW) so callers can read
    per-entry policy fields (mem_class etc.). The policy dispatch rides this.

    ── THE SUPERSEDE MACHINERY WAS BYPASSED ON THE MAIN TURN PATH (2026-07-14) ────────────
    This function iterated _store._load() — EVERY row, tombstones included — and left the lifecycle
    filter to whoever called it. Two callers. ONE of them remembered:

        memory.recall()        [e for e in ... if not e.get("lifecycle")]     <- filtered
        spine.recall_decider() hits = search_memories_ranked_rows(...)        <- DID NOT

    recall_decider is the AUTOMATIC recall — the context injection that runs on EVERY TURN,
    without her choosing it. PROVEN, on the real code path:

        THE STORE:                     TOMBSTONE 'My GPU is an RTX 2060'
                                       LIVE      'My GPU is an RTX 3090'

        the recall() TOOL:             1. Sam told me: My GPU is an RTX 3090     correct
        INJECTED EVERY TURN:           -> My GPU is an RTX 2060      THE DEAD ONE, AND FIRST
                                       -> My GPU is an RTX 3090

    He tells her he upgraded his card. Supersede fires perfectly, writes the tombstone — and then
    every turn for the rest of her life the automatic recall hands her the corpse ANYWAY, ranked
    ABOVE the truth, and she has no way to know one of them is dead.

    So the entire lifecycle system — supersede, the identity firewall, all of MEM-OKF v2, every
    correction he has ever made — was live ONLY when she happened to call the recall() TOOL. On
    the path that actually feeds her context, it never ran at all.

    THE BUG IS NOT THE MISSING FILTER. It is that an invariant every reader must hold was written
    in a CALLER instead of in the SEAM they share — the same shape as on_user_turn armed on one
    path of two, and the shear guard testing a proxy. A rule enforced in one of two paths is
    enforced in NEITHER, because the unguarded path is the one that runs.

    It lives here now. A caller can no longer forget it; it must ASK for the dead
    (include_retired=True), which is a thing only the audit lane has any business doing.

    ── AND TESTIMONY OUTRANKS INFERENCE, IN THE SAME SEAM ─────────────────────────────────
    An inference is not a memory of something that happened; it is a conclusion she drew. She is
    allowed to be wrong about him. SHE IS NOT ALLOWED TO SAY IT OVER HIM. If she has concluded
    something about a topic HIS OWN WORDS already cover, his words go and her guess stays home:

        observed  'Sam is terrified of open water'   <- he told her
        inferred  'Sam is comfortable in open water' <- she decided otherwise

    Surfacing both is not scrupulous, it is deaf: she would say "you told me you're terrified" and
    "I've come to think you're comfortable" in one breath. This is a SPEECH rule, not a storage
    rule — nothing is destroyed, the inference stays on disk and stays auditable. It simply does
    not get to take the floor on a subject he has already spoken to.

    It is deliberately a TOPIC test and not a contradiction test, because I cannot detect semantic
    contradiction with string operations and a verdict I cannot defend is a lie with a timestamp.
    A topic test fails SAFE in the only direction that matters: at worst she is quieter than she
    needed to be. It can never delete a fact and never assert something false.
    """
    from harness.skills import lifecycle as lc
    clause = re.split(r"[.:;!]", query)[-1].strip() or query
    eps = _store._load()

    # ── SEM S1 (docs/SEMANTICS.md): the DUAL admission gate, in THE seam ──────────────────
    # A paraphrase shares no content tokens with the fact it asks about, so the lexical gate
    # alone recalls it at 0.06 on the frozen corpus (fixtures/sem/baseline-receipt.json). A
    # row may now ALSO be admitted by semantic match: cosine >= SP_SEM_TAU against its
    # semindex row, SAME embedding space only (cross-space cosine is noise). This is
    # admission by MATCH, not by salience — G-SALIENCE's law is untouched, salience still
    # only breaks ties among the admitted. Off (SP_SEM_RANK unset) is byte-identical to the
    # lexical path: G-SEM-CONSERVE holds the golden. Any failure inside SEM degrades to
    # lexical silently — a ranker may never cost her a sentence. It lives HERE because the
    # three comments below this one are all the same story: a guard in a caller guards
    # nothing. Gates: G-SEM-RANK, G-SEM-CLAIM.
    sem_idx, qvec, qmodel, sem_tau, smean = {}, None, None, 2.0, None
    if os.environ.get("SP_SEM_RANK", "0") == "1":
        from harness.skills import semindex as sx
        try:
            sem_tau = float(os.environ.get("SP_SEM_TAU", "0.60"))
            sem_idx = sx.load_cached()
            if sem_idx:
                qvec, qmodel = sx.query_embed(query)
                # TAU IS PER SPACE (2026-08-23). SP_SEM_TAU=0.60 was set for l5's inflated
                # raw cosines; the aux space's paraphrase median is 0.293 and its measured
                # operating point is 0.20, so the shared threshold would admit nothing at
                # all and the whole gate would look "safe" by being dead.
                if qmodel == sx.MODEL_AUX:
                    sem_tau = sx.aux_tau()
                if qvec is not None and qmodel == sx.MODEL_L5:
                    # ONCE, not per candidate row: space_mean() stats the index file
                    # and takes a lock on every call, and the loop below ran it for
                    # every row in the store.
                    smean = sx.space_mean()
        except Exception as _swx:
            _sw(_log, "search_memories_ranked_rows", _swx, lane="skills")
            sem_idx, qvec = {}, None      # degrade to lexical, never block

    scored = []
    for e in eps:
        if not include_retired and e.get("lifecycle"):
            continue                      # superseded is superseded — on EVERY path, not just the polite one
        t = _text(e)
        ov = _overlap(query, t)
        if clause != query:
            ov = max(ov, _overlap(clause, t))
        cos = 0.0
        if qvec is not None:
            srow = sem_idx.get((sx.addr_of(e.get("text") or t), e.get("ts") or ""))
            if srow is not None and srow.get("model") == qmodel:
                # l5-space is anisotropic (measured: every raw pair >= 0.70) — center on
                # the index population so the absolute threshold means something. Raw
                # cosine for hash-space (sparse, no common-direction pathology).
                if qmodel == sx.MODEL_L5:
                    cos = sx.centered_cosine(qvec, srow.get("vec") or [], smean)
                else:
                    cos = sx.cosine(qvec, srow.get("vec") or [])
        # THE RATIO SAYS HOW MUCH OF THE QUESTION IS COVERED; THE FLOOR SAYS WHETHER THAT
        # COVERAGE MEANS ANYTHING. A one-token query matches at 1.00 on any row carrying
        # that token, which is how "the lights are on" reached three of her rows about
        # luminescence, a stopped world and the edge of sleep. See _evidence.
        # A SEMANTIC HIT IS ADMITTED ON ITS OWN TERMS: cosine is not a bag of words and a
        # lexical floor has no business ruling on it.
        if cos >= sem_tau:
            scored.append((max(ov, cos), e))
        elif ov >= min_overlap and _evidence(query, t) >= _idf_table()[1]:
            scored.append((ov, e))
    matched = {_row_key(e) for _s, e in scored}     # these are the ones his WORDS reached

    # ── HE ASKED SOMEBODY, AND NOBODY'S WORDS MATCHED ────────────────────────────────
    # The evidence floor is right to reject "how do you feel about us?" — feel, about and
    # us are in a third of the store and match nothing in particular. But the question is
    # plainly addressed to her, and answering a question aimed at a person with silence
    # because it contained no rare noun is a worse failure than the one the floor fixes.
    #
    # SO A SECOND ROUTE IN, AND IT CLAIMS SOMETHING DIFFERENT. Route one says "this row is
    # about what you asked". Route two says "you asked HER, and this is what is most alive
    # for her" — salience, which is already mentions x recency and already what the rest of
    # this file means by alive. It only opens when the question names a lane, so the
    # conversational turn that names nobody still gets silence rather than filler.
    #
    # THEY ARE ADMITTED HERE, before testimony_wins / _target_and_rank / the sem law, and
    # not appended to the winners afterwards. A row that skips the filter chain is the bug
    # this function's own docstring is three paragraphs about; a second entrance must open
    # into the same corridor. `matched` above is how the words keep their precedence —
    # `_select` fills its slots from route one first, so aliveness can never outrank an
    # answer to the actual question.
    # `len(scored) < k` IS AN OPTIMISATION, NOT A RULE, and it is labelled so nobody later
    # mistakes it for one: `_select` puts the matched rows first and truncates to k, so
    # topping up a full result set is inert — verified by mutation, which is why G-RECALL-
    # EVIDENCE has no leg for it. What it buys is not scanning the lane on every query his
    # words already answered, and the per-turn note runs this on every turn.
    _target = _query_target(query)
    if _target and not include_retired and len(scored) < k and _no_rare_word(query):
        band = min_overlap * 0.9        # strictly under any real match
        alive = [e for e in eps
                 if not e.get("lifecycle")
                 and (e.get("speaker") or lc.SPEAKER_USER) == _target
                 and _row_key(e) not in matched]
        # RECENCY, NOT SALIENCE, and the difference is the whole point. Salience is
        # mentions x recency, which is right for "what do you know about X" and wrong here:
        # her most salient rows are `My mood has turned playful/warm/naughty/tender`, eleven
        # variations of one line the mood machinery writes on every change. Asked what she
        # has been up to, she would have answered with her own housekeeping. What an open
        # question about a person wants is the LATEST — measured, her last night's thinking
        # and his last night's conclusions, which is what the question was for.
        alive.sort(key=lambda e: (e.get("ts") or ""), reverse=True)
        # ── AND A SEAT FOR THE FAR PAST (2026-08-28, his ask: "not only recent memories
        # valued so much over old ones"). MEASURED before this: on neutral turns every
        # pick was under 9 days old (median 4.0, 0 of 12 over 30 days), because this pool
        # was the newest 3k rows full stop. Recency stays the ORDER — an open question
        # about a person still wants what is latest — but the tail of the pool now holds
        # the most SALIENT rows older than 30 days, so `recall.explore`'s wildcard (and
        # an empty slot) can hand back an old thread. Salience picks the elders because
        # for the far past, what mattered repeatedly beats what happened last: the exact
        # opposite of the recent end, and both are right for their span.
        pool = alive[:2 * k]
        _cut = "%sT00:00:00Z" % time.strftime("%Y-%m-%d", time.gmtime(time.time() - 30 * 86400))
        elders = [e for e in alive[2 * k:] if (e.get("ts") or "") < _cut]
        elders.sort(key=lambda e: -_alive(e))
        pool += elders[:k]
        n = len(pool) + 1.0
        for i, e in enumerate(pool):
            scored.append((band * (1.0 - i / n), e))

    scored.sort(key=lambda x: -x[0])
    if not include_retired:
        scored = lc.testimony_wins(scored)
        # ── AND THE OWNERSHIP SCOPING LIVES HERE NOW, FOR THE SAME REASON (2026-07-14) ────
        #
        # _target_and_rank() — the pronoun scoping, the relationship penalty, the identity
        # boost, the salience prior — was called by recall(). THE TOOL. Not by the seam.
        #
        # So spine.recall_decider(), the AUTOMATIC per-turn injection, never ran any of it, and
        # the live transcript is what that costs:
        #
        #     you: "what is your NAME?"
        #     recall: ["The user said: My cat's NAME is Tuffy.", "The user's NAME is Sam",
        #              "My NAME is Kairos."]
        #     her: "Your cat's named Tuffy? I was wondering why you kept calling him that."
        #
        # She answered a question about HER NAME with HIS CAT'S NAME. The query token was {name};
        # the cat row contains "name"; it scored 1.00. _target_and_rank would have caught it
        # THREE WAYS — "your" scopes to speaker=self, the cat is a relationship noun the question
        # never mentioned (-0.40), and the identity row gets +0.30 — and its own comment says so,
        # in as many words. It just was not on the path that runs.
        #
        # Third time in this one file: the lifecycle filter, the twin ranker, and now this. The
        # polite path had every guard; the automatic one had none of them.
        scored = _target_and_rank(query, scored)
        # ── SEM PHASE B2 CUTOVER (docs/INVARIANT-MEMORY.md): the table RULES ─────────────
        # Behind SP_SEM_VERDICT (mapped in serve.py). Silence-direction only: the law can
        # drop a row it rules inadmissible (this is what closes the ladders leak once a
        # slot link exists); it cannot admit, cannot reorder, keeps unmapped cells (loud,
        # counted — unlegislated is not forbidden). Old conditionals stay: authority
        # moved, code did not get deleted. Gate: G-SEM-VERDICT.
        if os.environ.get("SP_SEM_VERDICT", "0") == "1":
            from harness.skills import verdict as _law2
            scored = _law2.enforce(query, scored, eps)
        # ── SEM PHASE B SHADOW (docs/INVARIANT-MEMORY.md): the law watches the seam ──────
        # Read-only, behind SP_SEM_LAW (mapped in serve.py). Checks the one direction that
        # is checkable and load-bearing: EVERYTHING ADMITTED IS TABLE-ADMISSIBLE. Counters
        # + optional witnesses (SP_SEM_LAW_LOG); never raises, never reorders, never costs
        # a sentence. Cutover to ruling-as-filter is Phase B2, gated on a zero-divergence
        # receipt. Gate: G-SEM-LAW.
        if os.environ.get("SP_SEM_LAW", "0") == "1":
            from harness.skills import verdict as _law
            _law.shadow(query, [e for _s, e in scored[:k]], eps)
        # THE TRUNCATION IS A DECISION, so it is made in one named place rather than by a
        # slice: dedupe first, then reserve a slot for the lane the question did not name.
        # See _select. The audit lane (include_retired) is untouched — it wants the raw
        # ranking and nothing chosen for it.
        return _select(query, scored, k, _query_target(query), matched)
    return scored[:k]


def search_memories_ranked(query: str, k: int = 5, min_overlap: float = 0.25,
                           include_retired: bool = False):
    """Internal: [(score, TEXT)] of the top-k live facts. The search tool rides this.

    ── I FIXED ONE OF TWO TWINS, AND THE OTHER ONE WAS RIGHT HERE (2026-07-14) ─────────────
    Hours after committing the fix for search_memories_ranked_rows — with a commit message
    explaining at length that AN INVARIANT ENFORCED IN ONE OF TWO PATHS IS ENFORCED IN NEITHER —
    the sweep for OTHER instances of that class found this function, DIRECTLY BELOW IT, doing the
    identical thing: `eps = _store._load()` over every row, tombstones included.

    And it is not dead code. It is the `search_memories` TOOL, and that tool is LIVE:

        MEMORY_TOOLS_EXTRA = [provenance, search_memories, memory_stats]
        spine.py:287   core = MEMORY_TOOLS + MEMORY_TOOLS_EXTRA[:2]     <- both of them
        agent.py:230   tools = MEMORY_TOOLS + MEMORY_TOOLS_EXTRA        <- all three

    So while I was congratulating myself for moving the lifecycle filter into "the seam", there
    were TWO seams. I had found the class, named the class, written the class on the wall — and
    then fixed the instance in front of me and stopped looking. THAT is the actual bug, and it is
    mine, not the code's.

    THE FIX IS NOT A THIRD COPY OF THE FILTER. A rule you have to remember is a rule you will
    forget; there is now exactly ONE function that reads the store for recall, and this one is a
    projection of it. The twin cannot drift because the twin no longer exists.
    """
    return [(s, _text(e)) for s, e in
            search_memories_ranked_rows(query, k=k, min_overlap=min_overlap,
                                        include_retired=include_retired)]


# ── WHO IS THE QUESTION ABOUT? (2026-07-12) ───────────────────────────────────
# The trace that forced this. Asked "what is my name?", recall returned:
#
#     1. Sam told me: My cat's name is Tuffy.
#     2. Sam told me: The user's name is Sam
#     3. About myself: My name is Kairos.
#
# ...and she answered "My name is Kairos." Of course she did — of the three, row 3 is the
# one whose SURFACE FORM matches the question. Pure token overlap cannot tell "my name" in
# HIS mouth from "my name" in HERS; it just sees the words line up.
#
# But the store already knows whose each fact is — `speaker` is stamped on every row. The
# missing step is reading the PRONOUN IN THE QUESTION: when he says "my", he is asking
# about HIM; when he says "your", he is asking about HER. Scope the search to that person
# and the ambiguity is gone at the source, rather than being left for the model to resolve
# by guessing — which is precisely the guess that keeps coming out wrong.
#
# The relationship penalty is the second half: "My cat's name is Tuffy" tied with "The
# user's name is Sam" at 1.00, because the query token was {name} and both rows have it.
# A row that drags in an entity the question never mentioned (a cat) is answering a
# question that was not asked.
_ASKS_SELF = re.compile(r"\b(your|yours|you|you're|youre)\b", re.I)
_ASKS_USER = re.compile(r"\b(my|mine|me|i|i'm|im)\b", re.I)

# ── "DO YOU" IS NOT A QUESTION ABOUT YOU (2026-07-14) ─────────────────────────────────
# Caught replaying the live transcript after the first fix. He asks:
#
#     "do YOU remember my cat's name?"
#
# _ASKS_SELF matches the bare word `you`, and it is checked first — so the question scoped to
# SPEAKER_SELF and she answered HIS CAT'S NAME with "My name is Kairos."
#
# The `you` in "do you remember ..." is the ADDRESSEE. It is who he is TALKING TO, not who he is
# ASKING ABOUT. And it is in front of practically every memory question a person actually asks:
# "do you remember", "do you know", "can you tell me", "do you recall". So the ownership resolver
# was reading the wrong pronoun on nearly every real question, and the only reason it ever worked
# is that people also say "what is my name?" with no framing at all.
#
# Same shape as the _STOP fix one function up: THE FRAMING OF A QUESTION IS NOT THE QUESTION.
# There it made the verb into content; here it made the addressee into the subject. Strip the
# frame, THEN read the pronouns — after which a bare `you` is meaningful again ("what sex are
# YOU" -> hers) because the only `you` left is the one he actually asked about.
_ASK_FRAME = re.compile(
    r"^\s*(?:"
    r"(?:hey|hi|ok|okay|so|and|well|but)\b[\s,]*"
    r"|(?:do|did|can|could|would|will|does)\s+you\b"
    r"|(?:do|did)\s+you\s+(?:still\s+)?(?:remember|recall|know|have)\b"
    r"|(?:can|could|would)\s+you\s+(?:please\s+)?(?:tell|remind|say)\s+me\b"
    r"|(?:tell|remind)\s+me\b"
    r"|(?:what|which)\s+do\s+you\s+(?:remember|know)\b"
    r"|please\b"
    r")[\s,:]*", re.I)


def _unframe(q: str) -> str:
    """Peel the conversational wrapper off a question until only the question is left."""
    t = (q or "").strip()
    prev = None
    while t != prev:
        prev = t
        t = _ASK_FRAME.sub("", t, count=1).strip()
    return t or (q or "").strip()
# The trailing `s?` is load-bearing and I got it wrong once: I depluralised the RESULT of findall
# instead of what it SEARCHES, so `\bcat\b` still did not match "cats", q_rel stayed empty, and the
# cat row kept taking the -0.40 "you never asked about a pet" penalty on a question that was
# literally about his cat. Match the plural at the source; the group still yields the singular.
_REL_NOUN = re.compile(
    r"\b(wife|husband|partner|girlfriend|boyfriend|brother|sister|mother|father|mum|mom|"
    r"dad|son|daughter|friend|cat|dog|pet)s?\b", re.I)




def _query_target(query: str):
    """Whose fact is this question asking for? Resolved from HIS sentence, not from her
    paraphrase of it — see _QUESTION. 'your' -> hers. 'my' -> his.

    UNFRAMED FIRST: "do YOU remember MY cat's name" has both pronouns in it, and the `you` is the
    addressee. Peel the frame and only the pronoun he is actually asking about survives."""
    from harness.skills import lifecycle as lc
    src = _unframe(_QUESTION.get() or query)   # his words if we have them; hers only as a fallback
    if _ASKS_SELF.search(src):
        return lc.SPEAKER_SELF
    if _ASKS_USER.search(src):
        return lc.SPEAKER_USER
    return None


# ── WHAT GETS SURFACED, AFTER THE MATCH HAS RANKED (2026-08-28) ──────────────────────
# MEASURED on his live store, before any of this existed. Recall was correct where the
# question named a person and skewed where it did not:
#
#     questions about HIM  ("what gpu do I have?")     14 rows, 0% hers   correct
#     questions about HER  ("how are you?")             9 rows, 100% hers  correct
#     NEUTRAL, conversational                          15 rows, 73% hers  <- the defect
#
# And the mechanism was in `_overlap`, which is |q&t| / |q| — divided by the QUERY only, so
# a longer row can only ever score higher. His facts have a median length of 53 characters
# and her narrative 140; on a neutral turn the rows it surfaced had a median of 340. It was
# picking her longest prose because it was long.
#
# THE FIX IS NOT A BETTER SIMILARITY NUMBER. Dice (2|q&t|/(|q|+|t|)) was measured and
# over-corrects to 33% hers with a median row length of 45 — the same imbalance mirrored,
# and choosing an exponent between the two is inventing a constant to sit under a
# measurement, which this tree has a rule about. So MATCH stays what it is, and the two
# things that were actually wrong are fixed as what they are: a MISSING PRIOR and a
# MISSING SELECTION RULE.
# ── ONE SHARED COMMON WORD IS NOT A TOPIC (2026-08-28) ───────────────────────────────
# `_overlap` is |q&t| / |q|, so a query with ONE content token matches at 1.00 on any row
# containing that token. Measured on his store, this is what the per-turn note was doing:
#
#     "the lights are on"        -> shared={light}      three of her rows about
#                                                       luminescence, a stopped world,
#                                                       and the edge of sleep
#     "it is beautiful isn't it" -> shared={beautiful}
#     "long day"                 -> shared={day}
#
# Nothing there is about his lamps. The ratio was 1.00 every time because the query had one
# word to divide by. A weighting cannot fix a one-token intersection; what is missing is a
# floor on HOW MUCH EVIDENCE a match carries, and information theory already names it: a
# shared token is worth -log2 p(token), so a word in fifty rows is worth little and a word
# in two is worth a lot.
#
# THE FLOOR IS DERIVED, NOT CHOSEN. It is the median IDF over token OCCURRENCES in his own
# store — "more evidence than an average word carries". On 684 live rows that is 3.89,
# which is a word appearing in about thirteen of them, and it lands where it should:
#
#     rejected: light (50 rows)  beautiful (24)  day (17)  nightie (16)
#     admitted: morning (12)  sine (10)  long (9)  good (8)  tuffy (6)  gpu (2)  radar (0)
#
# It moves with the store rather than sitting under one measurement of it, and the failure
# direction is silence — which this file already treats as an answer.
def _no_rare_word(query: str) -> bool:
    """True when nothing he said is rarer than an average word — i.e. there is no lexical
    question here to answer, only a person being addressed.

    THIS IS WHAT KEEPS THE LANE TOP-UP FROM BECOMING FILLER. "tell me about my radar setup"
    names a lane too, and when the store holds nothing about radar the honest answer is
    that it holds nothing about radar — not his name and his cat, which is what aliveness
    alone offered. He used a rare word; that word IS the question; silence is the answer.
    "how do you feel about us?" is made entirely of words in a third of the store, so there
    is no such word to be silent about, and what is alive in her lane is the best answer
    available. Same table and same floor as the admission test, read the other way round.
    """
    idf, floor = _idf_table()
    if not idf:
        return False                      # no table: never invent a reason to speak
    ts = _toks(query)
    if not ts:
        return False
    unknown = math.log(len(idf) + 1)      # a word the store has never seen is rare, and
    return max(idf.get(t, unknown) for t in ts) < floor    # that is a question too


def _row_key(e: dict) -> tuple:
    """Identity of a row ACROSS the filter chain. Not id(), which the first step that
    rebuilds a dict would silently break, and not text alone, which two tellings share."""
    return (e.get("ts") or "", (e.get("text") or "")[:120])


def _alive(e: dict) -> float:
    """How live this row is, independent of the question. Mentions x recency, which
    `lifecycle.salience` already owns — a second decay curve here would be the two-copies
    bug again, and this file has paid for that three times."""
    try:
        from harness.skills import lifecycle as lc
        return float(lc.salience(e))
    except Exception as exc:
        _sw(_log, "_alive", exc, lane="recall")
        return 0.0


_IDF_CACHE: list = []


def _idf_table():
    """({token: idf}, floor). Rebuilt when the row count changes. Never raises."""
    try:
        rows = [r for r in _store._load() if not r.get("lifecycle")]
        if _IDF_CACHE and _IDF_CACHE[0] == len(rows):
            return _IDF_CACHE[1], _IDF_CACHE[2]
        import collections
        import statistics
        n = max(1, len(rows))
        df = collections.Counter()
        per_row = []
        for r in rows:
            ts = _toks(_text(r))
            per_row.append(ts)
            for t in ts:
                df[t] += 1
        idf = {t: math.log((n + 1) / (c + 1)) for t, c in df.items()}
        occ = [idf[t] for ts in per_row for t in ts]
        floor = statistics.median(occ) if occ else 0.0
        _IDF_CACHE[:] = [len(rows), idf, floor]
        return idf, floor
    except Exception as exc:
        # AN EMPTY TABLE IS ALSO WHAT AN EMPTY STORE LOOKS LIKE, so this handler could hide
        # a broken floor behind "he has no memories yet" forever — and it did, for the
        # length of one measurement: `math` was unimported, every call raised NameError,
        # the floor read 0.0 and admitted everything. See harness/loud.py.
        _sw(_log, "_idf_table", exc, lane="recall")
        return {}, 0.0


def _evidence(query: str, target: str) -> float:
    """How much information the shared tokens carry, in bits. 0 when nothing is shared."""
    idf, _floor = _idf_table()
    if not idf:
        return 1e9                    # no table yet: admit as before, never block on this
    shared = _toks(query) & _toks(target)
    unknown = math.log(len(idf) + 1)  # a token the store has never seen is maximally rare
    return sum(idf.get(t, unknown) for t in shared)


_SURP_CACHE: dict = {}


def _surprisal_of(row: dict) -> float:
    """Information content of one of HIS facts, 0..1. Her lane scores 0, on purpose.

    I(x) = -log2 p(x | model of him), which `person.PersonModel` already computes and which
    nothing in recall was reading. On his store it separates substance from pleasantry
    exactly as it should:
    
        8.00  My GPU is an RTX 2060
        4.12  Sam is a deeply devoted partner who finds comfort in ...
        0.01  a warm two-word pleasantry, of the kind said most days
        0.01  a second one, different words, same shape

    (The two low rows are real rows and those are their real scores; they are DESCRIBED
    rather than quoted because this file ships in the export, and what ships should be a
    neutral template rather than a transcript of the two of them. Same rule as the
    fixtures.)
    
    IT IS A RANK AND NOT A VERDICT, which is the use this repo has already sanctioned for it
    in kairos/scheduler.py: "the metric measures lexical novelty, which is a perfectly good
    RANK and an unsound VERDICT". A one-off odd phrase scores 8.00 too. Nothing is admitted
    or refused by it — it moves things within an already-admitted set.
    
    HER LANE SCORES ZERO because there is no model of her to be surprised by, and the one
    time this tree tried to score her prose with machinery built for attributive facts the
    receipt was twelve proposals and twelve wrong (docs/OFF-BY-DEFAULT.md #1). Zero is the
    honest number, not a penalty: it says we cannot measure this, so it does not lift.
    """
    key = (row.get("name") or "", row.get("ts") or "")
    if key in _SURP_CACHE:
        return _SURP_CACHE[key]
    val = 0.0
    try:
        from harness.skills import lifecycle as lc
        if (row.get("speaker") or lc.SPEAKER_USER) == lc.SPEAKER_USER:
            pm = _person_model()
            if pm is not None:
                val = min(1.0, max(0.0, pm.surprisal(_text(row),
                                                     row.get("mem_class") or "") / 8.0))
    except Exception as _swx:
        _sw(_log, "_surprisal_of", _swx, lane="skills")
        val = 0.0
    _SURP_CACHE[key] = val
    return val


_PM_CACHE: list = []


def _person_model():
    """The model of him, rebuilt when the store changes. NEVER raises."""
    try:
        n = len(_store._load())
        if _PM_CACHE and _PM_CACHE[0] == n:
            return _PM_CACHE[1]
        from harness.model.person import PersonModel
        pm = PersonModel.from_registry()
        _PM_CACHE[:] = [n, pm]
        _SURP_CACHE.clear()
        return pm
    except Exception as _swx:
        _sw(_log, "_person_model", _swx, lane="skills")
        return None


def _select(query: str, scored: list, k: int, target, matched=None) -> list:
    """Choose WHICH of the ranked rows he actually sees. Deduped, balanced, mostly stable.

    Three rules, and none of them is a tuned number:

    1. NO TWO PICKS THAT SAY THE SAME THING. Measured on his store: one question returned
       the silver nightie three times in three slots. `reprise` already owns "are these two
       the same telling" for the WRITING path, so reading uses the same rule rather than a
       second one — a near-duplicate costs a slot that had something else to say in it.

    2. BOTH LANES GET A VOICE WHEN THE QUESTION NAMES NEITHER. If he asks about himself or
       about her, `_target_and_rank` has already narrowed and this does nothing — that
       behaviour measured correct in both directions and is left alone. It is the
       conversational turn, where the question names no one, that was 73% hers. There, one
       slot is reserved for the other lane IF that lane has an admitted candidate. A
       reservation, not a quota: if only one lane matched, it keeps every slot.

    3. THE ORDER IS OTHERWISE THE RANKING'S. No shuffling by default.

    `recall.explore` (default 0) adds the bit of variety he asked for: with that
    probability the LAST slot is drawn from the admitted-but-unpicked remainder instead of
    taken in order. It is off by default so every gate is deterministic, and it can only
    ever swap the weakest pick — exploration must not cost the best answer.
    """
    from harness.skills import lifecycle as lc
    if k <= 0 or not scored:
        return scored[:k]

    # ── 0. HIS WORDS FIRST, ALWAYS ───────────────────────────────────────────────────
    # `matched` is the set of rows admitted because they answer what he asked, as opposed
    # to the lane top-up admitted because it is alive. Both went through the same filters,
    # and the ranking mixes them — salience and surprisal are added to every row alike, so
    # a vivid unrelated row can float over a plain answer. Order is restored here rather
    # than by shrinking the bonuses, because the bonuses are doing the right thing for the
    # rows that DID match and only the wrong thing across this boundary.
    # ...AND THE TOP-UP IS ORDERED EVEN WHEN NOTHING MATCHED, which is the case route two
    # exists for. The first cut guarded this whole block on a non-empty `matched`, so on a
    # question his words reached nothing — "what have you been up to?" — the reordering was
    # skipped entirely and the ranker's salience order stood: her three mood marks, which
    # is precisely the answer this was written to prevent. An empty set is a real answer
    # here, not a reason to do nothing.
    if matched is not None:
        strong = [x for x in scored if _row_key(x[1]) in matched]
        # AND ROUTE TWO'S ORDER IS RECENCY, RESTATED HERE rather than left to survive the
        # ranker. Its rows enter under a score band below any real match, but
        # `_target_and_rank` then adds salience and surprisal to every row alike — bonuses
        # whose range is several times the width of that band, so the mood-mark family
        # would sort itself straight back to the top. The band keeps route two BELOW route
        # one, which the bonuses cannot undo; the order WITHIN it is set here.
        rest = sorted((x for x in scored if _row_key(x[1]) not in matched),
                      key=lambda x: (x[1].get("ts") or ""), reverse=True)
        scored = strong + rest

    # ── 1. dedupe, through reprise's own rule ────────────────────────────────────────
    try:
        from harness.skills import reprise as _rp
        reg = _rp.register_tokens([{"text": _text(e)} for _s, e in scored])
    except Exception as _swx:
        _sw(_log, "_select", _swx, lane="skills")
        _rp, reg = None, set()
    picked, seen_prefix, rest = [], set(), []
    for s, e in scored:
        pref = ""
        if _rp is not None:
            try:
                pref = " ".join(_rp.content_prefix(_text(e), reg, 5))
            except Exception as _swx:
                _sw(_log, "_select", _swx, lane="skills")
                pref = ""
        if pref and pref in seen_prefix:
            continue                      # she already says this in a slot above
        if pref:
            seen_prefix.add(pref)
        (picked if len(picked) < k else rest).append((s, e))

    # ── 2. reserve a slot for the other lane, only when the question named nobody ────
    if target is None and len(picked) >= 2:
        lanes = {(e.get("speaker") or lc.SPEAKER_USER) for _s, e in picked}
        if len(lanes) == 1:
            here = next(iter(lanes))
            other = next(((s, e) for s, e in rest
                          if (e.get("speaker") or lc.SPEAKER_USER) != here), None)
            if other is not None:
                picked[-1] = other        # the weakest pick yields, never the best one

    # ── 3. a little variety, off by default ─────────────────────────────────────────
    try:
        from harness.tuning import registry as _tune
        p = float(_tune.get("recall.explore", 0.0) or 0.0)
    except Exception as _swx:
        _sw(_log, "_select", _swx, lane="skills")
        p = 0.0
    if p > 0.0 and rest and len(picked) >= 2:
        # VARIETY, NOT NONDETERMINISM, and the difference is not pedantry. `random.random()`
        # here means the recall seam answers the same question differently on two calls in
        # one turn, and G-SEM-CONSERVE's determinism leg exists because a ranker with hidden
        # state cannot be audited — it passed only because that corpus never populated
        # `rest`. The roll is drawn instead from the SITUATION: this question, over these
        # candidates. Same question and same store, same third memory; and since his store
        # takes new rows through most turns, the wildcard still moves — which is the variety
        # he asked for, without a coin flip inside a path everything else is graded against.
        #
        # hashlib, not hash(): str hashing is salted per process, so hash() would be
        # reproducible within a run and different in the next one — the worst of both.
        import hashlib
        situation = "|".join([query] + ["%s%s" % _row_key(e) for _s, e in picked + rest])
        seed = int(hashlib.blake2b(situation.encode("utf-8"),
                                   digest_size=8).hexdigest(), 16)
        if (seed % 1000003) / 1000003.0 < p:
            picked[-1] = rest[(seed >> 20) % len(rest)]
    return picked[:k]


def _target_and_rank(query: str, hits):
    from harness.skills import lifecycle as lc
    target = _query_target(query)
    if target:
        owned = [(s, e) for s, e in hits
                 if (e.get("speaker") or lc.SPEAKER_USER) == target]
        if owned:                      # only narrow when the person HAS a matching fact
            hits = owned

    # Depluralised on BOTH sides, for the same reason the tokens are: _REL_NOUN is \bcat\b, so a
    # question about his "cats name" did not register as being about a cat at all, and the row
    # that answered it took the -0.40 penalty for mentioning a pet he supposedly never asked about.
    q_rel = set(_depluralise(m.lower()) for m in _REL_NOUN.findall(query))
    qt = _toks(query)

    def adjust(s, e):
        t = _text(e)
        # a row that introduces a relative/pet the question never mentioned is off-target
        row_rel = set(m.lower() for m in _REL_NOUN.findall(t))
        if row_rel - q_rel:
            s -= 0.40
        # an identity question wants the identity row, not everything containing "name"
        if "name" in qt and e.get("mem_class") == "identity":
            s += 0.30
        # THE REAL HER (2026-08-22): asked about HER (day / feelings / thoughts), her own
        # narrative is the answer's shape — a small nudge on top of its salience weight
        if target == lc.SPEAKER_SELF and e.get("mem_class") in ("self-narrative", "feeling"):
            s += 0.15

        # ── SALIENCE: THE PRIOR (2026-07-13) ────────────────────────────────────
        # What the match score CANNOT know: that he has told her this five times, or that
        # he mentioned it once in March and never again. Two facts can match a question
        # equally well and not deserve the same answer.
        #
        # It is a PRIOR, so it is small and it breaks ties — it does not overrule what the
        # question actually matched. A frequently-repeated fact about his cat still loses
        # to a one-off fact about his GPU when he asks about his GPU. That ordering matters:
        # salience decides which of the RELEVANT memories to surface, never which memories
        # are relevant. Let it dominate and she answers every question with her favourite
        # fact.
        #
        # The old tie-breakers above (the relationship penalty, the identity boost) are what
        # you write when you have no prior and two rows both score 1.00. This is the
        # principled version of the same instinct, and it is derived from what he actually
        # did rather than from what I guessed he meant.
        # ── AND WHAT IT TOLD US, not only how often and how recently ───────────────
        # salience is frequency x recency x class half-life: it knows he SAID it a lot,
        # lately. It cannot tell "My GPU is an RTX 2060" from a two-word endearment -- both
        # said often, both said lately, one a fact about him and the other a pleasantry.
        # surprisal is I(x) = -log2 p(x | model of him) and measures exactly that
        # difference; recall was not reading it. 0.18 sits just under salience's 0.22 on
        # purpose: what he repeats still outranks what was merely novel once, because this
        # term is a RANK and not a verdict.
        return s + 0.22 * lc.salience(e) + 0.18 * _surprisal_of(e)

    return sorted(((adjust(s, e), e) for s, e in hits), key=lambda x: -x[0])
