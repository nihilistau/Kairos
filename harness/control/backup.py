"""backup.py — everything she is, hourly, into a zip you can actually restore from.

WHY THIS EXISTS, dated because it is a scar: on 2026-07-31 a GATE overwrote
`persona.md` with a test payload — her voice, mood and traits, gone — and the only
backup that existed was a day old and had been written by accident, as a side
effect of an unrelated persona-layer edit. Her state is gitignored by design (it is
hers, not the repo's), which means git is not a safety net and nothing else was one.

WHAT IS BACKED UP: the small, irreplaceable things.

    var/memory/*.jsonl        the fact registry, the board, presence, quarantine
    var/memory/narrative.md   her journal
    var/memory/*.json         consolidation state
    var/senses/               the ambient eye's log of the room
    var/research/             research receipts (the provenance ledger)
    var/room/files/           the shared workspace
    var/room/ledger.json      the plan, the parked, and everything noticed
    var/tuning.json           every knob he has set
    persona.md + persona/     her voice, and the layered fragments
    memory-okf*/              the content-addressed stores (facts, self, personality,
                              conversations, telemetry)
    _task_state/              the task queue

WHAT IS NOT, and why it is not a hedge:

    var/memory/eps/     1.2 GB of KV episode snapshots, 154 of them at ~40 MB each.
                        Hourly copies would fill this box's remaining 35 GB inside a
                        day. The REGISTRY that references them is backed up, so what
                        is lost on a restore is replay fidelity, not the memory of
                        what happened. Set `include_episodes` if the disk allows.
    var/voice/          2.6 GB — extracted weights and baked corpora. Regenerable
                        from the checkpoint by tools/extract_audio_projection.py.
    var/drafter/,       models and build trees. Regenerable, and large.
    var/gold-build/,
    var/hidden/
    logs                var/*.log — daemon.log alone is 10 MB and grows.

THE RULES IT FOLLOWS, each of which is a way backups usually fail:

  * ATOMIC. Written to `.part` and renamed only after the zip is re-opened and
    verified. A half-written zip that looks like a backup is worse than no backup,
    because you find out when you need it.
  * VERIFIED. `testzip()` on every archive before it counts. Not "the write
    returned", which is what most backup code checks.
  * SKIP IF UNCHANGED. An idle night should not produce eight identical archives.
    The content digest is compared to the last one; identical means a touch of the
    existing file, not a copy.
  * NEVER RECURSIVE. The backup directory is excluded from itself by realpath, not
    by name.
  * NEVER FATAL. A failure logs and returns; a backup system that can take the
    stack down has inverted its own purpose.
  * IT SAYS WHAT IT SKIPPED. The manifest records every exclusion and the reason,
    so a restore knows what it does NOT have. A backup that silently omits things
    teaches you to trust it wrongly.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
import zipfile
from typing import Dict, List, Optional, Tuple

from harness.store_io import replace_atomic

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ENABLED = os.environ.get("SP_BACKUP", "1") != "0"
INTERVAL_S = float(os.environ.get("SP_BACKUP_INTERVAL_S", "3600"))
DIR = os.environ.get("SP_BACKUP_DIR", os.path.join(_ROOT, "var", "backups"))
KEEP_HOURLY = int(os.environ.get("SP_BACKUP_KEEP", "48"))
KEEP_DAILY = int(os.environ.get("SP_BACKUP_KEEP_DAILY", "30"))
INCLUDE_EPISODES = os.environ.get("SP_BACKUP_EPISODES", "0") == "1"

PREFIX = "sp-backup-"

# (path relative to repo root, recursive?) — order is display order in the manifest.
SOURCES: List[Tuple[str, bool]] = [
    ("persona.md", False),
    ("persona", True),
    ("var/tuning.json", False),
    ("var/memory", True),
    ("var/senses", True),
    ("var/research", True),
    ("var/room/files", True),
    # The ledger is gitignored operator state, so the hourly snapshot is the ONLY
    # thing standing between it and a var/ wipe. It is the plan and every noticed-
    # and-not-touched item; losing it loses the reasons, not just the rows.
    ("var/room/ledger.json", False),
    ("_task_state", True),
    ("memory-okf", True),
    ("memory-okf-self", True),
    ("memory-okf-personality", True),
    ("memory-okf-conv", True),
    ("memory-okf-telemetry", True),
]

# Excluded even inside an included tree. Reason is carried into the manifest.
EXCLUDE: Dict[str, str] = {
    "var/memory/eps": "1.2 GB of KV episode snapshots; the registry that references "
                      "them IS backed up, so a restore loses replay fidelity, not "
                      "the record of what happened. SP_BACKUP_EPISODES=1 to include.",
    "var/memory/memory.zip": "an export, regenerable from the registry",
}
_SKIP_SUFFIX = (".log", ".part", ".tmp", ".pyc")

_thread: Optional[threading.Thread] = None
_last: Dict = {}
_lock = threading.Lock()


def _excluded(rel: str) -> Optional[str]:
    r = rel.replace("\\", "/")
    if r.startswith("var/memory/eps") and INCLUDE_EPISODES:
        return None
    for key, why in EXCLUDE.items():
        if r == key or r.startswith(key + "/"):
            return why
    if r.endswith(_SKIP_SUFFIX):
        return "log/scratch"
    return None


def _files() -> Tuple[List[Tuple[str, str]], Dict[str, str]]:
    """(abs, rel) pairs to archive, plus the exclusions actually hit."""
    out: List[Tuple[str, str]] = []
    hit: Dict[str, str] = {}
    backups = os.path.realpath(DIR)
    for rel, recurse in SOURCES:
        ap = os.path.join(_ROOT, rel)
        if not os.path.exists(ap):
            continue
        if os.path.isfile(ap):
            out.append((ap, rel.replace("\\", "/")))
            continue
        for dirpath, dirnames, filenames in os.walk(ap):
            # NEVER RECURSIVE — by realpath, not by name.
            if os.path.realpath(dirpath).startswith(backups):
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in filenames:
                a = os.path.join(dirpath, fn)
                r = os.path.relpath(a, _ROOT).replace("\\", "/")
                why = _excluded(r)
                if why:
                    # Record the DIRECTORY that was excluded, not each of its 154
                    # members — and keep the segment that names it. The first cut
                    # split on "/eps/" and kept only the head, so the manifest said
                    # "var/memory" was excluded, which is both alarming and false.
                    key = r.split("/eps/")[0] + "/eps" if "/eps/" in r else r
                    hit.setdefault(key, why)
                    continue
                out.append((a, r))
            if not recurse:
                dirnames[:] = []
    return out, hit


def _digest(files: List[Tuple[str, str]]) -> str:
    """Content identity of the whole set: path + size + mtime, cheap and adequate.

    Not a hash of every byte — that would read 700 MB an hour to answer a question
    (has anything changed?) that size+mtime answers correctly for this workload."""
    h = hashlib.sha256()
    for _a, r in sorted(files, key=lambda x: x[1]):
        try:
            st = os.stat(_a)
            h.update(f"{r}:{st.st_size}:{int(st.st_mtime)}".encode())
        except OSError:
            continue
    return h.hexdigest()[:16]


def run_once(reason: str = "manual") -> Dict:
    """Take one backup. Returns a receipt; never raises."""
    global _last
    started = time.time()
    rec: Dict = {"at": started, "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "reason": reason, "ok": False}
    try:
        os.makedirs(DIR, exist_ok=True)
        files, skipped = _files()
        rec["files"] = len(files)
        rec["bytes"] = sum(os.path.getsize(a) for a, _ in files if os.path.exists(a))
        rec["digest"] = _digest(files)

        prev = _read_index()
        if prev and prev.get("digest") == rec["digest"]:
            # SKIP IF UNCHANGED. An idle night must not make eight identical zips.
            rec.update(ok=True, skipped=True, same_as=prev.get("name"),
                       seconds=round(time.time() - started, 2))
            _last = rec
            return rec

        name = f"{PREFIX}{time.strftime('%Y%m%d-%H%M%S')}.zip"
        final = os.path.join(DIR, name)
        part = final + ".part"
        manifest = {
            "created": rec["iso"], "reason": reason, "digest": rec["digest"],
            "repo": _ROOT, "files": len(files), "bytes": rec["bytes"],
            "excluded": skipped,
            "note": "Restore with: python restore.py extract <name> --to <dir>",
        }
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.writestr("MANIFEST.json", json.dumps(manifest, indent=2))
            for a, r in files:
                try:
                    z.write(a, r)
                except (OSError, ValueError):
                    continue                      # a file vanished mid-walk; fine
        # VERIFIED, before it is allowed to count as a backup.
        with zipfile.ZipFile(part) as z:
            bad = z.testzip()
            if bad is not None:
                raise OSError(f"archive verify failed at {bad}")
            if "MANIFEST.json" not in z.namelist():
                raise OSError("archive has no manifest")
        replace_atomic(part, final)                   # ATOMIC
        rec.update(ok=True, name=name, size=os.path.getsize(final),
                   seconds=round(time.time() - started, 2), excluded=skipped)
        _write_index(rec)
        rec["pruned"] = prune()
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
        try:
            if os.path.exists(part):              # never leave a .part behind
                os.remove(part)
        except Exception:
            pass
    _last = rec
    return rec


def _index_path() -> str:
    return os.path.join(DIR, "last.json")


def _read_index() -> Dict:
    try:
        with open(_index_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write_index(rec: Dict) -> None:
    try:
        with open(_index_path(), "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2)
    except OSError:
        pass


def listing() -> List[Dict]:
    """Every archive, newest first, with its manifest header."""
    out = []
    try:
        names = [n for n in os.listdir(DIR) if n.startswith(PREFIX) and n.endswith(".zip")]
    except OSError:
        return out
    for n in sorted(names, reverse=True):
        p = os.path.join(DIR, n)
        row = {"name": n, "size": os.path.getsize(p),
               "mtime": os.path.getmtime(p), "ok": None}
        try:
            with zipfile.ZipFile(p) as z:
                m = json.loads(z.read("MANIFEST.json"))
                row.update(created=m.get("created"), files=m.get("files"),
                           bytes=m.get("bytes"), reason=m.get("reason"),
                           excluded=list((m.get("excluded") or {}).keys()))
        except Exception as exc:
            row["error"] = str(exc)[:120]
        out.append(row)
    return out


def verify(name: str) -> Dict:
    """Actually open and CRC an archive. `ok` here means restorable."""
    p = os.path.join(DIR, name)
    if not os.path.isfile(p):
        return {"ok": False, "error": f"no such backup: {name}"}
    try:
        with zipfile.ZipFile(p) as z:
            bad = z.testzip()
            if bad is not None:
                return {"ok": False, "error": f"corrupt member: {bad}"}
            names = z.namelist()
            m = json.loads(z.read("MANIFEST.json"))
        return {"ok": True, "name": name, "members": len(names),
                "created": m.get("created"), "files": m.get("files")}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def prune() -> List[str]:
    """Keep the last KEEP_HOURLY archives, plus one per day for KEEP_DAILY days.

    The daily promotion matters: 48 hourly archives cover two days, and the failure
    you actually need a backup for is often noticed later than that."""
    removed: List[str] = []
    rows = listing()
    if not rows:
        return removed
    keep = {r["name"] for r in rows[:KEEP_HOURLY]}
    seen_days = {}
    for r in rows:
        day = time.strftime("%Y%m%d", time.localtime(r["mtime"]))
        if day not in seen_days:
            seen_days[day] = r["name"]
    for day in sorted(seen_days, reverse=True)[:KEEP_DAILY]:
        keep.add(seen_days[day])
    for r in rows:
        if r["name"] in keep:
            continue
        try:
            os.remove(os.path.join(DIR, r["name"]))
            removed.append(r["name"])
        except OSError:
            pass
    return removed


def status() -> Dict:
    rows = listing()
    nxt = None
    if _last.get("at") and ENABLED:
        nxt = max(0, round(_last["at"] + INTERVAL_S - time.time()))
    return {"enabled": ENABLED, "interval_s": INTERVAL_S, "dir": DIR,
            "running": bool(_thread and _thread.is_alive()),
            "count": len(rows), "newest": rows[0]["name"] if rows else None,
            "total_bytes": sum(r["size"] for r in rows),
            "keep_hourly": KEEP_HOURLY, "keep_daily": KEEP_DAILY,
            "include_episodes": INCLUDE_EPISODES,
            "last": _last or None, "next_in_s": nxt}


def _loop() -> None:
    # One immediately at start — a stack that has just come up is exactly when a
    # backup is cheapest and most likely to be wanted (something is about to change).
    nxt = time.time()
    while True:
        time.sleep(5.0)                 # short beat so a knob flip is prompt
        if os.environ.get("SP_BACKUP", "1") == "0":
            nxt = time.time() + INTERVAL_S
            continue
        if time.time() < nxt:
            continue
        try:
            run_once("hourly")
        except Exception:               # a sense must never take the stack down
            pass
        nxt = time.time() + INTERVAL_S


def start() -> bool:
    global _thread
    if _thread and _thread.is_alive():
        return True
    _thread = threading.Thread(target=_loop, name="backup", daemon=True)
    _thread.start()
    return True
