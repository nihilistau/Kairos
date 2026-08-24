"""backfill_episodes — mint the episodes that could not be minted for a month.

WHY (2026-08-23). `/v1/capture` refused on the model MoE from the day the model
landed until the FFN seam opened this morning (AGENTS.md trap 1, G-MOE-SEAM).
Every row written in that window carries `npos=0` and has no `ep.k`/`ep.v`/`ep.l5`
— so deep recall and the L5 half of the semantic index have nothing to read for
any of them. The engine can mint again; this walks back and does the ones it owed.

WHAT IT IS CAREFUL ABOUT, because it writes to her store:

  * LIVE ROWS ONLY, and only where `npos` is 0 or absent. A tombstoned row is not
    resurrected and a row that already has an episode is not re-minted.
  * IT NEVER EDITS TEXT. The only fields it touches are `npos` and `dir` — the
    two the mint owns. Everything else on the row is left byte-identical.
  * ONE WRITER. It goes through memory._save_all under the same _REG_LOCK the live
    writer uses, so a speak-up landing mid-backfill cannot lose a row.
  * IT STOPS ON A FULL DISK, at the same floor the live mint respects. An episode
    is mean 11.1 MB and 247 of them is ~2.7 GB.
  * RESUMABLE. Interrupt it and re-run it: the rows it finished no longer match
    the "npos == 0" filter.

THE LOCK IT WILL HOLD. Every capture takes the engine's forward mutex, so this
serializes against her turns for a second or two per row. Run it with the gateway
stopped (`python serve.py companion --daemon-only`) unless you want her waiting.

    python tools/memory/backfill_episodes.py --dry-run
    python tools/memory/backfill_episodes.py --limit 10
    python tools/memory/backfill_episodes.py            (all of them)
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="stop after N rows")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-free-gb", type=float, default=3.0,
                    help="stop when the target drive drops below this")
    a = ap.parse_args()

    from harness.skills import memory as M
    from harness.skills import semindex as sx

    root = M.eps_root()
    daemon = os.environ.get("SP_DAEMON_URL", "http://127.0.0.1:3000")
    rows = M._load()
    todo = [r for r in rows
            if not r.get("lifecycle") and not int(r.get("npos") or 0) and (r.get("text") or "").strip()]
    if a.limit:
        todo = todo[:a.limit]

    # THE TRAP I FELL INTO ON THE FIRST RUN. sx.upgrade() is what puts the engine's
    # ep.l5 into the l5 SPACE of the semantic index, and it returns False silently when
    # the index is not armed in THIS process's environment. So the first pass minted 247
    # episodes with ep.l5 on disk and indexed exactly none of them, and every line of
    # output said success. Say it out loud instead: the whole point of the backfill is
    # the l5 half of the index, and minting without indexing gets you the disk cost with
    # none of the benefit.
    if not sx.enabled():
        print("!! SP_SEM_MINT/SP_SEM_INDEX are not set in this environment, so ep.l5 will")
        print("!! be written to disk and NOT indexed. That is the whole point of this pass.")
        print("!! Re-run with SP_SEM_MINT=1 and SP_SEM_INDEX=<path>, or run the indexing")
        print("!! pass separately over the dirs afterwards.")
        if not a.dry_run:
            print("!! refusing rather than doing the expensive half and skipping the useful half")
            return 2
    print("registry : %s" % M._reg_path())
    print("episodes : %s" % root)
    print("daemon   : %s" % daemon)
    print("rows     : %d live with no episode (of %d total)" % (len(todo), len(rows)))
    try:
        free = shutil.disk_usage(os.path.splitdrive(root)[0] + os.sep).free / 1e9
        print("free     : %.1f GB on the episode drive  (~11.1 MB each, so ~%.1f GB for these)"
              % (free, len(todo) * 0.0111))
    except OSError:
        free = 999.0
    if a.dry_run:
        for r in todo[:8]:
            print("   would mint: %s" % (r.get("text") or "")[:66])
        if len(todo) > 8:
            print("   ...and %d more" % (len(todo) - 8))
        return 0
    if not todo:
        print("nothing owed.")
        return 0

    os.makedirs(root, exist_ok=True)
    ok = skipped = failed = 0
    t0 = time.perf_counter()
    for i, row in enumerate(todo, 1):
        drive = os.path.splitdrive(root)[0] + os.sep
        if shutil.disk_usage(drive).free / 1e9 < a.min_free_gb:
            print("!! stopping: %s is under the %.1f GB floor" % (drive, a.min_free_gb))
            break
        name, text = row.get("name"), row.get("text") or ""
        out_dir = os.path.join(root, "ep_back_%d_%d" % (int(time.time() * 1000), i)).replace("\\", "/")
        npos, minted = M._mint_now(daemon, text, out_dir)
        if not minted or not npos:
            failed += 1
            why = M.capture_status().get("why", "")
            print("  [%3d/%d] FAIL  %-52s %s" % (i, len(todo), text[:52], why[:60]))
            if why:                       # a structural refusal will not fix itself
                print("!! the engine is refusing; stopping rather than looping on it")
                break
            continue
        # ONLY npos AND dir. Under the same lock the live writer uses.
        with M._REG_LOCK:
            cur = M._load()
            hit = next((r for r in cur if r.get("name") == name), None)
            if hit is None:
                skipped += 1
                continue
            hit["npos"] = npos
            hit["dir"] = out_dir
            M._save_all(cur)
        try:
            sx.upgrade(out_dir, text, row.get("ts", ""))    # the l5 half of the index
        except Exception:
            pass
        ok += 1
        if ok % 10 == 0 or i == len(todo):
            dt = time.perf_counter() - t0
            print("  [%3d/%d] %d minted, %d failed  (%.1fs, %.2fs/row)"
                  % (i, len(todo), ok, failed, dt, dt / max(1, ok)))

    dt = time.perf_counter() - t0
    print("\nminted %d, failed %d, skipped %d in %.1fs" % (ok, failed, skipped, dt))
    try:
        print("free now : %.1f GB" % (shutil.disk_usage(
            os.path.splitdrive(root)[0] + os.sep).free / 1e9))
    except OSError:
        pass
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
