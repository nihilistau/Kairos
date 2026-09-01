"""quarantine_rows — retire named registry rows in place, with a reason, never deleting.

WHY THIS IS A TOOL AND NOT A ONE-OFF SCRIPT (2026-09-02). It is the third time fabricated
rows have had to come back out of her store:

  * 2026-08-24 — nine offline gates wrote into her real stores (`scrub_gate_rows.py`, which
    handles her journal, the day transcripts and the conv store, and is still the right tool
    for those).
  * 2026-08-30 — an overnight probe drove ~30 synthetic turns and `_capture_after_turn` minted
    twenty rows as things Sam SAID.
  * 2026-09-02 — `synthetic` governed the capture lane and NOT the model's own tool calls, so
    the live e2e gates' fixtures landed as facts, and she then spoke up about them twice and
    went looking for what "oak275009" meant.

Each time the cleanup was hand-written. This is the same operation every time, and it has one
rule that matters:

**TOMBSTONE, NEVER DELETE.** `lifecycle = 1` (which is what the engine reads),
`superseded_by = quarantine:<tag>`, `retired_because = <reason>`, `quarantined_at = <utc>`.
The words stay on disk and stop being recalled. `forget()` once did `open(p, "w")` minus a row
and that is the one thing this store's doctrine forbids.

THROUGH THE OWNING API, not by hand. It loads and saves via `harness.skills.memory.store`
under `registry_lock()`, so it cannot interleave with a live gateway write — the whole reason
`store_io.replace_atomic` exists is that her stack is usually running while this is used.

    python tools/memory/quarantine_rows.py --tag synthetic-tool-lane \\
        --reason "..." --name ep_tool_123 --name ep_tool_456
    python tools/memory/quarantine_rows.py ... --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", action="append", default=[],
                    help="row name (ep_tool_…); repeatable")
    ap.add_argument("--tag", required=True, help="quarantine tag, e.g. synthetic-tool-lane")
    ap.add_argument("--reason", required=True, help="why, in a sentence, for the audit lane")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.name:
        print("no --name given; nothing to do")
        return 2

    from harness.skills import memory as M

    want = set(a.name)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # ── UNDER THE LOCK, THROUGH THE STORE'S OWN READ AND WRITE ──────────────────────
    # Her gateway is normally up while this runs, and every mutation here is
    # load-all / change / rewrite-all — the exact interleaving `_REG_LOCK` exists for.
    with M.registry_lock():
        rows = M._load()
        hit, already, missing = [], [], set(want)
        for r in rows:
            nm = r.get("name")
            if nm not in want:
                continue
            missing.discard(nm)
            if r.get("lifecycle"):
                already.append(r)
                continue
            hit.append(r)
        for r in hit:
            print("  RETIRE %s  spk=%-4s ts=%s\n         %r"
                  % (r.get("name"), r.get("speaker"), (r.get("ts") or "")[:16],
                     (r.get("text") or "")[:110]))
            if a.dry_run:
                continue
            r["lifecycle"] = 1                       # what the engine reads
            r["superseded_by"] = "quarantine:" + a.tag
            r["superseded_at"] = stamp               # the audit lane reads these
            r["quarantined_at"] = stamp
            r["retired_because"] = a.reason
        if hit and not a.dry_run:
            M._save_all(rows)

    for r in already:
        print("  (already retired) %s" % r.get("name"))
    for nm in sorted(missing):
        print("  !! NOT FOUND: %s" % nm)
    print("\nretired: %d   already: %d   not found: %d%s"
          % (len(hit), len(already), len(missing),
             "   (dry run — nothing written)" if a.dry_run else ""))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
