"""READ LONG THINGS SO SHE DOESN'T HAVE TO — aux compression of bulk text.

The 26B pays ~21 ms/tok (batched) to merely INGEST a long page; the 1.2B sidecar
reads the same page on CPU in seconds and hands back the marrow. Used by
web_search's page-read (SP_AUX=1) and available to any harness caller with a
long document and a question. NEVER a voice: the output is labelled context,
folded into her prompt, not spoken for her.
"""
from __future__ import annotations

from typing import List

from harness.sidecar import client

_CHUNK = 6000          # chars per map step — well inside the sidecar's context
_MAX_CHUNKS = 8        # a cap, said out loud: past ~48 KB we summarize the head


def read_long(text: str, question: str = "", max_words: int = 180) -> str:
    """Map/reduce summary of `text`, oriented by `question` when given.
    Returns '' when the sidecar is dark — callers keep their pre-aux behavior."""
    text = (text or "").strip()
    if not text:
        return ""
    ask = ("Summarize the key substance of this text in at most %d words. "
           "Plain prose, no preamble, no bullet-point skeleton." % max_words)
    if question:
        ask = ("With this question in mind: %r — extract and summarize what the "
               "text says that bears on it, at most %d words. If the text says "
               "nothing relevant, say exactly: NOTHING RELEVANT." % (question, max_words))
    chunks = [text[i:i + _CHUNK] for i in range(0, len(text), _CHUNK)][:_MAX_CHUNKS]
    if len(chunks) == 1:
        return _scrub(client.chat([{"role": "user", "content": ask + "\n\n" + chunks[0]}],
                                  max_tokens=max_words * 3))
    partials: List[str] = []
    for c in chunks:
        p = _scrub(client.chat([{"role": "user", "content": ask + "\n\n" + c}],
                               max_tokens=max_words * 2))
        if p:
            partials.append(p)
    if not partials:
        return ""
    joined = "\n\n".join(partials)
    return _scrub(client.chat([{"role": "user", "content":
                                ask + "\n\nThese are partial summaries of consecutive "
                                "sections of one document; merge them:\n\n" + joined}],
                              max_tokens=max_words * 3))


def _scrub(p: str) -> str:
    """The sentinel counts only when it IS the answer. Live 2026-08-20: the 1.2B
    wrote a perfectly good summary and then appended 'NOTHING RELEVANT.' as a
    compliance tic — a substring filter binned all seven partials of a page that
    was entirely relevant. So: a reply that is (essentially) just the sentinel is
    nothing; a trailing sentinel on real text is trimmed off real text."""
    p = (p or "").strip()
    if not p:
        return ""
    bare = p.upper().strip().rstrip(".!")
    if bare == "NOTHING RELEVANT" or (len(p) < 40 and "NOTHING RELEVANT" in bare):
        return ""
    up = p.upper()
    i = up.rfind("NOTHING RELEVANT")
    if i > 0 and len(p) - i < 24:          # a trailing tic, not the substance
        p = p[:i].rstrip(" .\n")
    return p
