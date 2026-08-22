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

finish("G-PROVENANCE")
