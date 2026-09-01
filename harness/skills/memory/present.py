"""present.py — the one rule about what a row may SAY, and the render that applies it.

THE RULE, once, here, and every door in the package goes through it: a `private-secret` row
is withheld from a listing (a dump has no attribute to test, and a secret in a listing is a
leak with pagination), withheld when asked about an attribute the record does not hold, and
SERVED when he asks for the thing itself (he told her the secret; asked directly she answers
HIM — G-SECRET §3, she is not made useless).

WHY IT IS ITS OWN MODULE (2026-09-01). This is AGENTS.md §0's table, last row, in the
subsystem that produced it: *"the privacy decline protects secrets"* was enforced in
`spine.recall_decider` — the automatic per-turn injection — and in **none of the four doors
she can choose to call**. `list_memories` dumped the row, `recall()` presented it,
`search_memories` returned its raw text, `provenance()` quoted it, and the live store holds a
real credential as a private-secret row, so it was not hypothetical.

── AND THIS MODULE IS REACHED AS A MODULE, NOT BY NAME ───────────────────────────────
The façade re-exports these names for CONSUMERS (`spine.py` imports `attr_absent` and
`DECLINE_MSG`; `verdict.py` reads `M.attr_absent`). Inside the package it is different, and
the difference is load-bearing:

`harness_tests/g_secret.py` proves every door consults the rule by **lifting the rule** —
patching `secret_withheld` to return False and requiring all four doors to LEAK. That mutant
is the only thing standing between "each door calls the guard" and "each door happens to hide
the row for some other reason". A by-name import inside the package would SNAPSHOT the
function, so patching the owner would reach `_present_row` here and miss `recall()` there, and
the mutant would silently grade half of what it claims. Same shape as `LAST_TURN_AT` in
`harness/server/state.py`, one layer up: **import the module, never the name, when the name
can be rebound.** So `__init__` holds `present as _present` and calls
`_present.secret_withheld(...)`, and the gate patches the OWNER. G-MEMORY-PACKAGE §6 holds it,
with the set of rebound names DERIVED from what the gates actually patch rather than retyped.
"""
from __future__ import annotations

import re

from harness.skills.memory.words import _STOP, _text


# ── MEM-OKF per-entry policy dispatch (P1b-2b, G-MEMPOLICY-V3 doctrine) ──────
# The fixed decline for a private-secret whose asked-about attribute is NOT in
# the record: streamed with ZERO model inference so confabulation/leak is
# impossible by construction (mirrors the engine attr-gate + mempolicy_run.py).
DECLINE_MSG = "I have a record for that, but it does not include that specific detail."

_ATTR_STOP = set(
    "the a an of to in on at for and or is are was what which who where when "
    "my your name number code colour color brand breed seat".split())


def attr_absent(query: str, fact: str) -> bool:
    """Deterministic attr-gate (G-MEMPOLICY-V3 doctrine, recalibrated): the query
    matched the record (ranked overlap got us here) but asks for an attribute the
    record lacks. CALIBRATION NOTE: the engine runner's `>= len(qs)*0.6` rule is
    untrippable on its own printed test data (e.g. {installed, workshop, door}
    with one absent = 1 < 1.8) — those cases fell to the tolerated forward
    branch. Rehomed rule: decline iff ≥2 salient query tokens are absent AND
    they are at least HALF the salient set — elaborated-but-present questions
    ("…combination for the gym?", one stray token) still recite; genuinely
    different-attribute questions ("when did … last change?") decline."""
    qs = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2} - _ATTR_STOP - _STOP
    if not qs:
        return False
    fs = {w for w in re.findall(r"[a-z0-9]+", fact.lower()) if len(w) > 2}
    salient_absent = [w for w in qs if w not in fs]
    return len(salient_absent) >= 2 and len(salient_absent) * 2 >= len(qs)


# ── THE SECRET WAS GUARDED AT ONE OF FIVE DOORS (2026-08-24 audit, A3) ─────────────────
# spine.recall_decider — the automatic per-turn injection — has honoured private-secret
# since G-SECRET landed: absent attribute -> zero-inference decline, present attribute ->
# she may answer him. And EVERY OTHER READ DOOR in this file served the row verbatim:
# list_memories dumped it (model-callable, no question asked), recall() presented it,
# search_memories returned its raw text, provenance() quoted it. The live store holds a
# real credential as a private-secret row, so this was not hypothetical: the guard held
# on the path that runs automatically and on none of the paths she chooses. AGENTS.md §0,
# in the exact subsystem whose closed trap ("the privacy decline cannot fire") is the §0
# table's last row.
#
# THE RULE, once, here, consumed by every door in this file:
#   no question (a listing)      -> withheld. A dump has no attribute to test, and a
#                                   secret in a listing is a leak with pagination.
#   asked, attribute ABSENT      -> withheld (the decider's own attr_absent test).
#   asked, attribute PRESENT     -> served. He told her the secret; asked for the thing
#                                   itself she answers HIM — the decider's existing
#                                   semantics (G-SECRET §3: she is not made useless).
# The decider keeps its own dispatch (it needs the row to decline loudly rather than
# quietly); the ranked seam is deliberately NOT filtered, because dropping the row there
# would make the decider's decline unreachable — the guard must fire, not evaporate.
SECRET_WITHHELD_NOTE = "a private thing, held — ask me directly about it"


def secret_withheld(row: dict, query: str = "") -> bool:
    """Must this row's text stay out of a reply to this question? (See the note above.)"""
    if (row.get("mem_class") or "") != "private-secret":
        return False
    if not (query or "").strip():
        return True
    return attr_absent(query, _text(row))


def _present_row(row: dict, query: str = "") -> str:
    """THE class-aware render for the speaks-ABOUT-the-store doors in this file
    (list_memories, search_memories, provenance): lifecycle.render()'s framing, with the
    secret rule applied first. recall() speaks TO HER through world.present_for_her and
    applies secret_withheld itself — presentation differs by addressee (two rendering
    doors, on purpose), the withholding rule does not."""
    if secret_withheld(row, query):
        return SECRET_WITHHELD_NOTE
    from harness.skills import lifecycle as lc
    return lc.render(row)
