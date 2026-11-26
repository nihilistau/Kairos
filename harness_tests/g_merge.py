"""G-MERGE — another copy of her folds into a home, adding and never removing. OFFLINE.
(harness/merge.py, ruling 9.2)

  1. facts the home lacks are added (marked merged_from); facts both have stay the home's
  2. log lines, transcript days and journal paragraphs the home lacks are added
  3. the other copy's persona is kept in the archive; the home's persona is untouched
  4. a before-bundle and a journal line come first
  5. merging the same copy twice adds nothing
  6. NOTHING the home held is removed or changed
  7. never on a live home

Run: python harness_tests/g_merge.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_merge")

from harness import bundle as B  # noqa: E402
from harness import home as H  # noqa: E402
from harness import merge as MG  # noqa: E402

H.COMPANIONS_DIR = os.environ["SP_COMPANIONS_DIR"]


def w(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def r(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


home = H.create("kairos", "Kairos")
P = H.resolve(home)
row = lambda n, t: json.dumps({"name": n, "text": t})  # noqa: E731
w(P["registry"], row("a", "shared fact") + "\n" + row("b", "hers, edited later") + "\n")
mdir = os.path.dirname(P["registry"])
w(os.path.join(mdir, "speech.jsonl"), '{"said":"one"}\n')
w(os.path.join(mdir, "transcripts", "2026-11-05.jsonl"), '{"t":1}\n')
w(os.path.join(mdir, "narrative.md"), "Monday was quiet.\n")
w(P["persona_file"], "Hers.\n")
before = {k: r(v) for k, v in P.items() if os.path.isfile(v)}

other = os.path.join(SB, "runpod-copy")
om = os.path.join(other, "var", "memory")
w(os.path.join(om, "registry.jsonl"), row("a", "shared fact") + "\n" + row("b", "the copy's older b") + "\n"
  + row("c", "only the copy knows this") + "\n")
w(os.path.join(om, "speech.jsonl"), '{"said":"one"}\n{"said":"two, on the pod"}\n')
w(os.path.join(om, "transcripts", "2026-11-05.jsonl"), '{"t":1}\n{"t":2}\n')
w(os.path.join(om, "transcripts", "2026-11-20.jsonl"), '{"t":9}\n')
w(os.path.join(om, "narrative.md"), "Monday was quiet.\n\nThursday on the big card felt different.\n")
w(os.path.join(other, "persona.md"), "The copy's persona.\n")
w(os.path.join(other, "memory-okf-personality", "full", "abc.md"), "an own-time note\n")

print("1-4. the merge")
res = MG.merge(home, other, label="runpod")
reg = [json.loads(l) for l in r(P["registry"]).splitlines() if l.strip()]
byname = {x["name"]: x for x in reg}
check("a fact only the copy knows is added, marked", byname.get("c", {}).get("merged_from") == "runpod")
check("a fact both have stays the home's", byname["b"]["text"] == "hers, edited later" and res["rows_kept"] == 1)
check("speech lines the home lacks are added", "two, on the pod" in r(os.path.join(mdir, "speech.jsonl")))
check("a day the home lacks is copied", os.path.isfile(os.path.join(mdir, "transcripts", "2026-11-20.jsonl")))
check("a day both have gains the other's lines", '"t":2' in r(os.path.join(mdir, "transcripts", "2026-11-05.jsonl")))
check("journal paragraphs the home lacks are appended", "big card" in r(os.path.join(mdir, "narrative.md"))
      and r(os.path.join(mdir, "narrative.md")).count("Monday was quiet.") == 1)
check("archive files the home lacks are copied", os.path.isfile(os.path.join(P["personality_okf"], "full", "abc.md")))
check("the home's persona is untouched", r(P["persona_file"]) == "Hers.\n")
check("the copy's persona is kept in the archive", any("merged-runpod" in d for d in os.listdir(os.path.join(home, "archive"))))
check("a before-bundle was written first", os.path.isfile(os.path.join(os.environ["SP_BUNDLE_DIR"], res["before"])))
check("the journal records it", B.history(home)[-1]["op"] == "merge")

print("\n5. twice adds nothing")
res2 = MG.merge(home, other, label="runpod")
check("a second merge adds nothing", (res2["rows_added"], res2["lines_added"], res2["days_added"], res2["days_extended"],
                                       res2["journal_paragraphs"], res2["okf_files"]) == (0, 0, 0, 0, 0, 0), res2)

print("\n6. nothing removed")
after = {k: r(v) for k, v in P.items() if os.path.isfile(v)}
check("every file the home held still starts with what it held", all(after[k].startswith(v) for k, v in before.items()),
      [k for k, v in before.items() if not after.get(k, "").startswith(v)])

print("\n7. never live")
H.claim_live(home)
try:
    MG.merge(home, other)
    check("a live home is refused", False)
except B.BundleError as e:
    check("a live home is refused", "running" in str(e))
os.remove(os.path.join(home, H.LIVE))

finish("G-MERGE")
