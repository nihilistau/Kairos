"""THE COMPANION HOME — one folder per companion, one resolver for every store in it.

Before 2026-11-26 her state lived at about twenty paths: the registry from the profile, five
`memory-okf*` trees at the repo root, `persona.md` and `persona/` at ROOT (no profile key), and
`var/{senses,research,room,…}` built from a literal in serve.py and again, as a fallback, in
the module that reads it. Nothing could name "her" as a unit, so nothing could back her up,
export her, reset her, or start a second companion beside her. Worse, the external-engine
profile (`companion`) shared her persona.md and tuning.json, because neither had a key.

Now a companion is a folder, `companions/<id>/`, with a `companion.toml`:

    [companion]
    id = "kairos"
    name = "Kairos"          # SP_COMPANION_NAME — user.say() fills {companion} with it
    format = 1

    [paths]                   # OPTIONAL overrides, relative to this folder or absolute.
    registry = "../../var/memory/registry.jsonl"     # her adoption: today's paths, unmoved

Every key not overridden takes the clean layout below. `env_for(home)` turns a home into the
SP_* environment serve.py hands the gateway; `path(key)` is what a module calls for a default
when no env is set (gates, bare imports) — the SAME table, so a module and the door cannot
disagree about where a store lives (AGENTS.md §0).

MACHINE-WIDE state is not here and stays in var/: voice weights, secrets, the HA token and
allowlist, MCP pins, launch setups, logs, and the backups themselves.

The PART column is what a bundle export/import/reset (design §3) moves together:
    personality  who she is            history   what happened
    face         her avatar/wardrobe   episodes  KV snapshots (large, engine-bound)
    working      receipts and sense logs — history-adjacent, optional in a bundle

Gate: G-HOME (harness_tests/g_home.py).
"""
from __future__ import annotations

import os
import tomllib
from typing import Dict, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAR = os.path.join(ROOT, "var")
# Where companions are made and listed: companions/ beside the code, unless the profile's
# [paths] companions_dir (SP_COMPANIONS_DIR) puts them elsewhere — a second install, a test.
COMPANIONS_DIR = os.environ.get("SP_COMPANIONS_DIR") or os.path.join(ROOT, "companions")
MANIFEST = "companion.toml"
FORMAT = 1

# key -> (env var, clean layout under the home, legacy default under ROOT, part)
# A legacy default of "" means "beside the registry" — the module derives it, as it always did.
KEYS: Dict[str, Tuple[str, str, str, str]] = {
    "registry":        ("SP_RECALL_REGISTRY",      "memory/registry.jsonl", "var/memory/registry.jsonl", "history"),
    "sem_index":       ("SP_SEM_INDEX",            "memory/semindex.jsonl", "",                          "history"),
    "graph_dir":       ("SP_GRAPH_DIR",            "memory/graph",          "",                          "history"),
    "decisions":       ("SP_DECISIONS",            "memory/decisions.jsonl", "",                         "history"),
    "conv_okf":        ("SP_CONV_OKF_ROOT",        "okf/conv",              "memory-okf-conv",           "history"),
    "task_root":       ("SP_TASK_ROOT",            "tasks",                 "_task_state",               "history"),
    "eps_dir":         ("SP_EPS_DIR",              "eps",                   "",                          "episodes"),
    "persona_file":    ("SP_PERSONA_FILE",         "persona.md",            "persona.md",                "personality"),
    "persona_dir":     ("SP_PERSONA_DIR",          "persona",               "persona",                   "personality"),
    "personality_okf": ("SP_PERSONALITY_OKF_ROOT", "okf/personality",       "memory-okf-personality",    "personality"),
    "self_okf":        ("SP_SELF_MODEL_ROOT",      "okf/self",              "memory-okf-self",           "personality"),
    "caps_okf":        ("SP_CAPS_OKF_ROOT",        "okf/caps",              "memory-okf-caps",           "personality"),
    "tuning":          ("SP_TUNING_FILE",          "tuning.json",           "var/tuning.json",           "personality"),
    "avatar_dir":      ("SP_AVATAR_DIR",           "room/avatar",           "var/room/avatar",           "face"),
    "ledger":          ("SP_LEDGER_FILE",          "room/ledger.json",      "var/room/ledger.json",      "history"),
    "workspace":       ("HARNESS_WORKSPACE",       "room/files",            "var/room/files",            "history"),
    "games_dir":       ("SP_GAMES_DIR",            "room/games",            "var/room/games",            "working"),
    "scenes_dir":      ("SP_SCENES_DIR",           "room/scenes",           "var/room/scenes",           "working"),
    "scenarios_dir":   ("SP_SCENARIOS_DIR",        "room/scenarios",        "var/room/scenarios",        "working"),
    "telemetry_okf":   ("SP_TELEMETRY_OKF_ROOT",   "okf/telemetry",         "memory-okf-telemetry",      "working"),
    "telemetry_dir":   ("SP_TELEMETRY_DIR",        "telemetry",             "var/telemetry",             "working"),
    "ambient_log":     ("SP_AMBIENT_LOG",          "senses/ambient.jsonl",  "var/senses/ambient.jsonl",  "working"),
    "research":        ("SP_RESEARCH_RECEIPTS",    "research",              "var/research",              "working"),
    "consult":         ("SP_CONSULT_RECEIPTS",     "consult",               "var/consult",               "working"),
    # Found by the 2026-11-26 audit: literals under var/ that a second companion would have
    # read as hers — her held-back lines replayed by the next one, deep recall's index of
    # her transcripts, her place in each book.
    "undelivered":     ("SP_UNDELIVERED",          "room/undelivered.jsonl", "var/room/undelivered.jsonl", "history"),
    "aux_index":       ("SP_AUX_INDEX_DIR",        "aux/archive",           "var/aux/archive",           "working"),
    "bookmarks":       ("SP_LIBRARY_BOOKMARKS",    "library-bookmarks.json", "var/library/.bookmarks.json", "history"),
    # First-run hints' progress (harness/hints.py) — which cards are done or dismissed.
    "hints":           ("SP_HINTS_STATE",          "hints.json",            "var/hints.json",            "working"),
    # Who and what she knows, and which of them are users (harness/people.py). Beside the
    # registry: the people a fact is ABOUT travel with the facts.
    "people":          ("SP_PEOPLE",               "memory/people.jsonl",   "var/memory/people.jsonl",   "history"),
}
# Keys a home may set but the clean layout leaves empty (cold storage is a drive, not a layout).
OPTIONAL = {"eps_cold_dir": ("SP_EPS_COLD_DIR", "episodes")}
# Two env vars name the personality tier (curator/self-model vs narrative); one value feeds both.
MIRRORS = {"SP_PERSONALITY_TIER": "personality_okf"}

PARTS = ("personality", "history", "face", "episodes", "working")


class HomeError(ValueError):
    """A home that cannot be used as written. serve.py prints it and refuses to start."""


def home_dir(ref: str, base: str = "") -> str:
    """A companion id ('kairos') or a path to a home folder -> the absolute folder. A bare
    id resolves in `base` when given (serve.py passes the PROFILE's companions folder — the
    door must not take it from an inherited environment), else in COMPANIONS_DIR."""
    ref = (ref or "").strip()
    if not ref:
        raise HomeError("no companion named")
    if os.path.isabs(ref) or os.sep in ref or "/" in ref:
        d = ref if os.path.isabs(ref) else os.path.join(ROOT, ref)
    else:
        d = os.path.join(base or COMPANIONS_DIR, ref)
    return os.path.normpath(d)


def read(home: str) -> dict:
    """The parsed companion.toml of `home` (a folder). Refuses a folder without one."""
    p = os.path.join(home, MANIFEST)
    if not os.path.isfile(p):
        raise HomeError(f"{home} has no {MANIFEST} — not a companion home")
    with open(p, "rb") as f:
        doc = tomllib.load(f)
    comp = doc.get("companion") or {}
    if not comp.get("id"):
        raise HomeError(f"{p}: [companion] id is required")
    fmt = int(comp.get("format", FORMAT))
    if fmt > FORMAT:
        raise HomeError(f"{p}: format {fmt} is newer than this harness understands ({FORMAT})")
    unknown = set((doc.get("paths") or {})) - set(KEYS) - set(OPTIONAL)
    if unknown:
        # A misspelled key would silently take the layout default — a store quietly moved.
        raise HomeError(f"{p}: unknown [paths] keys {sorted(unknown)}")
    return doc


def resolve(home: str, doc: Optional[dict] = None) -> Dict[str, str]:
    """key -> absolute path for every store of this home (overrides first, then layout)."""
    doc = doc if doc is not None else read(home)
    over = doc.get("paths") or {}

    def _abs(rel: str) -> str:
        # An ABSOLUTE override passes AS WRITTEN: the daemon reads SP_EPS_DIR too, and a
        # forward-slash path must reach it byte-identical, not respelled with backslashes.
        return rel if os.path.isabs(rel) else os.path.normpath(os.path.join(home, rel))

    out = {key: _abs(over.get(key) or layout) for key, (_e, layout, _l, _p) in KEYS.items()}
    out.update({key: _abs(over[key]) for key in OPTIONAL if over.get(key)})
    return out


def backup_dir(home: str, doc: Optional[dict] = None) -> str:
    """Where this home's hourly backups go: [backup] dir in companion.toml, else
    var/backups/<id>. ONE FOLDER PER COMPANION — backup.py prunes by name prefix and keeps
    a last.json digest in its folder, so two companions sharing one would prune each
    other's archives and skip each other's runs as "unchanged"."""
    doc = doc if doc is not None else read(home)
    d = (doc.get("backup") or {}).get("dir") or ""
    if d:
        return os.path.normpath(d if os.path.isabs(d) else os.path.join(home, d))
    return os.path.join(VAR, "backups", str(doc["companion"]["id"]))


def backup_extra(home: str, doc: Optional[dict] = None) -> list:
    """[backup] extra = [...] — trees the hourly backup also takes that no KEYS store names
    (her legacy `memory-okf/`, untouched since July but hers). Relative to the home."""
    doc = doc if doc is not None else read(home)
    out = []
    for d in (doc.get("backup") or {}).get("extra") or []:
        out.append(os.path.normpath(d if os.path.isabs(d) else os.path.join(home, d)))
    return out


def env_for(home: str) -> Dict[str, str]:
    """The SP_* environment for a home: every store path, plus its identity."""
    doc = read(home)
    paths = resolve(home, doc)
    comp = doc["companion"]
    env = {"SP_HOME": os.path.normpath(home),
           "SP_COMPANION_ID": str(comp["id"]),
           "SP_COMPANION_NAME": str(comp.get("name") or comp["id"])}
    for key, p in paths.items():
        var = KEYS[key][0] if key in KEYS else OPTIONAL[key][0]
        env[var] = p
    for var, key in MIRRORS.items():
        env[var] = paths[key]
    env["SP_BACKUP_DIR"] = backup_dir(home, doc)
    return env


def path(key: str) -> str:
    """Where store `key` is for THIS process: its env var if set, else the legacy default
    under ROOT, else '' (= the module derives it beside the registry, as it always has).
    Read at call time, so a gate's sandbox env wins."""
    var, _layout, legacy, _part = KEYS[key]
    # The personality tier has two names. SP_PERSONALITY_TIER wins: the journal's readers and
    # writers (narrative, archive) always honoured it, and seven gates point it at their own
    # tier; only the curator read SP_PERSONALITY_OKF_ROOT, and no gate sets that one alone.
    if key == "personality_okf" and os.environ.get("SP_PERSONALITY_TIER"):
        return os.environ["SP_PERSONALITY_TIER"]
    v = os.environ.get(var, "")
    if v:
        return v
    return os.path.join(ROOT, legacy) if legacy else ""


# ── THE LIVE MARKER (2026-11-26) ────────────────────────────────────────────────────────
# The gateway writes <home>/live.json with its pid as it starts serving; bundle.py refuses
# to move a live home's stores out from under it. A marker whose pid is gone is stale and
# means "not live" — a crash must not lock a companion forever.
LIVE = "live.json"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        # NOT os.kill(pid, 0): on Windows any signal but CTRL_* TERMINATES the process.
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259          # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def claim_live(home: str = "") -> None:
    """The gateway, as it starts serving: mark this home live with our pid."""
    home = home or current()
    if not home or not os.path.isdir(home):
        return
    import json as _j
    with open(os.path.join(home, LIVE), "w", encoding="utf-8") as f:
        _j.dump({"pid": os.getpid(), "at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S")}, f)


def is_live(home: str) -> bool:
    """Is a gateway that is still running serving this home?"""
    import json as _j
    try:
        with open(os.path.join(home, LIVE), encoding="utf-8") as f:
            pid = int(_j.load(f).get("pid", 0))
    except (OSError, ValueError, TypeError):
        return False
    return _pid_alive(pid)       # a gateway asking about its own home IS live: its pid counts


def current() -> str:
    """The home this process runs on, or '' (legacy profile, no home)."""
    return os.environ.get("SP_HOME", "")


def list_homes() -> list:
    """Every companion under companions/: [{id, name, dir}], sorted by id. Unreadable
    folders are listed with an `error` instead of hidden — a home you cannot see is a home
    you cannot back up."""
    out = []
    if not os.path.isdir(COMPANIONS_DIR):
        return out
    for d in sorted(os.listdir(COMPANIONS_DIR)):
        full = os.path.join(COMPANIONS_DIR, d)
        if not os.path.isdir(full):
            continue
        try:
            comp = read(full)["companion"]
            out.append({"id": comp["id"], "name": comp.get("name") or comp["id"], "dir": full})
        except (HomeError, OSError, tomllib.TOMLDecodeError) as e:
            out.append({"id": d, "name": d, "dir": full, "error": str(e)})
    return out


def create(cid: str, name: str = "", *, persona_template: str = "") -> str:
    """Make a new, empty companion home with the clean layout. Refuses an existing one —
    creating never overwrites. Returns the folder."""
    import re
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", cid or ""):
        raise HomeError("companion id: lower-case letters, digits, - and _, up to 40")
    home = os.path.join(COMPANIONS_DIR, cid)
    if os.path.exists(home):
        raise HomeError(f"{home} already exists")
    os.makedirs(os.path.join(home, "memory"))
    os.makedirs(os.path.join(home, "persona"))
    name = (name or cid).replace('"', "'")
    with open(os.path.join(home, MANIFEST), "w", encoding="utf-8", newline="\n") as f:
        f.write(f'[companion]\nid = "{cid}"\nname = "{name}"\nformat = {FORMAT}\n'
                f'created = "{__import__("time").strftime("%Y-%m-%d")}"\n')
    if persona_template and os.path.isdir(persona_template):
        import shutil
        for fn in sorted(os.listdir(persona_template)):
            src = os.path.join(persona_template, fn)
            if os.path.isfile(src) and fn.endswith(".md"):
                shutil.copy2(src, os.path.join(home, "persona", fn))
    return home
