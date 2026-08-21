"""MEMORY TRIAGE — separate real memories from the voice/ASR test corpus.

The registry is 405 rows, 404 of them framed "The user said: ...", and most of them
are TEMPLATE-GENERATED speech-test sentences, not memories:

    "The kind nurse painted the tall building as the sun went down."
    "A lonely sailor polished the garden as the church bells rang."
    "The quick brown fox jumps over the lazy dog."
    "Transcribe the audio exactly."

They were captured by the B4 nightshift growth lane during voice testing and have been
polluting recall ever since (this is what makes an unrelated memory surface mid-answer).

REVERSIBLE BY CONSTRUCTION: nothing is deleted. Rows are partitioned into
    var/memory/registry.jsonl        (keep)
    var/memory/quarantine.jsonl      (test corpus — restorable)
and the original is backed up to registry.jsonl.bak-<ts>.

Run:  python tools/memory/triage.py           # dry run, prints the split
      python tools/memory/triage.py --apply   # writes
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REG = os.path.join(ROOT, "var", "memory", "registry.jsonl")
QUAR = os.path.join(ROOT, "var", "memory", "quarantine.jsonl")

PREFIX = "The user said: "

# The generator's fingerprints. These sentences were synthesised from a small closed
# vocabulary — subject template x verb x object x time-phrase — so they are detectable
# structurally rather than by keyword luck.
SUBJ = r"(?:The|A|An|Our|My)\s+(?:quick|lazy|old|tall|kind|busy|tired|lonely|small|big|young|happy|sad|angry|quiet|loud|brown|golden)\s+\w+"
# The generator drew its trailing clause from a CLOSED SET. That makes the tail an
# exact fingerprint — far more reliable than guessing at the subject template (which
# also emits "My brother ..." / "Our teacher ...", i.e. it carries personal pronouns
# and would otherwise sail through the personal-reference rule).
TIME = (r"(?:as the sun went down|before the rain started|on the way back home|"
        r"as the church bells rang|just before dinner time|after a long day|"
        r"near the old bridge|while the kettle boiled|as the train pulled in|"
        r"while humming a tune|on a cold winter night|during the summer holiday|"
        r"in the middle of the town|with great care and patience|without saying a word|"
        r"just before dawn|as the clock struck noon|in the pouring rain)")
TEMPLATE = re.compile(rf"^{SUBJ}\s+\w+\s+.*\b{TIME}\b\.?$", re.I)

PANGRAMS = (
    "the quick brown fox jumps over the lazy dog",
    "pack my box with five dozen liquor jugs",
    "how vexingly quick daft zebras jump",
)

ASR_DIRECTIVES = (
    "transcribe the audio",
    "transcribe exactly",
    "say the following",
    "repeat after me",
    "read this aloud",
    "testing one two three",
    "this is a test",
    "audio test",
    "voice test",
    "mic test",
)


def body(row: dict) -> str:
    t = (row.get("text") or "").strip()
    return t[len(PREFIX):].strip() if t.startswith(PREFIX) else t


# Voice-lane scaffolding that was captured verbatim as "memories".
VOICE_SCAFFOLD = (
    "[voice:", "<|audio", "transcribe the following audio", "spoke to you out loud",
    "repeat back word-for-word", "listen to what they said",
)

# MY OWN probe prompts from this session's debugging, which the B4 growth lane
# dutifully captured. Distinctive phrases only — never bare digits, because
# "My lucky number is 7741" is a REAL memory and must survive.
MY_PROBES = (
    "quartzblanket", "the code is 4471", "the code is a7b2", "the code is 8302",
    "describe a thunderstorm over the ocean", "the archive records the following",
    "21.7c", "the station is k9", "repeat it.", "digits only",
)

# A memory is ABOUT SOMEONE. The test corpora are generic third-person declaratives
# about nobody ("The children played happily in the green park"). Personal reference
# is the discriminator that separates a memory from a sentence.
PERSONAL = re.compile(r"\b(i|i'm|i've|my|me|mine|you|you're|your|we|our|us|sam|tuffy|kairos)\b", re.I)


def is_test_corpus(row: dict) -> tuple[bool, str]:
    t = body(row)
    low = t.lower().rstrip(".!? ")
    if not t:
        return True, "empty"
    if any(m in low for m in VOICE_SCAFFOLD):
        return True, "voice scaffolding"
    if any(p in low for p in MY_PROBES):
        return True, "debug probe (mine)"
    if low in PANGRAMS or any(p in low for p in PANGRAMS):
        return True, "pangram"
    if any(d in low for d in ASR_DIRECTIVES):
        return True, "asr-directive"
    if TEMPLATE.match(t):
        return True, "template sentence"
    if re.search(rf"\b{TIME}\b", t, re.I):
        return True, "template tail"
    # The load-bearing rule: no personal reference => it is a SENTENCE, not a MEMORY.
    if not PERSONAL.search(t):
        return True, "impersonal declarative (no one it is about)"
    return False, ""


def main() -> int:
    apply = "--apply" in sys.argv
    rows = []
    for ln in open(REG, encoding="utf-8", errors="replace"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:
            pass

    keep, junk = [], []
    for r in rows:
        bad, why = is_test_corpus(r)
        (junk if bad else keep).append((r, why))

    print(f"registry: {len(rows)} rows")
    print(f"  KEEP      : {len(keep)}")
    print(f"  QUARANTINE: {len(junk)}   (voice/ASR test corpus)\n")

    from collections import Counter
    for why, n in Counter(w for _, w in junk).most_common():
        print(f"    {n:4d}  {why}")

    print("\n  --- KEEPING (real memories) ---")
    for r, _ in keep[:40]:
        print(f"    {body(r)[:88]}")
    if len(keep) > 40:
        print(f"    ... and {len(keep)-40} more")

    if not apply:
        print("\n(dry run — pass --apply to write)")
        return 0

    bak = REG + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(REG, bak)
    with open(REG, "w", encoding="utf-8") as f:
        for r, _ in keep:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(QUAR, "a", encoding="utf-8") as f:
        for r, why in junk:
            r = dict(r)
            r["quarantine_reason"] = why
            r["quarantined_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\napplied. backup: {os.path.basename(bak)}")
    print(f"  registry.jsonl   -> {len(keep)} rows")
    print(f"  quarantine.jsonl -> +{len(junk)} rows (restorable)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
