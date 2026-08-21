"""BACKFILL SALIENCE — give the existing rows a place to be counted from.

Every row already on disk was said at least once (that is why it is there), so mentions=1
is not a guess, it is the truth. first_seen/last_seen come from `ts`, which every row has.

WHAT CANNOT BE RECOVERED, AND I AM NOT GOING TO PRETEND OTHERWISE: how many times he
ACTUALLY said each of these before today. Every one of those repetitions was discarded at
the door by the old dedupe guard — "already in memory" and nothing written down. The
counter starts now. In a week it will mean something; today it means "once, as far as we
can prove".

Inventing plausible counts from the log would be worse than starting at one. A memory
system that fabricates its own evidence is the exact failure this whole store spent a week
climbing out of.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REG = os.environ.get("SP_RECALL_REGISTRY") or os.path.join(ROOT, "var", "memory", "registry.jsonl")

sys.path.insert(0, ROOT)
from harness.skills import lifecycle as lc          # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv
    rows = []
    with open(REG, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))

    changed = 0
    for r in rows:
        if "mentions" in r and "last_seen" in r:
            continue
        ts = r.get("ts") or ""
        r.setdefault("mentions", 1)
        r.setdefault("first_seen", ts)
        r.setdefault("last_seen", ts)
        r.setdefault("recalled", 0)
        changed += 1

    live = [r for r in rows if not r.get("lifecycle")]
    live.sort(key=lambda r: -lc.salience(r))
    print(f"  {changed} row(s) backfilled · {len(live)} live\n")
    print("  MOST SALIENT RIGHT NOW (all at mentions=1, so this is recency x class):")
    for r in live[:8]:
        print("   %5.2f  %-9s x%-2d  %s" % (
            lc.salience(r), r.get("mem_class", "?"), r.get("mentions", 1),
            lc.strip_prefix(r.get("text", ""))[:56]))
    print()
    print("  LEAST SALIENT (old, one-off — these stop elbowing into answers, "
          "but are NOT deleted):")
    for r in live[-4:]:
        print("   %5.2f  %-9s x%-2d  %s" % (
            lc.salience(r), r.get("mem_class", "?"), r.get("mentions", 1),
            lc.strip_prefix(r.get("text", ""))[:56]))

    if not apply:
        print("\n  DRY RUN — re-run with --apply")
        return 0

    bak = f"{REG}.{int(time.time())}.bak"
    shutil.copy2(REG, bak)
    with open(REG, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n  APPLIED — backup {os.path.basename(bak)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
