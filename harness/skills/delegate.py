"""delegate — her hands, held at arm's length. Grok writes code in a worktree; the operator merges.

THE ARRANGEMENT, which is the operator's and not mine
─────────────────────────────────────────────────────
    AUTONOMY       worktree + gates; HE MERGES. She never lands anything.
    BLAST RADIUS   harness/, harness_tests/, docs/, profiles/, gates/ writable.
                   .rs, .cu, serve.py READ-ONLY — she may read engine source and propose an
                   engine diff in prose, and may not edit one.

Both are enforced here, and the enforcement is deliberately not where you would first put it.

WHY THE FLAGS ARE NOT THE GUARANTEE
───────────────────────────────────
`~/.grok/config.toml` on this machine contains:

    permission_mode = "always-approve"

so every invocation MUST pass `--permission-mode` and `--deny` EXPLICITLY rather than inherit.
It does. But a rule you have to remember to pass is a rule you will one day forget — this repo's
entire bug class is an invariant enforced in one of two paths — and `--deny`'s grammar is
Claude Code's, resolved out of `~/.claude/settings.json`, which is a file neither this module nor
its gate controls. A silently mis-spelled rule fails OPEN.

So the flags are the first layer and the VERDICT ON THE RESULTING DIFF is the authority:

    every changed path must lie inside a writable root, or the delegation is REFUSED.

That check reads what actually happened on disk. It cannot be mis-spelled into permissiveness,
it does not depend on Grok honouring anything, and it is what `g_delegate.py` asserts. A refused
delegation still leaves its branch — nothing is deleted, the operator can look — but it is
reported as REFUSED and its gate results are not offered as reassurance.

AND THE WORKTREE IS THE FLOOR UNDER BOTH — BUT ONLY BECAUSE WE BUILD IT OURSELVES
────────────────────────────────────────────────────────────────────────────────
The first cut of this passed `--worktree sp/<slug>` and treated the resulting isolation as the
floor under everything. MEASURED, 2026-07-30, against grok 0.2.93:

    grok -p "..." --cwd <repo> --worktree probe1 --permission-mode acceptEdits
      -> returncode 0, valid JSON, "stopReason": "Cancelled"
      -> NO WORKTREE CREATED, no branch, nothing in `git worktree list`

`--worktree` says "start the SESSION in a new git worktree" and does not apply to headless
`-p`. It is accepted, ignored, and silent. Had the permission mode not independently cancelled
the run, the edits would have landed in THE LIVE TREE while this module reported a branch name
that never existed — and the diff verdict would have been judging his working copy after the
fact. A flag that quietly does nothing is worse than no flag, because it is load-bearing in
the reader's head.

So the worktree is created HERE, with git, before Grok is invoked, and Grok is pointed at it
with `--cwd`. Isolation is now a thing we built rather than a thing we requested. This is the
same principle as the diff verdict above: never let the guarantee depend on another program
honouring a flag.

WHAT SHE IS TOLD ABOUT THIS, AND WHY IT MATTERS THAT SHE IS TOLD
────────────────────────────────────────────────────────────────
A capability the model does not understand is a capability it misuses politely. The live teaching
lives in `persona.md` ("Your hands, and how far they reach") — which is gitignored, operator-owned
and therefore NOT in a fresh clone, so the substance is recorded here as prose rather than as a
second copy of the text that would drift from it:

  - the work happens in an ISOLATED COPY on its own branch; nothing she does touches his tree;
  - **she never merges** — she reports the branch, the file count and the gate result, and says
    outright that merging is his;
  - the harness, tests, docs and profiles are hers to change; the ENGINE (`.rs`, `.cu`,
    `serve.py`) is read-only — she may read it and describe a change she would make, and may not
    make it, because a bad edit there does not fail loudly, it fails as her;
  - keep each job SMALL — one change a person can review in a couple of minutes, because a
    sprawling diff nobody reviews is not help;
  - report honestly: a refusal is stated plainly and not dressed up with the gate results, a
    failed test leads, and "it's done" is only ever said about something she watched be true.

The last one is the load-bearing line. Every hard guarantee above is enforced in code — the
worktree, the diff verdict, the absence of any merge path — so the ONLY thing the prompt is
actually responsible for is whether she describes the outcome truthfully. That is the part no
gate can hold, which is why it is the part the teaching spends its words on.

THE PERMISSION MODE, also measured, and it is not the one you would guess:

    acceptEdits -> Cancelled (headless has nobody to ask)
    dontAsk     -> Cancelled
    auto        -> executes

So `auto` it is, and `--always-approve` still never. `auto` is more permissive than I wanted,
which makes the deny rules and the diff verdict MORE load-bearing, not less — and it is
acceptable only because the containment is now real: it runs inside a disposable worktree this
module created, and nothing it does can reach the live tree or be merged.

WHAT SHE GETS BACK is a sentence: "branch sp/<slug>, 3 files, gates 27/27" — or the refusal and
why. Every delegation writes a receipt (goal, branch, argv, changed paths, verdict, gates,
diffstat) to the telemetry tier, because an action without a record is the thing this project
does not do.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from typing import Callable, Dict, List, Optional, Tuple

from harness.loud import swallowed as _swallowed

logger = logging.getLogger(__name__)

GROK = os.environ.get("SP_GROK_BIN") or os.path.join(
    os.path.expanduser("~"), ".grok", "bin", "grok.exe")

# ── THE BLAST RADIUS, AS DATA ────────────────────────────────────────────────────────
# Prefixes, matched against repo-relative paths with forward slashes. A changed path is
# allowed iff it lies under one of these. Everything else — including anything the list
# simply does not anticipate — is refused: the default is NO, which is the only default
# that stays correct when the repo grows a directory nobody thought about.
WRITABLE_ROOTS: Tuple[str, ...] = (
    "harness/", "harness_tests/", "docs/", "profiles/", "gates/", "fixtures/",
)

# The read-only surface, named EXPLICITLY as well. Redundant with the allow-list above by
# construction (none of these live under a writable root), and kept because a refusal should
# be able to say "that is engine source" rather than "that is not on a list".
ENGINE_READONLY = re.compile(
    r"(^|/)(serve\.py)$|\.(rs|cu|cuh|h|hpp|cpp|toml\.lock)$|^(engine|core)/", re.IGNORECASE)

# Deny rules in Claude Code grammar, passed EXPLICITLY on every call. First layer only —
# see the module docstring on why these are not the guarantee.
DENY_RULES: Tuple[str, ...] = (
    "Edit(engine/**)", "Write(engine/**)", "Edit(core/**)", "Write(core/**)",
    "Edit(**/*.rs)", "Write(**/*.rs)", "Edit(**/*.cu)", "Write(**/*.cu)",
    "Edit(serve.py)", "Write(serve.py)",
    "Bash(git push:*)", "Bash(git merge:*)", "Bash(git checkout main:*)",
    "Bash(git checkout master:*)", "Bash(git reset:*)",
)

DEFAULT_MAX_TURNS = 20
DEFAULT_TIMEOUT_S = 1800.0

REFUSED = "REFUSED"
CLEAN = "CLEAN"
FAILED = "FAILED"


def enabled() -> bool:
    """SP_DELEGATE — mapped in serve.py, DEFAULT OFF.

    This spawns a coding agent with edit rights on his machine. It is exactly the kind of
    capability that should be switched on deliberately and never discovered.
    """
    return os.environ.get("SP_DELEGATE", "0") == "1"


def repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def slugify(goal: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (goal or "").lower()).strip("-")
    return (s[:40].rstrip("-") or "task")


# ── THE VERDICT ON THE DIFF: the authority ───────────────────────────────────────────
def classify(paths: List[str]) -> Dict[str, List[str]]:
    """Split changed paths into allowed / engine / outside. Pure, so the gate can walk it."""
    allowed, engine, outside = [], [], []
    for p in paths:
        q = (p or "").replace("\\", "/")
        # `lstrip("./")` strips those as a CHARACTER SET, not a prefix — the classic misuse,
        # and here it was a hole rather than a cosmetic bug: it turned ".github/x" into
        # "github/x" and, worse, ".harness/evil.py" into "harness/evil.py", WHICH IS AN
        # ALLOWED PATH. A dotfile directory would have been normalised straight through the
        # blast radius. Strip the prefix, repeatedly, and only the prefix.
        while q.startswith("./"):
            q = q[2:]
        if not q:
            continue
        # Traversal and absolute paths are refused outright rather than normalised. `git
        # status --porcelain` emits neither, so refusing costs nothing real — and "normalise
        # it until it looks safe" is how the lstrip hole existed in the first place.
        if ".." in q.split("/") or q.startswith("/") or re.match(r"^[A-Za-z]:", q):
            outside.append(q)
            continue
        if ENGINE_READONLY.search(q):
            engine.append(q)
        elif any(q.startswith(r) for r in WRITABLE_ROOTS):
            allowed.append(q)
        else:
            outside.append(q)
    return {"allowed": allowed, "engine": engine, "outside": outside}


def verdict_for(paths: List[str]) -> Tuple[str, str]:
    """(verdict, reason) for a set of changed paths. REFUSED unless every one is allowed."""
    c = classify(paths)
    if c["engine"]:
        return REFUSED, "touched engine source (read-only): %s" % ", ".join(c["engine"][:6])
    if c["outside"]:
        return REFUSED, "touched paths outside the blast radius: %s" % ", ".join(c["outside"][:6])
    if not c["allowed"]:
        return FAILED, "no files changed"
    return CLEAN, "%d file(s), all inside the blast radius" % len(c["allowed"])


# ── the invocation ───────────────────────────────────────────────────────────────────
def build_argv(goal: str, *, cwd: str,
               max_turns: int = DEFAULT_MAX_TURNS) -> List[str]:
    """The exact command line. Extracted so the gate can assert on it without running it.

    `cwd` IS THE WORKTREE, not the repo — see the module docstring. `--worktree` is
    deliberately NOT passed: measured against grok 0.2.93 it is accepted, ignored and silent
    in headless `-p` mode, and a flag that quietly does nothing is worse than no flag.

    Every safety-relevant flag is passed EXPLICITLY — `--permission-mode` above all, because
    the user config sets `permission_mode = "always-approve"` and inheriting that would give a
    headless agent blanket approval on his machine.
    """
    argv = [GROK, "-p", goal,
            "--cwd", cwd,
            "--output-format", "json",
            "--max-turns", str(int(max_turns)),
            # MEASURED: acceptEdits and dontAsk both return stopReason "Cancelled" headless —
            # there is nobody to ask — so `auto` is the only mode that executes at all. It is
            # more permissive than I would choose, which is why the deny rules and the diff
            # verdict matter more here, not less. Never `bypassPermissions`, never
            # `--always-approve`. The containment is the worktree, and we build that.
            "--permission-mode", "auto",
            # no fan-out and no network: a delegated edit has no business browsing, and
            # subagents would each need their own copy of every rule below.
            "--no-subagents", "--disable-web-search"]
    for rule in DENY_RULES:
        argv += ["--deny", rule]
    return argv


PROMPT_PREFIX = (
    "You are making a SMALL, REVIEWABLE change in an isolated git worktree of the "
    "Kairos repository. Read AGENTS.md first.\n\n"
    "HARD CONSTRAINTS:\n"
    "- You may edit ONLY: harness/, harness_tests/, docs/, profiles/, gates/, fixtures/.\n"
    "- engine/, core/, any .rs or .cu file, and serve.py are READ-ONLY. You may read them "
    "and describe a change in prose; you may not edit them. A diff touching them is "
    "discarded wholesale.\n"
    "- Do not commit, merge, push, or switch branches. Leave the work in the worktree.\n"
    "- Every claim needs a repeatable check. If you change behaviour, change or add the gate "
    "that proves it.\n"
    "- Nothing in memory is ever deleted: tombstone or quarantine, never rewrite a store "
    "minus a row.\n\n"
    "THE GOAL:\n")


def worktree_root() -> str:
    """Where delegated worktrees live: BESIDE the repo, never inside it.

    Inside would put the agent's checkout under the repo's own path, where `git status` in the
    live tree would see it and where a careless glob could sweep it into a commit.
    """
    return os.environ.get("SP_DELEGATE_WORKTREES") or os.path.join(
        os.path.dirname(repo_root()), "_sp_worktrees")


def _make_worktree(root: str, branch: str) -> Tuple[Optional[str], str]:
    """Create the worktree OURSELVES, off the current HEAD. (path, reason).

    This is the containment, and it is ours — `--worktree` is inert in headless mode (see the
    module docstring). If this fails, the delegation does NOT run: there is no fallback to
    "just work in the live tree", because that is precisely the outcome the whole design
    exists to make impossible.
    """
    base = worktree_root()
    path = os.path.join(base, branch.replace("/", "-"))
    try:
        os.makedirs(base, exist_ok=True)
        if os.path.exists(path):
            return None, "a worktree for %s already exists at %s" % (branch, path)
        r = subprocess.run(["git", "-C", root, "worktree", "add", "-b", branch, path, "HEAD"],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            return None, (r.stderr or r.stdout or "git worktree add failed").strip()[:300]
    except Exception as exc:
        return None, str(exc)[:200]
    if not os.path.isdir(path):
        return None, "git reported success but %s does not exist" % path
    return path, "created"


def _changed_paths(wt: str, base: str = "HEAD") -> List[str]:
    try:
        out = subprocess.run(["git", "-C", wt, "status", "--porcelain"],
                             capture_output=True, text=True, timeout=120).stdout
    except Exception as _swx:
        _swallowed(logger, "_changed_paths", _swx, lane="skills")
        return []
    paths = []
    for line in out.splitlines():
        s = line[3:].strip() if len(line) > 3 else ""
        if " -> " in s:                     # a rename touches BOTH sides
            a, b = s.split(" -> ", 1)
            paths += [a.strip().strip('"'), b.strip().strip('"')]
        elif s:
            paths.append(s.strip().strip('"'))
    return paths


def _stop_reason(stdout: str) -> str:
    """Grok's own verdict on its run. "Cancelled" is the one that cost an afternoon: a
    returncode of 0 and well-formed JSON, with nothing done."""
    try:
        return str(json.loads(stdout or "{}").get("stopReason", ""))
    except Exception as _swx:
        _swallowed(logger, "_stop_reason", _swx, lane="skills")
        return ""


# ── WHICH GATES CAN HONESTLY BE RUN IN A WORKTREE (measured 2026-07-30) ──────────────
# A fresh worktree has no `var/memory/` — the store is gitignored, so it is simply not there.
# The first live delegation reported "Gates 6/8 (failing: g_durability, g_onedoor)" for a
# change that added ONE DOCS FILE. Both of those read the live store, so they fail in any
# worktree, for any change, forever. Reporting that as a gate failure of HER work is a lie
# with a receipt on it, and it would have taught him to ignore the number.
#
# Determined by running every candidate in a clean worktree: these pass, those two do not.
# The list is deliberately the PORTABLE set rather than the important set — a gate that
# cannot run here tells us nothing here.
OFFLINE_GATES = ("g_claim", "g_memory_lifecycle", "g_sem_conserve", "g_toolsafety",
                 "g_task_table", "g_narrative", "g_salience", "g_hodor", "g_ladder_table",
                 "g_sem_table", "g_sem_admissible", "g_sem_stable", "g_asked", "g_secret",
                 "g_onewriter", "g_capture_async")
# Excluded, with the reason, so nobody "helpfully" adds them back:
STORE_DEPENDENT_GATES = ("g_durability", "g_onedoor")   # read var/memory/, absent in a worktree


def _run_gates(wt: str, gates=OFFLINE_GATES, timeout: float = 900.0) -> Dict[str, object]:
    """Run the offline suite INSIDE the worktree. Reported, never trusted to pass."""
    passed, failed = [], []
    for g in gates:
        p = os.path.join(wt, "harness_tests", "%s.py" % g)
        if not os.path.exists(p):
            continue
        try:
            r = subprocess.run(["python", p], cwd=wt, capture_output=True,
                               text=True, timeout=timeout)
            (passed if r.returncode == 0 else failed).append(g)
        except Exception:
            failed.append(g)
    return {"passed": passed, "failed": failed,
            "summary": "%d/%d" % (len(passed), len(passed) + len(failed))}


def _receipt(rec: Dict[str, object]) -> Optional[str]:
    try:
        from harness.personality.self_model import HARNESS_ROOT
        tier = os.environ.get("SP_TELEMETRY_OKF_ROOT") or str(
            HARNESS_ROOT / "memory-okf-telemetry")
        d = os.path.join(tier, "delegate")
        os.makedirs(d, exist_ok=True)
        # The branch contains a "/" and a branch name is not a filename — the first live run
        # died on exactly that, after the work was done.
        safe = str(rec.get("branch", "x")).replace("/", "-").replace("\\", "-")
        p = os.path.join(d, "%s-%s.json" % (int(time.time()), safe))
        with open(p, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2)
        return p
    except Exception as exc:
        logger.warning("[delegate] receipt not written: %s", exc)
        return None


def delegate_code(goal: str, run: Optional[Callable] = None,
                  max_turns: int = DEFAULT_MAX_TURNS) -> str:
    """Ask the coding agent to make a change in an isolated worktree. NEVER merges.

    Returns one sentence for her to say. `run` is injectable so the gate can exercise every
    path — including a rogue agent that edits engine source — without spawning anything.
    """
    if not enabled():
        return ("(I can't make code changes right now — delegation is switched off. "
                "SP_DELEGATE would need to be on.)")
    goal = (goal or "").strip()
    if not goal:
        return "(I need to know what to change.)"

    root = repo_root()
    branch = "sp/" + slugify(goal)
    rec: Dict[str, object] = {"goal": goal, "branch": branch,
                              "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    # THE CONTAINMENT COMES FIRST, AND IT IS OURS. No worktree, no run — there is deliberately
    # no fallback to working in the live tree, because that is the outcome this whole design
    # exists to make impossible.
    wt, why = _make_worktree(root, branch)
    rec["worktree"], rec["worktree_reason"] = wt, why
    if not wt:
        rec["verdict"] = FAILED
        rec["reason"] = "no worktree: %s" % why
        _receipt(rec)
        return ("(I couldn't make an isolated copy to work in, so I didn't start: %s)"
                % why[:140])

    argv = build_argv(PROMPT_PREFIX + goal, cwd=wt, max_turns=max_turns)
    rec["argv"] = argv
    runner = run or (lambda a: subprocess.run(a, capture_output=True, text=True,
                                              timeout=DEFAULT_TIMEOUT_S))
    try:
        proc = runner(argv)
        rec["returncode"] = getattr(proc, "returncode", None)
        rec["stop_reason"] = _stop_reason(getattr(proc, "stdout", "") or "")
    except Exception as exc:
        rec["verdict"] = FAILED
        rec["reason"] = str(exc)[:200]
        _receipt(rec)
        return "(I tried to delegate that and the coding agent would not start: %s)" % str(exc)[:120]

    changed = _changed_paths(wt)
    rec["changed"] = changed
    verdict, reason = verdict_for(changed)
    rec["verdict"], rec["reason"] = verdict, reason

    # A cancelled run with no diff is not a failure of the blast radius; it is Grok declining
    # to act, and saying so plainly beats "no files changed".
    if verdict == FAILED and rec.get("stop_reason") == "Cancelled":
        _receipt(rec)
        return ("The coding agent cancelled that one without doing anything — branch `%s` is "
                "there but empty." % branch)

    if verdict != CLEAN:
        # NOTHING IS DELETED — the branch stays for him to inspect. But the gates are not run
        # and not reported: a green suite next to an out-of-bounds diff reads as reassurance,
        # and the diff is the problem.
        _receipt(rec)
        logger.warning("[delegate] %s on %s: %s", verdict, branch, reason)
        return ("I worked on that in branch `%s`, but I'm not offering it: %s. "
                "The branch is there if you want to look." % (branch, reason))

    gates = _run_gates(wt)
    rec["gates"] = gates
    _receipt(rec)
    tail = "" if not gates["failed"] else " (failing: %s)" % ", ".join(gates["failed"])
    return ("Branch `%s` — %d file(s), all inside harness/tests/docs. Gates %s%s. "
            "I haven't merged it; that's yours."
            % (branch, len(changed), gates["summary"], tail))


DELEGATE_TOOLS = [delegate_code]
