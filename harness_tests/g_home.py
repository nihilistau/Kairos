"""G-HOME — a companion is a folder, and every store resolves through ONE table. OFFLINE.

WHY (2026-11-26, design docs/DESIGN-2026-11-26-homes-people-setup.md §1): her state lived at
about twenty paths, built in serve.py and again as a fallback in each reader, several of which
ignored the env entirely (agency_feed, the journal panel). Nothing could name "her" as a unit,
and the external-engine profile shared her persona.md and tuning.json. harness/home.py is the
table now; serve.py takes every state path from the home, and refuses a profile that names one
too.

  1. a fresh home resolves every store inside itself, with its own name and backup folder
  2. a home that cannot be used as written is refused, by name
  3. HER ADOPTION MOVED NOTHING: companion resolves every store where it was before the home
  4. serve.py refuses two sources for one store, and a home + a profile name for her
  5. a second companion shares no store with her
  6. the gate sandbox covers every store in the table
  7. the readers honour the resolver (the ones that used to read the repo-root literal)
  8. the backup takes the home's stores, names the companion, and keeps out of her folder
  9. no harness module builds a memory-okf path outside the table

Run: python harness_tests/g_home.py
"""
from __future__ import annotations

import io
import os
import re
import sys
import tokenize
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from _gate import _STORE_ENV, check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_home")
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"

from harness import home as H  # noqa: E402

N = lambda p: os.path.normcase(os.path.normpath(p))  # noqa: E731
inside = lambda p, d: N(p).startswith(N(d) + os.sep)  # noqa: E731

H.COMPANIONS_DIR = os.path.join(SB, "companions")     # the owner's global, read at call time
_REAL_VAR = H.VAR
H.VAR = os.path.join(SB, "var")

print("1. a fresh home resolves every store inside itself")
tmpl = os.path.join(ROOT, "kairos-export", "persona-template")
home = H.create("ivy", "Ivy", persona_template=tmpl if os.path.isdir(tmpl) else "")
env = H.env_for(home)
check("SP_HOME is the folder", N(env["SP_HOME"]) == N(home), env["SP_HOME"])
check("her name comes from companion.toml", env["SP_COMPANION_NAME"] == "Ivy"
      and env["SP_COMPANION_ID"] == "ivy", (env["SP_COMPANION_ID"], env["SP_COMPANION_NAME"]))
outside = [v for k, (v_, *_r) in H.KEYS.items() for v in [env[v_]] if not inside(v, home)]
check("every store in the table lives inside the home", not outside, outside[:3])
check("every KEYS env var is set", all(H.KEYS[k][0] in env for k in H.KEYS))
check("the personality tier's two names agree",
      env["SP_PERSONALITY_TIER"] == env["SP_PERSONALITY_OKF_ROOT"])
check("its backups go to var/backups/<id>",
      N(env["SP_BACKUP_DIR"]) == N(os.path.join(H.VAR, "backups", "ivy")), env["SP_BACKUP_DIR"])


def _try(f):
    try:
        f()
        return False
    except H.HomeError:
        return True


check("create refuses an existing home (never overwrites)", _try(lambda: H.create("ivy")))
check("create refuses a bad id", _try(lambda: H.create("Ivy Two")) and _try(lambda: H.create("../x")))
check("list_homes sees it", [h["id"] for h in H.list_homes()] == ["ivy"], H.list_homes())
H.COMPANIONS_DIR = os.path.join(ROOT, "companions")   # back to the real one for her (§3)

print("\n2. a home that cannot be used as written is refused, by name")
bad = os.path.join(SB, "bad")
os.makedirs(bad)
check("a folder with no companion.toml", _try(lambda: H.read(bad)))
for body, why in (('[companion]\nname = "x"\n', "no id"),
                  ('[companion]\nid = "x"\nformat = 99\n', "a newer format"),
                  ('[companion]\nid = "x"\n[paths]\nregistery = "r.jsonl"\n', "a misspelled path key")):
    with open(os.path.join(bad, "companion.toml"), "w", encoding="utf-8") as f:
        f.write(body)
    check("refused: " + why, _try(lambda: H.read(bad)))

print("\n3. HER ADOPTION MOVED NOTHING")
import serve as S  # noqa: E402
# HER ADOPTION lives only in her own tree: the export has neither companion nor her home, and
# her real paths are read from her companion.toml rather than spelled here (the export's
# scrub refuses machine paths in shipped files — and a second copy of them would drift).
HER_HOME = os.path.join(ROOT, "companions", "kairos", "companion.toml")
HER_HERE = os.path.isfile(os.path.join(ROOT, "profiles", "companion.toml")) and os.path.isfile(HER_HOME)
if not HER_HERE:
    print("  omitted  §3: her profile and home are not in this tree (the public export)")
else:
    import tomllib
    with open(HER_HOME, "rb") as _f:
        _written = tomllib.load(_f).get("paths", {})
    _env0 = dict(os.environ)
    her = S.build_env(S.load_profile("companion"))
    os.environ.clear()
    os.environ.update(_env0)
    check("companion runs on her home", N(her.get("SP_HOME", "")) == N(os.path.join(ROOT, "companions", "kairos")),
          her.get("SP_HOME"))
    check("…and calls her Kairos", her.get("SP_COMPANION_NAME") == "Kairos")
    reg = os.path.join(ROOT, "var", "memory", "registry.jsonl")
    # Where each store was on 2026-11-26 before the home: explicit profile keys, else the
    # reader's own default (repo-root literal, or beside the registry).
    was = {"registry": reg, "sem_index": os.path.join(ROOT, "var", "memory", "semindex.jsonl"),
           "eps_dir": _written.get("eps_dir", ""), "graph_dir": os.path.join(os.path.dirname(reg), "graph"),
           "decisions": os.path.join(os.path.dirname(reg), "decisions.jsonl")}
    for k, (var, _l, legacy, _p) in H.KEYS.items():
        exp = was.get(k) or os.path.join(ROOT, legacy)
        check(f"{k} is where it was", N(her.get(var, "")) == N(exp), (her.get(var), exp))
    # BYTE FOR BYTE for the values her profile used to write out: a normalised comparison
    # once hid a forward-slash path arriving back-slashed — and the daemon reads it.
    for var, key in (("SP_EPS_DIR", "eps_dir"), ("SP_EPS_COLD_DIR", "eps_cold_dir")):
        check(f"{var} is byte-identical to what her home wrote", her.get(var) == _written.get(key),
              (her.get(var), _written.get(key)))
    check("SP_RECALL_REGISTRY is byte-identical to the old profile's spelling",
          her.get("SP_RECALL_REGISTRY") == (reg.replace("/", "\\") if os.name == "nt" else reg))
    check("her backups stay in var/backups (restore.py's listing unbroken)",
          N(her.get("SP_BACKUP_DIR", "")) == N(os.path.join(ROOT, "var", "backups")), her.get("SP_BACKUP_DIR"))

print("\n4. serve.py refuses two sources for one store")
c = S.load_profile("companion")
c["paths"] = dict(c["paths"], registry="elsewhere/registry.jsonl")
c["_companion"] = home
try:
    S.build_env(c)
    check("a profile registry beside a home is refused", False)
except SystemExit as e:
    check("a profile registry beside a home is refused", "[paths].registry" in str(e), str(e)[:120])
c = S.load_profile("companion")
c["paths"] = {k: v for k, v in c["paths"].items() if k != "registry"}
c["_companion"] = home
c["companion"] = {"name": "Other"}
try:
    S.build_env(c)
    check("a profile [companion] name beside a home is refused", False)
except SystemExit as e:
    check("a profile [companion] name beside a home is refused", "companion" in str(e), str(e)[:120])
c = S.load_profile("companion")
c["companion"] = {"name": "Robin"}
check("without a home, [companion] name reaches SP_COMPANION_NAME",
      S.build_env(c).get("SP_COMPANION_NAME") == "Robin")
check("…and the shipped companion profile names nobody",
      not S.build_env(S.load_profile("companion")).get("SP_COMPANION_NAME"))
c = S.load_profile("companion")
c["paths"] = {k: v for k, v in c["paths"].items() if k != "registry"}
c["_companion"] = "no-such-companion"
try:
    S.build_env(c)
    check("--companion= naming a missing home is refused", False)
except SystemExit as e:
    check("--companion= naming a missing home is refused", "companion home" in str(e), str(e)[:120])

print("\n5. a second companion shares no store with her")
c = S.load_profile("companion")
c["paths"] = {k: v for k, v in c["paths"].items() if k != "registry"}
c["_companion"] = home
ivy = S.build_env(c)
if not HER_HERE:                     # the export: the other companion is one made here
    H.COMPANIONS_DIR = os.path.join(SB, "companions")
    _other = H.create("rowan", "Rowan")
    c2 = dict(c, _companion=_other)
    her = S.build_env(c2)
shared = [var for k, (var, *_r) in H.KEYS.items() if N(ivy.get(var, "?")) == N(her.get(var, "!"))]
check("no store path in common", not shared, shared)
check("…and not the backup folder", N(ivy["SP_BACKUP_DIR"]) != N(her["SP_BACKUP_DIR"]))

print("\n6. the gate sandbox covers every store in the table")
# A store added to KEYS and not to _gate._STORE_ENV is a store every gate writes for real.
# Exempt, each with its reason: the persona FRAGMENTS are read-only for gates and several
# grade her real ones; the sem index is off when empty; decisions derive beside the sandbox
# registry.
EXEMPT = {"SP_PERSONA_DIR", "SP_SEM_INDEX", "SP_DECISIONS"}
missing = [var for (var, *_r) in H.KEYS.values() if var not in _STORE_ENV and var not in EXEMPT]
check("every home store is in _STORE_ENV", not missing, missing)
check("the sandbox drops a live launch's SP_HOME", not os.environ.get("SP_HOME"))

print("\n7. the readers honour the resolver")
for k, v in env.items():                       # run as Ivy
    os.environ[k] = v
from harness.control import agency_feed, task_loop  # noqa: E402
from harness.personality import curator, self_model  # noqa: E402
from harness.skills import narrative  # noqa: E402
check("agency_feed reads her own-time from the home", inside(agency_feed._mem_root(), home),
      agency_feed._mem_root())
check("the task queue is the home's", inside(task_loop._task_root(), home), task_loop._task_root())
check("the self-model is the home's", inside(str(self_model._resolve_root()), home))
check("the personality curator is the home's", inside(str(curator._tier_root()), home))
src = open(os.path.join(ROOT, "harness", "server", "panels.py"), encoding="utf-8").read()
check("the journal panel asks the resolver, not a literal",
      '"memory-okf-personality", "full")' not in src and 'path("personality_okf")' in src)

print("\n8. the backup takes the home's stores and keeps out of hers")
for rel in ("persona.md", "memory/registry.jsonl", "memory/speech.jsonl", "okf/personality/full/a.md",
            "eps/ep1/k.bin", "tuning.json"):
    p = os.path.join(home, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write("ivy %s\n" % rel)
from harness.control import backup as B  # noqa: E402
B.DIR = os.environ["SP_BACKUP_DIR"]
files, skipped = B._files()
rels = sorted(r for _a, r in files)
check("only the home's files", files and all(inside(a, home) for a, _r in files),
      [a for a, _r in files if not inside(a, home)][:2])
check("the registry folder, persona and knobs are in it",
      {"memory/registry.jsonl", "memory/speech.jsonl", "persona.md", "tuning.json"}
      <= {r.split("companions/ivy/", 1)[-1] for r in rels}, rels)
check("the home's episodes are not archived (not a source, as before)",
      not any("/eps/" in r for r in rels), [r for r in rels if "/eps/" in r][:2])
rec = B.run_once("g_home")
check("a backup completes", rec.get("ok"), rec.get("error"))
if rec.get("name"):
    with zipfile.ZipFile(os.path.join(B.DIR, rec["name"])) as z:
        man = __import__("json").loads(z.read("MANIFEST.json"))
    check("the manifest names the companion", man.get("companion") == "ivy", man.get("companion"))
check("…written to Ivy's folder, not hers", N(B.DIR) != N(os.path.join(ROOT, "var", "backups")))

print("\n9. no harness module builds a memory-okf path outside the table")
RX = re.compile(r"memory-okf")
ALLOW = {os.path.join("harness", "home.py"), os.path.join("harness", "control", "backup.py"),
         os.path.join("harness", "telemetry", "sink.py")}    # sink: a CLI default, --root
hits = []
for dp, dn, fn in os.walk(os.path.join(ROOT, "harness")):
    dn[:] = [d for d in dn if d != "__pycache__"]
    for f in fn:
        if not f.endswith(".py"):
            continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, ROOT)
        if rel in ALLOW:
            continue
        s = open(p, encoding="utf-8", errors="replace").read()
        toks = list(tokenize.generate_tokens(io.StringIO(s).readline))
        for i, t in enumerate(toks):
            if t.type == tokenize.STRING and RX.search(t.string) and not t.string.lstrip("rbuRBU").startswith(('"""', "'''")):
                hits.append("%s:%d" % (rel, t.start[0]))
check("no reader composes its own OKF root", not hits, hits[:6])

H.VAR = _REAL_VAR
finish("G-HOME")
