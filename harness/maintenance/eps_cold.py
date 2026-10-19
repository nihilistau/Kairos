"""eps_cold.py — the episode cold tier (D2): long-dead episodes leave the hot disk.

THE PROBLEM (2026-10-19; spec docs/superpowers/specs/2026-10-19-memory-direction-design.md
§6 D2). One KV episode directory per minted row, ~16 MB each, ~0.5 GB a day, on the disk
she runs from. Once a row has been tombstoned for a month, only the audit lane reads its
episode. lifecycle.EPS_COLD_RULE names the ones that may go.

WHAT THIS IS. The mover, and nothing else:
  * it READS rows through memory.all_rows(), the audit door, and never writes the registry;
  * it MOVES a directory hot -> cold. On one disk that is a rename. Across disks it is a
    copy to <cold>/.partial-<ep>, a verify, a rename to <cold>/<ep>, a record, and then the
    hot copy is retired through <hot>/.moved-<ep>;
  * it RECORDS each move as one append-only row of the move ledger (epdir.ledger_path()),
    which is how both resolvers learn where an episode went. The row names the episode by
    basename and the tiers by name; it never holds a path;
  * recover() finishes or undoes whatever a crash left, before every live pass.

FLOORS. A move is refused when the cold root does not exist (it is never created: on
Linux an unmounted disk leaves its mount point behind, and creating the root would write
through to the system disk). It is also refused when the move is larger than the cold
disk's free space, or would leave less than eps_cold_min_free_gb there. The hot disk warns
under eps_hot_warn_free_gb, at boot and every night. Units are 1e9 bytes, as the mint floor.

OFF unless [memory].eps_cold_dir is set; a DRY RUN unless eps_cold_armed is true
(docs/OFF-BY-DEFAULT.md §19). The arming is checked AT THE WRITE: run() refuses a live
pass, move_one() refuses and recover() touches nothing when the config is unarmed,
so no caller added later can move an episode by skipping run(). Held by anonymous mode
as the door `eps.move`.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from harness.skills import epdir as _epdir
from harness.skills import lifecycle as _lc
from harness.store_io import replace_atomic

_log = logging.getLogger(__name__)

GB = 1e9
PARTIAL, LEAVING = ".partial-", ".moved-"
_MOVE_LOCK = threading.Lock()

# The seams the gates patch, here at the owner (memory: "mutants patch the owner").
_disk_usage = shutil.disk_usage
_copytree = shutil.copytree
_rmtree = shutil.rmtree
# Every rename goes through store_io's retry (G-STORE-WRITES): on Windows a directory
# cannot be renamed while a reader (the daemon on a deep recall) holds a file inside it.
# Past the budget it raises, and the caller's OSError path is the truth.
_rename = replace_atomic

OFF_LINE = ("[eps-cold] OFF: no cold root ([memory].eps_cold_dir is empty), so nothing moves. "
            "To arm: set eps_cold_dir to an existing folder on a disk with room (a sibling of "
            "the hot root works on a one-disk machine), read a dry run "
            "(POST /v1/maintenance/eps_cold), then set eps_cold_armed = true. "
            "docs/OFF-BY-DEFAULT.md section 19.")
DRY_LINE = ("[eps-cold] DRY RUN ONLY: the cold root %s is set and eps_cold_armed is false; "
            "the nightly pass lists what would move and moves nothing.")
ARMED_LINE = "[eps-cold] ARMED: episodes lifecycle.EPS_COLD_RULE names move nightly to %s."


@dataclass(frozen=True)
class ColdConfig:
    hot: str
    cold: str
    after_days: float
    min_free_gb: float
    hot_warn_free_gb: float
    armed: bool


def _num(var: str, default: float) -> float:
    try:
        return float(os.environ.get(var, "") or default)
    except ValueError:
        return float(default)


def config() -> ColdConfig:
    from harness.skills import memory as _M
    return ColdConfig(hot=_M.eps_root(), cold=_epdir.cold_root(),
                      after_days=_num("SP_EPS_COLD_AFTER_DAYS", 30),
                      min_free_gb=_num("SP_EPS_COLD_MIN_FREE_GB", 20),
                      hot_warn_free_gb=_num("SP_EPS_HOT_WARN_FREE_GB", 30),
                      armed=os.environ.get("SP_EPS_COLD_ARMED", "0") == "1")


def _norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(p))


def _under(root: str, path: str) -> bool:
    """`path` is a direct child of `root`, compared the way this OS compares paths."""
    if not root or not path:
        return False
    return _norm(os.path.dirname(os.path.normpath(path))) == _norm(root)


def free_bytes(path: str) -> Optional[int]:
    """Free bytes on the disk holding the existing directory `path`; None if none answers."""
    if not path or not os.path.isdir(path):
        return None
    try:
        return int(_disk_usage(path).free)
    except OSError:
        return None


def _same_device(a: str, b: str) -> bool:
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except (OSError, ValueError):
        return False


def _tree(path: str) -> tuple:
    """(bytes, files) under `path`."""
    nbytes = nfiles = 0
    for dp, _dn, fns in os.walk(path):
        for fn in fns:
            nfiles += 1
            nbytes += os.path.getsize(os.path.join(dp, fn))
    return nbytes, nfiles


def _sha(path: str) -> str:
    """sha256 of one file, streamed (an episode is ~16 MB)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _files(root: str) -> set:
    """Every file under `root`, as a relative path with forward slashes."""
    out = set()
    for dp, _dn, fns in os.walk(root):
        for fn in fns:
            out.add(os.path.relpath(os.path.join(dp, fn), root).replace("\\", "/"))
    return out


def _differs(a: str, b: str, subset: bool = False) -> str:
    """"" when `a` holds the same files as `b` with the same sha256 each; otherwise the
    first difference, named. NEVER a byte or file-count total: two trees can agree on both
    and differ in every byte. `subset` allows `a` to lack files `b` has (a hot copy whose
    retirement was cut off half-way), never to hold one `b` lacks or a different one."""
    fa, fb = _files(a), _files(b)
    extra = (fa - fb) if subset else (fa ^ fb)
    if extra:
        return "the file sets differ at %s" % sorted(extra)[0]
    for rel in sorted(fa):
        if _sha(os.path.join(a, rel)) != _sha(os.path.join(b, rel)):
            return "%s differs" % rel
    return ""


# The episode name the registry gives a directory: `ep_<kind>_<digits>[_<n>]`, as the
# harness mint (memory.store.new_row_name) and the daemon (routes.rs) write them.
EP_SHAPE = re.compile(r"^ep_[a-z]+_[a-z]?\d+(?:_\d+)?$")
_FOREIGN_LOGGED: set = set()


def _hers(rows: Optional[list] = None) -> Dict[str, str]:
    """{ep_key(basename): row name} for every registry row whose `dir` basename has the
    episode shape, read through the audit door. Recovery records nothing outside this."""
    if rows is None:
        from harness.skills import memory as _M
        rows = _M.all_rows()
    out: Dict[str, str] = {}
    for r in rows:
        base = os.path.basename((r.get("dir") or "").replace("\\", "/").rstrip("/"))
        if base and EP_SHAPE.match(base):
            out.setdefault(_epdir.ep_key(base), r.get("name", ""))
    return out


def _size(n: float) -> str:
    return "%.2f GB" % (n / GB) if abs(n) >= 1e7 else "%d B" % n


def hot_free_warning(cfg: ColdConfig) -> str:
    free = free_bytes(cfg.hot)
    if free is None or free >= cfg.hot_warn_free_gb * GB:
        return ""
    return ("[eps-cold] WARNING: the hot episode disk (%s) has %s free, under "
            "eps_hot_warn_free_gb = %g." % (cfg.hot, _size(free), cfg.hot_warn_free_gb))


def _gb(n: Optional[int]) -> Optional[float]:
    return None if n is None else round(n / GB, 2)


def status(cfg: Optional[ColdConfig] = None) -> Dict[str, Any]:
    """The tier's state, read-only: what the boot line prints and GET /v1/maintenance/eps_cold
    answers. Touches nothing; the cold root is only asked about, never created."""
    cfg = cfg or config()
    cold_exists = bool(cfg.cold) and os.path.isdir(cfg.cold)
    return {"ok": True, "state": "off" if not cfg.cold else ("armed" if cfg.armed else "dry-run"),
            "hot": cfg.hot, "hot_free_gb": _gb(free_bytes(cfg.hot)),
            "cold": cfg.cold, "cold_exists": cold_exists,
            "cold_free_gb": _gb(free_bytes(cfg.cold)) if cold_exists else None,
            "after_days": cfg.after_days, "min_free_gb": cfg.min_free_gb,
            "hot_warn_free_gb": cfg.hot_warn_free_gb, "warning": hot_free_warning(cfg)}


def _facts(st: Dict[str, Any]) -> str:
    """The boot line's tail: ` | state=<off|dry-run|armed> hot=<root> hot_free=<n GB|unknown>`
    and, when a root is set, ` cold_root=<exists|missing ...> cold_free=<n GB|unknown>`."""
    def _f(gb: Optional[float]) -> str:
        return "unknown" if gb is None else "%.2f GB" % gb
    out = " | state=%s hot=%s hot_free=%s" % (st["state"], st["hot"] or "(none)", _f(st["hot_free_gb"]))
    if st["cold"]:
        out += " cold_root=%s cold_free=%s" % (
            "exists" if st["cold_exists"] else
            "missing (the operator creates it by hand; the mover never does)",
            _f(st["cold_free_gb"]))
    return out


def boot_report() -> str:
    """One line at gateway boot: off, dry run or armed; whether the cold root exists; free
    space on both disks. The hot-disk warning, when it fires, is a second line."""
    cfg = config()
    if not cfg.cold:
        line = OFF_LINE
    elif not cfg.armed:
        line = DRY_LINE % cfg.cold
    else:
        line = ARMED_LINE % cfg.cold
    st = status(cfg)
    line += _facts(st)
    _log.info(line)
    warn = st["warning"]
    if warn:
        _log.warning(warn)
    return line + ("\n" + warn if warn else "")


def _record(name: str, ep: str, nbytes: int, nfiles: int, how: str) -> None:
    """Append ONE ledger row, flushed to disk. The only writer of the move ledger.

    BASENAMES AND TIER NAMES ONLY, never a path: the ledger travels with the registry to
    other machines, and the cold root is configuration (epdir.py). `from`/`to` say which
    tier, so a reader learns where an episode went from the profile, not from this row."""
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "name": name,
           "ep": os.path.basename(os.path.normpath(ep)), "from": "hot", "to": "cold",
           "bytes": int(nbytes), "files": int(nfiles), "how": how}
    with open(_epdir.ledger_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def plan(cfg: ColdConfig, rows: Optional[list] = None, now: Optional[float] = None) -> Dict[str, Any]:
    """What the rule names, resolved to a directory under the hot root, with sizes."""
    if rows is None:
        from harness.skills import memory as _M
        rows = _M.all_rows()
    moved = _epdir.moved_names()
    out: Dict[str, Any] = {"candidates": [], "skipped": {}}
    seen = set()
    for r in _lc.cold_episode_rows(rows, cfg.after_days, now):
        path, how = _epdir.resolve(r.get("dir") or "", cold=cfg.cold, moved=moved)
        ep = os.path.basename(os.path.normpath(path)) if path else ""
        if how == _epdir.COLD:
            why = "already_cold"
        elif path is None:
            why = "missing"
        elif not _under(cfg.hot, path):
            why = "outside_hot_root"
        elif _epdir.ep_key(ep) in seen:
            why = "shared"
        else:
            why = ""
        if why:
            out["skipped"][why] = out["skipped"].get(why, 0) + 1
            continue
        seen.add(_epdir.ep_key(ep))
        nbytes, nfiles = _tree(path)
        out["candidates"].append({"name": r.get("name", ""), "ep": ep, "src": path,
                                  "bytes": nbytes, "files": nfiles})
    return out


def _refuse(res: dict, why: str) -> dict:
    _log.warning("[eps-cold] refused %s: %s", res["ep"], why)
    return {**res, "result": "refused", "why": why}


def _retire_hot_copy(src: str) -> bool:
    """Remove the hot copy of a recorded move, through <hot>/.moved-<ep> so a crash
    half-way leaves a name recover() knows, never a half-deleted episode at its own name."""
    leaving = os.path.join(os.path.dirname(src), LEAVING + os.path.basename(src))
    try:
        _rename(src, leaving)
        _rmtree(leaving)
        return True
    except OSError as exc:
        _log.warning("[eps-cold] %s: the hot copy could not be removed yet (%s); the cold copy "
                     "is recorded and the next pass retries", os.path.basename(src), exc)
        return False


def move_one(c: dict, cfg: ColdConfig, dry_run: bool, pending: int = 0) -> Dict[str, Any]:
    """Move one plan() candidate. `pending` is what this dry run already promised the cold disk."""
    ep, src = c["ep"], c["src"]
    res = {"ep": ep, "name": c.get("name", ""), "bytes": c["bytes"], "files": c["files"]}
    final, partial = os.path.join(cfg.cold, ep), os.path.join(cfg.cold, PARTIAL + ep)
    if os.path.isdir(final):
        return {**res, "result": "already_cold"}
    if not os.path.isdir(cfg.cold):
        return _refuse(res, "the cold root %s does not exist; create it on the disk it should use" % cfg.cold)
    free = free_bytes(cfg.cold)
    if free is None:
        return _refuse(res, "the cold root %s is not reachable (no disk answered)" % cfg.cold)
    same = _same_device(src, cfg.cold)
    need = 0 if same else c["bytes"]
    free -= pending
    if need > free:
        return _refuse(res, "%s to move, %s free on the cold disk" % (_size(need), _size(free)))
    if free - need < cfg.min_free_gb * GB:
        return _refuse(res, "moving %s would leave %s free on the cold disk, under "
                            "eps_cold_min_free_gb = %g" % (_size(need), _size(free - need), cfg.min_free_gb))
    if dry_run:
        return {**res, "result": "would_move", "same_disk": same}
    if not cfg.armed:
        return _refuse(res, "eps_cold_armed is false: only a dry run is allowed")
    from harness.control import anon as _anon
    if _anon.holds("eps.move"):
        return {**res, "result": "held"}
    try:
        if same:
            _rename(src, partial)
        else:
            _copytree(src, partial)
            diff = _differs(partial, src)
            if diff:
                _rmtree(partial, ignore_errors=True)
                return {**res, "result": "error",
                        "why": "the copy did not match its source (%s); the source is kept" % diff}
        _rename(partial, final)
        _record(res["name"], ep, c["bytes"], c["files"], "move")
    except OSError as exc:
        _log.warning("[eps-cold] %s: the move failed and is left for recover(): %s", ep, exc)
        return {**res, "result": "error", "why": str(exc)[:160]}
    if not same:
        _retire_hot_copy(src)
    return {**res, "result": "moved", "to": final.replace("\\", "/")}


def recover(cfg: ColdConfig, rows: Optional[list] = None) -> Dict[str, List[str]]:
    """Finish or undo what a crash left. Idempotent; runs before every live pass.

    Three rules hold every branch:
      * A HOT copy is removed only when the cold copy has the same files with the same
        sha256 each (_differs). Anything else is a `conflict`: both are kept, the first
        difference is logged, and the operator decides.
      * Only HER episodes are touched in the cold root: a name with the registry's episode
        shape that some row's `dir` names. Anything else there is `foreign`, logged once,
        never moved, removed or recorded.
      * One episode that cannot be handled right now (a Windows handle, a file that will
        not read) is `locked`: warned by name and skipped. The rest of the pass goes on."""
    out: Dict[str, List[str]] = {"rolled_back": [], "finished": [], "adopted": [],
                                 "restored": [], "conflicts": [], "foreign": [], "locked": []}
    if not cfg.armed or not cfg.cold or not os.path.isdir(cfg.cold):
        return out
    moved = set(_epdir.moved_names())
    hers = _hers(rows)

    def _key(n: str) -> str:
        return _epdir.ep_key(n)

    def _ledger(ep: str, dst: str, how: str) -> None:
        nb, nf = _tree(dst)
        _record(hers.get(_key(ep), ""), ep, nb, nf, how)
        moved.add(_key(ep))

    def _conflict(ep: str, diff: str) -> None:
        _log.warning("[eps-cold] recover: %s has a hot and a cold copy that differ (%s); both "
                     "are kept for the operator", ep, diff)
        out["conflicts"].append(ep)

    def _foreign(n: str) -> bool:
        if n.startswith(PARTIAL):
            n = n[len(PARTIAL):]
        if _key(n) in hers:
            return False
        if n not in _FOREIGN_LOGGED:
            _FOREIGN_LOGGED.add(n)
            _log.info("[eps-cold] recover: %s in the cold root is not one of her episodes; "
                      "it is left alone", n)
        out["foreign"].append(n)
        return True

    def _partial(n: str) -> None:                                # 1. partial copies
        ep = n[len(PARTIAL):]
        partial, hot, final = os.path.join(cfg.cold, n), os.path.join(cfg.hot, ep), os.path.join(cfg.cold, ep)
        if os.path.isdir(hot):
            _rmtree(partial)
            out["rolled_back"].append(ep)
        elif not os.path.exists(final):
            _rename(partial, final)
            _ledger(ep, final, "recovered")
            out["finished"].append(ep)
        else:
            _conflict(ep, "a partial copy beside a whole one")

    def _leaving(n: str) -> None:                                # 2. hot copies caught leaving
        ep = n[len(LEAVING):]
        leaving, final = os.path.join(cfg.hot, n), os.path.join(cfg.cold, ep)
        if os.path.isdir(final) and _key(ep) in moved:
            diff = _differs(leaving, final, subset=True)
            if diff:
                _conflict(ep, diff)
                return
            _rmtree(leaving)
            out["finished"].append(ep)
        else:
            _rename(leaving, os.path.join(cfg.hot, ep))
            out["restored"].append(ep)

    def _whole(n: str) -> None:                                  # 3. whole episodes
        final, hot = os.path.join(cfg.cold, n), os.path.join(cfg.hot, n)
        if os.path.isdir(hot):
            diff = _differs(hot, final)
            if diff:
                _conflict(n, diff)
                return
            if _key(n) not in moved:
                _ledger(n, final, "recovered")
            if _retire_hot_copy(hot):
                out["finished"].append(n)
        elif _key(n) not in moved:
            _ledger(n, final, "adopted")
            out["adopted"].append(n)

    def _each(step, n: str) -> None:
        try:
            step(n)
        except OSError as exc:
            _log.warning("[eps-cold] recover: %s cannot be handled yet (%s); skipped this pass", n, exc)
            out["locked"].append(n[len(PARTIAL):] if n.startswith(PARTIAL) else
                                 n[len(LEAVING):] if n.startswith(LEAVING) else n)

    for n in sorted(os.listdir(cfg.cold)):
        if n.startswith(PARTIAL) and not _foreign(n):
            _each(_partial, n)
    if os.path.isdir(cfg.hot):
        for n in sorted(os.listdir(cfg.hot)):
            if n.startswith(LEAVING):
                _each(_leaving, n)
    for n in sorted(os.listdir(cfg.cold)):
        if not n.startswith(PARTIAL) and os.path.isdir(os.path.join(cfg.cold, n)) and not _foreign(n):
            _each(_whole, n)
    for k, v in out.items():
        if v:
            _log.info("[eps-cold] recover: %s %d (%s)", k, len(v), ", ".join(v[:8]))
    return out


def run(dry_run: Optional[bool] = None, now: Optional[float] = None) -> Dict[str, Any]:
    """The nightly step and the maintenance route. dry_run None = the profile decides
    (armed -> live, else dry); a live pass is refused unless armed."""
    cfg = config()
    out: Dict[str, Any] = {"ok": True, "hot": cfg.hot, "cold": cfg.cold, "armed": cfg.armed, "warnings": []}
    warn = hot_free_warning(cfg)
    if warn:
        _log.warning(warn)
        out["warnings"].append(warn)
    if not cfg.cold:
        out.update(off=True, line=OFF_LINE)
        return out
    dry = (not cfg.armed) if dry_run is None else bool(dry_run)
    out["dry_run"] = dry
    if not dry and not cfg.armed:
        out.update(ok=False, refused="eps_cold_armed is false: only a dry run is allowed")
        return out
    if not _epdir.ledger_path():
        out.update(ok=False, refused="no registry is configured, so there is no move ledger")
        return out
    if not _MOVE_LOCK.acquire(blocking=False):
        out.update(ok=False, skipped="a cold-tier pass is already running")
        return out
    try:
        if not dry:
            from harness.control import anon as _anon
            if _anon.on():
                n = len(plan(cfg, now=now)["candidates"])
                _anon.holds("eps.move", n=n or 1)
                out.update(held=n)
                return out
            try:
                out["recovered"] = recover(cfg)
            except OSError as exc:
                # A crash's leftovers that cannot be finished or undone yet: move nothing
                # more until they can, so a second half-state never piles on the first.
                _log.warning("[eps-cold] recover could not finish, so nothing moves this pass: %s", exc)
                out.update(ok=False, refused="recovery could not finish: %s" % str(exc)[:160])
                return out
        p = plan(cfg, now=now)
        locked = {_epdir.ep_key(e) for e in (out.get("recovered") or {}).get("locked", [])}
        if locked:
            keep = [c for c in p["candidates"] if _epdir.ep_key(c["ep"]) not in locked]
            p["skipped"]["locked"] = len(p["candidates"]) - len(keep)
            p["candidates"] = keep
        out["skipped"], out["candidates"] = p["skipped"], len(p["candidates"])
        results: List[dict] = []
        pending = 0
        for c in p["candidates"]:
            r = move_one(c, cfg, dry, pending)
            results.append(r)
            if r["result"] == "would_move" and not r.get("same_disk"):
                pending += c["bytes"]
            if r["result"] == "refused":
                out["stopped"] = r["why"]
                break
        for k in ("moved", "would_move", "refused", "already_cold", "held", "error"):
            out[k] = [r for r in results if r["result"] == k]
        out["bytes"] = sum(r["bytes"] for r in results if r["result"] in ("moved", "would_move"))
        out["cold_free"] = _size(free_bytes(cfg.cold) or 0)
        _log.info("[eps-cold] %s: %d %s (%s), %d refused, %d errors, skipped %s",
                  "dry run" if dry else "pass", len(out["would_move"] if dry else out["moved"]),
                  "would move" if dry else "moved", _size(out["bytes"]), len(out["refused"]),
                  len(out["error"]), p["skipped"])
        return out
    finally:
        _MOVE_LOCK.release()
