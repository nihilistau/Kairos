"""REPAIR #2 — she overwrote his GENDER this time, and ate her own tool output.

Found live, hours after the NAME fix:

    ep_tool_1783880554158  "I am a woman"                     speaker=user class=identity LIVE
      -> superseded "I am male"                                (his, retired)
    ep_tool_1783880561704  "remember -> stored: I am a woman"  speaker=user src="user turn"

TWO BUGS, BOTH ALREADY "FIXED" ONCE:

1. THE FIREWALL WAS THE INSTANCE, NOT THE CLASS. It guarded her NAME, because her name is
   what had eaten his. Her GENDER walked straight through the same door, into the same
   lane, and supersede did exactly what it is built to do. The store then asserted that
   SAM IS A WOMAN.

2. SHE WAS EATING HER OWN EXHAUST. Capture took "the last message with role=user" — but
   agent_chat_stream runs mutate_messages=True on the console path, and the Gemma tool
   protocol feeds a tool RESULT back as a role=user message. So after any tool call, "the
   last user message" was HER OWN TOOL RECEIPT. A write produced an output, the output
   looked like the user talking, and the output got written.

   A protocol role is not a speaker.

Both are fixed at the source (lifecycle.admit_to_user_store now covers every value that
constitutes her; _capture_after_turn is HANDED the human's text, taken before the tool
loop can touch the list). This repairs the rows they left behind.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REG = os.environ.get("SP_RECALL_REGISTRY") or os.path.join(ROOT, "var", "memory", "registry.jsonl")

# her gender, filed as his identity — it retired "I am male"
BAD_GENDER = "ep_tool_1783880554158"
# her tool's own receipt, captured as a fact about him
BAD_ECHO = "ep_tool_1783880561704"


def main() -> int:
    apply = "--apply" in sys.argv
    rows = []
    with open(REG, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    by_name = {r.get("name", ""): r for r in rows}

    changed = []
    victims = []

    bad = by_name.get(BAD_GENDER)
    if bad:
        victims = [v for v in (bad.get("supersedes") or []) if v in by_name]
        print(f"HER GENDER, FILED AS HIS: {BAD_GENDER}")
        print(f"  {bad.get('text')!r}  speaker={bad.get('speaker')} class={bad.get('mem_class')}")
        for v in victims:
            print(f"  it retired: {by_name[v].get('text')!r}")

    echo = by_name.get(BAD_ECHO)
    if echo:
        print(f"\nHER OWN TOOL RECEIPT, STORED AS A FACT: {BAD_ECHO}")
        print(f"  {echo.get('text')!r}")

    for r in rows:
        n = r.get("name", "")

        # 1. "I am a woman" is TRUE — of HER. Re-file it into the self lane, where it is
        #    simply a fact about herself, and strip the supersede it should never have
        #    been allowed to perform on him.
        if n == BAD_GENDER:
            r["speaker"] = "self"
            r["mem_class"] = "identity"
            r["supersedes"] = []
            r["src"] = "repair2: refiled user->self (her gender is not his) 2026-07-12"
            changed.append(n)

        # 2. The tool receipt is not a memory at all. It is exhaust. Tombstone it.
        elif n == BAD_ECHO:
            r["lifecycle"] = 1
            r["src"] = "repair2: tool output captured as a fact (feedback loop) 2026-07-12"
            changed.append(n)

        # 3. His gender comes back.
        elif n in victims:
            r["lifecycle"] = 0
            r["superseded_by"] = ""
            r["src"] = (r.get("src") or "") + " | repair2: un-retired 2026-07-12"
            changed.append(n)

    live_id = [r for r in rows if r.get("mem_class") == "identity" and not r.get("lifecycle")]
    print("\nAFTER REPAIR — live identity rows:")
    for r in sorted(live_id, key=lambda r: r.get("speaker", "")):
        print(f"  speaker={r.get('speaker'):<5} :: {r.get('text')}")

    if not apply:
        print(f"\nDRY RUN — {len(changed)} row(s) would change. Re-run with --apply.")
        return 0

    bak = f"{REG}.{int(time.time())}.bak"
    shutil.copy2(REG, bak)
    with open(REG, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nAPPLIED — {len(changed)} row(s) changed. Backup: {os.path.basename(bak)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
