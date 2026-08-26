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


def sandbox(name: str = "gate", persona: str = "") -> str:
    """Point every store this repo owns at a fresh temp dir. Returns its path.

    Call it BEFORE importing anything from `harness.` — a module that resolves its root at
    import time has already found her real one by the time you set the variable.

    `persona` seeds persona.md, because a gate that needs one usually needs it non-empty.
    """
    import tempfile
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
