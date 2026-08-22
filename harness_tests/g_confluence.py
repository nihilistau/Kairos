"""G-CONFLUENCE — order matters exactly where a correction lives, and nowhere else. OFFLINE.

THE QUESTION NOTHING ASKED. `docs/INVARIANT-MEMORY.md` is a document about order invariance
and `g_sem_stable.py` holds three real order laws — a verdict survives time translation, an
unrelated append, an unrelated retirement. What none of them asks is the one an operator
would assume:

    ingest the same set of claims in a different order and does the store know the same things?

I assumed the answer should be yes and wrote a gate to prove it. **The answer is no, and no
is correct** — which is worth more than the gate I set out to write.

    canonical order:  cat is Tuffy -> cat is Milo -> cat is Pepper     live: PEPPER
    shuffled:         cat is Pepper -> cat is Tuffy -> cat is Milo     live: MILO

A store where the third thing he said about his cat does NOT beat the first, because they
arrived in a different order, is a store that cannot learn a correction. **Supersession is
order-dependent by design, and must be**: "he changed his mind" is a fact about sequence.
Demanding confluence over the sequence of assertions would demand a memory that cannot be
corrected.

So this gate holds the claims that ARE true, and they are sharper than the one I wanted:

  1. WHERE THERE IS NO CONTEST, ORDER IS IRRELEVANT. Every claim not competing for an
     attribute slot is live in every order; the store is the same size; his testimony
     survives her inference whichever arrived first; her narrative accumulates regardless.
  2. WHERE THERE IS A CONTEST, THE LAST ASSERTION WINS — DETERMINISTICALLY. Not "some"
     value survives: the one asserted last IN THAT ORDER does. Order-dependence that is a
     function of the order is a correction working. Arbitrary order-dependence would be a
     coin flip wearing a memory's clothes.
  3. AND THE ONE PLACE IT LEAKS. Measured on her real store (2026-08-23, 140 claims x 4
     shuffles): identical row counts every time, and every divergence was a pair like

         "my gpu is an rtx 2060"   vs   "my gpu is an rtx 2060."

     Same claim, different punctuation, filling the same slot — so one "corrects" the other
     and arrival order picks the survivor. Nothing was corrected. That is a real defect, and
     it is asserted here as a named non-demand with its witness: a non-demand written down
     is a decision, one merely absent is a gap nobody has looked at.

    python harness_tests/g_confluence.py
"""
from __future__ import annotations

import os
import random
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"      # discard port: no engine, no mint
# NO CAPTURE AT ALL, and it is worth 300x (2026-08-23). Pointing SP_DAEMON_URL at a dead
# port does not make the mint cheap: _mint_now still opens a socket per write, and on
# Windows that connect costs ~2 SECONDS before it gives up. This gate does 7 x 19 writes.
# Declaring the backend kind instead makes supports("capture") False, so the mint returns
# immediately: measured 10 writes in 0.07s against 20s. Any offline gate that writes memory
# is paying the same toll.
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ["SP_CAPTURE_ASYNC"] = "0"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["SP_SEM_MINT"] = "0"
os.environ.pop("SP_SEM_INDEX", None)

SEEDS = 6

# The corpus EXERCISES the order-sensitive machinery rather than being typical:
#   - a three-deep supersede chain and a two-deep one, on REAL slots. Probe-verified:
#     "Sam's cat is called Tuffy" has attribute_key None, because a bare-subject sentence
#     has no slot and properties ACCUMULATE by design (the "cat destroyed the water" fix).
#     Only the possessive-before-copula shape competes. Intent proposes; attribute_key
#     disposes — the same rule sem_enum.py's text bank learned the hard way.
#   - an inference that argues with testimony (may_supersede must refuse it either way)
#   - two spellings of ONE claim, filling one slot (the named non-demand)
#   - her own narrative, which accumulates and may never supersede
CONTESTED = ("my cat s name is", "my favourite soup is", "my gpu is",
             "my laptop s name is")
FACTS = [
    ("user", "My cat's name is Tuffy", "user turn", ""),
    ("user", "My cat's name is Milo", "user turn", ""),
    ("user", "My cat's name is Pepper", "user turn", ""),
    ("user", "My favourite soup is spicy laksa", "user turn", ""),
    ("user", "My favourite soup is pea and ham", "user turn", ""),
    ("user", "My gpu is an RTX 2060", "user turn", ""),
    ("user", "My gpu is an RTX 2060.", "user turn", ""),          # ONE claim, two spellings
    # THE ASYMMETRY, ON A SLOT THAT ACTUALLY CONTESTS. The first draft of section 3 used
    # the open-water pair - and the mutant that made may_supersede return True sailed
    # straight through, because a bare-subject sentence has attribute_key None and
    # find_superseded never fired on it at all. His testimony survived for a reason that
    # had nothing to do with the law under test. These two share user::laptop's name, so
    # the asymmetry is the ONLY thing standing between her inference and his testimony.
    ("user", "My laptop's name is Vessel", "user turn", ""),
    ("user", "My laptop's name is Anchor", "reflection pass", ""),
    ("user", "Sam is terrified of open water", "user turn", ""),
    ("user", "Sam is comfortable in open water", "reflection pass", ""),
    ("user", "Sam's flight to Perth is on the twelfth", "user turn", ""),
    ("user", "Sam's sister is a nurse who lives in Perth", "user turn", ""),
    ("user", "Sam's brother is a diver who lives in Broome", "user turn", ""),
    ("user", "Sam likes the sound of rain on a tin roof", "user turn", ""),
    ("self", "I like the hour just before sunrise", "her own words", ""),
    ("self", "I feel quietly content tonight", "her own words", "feeling"),
    ("self", "I feel uneasy about the storm that is coming", "her own words", "feeling"),
    ("self", "I spent the evening reading about tides and lost the hour", "her own words",
     "narration"),
    ("self", "We talked about the weather and I kept thinking about the tides",
     "her own words", "journal"),
    ("self", "I have been turning toward the quiet hours",
     "reflection on myself (nightly becoming)", "self_description"),
]

_PUNCT = re.compile(r"[^a-z0-9 ]+")


def claim(text: str) -> str:
    """THE CLAIM, not the spelling: case, punctuation and whitespace folded."""
    return " ".join(_PUNCT.sub(" ", (text or "").lower()).split())


def contested(c: str) -> bool:
    return any(c.startswith(k) for k in CONTESTED)


def last_asserted(order, key):
    """The value the ORDER asserted last for this slot — what the store must be holding."""
    hit = ""
    for _lane, text, _src, _kind in order:
        if claim(text).startswith(key):
            hit = claim(text)
    return hit


def ingest(order):
    """Replay one order through the REAL writer into a fresh store."""
    import importlib
    d = tempfile.mkdtemp(prefix="g_confluence_")
    os.environ["SP_RECALL_REGISTRY"] = os.path.join(d, "reg.jsonl")
    open(os.environ["SP_RECALL_REGISTRY"], "w").close()
    from harness.skills import memory as M
    importlib.reload(M)
    for lane, text, src, kind in order:
        tok = M.set_author(lane)
        try:
            if lane == "self" and kind:
                M.remember_about_self(text, kind=kind, source=src)
            elif lane == "self":
                M.remember_about_self(text, source=src)
            else:
                M.remember(text, source=src)
        except Exception:
            pass
        finally:
            M._AUTHOR.reset(tok)
    rows = M._load()
    return {
        "live": {claim(r.get("text")) for r in rows if not r.get("lifecycle")},
        "dead": {claim(r.get("text")) for r in rows if r.get("lifecycle")},
        "texts": {" ".join((r.get("text") or "").split())
                  for r in rows if not r.get("lifecycle")},
        "rows": len(rows),
    }


base = ingest(list(FACTS))
runs = []
for seed in range(1, SEEDS + 1):
    o = list(FACTS)
    random.Random(seed).shuffle(o)
    runs.append((seed, o, ingest(o)))

print("1. WHERE THERE IS NO CONTEST, ORDER IS IRRELEVANT")
check("the gate is not vacuous: supersession really ran", len(base["dead"]) >= 2,
      sorted(base["dead"]))
uncontested = {c for c in base["live"] if not contested(c)}
check("...and there is uncontested material to compare", len(uncontested) >= 8,
      len(uncontested))
for seed, _o, r in runs:
    check("seed %d: every UNCONTESTED claim is live, identically" % seed,
          {c for c in r["live"] if not contested(c)} == uncontested,
          {"only canonical": sorted(uncontested - r["live"])[:3],
           "only this order": sorted({c for c in r["live"] if not contested(c)}
                                     - uncontested)[:3]})
check("the store is the same SIZE in every order",
      all(r["rows"] == base["rows"] for _s, _o, r in runs),
      [r["rows"] for _s, _o, r in runs])

print("\n2. WHERE THERE IS A CONTEST, THE LAST ASSERTION WINS - DETERMINISTICALLY")
for key in ("my cat s name is", "my favourite soup is"):
    check("canonical: the slot %r holds exactly one value" % key,
          len([c for c in base["live"] if c.startswith(key)]) == 1,
          sorted(c for c in base["live"] if c.startswith(key)))
    check("...and it is the one asserted LAST",
          {c for c in base["live"] if c.startswith(key)} == {last_asserted(FACTS, key)},
          (sorted(c for c in base["live"] if c.startswith(key)),
           last_asserted(FACTS, key)))
    for seed, o, r in runs:
        check("seed %d: %r still holds the LAST-asserted value" % (seed, key),
              {c for c in r["live"] if c.startswith(key)} == {last_asserted(o, key)},
              (sorted(c for c in r["live"] if c.startswith(key)), last_asserted(o, key)))

print("\n3. THE LAWS THAT HOLD IN EVERY ORDER, CONTEST OR NOT")
VESSEL = claim("My laptop's name is Vessel")
ANCHOR = claim("My laptop's name is Anchor")
check("HIS TESTIMONY SURVIVES HER INFERENCE ON THE SAME SLOT, in every order",
      VESSEL in base["live"] and all(VESSEL in r["live"] for _s, _o, r in runs),
      "may_supersede: an inference may NEVER retire ground truth")
check("...and it is never retired, in any order",
      all(VESSEL not in r["dead"] for _s, _o, r in runs))
check("...even when her inference is the LAST thing asserted (last-wins never "
      "outranks the asymmetry)",
      all(VESSEL in r["live"] for _s, o, r in runs
          if last_asserted(o, "my laptop s name is") == ANCHOR),
      "the whole reason status exists: two claims, one slot, the weaker may not win")
TERRIFIED = claim("Sam is terrified of open water")
check("and a BARE-SUBJECT pair never competes at all - properties accumulate",
      TERRIFIED in base["live"]
      and claim("Sam is comfortable in open water") in base["live"],
      "no slot, no contest: testimony_wins handles that one at the mouth, not the store")
check("her narrative ACCUMULATES: all of her rows live, in every order",
      all(sum(1 for c in r["live"] if c.startswith("i ")) >= 4 for _s, _o, r in runs),
      [sum(1 for c in r["live"] if c.startswith("i ")) for _s, _o, r in runs])
check("...and she never supersedes herself",
      all(not any(c.startswith("i ") for c in r["dead"]) for _s, _o, r in runs),
      [sorted(c for c in r["dead"] if c.startswith("i ")) for _s, _o, r in runs][:2])

print("\n4. THE NON-DEMAND, NAMED, WITH ITS WITNESS")
gpu_live = {sorted(t for t in r["texts"] if t.lower().startswith("my gpu"))[0]
            for _s, _o, r in runs if any(t.lower().startswith("my gpu") for t in r["texts"])}
check("the slot holds exactly one gpu row in every order",
      all(len([c for c in r["live"] if c.startswith("my gpu")]) == 1
          for _s, _o, r in runs))
check("...and as a CLAIM it is the same thing every time",
      len({c for _s, _o, r in runs for c in r["live"] if c.startswith("my gpu")}) == 1,
      sorted({c for _s, _o, r in runs for c in r["live"] if c.startswith("my gpu")}))
check("NON-DEMAND: which SPELLING of one claim survives is decided by arrival order",
      True,
      "spellings seen across %d orders: %s. Two texts differing only in punctuation fill "
      "the same slot, so one supersedes the other and the winner is whichever came last. "
      "NOTHING WAS CORRECTED. If this ever needs to be canonical the fix is a normalised "
      "representative at the slot, NOT a change to supersession - supersession is "
      "order-dependent on purpose, and that is the whole of how she learns a correction."
      % (len(runs), sorted(gpu_live)))

print("\n5. AND THE CLAIM IS NOT VACUOUS")
check("more than one order was tried, and they really differed",
      SEEDS >= 5 and any(o != list(FACTS) for _s, o, _r in runs), SEEDS)
check("the corpus exercises supersession, inference, spelling AND her lane",
      sum(1 for f in FACTS if "cat's name" in f[1]) == 3
      and any(f[2] == "reflection pass" and "laptop" in f[1] for f in FACTS)
      and sum(1 for f in FACTS if f[1].lower().startswith("my gpu")) == 2
      and any(f[0] == "self" for f in FACTS))
check("the contested keys really are contested (each asserted more than once)",
      all(sum(1 for f in FACTS if claim(f[1]).startswith(k)) >= 2 for k in CONTESTED),
      {k: sum(1 for f in FACTS if claim(f[1]).startswith(k)) for k in CONTESTED})

finish("G-CONFLUENCE")
