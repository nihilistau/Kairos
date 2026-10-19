"""G-EPS-COLD-WIRE — the cold tier is wired, OFF in public, and portable. OFFLINE.

D2, spec §2 constraint 8: no path or drive letter hard-coded; the public default is OFF and
the boot line says so with the arming condition; every threshold is a profile knob with the
spec's value as its default; paths are case- and separator-agnostic; nothing Windows-only.

  §1 sp (the public profile): no cold root, unarmed, the spec's thresholds
  §2 his profile, when present: a root set, still unarmed (the dry run comes first)
  §3 OFF says so, with the arming condition, and touches nothing
  §4 the boot line names the state, whether the root exists, and both disks' free space,
     and creates nothing
  §5 wiring: the nightly step (after reflect, before the prefix refresh), the boot line,
     the route (POST runs, defaulting to a dry run; GET reads the state)
  §6 no drive letter or absolute root in the new code
  §7 Linux path handling: nothing Windows-only; containment compared the OS's way

    python harness_tests/g_eps_cold_wire.py
"""
import collections
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness_tests._gate import sandbox, check, finish, omit, utf8_stdout  # noqa: E402
from harness_tests import _src as _srcmod  # noqa: E402

utf8_stdout()
SB = sandbox("g_eps_cold_wire")  # FIRST, before any harness. import

try:
    import tomllib
except ImportError:                                   # pragma: no cover
    import tomli as tomllib  # type: ignore
import serve  # noqa: E402
from harness.maintenance import eps_cold as EC  # noqa: E402


def _code(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    if path.endswith(".rs"):
        return re.sub(r"//[^\n]*", "", src)
    return _strip(src)


def _strip(src):
    """Python source without comments or docstrings (memory: "my comment is the gate's subject")."""
    return re.sub(r'(?s)""".*?"""', "", re.sub(r"#[^\n]*", "", src))


DRIVE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]")
Usage = collections.namedtuple("Usage", "total used free")

print("§1 the public default is OFF")
env = serve.build_env(serve.load_profile("sp"))
check("sp: no cold root", env.get("SP_EPS_COLD_DIR", "") == "", env.get("SP_EPS_COLD_DIR"))
check("sp: not armed", env.get("SP_EPS_COLD_ARMED") == "0", env.get("SP_EPS_COLD_ARMED"))
check("sp: the spec's thresholds are the defaults",
      (env.get("SP_EPS_COLD_AFTER_DAYS"), env.get("SP_EPS_COLD_MIN_FREE_GB"), env.get("SP_EPS_HOT_WARN_FREE_GB"))
      == ("30", "20", "30"),
      (env.get("SP_EPS_COLD_AFTER_DAYS"), env.get("SP_EPS_COLD_MIN_FREE_GB"), env.get("SP_EPS_HOT_WARN_FREE_GB")))
with open(os.path.join(ROOT, "profiles", "sp.toml"), "rb") as f:
    sp_mem = tomllib.load(f)["memory"]
check("sp.toml writes the OFF state down, not by omission",
      sp_mem.get("eps_cold_dir") == "" and sp_mem.get("eps_cold_armed") is False, sp_mem)

print("§2 his profile")
# THE EXPORT IS DETECTED BY ITS OWN MARKER, NOT BY A PROFILE'S ABSENCE (2026-10-19). The scrub
# renames his profile to the public companion profile, which the export DOES ship (with no cold
# root), so "is his profile here?" passed in Kairos and this leg failed there against the wrong
# profile. KAIROS-SOURCE.txt exists only inside the export (the g_delegate / g_src_trap pattern).
if (os.path.exists(os.path.join(ROOT, "KAIROS-SOURCE.txt"))
        or not os.path.exists(os.path.join(ROOT, "profiles", "companion.toml"))):
    omit("his profile", "this is the public export, or his profile is not in this tree")
else:
    his = serve.load_profile("companion")
    henv = serve.build_env(his)
    check("a cold root is set on his profile, and mapped as written",
          bool(his["memory"].get("eps_cold_dir")) and henv.get("SP_EPS_COLD_DIR") == his["memory"]["eps_cold_dir"],
          henv.get("SP_EPS_COLD_DIR"))
    # ARMED BY THE OPERATOR (2026-10-20), after the dry run. Arming is his decision, not the
    # code's, so the gate does not pin a state: it holds that whichever state the profile is
    # in, the off-ledger says the same (an armed tier is recorded as ARMED in §19; an
    # unarmed one is not).
    _armed = henv.get("SP_EPS_COLD_ARMED") == "1"
    _ledger = open(os.path.join(ROOT, "docs", "OFF-BY-DEFAULT.md"), encoding="utf-8").read()
    _sec = next((l for l in _ledger.splitlines() if l.startswith("### 19.")), "")
    check("...and its armed state is the one the off-ledger records",
          _armed == ("**ARMED" in _sec), (henv.get("SP_EPS_COLD_ARMED"), _sec[:80]))
    check("...at the spec's thresholds",
          (henv.get("SP_EPS_COLD_AFTER_DAYS"), henv.get("SP_EPS_COLD_MIN_FREE_GB"),
           henv.get("SP_EPS_HOT_WARN_FREE_GB")) == ("30", "20", "30"))

print("§3 OFF says so, and touches nothing")
os.environ["SP_EPS_COLD_DIR"] = ""
os.environ["SP_EPS_HOT_WARN_FREE_GB"] = "0"
before = sorted(os.listdir(SB))
r = EC.run()
check("no cold root: the pass is off", r.get("off") is True and r.get("ok") is True, r)
check("...and says how to arm it",
      "eps_cold_dir" in r.get("line", "") and "eps_cold_armed" in r.get("line", "")
      and "OFF-BY-DEFAULT" in r.get("line", ""), r.get("line"))
check("...and so does the boot line", EC.boot_report().startswith(EC.OFF_LINE))
check("...whose state field says off", "state=off" in EC.boot_report(), EC.boot_report())
check("...and nothing was created", sorted(os.listdir(SB)) == before)

print("§4 the boot line: the state, the root's existence, both disks")
HOT, COLD = os.path.join(SB, "hot"), os.path.join(SB, "cold")
os.makedirs(HOT)
os.environ["SP_EPS_DIR"] = HOT
os.environ["SP_EPS_COLD_DIR"] = COLD                  # set, and NOT created
REAL_DU = EC._disk_usage
EC._disk_usage = lambda p: Usage(10 ** 12, 10 ** 12 - int(28e9), int(28e9))
os.environ["SP_EPS_HOT_WARN_FREE_GB"] = "30"
line = EC.boot_report()
first = line.split("\n")[0]
check("a root set, unarmed: DRY RUN, and the state field says so",
      first.startswith(EC.DRY_LINE % EC.config().cold) and "state=dry-run" in first, first)
check("...a missing root says MISSING and that it is made by hand, never by the mover",
      "cold_root=missing" in first and "by hand" in first, first)
check("...with the hot disk's free space, in the mint floor's units", "hot_free=28.00 GB" in first, first)
check("...and the cold disk's as unknown, since there is no root to ask", "cold_free=unknown" in first, first)
check("...the hot-disk warning rides on its own line, with numbers",
      "\n" in line and "28.00 GB free" in line.split("\n")[1]
      and "eps_hot_warn_free_gb = 30" in line.split("\n")[1], line)
check("...and the boot line did not create the root", not os.path.exists(COLD))
os.makedirs(COLD)
first = EC.boot_report().split("\n")[0]
check("an existing root says exists, with its free space",
      "cold_root=exists" in first and "cold_free=28.00 GB" in first, first)
os.environ["SP_EPS_COLD_ARMED"] = "1"
first = EC.boot_report().split("\n")[0]
check("armed: ARMED, and the state field says so",
      first.startswith(EC.ARMED_LINE % EC.config().cold) and "state=armed" in first, first)
os.environ.pop("SP_EPS_COLD_ARMED", None)
os.environ["SP_EPS_HOT_WARN_FREE_GB"] = "0"
check("...no warning line under the floor's knob", "\n" not in EC.boot_report())
st = EC.status()
check("status() carries the same facts, for the GET route",
      st.get("state") == "dry-run" and st.get("cold_exists") is True and st.get("hot_free_gb") == 28.0
      and st.get("cold_free_gb") == 28.0 and st.get("ok") is True, st)
EC._disk_usage = REAL_DU

print("§5 wiring")
day = _code(os.path.join(ROOT, "harness", "server", "day.py"))
m = re.search(r"def run_consolidation\b(.*?)\ndef ", day, re.S)
body = m.group(1) if m else ""
i_ref, i_ec, i_pre = body.find('"step": "reflect"'), body.find("_ec.run()"), body.find('"step": "prefix_refresh"')
check("the nightly pass runs the cold tier after reflect and before the prefix refresh",
      0 <= i_ref < i_ec < i_pre, (i_ref, i_ec, i_pre))
check("...as its own step, `eps_cold`", '"step": "eps_cold"' in body)
m = re.search(r"def start_consolidation_ticker\b(.*?)SP_CONSOLIDATE_HOUR", day, re.S)
check("the boot line is printed before the ticker's hour check", bool(m) and "boot_report()" in m.group(1))
# The gateway PACKAGE, not one file (G-SRC-TRAP): a route that moves to a sibling module
# must still be found, never silently absent.
app = _strip(_srcmod.pkg("harness", "server"))
check("POST /v1/maintenance/eps_cold exists and defaults to a dry run",
      'p == "/v1/maintenance/eps_cold"' in app
      and 'run(dry_run=body.get("dry_run", True) is not False)' in app)
check("GET /v1/maintenance/eps_cold reads the state and moves nothing",
      re.search(r'"/v1/maintenance/eps_cold":\s*lambda:[^,]{0,120}?eps_cold[^,]*,[^)]*\)\.status\(\)', app)
      is not None)
sv = _code(os.path.join(ROOT, "serve.py"))
for k, key in (("SP_EPS_COLD_DIR", "eps_cold_dir"), ("SP_EPS_COLD_ARMED", "eps_cold_armed"),
               ("SP_EPS_COLD_AFTER_DAYS", "eps_cold_after_days"),
               ("SP_EPS_COLD_MIN_FREE_GB", "eps_cold_min_free_gb"),
               ("SP_EPS_HOT_WARN_FREE_GB", "eps_hot_warn_free_gb")):
    check("serve.py maps %s from [memory].%s" % (k, key),
          re.search(r'"%s":[^\n]*mem\.get\("%s"' % (k, key), sv) is not None)

print("§6 no drive letter or absolute root in the new code")
for rel in (("harness", "maintenance", "eps_cold.py"), ("harness", "skills", "epdir.py")):
    hits = DRIVE.findall(_code(os.path.join(ROOT, *rel)))
    check("%s names no drive" % rel[-1], not hits, hits)
RS = os.path.join(ROOT, "engine", "tools", "sp_daemon", "src", "recall.rs")
if not os.path.exists(RS):
    omit("recall.rs names no drive", "engine/ is not in this tree")
else:
    rs = _code(RS)
    fns = "".join(mm.group(0) for mm in re.finditer(
        r"pub fn (resolve_episode_dir|ep_key|ep_basename|eps_moves_path|load_moved_names)\b.*?\n}\n", rs, re.S))
    check("the daemon's cold-tier functions name no drive", len(fns) > 200 and not DRIVE.findall(fns), DRIVE.findall(fns))

print("§7 Linux path handling")
WIN_ONLY = ("windll", "GlobalMemoryStatusEx", "msvcrt", "winreg", "startfile", "GetDiskFreeSpace", "ctypes", "win32")
for rel in (("harness", "maintenance", "eps_cold.py"), ("harness", "skills", "epdir.py")):
    src = _code(os.path.join(ROOT, *rel))
    bad = [t for t in WIN_ONLY if t in src]
    check("%s calls nothing Windows-only" % rel[-1], not bad, bad)
    check("%s joins no path with a literal backslash" % rel[-1], '+ "\\\\" +' not in src and "'\\\\' +" not in src)
hot = os.path.join(SB, "Hot")
check("containment: a direct child is under its root", EC._under(hot, os.path.join(hot, "ep-1")))
check("...a sibling with a shared prefix is not", not EC._under(hot, os.path.join(SB, "Hotter", "ep-1")))
check("...a grandchild is not", not EC._under(hot, os.path.join(hot, "x", "ep-1")))
if os.name == "nt":
    check("...and on Windows case and separators do not matter",
          EC._under(hot, hot.lower().replace("\\", "/") + "/ep-1"))
else:
    check("...and on POSIX case does matter", not EC._under(hot, hot.lower() + "/ep-1"))

finish("G-EPS-COLD-WIRE")
