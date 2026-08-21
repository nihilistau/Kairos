"""THE WATCH — she said she would keep an eye out. Now she can.

    her: "I will look out for a 3090 GPU to be available."
    him: "...how?"

She could not. There was no mechanism to look out for anything, and she said it anyway — a
beautifully-formed promise with nothing behind it. This is the SAME failure as a reminder
that never fires, and it is the worst kind this system produces: not a crash, not an error,
but a thing he TRUSTED that quietly was not true. He only found it because he stopped and
asked "how?". Most such promises are never audited at all; they simply rot.

Two honest fixes were on the table: STOP HER SAYING IT, or MAKE IT TRUE.

    A reminder fires when the CLOCK says so.
    A watch fires when THE WORLD does.

Everything else already existed — the board, the tick, the raise-it-like-a-reminder path.
The only missing piece was a note whose trigger is a QUESTION instead of a TIME.

── THE THREE RULES, AND THEY ARE ALL THE SAME RULE ──────────────────────────────

1. SHE MUST ACTUALLY LOOK. `checked` counts the times she really searched. It is the receipt
   that turns "I'll keep an eye out" from a pleasantry into a claim he can audit — and if
   she has looked eleven times and found nothing, that is worth knowing too.

2. SHE MUST SHOW WHAT SHE SAW. A watch cannot fire without EVIDENCE: a title, a snippet, a
   URL he can click. A watch that can fire on nothing is a watch that has learned to
   hallucinate, and it would be worse than no watch at all, because he would believe it.

3. SHE MUST BE ABLE TO SAY NO. The judgement is a strict YES/NO with a quotation, and NO is
   the expected answer nearly every time. A model asked "did this fire?" and rewarded for
   enthusiasm will fire on the first plausible-looking snippet it sees.
"""
from __future__ import annotations

import calendar
import logging
import os
import time
from typing import Optional

from harness.skills import notes as N
from harness.skills.system_tools import search_web

logger = logging.getLogger(__name__)


def due_checks(now: Optional[float] = None, every_hours: float = 6.0) -> list:
    """Watches that have not been looked at recently enough. Cheap; no network."""
    now = now or time.time()
    out = []
    for r in N.live():
        if r.get("category") != "watch" or not r.get("watch") or r.get("done"):
            continue
        last = r.get("last_checked") or ""
        if not last:
            out.append(r)
            continue
        try:
            # THE TIMEZONE THAT BURNED THE GPU (2026-07-13).
            #
            # check() writes this stamp with time.gmtime() -- UTC. This line used to read it
            # back with time.mktime(), which interprets a struct_time as LOCAL time. The
            # operator is at UTC+10, so every stamp she wrote was read back as TEN HOURS OLDER
            # THAN IT WAS. A watch checked one second ago computed as 10h stale, the 6-hour
            # gate could never close, and the ticker re-ran the watch EVERY 15 SECONDS: a live
            # web search plus a ~1450-token judge call, 78 seconds of GPU, forever. She had
            # checked for his RTX 3090 forty-six times. It is why his turns took 86 seconds
            # instead of 4.5 -- they were queued behind her, looking for a graphics card.
            #
            # calendar.timegm IS THE INVERSE OF gmtime. time.mktime is the inverse of
            # localtime. Pairing gmtime with mktime is a silent 10-hour lie here, a silent
            # 5-hour lie in New York, and CORRECT IN LONDON -- which is exactly why no test
            # caught it and why it can only be caught by a test that asserts the ROUND TRIP.
            t = calendar.timegm(time.strptime(last, "%Y-%m-%dT%H:%M:%SZ"))
        except Exception:
            out.append(r)
            continue
        if (now - t) >= every_hours * 3600.0:
            out.append(r)
    return out


def check(note: dict, judge=None) -> dict:
    """Look at the world once, for this one watch.

    `judge(question, evidence) -> (fired: bool, why: str)` is injected so the whole thing is
    testable without a GPU. In production it is her, reading the search results and deciding
    — and told, in as many words, that NO is the expected answer.
    """
    q = (note.get("watch") or "").strip()
    if not q:
        return {"ok": False, "why": "not a watch"}

    hits = search_web(q, n=5)
    real = [h for h in hits if h.get("url") and not h["title"].startswith("[search error")]

    N.update(note["id"],
             **{"checked": int(note.get("checked", 0) or 0) + 1,
                "last_checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

    if not real:
        # THE SEARCH FOUND NOTHING, AND THAT IS NOT THE SAME AS "NO". Saying "no" here would
        # be a claim about the world; the truth is that she failed to look at it. The old
        # web_search returned "(no instant answer)" for every real question ever asked, and a
        # model that treats that as evidence of absence will confidently tell him the 3090
        # is unavailable forever.
        logger.info("[watch] %r — search returned nothing; NOT reporting absence", q[:40])
        return {"ok": True, "fired": False, "why": "the search came back empty — "
                                                   "that is not evidence of absence"}

    evidence = "\n".join(f"- {h['title']}\n  {h['snippet'][:160]}\n  {h['url']}"
                         for h in real[:4])

    fired, why = (judge or _pick_judge())(q, evidence)

    # ── RULE 2, ENFORCED AT THE DOOR AND NOT IN THE JUDGE ────────────────────────
    # The grounding check used to live inside _judge(), which meant ANY other judge — a
    # test double, a future model, a smarter one — bypassed it entirely. That is precisely
    # the mistake this codebase has made over and over: an invariant enforced in the CALLER
    # instead of at the SEAM is an invariant enforced nowhere. It cost the identity firewall
    # twice and the kairos hooks six times.
    #
    # So it is here now, where every judge must pass through it: a YES whose proof does not
    # actually appear in the page she was shown is not a YES. She is a 12B — if she has
    # invented the evidence, the invention will not be in the evidence, and that is checkable.
    # A watch that can fire on nothing is worse than no watch, because he would believe it.
    if fired and not _grounded(why, evidence):
        logger.info("[watch] YES with no quotable evidence — refusing to fire: %r", why[:50])
        fired, why = False, "she said yes but could not point at the line that proves it"

    if fired:
        N.update(note["id"], evidence=evidence, raised=False)
        logger.info("[watch] FIRED %r :: %s", q[:40], why[:60])
    return {"ok": True, "fired": bool(fired), "why": why, "evidence": evidence,
            "results": real[:4]}


def _pick_judge():
    """The sidecar judges watches when armed (SP_AUX_WATCH_JUDGE=1); the model stays
    the fallback the moment the sidecar is dark or gives no usable shape.

    WHY THIS IS SAFE TO OFFLOAD: the dangerous failure of a watch judge is a
    hallucinated YES, and the defence against that was moved to the DOOR years
    of bugs ago — check() re-grounds every YES against the evidence, whoever
    judged. A sidecar NO costs one more poll cycle; a sidecar YES still has to
    quote a line that actually appears in the search results. The 26B one-shot
    this replaces measured 6.6-78 s of GPU per poll; the 1.2B answers on CPU in
    about a second."""
    if os.environ.get("SP_AUX_WATCH_JUDGE", "0") == "1":
        return _judge_sidecar
    return _judge


def _judge_sidecar(question: str, evidence: str):
    """The watch prompt, word for word, on the CPU sidecar. Any failure — dark
    sidecar, empty reply, unrecognizable shape — falls back to the model _judge
    rather than inventing a ruling."""
    try:
        from harness.sidecar import client as _aux
    except Exception:
        return _judge(question, evidence)
    if not _aux.available():
        return _judge(question, evidence)
    prompt = (
        f"Sam asked you to watch for this:\n  {question}\n\n"
        f"Here is what a web search just returned:\n{evidence}\n\n"
        "Has the thing he is waiting for ACTUALLY HAPPENED, according to these results?\n"
        "Almost always the answer is NO — a page merely EXISTING about a product is not the "
        "same as the thing he asked for being true. Do not stretch.\n"
        "Answer in exactly this shape:\n"
        "  NO: <one short reason>\n"
        "or, only if a specific line above proves it:\n"
        "  YES: <quote the exact line that proves it>"
    )
    txt = _aux.chat([{"role": "user", "content": prompt}], max_tokens=90).strip()
    if not txt:
        return _judge(question, evidence)
    head = txt.split("\n", 1)[0].strip()
    if head.upper().startswith("YES"):
        why = head[3:].lstrip(": ").strip()
        if len(why) < 8:
            return False, "she said yes but quoted nothing"
        return True, why          # check() does the grounding — at the door, for EVERY judge
    if head.upper().startswith("NO"):
        return False, head[2:].lstrip(": ").strip() or "not yet"
    return _judge(question, evidence)     # unrecognizable shape: the model rules


def _judge(question: str, evidence: str):
    """HER judgement, and she is told that NO is the expected answer.

    A model asked "has this happened yet?" and rewarded for being helpful will find a way to
    say yes. So the prompt makes NO cheap and YES expensive: YES requires her to quote the
    line that proves it. If she cannot quote it, it did not happen."""
    from harness.inference import InferenceConfig
    from harness.inference.client import get_client

    prompt = (
        f"Sam asked you to watch for this:\n  {question}\n\n"
        f"Here is what a web search just returned:\n{evidence}\n\n"
        "Has the thing he is waiting for ACTUALLY HAPPENED, according to these results?\n"
        "Almost always the answer is NO — a page merely EXISTING about a product is not the "
        "same as the thing he asked for being true. Do not stretch.\n"
        "Answer in exactly this shape:\n"
        "  NO: <one short reason>\n"
        "or, only if a specific line above proves it:\n"
        "  YES: <quote the exact line that proves it>"
    )
    # ONE-SHOT. She answers this once and the session is thrown away — there is nothing here to
    # continue. Through chat() this landed in THE RESIDENT KV SLOT, the one holding his
    # conversation: ~1450 tokens of PER-TOKEN prefill (78 SECONDS, to produce one YES/NO token),
    # and it EVICTED his chat on the way out, so his next turn re-prefilled from token 0.
    # Its own scratch cache now; batched; released. The resident cache is not touched.
    txt = (get_client().oneshot(
        [{"role": "user", "content": prompt}], max_tokens=90, temperature=0.0,
    ) or "").strip()

    head = txt.split("\n", 1)[0].strip()
    if head.upper().startswith("YES"):
        why = head[3:].lstrip(": ").strip()
        if len(why) < 8:
            return False, "she said yes but quoted nothing"
        return True, why          # check() does the grounding — at the door, for EVERY judge
    return False, head[3:].lstrip(": ").strip() or "not yet"


def _grounded(claim: str, evidence: str) -> bool:
    """Does her 'proof' actually appear in what she was shown?"""
    ev = evidence.lower()
    words = [w for w in "".join(c.lower() if (c.isalnum() or c.isspace()) else " "
                                for c in claim).split() if len(w) > 3]
    if not words:
        return False
    hit = sum(1 for w in words if w in ev)
    return hit / len(words) >= 0.6
