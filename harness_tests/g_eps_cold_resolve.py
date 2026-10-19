"""G-EPS-COLD-RESOLVE — an episode the cold tier moved is still found, through the ledger. OFFLINE.

D2 (spec docs/superpowers/specs/2026-10-19-memory-direction-design.md §6). The read-time
resolver from the moved-root repair (commit 1a17877) answers "as written" or "under SP_EPS_DIR".
The cold tier moves dead episodes to SP_EPS_COLD_DIR and records each move in
eps-moves.jsonl, beside the registry. The resolver learns the move from that ledger and
nowhere else: the location comes from the profile, so the store stays portable between
machines, and an absolute `to` cannot go stale the way the old-root rows did.

  §1 the four answers: hot root, cold (ledger-named), cold-but-unrecorded = missing, missing
  §2 portable: a backslash-written dir resolves anywhere; case-agnostic on Windows only
  §3 the ledger is re-read when it grows
  §4 the census counts the cold tier
  §5 one harness reader of SP_EPS_COLD_DIR (epdir.py)
  §6 the daemon side (omitted where engine/ is absent, as in the public export)

The daemon's behaviour is asserted by the Rust test recall::eps_cold_tests, which needs the
engine toolchain:
    cargo test --lib eps_cold_tests     (engine/tools/sp_daemon; SP_SYSTEM_* as in the build)

    python harness_tests/g_eps_cold_resolve.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness_tests._gate import sandbox, check, finish, omit, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_eps_cold_resolve")  # FIRST, before any harness. import

HOT = os.environ["SP_EPS_DIR"].replace("\\", "/")
COLD = os.environ["SP_EPS_COLD_DIR"].replace("\\", "/")
GONE = os.path.join(SB, "gone-root").replace("\\", "/")
for d in (HOT + "/ep-hot", COLD + "/ep-cold", COLD + "/ep-stray"):
    os.makedirs(d, exist_ok=True)
LEDGER = os.path.join(os.path.dirname(os.environ["SP_RECALL_REGISTRY"]), "eps-moves.jsonl")
os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
with open(LEDGER, "w", encoding="utf-8") as f:
    f.write(json.dumps({"ep": "ep-cold", "how": "move"}) + "\n")
    f.write("not json\n")
    f.write("[1, 2]\n")

from harness.skills import epdir  # noqa: E402


def _code(path):
    """Source with comments and docstrings removed — a gate that greps prose passes on the explanation."""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    if path.endswith(".rs"):
        return re.sub(r"//[^\n]*", "", src)
    return re.sub(r'(?s)""".*?"""', "", re.sub(r"#[^\n]*", "", src))


print("§1 the four answers")
check("hot: a stale-root episode resolves under SP_EPS_DIR",
      epdir.resolve(GONE + "/ep-hot") == (HOT + "/ep-hot", epdir.MOVED), epdir.resolve(GONE + "/ep-hot"))
check("cold: the ledger names it and the cold root has it",
      epdir.resolve(GONE + "/ep-cold") == (COLD + "/ep-cold", epdir.COLD), epdir.resolve(GONE + "/ep-cold"))
check("a cold dir the ledger does not name is MISSING (the ledger is the one place a move is learned)",
      epdir.resolve(GONE + "/ep-stray") == (None, epdir.MISSING), epdir.resolve(GONE + "/ep-stray"))
check("missing everywhere is MISSING", epdir.resolve(GONE + "/ep-lost") == (None, epdir.MISSING))
check("no cold root: the cold tier is off",
      epdir.resolve(GONE + "/ep-cold", cold="") == (None, epdir.MISSING))
check("malformed ledger lines are skipped, not fatal", epdir.moved_names() == frozenset({epdir.ep_key("ep-cold")}),
      epdir.moved_names())

print("§2 portable")
check("a backslash-written dir resolves by its basename on any OS",
      epdir.resolve(GONE.replace("/", "\\") + "\\ep-cold")[1] == epdir.COLD)
if os.name == "nt":
    check("case-agnostic on Windows", epdir.resolve(GONE + "/EP-COLD")[1] == epdir.COLD)
else:
    omit("case-agnostic on Windows", "POSIX filesystems are case-sensitive; an exact match is right here")
check("the ledger lives beside the registry",
      os.path.normcase(os.path.abspath(epdir.ledger_path())) == os.path.normcase(os.path.abspath(LEDGER)))

print("§3 the ledger is re-read when it grows")
os.makedirs(COLD + "/ep-late", exist_ok=True)
check("before its ledger row, ep-late is missing", epdir.resolve(GONE + "/ep-late")[1] == epdir.MISSING)
with open(LEDGER, "a", encoding="utf-8") as f:
    f.write(json.dumps({"ep": "ep-late", "how": "move"}) + "\n")
check("after its ledger row, ep-late is cold", epdir.resolve(GONE + "/ep-late")[1] == epdir.COLD)

print("§4 the census counts the cold tier")
c = epdir.census([{"dir": GONE + "/ep-hot"}, {"dir": GONE + "/ep-cold"}, {"dir": GONE + "/ep-lost"}])
check("one moved, one cold, one missing",
      (c[epdir.MOVED], c[epdir.COLD], c[epdir.MISSING]) == (1, 1, 1), c)

print("§5 one harness reader of SP_EPS_COLD_DIR")
readers = []
for dp, _dn, fns in os.walk(os.path.join(ROOT, "harness")):
    for fn in fns:
        if fn.endswith(".py") and re.search(r"environ[^\n]*SP_EPS_COLD_DIR", _code(os.path.join(dp, fn))):
            readers.append(fn)
check("SP_EPS_COLD_DIR has one reader, epdir.py", readers == ["epdir.py"], readers)

print("§6 the daemon side")
RS = os.path.join(ROOT, "engine", "tools", "sp_daemon", "src", "recall.rs")
if not os.path.exists(RS):
    omit("the daemon resolver", "engine/ is not in this tree (the public export ships no engine)")
else:
    rs = _code(RS)
    m = re.search(r"pub fn load_registry_report\b(.*?)\n}\n", rs, re.S)
    body = m.group(1) if m else ""
    check("load_registry_report takes the cold root and the moved set",
          re.search(r"pub fn load_registry_report\(path: &Path, eps_root: Option<&str>, cold_root: Option<&str>, moved: &HashSet<String>\)", rs) is not None)
    check("a Cold row loads from the resolved path, not the row's",
          re.search(r"EpisodeDir::Cold\((\w+)\)\s*=>\s*\{[^}]*\b\1\s*\}", body) is not None)
    check("the cold step is gated on the ledger",
          re.search(r"moved\.contains\(&ep_key\(base\)\)", rs) is not None)
    check("load_registry reads the ledger beside the registry and SP_EPS_COLD_DIR",
          re.search(r"pub fn load_registry\(.*?SP_EPS_COLD_DIR.*?load_moved_names\(&eps_moves_path\(path\)\)", rs, re.S) is not None)
    check("the ledger's name is spelled once", rs.count('"eps-moves.jsonl"') == 1, rs.count('"eps-moves.jsonl"'))
    check("the daemon reader still never writes the registry", "fs::write" not in body)

finish("G-EPS-COLD-RESOLVE")
