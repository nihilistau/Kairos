"""REPAIR THE IDENTITY SLOT — undo the supersede that renamed the user.

WHAT HAPPENED (2026-07-12, caused by a gate run, found in the live registry):

    ep_tool_1783829466931   "My name is Kairos."   speaker=user  class=identity  LIVE
      supersedes:
        ep_live_m1783583016468   "The user said: my name is Sam"
        ep_live_m1783815036340   "My name is Sam"
        ep_tool_1783829324670    "The user's name is Sam"

G-RECALL-PRECISION asked her "what is your name?". She answered "My name is Kairos."
— correctly. Then that sentence went into memory through remember(), which is the USER
store, so it was stamped speaker=user. classify() read "name is" and called it identity.
find_superseded() then did exactly what it is built to do: an identity fact for the same
speaker with a different value RETIRES the old one. All three rows saying the user is
Sam were tombstoned.

The store now asserts that the user's name is Kairos. The gate still "passed" (she
answered 'Sam.') because recall found his name in other rows — the identity slot was
already wrong and the gate could not see it. That is a gate that measures the wrong thing.

This script repairs the DATA. The write-path guard that stops it recurring is separate —
data repair without the guard is just waiting for the next turn.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REG = os.environ.get("SP_RECALL_REGISTRY") or os.path.join(ROOT, "var", "memory", "registry.jsonl")

BAD = "ep_tool_1783829466931"          # "My name is Kairos." filed as the USER's identity
KEEP = "ep_tool_1783829324670"         # "The user's name is Sam" — the row that must be live


def main() -> int:
    apply = "--apply" in sys.argv
    rows = []
    with open(REG, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))

    by_name = {r.get("name", ""): r for r in rows}
    bad = by_name.get(BAD)
    if not bad:
        print(f"!! {BAD} not found — nothing to repair")
        return 1

    victims = [v for v in (bad.get("supersedes") or []) if v in by_name]
    print(f"BAD ROW   {BAD}")
    print(f"          {bad.get('text')!r}  speaker={bad.get('speaker')} "
          f"class={bad.get('mem_class')} lifecycle={bad.get('lifecycle')}")
    print(f"          it retired {len(victims)} row(s):")
    for v in victims:
        print(f"            - {v}  {by_name[v].get('text')!r}")
    print()

    changed = 0
    for r in rows:
        n = r.get("name", "")

        # 1. The bad row is TRUE — of HER. It is not deleted; it is re-filed into the
        #    self lane where it belongs, and stripped of the supersede it should never
        #    have been allowed to perform.
        if n == BAD:
            r["speaker"] = "self"           # it is HER name
            r["mem_class"] = "identity"
            r["supersedes"] = []            # it retires nothing — it was never about him
            r["src"] = "repair: refiled from user->self (2026-07-12)"
            changed += 1

        # 2. Every row it wrongly retired comes back.
        elif n in victims:
            r["lifecycle"] = 0
            r["superseded_by"] = ""
            r["src"] = (r.get("src") or "") + " | repair: un-retired (2026-07-12)"
            changed += 1

    # 3. The two OLDER Sam rows are genuine duplicates of the canonical one. Leave the
    #    canonical row live and re-retire the duplicates AGAINST IT — that is what
    #    supersede is for, and it keeps the identity slot single-valued.
    canon = by_name.get(KEEP)
    if canon:
        for r in rows:
            n = r.get("name", "")
            if n in victims and n != KEEP:
                r["lifecycle"] = 1
                r["superseded_by"] = KEEP
                r["src"] = "repair: duplicate of the canonical identity row (2026-07-12)"

    live_id = [r for r in rows
               if r.get("mem_class") == "identity" and not r.get("lifecycle")]
    print("AFTER REPAIR — live identity rows:")
    for r in live_id:
        print(f"  speaker={r.get('speaker'):<5} :: {r.get('text')}")
    print()

    if not apply:
        print(f"DRY RUN — {changed} row(s) would change. Re-run with --apply.")
        return 0

    bak = f"{REG}.{int(time.time())}.bak"
    shutil.copy2(REG, bak)
    with open(REG, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"APPLIED — {changed} row(s) changed. Backup: {os.path.basename(bak)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
