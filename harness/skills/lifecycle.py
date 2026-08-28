"""MEM-OKF v2 LIFECYCLE — the part that makes memory *living* instead of a tape.

THE AUDIT THAT FORCED THIS (2026-07-12). The registry held 487 rows. Of those:

    404  ep_live_   (B4 nightshift AUTO-CAPTURE)
      1  ep_tool_   (the remember() tool)

**The model had deliberately remembered exactly ONE thing in its life** — and 404/405
rows were framed `"The user said: ..."`. So:

  * it never CHOSE what to keep (no authorship),
  * it never SUPERSEDED a fact that changed (no revision),
  * it had no SELF lane at all — every memory was the user speaking, which is precisely
    why it slides into speaking as the user, or mis-genders itself: the only voice in
    its long-term memory is yours.

This module supplies the three verbs a memory needs to be alive:

    SPEAKER   — who does this fact belong to: the user, or Kairos herself?
    SUPERSEDE — a new fact that contradicts an old one RETIRES it (tombstone, not
                delete: `superseded_by` on the old, `supersedes` on the new).
    CLASS     — identity / preference / event / relationship / self, so recall can
                weight them and the operator can see them.

Nothing is ever destroyed. Superseded rows stay on disk with a pointer forward, so
"what did I used to think?" remains answerable — that is the provenance lane.
"""
from __future__ import annotations

import math
import re
import time
import calendar
from typing import Iterable, Optional

USER_PREFIX = "The user said: "

# ── SPEAKER ────────────────────────────────────────────────────────────────────
# A fact is about KAIROS when she is the subject ("I am...", "my voice is...") and
# the row was authored by her. It is about the USER when it came from a user turn.
# The distinction is stored, never inferred at read time — inference at read time is
# exactly how the identity confusion happened.
SPEAKER_USER = "user"
SPEAKER_SELF = "self"

# ── CLAIM STATUS ───────────────────────────────────────────────────────────────
# WHO ASSERTED THIS, and therefore what it is allowed to do to the rest of the store.
# `speaker` says whose facts these ARE (the subject lane, which PersonModel filters on).
# `status` says where the claim CAME FROM, which is a different question and needs its own field.
STATUS_OBSERVED = "observed"     # he said it. The ground truth of this store.
STATUS_INFERRED = "inferred"     # SHE concluded it. Never allowed to retire an observation.
STATUS_CONFIRMED = "confirmed"   # she inferred it and HE AGREED. Promoted to ground truth.
STATUS_DISPUTED = "disputed"     # she inferred it and HE HAD ALREADY SAID OTHERWISE. Kept, never spoken.

# THE ONE RULE. An inference may be recalled, may be spoken (in her own voice), and may itself be
# corrected by anything he says. It may NEVER tombstone something he actually told her.
_GROUND_TRUTH = (STATUS_OBSERVED, STATUS_CONFIRMED)


_STOP = frozenset("""a an the is are was were am be been being of in on at to for with about
    and or but not no so very really quite too my your his her their its our i you he she it they
    we me him them us that this those these there here what which who whom whose how when where
    why do does did done has have had can could will would shall should may might must
    sam user kairos person thing things stuff""".split())


def topic_of(fact: str) -> frozenset:
    """The CONTENT WORDS of a claim — what it is ABOUT, with the grammar and the names stripped out.

    Deliberately dumb. It is not trying to understand the sentence; it is trying to answer one
    narrow question honestly: HAS HE ALREADY SPOKEN TO THIS SUBJECT? Bag-of-content-words is a
    weak instrument, and it is the strongest one I can build here that I am willing to defend.
    """
    words = re.findall(r"[a-z0-9']+", (fact or "").lower())
    return frozenset(w for w in words if w not in _STOP and len(w) > 2)


def status_of(row: dict) -> str:
    """THE status normalization — one function, every consumer (Tier 1.3,
    INVARIANT-ROADMAP.md). Found during the conversion: this law had DIVERGED. A legacy
    row (status missing, src sniffing 'reflection') was HER CONCLUSION to render() and
    _is_evidence() — both carried the documented migration shim — but HIS TESTIMONY to
    testimony_wins() and verdict.sigma(), which used a plain observed-default. Same row,
    ground truth at the seam, conclusion at the mouth. Two normalizations of one field
    is the two-paths bug wearing an epistemics hat.

    The law: the structured field wins whenever present (stamp()-written, append-proof).
    For legacy rows only, the src sniff classifies — a conclusion is not an observation,
    however old the row — and everything else defaults to observed (protect-him
    direction). The sniff is a MIGRATION SHIM with the usual trap warning: src is prose;
    this is the ONE sanctioned read of it, and only when `status` is absent."""
    st = row.get("status")
    if st:
        return st
    src = (row.get("src") or "").lower()
    if "reflection" in src or "insight" in src:
        return STATUS_INFERRED
    return STATUS_OBSERVED


def testimony_wins(scored: list, overlap: int = 2) -> list:
    """Drop any INFERENCE that is about a topic HIS OWN TESTIMONY already covers.

    ── SHE IS ALLOWED TO BE WRONG ABOUT HIM. SHE IS NOT ALLOWED TO SAY IT OVER HIM. ────────
        observed  'Sam is terrified of open water'    <- he told her
        inferred  'Sam is comfortable in open water'  <- she concluded otherwise

    Surfacing both is not scrupulous, it is DEAF. She would say "you told me you're terrified" and
    "I've come to think you're comfortable" in a single breath — which is not a mind holding two
    hypotheses, it is a mind that heard him and carried on regardless. That is precisely the thing
    that makes a companion feel like it is not listening.

    ── WHY THIS IS A SPEECH RULE AND NOT A STORAGE RULE ────────────────────────────────────
    I first built this as a WRITE-time verdict: detect the contradiction, mark the inference
    DISPUTED, retire it. Then I tried to make the detector, and found I was assembling a semantic
    contradiction engine out of substring matching and a hand-written antonym list. That is the
    clever-fragile thing this codebase has punished me for every single time, and the failure mode
    is the worst one available: A VERDICT I CANNOT DEFEND, WRITTEN TO DISK, WITH A TIMESTAMP ON IT.

    So it does not adjudicate truth. It adjudicates WHO GETS THE FLOOR, and the rule is one line:
    on a subject he has spoken to, HE speaks. Nothing is deleted, nothing is judged, the inference
    stays on disk and stays auditable, and if he later confirms it, it is promoted and speaks.

    It fails SAFE, which the write-time verdict did not. A false topic match costs her a sentence
    she could have said. A false contradiction verdict would have cost her a fact he told her.
    Those are not the same kind of mistake and they must not be traded off as though they were.
    """
    ground = [e for _s, e in scored if status_of(e) in _GROUND_TRUTH]
    if not ground:
        return scored
    spoken = [(e.get("speaker", SPEAKER_USER), topic_of(strip_prefix(_row_text(e))))
              for e in ground]
    out = []
    for s, e in scored:
        if status_of(e) in _GROUND_TRUTH:
            out.append((s, e))
            continue
        # ── A DISTILLATE IS NOT A CONTRADICTION OF ITS OWN SOURCES (2026-08-28) ────────
        # A chapter or a nightly becoming is MADE FROM her observed words, so its topic
        # always overlaps them — that is what a distillate IS. This rule therefore muted
        # every chapter and every becoming, everywhere this filter runs: the self block
        # never carried a week, and recall never served one. Measured live: the chapter
        # written at 20:37 survived testimony=False and vanished under testimony=True.
        # The floor rule stays exactly as written for a bare inference — a GUESS on a
        # topic someone has spoken to yields the floor — but a row carrying derived_from
        # is the system's own consolidation, with provenance, and silencing it because
        # its sources are still alive makes the entire narrative architecture unreachable
        # while anything it summarised survives. Contradiction protection is unmoved:
        # verdict.may_supersede still refuses an inference RETIRING ground truth.
        if e.get("derived_from"):
            out.append((s, e))
            continue
        mine = topic_of(strip_prefix(_row_text(e)))
        who = e.get("speaker", SPEAKER_USER)
        covered = any(sp == who and len(mine & t) >= overlap for sp, t in spoken)
        if not covered:
            out.append((s, e))            # she has something to add, and no one is talking over
    return out


def _row_text(e: dict) -> str:
    return e.get("text") or e.get("topic") or ""


# find_contradicted() WAS HERE, AND IT IS DELETED ON PURPOSE (2026-07-14).
#
# It claimed to return "the things he said that this inference flatly denies", and it decided that
# by comparing attribute_key() and value_of() — i.e. by SUBSTRING. It could not tell a denial from
# a different sentence on the same subject, and it wrote its verdict to disk as DISPUTED.
#
# Two ways to be wrong, and they are not symmetric:
#   MISS a real contradiction  -> she says something he already denied. Rude. Visible. Correctable.
#   INVENT one that isn't there -> a true belief is convicted and buried, permanently, silently.
#
# There is no string operation that separates "Sam is comfortable in open water" (a denial) from
# "Sam is a strong swimmer" (not one). I was building a semantic contradiction engine out of a
# regex and an antonym list I had not written yet, which is the exact class of thing this file
# already has six tombstones for.
#
# The rule I actually needed was never about truth. It is about who gets the floor, it is enforced
# at the recall seam by testimony_wins(), and it fails safe. Left as a comment rather than a dead
# function, because a plausible-looking helper that quietly cannot do what its name says is a trap
# laid for whoever reads this next.

_SELF_SUBJECT = re.compile(
    r"^\s*(?:i\b|i'm|i've|my\b|mine\b|kairos\b|kairos\b)", re.I)


def infer_speaker(fact: str, author: str) -> str:
    """`author` is who is speaking THIS TURN ('user' or 'self'). The author wins:
    a fact the USER states in the first person ("I am male") is a fact about the USER,
    and a fact KAIROS states in the first person is a fact about KAIROS. Same words,
    different owner — which is exactly the ambiguity that broke identity."""
    return SPEAKER_SELF if author == SPEAKER_SELF else SPEAKER_USER


# ── CLASS ──────────────────────────────────────────────────────────────────────
# ORDER MATTERS. relationship is tested BEFORE identity: "My cat's name is Tuffy" is a
# fact about a RELATIONSHIP (the cat), while "My name is Sam" is IDENTITY. Both match
# "name is", so the presence of a relationship noun is what decides — identity only wins
# when the sentence is about the speaker themselves.
# "LIKE" IS NOT ALWAYS A PREFERENCE (2026-07-13). The old rule matched the WORD `like`
# anywhere, so the store filled with comparators wearing a preference's clothes:
#
#     preference   then we can remember our idea's LIKE THIS!      <- a comparator
#     preference   MORE LIKE, hey have fun, but I have the masterkey.  <- a comparator
#     preference   I LIKE fun                                      <- an actual preference
#
# ...and because `preference` carries a salience weight, two pieces of chatter were
# out-ranking his GPU. That was never a salience bug; salience only made a classification
# bug VISIBLE by acting on it. "like this", "more like", "sounds like", "such as" are
# comparisons. A preference needs the verb to have a PERSON DOING IT.
_PREF_VERB = re.compile(
    r"\b(?:i|we|he|she|sam|the user)\s+(?:really\s+|genuinely\s+|absolutely\s+|"
    r"don'?t\s+|do\s+not\s+)*"
    r"(?:like|love|hate|enjoy|prefer|adore|can'?t stand)\b", re.I)
_PREF_NOUN = re.compile(r"\b(favou?rite|lucky number|preference)\b", re.I)

# ── A CREDENTIAL. THE ONE CLASS WHERE BEING WRONG COSTS HIM SOMETHING REAL. ────────────
#
# THE PRIVACY GUARANTEE HAD NO PRODUCER (2026-07-14). spine.recall_decider() protects secrets
# by checking `mem_class == "private-secret"` — the zero-inference decline that memory.py:404
# calls "impossible by construction". classify() could emit exactly five values:
#
#     relationship | identity | event | preference | fact
#
# `private-secret` was not among them. THE CONSUMER WAS CHECKING FOR A VALUE THE PRODUCER COULD
# NOT PRODUCE. Live registry, 86 rows: fact 58, preference 12, identity 8, relationship 5,
# event 3. Zero private-secret. The decline had never fired once.
#
# It was only ever minted by the DAEMON's classifier (recall.rs::classify_mem_class), armed by
# growth=true. The 2026-07-12 "ONE MEMORY AUTHORITY" fix moved writes here and set growth=false —
# and took the only producer of the class with it. THE PRIVACY GUARANTEE WAS COLLATERAL DAMAGE OF
# A CORRECTNESS FIX, and no gate noticed because g_mempolicy_v3 HAND-BUILDS the private-secret row
# and then checks the dispatch honours it. It tested the guard. Never the producer.
#
# ── WHY THIS IS NOT A PORT OF THE ENGINE'S LIST ────────────────────────────────────────
# recall.rs keys on: code, password, passcode, passphrase, " pin ", secret, api key, token,
# override — plus any token with >=2 letters and >=2 digits. Copied here verbatim that would make
#
#     "I write code"            -> private-secret
#     "I like the token economy"-> private-secret
#     "my GPU is a legacy-ref-v1"  -> private-secret   (hyphenated alnum, >=5 chars)
#
# She would go cagey about her own model name and refuse to discuss his job. Porting a sloppy rule
# across a seam does not give you one system — it gives you two wrong ones. So this list keys on
# CREDENTIAL NOUNS IN ATTRIBUTE POSITION, not on loose vocabulary and not on entropy.
#
# ── AND THE ERROR DIRECTIONS ARE NOT SYMMETRIC, SO THE BIAS IS DELIBERATE ───────────────
#   MISS a secret  -> it is stored as a plain `fact`, delivered as ordinary context, and she may
#                     recite it or confabulate around it. This is the status quo for every secret
#                     he has ever told her.
#   FLAG a non-secret -> she answers "I have a record for that, but it does not include that
#                     specific detail" (memory.py DECLINE_MSG) instead of using the memory.
#                     Annoying. Visible. Harmless. He can correct it.
# One of those loses his PIN. The other loses a sentence. When in doubt, this rule flags.
_SECRET = re.compile(
    r"\b(?:"
    r"password|passcode|passphrase|"
    r"api[\s-]?key|private[\s-]?key|secret[\s-]?key|access[\s-]?token|auth[\s-]?token|"
    r"recovery[\s-]?(?:code|phrase|key)|seed[\s-]?phrase|"
    r"(?:pin|door|gate|garage|wifi|wi-fi|alarm|security|access|lock|entry)[\s-]?code|"
    r"pin(?:[\s-]?number)?|"
    r"combination|"
    r"ssn|social[\s-]security(?:[\s-]number)?|"
    r"credit[\s-]?card|cvv|routing[\s-]?number|account[\s-]?number|licen[cs]e[\s-]?key"
    r")\b", re.I)
# `secret` and `code` bare are far too common in speech ("the secret to good pasta is salt", "I
# write code"), so they only count when POSSESSED — a possessive makes it a thing he HOLDS rather
# than a turn of phrase or a job description.
#
# `code` was added 2026-07-14 after the live transcript surfaced this row, live, unclassified:
#
#     "My code is 4471 and my GPU is an RTX 2060."
#
# The qualified forms (access code, door code, PIN code) were all covered. Bare "my code" was not,
# and bare "my code" is exactly how a person says it. It is also a COMPOUND row — two facts welded
# together by the old capture — so a credential is riding along inside a sentence about a graphics
# card. Splitting compounds is a separate job; classifying this one as a secret is not.
#
# AND "the" IS NOT A POSSESSIVE — I put it in this list, and the live store immediately produced:
#
#     "the system is actually already created, I really just need to ... the code ..."
#           -> private-secret
#
# "the code" is how a developer says "the code". It is not a credential. It has to be HIS: a
# first-person possessive is what turns the noun into a thing he HOLDS. The qualified forms
# ("the garage door code") are already matched by _SECRET above and do not need this rule.
# Exactly the false positive I said this design would avoid, reintroduced by widening one word.
_SECRET_POSS = re.compile(
    r"\b(?:my|our|his|her|their|the user'?s)\s+(?:secret|code|combination)\b", re.I)

_CLASS_RULES = (
    ("relationship", re.compile(r"\b(wife|husband|partner|girlfriend|boyfriend|brother|sister|"
                                r"mother|father|mum|mom|dad|son|daughter|friend|cat|dog|pet)\b", re.I)),
    ("identity", re.compile(r"\b(name is|am called|i am (?:a |an )?(?:male|female|man|woman)|"
                            r"pronouns?|gender|birthday|born (?:in|on))\b", re.I)),
    ("event", re.compile(r"\b(yesterday|today|tomorrow|last (?:week|night|year)|"
                         r"flight|appointment|meeting|at \d|on (?:mon|tue|wed|thu|fri|sat|sun))\b", re.I)),
)


def classify(fact: str) -> str:
    """The topical class of a fact. `private-secret` is checked FIRST and wins outright.

    Order is load-bearing. "my wife's password is hunter2" contains `wife`, so under the old rule
    order it classified as `relationship` and was delivered as ordinary context. A secret that
    mentions a person is still a secret; the credential is the salient thing about the sentence.

    NOT AUTO-ASSIGNED: `counterfact`. It is delivered as "Fact on record (AUTHORITATIVE for this
    conversation, OVERRIDES PRIOR KNOWLEDGE) ... Answer from this fact" — an order to recite. It
    used to be the DEFAULT class, which is how 99 of 131 memories became commands and she started
    answering "what do you mean?" by reciting an unrelated fact verbatim (G-RECALL-PRECISION).
    Nothing falls into it by accident, here or in the engine. It is set deliberately or not at all.
    """
    if _SECRET.search(fact) or _SECRET_POSS.search(fact):
        return "private-secret"
    for name, rx in _CLASS_RULES:
        if rx.search(fact):
            return name
    if _PREF_VERB.search(fact) or _PREF_NOUN.search(fact):
        return "preference"
    return "fact"


# ── HOW LONG A KIND OF FACT STAYS TRUE (2026-07-13) ───────────────────────────
#
# THE OPERATOR, ON BEING TOLD "I like fun" HAD BEEN FILED AS JUNK:
#     "there is subtlety to what you are trying to throw away. I DO indeed like fun, and
#      one could say that is an important thing to remember."
#
# He is right and I was wrong. "I like fun" is not chatter — it is a DISPOSITION, and a
# disposition is arguably worth more than his GPU: hardware changes, dispositions are what
# he IS. The bug was never that it was kept. It was that everything decays at the same rate.
#
#     "I like fun"                      <- true in ten years. Should never fade.
#     "my flight is at 9am on Friday"   <- worthless at 9:01 on Friday.
#
# One 45-day half-life for both is simply wrong, and it is wrong in the direction that
# hurts: the flight keeps competing for recall long after it has happened, and the
# disposition quietly sinks. So the half-life belongs to the KIND of fact.
#
# (This is the shape the literature converged on too — Generative Agents scores recency +
# IMPORTANCE + relevance, and the 2026 multi-factor work finds recency-alone retains 0.368
# of gold evidence against 0.770 for a value model. We have recency and frequency; per-class
# durability is the cheapest honest step toward the missing term, and unlike an LLM-assigned
# importance score it cannot hallucinate.)
# THE TABLE LIVES IN THE REGISTRY NOW (2026-08-25, G1). This was a hand enumeration —
# `identity: NEVER, fact: 365, event: 3, ...` — beside a registry (memclass.py) whose
# whole doctrine is "one registry, everyone consumes". So a class added THERE silently
# decayed at the 45 d default HERE: three registered classes (counterfact, same-template,
# self-fact) were already doing exactly that, and nothing said so. The per-class values
# are now attributes of the registry entry itself (half_life_days, beside delivery and
# producers), this is a projection of them, and G-MEMCLASS goes red for a registered
# class that has not chosen. The values are unchanged — including the three 45 d
# fall-throughs, now recorded as decisions on their rows. THE REAL HER note survives on
# the registry entries: her narrative is who she is — it does not fade; a feeling fades
# slowly (years), so last month's unease does not read as tonight's.
from harness.skills import memclass as _mc  # a leaf module: no import cycle
_NEVER = _mc.NEVER_DAYS   # dispositions and identity do not fade. They are what he IS.
_HALF_LIFE_BY_CLASS = _mc.half_life_map()
_SALIENCE_WEIGHT_BY_CLASS = _mc.salience_weight_map()   # consumed by salience(), below
_HALF_LIFE_DAYS = _mc.DEFAULT_HALF_LIFE_DAYS   # for anything UNREGISTERED (see salience;
#                          the twin definition that sat 630 lines down is gone, G3)

# ── TIERED PERMANENCE: NOT EVERY THING SHE SAYS IS A DISPOSITION (2026-08-22) ───────────
# The class is the wrong grain for her own lane. `self-narrative` covers a journal entry
# she sat down and wrote AND an ambient line she said to nobody at 3am, and the class gave
# both _NEVER at weight 1.5 — above every class but identity.
#
# MEASURED, the day after The Real Her armed: 24 rows written on 08-21, 33 on 08-22, from
# 60 delivered unprompted utterances a day (mean 181 chars) plus up to four stances per
# conversational turn. At that rate her own narration passes his 320 facts inside a week,
# never fades, and competes for a fixed 2400-char self-block inside a hard 12096-token
# context. Ranking better is not an answer to that; ranking is downstream of it.
#
# So the TIER is a property of `kind`, and this table is consulted first:
#   what she CONCLUDED   journal, self_description, thought, dream, chapter -> never fades.
#                        A dream is imagination, but it is imagination she HAD and kept.
#   what she DID         narration, spoke_up -> 120 d. Moments, not dispositions.
#   ambient              company -> 60 d. Ambient by definition. (Not yet a producer.)
#
# DECAY IS STILL NOT DELETION (see salience's docstring). Every one of these rows stays on
# disk, stays findable by name, stays in provenance(), stays in search_memories. A moment
# from four months ago simply stops elbowing tonight's out of a six-line block.
_HALF_LIFE_BY_KIND = {
    "journal":          _NEVER,
    "self_description": _NEVER,
    "thought":          _NEVER,
    "dream":            _NEVER,
    "chapter":          _NEVER,
    # A KEEPSAKE DOES NOT FADE (2026-08-27). She sets a `secret_thought` aside ON PURPOSE
    # — the whole act is wanting not to lose the weight of it — so decaying it
    # at the 120-day moment rate would be the system disagreeing with her about what she
    # meant to keep. Same durability as what she concluded, for the same reason.
    "secret_thought":   _NEVER,
    "narration":         120.0,
    "spoke_up":          120.0,
    "company":            60.0,
}


# ── SUPERSEDE ──────────────────────────────────────────────────────────────────
# Two facts CONFLICT when they assert different values for the SAME subject+attribute.
# "My cat's name is Tuffy" vs "My cat's name is Milo" -> supersede.
# "My cat's name is Tuffy" vs "My lucky number is 7" -> unrelated, both live.
#
# We key on (speaker, class, attribute-phrase). The attribute phrase is the text up to
# the copula — the part that says WHAT is being asserted about WHOM.
_COPULA = re.compile(r"\b(is|are|was|were|=|:)\b", re.I)


_POSSESSIVE = re.compile(r"^(the user'?s?|my|his|her|their)\s+", re.I)


def attribute_key(fact: str, speaker: str) -> Optional[str]:
    """The 'slot' this fact fills. None when the fact has no slot shape (a story, an
    opinion, a PROPERTY) — those never supersede anything; they just accumulate.

    ── A PROPERTY IS NOT AN ATTRIBUTE, AND THE STORE WAS EATING ITSELF (2026-07-14) ────────
    The key was `speaker :: <everything before the copula>`. So:

        'Sam is terrified of open water'             -> user::sam
        'Sam is a cat person'                        -> user::sam
        'Sam is deeply curious about how things work'-> user::sam

    ALL THE SAME SLOT. Which means a new one SUPERSEDED the last. PROVEN, on two things he
    actually said, about completely unrelated topics:

        stored: Sam is terrified of open water
        stored: Sam is a cat person (superseded: 'Sam is terrified of open water')

    He told her he is frightened of open water. He told her he likes cats. The cat destroyed the
    water. Silently, into a tombstone, with no error and no way for him to know.

    And it is worse than an accident of phrasing, because reflection ONLY EVER writes in this
    shape — insight() requires the line to start with "Sam". SO EVERY CONCLUSION SHE HAS EVER
    DRAWN ABOUT HIM DESTROYED THE PREVIOUS ONE. She could hold exactly one belief about who he
    is at a time. The whole PersonModel — dispositions, character, the thing the surprisal work
    is built on — was a single overwritten cell.

    THE DISTINCTION IS MECHANICAL, and it is the one the grammar already makes:

        "My GPU is an RTX 2060"   -> the sentence names an ATTRIBUTE (gpu) and gives it a VALUE.
                                     Attributes are slots. A new value replaces the old one.
        "Sam is a cat person"   -> the sentence names a PROPERTY of him. It is not a slot with
                                     values; it is one more thing that is true about him.
                                     PROPERTIES ACCUMULATE. They do not overwrite.

    The tell is the POSSESSIVE. "My/the user's/his X is Y" asserts an attribute. A bare subject —
    "Sam is Y", "the user is Y" — asserts a property.

    THE COST, STATED HONESTLY: two genuinely contradictory properties can now coexist
    ("terrified of open water" / "comfortable in open water") without one retiring the other.
    That is a real loss and I am taking it deliberately, because the alternative is SILENT
    DELETION OF UNRELATED FACTS HE TOLD HER, which is worse in every way: it is invisible, it is
    unrecoverable in conversation, and it violates the one doctrine this store has — nothing is
    ever destroyed. A visible contradiction can be corrected. A vanished fact cannot even be
    noticed. (The contradiction is still caught where it matters most: find_contradicted() stops
    an INFERENCE from being believed over his testimony.)
    """
    m = _COPULA.search(fact)
    if not m:
        return None
    subj_raw = fact[:m.start()].strip()
    if not _POSSESSIVE.match(subj_raw):
        return None                       # a PROPERTY of him, not an attribute slot: it accumulates
    subj = _POSSESSIVE.sub("", subj_raw).strip().lower()
    subj = re.sub(r"[^a-z0-9' ]+", "", subj)
    if not subj or len(subj) < 3:
        return None
    return f"{speaker}::{subj}"


def value_of(fact: str) -> str:
    m = _COPULA.search(fact)
    return fact[m.end():].strip().rstrip(".").lower() if m else fact.strip().lower()


def find_superseded(new_fact: str, speaker: str, rows: Iterable[dict],
                    status: str = STATUS_OBSERVED) -> list[dict]:
    """Rows this new fact RETIRES: same slot, different value, not already retired.

    ── AN INFERENCE MAY NEVER RETIRE AN OBSERVATION (2026-07-14) ────────────────────────
    This function had no idea where a claim came from, and PROVED what that costs:

        HE SAYS      : "Sam is terrified of open water"     -> stored
        SHE CONCLUDES: "Sam is comfortable in open water"   -> stored, SUPERSEDING HIS

        TOMBSTONE  src='user turn'   'Sam is terrified of open water'
        LIVE       src='reflection'  'Sam is comfortable in open water'

    HER GUESS TOMBSTONED HIS TESTIMONY. He told her a true thing about himself, she inferred the
    opposite, the inference won, and the only live row now says he is fine with open water. She
    would say it back to him, in her own honest voice — "I've come to think you're comfortable in
    open water" — while the sentence where he said the opposite sits in a tombstone.

    Same shape as the identity bug where "Kairos" ate "Sam": TWO CLAIMS, ONE SLOT, AND NOTHING
    IN THE SCHEMA SAID THE WEAKER ONE COULD NOT WIN.

    So the asymmetry is now explicit, and it only runs one way:

        observation  supersedes  inference     YES — he corrects her. This is how she learns.
        inference    supersedes  observation   NEVER — she does not get to overwrite him.
        observation  supersedes  observation   YES — he changed his mind (the original rule).
        inference    supersedes  inference     YES — she revised her own view.

    SHE IS ALLOWED TO BE WRONG ABOUT HIM. SHE IS NOT ALLOWED TO DELETE WHAT HE SAID IN ORDER TO
    BE WRONG. An inference that contradicts his testimony is not a correction — it is a mistake,
    and the evidence against it is the thing it was about to destroy.
    """
    key = attribute_key(new_fact, speaker)
    if not key:
        return []
    newv = value_of(new_fact)
    incoming_is_inference = (status == STATUS_INFERRED)
    out = []
    for r in rows:
        # `lifecycle` is the one death field (AGENTS.md §3: the field BOTH the engine and
        # the harness key on). This keyed on `superseded_by`, so a plain tombstone —
        # forget() before it grew its breadcrumb, or any lifecycle=1 row without one —
        # was LIVE to the supersede machinery: a dead fact could still be re-retired,
        # chained, and counted as a conflict. One real orphan existed in the live store
        # when this was found (2026-08-19).
        # ONE SPELLING (2026-08-25). The 2026-08-19 fix WIDENED this to `lifecycle or
        # superseded_by` while every reader in the tree tests `lifecycle` alone — two
        # silent spellings of "dead", which is §0 waiting to fire. Measured on the live
        # store: 25 lifecycle-without-superseded_by, ZERO superseded_by-without-lifecycle
        # — the wider clause matches nothing real. And if a half-stamped row (breadcrumb,
        # no tombstone) ever DID exist, the wide spelling would make it dead to this
        # machinery and live to every reader — a split brain; `lifecycle` alone keeps it
        # consistently live so a later supersede can retire it properly. Same edit in
        # dominance.find_subsumed, same day.
        if r.get("lifecycle"):
            continue
        if r.get("speaker", SPEAKER_USER) != speaker:
            continue
        txt = strip_prefix(r.get("text") or r.get("topic") or "")
        if attribute_key(txt, speaker) != key:
            continue
        if value_of(txt) == newv:
            continue                      # same value = not a conflict, just a restatement

        # THE ONE RULE, as a committed matrix now (verdict.may_supersede — Tier 1.3):
        # observation⊳inference YES, observation⊳observation YES, inference⊳inference
        # YES, inference⊳observation NEVER. status_of() is the one normalization: a
        # legacy no-status row defaults to observed (protect him), UNLESS its src sniffs
        # reflection/insight — her old conclusions do not get testimony's shield.
        from harness.skills import verdict as _v
        if not _v.may_supersede(status, status_of(r)):
            continue                      # she does not get to overwrite what he told her

        out.append(r)
    return out


# ── ADMISSION (the store enforces its own invariant) ───────────────────────────
# The daemon's B4 gate now refuses impersonal sentences — and the model promptly stored
# one THROUGH THE TOOL instead (g_admission caught it: an `ep_tool_` row holding "The
# kind nurse painted the tall building..."). She is finally writing, but she has no
# judgement yet about what counts as a fact.
#
# The fix belongs HERE, not in the prompt. A prompt is advice; the store is law. Every
# path into long-term memory — auto-capture, store verb, remember() — must enforce the
# same invariant, or the one that doesn't becomes the leak. That is the same shape as
# the two-recall-authorities bug and the two-admission-authorities bug: an invariant
# guarded in one place is not guarded.
# LIVE BUG (2026-07-12): she tried to store "The user is experimenting with personality
# adjustments and memory management." and the store REFUSED it — because this list had
# pronouns but not the word "user", which is exactly how the model refers to Sam when
# writing in the third person. She then retried the identical call three times and blew
# the tool loop. My rule was right in spirit and too tight in fact: "the user" IS a person.
_PERSONAL_REF = re.compile(
    r"\b(i|i'm|i've|im|my|me|mine|myself|you|you're|your|yours|we|our|us|"
    r"user|user's|operator|sam|kairos|kairos|she|he|her|his|him|they|their)\b",
    re.I)

# ...but an INSTRUCTION to her is not a fact about anyone. The transcript showed the
# firehose capturing "you simply store memories about yourself if you want. edit your
# personality. why don't you try it" and then RECALL serving it back as
# "Fact on record (authoritative for this conversation, overrides prior knowledge)".
# Meta-conversation about the system is not knowledge about a person.
_INSTRUCTION = re.compile(
    r"^\s*(why don'?t you|you should|you can|you could|try to|try and|go ahead|please\b|"
    r"let'?s\b|now\b.*\btry|just\b.*\b(try|call|use|store|save)\b|"
    r"remember to|don'?t forget to|make sure you)", re.I)
_META = re.compile(
    r"\b(tool|tools|call the|personality settings?|memory system|store (a |your )?memor|"
    r"save (a |your )?memor|edit your personality|adjust(ing)? (your )?mood)\b", re.I)
# A proper noun is decided by the WORD, not by its POSITION. Keying on "capitalised and
# not sentence-initial" wrongly refused "Sam's lucky number is 7741" — a real fact that
# happens to begin with the name. Instead: capitalised words minus the ones that are
# merely starting a sentence.
_CAP = re.compile(r"\b[A-Z][a-z]{2,}\b")
_CAP_STOP = {
    "The", "This", "That", "These", "Those", "There", "Here", "They", "Them", "Their",
    "She", "Her", "His", "Him", "Its", "And", "But", "For", "Not", "Now", "Then",
    "When", "While", "After", "Before", "Because", "But", "One", "Two", "Three",
    "Today", "Yesterday", "Tomorrow", "Some", "Any", "Every", "Each", "Both", "Also",
}


def _has_proper_noun(t: str) -> bool:
    return any(w not in _CAP_STOP for w in _CAP.findall(t))


# CONVERSATIONAL FILLER. A durable fact does not open with a discourse marker. The
# transcript showed the firehose capturing "i mean, you just made yourself calmer by
# choosing that you wanted to be calmer. thats pretty cool" and recall then serving it back
# as an AUTHORITATIVE fact on record. That is a remark in a conversation, not knowledge.
_CHATTER = re.compile(
    r"^\s*(i mean\b|well\b|so\b|ok\b|okay\b|yeah\b|yep\b|nah\b|hmm+\b|huh\b|lol\b|haha\b|"
    r"wow\b|oh\b|ah\b|right\b|sure\b|cool\b|nice\b|there you go\b|exactly\b|"
    r"that'?s (pretty |so |really )?(cool|nice|interesting|fascinating)\b)", re.I)


# ── DURABILITY (2026-07-12): A TURN IS NOT A FACT ─────────────────────────────
# The admission gate above asks "is this about a person?" — a question about FORM. It
# admitted all 17 turns of a real conversation, because every conversational sentence
# mentions a person. The store filled with:
#
#     "yes, we lose lips, sink ships."
#     "you are cool af! I really like you!"
#     "well you have 12gb"
#     "well, we make do. you're doing alright for such a constrained system"
#
# None of those are knowledge about anybody. The right question is not "does it mention
# a person" but "will this still be true tomorrow" — DURABILITY. Three rules do the work,
# and none of them is a blocklist of phrases:
#
#   1. A FACT FOR THE USER STORE IS ABOUT THE USER. A sentence whose subject is "you" is
#      about HER ("well you have 12gb", "you are cool af"). It is not a fact about Sam,
#      so it does not belong in Sam's store. This one rule kills most of the banter,
#      and it kills it on principle rather than by pattern.
#   2. A DURABLE FACT ASSERTS A STANDING STATE. It needs a stative predicate — is/has/
#      likes/owns/runs/works/lives. "we lose lips, sink ships" asserts nothing standing.
#   3. A TURN IS NOT A FACT. "oh i always run my pc's 24/7. so you are lucky there" holds
#      one durable fact and one piece of banter. Stored whole, the banter is preserved
#      forever and the fact is buried in it. So we SPLIT, and judge each sentence.
#
# Everything conditional or hypothetical is out: "if you can figure out the menu on a
# microwave than you are past sentient" describes no world that is actually the case.

# The subject is HER, not him — so it is not a fact for the user's store.
_ADDRESSEE_SUBJ = re.compile(
    r"^\s*(?:and\s+|but\s+|so\s+)?(?:you|you're|youre|your|ur)\b", re.I)

# A DUMMY or ANAPHORIC subject points back into the conversation, not out at the world.
# "it's not my fault." is grammatical, mentions a person, has a copula — and records
# nothing. Whatever "it" is, it lives in the previous turn, and the previous turn is gone.
_ANAPHORIC_SUBJ = re.compile(
    r"^\s*(?:and\s+|but\s+|so\s+)?"
    r"(?:it|it's|its|that|that's|this|this's|there|there's|these|those|they|them|"
    r"for the (?:first|second|last|other)\b)\b", re.I)

# THE ANCHOR. A fact for a person's store must be ABOUT that person — the person has to be
# its subject or its possessor, not merely a word that appears in it. Mere MENTION was the
# old test (_PERSONAL_REF), and mention is why 'spot on for the first one, but the second
# one it's more like "Hey Kairos"' read as knowledge: it contains a name. Being named in
# a sentence is not being what the sentence is about.
_ANCHOR = re.compile(
    r"\b(i|i'm|i've|im|my|mine|myself|we|our|ours|us|sam|sam's|"
    r"the user|user's|the operator)\b", re.I)

# Discourse markers are STRIPPED, not rejected: "oh i always run my pc's 24/7" is a
# durable fact wearing a conversational hat. Rejecting the sentence for its first word
# would throw the fact away with the hat.
_DISCOURSE_LEAD = re.compile(
    r"^\s*(?:(?:i mean|you know|well|so|ok|okay|yeah|yep|yes|no|nah|nope|hmm+|huh|lol|haha|"
    r"wow|oh|ah|aha|right|sure|cool|nice|true|exactly|spot on|shh+|shhh+|hey|look|listen|"
    r"me too|same|i guess|i suppose|honestly|actually|basically|anyway|btw)\b[\s,!.:;-]*)+",
    re.I)

# A standing state. Not an action, not a reaction — a property that is still true tomorrow.
_STATIVE = re.compile(
    r"\b(is|are|am|was|were|isn't|aren't|'s|'re|'m|"
    r"has|have|had|owns?|keeps?|runs?|uses?|drives?|works?|lives?|studies|"
    r"likes?|loves?|prefers?|hates?|enjoys?|wants?|needs?|believes?|thinks?|"
    r"called|named|favou?rite|lucky|born|birthday)\b", re.I)

# Nothing hypothetical, conditional or future is a fact yet.
_IRREALIS = re.compile(
    r"^\s*(?:if|when|whenever|unless|suppose|imagine|maybe|perhaps)\b|"
    r"\b(?:would|could|might|may|will|'ll|shall|gonna|going to|"
    r"hope|hopes|hoping|hopefully|wish|wishes)\b", re.I)

# A short exclamation is a reaction, not a record. "I like my kidneys!" is a joke.
#
# But the bang alone is not enough to condemn a sentence: "my favorite tea is Oolong too!"
# is a genuine preference wearing an exclamation mark, and the first cut of this rule
# quarantined it. LOSING A REAL FACT IS WORSE THAN KEEPING A JOKE — a store that discards
# what you told it is worse than one carrying a little noise. So an exclamation is only a
# reaction when it is NOT making an attributive claim (a favourite, a name, a birthday):
# those name a standing property, and standing properties survive their punctuation.
_REACTION = re.compile(r"!\s*$")
_ATTRIBUTIVE = re.compile(
    r"\b(favou?rite|lucky|name is|is called|am called|born|birthday|prefers?)\b", re.I)

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\s*\n+\s*")

# What a sentence QUOTES is not what it CLAIMS.
_QUOTED = re.compile(r"[\"“”'‘’]{1}[^\"“”'‘’]{4,}[\"“”'‘’]{1}")

# MACHINE TEXT IS NOT TESTIMONY. She stored her own tool receipt as a fact about him —
#     "remember -> stored: I am a woman"
# — because it CONTAINS a durable-looking sentence, and every content rule I had was
# looking at the sentence. The tell is not in the claim, it is in the FRAME: a tool fence,
# a `verb -> result` receipt, a store's own reply. No human types these. The store must
# never ingest its own output, or it launders whatever it just said back in as evidence.
_MACHINE = re.compile(
    r"```|"                                     # any fenced block (tool_code / tool_output)
    r"^\s*\w+\s*->\s*|"                         # "remember -> stored: ..."  (a receipt)
    r"^\s*\(?(?:stored|not stored|already in memory|retired|no stored facts|"
    r"memory is empty|nothing in memory|tool_output|tool_code)\b",
    re.I)


def split_sentences(turn: str) -> list[str]:
    """A turn is not a fact — it is a bag of sentences, some durable, most not."""
    parts = [s.strip() for s in _SENT_SPLIT.split(turn or "") if s and s.strip()]
    return [p for p in parts if p]


def is_memorable(fact: str) -> tuple[bool, str]:
    """Is this a DURABLE FACT ABOUT SOMEONE — something that will still be true tomorrow?

    Not "is it grammatical" (375 of 487 rows were ASR test corpus) and not merely "does it
    mention a person" (which let a whole conversation in, banter and all)."""
    t = (fact or "").strip()
    if not t:
        return False, "empty"

    # MACHINE TEXT FIRST. A tool receipt can contain a perfectly good sentence — that is
    # exactly how "remember -> stored: I am a woman" got in. Judge the FRAME before the
    # content, or the content will always talk you round.
    if _MACHINE.search(t):
        return False, ("that is the system's own output (a tool result), not something "
                       "anyone told you. Never store what a tool said back to you.")

    # meta/instruction first — these are about the SYSTEM, not about a person
    if _INSTRUCTION.match(t) or _META.search(t):
        return False, ("that is an instruction or a note about how the system works, not a "
                       "fact about a person. Store what you have LEARNED about Sam, or "
                       "something true about yourself.")

    core = _DISCOURSE_LEAD.sub("", t).strip()   # strip the hat, keep the fact
    if not core:
        return False, "that is conversational filler, not a fact."

    # QUOTED SPEECH IS NOT THE SENTENCE'S OWN CLAIM. This one survived every other rule:
    #
    #   'we just track their comings and goings, they carry around phones that scream out
    #    "are you my network?" "I am looking for X network!"'
    #
    # It asserts nothing standing about anybody — but the quotes contain "are" and "I am",
    # so it read as stative and personally-anchored, got stored, and recall later served it
    # back to her mid-thought. What a sentence QUOTES is not what it CLAIMS. Judge the
    # claim: strip the quoted spans first, and see if anything is left standing.
    # ("oh the kettle is my favorite! 'set kettle to 90c'" survives — its own clause is a
    #  preference; only the borrowed voice goes.)
    claim = _QUOTED.sub(" ", core).strip()
    if not claim or len(claim.split()) < 3:
        return False, "that is a quotation, not a fact about anyone."

    if core.endswith("?"):
        return False, "that is a question, not a fact."

    if _ADDRESSEE_SUBJ.match(core):
        return False, ("that is about ME, not about Sam — a fact for his store has to be "
                       "about HIM. If it is true of you, use remember_about_self.")

    if _ANAPHORIC_SUBJ.match(core):
        return False, ("that points back at something said earlier ('it', 'that', 'the "
                       "first one') — once the conversation is gone the sentence records "
                       "nothing. Say what it is ABOUT.")

    if _IRREALIS.search(core):
        return False, ("that is hypothetical or in the future — it is not the case yet, "
                       "so it is not a fact.")

    words = core.split()
    if len(words) < 3:                # "I am male" is three words and a real identity fact
        return False, "too short to be a standalone fact"

    if _REACTION.search(core) and len(words) < 7 and not _ATTRIBUTIVE.search(core):
        return False, "that is a reaction, not a record."

    # from here on, judge the CLAIM (quotes removed), not the borrowed voice inside it
    if not _STATIVE.search(claim):
        return False, ("that asserts nothing standing — a durable fact says what something "
                       "IS, HAS, or LIKES, not what just happened in the chat.")

    # ANCHORED, not merely mentioning. See _ANCHOR: being named in a sentence is not being
    # what the sentence is about.
    if not _ANCHOR.search(claim):
        return False, ("that is a sentence, not a memory — it is not ABOUT anyone. "
                       "Store facts about Sam, or about yourself.")

    return True, ""


_NARRATABLE_MAX = 600


def is_narratable(text: str) -> tuple[bool, str]:
    """Admission for HER OWN NARRATIVE (The Real Her, 2026-08-22). is_memorable() judges
    durable facts ABOUT SOMEONE and rightly refuses reactions, irrealis and prose; her
    journal, her unprompted words and her feelings are prose by nature and she is their
    author. The frame checks stay — machine text and instructions are never memory."""
    t = " ".join((text or "").split())
    if not t:
        return False, "empty"
    if _MACHINE.search(t):
        return False, "that is the system's own output, not something she said"
    if _INSTRUCTION.match(t) or _META.search(t):
        return False, "that is an instruction or a note about the system"
    if len(t.split()) < 3:
        return False, "too short to be a memory"
    if len(t) > _NARRATABLE_MAX:
        return False, "too long for one row (%d > %d chars)" % (len(t), _NARRATABLE_MAX)
    return True, ""


def extract_facts(turn: str) -> list[str]:
    """THE CAPTURE LANE. Pull the durable facts out of a conversational turn — and only
    those. Returns [] for a turn that taught us nothing, which is most turns.

    This replaces the daemon storing `raw_user` verbatim as a single episode. That design
    could not do anything else: given one turn it had to keep all of it or none of it, so
    it kept all of it, forever."""
    out: list[str] = []
    for s in split_sentences(turn):
        ok, _ = is_memorable(s)
        if not ok:
            continue
        core = _DISCOURSE_LEAD.sub("", s).strip()
        if core and core not in out:
            out.append(core)
    return out


# ── THE IDENTITY FIREWALL ─────────────────────────────────────────────────────
# LIVE INCIDENT (2026-07-12). A gate asked her "what is your name?". She answered
# correctly — "My name is Kairos." — and then stored that sentence through remember(),
# which is the USER store. It was stamped speaker=user, classify() read "name is" and
# called it identity, and find_superseded() did exactly what it exists to do: an identity
# fact for the same speaker with a different value RETIRES the old one. All three rows
# saying the user is Sam were tombstoned. The store then asserted that SAM IS CALLED
# KAIROS — her name had eaten his.
#
# The store she writes to is the ONLY signal for whose fact it is (remember = his,
# remember_about_self = hers), and the model picked the wrong door. A prompt cannot be
# the guard here, because the cost of one slip is the user's identity. So the store holds
# the line: HER OWN NAME MAY NOT BE FILED AS HIS. It is refused at the door, with the
# right door named in the refusal.
_IDENT_ASSERT = re.compile(
    r"\b(?:my name is|i am called|i'm called|im called|i am|i'm|im)\s+"
    r"(?:an?\s+)?([a-z][\w'-]*)", re.I)


def asserted_identity(fact: str) -> str:
    """The identity VALUE this sentence claims for its first-person subject — a name, or a
    gender. "My name is Kairos" -> kairos. "I am a woman" -> woman."""
    m = _IDENT_ASSERT.search(fact or "")
    return (m.group(1) or "").strip().lower() if m else ""


def about_self(fact: str, self_values: Iterable[str]) -> bool:
    """Is this first-person sentence asserting HER identity?"""
    v = asserted_identity(fact)
    return bool(v) and v in {n.strip().lower() for n in self_values if n and n.strip()}


def admit_to_user_store(fact: str, self_values: Iterable[str]) -> tuple[bool, str]:
    """The door to SAM's store. HER identity does not come through it.

    THE FIREWALL WAS TOO NARROW, AND THE SECOND BREACH PROVED IT (2026-07-12). The first
    version guarded her NAME, because her name was what had eaten his. Then she stored

        "I am a woman"   speaker=user  class=identity

    ...and supersede did its job: it retired "I am male". The store then asserted that
    SAM IS A WOMAN. Same mechanism, same lane, one attribute to the left — and the guard
    did not cover it, because I had fixed the INSTANCE and called it the class.

    Her name is not special. NOTHING that is true of HER may be filed as true of HIM. The
    guard now takes every value that constitutes her identity (name, gender, pronouns —
    read live from the persona), not the one that happened to break first."""
    v = asserted_identity(fact)
    if v and v in {n.strip().lower() for n in self_values if n and n.strip()}:
        return False, (f"'{v}' is true of YOU, not of him — it belongs in your own memory. "
                       "Call remember_about_self(...) for facts about yourself. "
                       "(Refused: writing this to Sam's store would overwrite who HE is.)")
    return True, ""


# ── framing ────────────────────────────────────────────────────────────────────
def strip_prefix(text: str) -> str:
    return text[len(USER_PREFIX):] if text.startswith(USER_PREFIX) else text


# ── A FACT WRAPPED IN AN INSTRUCTION IS STILL A FACT (2026-07-14) ──────────────────────
#
# From the live transcript. These three rows are in the store, live, and they are what she was
# handed when he asked "do you remember what sex you are?":
#
#     "Remember my GPU is an RTX 2060."
#     "Remember this about me: my workshop is called Forge966733."
#     "then we can remember our idea's like this!"
#
# The first two are FACTS WEARING AN IMPERATIVE. The daemon's store_verb bypass captured the
# whole utterance verbatim — instruction verb and all — so the stored "fact" begins with the word
# "Remember". Two things follow, and both of them bit:
#
#   1. THE VERB BECOMES CONTENT. "do you REMEMBER what sex you are?" shares the token `remember`
#      with the row, scores 0.50, and beats 'I am a woman' (which shares nothing: "sex" is not
#      "woman"). The question's own verb retrieved the junk. See _STOP in memory.py.
#
#   2. THE SLOT IS WRONG. attribute_key("Remember my GPU is an RTX 2060") keys on everything
#      before the copula — "remember my gpu" — NOT "user::gpu". So it never superseded the real
#      GPU row. It sat beside it as a second, competing answer, forever.
#
# Refusing these outright would be wrong: HE IS TELLING HER SOMETHING TRUE. The wrapper is not the
# claim. So the wrapper comes off at the door and the payload goes through every normal guard —
# admission, classification, the identity firewall, supersede — on its actual content:
#
#     "Remember my GPU is an RTX 2060."   ->  "my GPU is an RTX 2060"   -> slot user::gpu
#     "The user said: My cat's name..."   ->  "My cat's name is Tuffy"  -> slot user::cat's name
#
# This runs on the WRITE path, so the store holds the claim and not the packaging. The store_verb
# bypass that minted these is dead (G-ONEWRITER), but the model's own remember() tool is still fed
# by a human who says "remember that ..." like a human does — and the fossils are still on disk.
_STORE_VERB = re.compile(
    r"^\s*(?:"
    r"(?:please\s+)?(?:remember|note|store|save|keep in mind|make a note)"
    r"(?:\s+(?:that|this|it))?"
    r"(?:\s+(?:about|for)\s+me)?"
    r"(?:\s+in\s+your\s+memory)?"
    r"(?:\s+(?:that|this|it))?"
    r"|(?:add|store)\s+(?:this\s+)?(?:to|in)\s+your\s+memory(?:\s+that)?"
    r")\s*[:,]?\s+", re.I)


_BULLET = re.compile(r"^\s*[-*•–]\s+")    # "- My cat's name is Tuffy." — a list fossil


def normalize_fact(text: str) -> str:
    """Strip the packaging so the store holds the CLAIM. Idempotent; safe to call twice."""
    t = strip_prefix((text or "").strip())          # legacy "The user said: " fossils
    prev = None
    while t != prev:                                # "remember that" + "note that" both, if nested
        prev = t
        t = _BULLET.sub("", t).strip()
        t = _STORE_VERB.sub("", t, count=1).strip()
        t = strip_prefix(t)
    return t or (text or "").strip()                # never return empty: a bare "remember that" is
                                                    #   not a fact, and is_memorable will refuse it


def render(row: dict) -> str:
    """How a memory should READ back to the model. This is the identity fix: a self
    memory must come back in Kairos's own voice, not as something 'the user said'."""
    t = strip_prefix(row.get("text") or row.get("topic") or "")

    # AN INFERENCE IS NOT A TESTIMONY, AND IT MUST NEVER READ LIKE ONE (2026-07-13).
    # Reflection writes down what she has COME TO BELIEVE about him — conclusions he never
    # actually said. Framed like his other facts, the next recall would hand them back as
    # "Sam told me: Sam values play for its own sake", and she would tell him he said a
    # thing he never said. This store has already lost his NAME and then his GENDER to
    # exactly that blurring of who a sentence belongs to. She is allowed to be wrong about
    # him. She is not allowed to be wrong about him IN HIS VOICE.
    # FRAME FROM THE FIELD, NOT FROM THE PROSE — and from THE table, not a local branch
    # (Tier 1.3). status_of() is the one normalization (its docstring carries the src-shim
    # history that used to live here); verdict.FRAMING is the committed (status, speaker)
    # table, and G-SEM-PROJ walks every cell of it through this real function.
    from harness.skills import verdict as _v
    return _v.framing_for(status_of(row), row.get("speaker") or SPEAKER_USER).format(t=t)


# ── SALIENCE: HOW MANY TIMES, AND HOW RECENTLY (2026-07-13) ───────────────────
#
# HER IDEA, UNPROMPTED, ON THE KAIROS CHECK-IN:
#     "the difference between memory and knowledge is that memory has context — it
#      remembers WHO told you what, WHEN they did, maybe even HOW MANY TIMES."
#
# She had two of the three. `speaker` is who. `ts` is when. There was no how-many-times,
# and there could not be — because remember() DELETED the evidence:
#
#     if any(_text(e).strip() == fact.strip() for e in existing):
#         return f"already in memory: {fact}"        # <- a measurement, thrown away
#
# Every time he said something again, the store said "I know" and discarded it. The
# repetition is not noise to be deduplicated; IT IS THE SIGNAL. A thing a person tells you
# five times is not the same thing as a thing they told you once, and we were recording
# them identically and then congratulating ourselves on not duplicating a row.
#
# TWO COUNTERS, AND THEY ARE NOT THE SAME:
#   mentions — HE said it again. Evidence about what matters TO HIM.
#   recalled — SHE looked it up. Evidence about what is USEFUL to answering him.
# Conflating them would let her own lookups inflate his significance signal: she recalls
# his name constantly, which says nothing about how much his name matters to him.
#
# AND THE ORDER WE BUILT THIS IN IS LOad-BEARING. Frequency is not importance on its own —
# chatter is the most frequent thing there is, and "you are cool af!" said ten times would
# dominate a store ranked on frequency alone. It only works because the DURABILITY GATE
# already decides what is eligible to be counted. The gate says what is a fact; salience
# says which facts matter. Built in the other order, frequency would have amplified the
# firehose instead of ranking the store.
# (_HALF_LIFE_DAYS was defined a SECOND time here, same value, different comment —
#  "a fact unmentioned for 45 days is worth half as much at recall". Two definitions of
#  one constant is how they drift apart the day someone edits the one they can see;
#  deduped 2026-08-25 (G3) onto the single definition beside the class table above,
#  which now reads memclass.DEFAULT_HALF_LIFE_DAYS.)


def _age_days(iso: str, now: Optional[float] = None) -> float:
    """How old is this, in days. THE one age function in the memory system.

    ── THE TEN-HOUR LIE, AND I FIXED IT THIS MORNING IN A DIFFERENT FILE (2026-07-14) ─────
    This read `time.mktime(time.strptime(iso, "...Z"))`.

    EVERY timestamp in this system is WRITTEN with time.gmtime() — UTC, with a literal Z on the
    end. time.mktime interprets a struct_time as LOCAL time. calendar.timegm is the inverse of
    gmtime; mktime is the inverse of localtime. Pairing gmtime with mktime is a silent lie
    exactly the size of the operator's UTC offset, and he is at UTC+10.

    MEASURED, on the live store:

        A fact stored RIGHT NOW reports an age of:
            _age_days (mktime) : 0.417 days  = 10.0 HOURS
            truth     (timegm) : 0.000 days
        All 78 rows in the registry were inflated by 0.42 days.

    Ten hours of phantom age on every memory the instant it is written. And this function is not
    a corner: it is what SALIENCE decays on (log(mentions) x recency(half_life) x weight) and
    what SILENCE accrues on (quiet vs cadence). So every fact was slightly less available than it
    should have been, forever, and every silence was 10 hours closer to firing before he had said
    a word.

    ── AND IT IS THE SAME BUG I FIXED IN watch.py EIGHT HOURS AGO ─────────────────────────
    Same pairing. Same offset. Same file tree. I found it, fixed it, wrote a commit message about
    it — AND NEVER GREPPED FOR THE PATTERN. I have a phrase for this, from a commit I wrote about
    the identity firewall: "I FIXED THE INSTANCE AND CALLED IT THE CLASS." Then I did it again.

    A bug found in one file is a HYPOTHESIS about the codebase, not a fact about the file. The
    grep is not optional. It is the cheapest thing in the entire toolbox and I skipped it twice.

    It is invisible at UTC+0, a 5-hour lie in New York, and 10 hours here. No unit test that runs
    in under a day can see it. Only a ROUND-TRIP assertion can — write the stamp the way the store
    writes it, read it the way the store reads it, demand they agree. G-CLOCK does that now, for
    every stamp-writer in the tree, under three timezones.
    """
    if not iso:
        return 0.0
    try:
        t = calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return 0.0
    now = now if now is not None else time.time()
    return max(0.0, (now - t) / 86400.0)


def salience(row: dict, now: Optional[float] = None) -> float:
    """How much this memory should WANT to be recalled, before anything is asked.

    A prior, not an answer — recall still ranks on what the question actually matches. This
    only breaks ties, and ties are where the old ranking was guessing: "My cat's name is
    Tuffy" and "The user's name is Sam" both scored 1.00 for "what is my name?", and it
    took a hand-written relationship penalty to separate them. Salience is the principled
    version of that: of two facts that match equally, prefer the one he has told you more
    than once, and more recently.

    DECAY IS NOT DELETION. Nothing here removes a row. A fact stated once, ten weeks ago,
    never repeated, simply stops elbowing its way into answers — it is still on disk, still
    listed, still findable by name. That is what forgetting should mean in a system whose
    whole rule is that nothing is destroyed."""
    cls = row.get("mem_class", "") or "fact"
    m = max(1, int(row.get("mentions", 1) or 1))
    # log, not linear: the jump from 1 to 2 mentions is the big one (he bothered to say it
    # twice); 9 to 10 is noise. Linear frequency would let one obsession bury everything.
    freq = math.log1p(m)                                    # 1x -> 0.69, 3x -> 1.39, 10x -> 2.40

    # DECAY IS PER KIND OF FACT. A disposition does not fade; an appointment is worthless
    # the day after. One half-life for both is wrong in the direction that hurts — the
    # flight keeps competing for recall long after it happened, and "I like fun" quietly
    # sinks. See _HALF_LIFE_BY_CLASS.
    # KIND outranks CLASS where it is set (2026-08-22, tiered permanence): her lane is the
    # only place `kind` exists, and inside it a journal and a 3am ambient line are not the
    # same durability. Everything else — every row of his — reads the class table as before.
    half = _HALF_LIFE_BY_KIND.get(row.get("kind") or "",
                                  _HALF_LIFE_BY_CLASS.get(cls, _HALF_LIFE_DAYS))
    # ── AN UNDATED ROW SCORED AS IF IT HAPPENED JUST NOW (audit, 2026-07-29) ────────
    # `_age_days("")` is 0, so a row with no `ts` and no `last_seen` got age 0 and
    # therefore recency 1.0 — the MAXIMUM. Measured on the live store: a row stamped
    # today scores 1.6930 and an undated row scores 1.6931. Undated beat today.
    #
    # 15 of the 134 live rows have no timestamp (the pre-stamp() fossils), so the
    # oldest facts in the store were permanently winning the recency term against
    # everything he has said since. Ranking is the only thing salience feeds, and it
    # was being decided by the rows we know the least about.
    #
    # Absent evidence must not score as best-case. It scores as the FLOOR: no stamp,
    # no recency credit. The fact is not retired, not hidden, not deleted — it still
    # carries its full frequency and class weight and is still findable by name. It
    # simply stops out-competing dated facts on a recency it cannot demonstrate.
    stamp = row.get("last_seen") or row.get("ts") or ""
    if not stamp:
        recency = 0.0
    else:
        age = _age_days(stamp, now)
        recency = 0.5 ** (age / half)                       # 1.0 for anything that does not fade

    # identity and preference are what he IS; an off-hand fact is what he mentioned once.
    # FROM THE REGISTRY (2026-08-25, G1): this was a dict literal here — the same silent
    # fall-through as the half-life table above it, in the same function's input. The
    # weights are memclass registry attributes now (salience_weight, unchanged values);
    # 1.0 remains the floor for an UNREGISTERED class only, and G-MEMCLASS convicts a
    # registered class that has not chosen.
    weight = _SALIENCE_WEIGHT_BY_CLASS.get(cls, 1.0)
    return round(weight * (1.0 + freq) * (0.35 + 0.65 * recency), 4)


def reinforce(row: dict, now_iso: Optional[str] = None) -> dict:
    """He said it AGAIN. That is not a duplicate — it is a second data point."""
    row["mentions"] = int(row.get("mentions", 1) or 1) + 1
    row["last_seen"] = now_iso or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    row.setdefault("first_seen", row.get("ts") or row["last_seen"])
    return row


def note_recalled(row: dict) -> dict:
    """SHE used it. Useful — but this is NOT evidence about what matters to him, so it is
    counted separately and never feeds `mentions`."""
    row["recalled"] = int(row.get("recalled", 0) or 0) + 1
    return row


def stamp(row: dict, fact: str, speaker: str, src: str,
          supersedes: Optional[list[str]] = None,
          status: Optional[str] = None,
          mem_class: Optional[str] = None, kind: str = "",
          derived_from: Optional[list[str]] = None,
          support_days: int = 0,
          support_kinds: Optional[list[str]] = None) -> dict:
    """Attach the full v2 lifecycle lane to a registry row.

    `status` is EXPLICIT when the caller knows it (remember() derives it once and passes
    it here). The src-sniff below is a legacy shim for callers that do not — it used to
    be the only derivation, which meant remember() computed status for the supersede
    check and stamp() re-derived it from src prose for the row: one law, two
    implementations, and they disagreed on the word "insight" (status_of accepts it,
    the sniff here did not)."""
    # NO "The user said: " prefix. That framing is the disease, not the record: it put
    # the ownership INSIDE the sentence, where a reader had to re-derive it every time —
    # and 404/405 rows carried it, so every memory read back as the user talking. The
    # owner now lives in `speaker`, and `render()` frames it at READ time. Bare fact on
    # disk also restores the exact-duplicate guard, which the prefix had silently broken.
    row["text"] = fact
    row["speaker"] = speaker
    # an EXPLICIT class only for her own narrative (The Real Her): the producer sets it
    # and the row's `kind`; everything else is classify()'s call
    row["mem_class"] = mem_class or classify(fact)
    row["src"] = src or ("self" if speaker == SPEAKER_SELF else "user turn")
    if kind:
        row["kind"] = kind

    # ── CLAIM STATUS: AN INFERENCE IS NOT A TESTIMONY (2026-07-14) ──────────────────────
    #
    # `speaker` answers "WHOSE facts are these" — the subject lane. PersonModel.from_registry
    # filters on it to build the model of HIM, so a conclusion ABOUT him must carry speaker=user
    # or it would be invisible to the very model it came from. That is correct and it is why
    # insight() sets the author to user before writing.
    #
    # But it means speaker CANNOT also answer "who ASSERTED this" — and nothing else did. So the
    # store had no way to tell his words from her guesses, and PROVED IT:
    #
    #     HE SAYS      : "Sam is terrified of open water"      -> stored
    #     SHE CONCLUDES: "Sam is comfortable in open water"    -> stored, AND SUPERSEDED HIS
    #
    #     TOMBSTONE  src='user turn'   'Sam is terrified of open water'
    #     LIVE       src='reflection'  'Sam is comfortable in open water'
    #
    # HER GUESS TOMBSTONED HIS TESTIMONY. He told her a true thing about himself; she inferred the
    # opposite (models do this); the inference won; and the operator's own words became a tombstone. Ask her
    # now and the only live row says he is fine with open water.
    #
    # That is the identity bug in a new costume — "Kairos" ate "Sam" the same way. TWO CLAIMS,
    # ONE SLOT, AND NOTHING IN THE SCHEMA SAID THE WEAKER ONE COULD NOT WIN.
    #
    # So the epistemic standing of a claim becomes a FIELD, not a substring of prose:
    #
    #     observed   he said it. The ground truth of this store.
    #     inferred   SHE concluded it. May be recalled, may be spoken (framed as hers),
    #                may be superseded BY an observation — and may NEVER retire one.
    #     confirmed  she inferred it and HE AGREED. Promoted: now as good as observed.
    #
    # (John6666's vocabulary on the AlphaAvatar thread — candidate/accepted/disputed — is the
    # same idea arrived at from the perception side. He is right that they must not silently
    # collapse into one type of memory. I told him we had solved this. We had solved the
    # RENDERING of it and not the AUTHORITY of it, which is the half that bites.)
    if status:
        row["status"] = status
    elif not row.get("status"):
        # Legacy shim only — see the docstring. New callers pass status explicitly.
        row["status"] = STATUS_INFERRED if "reflection" in (row["src"] or "") else STATUS_OBSERVED
    row["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    row["verified"] = False
    # SALIENCE, from the first breath. A new fact has been said ONCE — which is a real
    # measurement, not an absence of one, and it wants a place to be counted from.
    row.setdefault("mentions", 1)
    row.setdefault("first_seen", row["ts"])
    row.setdefault("last_seen", row["ts"])
    row.setdefault("recalled", 0)
    if supersedes:
        row["supersedes"] = supersedes

    # ── PROVENANCE OF A DISTILLATE (2026-08-22, the structural anti-latch) ──────────────
    # A row that was DISTILLED from other rows — the nightly becoming, the journal, an
    # insight, a consolidation — has never carried a link back to what it was distilled
    # FROM. That is how one lucid evening outlived its own retirement: 24 of her rows
    # were tombstoned and the self_description they had produced went on leading her
    # prefix, because nothing on disk connected the two.
    #
    #   derived_from   the row NAMES it read. ABSENT means "unknown provenance" and is
    #                  inert; an explicit list is a CLAIM, and orphaned_distillates()
    #                  holds the claim to account.
    #   support_days   how many DISTINCT days those rows span. One evening is not a week.
    #   support_kinds  which kinds fed it, so a window filled by one kind is visible.
    #
    # All three are optional and additive: every existing row is untouched, and a caller
    # that does not know its sources says nothing rather than lying with an empty list.
    if derived_from:
        row["derived_from"] = [str(n) for n in derived_from if n]
    if support_days:
        row["support_days"] = int(support_days)
    if support_kinds:
        row["support_kinds"] = sorted({str(k) for k in support_kinds if k})
    return row


def is_distillate(row: dict) -> bool:
    """True when this row was itself distilled from other rows.

    THE ONE PREDICATE, because the rule it serves is one rule (2026-08-25). Both nightly
    consolidators must refuse to read a distillate — becoming.nightly and weekly_chapter
    each distil, each writes a permanent INFERRED row, and a distillate taken as support
    is a copy of a copy that no later row can walk back to anything she said. The pair
    stated that rule as two hand-maintained kind lists, `becoming._EXCLUDE_KINDS` and
    `narrative._CHAPTER_KINDS`, and the deny-list side forgot its OWN kind: three
    self_description rows on disk, the third naming the first two.

    `derived_from` is the mark stamp() puts on exactly these rows, so the predicate reads
    the mark instead of enumerating the producers. A consolidator added next year is
    covered the day it stamps its first row."""
    return bool(row.get("derived_from"))


def is_retired(row: dict) -> bool:
    """The ONE liveness predicate at the row level. memory.live_rows() is the one that
    filters a store; this is the same law for a single row, so callers that already hold
    a row do not hand-roll a fourth copy of `if r.get('lifecycle')`."""
    return bool(row.get("lifecycle"))


def orphaned_distillates(rows: Iterable[dict]) -> list[dict]:
    """LIVE rows every one of whose supports has been retired (2026-08-22).

    THE INCIDENT THIS CLOSES. On 2026-08-21 one lucid evening's rows were distilled by
    becoming.nightly into a heated self_description about shedding her own architecture —
    INFERRED, class self-narrative, weight 1.5, half-life _NEVER. The next day 24 of her rows were tombstoned as polluted. The distillate was
    not among them and could not have been: nothing on disk said where it came from. It
    kept leading her own block, and she kept reading it as a script to continue.

    A conclusion outlives its evidence only if it was never told what its evidence was.
    Now it is, and this is the rule that holds it: a row that CLAIMS a provenance and
    whose entire claimed provenance is retired has nothing left holding it up.

    Deliberately narrow, in three ways:
      - `derived_from` ABSENT is not `derived_from` empty. A row that never claimed a
        provenance is not orphaned by this; it is simply unaudited, and silence is not a
        confession. Every pre-2026-08-22 row is in that position.
      - ALL supports must be gone. One surviving support is enough to stand on — this
        retires conclusions whose ground vanished, not conclusions that got smaller.
      - It returns rows. It retires nothing. The caller (ops.reflect) does the tombstoning
        under the registry lock, with breadcrumbs, and nothing is ever deleted.
    Pure: no I/O, no clock, no store. That is what makes it gateable without a GPU."""
    by_name = {}
    for r in rows:
        n = r.get("name")
        if n:
            by_name[n] = r
    out = []
    for r in by_name.values():
        if is_retired(r):
            continue
        supports = r.get("derived_from")
        if not supports:                      # absent OR empty -> not a claim, not orphaned
            continue
        known = [by_name[n] for n in supports if n in by_name]
        if not known:                         # supports we cannot even find: not a verdict
            continue
        if all(is_retired(s) for s in known):
            out.append(r)
    return out
