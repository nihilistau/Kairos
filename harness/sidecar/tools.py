"""HER deep-recall tool — the archive, spoken to in her own vocabulary.

One tool, one verb. It joins the curated live set behind SP_AUX=1, taking that
set past the ~6-tool comfort line the same way NOTE_TOOLS did — so, like then,
G-NOTES-TOOLS-style measurement beats assumption: h_aux gate section 4 checks the
tool renders a spec a small model can pick correctly.

The tool READS. It never writes the registry: if what comes back is worth
keeping, she calls remember() herself and the fact enters through the front door
(verdicts, ranking, testimony rules) with the day as provenance in her own words.
"""
from __future__ import annotations

from harness.sidecar import archive, client


def deep_recall(query: str) -> str:
    """Search EVERY past conversation for a moment or fact (beyond active memory).

    e.g. deep_recall("the night we talked about the lighthouse keepers")
    Returns the actual words from the actual days, each labelled with its date.
    If nothing comes back, say so — never fill the gap with something plausible."""
    if not client.available():
        return ("(deep recall is not armed on this profile — answer from active "
                "memory, and say plainly when you do not remember)")
    hits = archive.search(query, k=4)
    # THE FLOOR: cosine top-k always returns SOMETHING — the best of nothing is
    # still nothing. Calibrated on the FULL live index (1,029 chunks, 2026-08-20):
    # real moments score 0.39–0.57 ("the flannel shirt compliment" -> 0.548, the
    # exact exchange), while a query about a night that never happened tops out
    # at 0.24 of unrelated chat. 0.30 splits the observed bands with margin on
    # both sides. Below it the honest answer is "I don't remember", not the
    # least-unrelated moment of her whole life.
    hits = [h for h in hits if h["score"] >= 0.30]
    if not hits:
        return ("(deep recall found nothing for %r — say plainly that you do not "
                "remember, do not invent)" % (query or "")[:80])
    out = []
    # ── A TRANSCRIPT REMEMBERS WHAT THE REGISTRY WITHHOLDS (2026-08-28, external
    # review). secret_withheld guards the CLASSIFIED store; day transcripts were never
    # classified, so a credential said out loud in chat came back verbatim through this
    # door while every registry door declined it. The write-path classifier's own
    # detectors decide WHICH sentences are secret-shaped; the whole sentence is covered,
    # because masking only the matched phrase would leave the credential standing right
    # after the words "my password is". The moment still returns — the day, the rest of
    # the conversation — only the secret-bearing sentences are withheld.
    def _mask(t: str) -> str:
        try:
            from harness.skills.lifecycle import _SECRET, _SECRET_POSS
        except Exception:
            return t
        import re as _re
        parts = _re.split(r"(?<=[.!?\n])", t)
        return "".join("[a private sentence — withheld] " if
                       (_SECRET.search(p) or _SECRET_POSS.search(p)) else p
                       for p in parts)
    for h in hits:
        out.append("[%s] (match %.2f)\n%s" % (h["day"], h["score"], _mask(h["text"][:700])))
    out.append("(these are verbatim transcript moments — if one is worth keeping, "
               "store the FACT with remember() and cite the day)")
    return "\n\n".join(out)


DEEP_RECALL_TOOLS = [deep_recall]
