"""G-MEMORY-LIFECYCLE / G-MEMORY-PROVENANCE — is the memory ALIVE?

THE AUDIT THAT FORCED THIS (2026-07-12): the registry held 487 rows, of which
**404 were B4 auto-capture and exactly ONE came from the remember() tool.** The model
had deliberately remembered one thing in its life, 404/405 rows were framed
"The user said: ...", and NO row carried speaker / supersedes / superseded_by. It was
an append-only tape with a firehose pointed at it — not a memory.

This gate asserts the three verbs that make it living:

  WRITE      a fact can be stored deliberately, with provenance (who/when/what class)
  SUPERSEDE  a fact that CHANGES retires the old one (tombstone forward, never delete)
  PROVENANCE self-facts and user-facts never merge — "I am male" means different things
             depending on WHO SAID IT, and the owner is stored at write time, not
             guessed at read time (guessing is how she began speaking as the user)

Offline: no daemon, no inference. Runs against a temp registry.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def rows(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main() -> int:
    print("G-MEMORY-LIFECYCLE - can memory be authored, revised, and owned?\n")
    tmp = tempfile.mkdtemp(prefix="g_mem_")
    reg = os.path.join(tmp, "registry.jsonl")
    open(reg, "w").close()
    os.environ["SP_RECALL_REGISTRY"] = reg
    os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:1"    # unreachable => no minting, fine

    from harness.skills import memory as M
    from harness.skills import lifecycle as lc

    # ── WRITE + provenance ────────────────────────────────────────────────────
    M.set_author("user")
    M.remember("My cat's name is Tuffy.")
    r = rows(reg)
    check("a stored fact carries a SPEAKER", r and r[-1].get("speaker") == "user",
          r[-1].get("speaker") if r else "no rows")
    check("a stored fact carries a CLASS", r and r[-1].get("mem_class") == "relationship",
          r[-1].get("mem_class") if r else "-")
    check("a stored fact carries a TIMESTAMP", bool(r and r[-1].get("ts")))

    # ── SUPERSEDE ─────────────────────────────────────────────────────────────
    out = M.remember("My cat's name is Milo.")
    r = rows(reg)
    old = [x for x in r if "Tuffy" in (x.get("text") or "")]
    new = [x for x in r if "Milo" in (x.get("text") or "")]
    check("a CHANGED fact supersedes the old one",
          bool(old and old[0].get("superseded_by")), out.strip())
    check("the old fact is TOMBSTONED, not deleted", bool(old))
    check("the new fact points BACK at what it replaced",
          bool(new and new[0].get("supersedes")))

    # an UNRELATED fact must not retire anything
    M.remember("My lucky number is 7741.")
    r = rows(reg)
    milo = [x for x in r if "Milo" in (x.get("text") or "")][0]
    check("an UNRELATED fact supersedes nothing", not milo.get("superseded_by"))

    # a RESTATEMENT of the same value must not churn the store
    before = len(rows(reg))
    M.remember("My lucky number is 7741.")
    check("a verbatim restatement is idempotent", len(rows(reg)) == before)

    # ── SELF vs USER (the identity lane) ──────────────────────────────────────
    M.remember("I am male")                       # the USER says it -> about the USER
    M.remember_about_self("I am female")          # KAIROS says it -> about KAIROS
    r = rows(reg)
    u = [x for x in r if x.get("speaker") == "user" and "male" in (x.get("text") or "")]
    s = [x for x in r if x.get("speaker") == "self"]
    check("the user's 'I am male' is owned by the USER", bool(u))
    check("Kairos's 'I am female' is owned by SELF", bool(s))
    check("the two DID NOT collide (no supersede across speakers)",
          bool(u and s and not u[0].get("superseded_by")),
          "same sentence shape, different owner - must not overwrite each other")

    # ── READ-BACK VOICE (why she spoke as the user) ───────────────────────────
    check("a self memory reads back in HER voice",
          s and lc.render(s[0]).startswith("About myself:"),
          lc.render(s[0]) if s else "-")
    check("a user memory reads back as the USER's",
          u and lc.render(u[0]).startswith("Sam told me:"),
          lc.render(u[0]) if u else "-")

    # ── THE DEAD ARE DEAD BY `lifecycle`, WHATEVER ELSE THE ROW LACKS ─────────
    # find_superseded (and the dominance proposer, and expand's corpus) keyed on
    # `superseded_by` — so an ORPHAN tombstone (lifecycle=1, no breadcrumb; the live
    # store had one, a repair-era row) was still LIVE to the supersede machinery: a new
    # conflicting fact would re-retire the corpse and OVERWRITE its history with a
    # breadcrumb naming the wrong cause. `lifecycle` is the one death field (AGENTS.md
    # §3); the breadcrumb is the audit trail, never the test.
    orphan = {"name": "ep_orphan_test", "text": "My monitor is a 24-inch Dell.",
              "speaker": "user", "status": "observed", "mem_class": "fact",
              "lifecycle": 1, "ts": "2026-07-01T00:00:00Z", "src": "repair-era row"}
    with open(reg, "a", encoding="utf-8") as f:
        f.write(json.dumps(orphan) + "\n")
    M.remember("My monitor is a 32-inch Samsung.")
    r = rows(reg)
    orow = [x for x in r if x.get("name") == "ep_orphan_test"][0]
    check("an orphan tombstone is DEAD to the supersede machinery",
          not orow.get("superseded_by"),
          "its history was rewritten to name the new row: %r" % orow.get("superseded_by"))
    nrow = [x for x in r if "Samsung" in (x.get("text") or "")]
    check("...and the new fact does not claim to have retired a corpse",
          bool(nrow) and "ep_orphan_test" not in (nrow[0].get("supersedes") or []),
          nrow[0].get("supersedes") if nrow else "-")

    # ── A PARAPHRASE IS NOT TESTIMONY ─────────────────────────────────────────
    # The consolidator asks the model to "write the facts the user stated" and stores
    # the answer. Those are the MODEL'S PARAPHRASES of a transcript, and they were
    # stamped status=observed — ground truth, with full authority to retire rows he
    # actually said (observed may supersede observed). 14 such rows sat live in the
    # store when this was found (2026-08-19).
    M.remember("My favourite drink is coffee.", source="user turn")
    M.remember("My favourite drink is tea.", source="consolidator")
    r = rows(reg)
    tea = [x for x in r if "tea" in (x.get("text") or "")]
    coffee = [x for x in r if "coffee" in (x.get("text") or "")]
    check("a consolidator row is stamped INFERRED (a paraphrase, not his words)",
          bool(tea) and tea[0].get("status") == "inferred",
          tea[0].get("status") if tea else "-")
    check("...and it CANNOT retire what he actually said",
          bool(coffee) and not coffee[0].get("lifecycle"),
          "his testimony was tombstoned by a paraphrase")

    print(f"\nG-MEMORY-LIFECYCLE: {'PASS' if not FAIL else 'FAIL'} "
          f"({len(PASS)}/{len(PASS) + len(FAIL)})")
    if FAIL:
        print("  ^ memory is still a tape, not a mind.")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
