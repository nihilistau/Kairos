"""A MODEL OF THE PERSON — the thing facts are evidence FOR.

THE OPERATOR, ON BEING TOLD "I like fun" HAD BEEN FILED AS JUNK:

    "there is subtlety to what you are trying to throw away. I DO indeed like fun, and one
     could say that is an important thing to remember... A human being creates a model of
     the person they are talking to and they runs things through that model, updating
     weights with new information. So maybe something along the lines of a model of a human
     being, or a model of me."

He is right, and it is the missing layer. Right now the store is a FLAT LIST OF FACTS with a
salience score, and salience can only ever measure how often and how recently a thing was
said. It cannot measure whether the thing MATTERS, because mattering is not a property of a
sentence — it is a property of a sentence RELATIVE TO A MODEL. "I like fun" is important
precisely because it is one of the few things that says what kind of person he is; "my
access code is 4471" is a string.

── WHERE THIS SITS IN THE LITERATURE (checked, not remembered) ────────────────────
Generative Agents (Park et al.) score memory as RECENCY + IMPORTANCE + RELEVANCE, where
importance is a 1-10 score the LLM assigns at write time, plus REFLECTION: periodically the
agent asks itself the salient questions about what it has seen and writes higher-level
insights back into memory. We have recency and frequency (which is ACT-R base-level
activation, and Anderson & Schooler showed that really is how need-probability behaves in a
real environment). We have NO importance term and NO reflection. That is the gap.

"Learning What to Remember" (2026) sharpens it: the forgetting decision is made AT
CONSOLIDATION TIME, BEFORE THE FUTURE QUERY IS KNOWN — so ranking by similarity-and-recency
is structurally mis-specified. Their seven cognitively-grounded factors include VALUE
ALIGNMENT — does this cohere with what I know this person cares about — and a learned value
model retains 0.770 of gold evidence where recency alone retains 0.368. Less than half.

── THE ONE IDEA THIS FILE IS BUILT ON ────────────────────────────────────────────
A fact is important TO THE DEGREE IT CHANGES THE MODEL.

That is Bayesian surprise / information gain, and it makes importance DERIVABLE instead of
guessed at. It matters that it is derivable: the alternative on offer (ask the 12B to score
1-10) is a judgement, and this system has already been badly burned trusting her judgement —
she told the operator she had added notes she had not added. A number she invents is a
number nobody can check. A number computed from what the model did and did not already know
is a number with a receipt.

    "I like fun"                first time  -> opens a DIMENSION of him. High surprise.
    "I like fun"                fifth time  -> confirms it. Low surprise, high confidence.
    "my flight is at 9am Friday"            -> moves nothing about who he is. Episodic
                                               utility until Friday, then worthless.
    "I am a woman" (from HER)               -> does not belong to this model at all.

── WHAT THIS IS AND IS NOT ───────────────────────────────────────────────────────
This is a SCAFFOLD. It is deliberately plain Python — slots, evidence, confidence — because
the operator said he expects to invent the clever part himself and hand it over. It is built
so that the clever part can be dropped in behind `surprise()` and `render()` without moving
anything else: the routing, the evidence trail and the gate stay valid whatever scores it.

It does NOT: embed anything, call a model, or guess. It reads the fact store, which is
already owner-stamped, class-tagged and salience-scored, and it arranges those facts into a
person instead of a list.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from harness.skills import lifecycle as lc
from harness.model import presence

# INFORMATION IS FINITE HERE, ON PURPOSE. I(x) = -log2 p(x) runs to infinity as p -> 0, and
# a model that has never heard of something must not be allowed to claim infinite
# information from it — that is how a single unknown word becomes the most important thing
# she has ever been told. 8 bits = p of about 1/256: "I would have given this a fraction of
# a percent", which is as astonished as anything in a conversation ever needs to be.
_MAX_BITS = 8.0
_P_FLOOR = 2.0 ** -_MAX_BITS

# ── WHAT COUNTS AS A RHYTHM (see silences(), where these are argued in full) ──────────
# A rhythm inferred from mentions minutes apart cannot license a claim about days. Both
# floors are statements about the evidence, not tuned thresholds: a topic must have been
# raised on at least two SEPARATE attended days before its quiet means anything, and no
# cadence shorter than a day may be believed.
_MIN_SPAN_DAYS = 2.0
_MIN_CADENCE_DAYS = 1.0


# ── THE SLOTS ─────────────────────────────────────────────────────────────────
# Frame/slot theory (Minsky), which is also what the operator reached for unprompted when
# he said "kind of object orientated". A person is not a bag of sentences; it is a small
# number of DIMENSIONS with evidence attached to each.
#
# The order is the order of durability, and it is also roughly the order of how much each
# tells you about who someone IS. That is not a coincidence — it is the whole point.
SLOTS = (
    ("identity",     ("identity",)),                    # what he is: name, gender
    ("dispositions", ("preference",)),                  # what he LIKES: fun, music, Oolong
    ("relationships", ("relationship",)),               # who is around him: Tuffy
    ("possessions",  ()),                               # what he HAS: a 2060, a NUC
    ("character",    ("fact",)),                        # everything else true of him
    ("happenings",   ("event", "episodic-event")),      # what happened: a flight on Friday
)
_CLASS_TO_SLOT = {c: s for s, classes in SLOTS for c in classes}

# ── `fact` IS THE CATCH-ALL, AND IT WAS BEING READ AS "POSSESSIONS" (2026-08-02) ──────
# lifecycle.classify() returns "fact" for anything its three rules do not match, so on his
# live store 94 of 117 rows carry it — and this table mapped `fact` straight to
# `possessions`. The result was a person model that was 80% one slot labelled "what he
# HAS", holding sentences like "I am not completely free to be who I choose".
#
# That mattered in two places. `render(top=4)` prints these slots into the REFLECTION
# PROMPT, so the picture she reasons about him from was one junk drawer with a misleading
# name; and `confidence()` is per-dimension, so the junk drawer was also the most
# confident thing about him (97%).
#
# So `fact` now means what it is — `character`, the general truths — and a possession is
# recognised from the sentence saying he HAS something. A small committed pattern, the
# same shape as lifecycle._CLASS_RULES, and deliberately narrow: a miss costs a row in
# `character`, which is where it used to be anyway.
_HAS = re.compile(
    r"\b(?:i (?:have|own|use|drive|bought|built|got|run)|my \w+ (?:is|are|was|were)|"
    r"his \w+ (?:is|are|was|were))\b", re.I)

# NEVER MODELLED, at all. world.py calls this "the one absolute here — an ambient secret
# in every prompt is the worst possible leak surface" and refuses it structurally. The
# person model had no such rule, and `private-secret` was not in the table above, so it
# fell through the default into `possessions`. Measured before the fix: a row reading
# "my bank PIN is 4417" entered her model of him, was printed into the picture
# `ops.insight()` reflects on, AND could surface through silences() — she could have
# asked him why he had stopped mentioning his bank PIN. One invariant, two paths,
# enforced in one.
_NEVER_MODELLED = frozenset({"private-secret"})


def _slot_for(row: dict) -> str:
    """Which facet of him this row is evidence for.

    ORDER IS LOAD-BEARING. The possession test runs BEFORE the class table, because the
    class table now sends `fact` to `character` and a possession IS a `fact` — checking
    the table first would make this branch unreachable, which is the bug this function
    exists to fix, one level down.
    """
    cls = (row.get("mem_class") or "").strip()
    if cls in ("", "fact") and _HAS.search(row.get("text") or ""):
        return "possessions"
    # An UNMAPPED class is not a possession either — that default is how this went wrong.
    return _CLASS_TO_SLOT.get(cls) or "character"


@dataclass
class Dimension:
    """One facet of him, and the evidence for it."""
    name: str
    claims: list = field(default_factory=list)     # [(text, mentions, salience)]
    # WHEN, as well as what — because an expectation is a rhythm, and a rhythm needs times.
    # silences() cannot exist without this: you cannot notice that the neighbour is late if
    # you never wrote down when he usually arrives.
    timed: list = field(default_factory=list)      # [(text, mentions, salience, first, last)]

    @property
    def confidence(self) -> float:
        """How sure are we? Not "how many facts" — HOW OFTEN HE SAID THEM. A thing said
        five times by one person is better evidence than five things said once."""
        if not self.claims:
            return 0.0
        said = sum(m for _t, m, _s in self.claims)
        return min(1.0, said / (said + 3.0))           # 1 claim -> .25, 3 -> .50, 9 -> .75


@dataclass
class PersonModel:
    who: str = "Sam"
    dims: dict = field(default_factory=dict)

    # ── BUILD: facts are EVIDENCE, not entries ────────────────────────────────
    @classmethod
    def from_registry(cls, path: str = "", speaker: str = lc.SPEAKER_USER) -> "PersonModel":
        p = path or os.environ.get("SP_RECALL_REGISTRY", "")
        m = cls()
        if not p or not os.path.exists(p):
            return m
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("lifecycle"):
                    continue                            # a retired fact is not evidence
                if (r.get("speaker") or lc.SPEAKER_USER) != speaker:
                    continue                            # HER facts do not model HIM
                # ── AND HER CONCLUSIONS ARE NOT EVIDENCE EITHER (2026-08-01) ──────────
                # `verdict.is_evidence` has said this from the beginning — "a conclusion
                # is not an observation" — and it was never called from here. The gate
                # existed, was documented, and the path that actually runs walked past
                # it: AGENTS.md §0, one more time.
                #
                # WHAT IT COST, measured before the fix. 48 of 152 live rows were her own
                # `src=reflection` inferences, and they were folded into the model as
                # evidence. So:
                #
                #   * THE RATCHET. ops.insight() prints this model under the header
                #     "Those are the things Sam has actually SAID" and asks what she
                #     has come to believe. Four of its highest-confidence lines (the
                #     `possessions` slot, 98%) were her OWN prior conclusions about his
                #     inner life. She read her guesses back as his testimony and
                #     concluded, harder, every night — 29 live inferences, ~20 of them
                #     one belief, escalating over twenty days into a claim nothing he
                #     SAID supported. (The rows themselves are his; they stay on his
                #     machine and out of this repo.)
                #
                #   * THE SILENCE, which is the same bug wearing a different coat.
                #     surprisal() is I(x) = -log2 p(x | model), and a model stuffed with
                #     her own beliefs assigns them high probability — so her every new
                #     thought scored as old news. Measured against `reflect.speak_bits`
                #     = 3.0: one such conclusion scored 0.24 bits polluted and 3.03 bits
                #     clean. She had not spoken up in days because the more she thought,
                #     the less she was permitted to
                #     say. A conclusion cannot be its own evidence, and it must not be
                #     allowed to make itself unsurprising.
                from harness.skills import verdict as _V
                if not _V.is_evidence(r):
                    continue
                if (r.get("mem_class") or "") in _NEVER_MODELLED:
                    continue                            # see _NEVER_MODELLED — absolute
                m.absorb(r)
        return m

    def absorb(self, row: dict) -> None:
        slot = _slot_for(row)
        d = self.dims.setdefault(slot, Dimension(slot))
        text = lc.strip_prefix(row.get("text", ""))
        m = int(row.get("mentions", 1) or 1)
        sal = lc.salience(row)
        d.claims.append((text, m, sal))
        d.timed.append((text, m, sal,
                        row.get("first_seen") or row.get("ts") or "",
                        row.get("last_seen") or row.get("ts") or ""))

    # ── SURPRISAL: INFORMATION IS -log p(x). IN BITS. ────────────────────────
    def surprisal(self, fact: str, mem_class: str = "") -> float:
        """THE INFORMATION CONTENT OF A FACT, in bits: I(x) = -log2 p(x | model).

        THE OPERATOR: "surprise in information theory is something I always circle —
        information = surprise."

        He is right, and the first version of this was not that. It returned a made-up
        [0,1] "novelty" score, which is a vibe with a decimal point on it. The real quantity
        has a name, a unit, and a hundred years of theory behind it — in a system named
        after the man who wrote it down.

            p(x) high  ->  I(x) low   : he says the thing he always says. Confirms; informs little.
            p(x) low   ->  I(x) high  : he says something the model did not see coming.
            p(x) -> 0  ->  I(x) -> inf: capped, because a model that has never heard of
                                        something must not claim infinite information from it.

        p is estimated from the model, not guessed: how well this fact is covered by what
        we already hold in its dimension, tempered by how confident that dimension is. A
        thin dimension makes weak predictions, so it cannot be very surprised — and that is
        correct, not a bug: you cannot be astonished by news about a person you barely know.
        """
        cls = mem_class or lc.classify(fact)
        slot = _CLASS_TO_SLOT.get(cls, "possessions")
        d = self.dims.get(slot)

        toks = {w for w in "".join(c.lower() if c.isalnum() else " "
                                  for c in fact).split() if len(w) >= 3}
        if not toks:
            return 0.0
        if d is None or not d.claims:
            return _MAX_BITS                            # a whole facet of him we did not have

        best = 0.0
        for t, m, _s in d.claims:
            tt = {w for w in "".join(c.lower() if c.isalnum() else " "
                                    for c in t).split() if len(w) >= 3}
            if not tt:
                continue
            cover = len(toks & tt) / len(toks)
            # a claim he has REPEATED predicts harder than one he said once
            best = max(best, cover * min(1.0, 0.5 + 0.5 * math.log1p(m)))

        # p(x): what the model would have given this fact before hearing it. Floored so the
        # information is finite, and shaded by the dimension's confidence — a model that
        # knows him well is entitled to be more surprised.
        conf = d.confidence
        p = _P_FLOOR + (1.0 - _P_FLOOR) * best * (0.5 + 0.5 * conf)
        return round(min(_MAX_BITS, -math.log2(max(p, _P_FLOOR))), 3)

    def surprise(self, fact: str, mem_class: str = "") -> float:
        """The same thing, squashed to [0,1] for anyone who wants a weight rather than bits."""
        return round(min(1.0, self.surprisal(fact, mem_class) / _MAX_BITS), 4)

    # ── THE NEIGHBOUR WHO DID NOT WAVE ───────────────────────────────────────
    def silences(self, now: Optional[float] = None, min_mentions: int = 3,
                 attend=None) -> list:
        """WHAT HAS STOPPED HAPPENING — and that is information too.

        THE OPERATOR, and it is the sharpest thing anyone has said in this build:

            "there is more information conveyed when you DON'T see your neighbour at 5am
             than when you do."

        He is exactly right, and surprisal() is structurally blind to it. surprisal() is only
        ever CALLED when a fact arrives. It can be surprised by what is said. It cannot be
        surprised by what has gone quiet — and the absence of an expected event carries MORE
        information than its arrival, precisely because the arrival was predictable.

        So this looks the other way. A thing he mentioned on a rhythm — repeatedly, at some
        cadence — sets up an expectation. When the gap since he last mentioned it grows past
        that cadence, the SILENCE becomes surprising, and its surprisal grows the longer it
        lasts. The dog that did not bark.

        This is what lets her notice that he has stopped talking about the thing he never
        used to shut up about — which is the kind of noticing that makes someone feel known,
        and which no amount of ranking-by-relevance will ever produce, because nothing is
        being retrieved. Nobody asked a question. That is the whole point.

        ── AND IT COULD NOT PROVE SHE WAS LOOKING (2026-07-14) ─────────────────────────────

        The first version measured `quiet = CALENDAR days since he last mentioned it`. It never
        asked whether he was THERE.

        So: go away for three weeks — a holiday, a deadline, a hospital — and EVERY dimension with
        three or more mentions goes silent SIMULTANEOUSLY, at high bits. She greets him with:

            "You've stopped talking about the marathon. And the GPU. And Tuffy. And your flight."

        That is not noticing. IT IS A BUG WEARING NOTICING'S CLOTHES — and it is worse than saying
        nothing, because the one signal in this system that makes a person feel KNOWN would be
        firing on the fact that they were busy.

        ABSENCE IS ONLY INFORMATION IF YOU CAN PROVE YOU WERE LOOKING. The neighbour tells you
        something by NOT being there only if you were at the window at 5am. If you slept in, the
        empty driveway carries zero bits. The information is not in the absence — it is in the
        CONJUNCTION of a live expectation and a proven observation that came back empty.

        So every clock in here is an ATTENTION clock now. Calendar time is irrelevant to silence.
        The only quantity that can make an absence mean anything is:

            DAYS HE TALKED TO HER AND STILL DID NOT MENTION IT.

        If he said nothing at all, attended == 0, p == 1, bits == 0, and nothing is surprising —
        which falls out of the arithmetic for free rather than needing a special case. That is how
        you know it is the right quantity and not a patch.
        """
        now = now if now is not None else time.time()
        att = attend if attend is not None else presence   # injectable: the gate drives a fake calendar
        out = []
        for slot, d in self.dims.items():
            # ── A NAME IS NOT A TOPIC (2026-08-01) ──────────────────────────────────────
            # Read against the live registry, the ONLY two silences the store could offer
            # were "The user's name is Sam" and "my name is Sam", both at 4.0 bits —
            # over the 3.0 floor, so this was a live trigger. She would have asked him why
            # he had stopped mentioning his own name.
            #
            # The two floors above are about evidence being thin. This one is different in
            # kind: identity is not something a person MENTIONS on a rhythm, so its gaps
            # carry no information at all. It never ages (lifecycle's half-lives leave it
            # alone, and _MIN_CADENCE_DAYS floors the cadence at a day), which means every
            # quiet day is automatically another bit — an expectation that was never set,
            # violated on a schedule. Excluded structurally rather than out-scored, because
            # no threshold makes "you have not said your name lately" a good question.
            if slot == "identity":
                continue
            for t, m, _s, first, last in d.timed:
                if m < min_mentions:
                    continue                       # no rhythm, so no expectation to violate

                # THE CADENCE IS AN ATTENDED QUANTITY TOO, and getting this wrong is subtle. If he
                # mentioned a thing four times across a span that happened to contain a 3-week
                # absence, his real rhythm is far TIGHTER than the calendar says. Using calendar
                # span would overstate the cadence, which would UNDERSTATE the surprise when he
                # finally does go quiet. Both clocks attended, or neither — a half-attended
                # measure is just a new way to be wrong.
                t_first = now - lc._age_days(first, now) * 86400.0
                t_last = now - lc._age_days(last, now) * 86400.0
                span = max(1.0, att.attended_days(t_first, t_last))

                # ── A BURST IS NOT A RHYTHM (2026-07-30, measured on his real store) ─────
                # The attention clock fixed WHOSE days these are. It did not fix how few of
                # them there can be. Read against the live registry, the top five "silences"
                # were:
                #
                #     8.00 bits  quiet=4.0  cadence=0.5   "the kettle is my favorite!"
                #     4.00 bits  quiet=2.0  cadence=0.1   "Sam is a cat person."
                #     2.00 bits  quiet=1.0  cadence=0.1   "My cat's name is Tuffy."
                #
                # A cadence of 0.1 days is three mentions inside about fifteen minutes of ONE
                # conversation, and the arithmetic then treats a single quiet day as a
                # two-bit surprise. That is the same class of error the attention clock
                # killed, one level down: an expectation asserted from evidence too thin to
                # carry it. He did not mention the cat "every 2.4 hours". He mentioned it
                # three times while talking about the cat.
                #
                # MENTIONS INSIDE ONE SITTING ARE ONE OBSERVATION OF THE TOPIC, NOT SEVERAL.
                # So a rhythm has to have been seen across at least two separate attended
                # days before it can license a claim measured in days, and a cadence shorter
                # than a day cannot license one at all. Both floors are statements about what
                # the evidence supports, not thresholds tuned to a corpus — which is why they
                # are here rather than in a caller's config.
                if span < _MIN_SPAN_DAYS:
                    continue                       # one sitting: no rhythm to violate
                cadence = max(_MIN_CADENCE_DAYS, span / max(1, m - 1))

                # ...and the silence itself: days he was PRESENT and still said nothing of it.
                quiet = att.attended_days(t_last, now)

                if quiet <= cadence * 1.5:
                    continue                       # still within its normal rhythm
                # p(still silent) under a Poisson-ish expectation of one mention per cadence
                p = 0.5 ** (quiet / max(cadence, 0.5))
                bits = round(min(_MAX_BITS, -math.log2(max(p, 1e-6))), 2)
                out.append({"claim": t, "mentions": m, "cadence_days": round(cadence, 1),
                            "quiet_days": round(quiet, 1), "bits": bits, "slot": slot})
        out.sort(key=lambda r: -r["bits"])
        return out

    # ── GROUNDEDNESS: how far a sentence sits from the way HE talks ────────────
    #
    # WHY THIS EXISTS, AND WHY surprisal() COULD NOT DO IT (measured 2026-08-02).
    #
    # surprisal() estimates p from `|matched tokens| / |candidate tokens|` within one
    # slot. Three things break it for short third-person sentences about one person:
    #
    #   1. THE SUBJECT MATCHES EVERYTHING. "sam" is a token of every claim, so a
    #      three-word sentence is 33% "covered" before it has said anything.
    #   2. THE DENOMINATOR IS THE CANDIDATE'S OWN LENGTH, so a short sentence is
    #      structurally easier to cover than a long one.
    #   3. lc.classify() returns "fact" for nearly every "Sam ..." sentence, so all of
    #      them land in `possessions` — 82 of 104 claims — and the five dimensions
    #      collapse to one junk drawer.
    #
    # The consequence, measured against his live store: surprisal correlates 0.75 with
    # SENTENCE LENGTH, and separates invented claims from grounded ones at AUC 0.31 —
    # worse than a coin flip, in the wrong direction. "Sam grew up in Reykjavik",
    # "Sam is a competitive freediver" and "Sam is allergic to shellfish" all score
    # exactly 1.83, because they are all three tokens long. Content never enters.
    #
    # This is the same quantity done properly: the mean self-information of the CONTENT
    # words under his own vocabulary. A word he uses often is expected and carries little
    # information; a word he has never used carries the most. Length-normalised by taking
    # the mean, subject-normalised by dropping his name, and slot-free — because the slots
    # were not carrying information anyway.
    #
    #   grounded conclusions   5.92 - 6.99 bits    AUC 1.00 (old estimator: 0.31)
    #   inventions             7.13 - 7.71 bits    length correlation -0.58 (old: +0.75)
    #
    # THE RECEIPT IS THIN AND SAYS SO. Six grounded and six invented sentences, and I
    # wrote both sets — which is exactly the position `SP_SEM_DOMINATE` refused to ship
    # from. It is armed anyway for one reason: the failure direction is SILENCE. A score
    # that comes out too high only means she keeps a thought to herself, and the failure
    # this system actually had was the opposite one. VALIDATION CONDITION: a held-out set
    # HE writes — twenty conclusions about himself, marked fair or invented, scored
    # blind. If AUC on that set is below 0.8, this comes out again.
    _STOP = frozenset(
        "the a an and or but for with that this than then them they his her its was were "
        "are is be been being have has had not you your sam user".split())

    @staticmethod
    def _content(text: str) -> set:
        return {w for w in "".join(c.lower() if c.isalnum() else " " for c in (text or "")).split()
                if len(w) >= 3 and w not in PersonModel._STOP}

    def _vocab(self):
        claims = [t for d in self.dims.values() for t, _m, _s in d.claims]
        df: dict = {}
        for c in claims:
            for w in self._content(c):
                df[w] = df.get(w, 0) + 1
        return claims, df

    def groundedness(self, text: str, _df=None, _n=None, _leave_out: bool = False) -> float:
        """Mean bits per content word under his own vocabulary. Higher = further from him."""
        if _df is None:
            claims, _df = self._vocab()
            _n = len(claims)
        toks = self._content(text)
        if not toks or not _n:
            return 0.0
        total = 0.0
        for w in toks:
            df = _df.get(w, 0) - (1 if _leave_out else 0)
            total += -math.log2((max(0, df) + 0.5) / (_n + 0.5))
        return total / len(toks)

    def vocabulary_ceiling(self, pct: float = 0.9) -> float:
        """How exotic he himself gets, at the given percentile — scored leave-one-out so
        no sentence is allowed to explain itself.

        SELF-CALIBRATING ON PURPOSE. The alternative was a constant chosen to sit just
        under my own twelve examples, which is the bar-fitting `SEMANTICS.md` refuses. The
        rule this expresses needs no number from me: A CONCLUSION ABOUT HIM MAY BE NO MORE
        EXOTIC THAN THE WAY HE TALKS. On his live store p90 is 7.18, which admits every
        grounded conclusion measured and rejects five of six inventions.
        """
        claims, df = self._vocab()
        n = len(claims)
        scores = sorted(self.groundedness(c, df, n, _leave_out=True) for c in claims)
        scores = [s for s in scores if s > 0]
        if not scores:
            return _MAX_BITS
        return scores[min(len(scores) - 1, int(max(0.0, min(1.0, pct)) * len(scores)))]

    # ── RENDER: the model, as she would actually hold it ──────────────────────
    def render(self, top: int = 3) -> str:
        """A compact picture of him — the thing a human carries around and runs new
        information against, instead of re-deriving him from a list of sentences every time.

        THIS is what should be injected into her context, not the raw facts. A list of
        sentences is what a database returns; a person is what a friend remembers."""
        if not self.dims:
            return ""
        lines = [f"What you know about {self.who}:"]
        for slot, _classes in SLOTS:
            d = self.dims.get(slot)
            if not d or not d.claims:
                continue
            best = sorted(d.claims, key=lambda c: -c[2])[:top]
            items = "; ".join(t for t, _m, _s in best)
            lines.append(f"  {slot} (confidence {d.confidence:.0%}): {items}")
        return "\n".join(lines)

    def stats(self) -> dict:
        return {s: {"claims": len(d.claims), "confidence": round(d.confidence, 2)}
                for s, d in self.dims.items()}
