"""G-EPS-COLD-MOVE — the mover moves only what the rule names, never past a floor, and survives a crash. OFFLINE.

D2 (spec §6). harness/maintenance/eps_cold.py moves an episode DIRECTORY from the hot root
to the cold root and records it in eps-moves.jsonl. The registry is never written. Every
fixture here is synthetic, in the sandbox; the floors are driven through the owner seam
eps_cold._disk_usage (memory: "mutants patch the owner").

  §1 a dry run lists what would move, with sizes, and changes nothing
  §2 a live pass needs eps_cold_armed, at run(), move_one() and recover() alike
  §3 armed: exactly the rule's episodes move, every row still finds its episode, and the
     ledger holds basenames and tier names, never a path
  §4 idempotent: a second pass moves nothing and records nothing
  §5 the floors refuse, with numbers: min free, larger than free, unreachable, no cold root
  §6 the hot disk warns under eps_hot_warn_free_gb
  §7 recovery: partials rolled back or finished, leftovers removed or restored, a crash
     mid-copy undone, a locked hot copy finished later; (g) never a deletion on a size
     match, only on matching sha256 per file; (h) only her episodes are adopted; (i) a
     locked partial skips its episode, not the pass
  §8 the registry is never written, and the mover names none of its writers
  §9 a second pass while one runs is skipped

    python harness_tests/g_eps_cold_move.py
"""
import calendar
import collections
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness_tests._gate import sandbox, check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_eps_cold_move")  # FIRST, before any harness. import
os.environ["SP_EPS_COLD_ARMED"] = "0"
os.environ["SP_EPS_COLD_MIN_FREE_GB"] = "0"
os.environ["SP_EPS_HOT_WARN_FREE_GB"] = "0"
HOT, COLD = os.environ["SP_EPS_DIR"], os.environ["SP_EPS_COLD_DIR"]
GONE, OUT = os.path.join(SB, "gone-root"), os.path.join(SB, "elsewhere")
REG = os.environ["SP_RECALL_REGISTRY"]
LEDGER = os.path.join(os.path.dirname(REG), "eps-moves.jsonl")
NOW = float(calendar.timegm((2026, 10, 19, 0, 0, 0)))
OLD = "2026-08-01T00:00:00Z"
Usage = collections.namedtuple("Usage", "total used free")


def episode(path, k=1000, v=500):
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "ep.k"), "wb") as f:
        f.write(b"k" * k)
    with open(os.path.join(path, "ep.v"), "wb") as f:
        f.write(b"v" * v)


def dead(name, d, **kw):
    r = {"name": name, "dir": d, "text": name, "lifecycle": 1, "superseded_at": OLD,
         "npos": 4, "sig_bits": "0" * 64}
    r.update(kw)
    return r


def live(name, d, **kw):
    r = {"name": name, "dir": d, "text": name, "lifecycle": 0, "npos": 4, "sig_bits": "0" * 64}
    r.update(kw)
    return r


def write_rows(rows):
    with open(REG, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with open(REG, "rb") as f:
        return f.read()


def reg_bytes():
    with open(REG, "rb") as f:
        return f.read()


def snap(root):
    out = {}
    for dp, _dn, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(dp, fn)
            out[os.path.relpath(p, root)] = os.path.getsize(p)
    return out


def ledger():
    if not os.path.exists(LEDGER):
        return []
    with open(LEDGER, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _code(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    return re.sub(r'(?s)""".*?"""', "", re.sub(r"#[^\n]*", "", src))


for n in ("ep_tool_1760000000001", "ep_tool_1760000000002", "ep_tool_1760000000003", "ep_tool_1760000000004", "ep_tool_1760000000005"):
    episode(os.path.join(HOT, n))
episode(os.path.join(OUT, "ep_tool_1760000000006"))
os.makedirs(COLD, exist_ok=True)
ROWS = [
    dead("a", os.path.join(HOT, "ep_tool_1760000000001")),
    dead("b", os.path.join(GONE, "ep_tool_1760000000002")),          # an old-root row: resolves MOVED under the hot root
    live("shares-a", os.path.join(HOT, "ep_tool_1760000000001")),    # a LIVE row naming the same episode (Review Focus 4)
    live("live", os.path.join(HOT, "ep_tool_1760000000003")),
    dead("folded", os.path.join(HOT, "ep_tool_1760000000004"), superseded_by="d"),
    live("d", os.path.join(HOT, "ep_tool_1760000000005"), derived_from=["folded"]),
    dead("out", os.path.join(OUT, "ep_tool_1760000000006")),
    # §7(b)'s orphaned partial is hers: a row names it, so recovery may finish and record it.
    # Its episode does not exist until §7, and a live row is never a candidate.
    live("x", os.path.join(HOT, "ep_tool_1760000000008")),
]
REG0 = write_rows(ROWS)

from harness.maintenance import eps_cold as EC  # noqa: E402
from harness.skills import epdir  # noqa: E402

REAL = {"du": EC._disk_usage, "same": EC._same_device, "copy": EC._copytree, "rm": EC._rmtree}

print("§1 a dry run lists what would move, with sizes, and changes nothing")
before = snap(SB)
r = EC.run(now=NOW)
wm = {x["ep"]: x for x in r.get("would_move", [])}
check("unarmed, the nightly default is a dry run", r.get("dry_run") is True, r)
check("it would move exactly the two the rule names", set(wm) == {"ep_tool_1760000000001", "ep_tool_1760000000002"}, sorted(wm))
check("...each with its size and file count",
      (wm.get("ep_tool_1760000000001", {}).get("bytes"), wm.get("ep_tool_1760000000001", {}).get("files")) == (1500, 2), wm.get("ep_tool_1760000000001"))
check("...and the total", r.get("bytes") == 3000, r.get("bytes"))
check("an episode outside the hot root is skipped and counted",
      r.get("skipped", {}).get("outside_hot_root") == 1, r.get("skipped"))
check("the dry run changed nothing on disk", snap(SB) == before)
check("...and wrote no ledger", not os.path.exists(LEDGER))

print("§2 a live pass needs the operator's arming")
r = EC.run(dry_run=False, now=NOW)
check("unarmed, a live pass is refused", r.get("ok") is False and "eps_cold_armed" in str(r.get("refused")), r)
check("...and nothing moved", snap(SB) == before)
# The guard is at the write, not only at run(): move_one and recover are public, and the
# route and the nightly step are not the only callers a later task could add.
_cand = EC.plan(EC.config(), now=NOW)["candidates"][0]
r = EC.move_one(_cand, EC.config(), dry_run=False)
check("unarmed, move_one refuses a live move by itself",
      r.get("result") == "refused" and "eps_cold_armed" in r.get("why", ""), r)
os.makedirs(os.path.join(COLD, ".partial-ep_tool_1760000000003"))
rec = EC.recover(EC.config())
check("unarmed, recover() touches nothing",
      not any(rec.values()) and os.path.isdir(os.path.join(COLD, ".partial-ep_tool_1760000000003")), rec)
if os.path.isdir(os.path.join(COLD, ".partial-ep_tool_1760000000003")):   # gone only under a mutant
    os.rmdir(os.path.join(COLD, ".partial-ep_tool_1760000000003"))
check("...and still nothing moved, and no ledger", snap(SB) == before and not os.path.exists(LEDGER))

print("§3 armed: the rule's episodes move, and are still found")
os.environ["SP_EPS_COLD_ARMED"] = "1"
r = EC.run(now=NOW)
check("armed, the nightly pass is live", r.get("dry_run") is False, r)
check("it moved exactly ep_tool_1760000000001 and ep_tool_1760000000002", {x["ep"] for x in r.get("moved", [])} == {"ep_tool_1760000000001", "ep_tool_1760000000002"}, r)
check("the hot copies are gone",
      not os.path.exists(os.path.join(HOT, "ep_tool_1760000000001")) and not os.path.exists(os.path.join(HOT, "ep_tool_1760000000002")))
check("the cold copies are whole", snap(os.path.join(COLD, "ep_tool_1760000000001")) == {"ep.k": 1000, "ep.v": 500})
L1 = ledger()
check("each move is one ledger row: episode, from, to, size, how",
      sorted(x["ep"] for x in L1) == ["ep_tool_1760000000001", "ep_tool_1760000000002"]
      and all(x.get("from") and x.get("to") and x.get("bytes") == 1500 and x.get("files") == 2
              and x.get("how") == "move" for x in L1), L1)
# The ledger travels with the registry to other machines; an absolute path in it would go
# stale exactly as the old-root rows did (epdir.py). Basenames and tier names only.
check("...and holds no path: basenames and tier names only",
      all(not any(isinstance(v, str) and ("/" in v or "\\" in v or ":" in v[1:3]) for k, v in x.items()
                  if k != "at") and x["from"] == "hot" and x["to"] == "cold" for x in L1), L1)
check("the dead row resolves to its cold copy", epdir.resolve(ROWS[0]["dir"])[1] == epdir.COLD,
      epdir.resolve(ROWS[0]["dir"]))
check("the old-root row resolves to its cold copy", epdir.resolve(ROWS[1]["dir"])[1] == epdir.COLD)
check("a LIVE row sharing the moved episode still finds it",
      epdir.resolve(ROWS[2]["dir"]) == (epdir.cold_root() + "/ep_tool_1760000000001", epdir.COLD), epdir.resolve(ROWS[2]["dir"]))
check("live, folded-into-live and distillate episodes stayed hot",
      all(os.path.isdir(os.path.join(HOT, n)) for n in ("ep_tool_1760000000003", "ep_tool_1760000000004", "ep_tool_1760000000005")))
check("the episode outside the hot root stayed where it was", os.path.isdir(os.path.join(OUT, "ep_tool_1760000000006")))

print("§4 idempotent")
cold_before = snap(COLD)
r = EC.run(now=NOW)
check("a second pass moves nothing", r.get("moved") == [], r.get("moved"))
check("...counts both as already cold", r.get("skipped", {}).get("already_cold") == 2, r.get("skipped"))
check("...and writes no ledger row", len(ledger()) == len(L1), len(ledger()))
check("...and leaves the cold copies as they were", snap(COLD) == cold_before)

print("§5 the floors refuse, with numbers")
episode(os.path.join(HOT, "ep_tool_1760000000007"))
REG0 = write_rows(ROWS + [dead("c", os.path.join(HOT, "ep_tool_1760000000007"))])
os.environ["SP_EPS_COLD_MIN_FREE_GB"] = "20"
EC._disk_usage = lambda p: Usage(10 ** 12, 10 ** 12 - int(5e9), int(5e9))
r = EC.run(now=NOW)
ref = r.get("refused") or [{}]
check("under eps_cold_min_free_gb the move is refused",
      ref[0].get("ep") == "ep_tool_1760000000007" and "eps_cold_min_free_gb = 20" in ref[0].get("why", "")
      and "5.00 GB free" in ref[0].get("why", ""), ref)
check("...the pass stops at the floor and says why", "eps_cold_min_free_gb" in str(r.get("stopped")), r.get("stopped"))
check("...a dry run shows the same refusal before arming",
      (EC.run(dry_run=True, now=NOW).get("refused") or [{}])[0].get("ep") == "ep_tool_1760000000007")
os.environ["SP_EPS_COLD_MIN_FREE_GB"] = "0"
EC._same_device = lambda a, b: False
EC._disk_usage = lambda p: Usage(10 ** 12, 10 ** 12 - 1000, 1000)
ref = EC.run(now=NOW).get("refused") or [{}]
check("a move larger than the cold disk's free space is refused",
      "1500 B to move, 1000 B free" in ref[0].get("why", ""), ref)


def _no_disk(p):
    raise OSError("no such device")


EC._disk_usage = _no_disk
ref = EC.run(now=NOW).get("refused") or [{}]
check("an unreachable cold disk is refused, not a crash", "not reachable" in ref[0].get("why", ""), ref)
EC._disk_usage = REAL["du"]
os.environ["SP_EPS_COLD_DIR"] = os.path.join(SB, "never-made")
ref = EC.run(now=NOW).get("refused") or [{}]
check("a cold root that does not exist is refused, never created",
      "does not exist" in ref[0].get("why", "") and not os.path.exists(os.path.join(SB, "never-made")), ref)
os.environ["SP_EPS_COLD_DIR"] = COLD
check("...and ep_tool_1760000000007 is still hot after all four", snap(os.path.join(HOT, "ep_tool_1760000000007")) == {"ep.k": 1000, "ep.v": 500})

print("§6 the hot disk warns under eps_hot_warn_free_gb")
EC._same_device = REAL["same"]
os.environ["SP_EPS_HOT_WARN_FREE_GB"] = "30"
EC._disk_usage = lambda p: Usage(10 ** 12, 10 ** 12 - int(10e9), int(10e9))
r = EC.run(dry_run=True, now=NOW)
check("the pass warns, with numbers",
      any("10.00 GB free" in w and "eps_hot_warn_free_gb = 30" in w for w in r.get("warnings", [])), r.get("warnings"))
check("...and so does the boot line", "WARNING" in EC.boot_report())
EC._disk_usage = REAL["du"]
os.environ["SP_EPS_HOT_WARN_FREE_GB"] = "0"

print("§7 a crash leaves nothing recovery cannot finish or undo")
cfg = EC.config()
if os.path.isdir(os.path.join(HOT, "ep_tool_1760000000007")):   # absent only under a mutant; (a) then fails by name
    shutil.copytree(os.path.join(HOT, "ep_tool_1760000000007"), os.path.join(COLD, ".partial-ep_tool_1760000000007"))   # (a)
episode(os.path.join(COLD, ".partial-ep_tool_1760000000008"))                                      # (b)
episode(os.path.join(HOT, ".moved-ep_tool_1760000000001"))                                         # (c)
episode(os.path.join(HOT, ".moved-ep_tool_1760000000009"))                                         # (d)
rec = EC.recover(cfg)
check("(a) a partial whose source is still hot is rolled back",
      "ep_tool_1760000000007" in rec["rolled_back"] and not os.path.exists(os.path.join(COLD, ".partial-ep_tool_1760000000007"))
      and os.path.isdir(os.path.join(HOT, "ep_tool_1760000000007")), rec)
check("...and is not recorded", "ep_tool_1760000000007" not in {x["ep"] for x in ledger()})
check("(b) a partial with no source left is finished and recorded",
      "ep_tool_1760000000008" in rec["finished"] and os.path.isdir(os.path.join(COLD, "ep_tool_1760000000008"))
      and any(x["ep"] == "ep_tool_1760000000008" and x["how"] == "recovered" for x in ledger()), rec)
check("(c) a recorded move's leftover hot copy is removed", not os.path.exists(os.path.join(HOT, ".moved-ep_tool_1760000000001")), rec)
check("(d) an unrecorded leftover is put back, not removed",
      "ep_tool_1760000000009" in rec["restored"] and os.path.isdir(os.path.join(HOT, "ep_tool_1760000000009")), rec)


def _half_copy(src, dst):
    os.makedirs(dst)
    shutil.copy2(os.path.join(src, "ep.k"), dst)
    raise OSError("the disk went away mid-copy")


EC._same_device, EC._copytree = (lambda a, b: False), _half_copy
r = EC.run(now=NOW)
check("(e) a crash mid-copy is an error, and the source is untouched",
      [x["ep"] for x in r.get("error", [])] == ["ep_tool_1760000000007"]
      and snap(os.path.join(HOT, "ep_tool_1760000000007")) == {"ep.k": 1000, "ep.v": 500}, r.get("error"))
EC._copytree = REAL["copy"]
r = EC.run(now=NOW)
check("(e) the next pass rolls the half copy back and moves it whole",
      "ep_tool_1760000000007" in (r.get("recovered") or {}).get("rolled_back", [])
      and {x["ep"] for x in r.get("moved", [])} == {"ep_tool_1760000000007"}
      and snap(os.path.join(COLD, "ep_tool_1760000000007")) == {"ep.k": 1000, "ep.v": 500}, r)
episode(os.path.join(HOT, "ep_tool_1760000000010"))
REG0 = write_rows(ROWS + [dead("c", os.path.join(HOT, "ep_tool_1760000000007")), dead("f", os.path.join(HOT, "ep_tool_1760000000010"))])


def _locked(p, *a, **k):
    raise PermissionError("in use by another process")


EC._rmtree = _locked
r = EC.run(now=NOW)
check("(f) a hot copy that cannot be removed still records the move",
      "ep_tool_1760000000010" in {x["ep"] for x in r.get("moved", [])} and any(x["ep"] == "ep_tool_1760000000010" for x in ledger()), r)
check("(f) ...and the row still resolves to a whole copy",
      epdir.resolve(os.path.join(HOT, "ep_tool_1760000000010"))[0] is not None)
EC._rmtree, EC._same_device = REAL["rm"], REAL["same"]
rec = EC.recover(EC.config())
check("(f) ...and the next pass removes the leftover",
      not os.path.exists(os.path.join(HOT, ".moved-ep_tool_1760000000010")) and "ep_tool_1760000000010" in rec["finished"], rec)

# (g) NO DELETION ON A SIZE MATCH. Two trees can agree on total bytes and file count and
# differ in a byte; a hot copy is removed only when every file's sha256 matches.
E1, E2 = "ep_tool_1760000000001", "ep_tool_1760000000002"     # both cold and recorded


def flipped(path):
    episode(path)
    with open(os.path.join(path, "ep.v"), "wb") as f:
        f.write(b"v" * 499 + b"w")                               # same size, one byte differs


flipped(os.path.join(HOT, E1))
flipped(os.path.join(HOT, ".moved-" + E2))
rec = EC.recover(EC.config())
check("(g) a hot copy with the same sizes but one different byte survives, counted conflict",
      E1 in rec["conflicts"] and os.path.isfile(os.path.join(HOT, E1, "ep.v"))
      and open(os.path.join(HOT, E1, "ep.v"), "rb").read()[-1:] == b"w"
      and snap(os.path.join(COLD, E1)) == {"ep.k": 1000, "ep.v": 500}, rec)
check("(g) ...and so does a leftover .moved- copy that differs",
      E2 in rec["conflicts"] and os.path.isdir(os.path.join(HOT, ".moved-" + E2)), rec)
shutil.rmtree(os.path.join(HOT, E1), ignore_errors=True)        # gone already only under a mutant
shutil.rmtree(os.path.join(HOT, ".moved-" + E2), ignore_errors=True)
os.makedirs(os.path.join(HOT, ".moved-" + E2))
shutil.copy2(os.path.join(COLD, E2, "ep.k"), os.path.join(HOT, ".moved-" + E2))
rec = EC.recover(EC.config())
check("(g) a leftover cut off half-way through its removal (a matching subset) is finished",
      E2 in rec["finished"] and not os.path.exists(os.path.join(HOT, ".moved-" + E2)), rec)

# (h) ADOPT ONLY WHAT IS HERS. A cold root someone shares holds other things.
os.makedirs(os.path.join(COLD, "holiday-photos"))
with open(os.path.join(COLD, "holiday-photos", "a.jpg"), "wb") as f:
    f.write(b"j" * 10)
episode(os.path.join(COLD, "ep_tool_1760000000999"))              # the right shape, no row names it
n_ledger = len(ledger())
rec = EC.recover(EC.config())
check("(h) an unrelated folder and an unnamed episode-shaped one are never adopted",
      rec["adopted"] == [] and {"holiday-photos", "ep_tool_1760000000999"} <= set(rec["foreign"])
      and len(ledger()) == n_ledger, rec)
check("(h) ...and are left exactly as they were",
      snap(os.path.join(COLD, "holiday-photos")) == {"a.jpg": 10}
      and snap(os.path.join(COLD, "ep_tool_1760000000999")) == {"ep.k": 1000, "ep.v": 500})

# (i) A LOCKED PARTIAL SKIPS ITS EPISODE, NOT THE PASS.
EL, EM, EG = "ep_tool_1760000000011", "ep_tool_1760000000012", "ep_tool_1760000000013"
for e in (EL, EM, EG):
    episode(os.path.join(HOT, e))
for e in (EL, EM):
    shutil.copytree(os.path.join(HOT, e), os.path.join(COLD, ".partial-" + e))
REG0 = write_rows(ROWS + [dead("c", os.path.join(HOT, "ep_tool_1760000000007")),
                          dead("f", os.path.join(HOT, "ep_tool_1760000000010")),
                          dead("l", os.path.join(HOT, EL)), live("m", os.path.join(HOT, EM)),
                          dead("g", os.path.join(HOT, EG))])


def _locked_partial(p, *a, **k):
    if os.path.basename(os.path.normpath(p)) == ".partial-" + EL:
        raise PermissionError("in use by another process")
    return REAL["rm"](p, *a, **k)


EC._rmtree = _locked_partial
try:
    r = EC.run(now=NOW)
finally:
    EC._rmtree = REAL["rm"]
rcv = r.get("recovered") or {}
check("(i) a locked partial is counted locked, and the pass goes on",
      r.get("ok") is True and EL in rcv.get("locked", []) and EM in rcv.get("rolled_back", [])
      and EG in {x["ep"] for x in r.get("moved", [])}, r)
check("(i) ...its episode is skipped this pass and both its copies are kept",
      r.get("skipped", {}).get("locked") == 1 and os.path.isdir(os.path.join(HOT, EL))
      and os.path.isdir(os.path.join(COLD, ".partial-" + EL)), r.get("skipped"))

print("§8 the registry is never written")
check("the registry is byte-identical after every pass", reg_bytes() == REG0)
src = _code(EC.__file__)
# Not replace_atomic: that is store_io's shared rename-with-retry, which every store writer
# must use (G-STORE-WRITES) and which the mover uses for its directory renames. What keeps
# the registry unwritten is the byte check above and the absence of these names.
banned = [t for t in ("_save_all", "commit_row", "_REG_LOCK", "registry_lock",
                      "SP_RECALL_REGISTRY", "registry.jsonl", "eps-moves.jsonl") if t in src]
check("the mover names none of the registry's writers, nor either file", not banned, banned)
check("...reads rows only through the audit door", "all_rows(" in src)
check("...and learns the ledger's path from epdir alone", "_epdir.ledger_path()" in src)

print("§9 one pass at a time")
EC._MOVE_LOCK.acquire()
try:
    r = EC.run(now=NOW)
finally:
    EC._MOVE_LOCK.release()
check("a second pass while one runs is skipped, not interleaved",
      r.get("ok") is False and "already running" in str(r.get("skipped")), r)

finish("G-EPS-COLD-MOVE")
