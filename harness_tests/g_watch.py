"""G-WATCH — "I will look out for a 3090 GPU to be available."  ...HOW?

She said that. She had no mechanism to look out for anything. It was a beautifully-formed
promise with nothing behind it — the SAME failure as a reminder that never fires, and the
worst kind this system produces: not a crash, not an error, but a thing he TRUSTED that
quietly was not true. He only caught it because he stopped and asked "how?".

Two honest fixes were available: stop her saying it, or MAKE IT TRUE.

    A reminder fires when the CLOCK says so.
    A watch fires when THE WORLD does.

THE THREE RULES, AND THEY ARE ALL THE SAME RULE — a watch that cannot be audited is a
prettier version of the lie it replaced:

  1. SHE MUST ACTUALLY LOOK.        `checked` counts real searches.
  2. SHE MUST SHOW WHAT SHE SAW.    no evidence -> it cannot fire.
  3. SHE MUST BE ABLE TO SAY NO.    and NO is the expected answer, nearly every time.
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp()
os.environ["SP_RECALL_REGISTRY"] = os.path.join(_TMP, "registry.jsonl")

from harness.skills import notes as N          # noqa: E402
from harness.skills import watch as W          # noqa: E402
from harness.skills import note_tools as T     # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def main() -> int:
    print("G-WATCH - she said she'd keep an eye out. Now she can.\n")

    # ── 1. SHE CAN ACTUALLY SET ONE UP ─────────────────────────────────────────
    out = T.watch_for("3090 back in stock", look_for="RTX 3090 in stock buy")
    check("watch_for() puts a real watch on the board", "watching:" in out, out[:64])
    w = next((n for n in N.live() if n["category"] == "watch"), None)
    check("...it is a WATCH, with a predicate instead of a due date",
          w and w["watch"] and not w["due_at"], str(w and w["watch"]))
    check("...and it is HERS (she promised it, so she owns it)", w["speaker"] == "self")

    # ── 2. SHE MUST ACTUALLY LOOK ──────────────────────────────────────────────
    # The receipt that turns "I'll keep an eye out" from a pleasantry into a claim he can
    # audit. Eleven checks and nothing found is itself worth knowing.
    check("(setup) a fresh watch is due for a look", bool(W.due_checks()), "")

    seen = {"searched": 0}

    def fake_search(q, n=5):
        seen["searched"] += 1
        return [{"title": "RTX 3090 | eBay", "url": "https://ebay.com/x",
                 "snippet": "Explore a wide range of our Rtx 3090 selection."}]

    W.search_web = fake_search  # inject: no network in a gate

    # ── 3. AND SHE MUST BE ABLE TO SAY NO ──────────────────────────────────────
    # THE DANGEROUS DEFAULT. A model asked "has this happened yet?" and rewarded for being
    # helpful will find a way to say yes. A page merely EXISTING about a product is not the
    # product being in stock. If NO is not cheap, the watch becomes a liar with a URL.
    r = W.check(w, judge=lambda q, e: (False, "an eBay listing page is not proof of stock"))
    check("a page merely EXISTING is not the thing happening", not r["fired"], r["why"])
    check("...but she DID look, and the receipt says so",
          seen["searched"] == 1 and N.get(w["id"])["checked"] == 1,
          f"checked={N.get(w['id'])['checked']}")

    # ── 4. SHE MUST SHOW WHAT SHE SAW ──────────────────────────────────────────
    # A watch that can fire on nothing is a watch that has learned to hallucinate — and it
    # would be WORSE than no watch, because he would believe it.
    # NB: this passes a judge that says YES with invented proof. It must STILL be refused —
    # the grounding lives in check(), at the door, so no judge can route around it. That was
    # a real bug the first time this gate ran: the rule was inside _judge(), so any other
    # judge bypassed it entirely. An invariant enforced in the caller is enforced nowhere.
    r = W.check(w, judge=lambda q, e: (True, "a 3090 is available for $1200 at NeverHeardOfIt.com"))
    check("a YES she cannot point at in the evidence is REFUSED — whatever the judge says",
          not r["fired"], r["why"])

    r = W.check(w, judge=lambda q, e: (True, "RTX 3090 | eBay"))
    check("...but a YES grounded in what she was actually shown FIRES", r["fired"], r["why"])
    check("...and the evidence is kept, so he can click the link himself",
          "ebay.com" in (N.get(w["id"])["evidence"] or ""), "")

    # ── 5. AN EMPTY SEARCH IS NOT A "NO" ───────────────────────────────────────
    # The old web_search returned "(no instant answer)" for EVERY real question ever asked.
    # A watch that treats "I failed to look" as "it has not happened" would confidently tell
    # him the 3090 is unavailable, forever, having never seen a single listing.
    W.search_web = lambda q, n=5: []
    w2 = N.add("thing", category="watch", watch="something obscure")
    r = W.check(w2, judge=lambda q, e: (True, "should never be consulted"))
    check("an empty search is NOT evidence of absence (and never fires)",
          not r["fired"] and "not evidence of absence" in r["why"], r["why"])

    # ── RULE 4: SHE MUST NOT LOOK AGAIN THE MOMENT SHE HAS LOOKED ────────────────────
    # THE TIMEZONE THAT BURNED THE GPU (2026-07-13). check() stamped last_checked with
    # time.gmtime() (UTC); due_checks() read it back with time.mktime() (LOCAL). At UTC+10
    # every stamp she wrote came back TEN HOURS OLD THE INSTANT SHE WROTE IT, so the 6-hour
    # gate could never close and the ticker re-ran the watch EVERY 15 SECONDS -- a live web
    # search plus a ~1450-token judge call, 78 seconds of GPU, forever. She had searched for
    # his RTX 3090 forty-six times. His own turns queued behind her and took 86 seconds
    # instead of 4.5. That is the whole "fast at first, painfully slow later" mystery.
    #
    # THE TEST HAS TO ASSERT THE ROUND TRIP, because the bug is INVISIBLE AT UTC+0. Any
    # assertion that only reads, or only writes, passes in London and burns the card in
    # Sydney. So: write the stamp the way check() writes it, read it the way due_checks()
    # reads it, and demand they agree -- under a forced non-zero TZ.
    import calendar
    import time as _t

    stamp = _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime())
    drift = abs(_t.time() - calendar.timegm(_t.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")))
    check("last_checked survives its own round trip (gmtime out, timegm back)",
          drift < 5, f"{drift:.0f}s drift (the bug read 36000s = exactly 10h)")

    # And the behaviour that drift actually causes: a watch looked at ONE SECOND AGO is not due.
    w3 = N.add("just looked", category="watch", watch="rtx 3090")
    N.update(w3["id"], checked=1,
             last_checked=_t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime()))
    still_due = [r for r in W.due_checks() if r["id"] == w3["id"]]
    check("a watch checked one second ago is NOT due again",
          not still_due, "it was due again immediately — the ticker will spin forever")

    total = len(PASS) + len(FAIL)
    print(f"\nG-WATCH: {'PASS' if not FAIL else 'FAIL'} ({len(PASS)}/{total})")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
