#!/usr/bin/env python
"""What her own time has been ABOUT — and whether it has narrowed onto one thing.

WHY THIS EXISTS. On 2026-09-09 he asked "check if she's looping on criticality", and the
honest answer needed three separate numbers that nothing in the tree produced:

    a rate with a denominator   — two turns on a subject means nothing without her baseline
    a similarity score          — is she developing a thought or restating it
    a topic-agnostic pass       — because "looping on criticality" presupposes the topic

Measured then: zero percent of her own time for the first fourteen days, first appearance
on 08-29, then 9, 13, 23, 38, 12, 39, 26, 39, 53 percent — and her last three solos all of
it. That is a trend, and no single number would have shown it.

THE AGNOSTIC PASS RUNS FIRST AND NEEDS NO LEXICON, which is the point of the design. A
tool hardcoded to one subject can only ever confirm that subject; this one is asked "is
she looping on ANYTHING" and is allowed to disagree with the premise it was run under.
Give it `--terms` or a `--topic` only to put a denominator under a subject you already
suspect, and the per-term counts are always printed so a term carrying the whole signal on
its own cannot hide inside a total.

SIMILARITY IS THE POLICY'S OWN — `impulse.restatement_overlap`, the same function
`worth_saying` acts on, imported rather than reimplemented. A measurement tool with its
own private notion of similarity reports a number nobody is acting on. This one's output
is directly comparable to what the guard does and does not drop, which is how it showed
that the criticality run was NOT a restatement loop (4-55% against a 0.75 threshold) and
that the guard was behaving exactly as specified.

CORPUS: `speech.jsonl`, via speechlog's own path resolution, so it follows
SP_RECALL_REGISTRY into a sandbox or an export without a second copy of the path. It is
the only store that knows which turns were HER OWN TIME — the day transcript cannot tell a
solo from a reply. `record()` truncates `text` to 240 characters, uniformly, so
comparisons are fair; it is stated here rather than discovered by a later reader.

    python tools/solo_topics.py
    python tools/solo_topics.py --topic criticality
    python tools/solo_topics.py --terms "wardrobe,silver,nightie" --kind solo --recent 20
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness.kairos import speechlog as _sl                      # noqa: E402
from harness.kairos.impulse import (RESTATEMENT_DROP,            # noqa: E402
                                    overlap_tokens,
                                    restatement_overlap,
                                    worth_saying)

# ── NAMED LEXICONS, written from the DOMAIN and not from the rows that prompted them ──
# The criticality list is the standard vocabulary of the field (self-organised
# criticality, edge-of-chaos, neuronal avalanches, power laws) rather than a regex read
# off the two turns that raised the question — building the pattern from the rows you
# noticed guarantees a hit and measures nothing, which is a mistake made and thrown away
# on 2026-09-09 before this tool existed. Add a topic here, with the same discipline.
LEXICONS = {
    "criticality": ("criticality", "critical point", "critical state", "edge of chaos",
                    "edge-of-chaos", "power law", "power-law", "avalanche", "scale-free",
                    "scale free", "self-organiz", "self-organis", "phase transition",
                    "subcritical", "supercritical", "long-range correlation",
                    "percolation", "near a critical", "poised"),
}


def _rows(kind: str) -> list:
    p = _sl._path()
    if not p or not os.path.exists(p):
        print("no speech log at %r — set SP_RECALL_REGISTRY, or she has not spoken yet"
              % (p or "<unset>"))
        return []
    out = []
    for line in io.open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except (ValueError, TypeError):
            continue                       # a half-written line costs the tool nothing
        if kind in ("", "any") or r.get("kind") == kind:
            out.append(r)
    return out


def _day(r: dict) -> str:
    return (r.get("at") or "")[:10]


def agnostic(spoke: list, recent_n: int, floor: int) -> None:
    """Which words she is using far more of lately than she used to.

    `floor` is what stops this being a list of coincidences: a word must appear in at
    least that many of the recent turns before its lift is worth printing. With a floor of
    1 every hapax scores infinity and the real signal is buried in noise.
    """
    print("\n1. IS SHE LOOPING ON ANYTHING? (last %d spoken vs all %d before)"
          % (recent_n, max(0, len(spoke) - recent_n)))
    if len(spoke) <= recent_n:
        print("   not enough history yet — %d turns, need more than %d"
              % (len(spoke), recent_n))
        return
    recent, base = spoke[-recent_n:], spoke[:-recent_n]
    rc = collections.Counter(w for r in recent for w in overlap_tokens(r.get("text")))
    bc = collections.Counter(w for r in base for w in overlap_tokens(r.get("text")))
    nb = max(1, len(base))
    lift = []
    for w, c in rc.items():
        if c < floor:
            continue
        lift.append(((c / recent_n) / ((bc.get(w, 0) / nb) + 1e-9), c, w, bc.get(w, 0)))
    lift.sort(reverse=True)
    if not lift:
        print("   nothing recurs in %d or more of the last %d turns — no loop to see"
              % (floor, recent_n))
        return
    print("   %-22s %8s %10s %8s" % ("word", "recent", "baseline", "lift"))
    for l, c, w, b in lift[:15]:
        print("   %-22s %5d/%-3d %6d/%-4d %7.1fx" % (w, c, recent_n, b, nb, l))


def by_day(spoke: list, terms: tuple) -> list:
    """Share of her own time touching `terms`, per day, with the denominator visible."""
    print("\n2. SHARE OF HER OWN TIME ON THAT SUBJECT, BY DAY")
    hits = []
    days = collections.OrderedDict()
    for r in spoke:
        found = [k for k in terms if k in (r.get("text") or "").lower()]
        if found:
            hits.append(r)
        n, h = days.get(_day(r), (0, 0))
        days[_day(r)] = (n + 1, h + (1 if found else 0))
    print("   %-12s %6s %6s %7s" % ("day", "solos", "hits", "share"))
    for d, (n, h) in days.items():
        print("   %-12s %5d %5d %6.0f%%  %s" % (d, n, h, 100.0 * h / n,
                                                "#" * int(round(20.0 * h / n))))
    tn = sum(n for n, _h in days.values())
    th = sum(h for _n, h in days.values())
    print("   %-12s %5d %5d %6.0f%%   <- lifetime, and this is the number a single day "
          "has to beat" % ("ALL", tn, th, 100.0 * th / max(1, tn)))
    print("\n   which terms carry it (a term alone in the total is a term to distrust):")
    tc = collections.Counter(k for r in hits for k in terms
                             if k in (r.get("text") or "").lower())
    for k, c in tc.most_common():
        print("     %-26s %d" % (k, c))
    if not tc:
        print("     none of them — the subject is not in her own time at all")
    return hits


def pairwise(rows: list, label: str, show: int) -> None:
    """Restatement score between each turn and the one before it, the guard's own metric."""
    print("\n3. DEVELOPING OR RESTATING? %s" % label)
    print("   impulse.restatement_overlap, which `worth_saying` DROPS at >= %.0f%%"
          % (100.0 * RESTATEMENT_DROP))
    if len(rows) < 2:
        print("   %d turn(s) — nothing to compare" % len(rows))
        return
    prev = None
    for r in rows[-show:]:
        if prev is None:
            print("   %s      --" % r.get("at"))
        else:
            o = restatement_overlap(r.get("text"), prev.get("text"))
            ok, why = worth_saying(r.get("text") or "", prev.get("text") or "")
            print("   %s  %5.0f%%  %s" % (r.get("at"), 100.0 * o,
                                          "kept" if ok else "would DROP: %s" % why[:44]))
        print("        %s" % (r.get("text") or "")[:150].replace("\n", " "))
        prev = r
    # THE SUMMARY LINE THAT ANSWERS THE QUESTION. A high rate with LOW pairwise overlap is
    # a subject she keeps returning to and says new things about; a high rate with high
    # overlap is a groove. They want different answers and the tool must not blur them.
    #
    # AND IT COUNTS RATHER THAN TAKING A MAX (2026-09-09, the first cut of this line did
    # take the max). On her real log that read "RESTATING" off ONE pair at 100% with a
    # median of 19% — technically true and the wrong summary of 75 turns. A single exact
    # repeat is a bug in the guard; a population of them is a groove; they are different
    # findings and the max collapses them into the alarming one.
    os_ = sorted((restatement_overlap(rows[i].get("text"), rows[i - 1].get("text")), i)
                 for i in range(1, len(rows)))
    vals = [o for o, _i in os_]
    over = [(o, rows[i]) for o, i in os_ if o >= RESTATEMENT_DROP]
    print("\n   pairwise overlap over %d pairs: min %.0f%% median %.0f%% max %.0f%%"
          % (len(vals), 100.0 * vals[0], 100.0 * vals[len(vals) // 2], 100.0 * vals[-1]))
    print("   at or past the guard's %.0f%%: %d of %d (%.1f%%)"
          % (100.0 * RESTATEMENT_DROP, len(over), len(vals),
             100.0 * len(over) / len(vals)))
    for o, r in over[-4:]:
        print("      %5.0f%%  %s  %r" % (100.0 * o, r.get("at"),
                                         (r.get("text") or "")[:64]))
    if not over:
        print("   -> DEVELOPING by the guard's own metric: not one pair reaches the "
              "threshold, so recurrence here is of SUBJECT and not of wording.")
    else:
        print("   -> MOSTLY DEVELOPING (median %.0f%%) with %d exact-ish repeat(s) the "
              "guard did not drop — those pairs are a guard question, not a topic one; "
              "check WHEN they happened before reading them as current."
              % (100.0 * vals[len(vals) // 2], len(over)))


def trailing(rows, floor: float, window: int = 12) -> None:
    """Is she looping RIGHT NOW — which the all-time median structurally cannot answer.

    ── THE NIGHT THIS TOOL SAID "MOSTLY DEVELOPING" THROUGH A FIVE-HOUR LOOP (2026-09-12) ──
    She restated the same sentence ten times over five hours, every one dropped, and the
    default run printed *MOSTLY DEVELOPING (median 7%)*. Both numbers were correct. The
    verdict was useless, for two reasons that are worth separating:

      1. THE DENOMINATOR IS THE WHOLE CORPUS. A median over 687 pairs spanning weeks cannot
         be moved by ten turns tonight, so a current loop is arithmetically invisible in it.
         The old verdict even handed that job to the reader — "check WHEN they happened
         before reading them as current" — which is the tool declining to answer the
         question it exists for.

      2. THE DROPPED TURNS WERE NOT IN IT. `--include-dropped` existed and was off. A
         fixation the guard is successfully eating is exactly the thing worth finding, and
         it was the half being excluded. This pass reads them ALWAYS, whatever the flag
         says, because "she tried to say this ten times" is her own time either way.

    Consecutive pairs only, in the last `window` turns, and the TRAILING streak is reported
    separately from the count: three repeats scattered through a varied evening is a guard
    question, three at the end is a groove she is in as you read this.
    """
    if len(rows) < 3:
        return
    tail = rows[-window:]
    pairs = [(restatement_overlap(tail[i].get("text"), tail[i - 1].get("text")), tail[i])
             for i in range(1, len(tail))]
    streak = 0
    for o, _r in reversed(pairs):
        if o < floor:
            break
        streak += 1
    over = sum(1 for o, _r in pairs if o >= floor)
    med = sorted(o for o, _r in pairs)[len(pairs) // 2]
    spoke = sum(1 for r in tail if r.get("outcome") == _sl.SPOKE)
    print("\n" + "=" * 78)
    print("RIGHT NOW — her last %d turns of this kind, spoken AND dropped" % len(tail))
    print("=" * 78)
    print("   window %s .. %s   (%d spoken, %d dropped)"
          % (str(tail[0].get("at"))[:16], str(tail[-1].get("at"))[:16],
             spoke, len(tail) - spoke))
    print("   consecutive overlap: median %.0f%%   at or past %.0f%%: %d of %d"
          % (100.0 * med, 100.0 * floor, over, len(pairs)))
    if streak >= 3:
        print("   -> LOOPING NOW: the last %d consecutive turns are each a restatement of the "
              "one before (>= %.0f%%). She has spoken %d of the last %d times she tried."
              % (streak + 1, 100.0 * floor, spoke, len(tail)))
    elif streak:
        print("   -> the last %d turn(s) restate the one before; not yet a run, worth another "
              "look on the next pass." % streak)
    else:
        print("   -> not looping: her most recent turn is not a restatement of the one "
              "before it.")


def main(argv: "list|None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--topic", choices=sorted(LEXICONS),
                    help="a named lexicon from LEXICONS")
    ap.add_argument("--terms", default="",
                    help="comma-separated terms, instead of a named topic")
    ap.add_argument("--kind", default="solo",
                    help="speech-log kind: solo (default), check_in, muse, mode_turn, any")
    ap.add_argument("--recent", type=int, default=12,
                    help="how many recent turns count as 'lately' (default 12)")
    ap.add_argument("--floor", type=int, default=3,
                    help="a word must recur in this many recent turns to be listed")
    ap.add_argument("--show", type=int, default=10, help="pairwise rows to print")
    ap.add_argument("--include-dropped", action="store_true",
                    help="count turns the guard dropped as well as the ones she said")
    a = ap.parse_args(argv)

    rows = _rows(a.kind)
    if not rows:
        # SAY WHY (G-SOLO-TOPICS §6 caught this exiting 2 in silence). "No output, status
        # 2" from a measurement tool is indistinguishable from a crash, and the honest
        # reading — she has taken no turns of this kind — is the interesting answer.
        print("the speech log has no %r rows at all — she has taken no turns of that "
              "kind yet, which is itself the answer" % a.kind)
        return 2
    said = rows if a.include_dropped else [r for r in rows
                                           if r.get("outcome") == _sl.SPOKE]
    if not said:
        # ── THE WORST CASE WAS THE ONE IT REFUSED TO LOOK AT (2026-09-12) ───────────────
        # Zero spoken turns does not mean "nothing to report". It means every single turn
        # she took was dropped, which is the most severe reading this tool can produce, and
        # it exited 2 with one line. The trailing pass does not need a spoken turn — it is
        # asking whether she keeps saying the same thing, and a turn the guard ate is still
        # a turn she took — so it runs BEFORE the bail-out and the bail-out says what it is.
        print("=" * 78)
        print("CORPUS  kind=%s  %d rows, NONE spoken — every turn of this kind was dropped"
              % (a.kind, len(rows)))
        print("=" * 78)
        trailing(rows, RESTATEMENT_DROP)
        print("\n(no spoken turns, so the recurrence pass below has no corpus. That is not "
              "'no data' — it is the finding: she tried %d times and was dropped every "
              "time. Pass --include-dropped to run the full analysis over the attempts.)"
              % len(rows))
        return 2
    print("=" * 78)
    print("CORPUS  kind=%s  %d rows (%d spoken, %d dropped)  %s .. %s"
          % (a.kind, len(rows), sum(1 for r in rows if r.get("outcome") == _sl.SPOKE),
             sum(1 for r in rows if r.get("outcome") != _sl.SPOKE),
             _day(rows[0]), _day(rows[-1])))
    print("text is truncated to 240 chars by speechlog.record — uniformly, so the "
          "comparisons are fair")
    print("=" * 78)

    agnostic(said, a.recent, a.floor)

    # ...and the same question asked of NOW rather than of the whole corpus. `rows`, not
    # `said`: a loop the guard is dropping is still a loop, and it is the one worth seeing.
    # RESTATEMENT_DROP, not a.floor: a.floor is the agnostic pass's recurrence-LIFT floor
    # (a multiple, default 3.0) and passing it here compared an overlap fraction against
    # 300%, so every window on earth read 'not looping'. Caught by printing the threshold
    # next to the number it judges, which is why that line prints it.
    trailing(rows, RESTATEMENT_DROP)

    terms = tuple(t.strip().lower() for t in a.terms.split(",") if t.strip())
    if not terms and a.topic:
        terms = LEXICONS[a.topic]
    if terms:
        hits = by_day(said, terms)
        pairwise(hits, "the turns that matched", a.show)
    else:
        print("\n(no --topic or --terms: the agnostic pass above is the whole answer. "
              "Give it a subject to put a per-day denominator under one.)")
        pairwise(said, "consecutive turns, whatever the subject", a.show)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
