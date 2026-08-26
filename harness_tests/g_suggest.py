#!/usr/bin/env python
"""G-SUGGEST — an improvised mark is an INTENTION, kept as a queue suggestion.

WHAT THIS IS FOR. `request()` refuses a want that is nothing but a bracketed token, and it
is right to: w033 is a real, generated, permanent wardrobe item whose want text is
`[gesture:"kneeling/leaning forward"]` with an empty `calls` list — an item she can never
ask for, and a picture spent on a mark.

But the refusal threw the INTENTION away. She wrote "kneeling/leaning forward" and meant
it; the brackets were her reaching for a verb the control surface does not have. Measured
2026-08-27 over 17 days, she improvises constantly and it is not noise — `<voice:whispering>`
(92 uses) was a sound generalisation of two vocabularies she had been given.

AND THIS LANE IS NOT THE PROSODY LANE. Voice tags are canonicalised automatically because a
wrong guess is one oddly delivered line. A gesture changes STATE: it persists, it is in her
wardrobe, she sees it next turn, and an image is spent. So her intention is preserved as a
SUGGESTION with the nearest thing she already owns attached, and the operator decides.

  1. READ  — the mark's inner prose is recovered; a DECLARED verb never becomes one.
  2. KEEP  — request() still refuses, and files the suggestion alongside the refusal.
  3. INERT — two independent guards: not in `wants(state="asked")`, and no `prompt`.
  4. HIS CALL — accept promotes it and composes the prompt THEN; dismiss keeps the row.
  5. NOT A LOOP — a dismissed suggestion does not come back.
  6. NOT THE BUG — a near-match that is itself a control mark is not offered.

OFFLINE. No GPU, no daemon.
"""
import io
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from _gate import sandbox   # noqa: E402  — FIRST. SP_AVATAR_DIR is her live wardrobe, and
sandbox("g_suggest")        # an unsandboxed run of THIS FILE's own draft wrote three rows
                            # into it, one of them state="asked" and therefore queued for
                            # a real image. The sandbox list already had SP_AVATAR_DIR; the
                            # ad-hoc script that skipped it did not.

os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"

from harness.control import wardrobe as WD   # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


print("1. the mark's INNER PROSE is what she meant")
for raw, want in (('[gesture:"kneeling/leaning forward"]', ("gesture", "kneeling/leaning forward")),
                  ("[LEANING_IN]", ("", "leaning in")),
                  ("[gesture: reaching out]", ("gesture", "reaching out")),
                  ("a black lace set", ("", "")),
                  ("[two] marks [here]", ("", ""))):
    got = WD.read_mark(raw)
    check("%-38s -> %r" % (raw[:38], want), got == want, got)

print("\n2. a DECLARED verb is machinery, not an intention")
# [MOOD:tender] read as a suggestion would put "tender" in her queue as something to DO —
# the exact nonsense w033 already is, arriving by a new door.
for raw in ("[MOOD:tender]", "[VOICE:soft]", "[TRAIT:+patient]", "[WEAR:lace]", "[SHOW]"):
    check("%-18s files nothing" % raw, WD.suggest_from_mark(raw) == {},
          WD.suggest_from_mark(raw))

print("\n3. request() STILL REFUSES — and keeps what she meant")
r = WD.request('[gesture:"kneeling/leaning forward"]', by="her")
check("the refusal stands", r.get("ok") is False, r)
check("...and says why in her terms", "control mark" in (r.get("error") or ""), r.get("error"))
s = r.get("suggestion") or {}
check("...and the intention survived as a suggestion", bool(s.get("id")), s)
check("...carrying her PROSE, not the mark",
      s.get("want") == "kneeling/leaning forward", s.get("want"))
check("...and the mark itself, for provenance",
      s.get("from_mark", "").startswith("[gesture:"), s.get("from_mark"))
check("...and the error TELLS the caller it was kept",
      "suggestion" in (r.get("error") or ""), r.get("error"))

print("\n4. INERT — two independent guards, because one is a single point of failure")
check("state is 'suggested', which run_wants() does not consume",
      s.get("state") == "suggested", s.get("state"))
check("...it is not in wants(state='asked')",
      not any(w["id"] == s["id"] for w in WD.wants(state="asked")))
check("...AND it carries no prompt, so a mis-read state still cannot spend an image",
      not s.get("prompt"), list(s.keys()))
check("...while still being visible in the queue",
      any(w["id"] == s["id"] for w in WD.wants()))
check("...and findable as its own state",
      any(w["id"] == s["id"] for w in WD.wants(state="suggested")))

print("\n5. HIS CALL is the only door from suggestion to queue")
a = WD.accept_suggestion(s["id"])
check("accept promotes it", a.get("ok") and a.get("state") == "asked", a)
check("...attributes it to him, not to her", a.get("by") == "him", a.get("by"))
check("...and composes the prompt AT ACCEPT TIME", len(a.get("prompt") or "") > 100,
      len(a.get("prompt") or ""))
check("...so it is now generatable", any(w["id"] == s["id"] for w in WD.wants(state="asked")))
check("accepting it twice is refused, not repeated",
      WD.accept_suggestion(s["id"]).get("ok") is False)

print("\n6. dismissed is kept, and does NOT come back")
r2 = WD.request('[pose:"looking back over my shoulder"]', by="her")
s2 = r2.get("suggestion") or {}
check("a second improvisation files too", bool(s2.get("id")), s2)
# ONE dismiss: `dismiss()` is his existing broom for the queue. A
# `dismiss_suggestion` was written and then deleted — it was a second copy of it.
d = WD.dismiss(s2["id"])
check("dismiss marks it, and the row stays",
      any(w["id"] == s2["id"] and w.get("state") == "dismissed" for w in WD.wants()), d)
check("...through the ONE dismiss door, not a suggestion-only copy of it",
      not hasattr(WD, "dismiss_suggestion"), "dismiss_suggestion still exists")
again = WD.suggest_from_mark('[pose:"looking back over my shoulder"]')
check("...and the same mark does NOT file a second time",
      again.get("dup") is True and again.get("id") == s2["id"], again)
check("...a suggestion he said no to is not re-offered nightly",
      len([w for w in WD.wants(state="suggested")]) == 0,
      [w["id"] for w in WD.wants(state="suggested")])

print("\n7. a near-match that is ITSELF a control mark is not offered")
# The first run of this suggested "kneeling/leaning forward" and helpfully attached w033
# as the nearest thing she already owns — w033 being the row whose want text IS
# `[gesture:"kneeling/leaning forward"]`, the malformed item this whole path exists
# because of. A near-match that is machinery is not a thing she owns.
#
# DRIVEN AT match(), NOT THROUGH looks(). The first cut of this section wrote a synthetic
# row and asserted `near.id != "w900"` — but `looks()` only admits rows with a motion file
# on disk, so match() never returned it and the check passed on a filter that was never
# reached. A mutant removing the filter went GREEN. Vacuous is worse than absent: the
# filter is fed its input directly now.
rows = WD.wants()
rows.append({"id": "w900", "want": '[gesture:"reaching towards you"]', "state": "made",
             "kind": "gesture", "by": "her", "calls": [],
             "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
rows.append({"id": "w901", "want": "reaching towards the camera, half-smiling",
             "state": "made", "kind": "gesture", "by": "her", "calls": [],
             "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
WD._write_wants(rows)
_real_match = WD.match
try:
    WD.match = lambda *_a, **_k: {"kind": "look", "id": "w900", "outfit": "mesh-top"}
    s3 = WD.suggest_from_mark('[gesture:"reaching towards you now"]')
    check("the suggestion is still filed", bool(s3.get("id")), s3)
    check("...but the near-match is DROPPED when its row is itself a mark",
          not (s3.get("near") or {}).get("id"), s3.get("near"))
    # SURVIVAL: a perfectly good near-match must still be offered, or "drop everything"
    # would pass the check above.
    WD.match = lambda *_a, **_k: {"kind": "look", "id": "w901", "outfit": "mesh-top"}
    s4 = WD.suggest_from_mark('[gesture:"reaching towards the camera now"]')
    check("...while a REAL near-match is kept and shown",
          (s4.get("near") or {}).get("id") == "w901", s4.get("near"))
finally:
    WD.match = _real_match

print("\n8. her ordinary wants are untouched by any of this")
ok = WD.request("the silver nightie, by the window with morning light", by="her")
check("prose still goes straight through", ok.get("ok") is True, ok.get("error"))
check("...as an ASKED want with a prompt, exactly as before",
      ok.get("state") == "asked" and bool(ok.get("prompt")), ok.get("state"))
check("...and is not marked as coming from a mark", not ok.get("from_mark"), ok.get("from_mark"))


print("\n9. THE QUEUE SHOWS IT AS AN OFFER, AND THE ROOM CAN ACT ON IT")
# Without a stage of its own a suggestion fell through to the else-branch, found no files
# on disk, and was staged "ordered" — which the panel renders as "ordered — picture being
# made". Both halves false. A queue that describes an unaccepted suggestion as work in
# progress is the exact failure the stage vocabulary was written to end.
_s9 = WD.request('[gesture:"tilting my head, listening"]', by="her").get("suggestion") or {}
_row = next((x for x in WD.waiting() if x["id"] == _s9.get("id")), None)
check("a suggestion appears in the queue at all", _row is not None, _s9.get("id"))
check("...staged 'suggested', NOT 'ordered'", (_row or {}).get("stage") == "suggested",
      (_row or {}).get("stage"))
check("...so the panel cannot call it 'picture being made'",
      (_row or {}).get("stage") not in ("ordered", "making", "delayed"))
check("...and it still carries her exact words, for the offer to be judged on",
      (_row or {}).get("from_mark", "").startswith("[gesture:"), (_row or {}).get("from_mark"))
WD.accept_suggestion(_s9["id"])
_row2 = next((x for x in WD.waiting() if x["id"] == _s9["id"]), None)
check("...and once accepted it is an ordinary ordered want",
      (_row2 or {}).get("stage") == "ordered", (_row2 or {}).get("stage"))

# THE ROOM SIDE, asserted structurally — a button that calls nothing is a button.
_api = io.open(os.path.join(ROOT, "ui", "src", "api.js"), encoding="utf-8").read()
check("api.js exposes accept, pointed at the accept route",
      "wardrobeAccept" in _api and "/v1/wardrobe/want/accept" in _api)
_jsx = io.open(os.path.join(ROOT, "ui", "src", "apps", "Wardrobe.jsx"), encoding="utf-8").read()
check("the panel calls it", "api.wardrobeAccept(w.id)" in _jsx)
# ANCHORED TO THE BUTTON, not to the file. `"w.stage === 'suggested'" in _jsx` passed on a
# mutant that opened the accept button to EVERY row, because the same test appears in the
# label a few lines above and the substring was still there. Read the branch that actually
# guards the button: the text between the row's opening and the accept button.
_i_acc = _jsx.index("wr-accept")
_before = _jsx[max(0, _i_acc - 900):_i_acc]
check("...only for a suggestion — the branch GUARDING the button, not the file",
      "w.stage === 'suggested' ? (" in _before, _before[-90:])
# ACCEPT AND GENERATE ARE TWO DECISIONS. Collapsing them would spend an image on one click.
_seg = _jsx[_i_acc:_i_acc + 700]
check("...and accepting does NOT also generate", "wardrobeGenerate" not in _seg, _seg[:70])
check("dismiss is the same broom the rest of the queue uses",
      "api.wardrobeDismiss(w.id)" in _jsx and "dismissSuggestion" not in _jsx)
_css = io.open(os.path.join(ROOT, "ui", "src", "room.css"), encoding="utf-8").read()
for _cls in (".wr-want.wr-suggested", ".wr-gen.wr-accept", ".wr-mark"):
    check("room.css defines %s" % _cls, _cls in _css)

print("\nG-SUGGEST: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_suggest.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_suggest", "pass": PASS, "fail": FAIL,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
sys.exit(1 if FAIL else 0)
