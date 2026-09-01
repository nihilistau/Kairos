"""G-REMEMBER-PIPELINE — the writer's phases, in order, each with exactly one caller. OFFLINE.

`remember()` is the authoritative writer: every fact that ever enters the store comes through
it — the tool, `_capture_after_turn`, the consolidator, the reflector, `remember_about_self`
and therefore every self-narrative row. It was 360 lines of interleaved policy, and on
2026-09-02 the admission chain became `harness/skills/memory/admission.py`.

WHAT A SPLIT WRITER CAN LOSE, and neither the sweep nor a type checker would notice:

  1. **A refusal stops being a sentence.** Every guard in front of the store answers with
     words she reads — *"not stored — that asserts nothing standing…"*. The contract is that
     `admit()` decides and `remember()` returns its sentence VERBATIM. If the writer ever
     invented its own wording for a refusal, that is a second implementation of a refusal, in
     the place it costs most: a store verb that fails quietly is how she ends up promising to
     remember what she cannot.
  2. **The ORDER changes.** Normalisation is first because *"every guard below must see the
     CLAIM, not the wrapper"*; the author picks the gate before the class is resolved; the
     firewall runs after admission. Each of those orderings is a bug that already happened
     (AGENTS.md §0 rows 1, 4 and the identity-firewall incident). Reordering is not a style
     change.
  3. **A SECOND admission path opens.** The one-door doctrine is the whole reason the chain
     is guarded at `remember()` and not at its callers — *"guarding callers instead is how you
     get a mode that says 'nothing was recorded' over an evening sitting in the registry."*
     An `admit()` with two callers is that mode being invented again.

So: the order is asserted over `admit()`'s OWN source (byte offsets inside one function —
`_src.body`, the only read a move cannot fool), the caller count is asserted over the whole
package, and every refusal is DRIVEN through `remember()` and required to come back word for
word.

    python harness_tests/g_remember_pipeline.py
"""
from __future__ import annotations

import ast
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, sandbox as _sandbox, utf8_stdout  # noqa: E402
import _src as _srcmod  # noqa: E402

utf8_stdout()
_SB = _sandbox(os.path.basename(__file__))
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"     # discard port: never needs a GPU
os.environ["SP_ENGINE_KIND"] = "openai"                # supports('capture') False: no mint
os.environ["SP_CAPTURE_ASYNC"] = "0"

import harness.skills.memory as M                      # noqa: E402
from harness.skills.memory import admission as A       # noqa: E402
from harness.skills import memclass as _mc             # noqa: E402

REG = os.environ["SP_RECALL_REGISTRY"]


def reset():
    open(REG, "w").close()


def rows():
    if not os.path.exists(REG):
        return []
    return [json.loads(l) for l in io.open(REG, encoding="utf-8") if l.strip()]


def as_self(fn):
    tok = M.set_author("self")
    try:
        return fn()
    finally:
        M.reset_author(tok)


print("1. THE ORDER INSIDE admit(), ASKED OF THE FUNCTION ITSELF")
# ── WHY OFFSETS AND NOT A DESCRIPTION (2026-09-02) ──────────────────────────────────
# `_src.body` is `inspect.getsource(A.admit)`: one function's own text, so these offsets
# cannot be satisfied by a sibling that happens to contain the same words, and they survive
# the function moving to another file. Each pair below is an ordering that WAS a bug.
_b = _srcmod.body(A.admit)
_at = {}
for _needle in ('_anon.holds("memory.row")', "lc.normalize_fact(fact)",
                "_AUTHOR.get() == \"self\"", "lc.is_narratable(fact)",
                "lc.is_memorable(fact)", "lc.admit_to_user_store(fact"):
    _at[_needle] = _b.find(_needle)
check("every phase marker is present in admit()'s own source",
      all(v >= 0 for v in _at.values()),
      {k: v for k, v in _at.items() if v < 0})
check("the anon hold is FIRST — nothing is even normalised off the record",
      _at['_anon.holds("memory.row")'] < _at["lc.normalize_fact(fact)"])
# "Remember my GPU is an RTX 2060" is a FACT WEARING AN IMPERATIVE. Stored whole, the verb
# becomes content and the slot is wrong, so it never supersedes the real GPU row.
check("normalisation precedes BOTH admission gates (the guards see the claim, not the wrapper)",
      _at["lc.normalize_fact(fact)"] < _at["lc.is_narratable(fact)"]
      and _at["lc.normalize_fact(fact)"] < _at["lc.is_memorable(fact)"])
# Her sentence was judged by `is_memorable` — the gate for facts ABOUT SOMEONE, which
# refuses first-person prose BY DESIGN — so her own door was shut and she said so herself.
check("the AUTHOR is read before either gate is chosen",
      _at['_AUTHOR.get() == "self"'] < _at["lc.is_narratable(fact)"]
      and _at['_AUTHOR.get() == "self"'] < _at["lc.is_memorable(fact)"])
check("the identity firewall runs LAST, after admission has already passed",
      _at["lc.admit_to_user_store(fact"] > _at["lc.is_memorable(fact)"])

print("\n2. ONE ADMISSION PATH — admit() has exactly one caller, and it is the writer")
# The one-door doctrine, structurally. Guarding callers rather than the door is what the
# anon note in admission.py warns about by name.
_callers = []
for _f in _srcmod.files("harness", "skills", "memory"):
    _t = ast.parse(_srcmod.text("harness", "skills", "memory", _f))
    for _n in ast.walk(_t):
        if not (isinstance(_n, ast.Call) and isinstance(_n.func, ast.Attribute)
                and _n.func.attr == "admit"):
            continue
        _fn = None
        for _cand in ast.walk(_t):
            if (isinstance(_cand, ast.FunctionDef)
                    and _cand.lineno <= _n.lineno <= (_cand.end_lineno or _cand.lineno)):
                _fn = _cand.name
        _callers.append("%s::%s" % (_f, _fn))
check("admit() is called exactly once in the package", len(_callers) == 1, _callers)
check("...and the caller is remember(), the authoritative writer",
      _callers == ["__init__.py::remember"], _callers)
# AND NOBODY OUTSIDE REACHES IT EITHER. A second caller anywhere is a second admission
# policy; G-MEMORY-PACKAGE §3 already forbids importing the sibling, so this is the other
# half — reaching it through the façade.
_outside = []
for _base in ("harness", "harness_tests", "tools"):
    for _here, _d, _fs in os.walk(os.path.join(ROOT, _base)):
        if "__pycache__" in _here or os.path.abspath(_here).startswith(
                os.path.abspath(os.path.join(ROOT, "harness", "skills", "memory"))):
            continue
        for _f in _fs:
            if not _f.endswith(".py"):
                continue
            _s = io.open(os.path.join(_here, _f), encoding="utf-8", errors="replace").read()
            if os.path.basename(__file__) == _f:
                continue
            for _pat in (".admit(", "admission.admit"):
                if _pat in _s:
                    _outside.append("%s (%s)" % (_f, _pat))
check("no consumer outside the package calls the admission chain", not _outside, _outside)

print("\n3. EVERY REFUSAL IS A SENTENCE SHE READS — driven through remember()")
# ── DRIVEN, NOT READ (AGENTS.md §4) ─────────────────────────────────────────────────
# The point of the whole file: `admit` decides and `remember` REPORTS ITS SENTENCE
# VERBATIM. So each case below is asserted twice — the wording that comes out of
# remember(), and that admit() is where it came from. If the writer ever started composing
# its own refusal text, the two would drift and this leg names which.
reset()
_cases = [
    ("an impersonal sentence (the shape that filled the registry 404 times)",
     lambda: M.remember("The kind nurse painted the tall building blue", "user turn"),
     lambda: A.admit("The kind nurse painted the tall building blue")),
    ("her name in HIS store (the identity firewall)",
     lambda: M.remember("My name is Kairos", "user turn"),
     lambda: A.admit("My name is Kairos")),
]
for _label, _door, _chain in _cases:
    reset()
    _said = _door()
    _adm = _chain()
    check("REFUSED: %s" % _label, _said.startswith("not stored — "), _said[:70])
    check("...and the writer returned admit()'s sentence VERBATIM",
          _adm.refusal == _said, (_adm.refusal, _said))
    check("...and nothing reached the store", not rows(), rows())

# HER OWN LANE HAS ITS OWN GATE, and this is the case that was shut: a plain self-fact,
# no producer's kind, judged by is_narratable and NOT by is_memorable.
reset()
_said = as_self(lambda: M.remember("I find astronomy genuinely moving.", "self"))
check("ADMITTED: her plain self-fact goes through HER gate, not his",
      _said.startswith("stored: "), _said[:70])
_r = rows()
check("...stored as hers, and NOT wearing a narrative kind no producer named",
      len(_r) == 1 and _r[0].get("speaker") == "self"
      and not _r[0].get("kind"), _r)

# AND A PRODUCER'S LABELS MEAN NOTHING OUTSIDE HER LANE.
reset()
M.remember("Sam likes teal", "user turn", kind="journal", mem_class=_mc.SELF_NARRATIVE)
_r = rows()
check("a class and kind passed in HIS lane are zeroed, not honoured",
      len(_r) == 1 and _r[0].get("mem_class") != _mc.SELF_NARRATIVE
      and not _r[0].get("kind"), _r)

print("\n4. AND THE WRAPPER COMES OFF BEFORE ANY GUARD SEES IT")
reset()
_said = M.remember("Remember my GPU is an RTX 2060", "user turn")
_r = rows()
check("the imperative is stripped from what gets STORED",
      len(_r) == 1 and not (_r[0].get("text") or "").lower().startswith("remember"),
      _r[0].get("text") if _r else None)
check("...and the sentence she gets back names the CLAIM, not the wrapper",
      "remember my gpu" not in _said.lower(), _said[:70])
# The refusal path proves the same ordering from the other side: normalised first, so the
# firewall tests the claim. "Remember my name is Kairos" must still be refused.
reset()
_said = M.remember("Remember my name is Kairos", "user turn")
check("an imperative-wrapped identity claim is still caught by the firewall",
      _said.startswith("not stored — "), _said[:70])
check("...and it still stored nothing", not rows(), rows())

print("\n5. THE WRITER'S OWN PHASES, IN ORDER, EACH CALLED ONCE")
# ── THE PIPELINE, ASKED OF remember() ITSELF (2026-09-02) ───────────────────────────
# After the split `remember()` is 46 lines of code: configured -> admit -> dedupe -> mint
# -> verdict -> row -> commit -> sidecar -> answer. Every ordering below is a bug if it
# reverses, and none of them is enforced by anything except this leg:
#
#   admit before dedupe    a REFUSED fact must never reinforce a row
#   dedupe before mint     a repeat must not mint an episode (that is the 1702 ms she was
#                          made to wait, spent on a fact that was already there)
#   mint before the row    the row carries out_dir and npos
#   verdict before commit  the tombstones must exist before anything is put down
#   commit before sidecar  semindex is DERIVED; a sidecar entry for a row that failed to
#                          land is an index pointing at nothing
_r = _srcmod.body(M.remember)
_ph = [("admit", "_admission.admit("),
       ("dedupe", "_dedupe.check_repeat("),
       ("mint", "_mint_is_async()"),
       ("verdict", "_supersede.what_it_retires("),
       ("row", "lc.stamp(line,"),
       ("commit", "_store.commit_row("),
       ("sidecar", "_sem.mint(")]
_off = {n: _r.find(m) for n, m in _ph}
check("every phase is present in remember()'s own source",
      all(v >= 0 for v in _off.values()), {k: v for k, v in _off.items() if v < 0})
_order = [n for n, _ in _ph]
_actual = sorted(_order, key=lambda n: _off[n])
check("...and they appear in the pipeline's order", _actual == _order,
      "expected %s, found %s" % (_order, _actual))
# EXACTLY ONE CALL EACH. A phase called twice is the shape §0 keeps producing: two paths,
# and the rule lands on one of them.
_dupes = {n: _r.count(m) for n, m in _ph if _r.count(m) != 1}
check("each phase is called exactly once by the writer", not _dupes, _dupes)
# AND COMMIT IS THE ONLY APPEND IN THE PACKAGE. `store.commit_row`'s docstring claims this;
# an append anywhere else is a second write path, which is how forget() once dropped a row
# with a bare open(p, "w").
_appends = []
for _f in _srcmod.files("harness", "skills", "memory"):
    _s = _srcmod.text("harness", "skills", "memory", _f)
    _c = "\n".join(l for l in _s.splitlines() if not l.lstrip().startswith("#"))
    _c = __import__("re").sub(r'"""[\s\S]*?"""', "", _c)
    for _m in __import__("re").finditer(r"\brows\.append\(|\.append\(line\)", _c):
        _appends.append("%s:%d" % (_f, _c[:_m.start()].count("\n") + 1))
check("the row append happens in exactly one place in the package",
      len(_appends) == 1, _appends)
check("...and that place is store.py", _appends and _appends[0].startswith("store.py"),
      _appends)

print("\n6. THE CHAIN DOES NOT WRITE, WHICH IS WHY IT CAN BE DRIVEN ALONE")
# admission.py reads the persona and the author; it must never touch the registry, or
# "decide" and "write" are one step again and the refusals stop being testable in isolation.
_asrc = _srcmod.text("harness", "skills", "memory", "admission.py")
_code = "\n".join(l for l in _asrc.splitlines() if not l.lstrip().startswith("#"))
import re as _re  # noqa: E402
_code = _re.sub(r'"""[\s\S]*?"""', "", _code)
_writes = [n for n in ("_save_all", "_REG_LOCK", "replace_atomic", "_load(")
           if n in _code]
check("the admission chain never writes and never takes the lock", not _writes, _writes)
reset()
_before = rows()
A.admit("Sam's workshop bench is made of oak")
A.admit("The kind nurse painted the tall building blue")
check("...proved by driving it: the store is untouched", rows() == _before, rows())

finish("G-REMEMBER-PIPELINE")
