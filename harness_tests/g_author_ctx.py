"""G-AUTHOR-CTX — speaker and question are per-turn, never process-wide.

AGENTS.md trap #4, MEMORY-AND-RECALL.md trap #5. The gateway is a
ThreadingHTTPServer. `_AUTHOR` and `_QUESTION` (and the notes twin) were module
globals, so two overlapping turns could stamp each other's speaker and resolve
ownership from the other turn's sentence.

The identity firewall and "what is YOUR name" scoping both read these. A race
here is not a style leak — it is how she files "I am a woman" as HIS testimony
and answers his name with hers.

Every remember() / notes.add() assertion below is on the REAL writer, not a
hand-called helper. The handshake is deterministic: turn A sets self, turn B
overwrites the process-wide slot (the old bug), then A proceeds. With a global,
A's write is stamped user. With a ContextVar, A stays self.

Also holds the nesting law: remember_about_self() must RESET the previous
author, not assume the previous author was "user". The old `finally:
set_author("user")` clobbered a surrounding self-turn even with no concurrency.

    python harness_tests/g_author_ctx.py        (offline: no GPU, no daemon)
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_fd, _reg = tempfile.mkstemp(suffix=".jsonl")
os.close(_fd)
os.environ["SP_RECALL_REGISTRY"] = _reg
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"
# SP_ENGINE_KIND: no capture attempt at all (2026-08-23). A dead SP_DAEMON_URL does
# NOT make the KV mint cheap - _mint_now still opens a socket per write and Windows
# takes ~2s to give up. Declaring the backend makes supports('capture') False and the
# mint returns immediately: 10 writes in 0.07s against 20s. See gates/README.md.
os.environ["SP_ENGINE_KIND"] = "openai"
os.environ["SP_CAPTURE_ASYNC"] = "0"

from harness.skills import memory as M                      # noqa: E402
from harness.skills import notes as N                       # noqa: E402
from harness.skills import lifecycle as lc                  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s   %s" % (name, detail))


def reset_reg():
    open(_reg, "w").close()
    notes = N._store()
    if os.path.exists(notes):
        open(notes, "w").close()


# ── 1. NESTING: reset the previous author, do not assume "user" ────────────────
print("\n1. remember_about_self restores the PREVIOUS author, not 'user'")
reset_reg()
M.set_author("self")
check("surrounding turn is self before the inner write", M.current_author() == "self")
inner = M.remember_about_self("I am a woman")
check("the inner write landed", "stored:" in inner or "reinforced" in inner, inner)
check("...as a self-row",
      any(r.get("speaker") == lc.SPEAKER_SELF and "woman" in (r.get("text") or "")
          for r in M._load() if not r.get("lifecycle")),
      [(r.get("speaker"), r.get("text")) for r in M._load()])
check("and the surrounding turn is STILL self after the inner finally",
      M.current_author() == "self", M.current_author())

M.set_author("user")
_ = M.remember_about_self("I like the sound of rain on a tin roof.")
check("a user-surrounding turn is still user after the inner write",
      M.current_author() == "user", M.current_author())


# ── 2. THE RACE the globals lost: two turns, one process ──────────────────────
print("\n2. overlapping turns do not swap speaker or question")
reset_reg()
ready = threading.Barrier(2)
go = threading.Barrier(2)
seen = {}
errs = {}


def turn_self():
    try:
        M.set_author("self")
        M.set_question("what is your name?")
        N.set_author(N.SPEAKER_SELF)
        ready.wait(timeout=5)
        go.wait(timeout=5)
        seen["self_author"] = M.current_author()
        seen["self_q"] = M.current_question()
        seen["self_note_author"] = N.current_author()
        seen["self_store"] = M.remember(
            "I like the sound of rain on a tin roof.", source="self")
        seen["self_note"] = N.add("her evening note", category="note")
    except Exception as e:
        errs["self"] = repr(e)


def turn_user():
    try:
        ready.wait(timeout=5)          # self has set; we now clobber the process slot
        M.set_author("user")
        M.set_question("what is my GPU?")
        N.set_author(N.SPEAKER_USER)
        go.wait(timeout=5)             # self proceeds UNDER the clobber
        seen["user_author"] = M.current_author()
        seen["user_q"] = M.current_question()
        seen["user_note_author"] = N.current_author()
        seen["user_store"] = M.remember("My GPU is an RTX 2060.", source="user turn")
        seen["user_note"] = N.add("his shopping list", category="note")
    except Exception as e:
        errs["user"] = repr(e)


t1 = threading.Thread(target=turn_self, name="turn-self")
t2 = threading.Thread(target=turn_user, name="turn-user")
t1.start(); t2.start()
t1.join(timeout=15); t2.join(timeout=15)
check("both turns finished", not t1.is_alive() and not t2.is_alive(),
      "alive=%s/%s errs=%s" % (t1.is_alive(), t2.is_alive(), errs))
check("no exception on either turn", not errs, errs)

check("self turn still reads author=self after the other turn wrote user",
      seen.get("self_author") == "self", seen)
check("user turn reads author=user",
      seen.get("user_author") == "user", seen)
check("self turn still holds HIS question about her",
      "your name" in (seen.get("self_q") or ""), seen.get("self_q"))
check("user turn still holds HIS question about the GPU",
      "GPU" in (seen.get("user_q") or ""), seen.get("user_q"))
check("notes twin: her add stayed speaker=self",
      (seen.get("self_note") or {}).get("speaker") == "self",
      seen.get("self_note"))
check("notes twin: his add stayed speaker=user",
      (seen.get("user_note") or {}).get("speaker") == "user",
      seen.get("user_note"))

rows = [r for r in M._load() if not r.get("lifecycle")]
rain = next((r for r in rows if "rain" in (r.get("text") or "")), None)
gpu = next((r for r in rows if "2060" in (r.get("text") or "")), None)
check("the rain fact (written on the self turn) is speaker=self",
      rain is not None and rain.get("speaker") == lc.SPEAKER_SELF, rain)
check("the GPU fact (written on the user turn) is speaker=user",
      gpu is not None and gpu.get("speaker") == lc.SPEAKER_USER, gpu)


# ── 3. STRUCTURAL: both lanes are ContextVars, neither is a module str ────────
print("\n3. the type is the seam — a str assignment cannot come back")


def _ctxvar_ok(paths, name):
    """Is `name` a ContextVar, assigned exactly once, with no `global` for it?

    ── ASKED OF A SUBJECT THAT MAY BE SEVERAL FILES (2026-09-01) ────────────────────
    This took ONE path, because `harness/skills/memory.py` was one file. It is a package
    now (`memory/__init__.py` plus siblings), so the subject is a LIST of files and the
    question is asked across all of them at once. That is not a workaround — it is the
    stronger form. `_AUTHOR` being a ContextVar in the file this gate happened to open
    says nothing if a sibling defines a second one; **exactly one assignment across the
    whole subject** is what "the type is the seam" actually needs, and the count is now
    part of the answer. A `global` anywhere in the package still convicts.
    """
    if isinstance(paths, str):
        paths = [paths]
    assigned, globals_hit, where = None, [], []
    for path in paths:
        tree = ast.parse(open(path, encoding="utf-8").read())
        for n in ast.walk(tree):
            hit = False
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name) and t.id == name:
                        assigned, hit = n.value, True
            if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == name:
                assigned, hit = n.value, True
            if hit:
                where.append("%s:%d" % (os.path.basename(path), n.lineno))
            if isinstance(n, ast.Global) and name in n.names:
                globals_hit.append("%s:%d" % (os.path.basename(path), n.lineno))
    if assigned is None:
        return False, "no assignment of %s in %s" % (name, [os.path.basename(p) for p in paths])
    if len(where) != 1:
        return False, "%s is assigned %d times (%s) — one owner, or the two-copies bug" % (
            name, len(where), where)
    # ContextVar("...", default=...)
    if not (isinstance(assigned, ast.Call)
            and isinstance(assigned.func, ast.Attribute)
            and assigned.func.attr == "ContextVar"):
        return False, "assigned to %s, not ContextVar" % ast.dump(assigned, include_attributes=False)
    if globals_hit:
        return False, "global %s at %s" % (name, globals_hit)
    return True, ""


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _src as _srcmod  # noqa: E402
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_mem_d = os.path.join(root, "harness", "skills", "memory")
mem_p = [os.path.join(_mem_d, f) for f in sorted(os.listdir(_mem_d)) if f.endswith(".py")]
notes_p = os.path.join(root, "harness", "skills", "notes.py")
ok, why = _ctxvar_ok(mem_p, "_AUTHOR")
check("memory._AUTHOR is a ContextVar (not a str, no global)", ok, why)
ok, why = _ctxvar_ok(mem_p, "_QUESTION")
check("memory._QUESTION is a ContextVar (not a str, no global)", ok, why)
ok, why = _ctxvar_ok(notes_p, "_AUTHOR")
check("notes._AUTHOR is a ContextVar (the twin, same class)", ok, why)
check("current_author / current_question are the read seam",
      callable(getattr(M, "current_author", None))
      and callable(getattr(M, "current_question", None))
      and callable(getattr(N, "current_author", None)))


# ── 4. AND THE CONTEXT CROSSES INTO THE GENERATION THREAD (2026-09-02) ────────────────
# THE DEFECT THIS EXISTS FOR, found live. `_arm_turn` runs in the REQUEST thread and sets
# all three of these vars. The tool loop, recall and `remember()` run in a thread the SSE
# handler spawns — and per PEP 567 a new `threading.Thread` starts with an EMPTY context,
# so every one of them reverted to its default the moment generation began.
#
#   _AUTHOR    defaults to "user" — RIGHT BY LUCK on a user turn, which is why nobody saw it
#   _QUESTION  defaults to ""     — not lucky: this is the 2026-07-12 defect `_arm_turn`'s
#                                   own docstring exists to prevent, where ownership falls
#                                   back to HER paraphrase and "what is YOUR name?" and
#                                   "what is MY name?" arrive as one indistinguishable string
#   _SYNTHETIC defaults to ""     — so a driven turn wrote into her real registry
#
# MEASURED on the running gateway: a turn declared synthetic stored "Sam's workshop bench
# is made of oak999777." and no refusal reached the log. After the fix, the same turn stores
# nothing and the log names the refusal.
#
# The fix is `contextvars.copy_context()` at the spawn and `ctx.run` as the target. This leg
# proves the MECHANISM (a bare Thread loses it, a copied context keeps it) and then asserts
# the gateway actually spawns the turn that way — the second half being the one that rots.
print("\n4. the arm-time context reaches the thread that does the work")
import contextvars as _cv4
import threading as _th4

_probe = _cv4.ContextVar("g_author_ctx_probe", default="DEFAULT")
_probe.set("armed")
_seen4 = {}
_t = _th4.Thread(target=lambda: _seen4.__setitem__("bare", _probe.get()))
_t.start(); _t.join()
check("a BARE thread loses the arm-time context (this is the trap, not a bug in the test)",
      _seen4.get("bare") == "DEFAULT", _seen4)
_ctx = _cv4.copy_context()
_t2 = _th4.Thread(target=_ctx.run, args=(lambda: _seen4.__setitem__("copied", _probe.get()),))
_t2.start(); _t2.join()
check("...and a copied context keeps it", _seen4.get("copied") == "armed", _seen4)

# AND THE GATEWAY SPAWNS ITS TURN THAT WAY. Structural, because the alternative is driving a
# whole SSE turn with a model attached; the mechanism above is what makes this line mean
# something. Mutant: put `target=_run` back and this goes red.
_app4 = _srcmod.pkg("harness", "server")
_code4 = "\n".join(l for l in _app4.splitlines() if not l.lstrip().startswith("#"))
check("the SSE turn thread runs inside the arm-time context",
      "_turn_ctx = _contextvars.copy_context()" in _code4
      and "target=_turn_ctx.run" in _code4,
      "a bare Thread here silently reverts _AUTHOR, _QUESTION and _SYNTHETIC to defaults")
check("...and no turn thread is spawned bare",
      "_threading.Thread(target=_run" not in _code4,
      "the generation thread must carry the turn's context")


os.unlink(_reg)
print("\nG-AUTHOR-CTX  %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
