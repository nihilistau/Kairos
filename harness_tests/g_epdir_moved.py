"""G-EPDIR-MOVED — an episode the store moved is still found; one that is gone is skipped. OFFLINE.

THE FINDING (2026-10-19). On 2026-09-06 the operator moved her episode store from
the old disk to a new root (the old one was too small). Registry rows are append-only and carry an ABSOLUTE
`dir`, so 1,287 rows still named the old root, where nothing is left:

    live         539 exist under the new root    216 exist nowhere
    tombstoned   365 exist under the new root    167 exist nowhere

Every one of the 383 that exist nowhere has npos=0: the KV was never minted, so nothing of
hers was in them. The daemon read `dir` straight off the row and every ep.k / ep.l5 /
ep.okf.md load fell into an `unwrap_or` — `loaded 1999 episode(s)` at boot, no count of how
many could not be opened.

THE FIX: resolve at READ, never rewrite the row. One resolver per side:
  daemon   recall.rs::resolve_episode_dir, called by load_registry_report — the only place
           an Episode's `dir` comes from; Missing rows are left out and named in the census
  harness  harness/skills/epdir.py, called by semindex.read_ep_l5 — the only harness
           function that opens an episode file by a row's `dir`

WHAT THIS HOLDS:
  §1 through the real harness reader (semindex.backfill -> mint -> read_ep_l5): the episode
     on the old root and the moved one both index from their ep.l5; the missing one degrades
     to hash-space without error
  §2 the census (verify_registry's stats) counts one moved and one missing, BY NAME
  §3 the registry fixture is byte-identical afterwards: nothing wrote it
  §4 the daemon side: load_registry_report resolves `dir` before any episode load, a Missing
     row `continue`s, and no other daemon source reads a row's `dir`
  §5 the harness side: SP_EPS_DIR has one reader (epdir.py)

The daemon's behaviour (moved loads, missing skipped by name, registry untouched) is
asserted by the Rust test recall::epdir_tests, which needs the engine toolchain:
    cargo test --lib epdir_tests     (engine/tools/sp_daemon; SP_SYSTEM_* as in the build)

    python harness_tests/g_epdir_moved.py
"""
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness_tests._gate import sandbox, check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_epdir_moved")  # FIRST, before any harness. import
os.environ["SP_SEM_INDEX"] = os.path.join(SB, "memory", "semindex.jsonl")
os.environ["SP_SEM_MINT"] = "1"
os.environ["SP_SEM_AUX_EMBED"] = "0"

import json  # noqa: E402

OLD = os.path.join(SB, "old-root").replace("\\", "/")      # the F: of this fixture
NEW = os.environ["SP_EPS_DIR"].replace("\\", "/")          # the C: of this fixture


def _episode(path, seed):
    os.makedirs(path, exist_ok=True)
    v = [0.0] * 512
    v[seed] = 1.0
    with open(os.path.join(path, "ep.l5"), "wb") as f:
        f.write(struct.pack("<512f", *v))
    return v


v_here = _episode(OLD + "/ep-here", 3)
v_moved = _episode(NEW + "/ep-moved", 7)
os.makedirs(OLD, exist_ok=True)                            # ep-lost exists on neither root

ROWS = [
    {"text": "the bench is oak", "ts": "2026-10-01T00:00:00Z", "dir": OLD + "/ep-here", "npos": 4,
     "lifecycle": 0, "speaker": "user", "src": "fixture", "sig_bits": "0" * 64},
    {"text": "the kettle whistles", "ts": "2026-10-02T00:00:00Z", "dir": OLD + "/ep-moved", "npos": 4,
     "lifecycle": 0, "speaker": "user", "src": "fixture", "sig_bits": "0" * 64},
    {"text": "the gate squeaks", "ts": "2026-10-03T00:00:00Z", "dir": OLD + "/ep-lost", "npos": 0,
     "lifecycle": 0, "speaker": "user", "src": "fixture", "sig_bits": "0" * 64},
]
REG = os.environ["SP_RECALL_REGISTRY"]
with open(REG, "w", encoding="utf-8") as f:
    for r in ROWS:
        f.write(json.dumps(r) + "\n")
with open(REG, "rb") as f:
    REG_BEFORE = f.read()

from harness.skills import semindex as S  # noqa: E402
from harness.skills import epdir  # noqa: E402
from harness.skills.memory import verify_registry  # noqa: E402
from harness.skills.memory import health as H  # noqa: E402

print("§1 the real harness reader")
got = S.backfill(ROWS)
check("backfill indexed all three, refused none", got.get("minted") == 3 and got.get("refused") == 0, got)
idx = S.load()


def _row(r):
    return idx.get((S.addr_of(r["text"]), r["ts"])) or {}


check("the episode still on its own root indexes from its ep.l5",
      _row(ROWS[0]).get("model") == S.MODEL_L5 and _row(ROWS[0]).get("vec") == v_here, _row(ROWS[0]).get("model"))
check("the MOVED episode indexes from its ep.l5 under SP_EPS_DIR",
      _row(ROWS[1]).get("model") == S.MODEL_L5 and _row(ROWS[1]).get("vec") == v_moved, _row(ROWS[1]).get("model"))
check("the missing episode degrades to hash-space, no error",
      _row(ROWS[2]).get("model") == S.MODEL_HASH, _row(ROWS[2]).get("model"))
check("resolve() names each case",
      [epdir.resolve(r["dir"])[1] for r in ROWS] == [epdir.AS_WRITTEN, epdir.MOVED, epdir.MISSING],
      [epdir.resolve(r["dir"]) for r in ROWS])

print("§2 the census, by name")
stats, _status = H._registry_health()
check("health reports one moved, one missing",
      stats.get("eps_moved") == 1 and stats.get("eps_missing") == 1, {k: stats.get(k) for k in ("eps_moved", "eps_missing")})
check("the missing one is named", epdir.census([])["missing_names"] == ["ep-lost"], epdir.census([]))
verify_registry()

print("§3 nothing wrote the registry")
with open(REG, "rb") as f:
    check("registry byte-identical after backfill + health + verify", f.read() == REG_BEFORE)


def _code(path):
    """Source with comments removed — a gate that greps prose passes on the explanation."""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    if path.endswith(".rs"):
        return re.sub(r"//[^\n]*", "", src)
    return re.sub(r'(?s)""".*?"""', "", re.sub(r"#[^\n]*", "", src))


print("§4 the daemon side, one place")
DSRC = os.path.join(ROOT, "engine", "tools", "sp_daemon", "src")
# THE PUBLIC TREE SHIPS NO DAEMON SOURCE (Kairos has no engine/). There the daemon leg has no
# subject and is omitted, by name; everything else in this gate still runs.
HAVE_DAEMON = os.path.exists(os.path.join(DSRC, "recall.rs"))
rs = _code(os.path.join(DSRC, "recall.rs")) if HAVE_DAEMON else ""
if HAVE_DAEMON:
    m = re.search(r"pub fn load_registry_report\b(.*?)\n}\n", rs, re.S)
    body = m.group(1) if m else ""
    i_res = body.find("resolve_episode_dir(")
    loads = [body.find(n) for n in ("load_episode_global_k(", "load_episode_l5key(", "load_episode_okf_policy(")]
    check("load_registry_report exists", bool(body))
    check("the row's dir is resolved before every episode load",
          i_res >= 0 and all(i > i_res for i in loads), (i_res, loads))
    check("a Moved row loads from the resolved path, not the row's",
          re.search(r"EpisodeDir::Moved\((\w+)\)\s*=>\s*\{[^}]*\b\1\s*\}", body) is not None
          and re.search(r"let dir = resolved\b", body) is not None)
    check("a Missing row is skipped",re.search(r"EpisodeDir::Missing\s*=>\s*\{[^}]*continue", body) is not None)
    check("load_registry goes through load_registry_report",
          re.search(r"pub fn load_registry\(.*?load_registry_report\(", rs, re.S) is not None)
    check("the daemon reader never writes the registry", "fs::write" not in body)
    readers = []
    for fn in os.listdir(DSRC):
        if fn.endswith(".rs"):
            for mm in re.finditer(r'get\("dir"\)', _code(os.path.join(DSRC, fn))):
                readers.append(fn)
    check("no other daemon source reads a row's dir", readers == ["recall.rs"], readers)
else:
    print("  omitted  §4: no daemon source in this tree (the public Kairos export)")

print("§5 the harness side, one place")
env_readers = []
for dp, _dn, fns in os.walk(os.path.join(ROOT, "harness")):
    for fn in fns:
        if fn.endswith(".py") and re.search(r"environ[^\n]*SP_EPS_DIR", _code(os.path.join(dp, fn))):
            env_readers.append(fn)
check("SP_EPS_DIR has one reader, epdir.py", env_readers == ["epdir.py"], env_readers)
check("read_ep_l5 resolves through epdir",
      re.search(r"def read_ep_l5\(.*?_epdir\.resolve\(", _code(os.path.join(ROOT, "harness", "skills", "semindex.py")), re.S)
      is not None)

finish("G-EPDIR-MOVED")
