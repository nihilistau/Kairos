"""mark_synthetic_rows — stamp `synthetic` on day-transcript rows that a probe produced.

WHY THIS IS A TOOL (2026-09-02). It is the third distinct shape of "take my test material
back out of her stores", and the other two already have one:

  * `quarantine_rows.py`   — registry rows. Tombstone in place, `lifecycle=1`.
  * `scrub_gate_rows.py`   — known gate FIXTURE literals in the transcript / journal / conv
                             store. Matches hardcoded strings.
  * this                   — a row in her DAY TRANSCRIPT that is genuinely her voice but was
                             produced by a driven turn, so it must not be read back as their
                             conversation. There is no literal to match: the text is real
                             prose the model wrote.

The operation is exactly what the `synthetic` flag would have done had it reached the path in
time. It does NOT delete: `_read_day_transcript` already excludes flagged rows from the 04:00
pass and the room's restore, and `include_synthetic=True` reads them back. So stamping the
field is the whole fix, and it is reversible.

ROWS ARE NAMED BY `at`, NEVER BY TEXT. Her genuine unprompted turns sit in the same minutes
and read the same way — the row above the two this was written for is a real check-in
("I was just thinking about how much I love it when you say 'babe'"). A text match would have
been a coin flip; the millisecond stamp is exact.

    python tools/memory/mark_synthetic_rows.py --day 2026-09-02 --reason "..." \\
        --at 1788302245128 --at 1788302811973 --dry-run
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


def _transcript(day: str) -> str:
    from harness.skills import memory as M
    reg = M.registry_path() if hasattr(M, "registry_path") else os.environ.get(
        "SP_RECALL_REGISTRY", "")
    base = os.path.dirname(reg) if reg else os.path.join(ROOT, "var", "memory")
    return os.path.join(base, "transcripts", "%s.jsonl" % day)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True, help="YYYY-MM-DD (the transcript file)")
    ap.add_argument("--at", action="append", default=[], required=True,
                    help="the row's `at` stamp, exactly as it appears; repeatable")
    ap.add_argument("--reason", required=True, help="goes in the `synthetic` field")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    p = _transcript(a.day)
    if not os.path.exists(p):
        print("no transcript at %s" % p)
        return 2

    want = set(str(x) for x in a.at)
    rows, hit, already = [], [], []
    for line in io.open(p, encoding="utf-8", errors="replace"):
        if not line.strip():
            continue
        r = json.loads(line)
        if str(r.get("at")) in want:
            if r.get("synthetic"):
                already.append(r)
            else:
                print("  MARK  at=%-16s role=%-9s %r" % (
                    r.get("at"), r.get("role"),
                    str(r.get("text") or r.get("content"))[:74]))
                r["synthetic"] = a.reason
                hit.append(r)
        rows.append(r)

    for r in already:
        print("  (already marked) at=%s" % r.get("at"))
    missing = want - {str(r.get("at")) for r in rows}
    for m in sorted(missing):
        print("  !! NOT FOUND: %s" % m)

    print("\nmarked: %d   already: %d   not found: %d%s"
          % (len(hit), len(already), len(missing),
             "   (dry run — nothing written)" if a.dry_run else ""))
    if a.dry_run or not hit:
        return 0 if not missing else 1

    # A COPY FIRST. The file is her day; a wrong `--at` must be undoable.
    bak = os.path.join(os.path.dirname(p), "..", "backups",
                       "transcript-%s-%s.jsonl" % (a.day, time.strftime("%Y%m%d-%H%M%S")))
    bak = os.path.abspath(bak)
    os.makedirs(os.path.dirname(bak), exist_ok=True)
    shutil.copy2(p, bak)
    print("backup: %s" % bak)

    # ...and through the atomic writer the rest of this store uses, because her stack is
    # usually running while this is used.
    # `replace_atomic(tmp, dst)` takes TWO PATHS — the first draft of this passed the file
    # body as `dst` and got "replace: dst too long for Windows", which is the guard doing
    # its job: nothing was written and the transcript was untouched.
    from harness.store_io import replace_atomic
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    tmp = p + ".tmp.mark-%d" % os.getpid()
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(body)
    replace_atomic(tmp, p)
    print("wrote %d rows (%d newly marked)" % (len(rows), len(hit)))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
