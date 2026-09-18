"""G-JLENS-PROBE — the calibration probe cannot reach her stores. OFFLINE.

WHY (2026-09-18). Band calibration needs many forward passes with activation taps, and the
last probe that ran against her live process took her presence for three hours. So it gets
its own boot on its own port — and the part that needs a gate is not the port, it is that
the boot cannot see her data even when the operator gets it wrong.

THE DAEMON READS STORE PATHS. `SP_RECALL_REGISTRY`, `SP_OKF_ROOT`, `SP_MEM_OKF_STORE`,
`SP_OKF_MEM` are all read inside sp-daemon, so "it is only the engine, it has no memory" is
false and isolation is a property that has to be asserted rather than assumed from the
architecture.

WHAT THIS HOLDS:

  §1 EVERY STORE IS REDIRECTED. The probe's env sets every name in `_gate._STORE_ENV`, and
     `violations()` is computed over that same list — one copy, so a store added to the
     sandbox and not to the probe fails here instead of opening a silent hole.
  §2 UNSET IS A VIOLATION, NOT A DEFAULT. `serve.py` deletes empty `SP_*` deliberately —
     "absent is the only value that lets the default run" — and the consumer's default is
     REPO-RELATIVE, i.e. inside her `var/`. So a missing store var points AT HER, and this
     gate treats absence as the fault it is.
  §3 RESOLVED PATHS, NOT STRING PREFIXES. The scratch dir is named `var-probe`, which
     `startswith("var")` matches. A prefix check passes it AND passes a junction from
     `var-probe/memory` to `var/memory`, which lands in her registry. The check resolves
     both sides and compares as paths.
  §4 THE REFUSAL REACHES THE EXIT CODE. `--start` returns 3 on a violation, because a guard
     whose verdict does not reach the caller is a print statement.
  §5 STOPPING IS BY PORT, NEVER BY IMAGE. `engine/launch.py::stop_daemon` kills
     `/IM sp-daemon.exe`, which matches her engine too. The probe resolves the pid holding
     its own port — measured necessary: the exe re-execs, so the Popen pid was 28580 while
     :3001 was held by its child 20032, and a kill of the recorded pid orphaned the server
     on the GPU while reporting success.

MUTANTS, run in-gate: unset a store var (§2 red), point one at her tree (§1/§3 red), and —
the one a prefix check survives — JUNCTION `var-probe/memory` onto her `var/memory` (§3
red). The junction leg OMITs itself where the OS refuses to create one rather than passing
vacuously.

    python harness_tests/g_jlens_probe.py
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _gate  # noqa: E402
from _gate import check, finish, sandbox, skip, utf8_stdout  # noqa: E402

utf8_stdout()
sandbox("g_jlens_probe")

# SKIPS IN THE PUBLIC SNAPSHOT, and this is not an accident of packaging. `harness_tests/**`
# ships wholesale, while the Kairos export's tools list is EXPLICIT and does not carry
# jlens_probe.py — and could not usefully, because that tool imports `engine/launch.py` and
# the export is engine-agnostic by design (no engine/ at all). So in a clone this gate's
# subject is genuinely absent: exit 2, real where it exists, vacuous here, and the exit code
# says which. The alternative — shipping a gate that crashes on import — is how a suite
# starts being ignored.
sys.path.insert(0, os.path.join(ROOT, "tools"))
if not os.path.isfile(os.path.join(ROOT, "tools", "jlens_probe.py")):
    skip("tools/jlens_probe.py is not in this tree (the export does not ship it)",
         "G-JLENS-PROBE")
if not os.path.isfile(os.path.join(ROOT, "engine", "launch.py")):
    skip("engine/launch.py is absent — the engine-agnostic export has no engine/",
         "G-JLENS-PROBE")
import jlens_probe as jp  # noqa: E402   the REAL guard, not a copy of its rule

# ── §1 every store is redirected, and the list is the shared one ─────────────────────
env = jp.build_env()
check("§1 the probe redirects every store in _gate._STORE_ENV",
      all(env.get(n) for n in jp.STORE_ENV),
      [n for n in jp.STORE_ENV if not env.get(n)])
check("§1 a clean env has no violations", jp.violations(env) == [],
      jp.violations(env)[:4])
check("§1 the store list IS _gate's, not a copy",
      jp.STORE_ENV is _gate._STORE_ENV,
      "jlens_probe must import the list; a second copy drifts the day a store is added")

# ── §2 unset is a violation ──────────────────────────────────────────────────────────
for victim in ("SP_RECALL_REGISTRY", "SP_TELEMETRY_DIR", "SP_PERSONA_FILE"):
    e2 = dict(env)
    e2.pop(victim, None)
    bad = [v for v in jp.violations(e2) if v[0] == victim]
    check("§2 an UNSET %s is a violation" % victim, bool(bad),
          "absent means the consumer's repo-relative default, which is inside her var/")

# ── §3 resolved paths, not prefixes ──────────────────────────────────────────────────
check("§3 var-probe is NOT read as inside var", not jp._under(jp.SCRATCH, jp.LIVE_VAR),
      "%s vs %s — a startswith check fails exactly here" % (jp.SCRATCH, jp.LIVE_VAR))
check("§3 a path inside var IS caught",
      jp._under(os.path.join(jp.LIVE_VAR, "memory", "registry.jsonl"), jp.LIVE_VAR), "")
e3 = dict(env)
e3["SP_TELEMETRY_DIR"] = os.path.join(jp.LIVE_VAR, "telemetry")
check("§3 a store pointed straight at her tree is caught",
      any(v[0] == "SP_TELEMETRY_DIR" for v in jp.violations(e3)), "")

# ── §4 the refusal reaches the exit code ─────────────────────────────────────────────
# Through the REAL entry point, in a subprocess, because the exit code is the thing under
# test and an in-process call cannot have one.
def _start_rc(extra_env: dict) -> int:
    ev = dict(os.environ)
    ev.update(extra_env)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "jlens_probe.py"),
                        "--status"], cwd=ROOT, capture_output=True, text=True, env=ev)
    return r.returncode


check("§4 --status on a clean tree exits 0", _start_rc({}) == 0, _start_rc({}))

# ── MUTANT: the junction a prefix check survives ─────────────────────────────────────
LINK = os.path.join(jp.SCRATCH, "memory")
made = False
moved = False
os.makedirs(jp.SCRATCH, exist_ok=True)
# `--start` creates var-probe/memory as a real directory, so on any box where the probe has
# ever run, mklink refuses and the first draft of this leg OMITTED ITSELF — passing the
# suite while never testing the one case a prefix check survives. An omit that fires in
# normal operation is a hole with a label on it. So: move a real, EMPTY directory aside,
# run the leg, put it back.
if os.path.isdir(LINK) and not os.path.islink(LINK) and not os.listdir(LINK):
    os.rename(LINK, LINK + ".gate-held")
    moved = True
if not os.path.exists(LINK):
    r = subprocess.run(["cmd", "/c", "mklink", "/J", LINK,
                        os.path.join(jp.LIVE_VAR, "memory")],
                       capture_output=True, text=True)
    made = r.returncode == 0

if not made:
    _gate.omit("MUTANT a junction from var-probe/memory into her var/memory is caught",
               "could not create a junction here (needs an elevated shell or Developer "
               "Mode, and var-probe/memory must not already exist) — the leg is real where "
               "it can run and must not pass vacuously")
else:
    try:
        v = [x for x in jp.violations(jp.build_env()) if x[0] == "SP_RECALL_REGISTRY"]
        check("MUTANT a junction from var-probe/memory into her var/memory is caught",
              bool(v),
              "resolved to %s — this is the leg a startswith() check passes, and the one "
              "that would have written her registry" % (v[0][2] if v else "nothing"))
        # ONLY IF THE VIOLATION WAS ACTUALLY SEEN. `--start` boots a 13 GB model when it
        # finds nothing wrong, and a gate that can do that during `tools/sweep.py` is a
        # hazard, not a check. So this leg runs only once the guard has already convicted
        # the junction above: it is asking "does the refusal reach the exit code", which
        # presupposes a refusal.
        if v:
            rc = subprocess.run([sys.executable,
                                 os.path.join(ROOT, "tools", "jlens_probe.py"), "--start"],
                                cwd=ROOT, capture_output=True, text=True)
            check("MUTANT --start REFUSES over the junction, exit 3", rc.returncode == 3,
                  "exit=%s out=%r" % (rc.returncode, (rc.stdout or "")[:160]))
        else:
            _gate.omit("MUTANT --start REFUSES over the junction, exit 3",
                       "not run because the guard did not convict the junction — starting "
                       "the probe here would boot a 13 GB model on a gate run")
    finally:
        subprocess.run(["cmd", "/c", "rmdir", LINK], capture_output=True)
        check("MUTANT the junction is removed again", not os.path.exists(LINK),
              "a gate that leaves a junction into her memory behind is worse than no gate")

if moved and not os.path.exists(LINK):
    os.rename(LINK + ".gate-held", LINK)
check("the real var-probe/memory is back where it was",
      (not moved) or (os.path.isdir(LINK) and not os.path.exists(LINK + ".gate-held")),
      "moved=%s link_exists=%s held_exists=%s"
      % (moved, os.path.exists(LINK), os.path.exists(LINK + ".gate-held")))

# ── §5 stopping is by port, never by image ───────────────────────────────────────────
def _code_only(path: str) -> str:
    """Source with COMMENTS AND DOCSTRINGS stripped — but string literals KEPT.

    The first draft grepped the raw file for "/IM" and went red on the comment explaining
    why /IM must not be used: a source gate asserting about its subject's prose instead of
    its code. g_hidden_tap.py strips comments first and says so, and this repo's own note
    is "my comment is the gate's subject".

    Keeping ordinary string literals is deliberate and is the other half of getting this
    right: a real `taskkill "/IM"` call IS a string literal, so stripping strings would
    make the check unable to see the thing it forbids — and would break the `/T` leg below,
    which requires one. So: drop comments, drop the module/function docstrings (a STRING
    alone on a logical line), keep everything else.
    """
    import io as _io
    import tokenize as _tok
    # A docstring is a STRING that OPENS a logical line, so the test is "what token came
    # immediately before". The first version deliberately did not update `prev` on
    # INDENT/NEWLINE in order to "skip layout" — which threw away the only signal that
    # identifies a docstring, so every one survived and the module docstring's own
    # explanation of /IM kept convicting the code. Update prev on EVERY token.
    LINE_START = (_tok.INDENT, _tok.DEDENT, _tok.NEWLINE, _tok.NL, _tok.ENCODING)
    out, prev = [], _tok.ENCODING
    with _io.open(path, "rb") as f:
        for t in _tok.tokenize(f.readline):
            if t.type == _tok.COMMENT:
                continue                      # prev unchanged: a comment is not a token
            if t.type == _tok.STRING and prev in LINE_START:
                prev = t.type
                continue
            prev = t.type
            out.append(t.string)
    return " ".join(out)


src = open(os.path.join(ROOT, "tools", "jlens_probe.py"), encoding="utf-8").read()
code = _code_only(os.path.join(ROOT, "tools", "jlens_probe.py"))
check("§5 the probe never kills by image name", "/IM" not in code,
      "taskkill /IM matches her sp-daemon too (checked against code with comments and "
      "string literals stripped, so the explanation does not convict the fix)")
check("§5 it resolves the pid by listening port", "pid_on_port" in src and "netstat" in src,
      "the exe re-execs; the Popen pid is not the process holding the port")
check("§5 and it kills the tree", '"/T"' in src,
      "the serving process is a CHILD of the spawned one; without /T it is orphaned on "
      "the GPU while the tool reports success")
launch = open(os.path.join(ROOT, "engine", "launch.py"), encoding="utf-8").read()
check("§5 engine/launch.py records why /IM cannot tell two daemons apart",
      "CANNOT TELL TWO DAEMONS APART" in launch,
      "the next person to reach for stop_daemon() from a probe needs the reason in situ")
check("§5 the argv has ONE owner", "def daemon_argv(" in launch
      and src.count("daemon_argv") >= 1,
      "three callers, one argv — the arguments are the half that drifted before")

finish("G-JLENS-PROBE")
