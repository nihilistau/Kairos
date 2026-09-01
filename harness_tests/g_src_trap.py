"""G-SRC-TRAP — a source assertion may not go quiet when the code moves. OFFLINE.

THE SRC-TRAP is this repo's own name for asserting over source text instead of over
behaviour (`gates/GATE-INDEX.md`, `harness/control/spine.py`, `harness_tests/g_lane_table.py`
— *"branching on a paragraph, the src-trap in a lab coat"*). Sometimes it is the only tool:
"every gateway path arms the memory lane before it consults it" is a claim about the SHAPE
of the code, and driving one path proves nothing about the others.

WHAT THIS GATE IS FOR is the trap's second edge, and splitting `harness/server/app.py` is
what walked onto it. Forty-two read sites across thirty-nine gates opened that one file:

  * `.index(marker)` raises ValueError and `.split(m)[1]` raises IndexError when the
    marker leaves the file. LOUD, and therefore safe.
  * `X not in src` goes GREEN, because X is genuinely not in that file any more. There
    were ~186 such assertions in those gates.
  * `src.count(X) == N` collapses for the same reason.
  * and the shape that is pure loss: `g_asked` AST-walked app.py for functions containing
    `run_pre_turn(` and asserted an ordering of each. Move the turn lifecycle to a sibling
    and NO FUNCTION MATCHES — the offender list is empty, the gate is green, and it has
    graded nothing. Two more were already like that before any refactor:
    `g_homeassistant` sliced off a `find()` that can return -1 (so the absence check ran
    over the last character of the file), and `g_profile_guard` anchored a 7000-byte
    window on the text of a COMMENT.

So the unit of a source assertion is not the FILE. It is the PACKAGE (`_src.pkg` — for
"nowhere in the gateway does X happen") or the OBJECT (`_src.body` — for "inside this
function, X comes before Y"). This gate holds that migration in place, and holds the
cheaper rule that would have caught two shipped reds today: a gate may not read a source
path that does not exist.

    python harness_tests/g_src_trap.py
"""
from __future__ import annotations

import ast
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402
import _src as _srcmod  # noqa: E402

utf8_stdout()
HT = os.path.join(ROOT, "harness_tests")
GATES = sorted(f for f in os.listdir(HT) if f.endswith(".py") and not f.startswith("_"))


def _text(fn):
    return io.open(os.path.join(HT, fn), encoding="utf-8", errors="replace").read()


print("1. THE THREE READS EXIST AND NONE OF THEM IS VACUOUS")
check("text() reads one file", len(_srcmod.text("harness", "store_io.py")) > 500)
check("pkg() reads a package", len(_srcmod.pkg("harness", "server")) > 100_000)
check("...over more than one file", len(_srcmod.files("harness", "server")) >= 2,
      _srcmod.files("harness", "server"))
from harness.server import app as _app  # noqa: E402
check("body() reads one object", "def _settle_turn(" in _srcmod.body(_app._settle_turn))
# A READER THAT ANSWERS "" FOR AN ABSENT SUBJECT IS THE TRAP WEARING THE FIX'S CLOTHES.
for _fn, _args, _exc in ((_srcmod.text, ("harness", "nope.py"), FileNotFoundError),
                         (_srcmod.pkg, ("harness", "nope"), NotADirectoryError)):
    _raised = None
    try:
        _fn(*_args)
    except Exception as exc:
        _raised = exc
    check("%s raises for an absent subject rather than answering empty" % _fn.__name__,
          isinstance(_raised, _exc), _raised)

print("\n2. EVERY SOURCE PATH A GATE READS EXISTS")
# THE CLASS THAT SHIPPED TWICE TODAY: `g_oneshot_bounds` read `engine/routes.rs` and
# `g_control_surface` read `console/index.html` — both excluded from the Kairos export, so
# both went red inside it on a FileNotFoundError, for subjects that cannot drift because
# they do not ship. A gate is allowed to skip what is absent; it is not allowed to die on
# it, and it is not allowed to name something that never existed.
# OPENED, not merely NAMED. `g_profile_door` asserts `profiles/agent.toml` is GONE and
# `g_docs_true` globs `docs/*.md` — a path inside an existence test or a glob is not a
# read, and flagging it would be a gate convicting gates for doing the right thing. So
# the join has to sit inside an `open(...)` on the same logical line.
_pat = re.compile(r'(?:io\.)?open\(\s*os\.path\.join\(\s*(?:ROOT|_ROOT\w*|root)\s*,'
                  r'\s*((?:"[^"*]+"\s*,\s*)*"[^"*]+")\s*\)')
_missing = []
_looked = 0
for fn in GATES:
    src = _text(fn)
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    code = re.sub(r"\s*\n\s*", " ", code)      # join wrapped calls onto one line
    for m in _pat.finditer(code):
        parts = [x.strip().strip('"') for x in m.group(1).split(",")]
        rel = "/".join(parts)
        if rel.startswith(("var/", "console/room/assets")):
            continue          # runtime artefacts, legitimately absent on a fresh clone
        _looked += 1
        if os.path.exists(os.path.join(ROOT, *parts)):
            continue
        # AND A GUARDED READ IS NOT A BROKEN ONE. `g_kairos_scrub` reads
        # `KAIROS-SOURCE.txt`, which exists only inside the export, behind its own
        # `os.path.exists(...) and open(...)`. That is the correct shape for a subject
        # that is legitimately absent here — the thing this leg is for is the read that
        # DIES on absence, not the one that asks first.
        _guard = re.search(r"os\.path\.exists\(\s*os\.path\.join\(\s*(?:ROOT|_ROOT\w*|root)"
                           r"\s*,\s*" + re.escape(m.group(1)), code)
        if _guard:
            continue
        _missing.append("%s -> %s" % (fn, rel))
check("the scan found source paths to check", _looked >= 40, _looked)
check("no gate names a source path that is not here", not _missing, _missing[:6])

print("\n3. THE TWO SPLIT SUBJECTS ARE READ AS PACKAGES, NOT AS ONE FILE")
# The migration, held. `harness/server/app.py` was split and `harness/skills/memory.py` is
# being split; a gate that re-pins either file would be green over whatever moved out of
# it, which is the whole failure above.
#
# ── AND FOR MEMORY THE PIN IS NOW A LIE OUTRIGHT (2026-09-01) ───────────────────────
# `harness/skills/memory.py` does not exist any more — it is `memory/__init__.py`, a
# package whose `__init__` IS the façade, so "one door" is structural instead of a
# convention held up by everything being in one file. A gate naming the old path does not
# go quietly green there; §2 catches it as a path that is not here. This leg is what stops
# it being RE-created: the next author reaching for `memory.py` gets told the unit is
# `_src.pkg("harness", "skills", "memory")` before the siblings arrive underneath it.
_SUBJECTS = ((r'"server"\s*,\s*"app\.py"|harness/server/app\.py', "harness/server/app.py"),
             (r'"skills"\s*,\s*"memory\.py"|harness/skills/memory\.py',
              "harness/skills/memory.py"))
for _rx, _label in _SUBJECTS:
    _pinned = []
    for fn in GATES:
        if fn in ("g_src_trap.py",          # this gate names the paths in order to forbid them
                  "g_store_writes.py"):     # keys its allow-list by path: a declaration
            continue
        src = _text(fn)
        # PROSE IS NOT A READ. Several gates explain the old shape in a docstring or a
        # comment — `g_asked` in the note recording why its walk changed, `g_byteexact` in
        # its own history, `g_store_writes` in the note about where the tmp guard went. A
        # check that cannot tell a path from a sentence about a path is the
        # comments-are-not-code lesson arriving as its own violation.
        code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
        code = re.sub(r'"""[\s\S]*?"""', "", code)
        if re.search(_rx, code):
            _pinned.append(fn)
    check("no gate reads %s as a file" % _label, not _pinned, _pinned)
_users = [fn for fn in GATES if "_srcmod.pkg(" in _text(fn) or "_src.pkg(" in _text(fn)]
check("...and the package reader is the one actually in use (>= 30 gates)",
      len(_users) >= 30, len(_users))

print("\n4. A WALK THAT FOUND NOTHING SAYS SO")
# The `g_asked` shape: an AST walk that reports offenders is green over an empty
# population. Every gate that walks for FunctionDefs must also assert it looked at
# something — named here rather than grepped generically, because the population guard
# is a claim about that gate's own subject.
for fn, needle in (("g_asked.py", "there are gateway paths that consult"),
                   ("g_routes_once.py", "the walk covered the gateway package"),
                   ("g_homeassistant.py", "the ingest route is where this looks for it")):
    check("%-24s asserts its population is non-empty" % fn, needle in _text(fn),
          "a walk over nothing reports no offenders either")

print("\n5. AND NO GATE IMPORTS A REBINDABLE SCALAR FROM A STATE MODULE")
# Ahead of the state extraction: `from x import SOME_SCALAR` snapshots the value, so a
# later `x.SOME_SCALAR = ...` is invisible to the importer. Objects (a lock, a dict, an
# Event) are safe because the binding is shared; scalars are not. The rule is that state
# is reached through its MODULE.
_bad_import = []
for fn in GATES:
    for m in re.finditer(r"from harness\.server\.state import ([^\n]+)", _text(fn)):
        _bad_import.append("%s: %s" % (fn, m.group(1).strip()))
check("state is reached through its module, never by name", not _bad_import, _bad_import)

print("\n6. A SPLIT MAY NOT STRAND A NAME")
# ── TWICE IN TWO STAGES, BOTH ON UNGATED PATHS (2026-09-01) ─────────────────────────
# Moving a function to a sibling module strands whatever it used from the old module's
# top-level imports. It happened twice:
#   * `panels.py` — `_room_pulse` used `_swallowed`; caught by CALLING the panels.
#   * `turn.py`   — `_repeat_guard`'s re-roll closure used `strip_control_surfaces`;
#     nothing caught it, because a re-roll needs a model and no gate drives that path.
#     Shipped, it would have been a NameError the first time she repeated herself.
# So: resolve every global name each module in the gateway package LOADS, statically. No
# model, no socket, no luck — this finds the stranded name on the path nobody runs.
# ── AND OVER THE MEMORY PACKAGE TOO (2026-09-01) ────────────────────────────────────
# `harness/skills/memory` is a package now, for the same reason and by the same procedure,
# and it is the subject where a stranded name would be most expensive: a NameError inside
# `remember()` is a fact she was told was stored. The walk was written for one package and
# generalises for nothing — so it takes a list, before the siblings arrive rather than
# after the first one strands something.
_PACKAGES = (("harness", "server"), ("harness", "skills", "memory"))
# FLAT, one module per iteration: nesting the package loop would have re-indented the
# whole walk below, and a diff that moves eighty lines sideways is a diff nobody reads.
_MODULES = [(_p, _n) for _p in _PACKAGES for _n in _srcmod.files(*_p)]
_stranded = {}
for _pkg, _name in _MODULES:
    _label = "/".join(_pkg[1:] + (_name,))
    _tree = ast.parse(_srcmod.text(*(_pkg + (_name,))))
    _mod = set(dir(__builtins__) if isinstance(__builtins__, dict) else dir(__builtins__))
    _mod |= set(__builtins__.keys()) if isinstance(__builtins__, dict) else set()
    _mod |= {"__file__", "__name__", "__doc__", "__builtins__"}
    for _n in _tree.body:
        if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _mod.add(_n.name)
        elif isinstance(_n, ast.Assign):
            for _t in _n.targets:
                for _nn in ast.walk(_t):
                    if isinstance(_nn, ast.Name):
                        _mod.add(_nn.id)
        elif isinstance(_n, ast.AnnAssign) and isinstance(_n.target, ast.Name):
            _mod.add(_n.target.id)
        elif isinstance(_n, (ast.Import, ast.ImportFrom)):
            for _a in _n.names:
                _mod.add(_a.asname or _a.name.split(".")[0])
    for _fn in [x for x in _tree.body if isinstance(x, ast.FunctionDef)]:
        _loc = {a.arg for a in _fn.args.args + _fn.args.kwonlyargs}
        if _fn.args.vararg:
            _loc.add(_fn.args.vararg.arg)
        if _fn.args.kwarg:
            _loc.add(_fn.args.kwarg.arg)
        for _sub in ast.walk(_fn):
            if isinstance(_sub, ast.Assign):
                for _t in _sub.targets:
                    for _nn in ast.walk(_t):
                        if isinstance(_nn, ast.Name):
                            _loc.add(_nn.id)
            elif isinstance(_sub, (ast.AnnAssign, ast.AugAssign)) and isinstance(_sub.target, ast.Name):
                _loc.add(_sub.target.id)
            elif isinstance(_sub, (ast.Import, ast.ImportFrom)):
                for _a in _sub.names:
                    _loc.add((_a.asname or _a.name).split(".")[0])
            elif isinstance(_sub, (ast.For, ast.comprehension)):
                _t = getattr(_sub, "target", None)
                if _t is not None:
                    for _nn in ast.walk(_t):
                        if isinstance(_nn, ast.Name):
                            _loc.add(_nn.id)
            elif isinstance(_sub, ast.ExceptHandler) and _sub.name:
                _loc.add(_sub.name)
            elif isinstance(_sub, ast.withitem) and _sub.optional_vars is not None:
                for _nn in ast.walk(_sub.optional_vars):
                    if isinstance(_nn, ast.Name):
                        _loc.add(_nn.id)
            elif isinstance(_sub, (ast.FunctionDef, ast.Lambda, ast.ClassDef)):
                # NESTED CLASSES COUNT (2026-09-01): the first cut collected nested `def`s
                # and not nested `class`es, so it convicted app.py for loading `Handler` —
                # which `_run_stdlib` defines inside itself and hands to ThreadingHTTPServer
                # forty lines later. A checker that convicts correct code is the thing this
                # whole gate exists to prevent.
                if isinstance(_sub, (ast.FunctionDef, ast.ClassDef)):
                    _loc.add(_sub.name)
                if not isinstance(_sub, ast.ClassDef):
                    _a2 = _sub.args
                    _loc |= {x.arg for x in _a2.args + _a2.kwonlyargs}
        for _sub in ast.walk(_fn):
            if isinstance(_sub, ast.Name) and isinstance(_sub.ctx, ast.Load):
                if _sub.id not in _loc and _sub.id not in _mod:
                    _stranded.setdefault(_label, set()).add(_sub.id)
check("the check read both packages",
      len(_srcmod.files("harness", "server")) >= 4
      and len(_srcmod.files("harness", "skills", "memory")) >= 1,
      {"/".join(p[1:]): _srcmod.files(*p) for p in _PACKAGES})
check("no module in the gateway or in memory loads a name it cannot resolve",
      not _stranded, {k: sorted(v) for k, v in _stranded.items()})

finish("G-SRC-TRAP")
