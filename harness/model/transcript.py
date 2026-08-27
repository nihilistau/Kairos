"""HIS TURNS, read from the day transcripts — the model layer's door onto the record.

WHY THIS EXISTS AS A MODULE. `person.silences()` needs to know when he last SAID a thing,
which the registry cannot answer (dedup collapses restatements, so a claim's row goes stale
while the behaviour continues — see the note above `_STOPWORDS` in person.py). The record
that can answer it is the day transcript.

Reading it inline in person.py would have made a THIRD private parser for one store —
`server/app.py::_read_day_transcript` and `sidecar/archive.py::_sources` are the other two —
and `G-PERSON-SLOTS` says exactly why that is refused: "a second JSONL parser is a second
policy." Its malformed-line handling, its synthetic-row policy and its timestamp units could
each drift from the others, silently, and the drift would show up as a wrong answer about
him rather than as an error.

So this is the shared door for the MODEL layer. It deliberately does not import the server:
`app.py` owns the writer and the quarantine policy, and migrating it here is a separate
change with its own risk — it is on the ledger, not smuggled into this one.

WHAT IT KNOWS THAT A NAIVE READER DOES NOT
  * `at` is epoch MILLISECONDS here. `speech.jsonl` is ISO-8601 and the registry is ISO with
    a literal Z. Mixing them has cost this repo two wrong analyses in one session.
  * `synthetic` rows are turns HE NEVER TYPED (app.py quarantines them rather than deleting
    them). They must never count as him having said something.
  * A row that cannot be placed in time cannot be evidence about time, so it is skipped
    rather than guessed at.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

# One transcript day is ~100 KB. The window is read once per call and reduced by the caller,
# so this bounds the read rather than the arithmetic.
DEFAULT_DAYS = 45

_WORD = re.compile(r"[a-z']+")

# Function words carry no topic. Deliberately short and general — this is not a sentiment
# lexicon or a phrase list, both of which are "a guard whose reach is a list somebody wrote
# once". Removing a word from here can only make corroboration STRICTER (fewer refutations).
STOPWORDS = frozenset("""
a an and are as at be been but by do does did for from had has have he her him his i if in
is it its me my no not of on or our she so than that the their them then there these they
this to too us was we were what when which who will with you your it's i'm don't
""".split())


def content_words(text: str) -> set:
    """The words a sentence is ABOUT: lowercased, function words dropped, possessives bare."""
    out = set()
    for w in _WORD.findall((text or "").lower()):
        w = w.strip("'")
        if len(w) > 2 and w not in STOPWORDS:
            out.add(w)
    return out


def _dir(registry: str = "") -> str:
    """The transcripts directory beside the registry — the resolution speechlog also uses."""
    reg = registry or os.environ.get("SP_RECALL_REGISTRY", "")
    return os.path.join(os.path.dirname(reg), "transcripts") if reg else ""


def his_turns(registry: str = "", days: int = DEFAULT_DAYS) -> Optional[list]:
    """[(epoch_seconds, content-words)] for each of HIS turns, NEWEST FIRST.

    Returns None — not [] — when the store cannot be read at all. The distinction is
    load-bearing for the caller: an empty list means "he said nothing", while None means
    "there is no record to consult", and only the second one may not license a conclusion.
    """
    d = _dir(registry)
    if not d or not os.path.isdir(d):
        return None
    try:
        names = sorted(n for n in os.listdir(d) if n.endswith(".jsonl"))[-days:]
    except OSError:
        return None
    out = []
    for n in names:
        try:
            with open(os.path.join(d, n), encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue        # one malformed line is not a reason to go blind
                    if row.get("role") != "user" or row.get("synthetic"):
                        continue
                    at = row.get("at")
                    if not isinstance(at, (int, float)):
                        continue        # unplaceable in time; not evidence about time
                    out.append((float(at) / 1000.0, content_words(row.get("content") or "")))
        except OSError:
            return None
    out.sort(key=lambda p: -p[0])
    return out


def spoken_since(turns: list) -> list:
    """Suffix-unions of `turns` (newest first): index i = every word used at or after i."""
    acc, run = [], set()
    for _t, words in turns:
        run = run | words
        acc.append(run)
    return acc


def said_since_fn(registry: str = "", days: int = DEFAULT_DAYS):
    """A callable `(epoch) -> set(words he used at or after it)`, or None if unreadable.

    Built once per caller so that per-claim corroboration is a bisect and a set lookup
    rather than a re-read of the corpus.
    """
    turns = his_turns(registry, days)
    if turns is None:
        return None
    stamps = [t for t, _w in turns]
    unions = spoken_since(turns)

    def said_since(t: float) -> set:
        import bisect
        # turns are NEWEST FIRST, so the words spoken at or after `t` are the suffix-union
        # at the last index whose stamp is still greater than t.
        i = bisect.bisect_left([-s for s in stamps], -t)
        return unions[i - 1] if i else set()

    return said_since
