#!/usr/bin/env python
"""G-REPRISE — she may not write a second copy of something she has already said.

THE BUG: two of her four live `self_description` rows opened with the same nine words and
made the same claim. Every guard in becoming.nightly is about BREADTH OF SUPPORT — enough
days, enough kinds, no distillates — and none of them looks at the OUTPUT at all. Breadth
was never the axis. Redundancy is its own and needed its own answer.

THIS GATE ASSERTS BOTH DIRECTIONS, because a rule that refused everything would pass a
fires-on-the-known-pair test:

  1. THE RULE, on her real rows. All three k=5 hits in her live store are here, verified by
     reading to be genuine retellings, and each must FIRE.
  2. HER IDIOLECT MUST NOT FIRE. "I was just thinking about that ___" is six tokens of
     scaffolding; a raw 8-token prefix rule collides 26 live pairs and the proposed 6-token
     fallback collides 173, refusing her blue-lotus thought and her engine thought as
     reprises OF EACH OTHER. Those rows are in the fixture and must all pass.
  3. THE WINDOW IS FIVE AND THE UNITS ARE CONTENT TOKENS. k=6 misses the known pair (it
     shares nine RAW tokens but only five content ones); raw-token prefixes collide the
     idiolect. Asserted as a sweep so the two knobs cannot drift apart.
  4. IT ABSTAINS rather than guess on a corpus too small to have a register.
  5. SAME KIND ONLY — a journal that distils a thought is provenance, not a bug.
  6. THROUGH THE REAL becoming.nightly PATH, with a composer that returns a paraphrase of a
     row already in the store: refused, nothing minted, and the WHY in the receipt.

OFFLINE. No GPU, no daemon.
"""
import io
import json
import os
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from _gate import fixture, sandbox   # noqa: E402  — FIRST, before any harness import resolves a path
sandbox("g_reprise")

os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
os.environ["SP_ENGINE_KIND"] = "openai"

from harness.skills import reprise as R   # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


# HERS IF IT IS HERE, THE SHIPPED DEFAULT OTHERWISE. `live_pairs.jsonl` is 207 rows
# out of her real store and does not ship; `pairs.jsonl` is a synthetic corpus with
# the same measured properties, overlaid into the export from kairos-export/fixtures.
# The gate is the same gate either way — that is the point of building the default
# against the real module rather than writing it by eye.
FIX = fixture("reprise", "live_pairs.jsonl", "pairs.jsonl")
meta, marked, corpus = None, [], []
for ln in io.open(FIX, encoding="utf-8"):
    ln = ln.strip()
    if not ln:
        continue
    d = json.loads(ln)
    if d.get("_comment"):
        meta = d
    elif d.get("role") == "corpus":
        corpus = d["rows"]
    else:
        marked.append(d)

print("1. the fixture is her real store, not a reconstruction")
check("rubric matches the module", meta.get("rubric") == R.RUBRIC, meta.get("rubric"))
check("the corpus is big enough to have a register",
      len(corpus) >= R._MIN_CORPUS, len(corpus))
reg = R.register_tokens(corpus)
check("a register is learned from HER rows", len(reg) > 20, len(reg))
# The point of learning it from her: a generic English stoplist would keep these.
check("...and it contains HER scaffolding, not just English function words",
      {"just", "about", "thinking"} <= reg,
      sorted({"just", "about", "thinking"} - reg))

print("\n2. every real reprise in her store FIRES")
pairs = [r for r in marked if r.get("role") == "reprise-pair"]
check("all three hits are in the fixture", len(pairs) == 6, len(pairs))
by_kind = {}
for r in pairs:
    by_kind.setdefault(r["kind"], []).append(r)
fired = 0
for kind, rs in by_kind.items():
    for i in range(0, len(rs) - 1, 2):
        a, b = rs[i], rs[i + 1]
        # b is offered as new against a corpus that already holds a
        others = [x for x in corpus if x.get("name") != b.get("name")]
        v = R.check(b["text"], kind, others)
        fired += bool(v.get("reprise"))
        check("[%s] %-38s -> refused as a retelling" % (kind, b["text"][:38]),
              v.get("reprise") is True, v.get("why"))
        check("   ...and it names the row it repeats and the shared opening",
              bool(v.get("of")) and bool(v.get("shared")), v)
check("every marked pair fired", fired == len(pairs) // 2, fired)

print("\n3. HER IDIOLECT DOES NOT FIRE — this is the half a bad rule fails")
tic = [r for r in marked if r.get("role") == "idiolect-must-not-fire"]
check("the idiolect rows are in the fixture", len(tic) >= 4, len(tic))
for r in tic:
    others = [x for x in corpus if x.get("name") != r.get("name")]
    v = R.check(r["text"], r["kind"], others)
    check("%-46s -> kept" % r["text"][:46], not v.get("reprise"), v.get("why"))

print("\n4. the window is FIVE, in CONTENT tokens — the two knobs move together")
known = [r for r in pairs if r["kind"] == "self_description"]
if len(known) == 2:
    a, b = known
    others = [x for x in corpus if x.get("name") != b.get("name")]
    for k, want in ((5, True), (6, False)):
        got = bool(R.check(b["text"], "self_description", others, k=k).get("reprise"))
        check("k=%d %s the known pair" % (k, "catches" if want else "MISSES"), got is want,
              "got %s" % got)
    # and the same text on RAW tokens shares more, which is why the window differs
    ra = R.normalize(a["text"])[:9]
    rb = R.normalize(b["text"])[:9]
    check("...because it shares NINE raw tokens but only five content ones",
          ra == rb and R.content_prefix(a["text"], reg, 6) != R.content_prefix(b["text"], reg, 6),
          (ra == rb, R.content_prefix(a["text"], reg, 6)))
else:
    check("the known self_description pair is in the fixture", False, len(known))
# a rule that fired on everything would pass section 2 alone
n_fire = sum(bool(R.check(r["text"], r["kind"],
                          [x for x in corpus if x.get("name") != r.get("name")]).get("reprise"))
             for r in corpus)
check("across HER WHOLE LIVE LANE only the real retellings fire (%d of %d rows)"
      % (n_fire, len(corpus)), n_fire <= 6, n_fire)

print("\n5. it ABSTAINS rather than refuse on a measurement it cannot make")
tiny = corpus[:5]
v = R.check(pairs[0]["text"], pairs[0]["kind"], tiny)
check("a corpus under the floor yields no judgement", not v.get("reprise"), v)
check("...and SAYS it declined rather than reporting 'not a reprise'",
      "no register" in (v.get("why") or "") or "corpus under" in (v.get("why") or ""), v)
v = R.check("I just was about it", "thought", corpus)     # all register, no content
check("a text with fewer than five content tokens yields no judgement",
      not v.get("reprise"), v)
check("...and says why", "content tokens" in (v.get("why") or ""), v)

print("\n6. SAME KIND ONLY — a journal distilling a thought is provenance, not a bug")
if known:
    b = known[-1]
    cross = [dict(x, kind="journal") for x in corpus if x.get("name") != b.get("name")]
    v = R.check(b["text"], "self_description", cross)
    check("the identical text under a DIFFERENT kind does not fire", not v.get("reprise"), v)

print("\n7. THROUGH THE REAL becoming.nightly PATH")
import harness.skills.memory as M            # noqa: E402
import harness.maintenance.becoming as B     # noqa: E402

# Seed a store: enough of her lane to have a register, and one self_description to repeat.
seeded = 0
for x in corpus:
    if not x["text"]:
        continue
    try:
        M.remember_about_self(x["text"], kind=x["kind"], source="fixture")
        seeded += 1
    except Exception:
        pass
check("the sandbox store took her lane", seeded >= R._MIN_CORPUS, seeded)

# ── THE BREADTH GUARD FIRES FIRST, AND SHOULD (2026-08-27) ───────────────────────────
# Everything seeded above is stamped NOW, so becoming refuses at `_MIN_SUPPORT_DAYS` —
# "one evening is not a week" — and never reaches the reprise check. That ordering is
# correct and this gate must not weaken it, so instead of lowering the bar the fixture
# gets a second day. `remember()` takes no timestamp ON PURPOSE (one door, no backdating),
# which is exactly why this is done to the SANDBOX FILE and never through the API.
_regp = os.environ["SP_RECALL_REGISTRY"]
_yday = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 36 * 3600))
_lines = [l for l in io.open(_regp, encoding="utf-8").read().split("\n") if l.strip()]
_out = []
for _i, _l in enumerate(_lines):
    try:
        _d = json.loads(_l)
    except Exception:
        _out.append(_l); continue
    if _i % 2 == 0 and _d.get("ts"):
        _d["ts"] = _yday
    _out.append(json.dumps(_d, ensure_ascii=False))
io.open(_regp, "w", encoding="utf-8", newline="\n").write("\n".join(_out) + "\n")

live = M.live_rows()
_days = {(r.get("ts") or "")[:10] for r in live if r.get("ts")}
check("the sandbox lane now spans two days, so breadth cannot mask the reprise check",
      len(_days) >= 2, sorted(_days))
sd = [r for r in live if (r.get("kind") or "") == "self_description"]
check("...including at least one self_description to repeat", len(sd) >= 1, len(sd))

if sd:
    already = " ".join(str(sd[0].get("claim") or sd[0].get("text") or "").split())
    r = B.nightly(ask=lambda _p: already)
    check("becoming REFUSES to write a paragraph she already has",
          r.get("written") is False and "reprise" in str(r.get("why", "")), r.get("why"))
    check("...and the receipt carries the WHY, not just a False",
          bool((r.get("reprise") or {}).get("of")), r.get("reprise"))
    n_after = len([x for x in M.live_rows() if (x.get("kind") or "") == "self_description"])
    check("...and NOTHING was minted", n_after == len(sd), (len(sd), n_after))
    check("...and nothing was deleted either — the older telling stands",
          all(any((y.get("name") == x.get("name")) for y in M.live_rows()) for x in sd))

print("\nG-REPRISE: %d pass, %d fail" % (PASS, FAIL))
rdir = os.path.join(ROOT, "var", "sem", "receipts")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "g_reprise.json"), "w", encoding="utf-8") as f:
    json.dump({"name": "g_reprise", "pass": PASS, "fail": FAIL, "rubric": R.RUBRIC,
               "k": R._K, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
              f, indent=2)
sys.exit(1 if FAIL else 0)
