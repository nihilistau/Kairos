"""dedupe.py — a repeat is not a duplicate. It is a second data point.

These two guards used to read `if <exact match>: return "already in memory"`, and that was
the end of it: every time he told her something AGAIN the store said "I know" and threw the
event away. It was proud of not duplicating a row.

**But the repetition IS the signal.** A thing a person tells you five times is not the same
thing as a thing they told you once, and we were recording them identically. She said it
herself, unprompted, on a kairos check-in: *"memory has context — WHO told you what, WHEN,
maybe even HOW MANY TIMES."* She had who. She had when. The third was arriving on every
restatement and being deleted at the door. So a repeat REINFORCES — `mentions += 1`,
`last_seen` moved, `first_seen` preserved, still exactly one row. The dedupe was right about
the STORAGE and wrong about the EVENT.

WHAT THIS MODULE OWNS, and why it is one module: **the decision is a read-modify-write**, and
the whole block runs under `store._REG_LOCK` because it loaded outside the lock once and
`_save_all`'d a stale list — a `remember()` landing between the read and the write was
silently rewritten away, the exact lost-write shape, on the hottest write path in the tree.
`G-REGISTRY-RMW` is the gate, and it drives this through `remember()`.

IT HANDS BACK `existing`, ON PURPOSE. The writer needs the row list for the supersede verdict
and must NOT re-read it under a second lock — the lock is released here before the mint,
because `_mint_now` can block on HTTP for up to 120 s and a registry lock held across a GPU
call would serialize every concurrent turn behind it. A stale `existing` is safe by
construction: `store.commit_row` applies its tombstones BY NAME against a fresh locked read.
That is the contract, and it is the reason this returns two values instead of one.

Extracted from `remember()` on 2026-09-02.
"""
from __future__ import annotations

import logging

from harness.skills.memory import store as _store
from harness.skills.memory.words import _text, _toks

_log = logging.getLogger("harness.memory")     # the same object; see store.py's note


def check_repeat(fact: str, source: str = ""):
    """Has she been told this before? Returns `(sentence_or_None, existing_rows)`.

    A sentence means the writer is DONE — it returns that verbatim, exactly as it does with
    an admission refusal. `existing` is handed back either way; see the header for why it is
    deliberately allowed to go stale.
    """
    from harness.skills import lifecycle as lc
    # ── A REPEAT IS NOT A DUPLICATE. IT IS A SECOND DATA POINT. (2026-07-13) ────────
    #
    # These two guards used to read:
    #     if <exact match>:      return f"already in memory: {fact}"
    #     if <paraphrase>:       return f"already in memory (paraphrase of): {...}"
    #
    # and that was the end of it. Every time he told her something AGAIN, the store said
    # "I know" and threw the event away. It was proud of not duplicating a row.
    #
    # But the repetition IS THE SIGNAL. A thing a person tells you five times is not the
    # same thing as a thing they told you once, and we were recording them identically.
    # She said it herself, unprompted, on a kairos check-in: "memory has context — WHO told
    # you what, WHEN, maybe even HOW MANY TIMES." She had who. She had when. The third one
    # was arriving on every restatement and being deleted at the door.
    #
    # So a repeat REINFORCES: mentions += 1, last_seen = now, first_seen preserved. Still
    # exactly one row — the dedupe was right about the STORAGE and wrong about the EVENT.
    def _reinforce(e: dict, why: str) -> str:
        lc.reinforce(e)
        _store._save_all(existing)
        n = e.get("mentions", 2)
        return ((f"reinforced ({n}x): {_text(e)}"
                 + (f"  [{why}]" if why else "")), existing)

    # ── THE REINFORCE BRANCH IS A READ-MODIFY-WRITE, SO IT HOLDS THE LOCK (2026-08-24
    # audit, A2). The invariant at _REG_LOCK's definition says a load/change/rewrite is
    # not interleaved with another — and this branch loaded OUTSIDE the lock, mutated a
    # row, and _save_all'd the stale list: a remember() landing between the read and the
    # write was silently rewritten away, the exact lost-write shape the comment up there
    # narrates, on the hottest write path in the file. The store branch below re-reads
    # inside its own locked block and was always right; this one now matches it.
    # The lock is RELEASED before the mint/supersede work that follows — _mint_now can
    # block on HTTP for up to 120 s when SP_CAPTURE_ASYNC=0, and a registry lock held
    # across a GPU call would serialize every concurrent turn behind it. A stale
    # `existing` beyond this block is safe by construction: the store branch applies
    # its tombstones by NAME against a fresh locked read. RLock, so _save_all's own
    # acquire nests without deadlock; nothing in this block does I/O beyond the store.
    # Gate: G-REGISTRY-RMW (mutant: lift this `with` and it goes red by name).
    with _store._REG_LOCK:
        existing = _store._load()

        for e in existing:
            if e.get("lifecycle"):
                continue                   # a tombstone is not reinforced back to life
            if _text(e).strip() == fact.strip():
                return _reinforce(e, "")

        # ── AN INFERENCE DOES NOT UNDO A RETIREMENT (2026-08-28) ─────────────────────
        # A tombstone is never reinforced (above) — but the same TEXT re-admitted as a
        # NEW row walked straight past it. Said by HIM again, that is right: fresh
        # testimony outranks old curation, and the new row stands beside the tombstone.
        # Re-minted by the CONSOLIDATOR re-reading an old transcript, it silently undid
        # a decision a person made in the panel an hour earlier — his report, verbatim:
        # "retired memories stay retired... it seems a little flaky". The paraphrase
        # passes (consolidator, reflection) are refused re-admission of a retired text;
        # the refusal names the tombstone so the log says WHY nothing was stored.
        if any(s in (source or "") for s in ("reflection", "consolidator")):
            ft_norm = fact.strip().lower()
            for e in existing:
                if e.get("lifecycle") and _text(e).strip().lower() == ft_norm:
                    return (("not stored — %r was retired (%s) and a %s pass may "
                             "not re-admit it; only being told again can"
                             % (fact[:60], e.get("superseded_at")
                                or e.get("retired_because") or "tombstoned", source)),
                            existing)

        ft = _toks(fact)
        if ft:
            for e in existing:
                if e.get("lifecycle"):
                    continue
                et = _toks(_text(e))
                if not et:
                    continue
                inter = len(ft & et)
                if inter / len(ft) >= 0.9 and inter / len(et) >= 0.9:
                    return _reinforce(e, "said again, in different words")
    # NOT A REPEAT. The writer goes on to mint, judge and store it; `existing` rides
    # along because the verdict needs the row list and must not take a second lock.
    return (None, existing)
