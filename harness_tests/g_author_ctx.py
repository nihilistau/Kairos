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


def _ctxvar_ok(path, name):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    assigned = None
    globals_hit = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    assigned = n.value
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == name:
            assigned = n.value
        if isinstance(n, ast.Global) and name in n.names:
            globals_hit.append(n.lineno)
    if assigned is None:
        return False, "no assignment of %s" % name
    # ContextVar("...", default=...)
    if not (isinstance(assigned, ast.Call)
            and isinstance(assigned.func, ast.Attribute)
            and assigned.func.attr == "ContextVar"):
        return False, "assigned to %s, not ContextVar" % ast.dump(assigned, include_attributes=False)
    if globals_hit:
        return False, "global %s at lines %s" % (name, globals_hit)
    return True, ""


root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
mem_p = os.path.join(root, "harness", "skills", "memory.py")
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


os.unlink(_reg)
print("\nG-AUTHOR-CTX  %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
