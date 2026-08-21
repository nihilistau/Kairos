"""music.py — the room's record player, and hers to reach for.

WHY THE STATE LIVES ON THE SERVER. The browser is what actually decodes audio, so
the naive design puts the player in the page — and then she cannot touch it, because
she has no browser. Instead the SERVER holds the intent (what is playing, paused,
what is queued) and the page follows it. That way "put something on" means the same
thing whether he clicked it or she called it, and if he has the room open on two
screens they agree.

The page still owns POSITION, because only it knows where the decoder actually is;
the server owns everything else. That split is the whole design.

── SHE MAY PUT MUSIC ON, UNDER THE SAME DISCIPLINE AS THE CAMERA ─────────────────

An AI that changes your music unprompted is annoying in exactly the way a camera
that watches unprompted is worse — same failure, lower stakes. So:

  * every control tool is cooldown-limited through harness/toolcore/cooldown.py
  * the persona says putting something on is an act, not a reflex
  * `now_playing` is FREE and uncooled, because knowing what is on is not an
    intervention and she should be able to talk about it as often as she likes

The asymmetry is deliberate: listening is free, changing is deliberate.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DIR = os.environ.get("SP_MUSIC_DIR") or os.path.join(
    os.path.expanduser("~"), "Music")
EXTS = (".mp3", ".m4a", ".ogg", ".opus", ".flac", ".wav", ".aac", ".webm")
MAX_TRACKS = int(os.environ.get("SP_MUSIC_MAX", "5000"))

_lock = threading.Lock()
_library: List[Dict] = []
_scanned_at: float = 0.0
_state: Dict = {"playing": False, "track": None, "queue": [],
                "position_s": 0.0, "changed_by": None, "changed_at": 0.0}


def _pretty(rel: str) -> Dict:
    """Artist/title out of the path, without a tag library.

    No mutagen, no eyed3 — `pyproject.toml` says `dependencies = []` and a metadata
    reader is not worth breaking that for. Folder and filename carry the answer
    almost always, and when they do not, the filename is still what he would
    recognise."""
    parts = rel.replace("\\", "/").split("/")
    stem = os.path.splitext(parts[-1])[0]
    # strip a leading track number: "03 - Title", "03. Title", "03 Title"
    t = stem
    for i, ch in enumerate(stem):
        if not (ch.isdigit() or ch in " .-_"):
            t = stem[i:]
            break
    artist = parts[-3] if len(parts) >= 3 else (parts[0] if len(parts) > 1 else "")
    album = parts[-2] if len(parts) >= 2 else ""
    if " - " in t:
        a, _, rest = t.partition(" - ")
        if not artist:
            artist = a
        t = rest or t
    return {"path": rel, "title": t.strip() or stem, "artist": artist, "album": album}


def scan(force: bool = False) -> List[Dict]:
    """The library. Cached — a cold walk of a big collection is seconds, and the
    room polls."""
    global _library, _scanned_at
    with _lock:
        if _library and not force and (time.time() - _scanned_at) < 300:
            return _library
        out: List[Dict] = []
        root = os.path.realpath(DIR)
        if os.path.isdir(root):
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for fn in sorted(filenames):
                    if not fn.lower().endswith(EXTS):
                        continue
                    ap = os.path.join(dirpath, fn)
                    rel = os.path.relpath(ap, root).replace("\\", "/")
                    try:
                        size = os.path.getsize(ap)
                    except OSError:
                        continue
                    row = _pretty(rel)
                    row["bytes"] = size
                    out.append(row)
                    if len(out) >= MAX_TRACKS:
                        break
                if len(out) >= MAX_TRACKS:
                    break
        _library, _scanned_at = out, time.time()
        return out


def resolve(rel: str) -> Optional[str]:
    """A library-relative path -> an absolute one, or None.

    REALPATH CONTAINMENT, the same discipline as the room's static handler and
    _persona_layer_write: `..%2f`, symlinks and Windows short names all survive a
    string check and none survive this. Refuse rather than sanitise."""
    root = os.path.realpath(DIR)
    ap = os.path.realpath(os.path.join(root, (rel or "").replace("\\", "/")))
    if not ap.startswith(root + os.sep):
        return None
    if not os.path.isfile(ap) or not ap.lower().endswith(EXTS):
        return None
    return ap


def state() -> Dict:
    with _lock:
        s = dict(_state)
    s["library_size"] = len(_library) if _library else len(scan())
    s["dir"] = DIR
    s["dir_exists"] = os.path.isdir(DIR)
    return s


def _find(q: str) -> Optional[Dict]:
    """Best match for a loose query — she will say 'put on something by X', not a path."""
    lib = scan()
    if not lib:
        return None
    ql = (q or "").strip().lower()
    if not ql:
        return None
    for t in lib:
        if t["path"].lower() == ql:
            return t
    scored = []
    for t in lib:
        hay = f"{t['title']} {t['artist']} {t['album']} {t['path']}".lower()
        if ql in hay:
            scored.append((len(hay), t))
    if scored:
        scored.sort(key=lambda x: x[0])
        return scored[0][1]
    return None


def set_state(**patch) -> Dict:
    with _lock:
        _state.update(patch)
        _state["changed_at"] = time.time()
    return state()


# ── tools ────────────────────────────────────────────────────────────────────
def now_playing() -> str:
    """What music is on right now."""
    s = state()
    if not s["dir_exists"]:
        return f"[no music library — {DIR} does not exist]"
    if not s.get("track"):
        return "Nothing is playing." + (
            f" There are {s['library_size']} tracks to choose from."
            if s["library_size"] else " The library is empty.")
    t = s["track"]
    who = s.get("changed_by") or "someone"
    return (f"{'Playing' if s['playing'] else 'Paused'}: "
            f"{t.get('title')}" + (f" — {t.get('artist')}" if t.get("artist") else "")
            + f" (put on by {who})")


def play_music(query: str = "") -> str:
    """Put music on. A title, artist or album — or nothing to resume."""
    s = state()
    if not s["dir_exists"]:
        return f"[no music library at {DIR}]"
    if not query:
        if not s.get("track"):
            lib = scan()
            if not lib:
                return "[the library is empty]"
            set_state(playing=True, track=lib[0], changed_by="her")
            return f"Started {lib[0]['title']}."
        set_state(playing=True, changed_by="her")
        return f"Resumed {s['track'].get('title')}."
    t = _find(query)
    if not t:
        return f"[nothing in the library matches {query!r}]"
    set_state(playing=True, track=t, position_s=0.0, changed_by="her")
    return f"Put on {t['title']}" + (f" by {t['artist']}" if t["artist"] else "") + "."


def pause_music() -> str:
    """Pause whatever is playing."""
    s = state()
    if not s.get("playing"):
        return "Nothing was playing."
    set_state(playing=False, changed_by="her")
    return f"Paused {s['track'].get('title') if s.get('track') else 'it'}."


def skip_track() -> str:
    """Skip to the next track."""
    lib = scan()
    if not lib:
        return "[the library is empty]"
    s = state()
    cur = (s.get("track") or {}).get("path")
    i = next((n for n, t in enumerate(lib) if t["path"] == cur), -1)
    nxt = lib[(i + 1) % len(lib)]
    set_state(playing=True, track=nxt, position_s=0.0, changed_by="her")
    return f"Skipped to {nxt['title']}."


def queue_track(query: str) -> str:
    """Add something to the queue without interrupting what is on."""
    t = _find(query)
    if not t:
        return f"[nothing in the library matches {query!r}]"
    with _lock:
        _state["queue"] = (_state.get("queue") or [])[:49] + [t]
        n = len(_state["queue"])
    return f"Queued {t['title']} ({n} waiting)."


def _specs():
    from harness.toolcore.tools import ToolSpec
    return [ToolSpec.from_callable(f) for f in
            (now_playing, play_music, pause_music, skip_track, queue_track)]


def music_tools():
    """Absent unless a library actually exists — a tool that always answers
    'no music' is worse than one that is not there, because she keeps reaching."""
    try:
        if os.environ.get("SP_MUSIC", "1") == "0" or not os.path.isdir(DIR):
            return []
        return _specs()
    except Exception:
        return []


MUSIC_TOOLS = music_tools()
