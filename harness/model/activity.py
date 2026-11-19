"""WHAT HE WAS DOING IN HIS OTHER APPS — the activity record, and its one reader.

WHY IT EXISTS (2026-11-08). Kairos is about to control other apps (Primer first, then
Clockwork, then a coding app). For her to say "you were reading about kookaburras ten
minutes ago" without scraping those apps, each app WRITES what he did to a small record
she can read. This module is that record's contract, its writer for Python callers and its
one reader. Apps in other languages write the same JSON lines directly. The contract is
below and in docs/MEMORY-AND-RECALL.md (Stores).

LAYOUT. `activity/<app>/<YYYY-MM-DD>.jsonl` beside the registry, the same "beside the
registry" resolution the transcripts use, so a gate's sandbox carries its own. One
directory per app means two apps never append to one file. `<app>` must match `APP_NAME`
(lowercase letters, digits, `_` and `-`, at most 32). A directory that does not is skipped,
never guessed at: the name becomes part of a node ID.

ONE ROW (one JSON object per line; the app writes, nobody rewrites):

    {"at": 1767344460000,          epoch MILLISECONDS, as the transcripts; optional
     "event": "open_page",         short verb, <= 40 chars; required
     "title": "Kookaburra",        what it was about, <= 200 chars; required
     "ref": "wiki:Kookaburra",     the app's own handle for it; optional
     "private": true}              optional; a private row is NEVER read, by anything

`private` is the off-the-record lever for an app: the app writes the row for its own
history, and this reader drops it before anything else sees it. Not a redaction: the row
does not exist as far as she is concerned. Rows are not otherwise trusted: `event` and
`title` are cut to their limits on read, and a row missing either is skipped.

WHAT THIS NEVER DOES. It never writes the registry or the transcripts, and nothing it reads
is a FACT. An event is a record of what he did in an app, not a claim he made. The memory
graph is its only consumer so far (`app_event` nodes, the `activity` rule), and the graph's
view (`graph/view.py`) is the only way an event's words reach her, under the same secret
rule as a turn.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import time
from typing import Optional

APP_NAME = re.compile(r"^[a-z0-9_-]{1,32}$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EVENT_MAX = 40
TITLE_MAX = 200


def _dir(registry: str = "") -> str:
    """`activity/` beside the registry, as `transcript._dir` resolves `transcripts/`."""
    reg = registry or os.environ.get("SP_RECALL_REGISTRY", "")
    return os.path.join(os.path.dirname(reg), "activity") if reg else ""


def record(app: str, event: str, title: str, *, ref: str = "", private: bool = False,
           at_ms: Optional[int] = None, registry: str = "") -> bool:
    """Append one event for `app`. False (never a raise) when there is no store or the app
    name is not a valid directory name. The day file is the LOCAL day, as the transcripts."""
    d = _dir(registry)
    if not d or not APP_NAME.match(app or "") or not (event or "").strip() or not (title or "").strip():
        return False
    at_ms = int(time.time() * 1000) if at_ms is None else int(at_ms)
    day = _dt.date.fromtimestamp(at_ms / 1000.0).isoformat()
    row = {"at": at_ms, "event": event.strip()[:EVENT_MAX], "title": title.strip()[:TITLE_MAX]}
    if ref:
        row["ref"] = str(ref)[:TITLE_MAX]
    if private:
        row["private"] = True
    try:
        os.makedirs(os.path.join(d, app), exist_ok=True)
        with open(os.path.join(d, app, day + ".jsonl"), "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def all_rows(registry: str = "") -> Optional[list]:
    """[(app, day, line_index, row)] for every readable, NON-private event, apps in name
    order, days oldest first, file order within a day.

    `line_index` counts every physical line (blank, malformed and private included) so the
    `a:<app>:<day>:<index>` ID never shifts when a bad or private line is skipped. Each kept
    row has `event` and `title` cut to their limits and `at` as given (ms) or absent.
    None (not []) when the directory exists and cannot be read; [] when there is none.
    """
    d = _dir(registry)
    if not d or not os.path.isdir(d):
        return []
    out = []
    try:
        apps = sorted(a for a in os.listdir(d) if APP_NAME.match(a) and os.path.isdir(os.path.join(d, a)))
    except OSError:
        return None
    for app in apps:
        try:
            names = sorted(n for n in os.listdir(os.path.join(d, app))
                           if n.endswith(".jsonl") and _DAY.match(n[:-len(".jsonl")]))
        except OSError:
            return None
        for n in names:
            day = n[:-len(".jsonl")]
            try:
                with open(os.path.join(d, app, n), encoding="utf-8", errors="replace") as f:
                    for idx, line in enumerate(f):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except ValueError:
                            continue
                        if not isinstance(row, dict) or row.get("private"):
                            continue
                        ev, ti = row.get("event"), row.get("title")
                        if not isinstance(ev, str) or not ev.strip() or not isinstance(ti, str) or not ti.strip():
                            continue
                        kept = {"event": ev.strip()[:EVENT_MAX], "title": ti.strip()[:TITLE_MAX]}
                        at = row.get("at")
                        if isinstance(at, (int, float)) and not isinstance(at, bool):
                            kept["at"] = at
                        if isinstance(row.get("ref"), str):
                            kept["ref"] = row["ref"][:TITLE_MAX]
                        out.append((app, day, idx, kept))
            except OSError:
                return None
    return out


def private_count(registry: str = "") -> int:
    """How many private rows were skipped, for the build summary: the lever is a number, not
    a silence. Counted by reading the raw lines; nothing else of a private row is looked at."""
    d = _dir(registry)
    n = 0
    if not d or not os.path.isdir(d):
        return 0
    try:
        for app in os.listdir(d):
            p = os.path.join(d, app)
            if not APP_NAME.match(app) or not os.path.isdir(p):
                continue
            for name in os.listdir(p):
                if not name.endswith(".jsonl") or not _DAY.match(name[:-len(".jsonl")]):
                    continue
                with open(os.path.join(p, name), encoding="utf-8", errors="replace") as f:
                    for line in f:
                        try:
                            row = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(row, dict) and row.get("private"):
                            n += 1
    except OSError:
        return n
    return n
