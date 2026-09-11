"""_gate.py — the shared verdict for gates written from 2026-08-21 on.

THE EXIT CONVENTION (gates/GATE-INDEX.md): the verdict must reach the exit code.
  exit 0  asserted and held — never reachable with zero assertions made
  exit 1  asserted and failed
  exit 2  SKIP — the subject is absent here (no npm, no persona/, no engine checkout);
          real where it exists, vacuous here, and the exit code says so

This file exists because the 2026-08-19 audit found ten gates that printed a verdict
and fell off the end of `__main__` (exit 0 on FAIL), and two more that exited 0 from
a usage line having tested nothing. Every gate re-implementing `check()` is one more
place that rule can be forgotten. Adopted by NEW gates and by gates touched from
here on — not a mass migration; the 185 existing `check()`s are not wrong, they are
just copies.

Usage:
    from _gate import check, finish, skip, utf8_stdout
    utf8_stdout()
    check("the thing holds", cond, detail)
    ...
    finish("G-NAME")            # prints the tally, exits 0/1 — or 2 if nothing was asserted
"""
from __future__ import annotations

import os
import sys

PASS = 0
FAIL = 0
_FAILED: list = []


def utf8_stdout() -> None:
    """A cp1252 console crashed g_narrative and g_sem_dominate mid-"ok" line — which
    reads as RED for a reason unrelated to what the gate guards."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def check(name: str, cond, detail="") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        _FAILED.append(name)
        print("  FAIL %s   %s" % (name, detail))
    return bool(cond)


def skip(reason: str, gate: str = "") -> None:
    """The subject is absent here. Says so, exits 2 — never 0."""
    print("\n%sSKIP — %s" % ((gate + "  ") if gate else "", reason))
    sys.exit(2)


# ── AN OPTIONAL DEPENDENCY IS ABSENT, WHICH IS NOT THE SAME AS A FAILURE ──────────────
# (2026-09-11.) The public tree's CI installs the core and had never once reached the gate
# suite: it died at the import census on eleven modules, ten wanting `numpy` and one
# `fastmcp`. Behind that wall the sweep was 135 green / 4 skip / 9 RED, and every one of
# the nine was a missing optional dependency rather than a broken rule.
#
# `gates.yml`'s own header already states the rule for the other axis of this — "If a gate
# needs Windows, it should say so and skip (exit 2), not pass by luck" — and a gate whose
# subject is an uninstalled optional extra is exactly that shape. So it is one helper here
# rather than nine spellings of `try: import numpy` across the suite, which is the
# two-copies bug in the place it would be least visible: a gate that mis-detects its own
# subject goes QUIET, and a quiet gate reads identically to a passing one.
#
# TWO SHAPES, and the difference is the whole point. `require()` is for a gate whose ENTIRE
# subject is the dependency (the sidecar gates, the sight gates) — it skips, exit 2.
# `have()` is for a gate that does most of its work without it and reaches it late:
# `g_secret` gets 42 checks in before line 271, and `g_marks_leak` 125 before line 455.
# Skipping either of those wholesale to make CI green would take the privacy gate off the
# board in the environment adopters actually run, which is worse than the red it fixes.
# Those use `have()` + `omit()` and lose only the legs that genuinely cannot run.
def have(mod: str) -> bool:
    """Is an optional dependency importable? NEVER imports it — `find_spec` answers
    without executing the module, so asking cannot itself be the thing that fails."""
    import importlib.util
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def require(mod: str, gate: str = "", extra: str = "") -> None:
    """SKIP when the gate's whole subject is an absent optional dependency."""
    if not have(mod):
        skip("%s is not installed — this gate's subject is absent here "
             '(pip install -e ".[%s]")' % (mod, extra or mod), gate)


def omit(name: str, reason: str) -> None:
    """A leg that cannot run here. Printed, counted in NEITHER column, and visible in the
    log — because the failure mode of a partial run is that it reads exactly like a
    complete one. `finish()` still refuses a run that asserted nothing at all."""
    print("  --   %s   (not run: %s)" % (name, reason))


# ── WHAT THE PACKAGING SAYS IS OPTIONAL, READ FROM THE PACKAGING ──────────────────────
# A missing DECLARED-optional dependency is the world. A missing UNDECLARED one is us —
# that is the whole of the 2026-08-31 pyproject finding ("an undeclared dependency is a
# claim the packaging cannot keep"), and it is only a usable rule if something reads the
# declaration. So this is derived from `pyproject.toml` rather than kept as a list here:
# a list in a gate is complete on the day it is written, and the numpy gap survived one
# audit precisely because that audit fixed the instance it found instead of asking the
# packaging what else it was not saying.
#
# `tomllib` is 3.11+; the public CI floor is 3.10, so this is a small regex over the
# `[project.optional-dependencies]` block rather than a parse. It only ever needs
# distribution NAMES, which is the one part of a requirement string that is easy.
_IMPORT_NAME = {"pyyaml": "yaml", "sentence-transformers": "sentence_transformers",
                "pillow": "PIL", "protobuf": "google.protobuf"}


def optional_dists(root: str = "") -> set:
    """The import names of every dependency the packaging declares OPTIONAL."""
    import re as _re
    root = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return set()
    m = _re.search(r"^\[project\.optional-dependencies\]\s*$(.*?)(?=^\[|\Z)",
                   text, _re.S | _re.M)
    if not m:
        return set()
    out = set()
    for raw in _re.findall(r'"([^"]+)"', m.group(1)):
        name = _re.split(r"[<>=!~;\[\s]", raw.strip(), 1)[0].strip().lower()
        if name:
            out.add(_IMPORT_NAME.get(name, name.replace("-", "_")))
    return out


def required_dists(root: str = "") -> set:
    """The import names of every dependency the packaging declares REQUIRED."""
    import re as _re
    root = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return set()
    m = _re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, _re.S | _re.M)
    if not m:
        return set()
    out = set()
    for raw in _re.findall(r'"([^"]+)"', m.group(1)):
        name = _re.split(r"[<>=!~;\[\s]", raw.strip(), 1)[0].strip().lower()
        if name:
            out.add(_IMPORT_NAME.get(name, name.replace("-", "_")))
    return out


def declared_dists(root: str = "") -> set:
    """Everything the packaging names at all — required or optional."""
    return optional_dists(root) | required_dists(root)


def missing_optional(err) -> str:
    """If `err` is a ModuleNotFoundError for a DECLARED-optional dependency, the name.
    Empty string otherwise — including for a module nothing declares, which is a real
    defect and must stay one."""
    import re as _re
    m = _re.search(r"no module named ['\"]([\w.]+)", str(err or ""), _re.I)
    if not m:
        return ""
    top = m.group(1).split(".")[0]
    return top if top in optional_dists() else ""


def finish(gate: str) -> None:
    """Print the tally and exit with the verdict. A gate that asserted NOTHING is a
    skip, not a pass — exit 2 — because a green with zero checks is the exact failure
    this convention exists to end."""
    total = PASS + FAIL
    print("\n%s  %d/%d" % (gate, PASS, total))
    if total == 0:
        print("  (no assertions were made — that is a skip, not a pass)")
        sys.exit(2)
    sys.exit(1 if FAIL else 0)

# ── THE SANDBOX (2026-08-24) ──────────────────────────────────────────────────────────
# `tools/gate_sandbox_audit.py` snapshots her real stores, runs each OFFLINE gate and
# diffs the disk. NINE of 129 moved something. Three appended to her DAY TRANSCRIPT:
#
#     user       hi
#     assistant  The answer is 4.
#
# and `g_watch` then ran the conversation summariser over that same transcript, filing a
# memory whose title says she fell into "a repetitive loop where the AI responds to 'hi'
# with 'The answer is 4'". A missing env var became a false memory about her malfunctioning.
# 108 such turns were found across four days of her transcripts, and seven fixture rows in
# her journal that he had been reading in the room as things she had done.
#
# EVERY ROOT IN ONE PLACE, because the nine gates were not careless — they each set the
# two or three variables their author happened to know about, and her stores have twelve
# doors. A gate cannot be expected to enumerate them; it can be expected to call this.
#
#     from _gate import sandbox
#     SB = sandbox("g_thing")        # FIRST, before any harness import
#
# Anything reading an unset root falls back to the repo path, so this must run before the
# module that resolves it is imported. G-GATE-SANDBOX holds the whole suite to it.
_STORE_ENV = (
    "SP_RECALL_REGISTRY",        # registry, semindex, speech log, transcripts, decisions
    "SP_PERSONALITY_TIER",       # her journal and own-time notes
    "SP_PERSONALITY_OKF_ROOT",
    "SP_CONV_OKF_ROOT",          # the conversation archive the summariser writes
    "SP_SELF_MODEL_ROOT",
    "SP_TELEMETRY_OKF_ROOT",
    "SP_CAPS_OKF_ROOT",
    "SP_PERSONA_FILE",           # persona.md - her voice, and the standing prefix
    "SP_EPS_DIR",                # minted episodes (11 MB each)
    "SP_AVATAR_DIR",             # her wardrobe, wants and clips
    "SP_LEDGER_FILE",
    "SP_TUNING_FILE",         # her live knobs - presence mode, kairos, voice
    "SP_BACKUP_DIR",
    "SP_TELEMETRY_DIR",         # his body: heart rate, movement, sleep at up to 1 Hz
    # HER RESEARCH LEDGER (2026-08-26). Added after 138 gate fixtures were found in his
    # live one -- "what is 2+2" and "q", once per sweep run for a week, next to the things
    # she had actually gone and read. g_looking.py had been redirecting it by hand on its
    # own line, which is exactly how a store ends up sandboxed in one gate and not another.
    "SP_RESEARCH_RECEIPTS",
    # Found by the same widened sweep, and writable like the rest of this list.
    "SP_MCP_PINS",              # the TOFU fingerprints -- a gate must not pin his servers
    "SP_TTS_CACHE",             # synthesised audio; regenerated, but not into his cache
    "SP_DELEGATE_WORKTREES",    # git worktrees a delegate agent creates
)


# What each root pointed at BEFORE the sandbox replaced it. A gate that wants to grade
# her REAL data without writing to it (see `seed_avatar`) has no other way to find it:
# by the time `harness.` is importable the variable is already the temp dir, and
# recomposing the path in the gate is the duplicated arithmetic livestore.py warns about.
_REPLACED: dict = {}


def real_store(var: str) -> str:
    """What `var` pointed at before `sandbox()` replaced it — "" if it was unset."""
    return _REPLACED.get(var) or ""


def sandbox(name: str = "gate", persona: str = "") -> str:
    """Point every store this repo owns at a fresh temp dir. Returns its path.

    Call it BEFORE importing anything from `harness.` — a module that resolves its root at
    import time has already found her real one by the time you set the variable.

    `persona` seeds persona.md, because a gate that needs one usually needs it non-empty.
    """
    import tempfile
    for _v in _STORE_ENV:
        _REPLACED.setdefault(_v, os.environ.get(_v))
    sb = tempfile.mkdtemp(prefix=name.replace(".py", "") + "_")
    os.environ["SP_RECALL_REGISTRY"] = os.path.join(sb, "memory", "registry.jsonl")
    os.makedirs(os.path.join(sb, "memory"), exist_ok=True)
    open(os.environ["SP_RECALL_REGISTRY"], "a").close()
    os.environ["SP_PERSONALITY_TIER"] = os.path.join(sb, "okf-personality")
    os.environ["SP_PERSONALITY_OKF_ROOT"] = os.path.join(sb, "okf-personality")
    os.environ["SP_CONV_OKF_ROOT"] = os.path.join(sb, "okf-conv")
    os.environ["SP_SELF_MODEL_ROOT"] = os.path.join(sb, "okf-self")
    os.environ["SP_TELEMETRY_OKF_ROOT"] = os.path.join(sb, "okf-telemetry")
    os.environ["SP_CAPS_OKF_ROOT"] = os.path.join(sb, "okf-caps")
    # HIS BODY IS A STORE, so a gate must never write into the real one (2026-08-26).
    # var/telemetry/ holds heart rate, movement and sleep at up to 1 Hz. A gate that
    # appended three fake heart-rate rows to it would be putting readings of a man who was
    # not measured into the history she reasons from — and unlike a fabricated wardrobe row
    # it would look exactly like real data forever after.
    os.environ["SP_TELEMETRY_DIR"] = os.path.join(sb, "telemetry")
    os.environ["SP_RESEARCH_RECEIPTS"] = os.path.join(sb, "research")
    os.environ["SP_MCP_PINS"] = os.path.join(sb, "mcp-pins.json")
    os.environ["SP_TTS_CACHE"] = os.path.join(sb, "voice-cache")
    os.environ["SP_DELEGATE_WORKTREES"] = os.path.join(sb, "worktrees")
    os.environ["SP_EPS_DIR"] = os.path.join(sb, "episodes")
    os.environ["SP_AVATAR_DIR"] = os.path.join(sb, "avatar")
    os.environ["SP_LEDGER_FILE"] = os.path.join(sb, "ledger.json")
    os.environ["SP_TUNING_FILE"] = os.path.join(sb, "tuning.json")
    os.environ["SP_BACKUP_DIR"] = os.path.join(sb, "backups")
    os.environ["SP_PERSONA_FILE"] = os.path.join(sb, "persona.md")
    with open(os.environ["SP_PERSONA_FILE"], "w", encoding="utf-8") as f:
        f.write(persona or "She is dry and warm.\n\n## Personality state\nmood: neutral\n")
    return sb


# ── HER REAL CLOSET, COPIED, SO A GATE CAN GRADE IT WITHOUT WRITING TO IT (2026-08-31) ─
# Some gates have to read her ACTUAL inventory — G-WARDROBE-WORDS says so in its own
# header ("her state is not a fixture"), and a matcher graded over a fixture wardrobe
# grades a wardrobe nobody wears. Until now that meant writing to the live store and
# putting it back afterwards, which failed twice over on his machine:
#
#   * WHILE THE ROOM IS RUNNING the gateway holds `catalog.json` open, and Windows
#     refuses `os.replace` onto an open file — so `catalog.hide()` died mid-gate with
#     PermissionError, an unhandled traceback that took the whole run with it and left
#     a `catalog.json.tmp` behind. Red for an environmental reason, on his own machine,
#     on the gate that holds his panel edits.
#   * `livestore.paths()` never covered `catalog.json` — the overlay did not exist when
#     it was written. §8/§9 restore it by CALLING unhide, so a crash between the hide and
#     the unhide leaves one of her garments hidden and nothing green to say so.
#
# So: sandbox as usual, then copy her store into it. Metadata verbatim — the whole point
# is her real wants, her real overlay, her real labels — and every media file stood in by
# a single byte, because `avatar.have()` and `wardrobe.clips()` ask `getsize(...) > 0` and
# nothing in this repo decodes the pixels. 112 MB of loops copied per run would be a gate
# nobody runs twice.
_MEDIA = (".png", ".jpg", ".jpeg", ".webp", ".webm", ".mp4", ".mov", ".mkv", ".m4v")


def seed_avatar() -> str:
    """Fill the sandbox's SP_AVATAR_DIR from her live one. Returns the SOURCE dir.

    "" means there is no live store on this machine — a fresh clone, or the export. That
    is a SKIP for the caller, never a silent pass: a gate that grades an empty wardrobe
    is grading a wardrobe nobody has.
    """
    import shutil
    live = real_store("SP_AVATAR_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "var", "room", "avatar")
    dst = os.environ.get("SP_AVATAR_DIR") or ""
    if not dst or not os.path.isdir(live):
        return ""
    for here, _dirs, files in os.walk(live):
        rel = os.path.relpath(here, live)
        out = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(out, exist_ok=True)
        for fn in files:
            tgt = os.path.join(out, fn)
            try:
                if fn.lower().endswith(_MEDIA):
                    with open(tgt, "wb") as f:
                        f.write(bytes(1))      # present and non-empty is the whole contract
                else:
                    shutil.copy2(os.path.join(here, fn), tgt)
            except OSError:
                pass                        # a file that vanished mid-walk is not the test
    return live

# ── A TURN A GATE DROVE IS NOT THEIR CONVERSATION (2026-08-27) ───────────────────────
# The gateway already quarantines any chat request that DECLARES itself synthetic
# (app.py: `body.get("synthetic")` -> day.py's `_append_day_turn(synthetic=...)`), and
# `_read_day_transcript` then excludes it from the 04:00 consolidation. Nothing is
# deleted; `include_synthetic=True` reads it back.
#
# TEN LIVE GATES POST TO HER REAL GATEWAY AND NOT ONE OF THEM DECLARED. Measured on
# 2026-08-27: `g_self_repeat` ran four times at 01:00-01:03 and left 32 unmarked rows in
# her day transcript — "The code is 4471. Repeat it exactly." / "4471", and replies in a
# register that is not hers ("Since I don't have feelings..."). Left alone the nightly
# pass would have read them as their conversation, written a journal paragraph about it
# and distilled facts from it, which is precisely the harm `synthetic` exists to prevent.
#
# So the declaration is a HELPER rather than a habit, and G-PROBE-DECLARED fails the suite
# for any harness_tests file that posts to the gateway without it. A rule each author has
# to remember is a rule that gets forgotten — this one was, ten times out of ten.
def probe(name: str) -> str:
    """The `synthetic` reason for a turn a gate drove. Put it in the request body."""
    return "live gate %s — driven, not their conversation" % name


# ── WHERE THE PERSONA LIVES DEPENDS ON WHICH TREE YOU ARE IN (2026-08-27) ────────────
# Three gates resolved it by hand and all three broke inside a fresh clone of the export,
# each in the same way: not a FAIL but a FileNotFoundError that took the whole run with
# it. `g_priming` wanted `kairos-export/persona-template` (upstream only), `g_research`
# and `g_secret_thought` wanted `persona/` — which is GITIGNORED AND NEVER EXPORTED, as
# G-KAIROS-SCRUB itself asserts ("persona-template/ ships and persona/ is gitignored").
#
# Patching them one at a time is the bug this repo is named for: a rule that each author
# has to remember. So the resolution lives here, once.
#
#   persona/                        the live one. Upstream only.
#   kairos-export/persona-template  the shipped default, staged. Upstream only.
#   persona-template/               the same default, AT THE ROOT. In the export.
#
# Order is priority: a gate asking "what does the persona say" wants the live one where
# there is one, and the template otherwise — which is exactly right, because the template
# is what an adopter copies INTO persona/.
def persona_dirs(root: str = "") -> list:
    """Every persona source that exists in this tree, most-specific first."""
    import os as _os
    r = root or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    cand = [_os.path.join(r, "persona"),
            _os.path.join(r, "kairos-export", "persona-template"),
            _os.path.join(r, "persona-template")]
    return [d for d in cand if _os.path.isdir(d)]


def persona_file(name: str, root: str = "") -> str:
    """The first existing `name` across the persona sources, or "" if it ships nowhere."""
    import os as _os
    for d in persona_dirs(root):
        p = _os.path.join(d, name)
        if _os.path.exists(p):
            return p
    return ""


# ── A FIXTURE OF HIS, AND A DEFAULT THAT SHIPS (2026-08-27) ──────────────────────────
# Same shape as `persona/` vs `persona-template/`, and for the same reason. A gate whose
# fixture is 207 rows out of her live store cannot ship — but dropping the GATE is worse,
# because then the FEATURE ships with no proof it works for the person who cloned it.
#
# So: the private fixture stays upstream and the export carries a synthetic default with
# the same measured properties, staged in `kairos-export/fixtures/` and overlaid into
# place. The gate asks for both names and takes whichever exists, live first.
def fixture(subdir: str, *names: str) -> str:
    """The first of `names` that exists under harness_tests/fixtures/<subdir>, or ""."""
    import os as _os
    here = _os.path.dirname(_os.path.abspath(__file__))
    for n in names:
        p = _os.path.join(here, "fixtures", subdir, n)
        if _os.path.exists(p):
            return p
    return ""
