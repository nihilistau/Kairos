"""G-MEMORY-PACKAGE — the façade is the one door, and it is the door the tree uses. OFFLINE.

WHAT THIS EXISTS FOR (2026-09-01, the memory.py split). `harness/skills/memory.py` was one
2273-line file. It is a package now, and its `__init__.py` is the façade, so the doctrine's
*"one door, and the readers go through it"* is a module boundary instead of a convention held
up by everything being adjacent.

A façade has exactly two ways to fail, and both are quiet:

  1. **A name stops resolving.** The tree reaches this package from 400-odd files, and 84 of
     those sites reach it DYNAMICALLY — `M._load`, `M._reg_path`, `M._present_row`,
     `M._REG_LOCK` — because `import harness.skills.memory as M` is the idiom here. Python
     does not check those until they run. A sibling extraction that forgets one re-export is
     an `AttributeError` on a path a gate may not drive for weeks; if that path is
     `remember()`, it is a fact she was told was stored.
  2. **A second door opens.** Somebody imports a sibling directly
     (`from harness.skills.memory.rank import search_memories_ranked_rows`) and now there are
     two ways in, which is how "the recall seam filters retired rows" came to be enforced in
     `search_memories_ranked_rows()` and not in `search_memories_ranked()` — AGENTS.md §0's
     second row, in this exact subsystem.

So this gate is a census built from **the tree's own usage**, read out of the source with the
AST rather than retyped here. A list of names kept in a gate file is the two-copies bug
wearing a lab coat: it would be complete on the day it was written and would miss the site
added next week, which is the one that matters.

    python harness_tests/g_memory_package.py
"""
from __future__ import annotations

import ast
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, sandbox as _sandbox, utf8_stdout  # noqa: E402
import _src as _srcmod  # noqa: E402

utf8_stdout()
_SB = _sandbox(os.path.basename(__file__))

PKG = ("harness", "skills", "memory")
DOTTED = ".".join(PKG)
PKG_DIR = os.path.join(ROOT, *PKG)

import harness.skills.memory as M  # noqa: E402

MEMBERS = [f for f in sorted(os.listdir(PKG_DIR)) if f.endswith(".py")]
SIBLINGS = [f for f in MEMBERS if f != "__init__.py"]

print("1. THE PACKAGE HAS A DOOR AND SOMETHING BEHIND IT")
check("`%s` is a package" % DOTTED, hasattr(M, "__path__"),
      getattr(M, "__file__", None))
check("...whose door is __init__.py",
      os.path.basename(getattr(M, "__file__", "")) == "__init__.py",
      getattr(M, "__file__", None))
check("...with siblings behind it", len(SIBLINGS) >= 1, MEMBERS)


def _walk(*roots):
    for base in roots:
        for here, dirs, files in os.walk(os.path.join(ROOT, base)):
            if "__pycache__" in here:
                continue
            if os.path.abspath(here).startswith(os.path.abspath(PKG_DIR)):
                continue                      # inside the package: not a consumer
            for f in sorted(files):
                if f.endswith(".py"):
                    yield os.path.join(here, f)


def _rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


# ── THE TREE'S OWN USAGE, READ WITH THE AST ──────────────────────────────────────────
# Every way this package is reached, from every consumer, resolved statically:
#   `import harness.skills.memory as M` / `from harness.skills import memory as M`
#      -> then every `M.<name>` in that file is a name the door must carry
#   `from harness.skills.memory import a, b`     -> a and b must be on the door
#   `from harness.skills.memory.<sibling> import` -> A SECOND DOOR. Convicted below.
# SCOPE-AWARE, AND IT HAD TO BE (2026-09-01). The first cut collected aliases per FILE and
# convicted the door of missing `KINDS`, `holdem_view`, `listing`, `load` and `public` — all
# five from `harness/server/panels.py`, which binds `from harness.games import match as M`
# inside `_games_json` while a different function 180 lines later binds `from harness.skills
# import memory as M`. Both are correct code; the census was reading one function's `M` in
# another function's body. The function-local import is this repo's IDIOM (181 of them in
# app.py alone, deliberately, to break import cycles), so a file-wide alias table is not an
# approximation here — it is the wrong unit, and a gate that convicts correct code is the
# thing gates exist to prevent.
_SCOPED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _own(node):
    """Every node in THIS scope, pruning at a nested one.

    `ast.walk` cannot express this: a `continue` on a nested FunctionDef skips that node and
    still yields its whole body, which is how the first cut kept reading `_games_json`'s `M`
    in a sibling function. Descent has to stop AT the boundary.
    """
    stack = [c for c in ast.iter_child_nodes(node)]
    while stack:
        n = stack.pop()
        yield n
        if not isinstance(n, _SCOPED):
            stack.extend(ast.iter_child_nodes(n))


def _scan(node, path, alias, out):
    """Collect `<alias>.<name>` loads, with `alias` resolved per scope.

    A scope inherits its parent's aliases, adds whatever it imports itself, and DROPS any
    it rebinds to something else — which is the panels.py case above.
    """
    here = set(alias)
    own = list(_own(node))
    # 1. what this scope binds, before looking at any usage (Python's own order inside a
    #    function body is irrelevant: the binding is in effect for the whole scope).
    for sub in own:
        if isinstance(sub, ast.Import):
            for a in sub.names:
                (here.add if a.name == DOTTED else here.discard)(a.asname or a.name.split(".")[0])
        elif isinstance(sub, ast.ImportFrom):
            mod = sub.module or ""
            for a in sub.names:
                nm = a.asname or a.name
                if mod == "harness.skills" and a.name == "memory":
                    here.add(nm)
                elif mod == DOTTED:
                    out["froms"].setdefault(a.name, set()).add(_rel(path))
                    here.discard(nm)
                elif mod.startswith(DOTTED + "."):
                    out["direct"].append("%s -> %s" % (_rel(path), mod))
                    here.discard(nm)
                else:
                    here.discard(nm)
        elif isinstance(sub, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            tgts = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
            for t in tgts:
                for nn in ast.walk(t):
                    if isinstance(nn, ast.Name) and isinstance(nn.ctx, ast.Store):
                        here.discard(nn.id)          # rebound: not the package here
    # 2. usage in THIS scope only, then recurse into the nested ones with what they inherit
    #
    # ── A GUARDED READ IS NOT A REQUIRED NAME (2026-09-01) ──────────────────────────
    # `hasattr(M, "x") and M.x()` is a consumer ASKING FIRST, which is the correct shape
    # for an optional name and is exempt for the same reason G-SRC-TRAP §2 exempts
    # `g_kairos_scrub`'s guarded read of a file that only exists inside the export. What
    # this leg is for is the read that DIES on absence.
    #
    # It earned its keep immediately: the only guarded name in the tree was
    # `g_turn_epilogue`'s `M.get_author()`, and there is no `get_author` in memory — the
    # seam is `current_author()`. So `hasattr` was always False, the expression was always
    # the literal `True`, and a check reading "the lane was restored after her turn" had
    # proved nothing since the day it was written. Fixed in the same commit as this gate,
    # and mutant-verified there (make `reset_author` not restore -> red).
    _guarded = {c.args[1].value for c in own
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                and c.func.id == "hasattr" and len(c.args) == 2
                and isinstance(c.args[0], ast.Name) and c.args[0].id in here
                and isinstance(c.args[1], ast.Constant) and isinstance(c.args[1].value, str)}
    for sub in own:
        if (isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name)
                and isinstance(sub.ctx, ast.Load) and sub.value.id in here
                and sub.attr not in _guarded):
            out["attrs"].setdefault(sub.attr, set()).add(_rel(path))
    for sub in own:
        if isinstance(sub, _SCOPED):
            _scan(sub, path, here, out)
    if here:
        out["files"].add(_rel(path))


_OUT = {"attrs": {}, "froms": {}, "direct": [], "files": set()}
for path in _walk("harness", "harness_tests", "tools"):
    try:
        _tree = ast.parse(io.open(path, encoding="utf-8", errors="replace").read())
    except SyntaxError:
        continue
    _scan(_tree, path, set(), _OUT)
ATTRS, FROMS, DIRECT = _OUT["attrs"], _OUT["froms"], _OUT["direct"]
_files = len(_OUT["files"])

print("\n2. EVERY NAME THE TREE REACHES THROUGH THE DOOR RESOLVES — %d dynamic, %d imported"
      % (len(ATTRS), len(FROMS)))
# A CENSUS THAT FOUND NOTHING IS NOT A PASS (the g_asked shape). Floors first.
check("the scan found the consumers", _files >= 40, _files)
check("...and a real population of names", len(ATTRS) >= 40, len(ATTRS))
_absent = sorted("%s (%s)" % (n, sorted(w)[0]) for n, w in ATTRS.items()
                 if not hasattr(M, n))
check("no dynamic `M.<name>` in the tree is missing from the door", not _absent, _absent[:8])
_absent_f = sorted("%s (%s)" % (n, sorted(w)[0]) for n, w in FROMS.items()
                   if n != "*" and not hasattr(M, n))
check("no `from harness.skills.memory import <name>` is missing either",
      not _absent_f, _absent_f[:8])

print("\n3. AND IT IS ONE DOOR — nobody reaches past it into a sibling")
# The §0 shape this package exists to prevent: two ways in, so a rule added at one of them
# is enforced at one of two paths. `harness_tests/` is held to it too — a gate that reaches
# a sibling directly is grading the implementation instead of the door, which is the other
# rule in AGENTS.md §4 ("a gate must drive the door the product uses").
check("no consumer imports a sibling directly", not DIRECT, DIRECT[:6])

print("\n4. A RE-EXPORT IS THE SAME OBJECT, NOT A COPY")
# The façade must ALIAS, not re-implement. If a name is both defined in a sibling and
# defined again in `__init__.py`, `M.<name>` and the sibling's own callers disagree — which
# is the two-copies bug with a shorter fuse than usual, because both look right in isolation.
_defs = {}
for f in MEMBERS:
    t = ast.parse(_srcmod.text(*(PKG + (f,))))
    for n in t.body:
        names = []
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [n.name]
        elif isinstance(n, ast.Assign):
            names = [x.id for x in n.targets if isinstance(x, ast.Name)]
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            names = [n.target.id]
        for nm in names:
            _defs.setdefault(nm, []).append(f)
_twice = {n: v for n, v in _defs.items() if len(v) > 1}
# ── ONE LOGGER IS NOT TWO COPIES (2026-09-01) ────────────────────────────────────────
# `logging.getLogger(name)` is idempotent BY CONTRACT: two modules naming
# `"harness.memory"` hold the same object, and that is the standard idiom every module in
# this repo uses. Forbidding the name would push the package into importing a logger from
# whichever sibling happened to declare it first, which is worse code for no gain. So the
# check is on the ARGUMENT — same string, therefore same object, therefore not a copy. A
# DIFFERENT string in two members is still convicted, because then they really are two.
_logger_of = {}
for f in MEMBERS:
    for n in ast.parse(_srcmod.text(*(PKG + (f,)))).body:
        if not (isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)):
            continue
        fn = n.value.func
        if getattr(fn, "attr", None) == "getLogger" and n.value.args:
            a0 = n.value.args[0]
            if isinstance(a0, ast.Constant):
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        _logger_of.setdefault(t.id, set()).add(a0.value)
for nm, names in _logger_of.items():
    if nm in _twice and len(names) == 1:
        del _twice[nm]
check("every shared logger names the SAME logger (idempotent, so one object)",
      all(len(v) == 1 for v in _logger_of.values()), _logger_of)
check("no name is DEFINED in two members of the package", not _twice, _twice)

# ── A NAME ITS OWNER REBINDS MUST NOT BE ALIASED AT ALL (2026-09-01) ─────────────────
# `mint._MINT_WORKER` starts as None and is rebound by `global _MINT_WORKER` when the worker
# is lazily started. Re-exporting THAT by name would put a permanent `None` on the door: the
# alias snapshots and the rebind is invisible to it — `LAST_TURN_AT` in
# `harness/server/state.py` exactly, which is why G-SRC-TRAP §5 exists one layer up. So it
# is deliberately NOT on the door, and the rule is checked rather than written down: §5
# below requires that nothing binds it by name anywhere.
GLOBALS = {}
for f in MEMBERS:
    for n in ast.walk(ast.parse(_srcmod.text(*(PKG + (f,))))):
        if isinstance(n, ast.Global):
            for nm in n.names:
                GLOBALS.setdefault(nm, set()).add(f)
check("the rebindable scalars are known (read from the `global` statements)",
      isinstance(GLOBALS, dict), sorted(GLOBALS))

# And the alias is the sibling's own object, driven rather than read.
_drifted = []
for f in SIBLINGS:
    mod = __import__("%s.%s" % (DOTTED, f[:-3]), fromlist=["x"])
    for nm in [n for n, v in _defs.items() if v == [f]]:
        if nm.startswith("__") or nm in GLOBALS:
            continue
        if not hasattr(M, nm):
            _drifted.append("%s.%s is not on the door" % (f, nm))
        elif getattr(M, nm) is not getattr(mod, nm):
            _drifted.append("%s.%s is a DIFFERENT object on the door" % (f, nm))
check("every sibling's public and private names ARE the door's names",
      not _drifted, _drifted[:8])

print("\n5. A NAME A GATE REBINDS IS REACHED AS A MODULE ATTRIBUTE, NEVER BY NAME")
# ── WHY THIS IS A LEG AND NOT A CONVENTION (2026-09-01) ──────────────────────────────
# `g_secret` proves every read door consults the secret rule by LIFTING the rule — patching
# `secret_withheld` to return False and requiring all four doors to leak. That mutant is the
# only thing between "each door calls the guard" and "each door happens to hide the row for
# some other reason", and AGENTS.md §0's last row is that exact guard being enforced on one
# path and no others.
#
# A by-name import SNAPSHOTS. So if one member of this package does
# `from ...present import secret_withheld` and another reaches `_present.secret_withheld`,
# patching the owner reaches the second and misses the first — and the mutant grades a
# SUBSET while printing a complete-looking pass. That is the same failure as `LAST_TURN_AT`
# in `harness/server/state.py` (G-SRC-TRAP §5), one layer up, and it is worse here because
# the thing going quiet is a privacy guard's only proof.
#
# THE SET IS DERIVED, not typed here: it is whatever the gates actually rebind. A hand-kept
# list would be right today and would miss the next mutant somebody writes — the same
# argument as §2 reading the tree's usage rather than a name list.
REBOUND, _AT_OWNER, _AT_ALIAS = {}, {}, {}
for path in _walk("harness_tests"):
    try:
        tree = ast.parse(io.open(path, encoding="utf-8", errors="replace").read())
    except SyntaxError:
        continue
    _o = {"attrs": {}, "froms": {}, "direct": [], "files": set()}
    _scan(tree, path, set(), _o)          # reuse the alias resolution, scopes and all
    live = set(_o["attrs"]) | {n for n in _o["froms"]}
    for n in ast.walk(tree):
        if not isinstance(n, (ast.Assign, ast.AugAssign)):
            continue
        for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
            if not isinstance(t, ast.Attribute):
                continue
            # `M.x = ...` and `M.sub.x = ...` are both a mutant naming `x`
            base = t.value
            if isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name) and (t.attr in live or base.id in ("M", "mem")):
                REBOUND.setdefault(t.attr, set()).add(_rel(path))
                # AT THE OWNER, OR AT THE ALIAS? `M.store._load = x` patches the owner and
                # every caller sees it; `M._load = x` patches a re-export that nothing in
                # the package calls. Recorded per site, because this is the half of the rule
                # the package cannot enforce on itself.
                (_AT_OWNER if isinstance(t.value, ast.Attribute) else _AT_ALIAS) \
                    .setdefault(t.attr, set()).add(_rel(path))
# only the names this package actually owns, and only those a SIBLING owns (a name defined
# in __init__.py has one binding by construction).
_owned_by_sibling = {n: v[0] for n, v in _defs.items() if len(v) == 1 and v[0] != "__init__.py"}
_watch = {n: w for n, w in REBOUND.items() if n in _owned_by_sibling}
# A name its OWNER rebinds (`global X`) is watched for the same reason and needs no gate to
# patch it: the rebind itself is the mutation an alias would miss. §4 keeps it off the door;
# here it must also not be bound by name inside the package or by any consumer.
for _g, _where in GLOBALS.items():
    if _g in _owned_by_sibling:
        _watch.setdefault(_g, set()).add("its own owner rebinds it (global in %s)"
                                         % sorted(_where)[0])
_aliased_out = sorted("%s: on the door as an alias, but its owner rebinds it" % g
                      for g in GLOBALS if g in _owned_by_sibling and hasattr(M, g))
check("no rebound scalar is aliased onto the door", not _aliased_out, _aliased_out)
check("the scan found the gates' mutants", len(REBOUND) >= 1, sorted(REBOUND))
_byname = []
for f in MEMBERS:
    t = ast.parse(_srcmod.text(*(PKG + (f,))))
    for n in ast.walk(t):
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith(DOTTED + "."):
            for a in n.names:
                if a.name in _watch and (a.asname or a.name) == a.name:
                    _byname.append("%s binds %s by name (%s patches it)"
                                   % (f, a.name, sorted(_watch[a.name])[0]))
# `__init__.py` re-exports these for CONSUMERS on purpose — that alias is the door's own
# contract (§4) and consumers only read. What may not happen is a member CALLING the alias,
# which is what the module-attribute style prevents; the call sites are asserted below.
_byname = [x for x in _byname if not x.startswith("__init__.py")]
check("no sibling binds a gate-rebound name by name", not _byname, _byname)
_init = _srcmod.text(*(PKG + ("__init__.py",)))
_direct_calls = []
for nm in sorted(_watch):
    for m in __import__("re").finditer(r"(?<![\w.])%s\(" % __import__("re").escape(nm), _init):
        line = _init[:m.start()].count("\n") + 1
        _direct_calls.append("__init__.py:%d calls %s( by name" % (line, nm))
check("...and the door CALLS it through its module, so a patched owner reaches every door",
      not _direct_calls, _direct_calls[:6])

# ── AND THE MUTANT MUST PATCH THE OWNER (2026-09-01) ────────────────────────────────
# The half the package cannot enforce on itself, and it caught a real silent green the hour
# it was written. `g_registry_rmw` replaces `_load` with a deliberately sluggish version to
# hold the read-modify-write window open, then drives `remember`, `recall` and `forget` and
# requires the concurrent write to survive. When `_load` moved to `store.py` and the doors
# started calling `_store._load()`, the gate's `M._load = ...` became inert: the race never
# opened, and "the concurrent fact survived" is TRIVIALLY TRUE when nothing was concurrent.
# MEASURED — with all four RMW locks removed from `__init__`, that gate still printed 6/6.
#
# So a mutant on a sibling-owned name must be installed at the owner. This is the leg that
# would have caught it, and it is checked rather than remembered.
_at_alias = sorted("%s patched at the ALIAS in %s — the doors call the owner, so it is inert"
                   % (n, sorted(w)[0]) for n, w in _AT_ALIAS.items()
                   if n in _owned_by_sibling)
check("every mutant on a sibling-owned name patches the OWNER, not the re-export",
      not _at_alias, _at_alias[:6])

print("\n6. AND THE DOORS STILL WORK — driven, not read")
# The census above proves the names are THERE. This proves the moved code still does its
# job through them, because a re-export of a broken function is a re-export.
check("_toks tokenises through the door (his 'cats name', the transcript case)",
      M._toks("do you remember my cats name?") == {"cat", "name"},
      sorted(M._toks("do you remember my cats name?")))
check("...and both sides of a comparison get the same treatment",
      M._overlap("my cat's name", "the cat name is Ash") > 0.9,
      M._overlap("my cat's name", "the cat name is Ash"))
check("_text reads either field", M._text({"topic": "t"}) == "t"
      and M._text({"text": "x", "topic": "t"}) == "x")
_tok = M.set_author("self")
check("the author round-trips through the door", M.current_author() == "self")
M.reset_author(_tok)
check("...and RESETS to what it was, not to a guess", M.current_author() == "user")
_qt = M.set_question("what is my name?")
check("the question's half of the same contract",
      M.current_question() == "what is my name?")
M.reset_question(_qt)
check("...resets too", M.current_question() == "")

finish("G-MEMORY-PACKAGE")
