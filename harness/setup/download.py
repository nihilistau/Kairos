"""Resumable, verified downloads. The file appears at `dest` only after its hash matches."""

from __future__ import annotations

import errno
import hashlib
import http.client
import os
import re
import shutil
import threading
import time
import urllib.parse
from pathlib import Path

from harness.setup.net import CatalogueError, Net
from harness.store_io import replace_atomic
import logging
from harness.loud import swallowed as _swallowed
_log = logging.getLogger(__name__)

CHUNK = 1024 * 1024
MARGIN = 64 * 1024 * 1024
PROGRESS_INTERVAL = 0.25
REFUSED_EXT = (".ckpt", ".pt", ".pth", ".bin", ".pkl")
_WIN_DISK_FULL = 112


class DownloadError(CatalogueError):
    """A download that cannot proceed or finish; `reason` is a short sentence."""


class DownloadCancelled(DownloadError):
    pass


class DownloadGone(DownloadError):
    """The server says the file is not there (404/410): trying again won't bring it back."""


def _write(fh, chunk: bytes) -> None:
    fh.write(chunk)


def _is_disk_full(exc: OSError) -> bool:
    return exc.errno == errno.ENOSPC or getattr(exc, "winerror", None) == _WIN_DISK_FULL


def _disk_full(part: Path) -> DownloadError:
    return DownloadError(f"the disk is full; free some space and try again (the partial file {part.name} is kept)")


def _close(stream) -> None:
    try:
        stream.close()
    except Exception as _swx:
        _swallowed(_log, "_close", _swx, lane="setup")


def download(
    url: str,
    dest: Path,
    *,
    size: int | None = None,
    sha256: str | None = None,
    md5: str | None = None,
    progress=None,
    cancel: threading.Event | None = None,
    transport=None,
    resolve=None,
    token: str | None = None,
    allowed_ext: tuple[str, ...] | None = None,
    allow_unhashed: bool = False,
) -> Path:
    """Fetch `url` to `dest` via `dest.name + '.part'`, verify, then rename.

    `transport(url, headers) -> (status, headers, stream)` is injectable for tests. Policy
    refusals (bad redirect, private address) surface as DownloadError with the reason.
    """
    dest = Path(dest)
    ext = dest.suffix.lower()
    if ext in REFUSED_EXT:
        raise DownloadError(f"{ext} files are not downloaded (they can run code)")
    if allowed_ext is not None and ext not in tuple(e.lower() for e in allowed_ext):
        raise DownloadError(f"{ext or 'this kind of'} file is not expected here")
    if sha256:
        algo, want = "sha256", sha256.lower()
    elif md5:
        algo, want = "md5", md5.lower()
    elif allow_unhashed:
        algo, want = None, None
    else:
        raise DownloadError("there is no published hash to check this file against")

    part = dest.with_name(dest.name + ".part")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        have = part.stat().st_size if part.exists() else 0
        if size is not None and have > size:
            part.unlink()
            have = 0
    except OSError as exc:
        raise DownloadError(f"cannot prepare {dest.parent}: {exc}") from None
    net = Net(stream_transport=transport, resolve=resolve)
    restarted = False
    while True:
        _check_space(dest.parent, size, have)
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            resp = net.open_stream(url, token=token, headers=headers)
        except DownloadError:
            raise
        except CatalogueError as exc:
            raise DownloadError(exc.reason) from None
        stream = resp.stream
        try:
            mode = "wb"
            restart = False
            if resp.status == 416 and have:
                if size is None or have == size:
                    mode = None
                else:
                    restart = True
            elif resp.status == 206 and have:
                start, total = _parse_content_range(resp.headers.get("content-range", ""))
                if total is not None and size is not None and total != size:
                    _drop(part)
                    raise DownloadError("the server's file is a different size than the catalogue says")
                if start != have:
                    restart = True
                else:
                    mode = "ab"
            elif resp.status in (200, 206):
                pass
            elif resp.status in (401, 403):
                host = (urllib.parse.urlsplit(resp.url).hostname or "the server")
                raise DownloadError(f"{host} refused the download (a token or an accepted licence may be needed)")
            elif resp.status in (404, 410):
                raise DownloadGone("the file was not found on the server")
            else:
                raise DownloadError(f"the server answered {resp.status}")
            if restart:
                if restarted:
                    raise DownloadError("the server would not resume the download; try again")
                restarted = True
                _drop(part)
                have = 0
                continue
            if mode == "wb":
                have = 0
            hasher = hashlib.new(algo) if algo else None
            if mode != "wb" and hasher:
                _rehash(part, hasher)
            done = have
            if mode is not None:
                done = _copy(stream, part, mode, hasher, have, size, progress, cancel)
            if size is not None and done < size:
                raise DownloadError("the connection closed early; try again to resume")
            _verify(part, done, size, hasher, want, algo)
            if progress:
                progress(done, size if size is not None else done)
            try:
                replace_atomic(str(part), str(dest))
            except OSError as exc:
                raise DownloadError(f"cannot move the file into place: {exc}") from None
            return dest
        finally:
            _close(stream)


def _drop(part: Path) -> None:
    try:
        part.unlink()
    except OSError as _swx:
        _swallowed(_log, "_drop", _swx, lane="setup")


def _check_space(folder: Path, size, have: int) -> None:
    if size is None:
        return
    try:
        free = shutil.disk_usage(folder).free
    except OSError:
        return
    need = size - have
    if free < need + MARGIN:
        short = (need + MARGIN - free) // (1024 * 1024) + 1
        raise DownloadError(f"the disk is full: about {short} MB more space is needed")


def _parse_content_range(value: str):
    """(start, total_or_None) from 'bytes a-b/total'; start is None when unparseable."""
    m = re.match(r"^\s*bytes\s+(\d+)-(\d+)/(\d+|\*)\s*$", value or "")
    if not m:
        return None, None
    return int(m.group(1)), (None if m.group(3) == "*" else int(m.group(3)))


def _rehash(part: Path, hasher) -> None:
    try:
        with open(part, "rb") as fh:
            while True:
                b = fh.read(CHUNK)
                if not b:
                    break
                hasher.update(b)
    except OSError as exc:
        raise DownloadError(f"cannot read {part.name}: {exc}") from None


def _copy(stream, part, mode, hasher, have, size, progress, cancel) -> int:
    done = have
    last = 0.0
    try:
        fh = open(part, mode)
    except OSError as exc:
        if _is_disk_full(exc):
            raise _disk_full(part) from None
        raise DownloadError(f"cannot write {part.name}: {exc}") from None
    with fh:
        while True:
            if cancel is not None and cancel.is_set():
                raise DownloadCancelled("the download was cancelled; it can be resumed later")
            try:
                chunk = stream.read(CHUNK)
            except TimeoutError:
                raise DownloadError("the download stalled; try again to resume") from None
            except (OSError, http.client.HTTPException) as exc:
                raise DownloadError(f"the connection dropped ({exc}); try again to resume") from None
            if not chunk:
                break
            try:
                _write(fh, chunk)
            except OSError as exc:
                if _is_disk_full(exc):
                    raise _disk_full(part) from None
                raise DownloadError(f"cannot write {part.name}: {exc}") from None
            if hasher:
                hasher.update(chunk)
            done += len(chunk)
            now = time.monotonic()
            if progress and now - last >= PROGRESS_INTERVAL:
                last = now
                progress(done, size)
    return done


def _verify(part: Path, done: int, size, hasher, want, algo) -> None:
    problem = None
    if size is not None and done != size:
        problem = f"the file is {done} bytes but {size} were expected"
    elif hasher is not None and hasher.hexdigest() != want:
        problem = f"the {algo.upper()} hash does not match the published hash"
    if problem:
        try:
            part.unlink()
        except OSError as _swx:
            _swallowed(_log, "_verify", _swx, lane="setup")
        raise DownloadError(f"{problem}; the download was discarded")
