"""BUNDLES — export, import, reset and undo, for a companion home (design §3, 2026-11-26).

A bundle is a zip with the extension `.kairos`:

    manifest.json            {"kairos_bundle": 1, companion {id,name}, parts, units, files{arc: sha256}}
    files/<key>/...          one folder per store (harness/home.py KEYS), by part

PARTS (home.KEYS' column): personality (persona, the personality/self/caps tiers, knobs),
history (the registry's folder — speech, transcripts, notes, journal, graph, decisions — the
conversation tier, task queue, ledger, workspace), working (receipts, sense log, telemetry,
games), face (avatar and wardrobe), episodes (KV snapshots; large and engine-bound).

NOTHING IS EVER DELETED (non-negotiable 2). Every change to a home goes:
    1. a full bundle of what is there now      -> var/bundles/before-<op>-<id>-<ts>.kairos
    2. the touched stores MOVED aside          -> <home>/archive/<ts>/<key>/...
    3. the new contents put in place (blank, or from a bundle)
    4. one line in <home>/archive/ops.jsonl
and `undo()` is the reverse of the last op, made by the same moves (the current contents
go to archive/<ts>-undo/ first). A reset is a move, never an rm.

NEVER ON A LIVE HOME. Moving a registry out from under a gateway that has it open is
corruption, so replace / reset / undo refuse while `home.is_live()` — the gateway's own
pid marker. The room SCHEDULES them instead (`schedule()` -> <home>/pending.json) and
serve.py applies them at the next launch, before the gateway starts (`apply_pending`).
Export is allowed live: it only reads, and a line being appended mid-copy is the same risk
the hourly backup has always taken.

Gate: G-BUNDLE (harness_tests/g_bundle.py).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import zipfile
from typing import Dict, Iterable, List, Optional, Tuple

from harness import home as H
from harness.store_io import replace_atomic

FORMAT = 1
EXT = ".kairos"
MANIFEST = "manifest.json"
BUNDLE_DIR = os.path.join(H.VAR, "bundles")
PARTS = ("personality", "history", "working", "face", "episodes")
DEFAULT_EXPORT = ("personality", "history")
CHANGEABLE = ("personality", "history", "working", "face")   # episodes are never moved
# A store whose UNIT is its folder, not itself: everything beside the registry is history.
DIR_OF = {"registry", "ambient_log"}
SKIP_NAMES = {"eps", "__pycache__", "archive", "live.json", "pending.json"}
SKIP_SUFFIX = (".log", ".part", ".tmp", ".pyc", ".lock")


class BundleError(ValueError):
    """Refused, with the reason. Callers show it as written."""


# ── where things are ────────────────────────────────────────────────────────────────────
def bundle_dir() -> str:
    return os.environ.get("SP_BUNDLE_DIR") or BUNDLE_DIR


def paths_for(home: str) -> Dict[str, str]:
    """key -> path for `home`. When `home` is the process's own (SP_HOME), the env wins,
    exactly as every reader sees it; otherwise the home's companion.toml."""
    if H.current() and os.path.normcase(os.path.normpath(H.current())) == \
            os.path.normcase(os.path.normpath(home)):
        return {k: H.path(k) for k in H.KEYS}
    return H.resolve(home)


def units(paths: Dict[str, str], parts: Iterable[str]) -> List[Tuple[str, str, str, str]]:
    """[(key, part, kind, path)] for the selected parts; kind is 'dir' or 'file'. A unit
    inside another selected unit is dropped (the graph inside the registry's folder)."""
    sel = []
    for key, (_v, _l, _g, part) in H.KEYS.items():
        if part not in parts or not paths.get(key):
            continue
        p = paths[key]
        if key in DIR_OF:
            sel.append((key, part, "dir", os.path.dirname(p)))
        elif os.path.splitext(p)[1] and not os.path.isdir(p):
            sel.append((key, part, "file", p))
        else:
            sel.append((key, part, "dir", p))
    out = []
    for u in sel:
        nu = os.path.normcase(os.path.normpath(u[3]))
        if any(o is not u and o[2] == "dir" and nu.startswith(os.path.normcase(os.path.normpath(o[3])) + os.sep)
               for o in sel):
            continue
        if any(o[3] == u[3] and sel.index(o) < sel.index(u) for o in sel):
            continue
        out.append(u)
    return out


def _protected(paths: Dict[str, str], parts: Iterable[str]) -> List[str]:
    """Paths a move must never take: every store of a part NOT selected, and the episodes."""
    keep = [paths[k] for k, (_v, _l, _g, part) in H.KEYS.items()
            if part not in parts and paths.get(k)]
    from harness.skills.epdir import cold_root          # the one reader of SP_EPS_COLD_DIR
    keep += [cold_root()]
    return [os.path.normcase(os.path.normpath(p)) for p in keep if p]


def _skip(name: str) -> bool:
    return name in SKIP_NAMES or name.endswith(SKIP_SUFFIX)


def _walk(root: str) -> Iterable[Tuple[str, str]]:
    """(absolute, relative-with-/) for every file under root, skipping SKIP_NAMES."""
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not _skip(d)]
        for f in fn:
            if _skip(f):
                continue
            a = os.path.join(dp, f)
            yield a, os.path.relpath(a, root).replace("\\", "/")


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── export ───────────────────────────────────────────────────────────────────────────────
def export(home: str, parts: Iterable[str] = DEFAULT_EXPORT, *, out: str = "",
           label: str = "") -> dict:
    """Write a bundle of `parts` of `home`. Returns {path, name, files, bytes, parts}."""
    parts = tuple(p for p in PARTS if p in set(parts))
    if not parts:
        raise BundleError("choose at least one part to export")
    doc = H.read(home)
    comp = doc["companion"]
    paths = paths_for(home)
    sel = units(paths, parts)
    os.makedirs(bundle_dir(), exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    name = "%s%s-%s%s" % ((label + "-") if label else "", comp["id"], ts, EXT)
    out = out or os.path.join(bundle_dir(), name)
    part_file = out + ".part"
    files, nbytes, unit_meta = {}, 0, {}
    with zipfile.ZipFile(part_file, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for key, part, kind, p in sel:
            n = 0
            if kind == "file":
                if os.path.isfile(p):
                    arc = "files/%s/%s" % (key, os.path.basename(p))
                    z.write(p, arc)
                    files[arc] = _sha(p)
                    nbytes += os.path.getsize(p)
                    n = 1
            elif os.path.isdir(p):
                for a, rel in _walk(p):
                    arc = "files/%s/%s" % (key, rel)
                    try:
                        z.write(a, arc)
                    except (OSError, ValueError):
                        continue                         # vanished mid-walk
                    files[arc] = _sha(a)
                    nbytes += os.path.getsize(a)
                    n += 1
            unit_meta[key] = {"part": part, "kind": kind, "files": n,
                              "name": os.path.basename(p) if kind == "file" else ""}
        manifest = {"kairos_bundle": FORMAT, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "companion": {"id": comp["id"], "name": comp.get("name") or comp["id"]},
                    "parts": list(parts), "units": unit_meta, "files": files, "bytes": nbytes}
        z.writestr(MANIFEST, json.dumps(manifest, indent=1))
    with zipfile.ZipFile(part_file) as z:              # verified before it counts
        if z.testzip() is not None:
            raise BundleError("the bundle failed its own read-back")
    replace_atomic(part_file, out)
    return {"ok": True, "path": out, "name": os.path.basename(out), "files": len(files),
            "bytes": nbytes, "parts": list(parts)}


# ── inspect ──────────────────────────────────────────────────────────────────────────────
_SAFE_ARC = re.compile(r"^files/[a-z_]+/[^\\:]+$")


def inspect(path: str, *, verify: bool = True) -> dict:
    """The manifest, checked: format, every name safe (no .., no absolute, no drive), and —
    with verify — every file's sha256. Refuses rather than half-trusting."""
    if not os.path.isfile(path):
        raise BundleError(f"no bundle at {path}")
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise BundleError(f"{os.path.basename(path)} is not a bundle (not a zip)")
    with z:
        try:
            man = json.loads(z.read(MANIFEST))
        except KeyError:
            raise BundleError(f"{os.path.basename(path)} has no {MANIFEST} — not a Kairos bundle")
        if int(man.get("kairos_bundle", 0)) != FORMAT:
            raise BundleError(f"bundle format {man.get('kairos_bundle')!r}; this harness reads {FORMAT}")
        names = set(z.namelist()) - {MANIFEST}
        for n in names:
            if not _SAFE_ARC.match(n) or "/../" in "/" + n or n.split("/")[1] not in H.KEYS:
                raise BundleError(f"unsafe or unknown entry in bundle: {n!r}")
        if names != set(man.get("files", {})):
            raise BundleError("the bundle's files and its manifest disagree")
        bad = []
        if verify:
            for n in names:
                if hashlib.sha256(z.read(n)).hexdigest() != man["files"][n]:
                    bad.append(n)
        if bad:
            raise BundleError(f"{len(bad)} file(s) fail their checksum, e.g. {bad[0]}")
    man["name"] = os.path.basename(path)
    man["size"] = os.path.getsize(path)
    return man


def listing() -> List[dict]:
    """Bundles in the bundle folder, newest first, with their manifest heads."""
    out = []
    d = bundle_dir()
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d), reverse=True):
        if not f.endswith(EXT):
            continue
        p = os.path.join(d, f)
        row = {"name": f, "size": os.path.getsize(p), "mtime": os.path.getmtime(p)}
        try:
            m = inspect(p, verify=False)
            row.update(companion=m["companion"], parts=m["parts"], created=m["created"],
                       files=len(m["files"]))
        except BundleError as e:
            row["error"] = str(e)
        out.append(row)
    return out


def resolve_name(name: str) -> str:
    """A bundle NAME from the room -> its path inside the bundle folder. Never a path."""
    if not name or os.path.basename(name) != name or not name.endswith(EXT):
        raise BundleError("name a bundle in the bundle folder")
    return os.path.join(bundle_dir(), name)


# ── moving, never deleting ───────────────────────────────────────────────────────────────
def _move_children(src: str, dst: str, protect: List[str]) -> int:
    """Move what is inside `src` to `dst`, except protected paths (recursing around them)."""
    n = 0
    if not os.path.isdir(src):
        return 0
    for name in os.listdir(src):
        a = os.path.join(src, name)
        na = os.path.normcase(os.path.normpath(a))
        if name in ("eps",) or na in protect:
            continue
        if any(p.startswith(na + os.sep) for p in protect):
            n += _move_children(a, os.path.join(dst, name), protect)
            continue
        os.makedirs(dst, exist_ok=True)
        shutil.move(a, os.path.join(dst, name))
        n += 1
    return n


def _aside(paths: Dict[str, str], parts: Iterable[str], to: str) -> dict:
    """Move every unit of `parts` into `to`/<key>/. Returns {key: entries moved}."""
    protect = _protected(paths, parts)
    moved = {}
    for key, _part, kind, p in units(paths, parts):
        dst = os.path.join(to, key)
        if kind == "file":
            if os.path.isfile(p):
                os.makedirs(dst, exist_ok=True)
                shutil.move(p, os.path.join(dst, os.path.basename(p)))
                moved[key] = 1
        else:
            moved[key] = _move_children(p, dst, protect)
    return moved


def _put_back(paths: Dict[str, str], parts: Iterable[str], frm: str) -> dict:
    """Reverse of _aside: move archive/<ts>/<key>/... back into place."""
    restored = {}
    for key, _part, kind, p in units(paths, parts):
        src = os.path.join(frm, key)
        if not os.path.isdir(src):
            continue
        if kind == "file":
            for f in os.listdir(src):
                os.makedirs(os.path.dirname(p), exist_ok=True)
                shutil.move(os.path.join(src, f), p)
                restored[key] = 1
        else:
            os.makedirs(p, exist_ok=True)
            n = 0
            for f in os.listdir(src):
                target = os.path.join(p, f)
                if os.path.exists(target):
                    continue                 # a protected neighbour; never overwritten
                shutil.move(os.path.join(src, f), target)
                n += 1
            restored[key] = n
    return restored


def _journal(home: str, row: dict) -> None:
    d = os.path.join(home, "archive")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "ops.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def history(home: str) -> List[dict]:
    p = os.path.join(home, "archive", "ops.jsonl")
    if not os.path.isfile(p):
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def _guard(home: str) -> None:
    if H.is_live(home):
        raise BundleError("she is running on this home — stop her first, or schedule it "
                          "for the next start (the room does this for you)")


def _template() -> str:
    for d in (os.path.join(H.ROOT, "persona-template"),
              os.path.join(H.ROOT, "kairos-export", "persona-template")):
        if os.path.isdir(d):
            return d
    return ""


def _blank(paths: Dict[str, str], parts: Iterable[str]) -> None:
    """A fresh start for each part: the persona template, and an empty registry."""
    if "personality" in parts:
        t = _template()
        pd = paths.get("persona_dir")
        if t and pd:
            os.makedirs(pd, exist_ok=True)
            for f in sorted(os.listdir(t)):
                if f.endswith(".md") and not os.path.exists(os.path.join(pd, f)):
                    shutil.copy2(os.path.join(t, f), os.path.join(pd, f))
    if "history" in parts and paths.get("registry"):
        os.makedirs(os.path.dirname(paths["registry"]), exist_ok=True)
        open(paths["registry"], "a").close()


def _extract(path: str, man: dict, paths: Dict[str, str], parts: Iterable[str]) -> dict:
    """Place a bundle's units for `parts` at `paths`. Targets were moved aside first."""
    placed = {}
    targets = {k: (kind, p) for k, _pt, kind, p in units(paths, parts)}
    with zipfile.ZipFile(path) as z:
        for arc in man["files"]:
            key, rel = arc.split("/", 2)[1], arc.split("/", 2)[2]
            meta = man["units"].get(key, {})
            if meta.get("part") not in parts:
                continue
            if key not in targets:
                # nested in another unit at the destination (e.g. the graph inside the
                # registry folder): place it at its own resolved path
                kind, base = ("dir", paths[key]) if key not in DIR_OF else ("dir", os.path.dirname(paths[key]))
            else:
                kind, base = targets[key]
            dst = base if kind == "file" else os.path.join(base, *rel.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with z.open(arc) as src, open(dst, "wb") as out:
                shutil.copyfileobj(src, out)
            placed[key] = placed.get(key, 0) + 1
    return placed


# ── the four changes ─────────────────────────────────────────────────────────────────────
def _change(home: str, op: str, parts: Iterable[str], fill) -> dict:
    parts = tuple(p for p in CHANGEABLE if p in set(parts))
    if not parts:
        raise BundleError("choose personality, history, or both")
    _guard(home)
    cid = H.read(home)["companion"]["id"]
    # The bundle is a portable COPY of exactly what is about to move; the moved-aside
    # archive is the undo itself. (Not every part: her face alone is 200 MB.)
    before = export(home, parts, label="before-" + op)
    ts = time.strftime("%Y%m%d-%H%M%S")
    paths = paths_for(home)
    moved = _aside(paths, parts, os.path.join(home, "archive", ts))
    filled = fill(paths, parts)
    row = {"ts": ts, "op": op, "parts": list(parts), "moved": moved, "before": before["name"],
           "companion": cid}
    if isinstance(filled, dict) and filled.get("from"):
        row["from"] = filled["from"]
    _journal(home, row)
    return {"ok": True, **row}


def reset(home: str, parts: Iterable[str]) -> dict:
    """Personality, history, or both back to a blank slate — by moving, never deleting."""
    return _change(home, "reset", parts, lambda paths, parts: _blank(paths, parts))


def replace(home: str, bundle: str, parts: Iterable[str]) -> dict:
    """Put a bundle's `parts` in place of this home's (the old ones moved aside)."""
    man = inspect(bundle)
    missing = [p for p in parts if p not in man["parts"]]
    if missing:
        raise BundleError(f"the bundle has no {', '.join(missing)} to load")

    def fill(paths, parts):
        _extract(bundle, man, paths, parts)
        return {"from": man["name"]}
    return _change(home, "load", parts, fill)


def undo(home: str) -> dict:
    """Reverse the last reset/load that has not been undone."""
    _guard(home)
    rows = history(home)
    done = {r.get("undoes") for r in rows if r.get("op") == "undo"}
    last = next((r for r in reversed(rows) if r.get("op") in ("reset", "load")
                 and r["ts"] not in done), None)
    if not last:
        raise BundleError("nothing to undo")
    ts = time.strftime("%Y%m%d-%H%M%S")
    paths = paths_for(home)
    _aside(paths, last["parts"], os.path.join(home, "archive", ts + "-undo"))
    restored = _put_back(paths, last["parts"], os.path.join(home, "archive", last["ts"]))
    row = {"ts": ts, "op": "undo", "undoes": last["ts"], "parts": last["parts"], "restored": restored}
    _journal(home, row)
    return {"ok": True, **row}


def import_new(bundle: str, cid: str, name: str = "") -> dict:
    """A NEW companion from a bundle (always safe: nothing existing is touched). A bundle
    without a personality gets the persona template, so she has a voice."""
    man = inspect(bundle)
    name = name or man["companion"]["name"]
    home = H.create(cid, name)
    paths = H.resolve(home)
    _extract(bundle, man, paths, [p for p in man["parts"] if p != "episodes"])
    # What the bundle did not bring is SEEDED, the same way a new companion is made: no
    # personality -> the named template and her own voice; no face -> the default set.
    from harness import companion_create as CC
    seeds = [] if "personality" in man["parts"] else ["persona", "voice"]
    seeds += [] if "face" in man["parts"] else ["face"]
    CC.fill(home, name, seeds=seeds)
    _journal(home, {"ts": time.strftime("%Y%m%d-%H%M%S"), "op": "created", "from": man["name"],
                    "parts": man["parts"], "companion": cid})
    return {"ok": True, "home": home, "id": cid, "parts": man["parts"]}


# ── scheduled for the next start (the room) ──────────────────────────────────────────────
def schedule(home: str, op: str, parts: Iterable[str] = (), bundle: str = "") -> dict:
    """Record a reset/load/undo to run at the next launch, before the gateway starts."""
    if op not in ("reset", "load", "undo"):
        raise BundleError("op must be reset, load or undo")
    if op == "load":
        inspect(bundle)
    if op != "undo" and not [p for p in parts if p in CHANGEABLE]:
        raise BundleError("choose personality, history, or both")
    row = {"op": op, "parts": list(parts), "bundle": os.path.basename(bundle) if bundle else "",
           "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    p = os.path.join(home, "pending.json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(row, f)
    replace_atomic(tmp, p)
    return {"ok": True, "pending": row}


def pending(home: str) -> Optional[dict]:
    try:
        with open(os.path.join(home, "pending.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def cancel(home: str) -> dict:
    p = os.path.join(home, "pending.json")
    if os.path.exists(p):
        replace_atomic(p, os.path.join(home, "pending.cancelled-%s.json" % time.strftime("%Y%m%d-%H%M%S")))
    return {"ok": True}


def apply_pending(home: str) -> Optional[dict]:
    """serve.py, before the gateway starts. Returns the receipt, or None if nothing waits.
    A failure is reported and the request kept as pending.failed-<ts>.json — never retried
    blindly on every boot, never silently dropped."""
    row = pending(home)
    if not row:
        return None
    if H.is_live(home):
        # The old gateway has not exited yet. NOT a failure: the request stays pending and
        # the next start tries again — it must not be marked failed by a race.
        return {"ok": False, "kept": True, "op": row.get("op"),
                "error": "the previous gateway still holds this home; left pending"}
    p = os.path.join(home, "pending.json")
    try:
        if row["op"] == "reset":
            res = reset(home, row["parts"])
        elif row["op"] == "load":
            res = replace(home, resolve_name(row["bundle"]), row["parts"])
        else:
            res = undo(home)
        replace_atomic(p, os.path.join(home, "archive", "pending-done-%s.json" % res["ts"]))
        return res
    except (BundleError, OSError) as e:
        os.makedirs(os.path.join(home, "archive"), exist_ok=True)
        replace_atomic(p, os.path.join(home, "pending.failed-%s.json" % time.strftime("%Y%m%d-%H%M%S")))
        return {"ok": False, "error": str(e), "op": row.get("op")}
