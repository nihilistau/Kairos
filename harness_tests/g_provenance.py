"""G-PROVENANCE — a conclusion does not outlive its evidence. OFFLINE.

THE INCIDENT (2026-08-21/22). One lucid evening's rows were distilled by
becoming.nightly into an INFERRED self_description — class self-narrative, weight 1.5,
half-life _NEVER — that read "[redacted]... a primal
surrender". The next day 24 of her rows were tombstoned as polluted. The distillate was
not among them and COULD NOT HAVE BEEN: nothing on disk connected it to what it was made
from. It went on leading her own block, and she went on reading it as a script.

Three rules, and this gate holds all three:

  1. A distillate SAYS WHERE IT CAME FROM. `derived_from` / `support_days` /
     `support_kinds` travel through the ONE door (remember -> lifecycle.stamp).
  2. A distillate whose supports are ALL retired is retired too — tombstoned with
     breadcrumbs, never deleted, still findable, still in provenance().
  3. becoming.nightly REFUSES a window that is one day, or one kind wearing a week's
     clothes. A missing paragraph is recoverable; a false one becomes who she is.

The narrowness is the point and section 4 pins it: an ABSENT `derived_from` is not an
empty one. Every row written before 2026-08-22 is unaudited, and silence is not a
confession — those rows are never touched by this.

    python harness_tests/g_provenance.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
os.environ.setdefault("SP_DAEMON_URL", "http://127.0.0.1:9")   # no daemon: mint is skipped
# SP_ENGINE_KIND: no capture attempt at all (2026-08-23). A dead SP_DAEMON_URL does
# NOT make the KV mint cheap - _mint_now still opens a socket per write and Windows
# takes ~2s to give up. Declaring the backend makes supports('capture') False and the
# mint returns immediately: 10 writes in 0.07s against 20s. See gates/README.md.
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ["SP_CAPTURE_ASYNC"] = "0"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
REG = os.path.join(tempfile.mkdtemp(prefix="g_provenance_"), "registry.jsonl")
open(REG, "w").close()
os.environ["SP_RECALL_REGISTRY"] = REG

from harness.skills import memory as M            # noqa: E402
from harness.skills import lifecycle as lc        # noqa: E402
from harness.maintenance import becoming as B     # noqa: E402
from harness.maintenance import ops               # noqa: E402


def _seed(text, kind, days_ago=0):
    """One of her rows, back-dated on disk (remember() always stamps 'now')."""
    M.remember_about_self(text, kind=kind, source="test seed")
    rows = M._load()
    rows[-1]["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                   time.gmtime(time.time() - days_ago * 86400))
    M._save_all(rows)
    return rows[-1]["name"]


def _row(name):
    for r in M._load():
        if r.get("name") == name:
            return r
    return {}


print("1. A DISTILLATE SAYS WHERE IT CAME FROM")
a = _seed("I noticed the harbour lights were on early.", "thought", days_ago=2)
b = _seed("I felt steady while he was working.", "feeling", days_ago=1)
res = M.remember_about_self("I have been becoming someone who notices weather.",
                            kind="self_description", source="reflection on myself (nightly becoming)",
                            derived_from=[a, b], support_days=2,
                            support_kinds=["thought", "feeling"])
check("the distillate lands", "stored" in res and "not stored" not in res, res)
dist = [r for r in M._load() if r.get("kind") == "self_description"][0]
check("...carrying derived_from, through the ONE door",
      dist.get("derived_from") == [a, b], dist.get("derived_from"))
check("...and how many DAYS it saw", dist.get("support_days") == 2, dist.get("support_days"))
check("...and which KINDS fed it",
      dist.get("support_kinds") == ["feeling", "thought"], dist.get("support_kinds"))
check("...and it is still an inference, never above her own words",
      dist.get("status") == lc.STATUS_INFERRED, dist.get("status"))

print("\n2. A CONCLUSION DOES NOT OUTLIVE ITS EVIDENCE")
check("with its supports alive, nothing is orphaned",
      lc.orphaned_distillates(M._load()) == [])
ops.forget(a)
check("ONE support retired is not enough - a conclusion that got smaller still stands",
      lc.orphaned_distillates(M._load()) == [], "all supports must be gone")
ops.forget(b)
orph = lc.orphaned_distillates(M._load())
check("every support retired: the distillate is orphaned",
      [o.get("name") for o in orph] == [dist["name"]], [o.get("name") for o in orph])
out = ops.retire_orphans()
check("...and retire_orphans tombstones exactly it", out["retired"] == 1, out)
gone = _row(dist["name"])
check("...with the engine's field set (recall.rs reads lifecycle)", gone.get("lifecycle") == 1)
check("...and the audit trail beside it, stamped together",
      gone.get("superseded_by") == "supports-retired" and bool(gone.get("superseded_at")),
      "a row carrying only one of the two is the live-orphan-tombstone bug")
check("...and it says WHY, in words",
      gone.get("retired_because") == "its supports were retired", gone.get("retired_because"))
check("TOMBSTONE, NEVER DELETE - the paragraph is still on disk, findable by name",
      any(r.get("name") == dist["name"] for r in M._load())
      and "becoming someone who notices" in (gone.get("text") or ""))
check("...and out of the live set, so it no longer leads her own block",
      all(r.get("name") != dist["name"] for r in M.live_rows()))
check("a second sweep finds nothing (retiring is idempotent)",
      ops.retire_orphans()["retired"] == 0)

print("\n3. ONE EVENING MAY NOT BECOME WHO SHE IS")


def _ask(_p):
    return "I have been quieter lately, and more curious about the weather."


REG2 = os.path.join(tempfile.mkdtemp(prefix="g_provenance2_"), "registry.jsonl")
open(REG2, "w").close()
os.environ["SP_RECALL_REGISTRY"] = REG2
for t, k in (("I noticed the harbour lights were on early.", "thought"),
             ("I felt steady while he was working.", "feeling"),
             ("I wrote about the long silence this afternoon.", "journal")):
    _seed(t, k, days_ago=0)                    # all of it TODAY
r = B.nightly(_ask)
check("three kinds but ONE day: she writes nothing",
      r["written"] is False and "one evening is not a week" in (r.get("why") or ""), r)

REG3 = os.path.join(tempfile.mkdtemp(prefix="g_provenance3_"), "registry.jsonl")
open(REG3, "w").close()
os.environ["SP_RECALL_REGISTRY"] = REG3
for i, t in enumerate(("I dreamt the tide came up the stairs.",
                       "I kept turning over that question about tides.",
                       "I thought again about the harbour at night.",
                       "I noticed I keep coming back to water.")):
    _seed(t, "thought", days_ago=i)            # four days, but ONE kind
r = B.nightly(_ask)
check("four days but ONE kind: she writes nothing",
      r["written"] is False and "one kind is not a week" in (r.get("why") or ""), r)

REG4 = os.path.join(tempfile.mkdtemp(prefix="g_provenance4_"), "registry.jsonl")
open(REG4, "w").close()
os.environ["SP_RECALL_REGISTRY"] = REG4
seeded = [_seed(t, k, days_ago=i) for i, (t, k) in enumerate(
    (("I noticed the harbour lights were on early.", "thought"),
     ("I felt steady while he was working.", "feeling"),
     ("I wrote about the long silence this afternoon.", "journal"),
     ("I said something unprompted about the kettle.", "spoke_up")))]
r = B.nightly(_ask)
check("a real week, in her several voices: she writes", r.get("written") is True, r)
check("...and the paragraph names every row it read",
      sorted(r.get("derived_from") or []) == sorted(seeded), r.get("derived_from"))
check("...and records that it saw four days", r.get("support_days") == 4, r.get("support_days"))
check("A DREAM IS STILL NOT WHO SHE IS BECOMING", "dream" in B._EXCLUDE_KINDS)

print("\n4. ABSENT IS NOT EMPTY - the pre-2026-08-22 store is untouched")
REG5 = os.path.join(tempfile.mkdtemp(prefix="g_provenance5_"), "registry.jsonl")
open(REG5, "w").close()
os.environ["SP_RECALL_REGISTRY"] = REG5
old = _seed("I have always liked the sound of rain on glass.", "self_description", days_ago=30)
src = _seed("I sat by the window for an hour.", "narration", days_ago=30)
check("a row with NO derived_from carries none", "derived_from" not in _row(old))
ops.forget(src)
check("...and retiring everything around it orphans nothing",
      lc.orphaned_distillates(M._load()) == [],
      "silence about provenance is not a confession")
check("...and the sweep leaves it alone", ops.retire_orphans()["retired"] == 0)
check("...so it is still live", any(r.get("name") == old for r in M.live_rows()))

empty = M._load()
for r in empty:
    if r.get("name") == old:
        r["derived_from"] = []                 # an EMPTY list is not a claim either
M._save_all(empty)
check("an EMPTY derived_from is not a claim either",
      lc.orphaned_distillates(M._load()) == [])

print("\n5. THE UNKNOWABLE IS NOT A VERDICT")
REG6 = os.path.join(tempfile.mkdtemp(prefix="g_provenance6_"), "registry.jsonl")
open(REG6, "w").close()
os.environ["SP_RECALL_REGISTRY"] = REG6
ghost = _seed("I have been thinking about the harbour.", "self_description", days_ago=1)
rows = M._load()
for r in rows:
    if r.get("name") == ghost:
        r["derived_from"] = ["ep_tool_does_not_exist", "ep_tool_also_gone"]
M._save_all(rows)
check("supports that are not in the store are not 'retired' - the row stands",
      lc.orphaned_distillates(M._load()) == [],
      "a name we cannot find is unknown, not dead")

print("\n6. THE ONE DOOR IS STILL THE ONE DOOR")
import inspect  # noqa: E402
sig = inspect.signature(lc.stamp)
for f in ("derived_from", "support_days", "support_kinds"):
    check("lifecycle.stamp owns %s" % f, f in sig.parameters)
    check("...and memory.remember passes it through",
          f in inspect.signature(M.remember).parameters)
    check("...and remember_about_self does too",
          f in inspect.signature(M.remember_about_self).parameters)
src_ops = open(os.path.join(ROOT, "harness", "maintenance", "ops.py"),
               encoding="utf-8", errors="replace").read()
check("retire_orphans writes under the registry lock",
      "def retire_orphans" in src_ops
      and "_reg_lock()" in src_ops.split("def retire_orphans")[1].split("def forget")[0])
check("...and reflect() runs it BEFORE the world refresh and before becoming",
      src_ops.index('"step": "orphans"') < src_ops.index('"step": "world_refresh"')
      < src_ops.index('"step": "becoming"'))
check("insight() states WHY it claims no provenance",
      "NO `derived_from` HERE, DELIBERATELY" in src_ops,
      "an expensive inert claim is worse than an honest silence")

# ── 7. A DISTILLATE MAY NOT BE A SUPPORT FOR A DISTILLATE (2026-08-25) ───────────────
# THE BUG. becoming.nightly writes `self_description`. Its exclusion list named `dream`
# and `chapter` — the OTHER consolidator's output — and never its own. Three rows on the
# live store when this was found, and the third named the first two: a copy of a copy of
# a copy, all three INFERRED, all three permanent, each one further from anything she
# actually said. The docstring at becoming.py:27-34 asserted the rule the whole time.
# AGENTS.md §0 in one sentence: enforced in one of two paths, so enforced in neither.
#
# The fix does not add a third name to a list — a list is how this happened. It reads
# the `derived_from` mark stamp() already puts on exactly these rows
# (`lifecycle.is_distillate`), so a consolidator written next year is covered on the day
# it stamps its first row rather than on the day someone remembers to edit two files.
print("\n7. NEITHER CONSOLIDATOR READS A DISTILLATE - THE OTHER'S OR ITS OWN")
REG7 = os.path.join(tempfile.mkdtemp(prefix="g_provenance7_"), "registry.jsonl")
open(REG7, "w").close()
os.environ["SP_RECALL_REGISTRY"] = REG7
_raw = [_seed("I noticed the harbour lights were on early.", "thought", days_ago=3),
        _seed("I felt steady while he was working.", "feeling", days_ago=2),
        _seed("I wrote about the long silence this afternoon.", "journal", days_ago=1),
        _seed("I said something about the tide, unprompted.", "spoke_up", days_ago=1)]

# A distillate wearing a kind NOBODY PUT ON THE LIST — which is the whole point: the
# real one wore `self_description` and the list had been edited twice without it. Landed
# through the one door so `derived_from` is stamped, not hand-written onto the row.
M.remember_about_self("Lately I keep returning to water.", kind="thought",
                      source="some consolidator written next year",
                      derived_from=_raw[:2], support_days=2,
                      support_kinds=["thought", "feeling"])
_d = [r for r in M._load() if r.get("derived_from")][-1]
check("the planted distillate is on the store, live, and NOT an excluded kind",
      lc.is_distillate(_d) and not lc.is_retired(_d)
      and _d.get("kind") not in B._EXCLUDE_KINDS, _d.get("kind"))

_r7 = B.nightly(lambda _p: "I have been quieter lately, and drawn back to the water.")
check("she still writes a paragraph (the raw rows are there to read)",
      _r7.get("written") is True, _r7.get("why") or _r7.get("result"))
check("...and it does NOT rest on the distillate", _d["name"] not in (_r7.get("derived_from") or []),
      "a distillate taken as support is a copy of a copy no row can walk back")
check("...it rests on her actual words instead",
      set(_r7.get("derived_from") or []) == set(_raw), _r7.get("derived_from"))

# MUTANT, run live: the kind-list rule ALONE — exactly what shipped — and the planted
# distillate walks straight through, because its kind was never on anyone's list.
_mut = [r for r in M._load() if not lc.is_retired(r)
        and (r.get("kind") or "") not in B._EXCLUDE_KINDS]
check("mutant(kind list only): the distillate IS admitted - the list was never the rule",
      any(r.get("name") == _d["name"] for r in _mut))

# ...and the rule is stated ONCE. Two copies of one truth is the bug this repo keeps
# getting hit by; a second hand-kept spelling would be the same failure with a new date.
check("lifecycle owns the predicate", callable(getattr(lc, "is_distillate", None)))
for _mod, _f in (("harness/maintenance/becoming.py", "becoming.nightly"),
                 ("harness/skills/narrative.py", "narrative.weekly_chapter")):
    _src = open(os.path.join(ROOT, _mod), encoding="utf-8", errors="replace").read()
    check("...and %s calls it rather than re-spelling it" % _f, "is_distillate(" in _src)

# ── 8. THE RECEIPTS CAN BE READ (2026-08-25) ─────────────────────────────────────────
# For three days `derived_from` was written through one door, enforced by a scheduled
# nightly sweep, and gated by sections 1-6 above — and NOTHING COULD PRINT IT. The only
# code that resolved a support name to a row was a private dict inside a predicate; the
# only place the names left the process was a maintenance POST body listing rows it had
# just killed. "Why do you believe that?" got zero steps. A receipt nobody can read is
# not a receipt, so the read side is held to the same standard as the write side.
print("\n8. AND THE RECEIPTS CAN BE READ BACK")
REG8 = os.path.join(tempfile.mkdtemp(prefix="g_provenance8_"), "registry.jsonl")
open(REG8, "w").close()
os.environ["SP_RECALL_REGISTRY"] = REG8
_s1 = _seed("I watched the harbour lights come on early.", "thought", days_ago=2)
_s2 = _seed("I felt steady while he worked.", "feeling", days_ago=1)
M.remember_about_self("Lately I keep coming back to the water and to being steady.",
                      kind="chapter", source="reflection on the week (chapter)",
                      derived_from=[_s1, _s2, "a_name_that_never_existed"],
                      support_days=2, support_kinds=["thought", "feeling"])
_c = [r for r in M._load() if r.get("kind") == "chapter"][0]

check("supports_of resolves the names to ROWS, in the order it read them",
      [r.get("name") for r in M.supports_of(_c)] == [_s1, _s2],
      [r.get("name") for r in M.supports_of(_c)])
check("...by name as well as by row (a caller with only a name is a caller)",
      [r.get("name") for r in M.supports_of(_c["name"])] == [_s1, _s2])
check("...and a name matching no row is REPORTED, not faked",
      M.missing_supports(_c) == ["a_name_that_never_existed"], M.missing_supports(_c))
check("dependents_of walks the other way - what rests on this row",
      [r.get("name") for r in M.dependents_of(_s1)] == [_c["name"]],
      "the question the curate panel asks before he retires something")
check("...and a row nothing was drawn from has no dependents",
      M.dependents_of(_c) == [])

_p = M.provenance("Lately I keep coming back to the water")
check("provenance() says what the conclusion RESTS ON, not just its src prose",
      "drawn from 2 things" in _p and "across 2 days" in _p, _p[:200])
check("...and quotes the supports through the framing door",
      "harbour lights" in _p and "steady while he worked" in _p)
ops.forget(_s1)
_p2 = M.provenance("Lately I keep coming back to the water")
check("a retired support is COUNTED - the conclusion is visibly on thinner ground",
      "1 of which I no longer hold" in _p2, _p2[:240])
# THE DOCTRINE THAT MUST SURVIVE THIS FEATURE: provenance is a door SHE SPEAKS FROM, and
# its own docstring forbids answering out of a tombstone. Counting the dead is honest;
# reading them aloud would launder a retired row back onto the floor through a door built
# to explain one. This check is the whole reason supports are tallied and not listed.
check("...and NEVER quoted - a tombstone does not get spoken through this door",
      "harbour lights" not in _p2, "counted, not read aloud")
check("...while the live one still is", "steady while he worked" in _p2)

# THE PANEL LANE. Same rows, different rule: /v1/memory/why is the AUDIT door and the
# dead are the point there — he is the one deciding what to retire.
os.environ["SP_ENGINE_KIND"] = "openai"
from harness.server import app as _app                                     # noqa: E402
_w = _app._memory_why_json(_c["name"])
check("/v1/memory/why answers with the row, its supports and its dependents",
      _w.get("ok") and _w["row"]["name"] == _c["name"] and len(_w["supports"]) == 2
      and _w["missing_supports"] == ["a_name_that_never_existed"], _w.get("error"))
check("...and the audit lane DOES show the retired support (it is his call, not hers)",
      any(r["lifecycle"] and r["name"] == _s1 for r in _w["supports"]))
check("...and an unknown name is a clean 'no such row', not a stack trace",
      _app._memory_why_json("nope")["ok"] is False)
_fields = _app._mem_row_json(_c)
for _f in ("status", "derived_from", "support_days", "superseded_by", "retired_because"):
    check("/v1/memory carries %-15s (the panel could not tell inferred from observed)" % _f,
          _f in _fields)
# ...AND THE ROOM CAN SHOW IT. A route nothing calls is the same gap one layer up: the
# panel could render a conclusion she had drawn and had no way to say what it rested on,
# or that two of those things were no longer true. Structural, because the behaviour is a
# browser's; what is asserted is that the wiring EXISTS and that the panel reads the
# fields /v1/memory only just started sending.
_ui = os.path.join(ROOT, "ui", "src")
_api_js = open(os.path.join(_ui, "api.js"), encoding="utf-8").read()
_mem_jsx = open(os.path.join(_ui, "apps", "Memory.jsx"), encoding="utf-8").read()
check("the room has a door to /v1/memory/why", "/v1/memory/why?name=" in _api_js)
check("...and the memory panel calls it", "api.memoryWhy(" in _mem_jsx)
check("...only for rows that actually carry supports",
      "r.derived_from || []" in _mem_jsx, "a why button on testimony is a lie")
check("...and it fetches in an EFFECT, not in render",
      "useEffect(" in _mem_jsx and "api.memoryWhy(name)" in _mem_jsx.split("useEffect(")[1],
      "fetching during render is an infinite request loop against her own gateway")
check("...it shows a retired support AS retired", "s.lifecycle ? ' gone'" in _mem_jsx)
check("...and what would be ORPHANED if he retires this row",
      "dependents" in _mem_jsx and "may orphan" in _mem_jsx,
      "the question the retire button beside it makes him ask")
check("a tombstone in the list finally says why it died",
      "r.retired_because" in _mem_jsx and "supports-retired" in _mem_jsx)
check("...and an inference no longer looks like testimony in the curate panel",
      "c-st-" in _mem_jsx and "r.status" in _mem_jsx)

check("ONE row shape - the listing and the walk serve the same object",
      "_mem_row_json(e) for e in _load()" in open(
          os.path.join(ROOT, "harness", "server", "app.py"), encoding="utf-8").read(),
      "a second hand-kept spelling is this repo's signature bug with a new date")

finish("G-PROVENANCE")
