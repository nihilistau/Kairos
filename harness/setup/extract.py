"""Safe ZIP extraction: validate every member first, enforce the size cap again while writing."""

from __future__ import annotations

import re
import stat
import zipfile
from pathlib import Path

import logging
from harness.loud import swallowed as _swallowed
_log = logging.getLogger(__name__)

MAX_MEMBERS = 20_000
MAX_RATIO = 4
CHUNK = 1024 * 1024
_DRIVE = re.compile(r"^[A-Za-z]:")
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.I)


class ExtractError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _declared_cap_for(archive_size: int) -> int:
    return MAX_RATIO * archive_size


def _cap_for(archive_size: int) -> int:
    return MAX_RATIO * archive_size


def _check_name(name: str) -> list[str]:
    norm = name.replace("\\", "/")
    if not norm or "\x00" in norm:
        raise ExtractError(f"unsafe name in archive: {name!r}")
    if norm.startswith("/") or _DRIVE.match(norm):
        raise ExtractError(f"unsafe absolute path in archive: {name!r}")
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    for p in parts:
        if p == ".." or ":" in p:
            raise ExtractError(f"unsafe path in archive: {name!r}")
        if _RESERVED.match(p) or p.endswith((".", " ")):
            raise ExtractError(f"unsafe name in archive (reserved on Windows): {name!r}")
    return parts


class ExtractCancelled(ExtractError):
    pass


def extract_zip(zip_path: Path, into: Path, *, skip_symlinks: bool = False, cancel=None) -> list[Path]:
    """Extract into `into` (which must be empty or absent). A symlink member refuses the whole
    archive, unless `skip_symlinks`: then it is left out (not written, not an error). `cancel`
    (an Event) is checked between members; set, it stops with ExtractCancelled and removes what
    was written."""
    zip_path, into = Path(zip_path), Path(into)
    try:
        archive_size = zip_path.stat().st_size
        zf = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ExtractError(f"cannot read the archive: {exc}") from None
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ExtractError(f"the archive has too many members ({len(infos)})")
        plan = []
        declared = 0
        for info in infos:
            parts = _check_name(info.filename)
            if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                if skip_symlinks:
                    continue
                raise ExtractError(f"the archive contains a symlink: {info.filename!r}")
            declared += info.file_size
            plan.append((info, parts))
        if declared > _declared_cap_for(archive_size):
            raise ExtractError("the archive expands too large (possible zip bomb)")
        root = into.resolve()
        targets = []
        for info, parts in plan:
            target = root.joinpath(*parts) if parts else root
            if target != root and root not in target.parents:
                raise ExtractError(f"unsafe path in archive: {info.filename!r}")
            targets.append(target)

        if into.exists() and (not into.is_dir() or any(into.iterdir())):
            raise ExtractError("the target folder is not empty")
        into.mkdir(parents=True, exist_ok=True)
        cap = _cap_for(archive_size)
        total = 0
        written: list[Path] = []
        created_dirs: list[Path] = []
        try:
            for (info, _), target in zip(plan, targets):
                if cancel is not None and cancel.is_set():
                    raise ExtractCancelled("the extraction was stopped")
                if info.is_dir():
                    if not target.exists():
                        target.mkdir(parents=True)
                        created_dirs.append(target)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                written.append(target)
                with zf.open(info) as src, open(target, "wb") as out:
                    while True:
                        chunk = src.read(CHUNK)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > cap:
                            raise ExtractError("the archive expands too large (possible zip bomb)")
                        out.write(chunk)
        except (ExtractError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
            for p in written:
                try:
                    p.unlink()
                except OSError as _swx:
                    _swallowed(_log, "extract_zip", _swx, lane="setup")
            for d in reversed(created_dirs):
                try:
                    d.rmdir()
                except OSError as _swx:
                    _swallowed(_log, "extract_zip", _swx, lane="setup")
            if isinstance(exc, ExtractError):
                raise
            raise ExtractError(f"extraction failed: {exc}") from None
        return written
