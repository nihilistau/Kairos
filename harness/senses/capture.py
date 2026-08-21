"""capture.py — getting pixels in: webcam, screen, and files on disk.

NO HARD DEPENDENCIES. `pyproject.toml` declares `dependencies = []` and that stays
true: every backend here is tried, and its absence is reported rather than raised
at import. Order is best-available-first, and `backends()` says which way it went
so the operator is never guessing.

    screen  : PIL.ImageGrab  ->  PowerShell + System.Drawing
    webcam  : cv2.VideoCapture -> ffmpeg dshow
    file    : PIL -> cv2 -> ffmpeg

CAPTURE IS AN EXPLICIT ACT. Nothing in this module runs on a timer, on a tick, or
as part of a turn she did not ask for. A camera that MIGHT be on is a different
object in a house than a camera that turns on when asked, and the difference is
not technical. Every function here is called from a tool, by name, once.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Optional

import numpy as np

# Default webcam index. `AIRHUG 02` is the built-in on this box; DroidCam sits
# alongside it, so the index is a knob rather than a constant.
CAM_INDEX = int(os.environ.get("SP_CAM_INDEX", "0"))
CAM_WARMUP = int(os.environ.get("SP_CAM_WARMUP", "5"))   # frames to discard


class CaptureError(RuntimeError):
    pass


def _try(mod: str):
    try:
        return __import__(mod)
    except Exception:
        return None


def backends() -> dict:
    """Which backends are actually importable, for the status surface."""
    return {
        "pillow": _try("PIL") is not None,
        "cv2": _try("cv2") is not None,
        "ffmpeg": _which("ffmpeg") is not None,
    }


def _which(exe: str) -> Optional[str]:
    from shutil import which
    return which(exe)


# ── decode ──────────────────────────────────────────────────────────────────
def load_image(path: str) -> np.ndarray:
    """Any image file -> HxWx3 uint8 RGB."""
    if not os.path.isfile(path):
        raise CaptureError(f"no such image: {path}")
    PIL = _try("PIL")
    if PIL is not None:
        from PIL import Image
        with Image.open(path) as im:
            return np.asarray(im.convert("RGB"), dtype=np.uint8)
    cv2 = _try("cv2")
    if cv2 is not None:
        bgr = cv2.imread(path, cv2.IMREAD_COLOR)
        if bgr is None:
            raise CaptureError(f"could not decode {path}")
        return np.ascontiguousarray(bgr[:, :, ::-1])
    raise CaptureError("no image decoder available (install Pillow or opencv)")


# ── screen ──────────────────────────────────────────────────────────────────
def screenshot() -> np.ndarray:
    """The whole primary display -> HxWx3 uint8 RGB."""
    PIL = _try("PIL")
    if PIL is not None:
        try:
            from PIL import ImageGrab
            im = ImageGrab.grab()
            return np.asarray(im.convert("RGB"), dtype=np.uint8)
        except Exception:
            pass                                  # fall through to PowerShell
    tmp = os.path.join(tempfile.gettempdir(), "sp_shot.png")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
        "$bm=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
        "$g=[System.Drawing.Graphics]::FromImage($bm);"
        "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
        f"$bm.Save('{tmp}');$g.Dispose();$bm.Dispose()"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0 or not os.path.isfile(tmp):
        raise CaptureError(f"screenshot failed: {(r.stderr or '').strip()[:200]}")
    try:
        return load_image(tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


# ── webcam ──────────────────────────────────────────────────────────────────
def photo(index: int | None = None) -> np.ndarray:
    """One frame from the webcam -> HxWx3 uint8 RGB.

    The warm-up matters and is not superstition: most USB cameras hand back the
    first few frames black or wildly mis-exposed while auto-exposure settles, so
    grabbing frame 0 reliably produces a photo of nothing."""
    idx = CAM_INDEX if index is None else index
    cv2 = _try("cv2")
    if cv2 is not None:
        capdev = cv2.VideoCapture(idx, getattr(cv2, "CAP_DSHOW", 0))
        try:
            if not capdev.isOpened():
                raise CaptureError(f"camera {idx} would not open")
            frame = None
            for _ in range(max(1, CAM_WARMUP)):
                ok, f = capdev.read()
                if ok:
                    frame = f
            if frame is None:
                raise CaptureError(f"camera {idx} opened but returned no frame")
            return np.ascontiguousarray(frame[:, :, ::-1])
        finally:
            capdev.release()
    if _which("ffmpeg"):
        return _photo_ffmpeg(idx)
    raise CaptureError("no camera backend available (install opencv or ffmpeg)")


def _photo_ffmpeg(idx: int) -> np.ndarray:
    name = list_cameras()
    if not name:
        raise CaptureError("ffmpeg found no dshow video devices")
    dev = name[min(idx, len(name) - 1)]
    tmp = os.path.join(tempfile.gettempdir(), "sp_cam.png")
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "dshow",
         "-i", f"video={dev}", "-frames:v", "1", tmp],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not os.path.isfile(tmp):
        raise CaptureError(f"ffmpeg capture failed: {(r.stderr or '').strip()[:200]}")
    try:
        return load_image(tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def list_cameras() -> list[str]:
    """dshow video device names, best-effort. Empty list if ffmpeg is absent."""
    if not _which("ffmpeg"):
        return []
    r = subprocess.run(["ffmpeg", "-hide_banner", "-list_devices", "true",
                        "-f", "dshow", "-i", "dummy"],
                       capture_output=True, text=True, timeout=30)
    out, names, video = (r.stderr or ""), [], False
    for line in out.splitlines():
        if "DirectShow video devices" in line:
            video = True
            continue
        if "DirectShow audio devices" in line:
            video = False
            continue
        if video and '"' in line and "Alternative name" not in line:
            names.append(line.split('"')[1])
    return names


def status() -> dict:
    return {"backends": backends(), "cameras": list_cameras(),
            "cam_index": CAM_INDEX, "warmup_frames": CAM_WARMUP}
