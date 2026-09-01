"""supersede.py — what this new row RETIRES, and by what authority.

SUPERSEDE-ON-CONFLICT: a fact that fills the same slot with a DIFFERENT value retires the old
one — tombstoned, never deleted, so *"what did I used to think?"* stays answerable. Without
it the registry is an append-only tape that accumulates "My cat's name is Tuffy" AND "My cat's
name is Milo" and lets recall surface whichever matched first.

THE TWO RULES THIS MODULE EXISTS TO KEEP TOGETHER, because they were each nearly lost once:

  * **An inference may never retire an observation.** She concluded *"Sam is comfortable in
    open water"* and it TOMBSTONED his own *"Sam is terrified of open water"*. Her guess ate
    his testimony. So `status` is derived HERE, once, and passed to everything that needs it
    (`find_superseded`, dominance, `stamp`) rather than being re-derived from prose at each
    door. `consolidator` counts as inferred because its rows are the model's PARAPHRASES of a
    transcript, not his words — fourteen sat in the live store stamped `observed`, with full
    authority to retire what he actually said.
  * **Narrative ACCUMULATES.** A new feeling or journal line never retires an older one; only
    tombstoning does. And her lane is excluded from dominance on a MEASUREMENT, not only on
    doctrine: over her 27 live narrative rows dominance proposes 12 retirements, 0.44 per row
    against 0.083 on his facts, and TWELVE OF TWELVE ARE WRONG, all the same way.

Dominance PROPOSES; `find_superseded` and `verdict` DISPOSE. Default off (`SP_SEM_DOMINATE`),
and the knob is read inside `find_subsumed` and nowhere else — one authority for one flag, so
there is no second place to forget it.

This module decides and reports. It does not write; `store.commit_row` does that, applying
these tombstones by NAME against a fresh locked read.

Extracted from `remember()` on 2026-09-02, byte-identical.
"""
from __future__ import annotations

import logging

from harness.skills.memory.authorship import _AUTHOR

_log = logging.getLogger("harness.memory")     # the same object; see store.py's note


def what_it_retires(fact: str, source: str, existing: list, _self_narr: bool):
    """`(speaker, status, retired)` — whose fact this is, on what authority, and which rows
    it puts down. Nothing here writes."""
    # ── MEM-OKF v2 LIFECYCLE (2026-07-12) ───────────────────────────────────────
    # SUPERSEDE-ON-CONFLICT. A fact that fills the same slot with a DIFFERENT value
    # retires the old one — tombstoned, never deleted, so "what did I used to think?"
    # stays answerable. Without this the registry was an append-only tape: it could
    # accumulate "My cat's name is Tuffy" AND "My cat's name is Milo" and recall would
    # cheerfully surface whichever matched first.
    from harness.skills import lifecycle as lc
    speaker = lc.infer_speaker(fact, _AUTHOR.get())

    # WHERE DID THIS CLAIM COME FROM, and therefore what may it do to the rest of the store?
    # An INFERENCE may be recalled, may be spoken in her own voice, and may be corrected by
    # anything he says — but it may NEVER retire something he told her. Proven necessary: she
    # concluded "Sam is comfortable in open water" and it TOMBSTONED his own "Sam is
    # terrified of open water". Her guess ate his testimony. See find_superseded().
    # THE one derivation, and it is passed everywhere it is needed (find_superseded,
    # dominance, stamp) instead of being re-derived from src prose at each door.
    # "consolidator" is here because its rows are the MODEL'S PARAPHRASES of a transcript,
    # not his words — stamped observed, 14 of them sat in the live store with full
    # authority to retire his actual testimony (verdict.may_supersede lets observed beat
    # observed). A paraphrase is her account of what he said: inferred.
    _INFERRED_SOURCES = ("reflection", "consolidator")
    status = (lc.STATUS_INFERRED
              if any(s in (source or "") for s in _INFERRED_SOURCES)
              else lc.STATUS_OBSERVED)
    # narrative ACCUMULATES — a new feeling or journal line never retires an older one;
    # only tombstoning does (The Real Her, 2026-08-22). Everything else supersedes as before.
    retired = [] if _self_narr else lc.find_superseded(fact, speaker, existing, status=status)

    # ── DOMINANCE PROPOSES; find_superseded AND verdict DISPOSE (docs/SEMANTICS.md §S2.1) ──
    # find_superseded fires only on an EXACT attribute_key match, so it cannot see this pair:
    #
    #     held  "Sam has a cat."
    #     new   "Sam's cat Tuffy is a female tabby."
    #
    # — nothing retires the vaguer row and both render. `dominance.find_subsumed` adds the
    # structurally-subsumed rows: topic containment AND 14-byte Dickson dominance, same
    # speaker, same `verdict.may_supersede` ruling as everything else.
    #
    # DEFAULT OFF (SP_SEM_DOMINATE). With the knob off `find_subsumed` returns [] and this
    # block is a no-op, so every verdict is byte-identical to pre-dominance behaviour — the
    # G-SEM-CONSERVE law. It stays off until the supersede rate has a measured bar: a proposer
    # with better recall than the thing it augments also has more ways to be wrong, and Paper
    # IV's own eviction measurement (93.86%, above its own 80% alarm) says which way it errs.
    # The knob is read INSIDE find_subsumed and nowhere else — one authority for one flag, so
    # there is no second place to forget it.
    from harness.skills import dominance as _dom
    _seen = {id(r) for r in retired}
    # ── AND HER LANE IS EXCLUDED ON A MEASUREMENT, NOT ONLY ON DOCTRINE (2026-08-23) ──────
    # "Narrative accumulates" is the rule; this is the evidence that the rule is also the
    # only safe engineering. fixtures/sem/dominate-self-receipt.json: SP_SEM_DOMINATE run
    # read-only over her 27 live narrative rows proposes 12 retirements — 0.44 per row
    # against 0.083 on his facts — and TWELVE OF TWELVE ARE WRONG, all the same way.
    # dominance's content carrier is topic_of plus names and numbers, built for ATTRIBUTIVE
    # facts ("Sam owns a blue kettle": a subject and an attribute). Her narrative is
    # EXPRESSIVE PROSE with almost no attributive content — a bare affectionate line reduces
    # to roughly ONE content word — so any longer sentence sharing that word dominates it
    # structurally, and a warmer variant is proposed to retire the plainer one.
    #
    # The hypothesis that lost was that her lane would be dominance's BEST case, because
    # near-duplicate restatement is rife there and retiring one of her own repeated lines is
    # low-stakes. The first half is true. The second does not follow: dominance cannot
    # IDENTIFY a near-duplicate in her lane, it identifies "shares a content word and is
    # longer" — on the material where being wrong costs the most. G-SEM-DOMINATE §10.
    for _r in ([] if _self_narr else _dom.find_subsumed(fact, speaker, existing, status=status)):
        if id(_r) not in _seen:
            retired.append(_r)
            _seen.add(id(_r))
    # The verdict, handed to the writer: it stamps `supersedes` from these names and
    # `store.commit_row` puts them down by name under the lock.
    return (speaker, status, retired)
