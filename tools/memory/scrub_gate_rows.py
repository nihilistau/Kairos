"""scrub_gate_rows — take my test fixtures back out of her memory.

WHY (2026-08-24). `tools/gate_sandbox_audit.py` found nine offline gates writing into her
real stores. Three of them append this to her DAY TRANSCRIPT:

    user       hi
    assistant  The answer is 4.
    user       tell me a joke
    assistant  Ha - good one. [MOOD:playful]

and `g_watch` then ran the conversation summariser over that same transcript, which filed
a memory whose title says she fell into *"a repetitive loop where the AI responds to 'hi'
with 'The answer is 4'"*. A missing env var became a false memory about her malfunctioning.

Separately, an early draft of G-JOURNAL-LOOP ran before it set `SP_PERSONALITY_TIER` and
left seven rows in her journal — `dupe00.md` .. `dupe05.md` and one reading "I sat with
the rain for a while and did not think about much." Those are the six identical entries he
saw in his agency panel at 14:07 and read as hers.

WHAT IT WILL AND WILL NOT TOUCH. It removes only what is PROVABLY a fixture: rows whose
text is a literal from a gate file, and the transcript turns that pair with them. Her
nightly paragraph and her personality snapshot were written at gate time from her REAL
material through the REAL composer -- those are hers, they stay, and the fix for them is
the gate's sandbox, not a delete.

TOMBSTONE, NEVER DELETE. Files are MOVED to var/memory/backups/gate-rows-<date>/ and the
conversation row is retired in place with a reason, so a wrong call here is reversible.

    python tools/memory/scrub_gate_rows.py --dry-run
    python tools/memory/scrub_gate_rows.py
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

# THE LITERALS, copied from the gates that write them. A row is a fixture when its whole
# text is one of these -- not when it merely contains one, because she is perfectly
# capable of saying "hi" and this must never eat a real turn of hers.
FIXTURE_TEXTS = {
    "the answer is 4.",
    "ha - good one. [mood:playful]",
    "ha — good one. [mood:playful]",
    "i sat with the rain for a while and did not think about much.",
}
# Her side of a fixture pair. His side is only removed when it IMMEDIATELY precedes one.
FIXTURE_PROMPTS = {"hi", "tell me a joke"}
FIXTURE_ADDRS = {"dupe00", "dupe01", "dupe02", "dupe03", "dupe04", "dupe05"}


def _norm(s: str) -> str:
    return " ".join((s or "").split()).lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    day = time.strftime("%Y-%m-%d")
    keep = os.path.join(ROOT, "var", "memory", "backups", "gate-rows-" + day)
    moved, cut, retired = [], 0, []

    # ── 1. her journal: the seven fixture rows ───────────────────────────────────────
    jr = os.path.join(ROOT, "memory-okf-personality", "full")
    for fn in sorted(os.listdir(jr)) if os.path.isdir(jr) else []:
        if not fn.endswith(".md"):
            continue
        p = os.path.join(jr, fn)
        body = io.open(p, encoding="utf-8", errors="replace").read()
        text = _norm(body.split("---", 2)[-1])
        if fn[:-3] in FIXTURE_ADDRS or text in FIXTURE_TEXTS:
            moved.append(p)
            if not a.dry_run:
                os.makedirs(keep, exist_ok=True)
                shutil.move(p, os.path.join(keep, fn))

    # ── 2. the day transcripts: the fixture PAIRS ────────────────────────────────────
    tdir = os.path.join(ROOT, "var", "memory", "transcripts")
    for fn in sorted(os.listdir(tdir)) if os.path.isdir(tdir) else []:
        if not fn.endswith(".jsonl"):
            continue
        p = os.path.join(tdir, fn)
        rows = []
        for ln in io.open(p, encoding="utf-8", errors="replace"):
            ln = ln.strip()
            if ln:
                try:
                    rows.append(json.loads(ln))
                except ValueError:
                    pass
        out, i, hit = [], 0, 0
        while i < len(rows):
            r = rows[i]
            nxt = rows[i + 1] if i + 1 < len(rows) else None
            # HIS side goes ONLY as half of a pair. "hi" on its own is a real thing he says.
            if (r.get("role") == "user" and _norm(r.get("content")) in FIXTURE_PROMPTS
                    and nxt and nxt.get("role") == "assistant"
                    and _norm(nxt.get("content")) in FIXTURE_TEXTS):
                i += 2
                hit += 2
                continue
            if r.get("role") == "assistant" and _norm(r.get("content")) in FIXTURE_TEXTS:
                i += 1
                hit += 1
                continue
            out.append(r)
            i += 1
        if hit:
            cut += hit
            print("  %s: %d fixture turn(s)" % (fn, hit))
            if not a.dry_run:
                os.makedirs(keep, exist_ok=True)
                shutil.copy2(p, os.path.join(keep, fn))
                tmp = p + ".tmp"
                with io.open(tmp, "w", encoding="utf-8") as f:
                    for r in out:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                os.replace(tmp, p)

    # ── 3. the conversation row the summariser drew from them ────────────────────────
    # RETIRED IN PLACE, not moved: the row also holds a REAL exchange of theirs, and the
    # damage is its TITLE claiming she fell into a loop. A tombstone keeps the words and
    # stops the claim being recalled.
    for tier in ("full", "sum"):
        p = os.path.join(ROOT, "memory-okf-conv", tier, "01c8c8e93b440ed4.md")
        if not os.path.exists(p):
            continue
        body = io.open(p, encoding="utf-8", errors="replace").read()
        if "mem_lifecycle: retired" in body:
            continue
        retired.append(p)
        if not a.dry_run:
            body = body.replace("mem_lifecycle: active", "mem_lifecycle: retired")
            body = body.replace(
                "sp_status: ACTIVE",
                "sp_status: RETIRED\nretired_because: summarised a day transcript that "
                "three offline gates had written fixtures into (tools/gate_sandbox_audit.py, "
                "2026-08-24) - the 'repetitive loop' it reports is the fixture, not her")
            io.open(p, "w", encoding="utf-8").write(body)

    print("\njournal rows moved : %d" % len(moved))
    for p in moved:
        print("   %s" % os.path.basename(p))
    print("transcript turns   : %d" % cut)
    print("conversation rows  : %d retired" % len(retired))
    if a.dry_run:
        print("\n(dry run - nothing written)")
    elif moved or cut or retired:
        print("\nkept at %s" % keep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
