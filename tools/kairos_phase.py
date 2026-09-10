#!/usr/bin/env python
"""Does her speech/silence have an attractor, or is it memoryless?

The instrument behind docs/PHASE-SPACE-BEHAVIOUR-2026-09-10.md. Four sections, in an order
that is not negotiable, inherited from docs/PHASE-SPACE-2026-09-09.md at the cost of a day:

  A  the APERIODICITY SCREEN, with a positive control. Dimension and determinism mean
     nothing until the series is shown to be aperiodic, and a detector that does not fire
     on a known-periodic series is not a detector. Both controls are synthesised at the
     real series' own length, every run.
  B  is the decision series memoryless -- conditional entropy, lag-1 dependence, runs --
     against a null that is the whole argument (see below).
  C  the same, per lane, because a pooled number hides a dead one.
  D  eot_margin: autocorrelation and recurrence determinism against a shuffle AND an AR(1)
     surrogate matched to its own lag-1, because a shuffle cannot separate "linear memory"
     from "nonlinear structure".
  E  inter-event intervals, where the configured clocks would show up if they shaped this.

THE NULL IS THE WHOLE ARGUMENT. Yesterday's series was a 3000-step decode trajectory: one
process, fixed dt, stationary by construction. This one is an event log spanning 40 days
with an 11-day hole, and the daily spoke-rate swings from 12% to 100%. Drift of that size
manufactures autocorrelation out of nothing, so a GLOBAL shuffle is the wrong null -- it
destroys the drift along with the order and hands the drift back as memory. The default is a
WITHIN-DAY block shuffle: every day's rate preserved exactly, only the order inside the day
destroyed. `--global-null` is available and prints the warning that belongs with it.
Measured 2026-09-10: drift alone accounts for +0.33 of the +0.76 lag-1 dependence, so the
global null would have overstated the effect by more than double.

WHAT IS DELIBERATELY NOT HERE. Correlation dimension needs ~10^D2 points and false nearest
neighbours is worse -- on the 2026-09-09 pass a white-noise surrogate "converged" to m*=5.
At these lengths both would return a confident number for anything, so neither is computed.
"No attractor" from this tool means "no structure beyond lag-1 clustering that these
measures can see", which is a different claim from absence, and the receipt says so.

    python tools/kairos_phase.py
    python tools/kairos_phase.py --surrogates 5000 --era 2026-09-02
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import io
import itertools
import json
import math
import os
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def hdr(s):
    print("\n" + "=" * 78)
    print(s)
    print("=" * 78)


# ── the stores ─────────────────────────────────────────────────────────────────────
def load_decisions(root=ROOT):
    """One row per unprompted turn that reached the LAST gate.

    Note what this store is NOT: the clocks (cooldown, hourly cap, chain) veto inside
    `decide()` BEFORE anything is generated, so a clock-vetoed beat never appears here at
    all -- verified, 0 of 1258 drops name one. This is a CONTENT series, and any dependence
    in it is not the thermostat.
    """
    p = os.path.join(root, "var", "memory", "speech.jsonl")
    out = []
    if not os.path.exists(p):
        return out
    for line in io.open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except (ValueError, TypeError):
            continue
        if r.get("outcome") in ("spoke", "dropped") and r.get("at"):
            out.append(r)
    out.sort(key=lambda r: r["at"])
    return out


_MARGIN_RX = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ .*?\[kairos\] session=(\S+) "
                        r"margin=(-?\d+(?:\.\d+)?) -> (\w+)")


def load_margins(root=ROOT):
    """eot_margin, from the gateway log, which is the only place it is ever written."""
    p = os.path.join(root, "var", "gateway.log")
    out = []
    if not os.path.exists(p):
        return out
    for line in io.open(p, encoding="utf-8", errors="replace"):
        if "margin=" not in line:
            continue
        m = _MARGIN_RX.match(line)
        if m:
            out.append({"at": m.group(1), "session": m.group(2),
                        "margin": float(m.group(3)), "verdict": m.group(4)})
    return out


def telemetry_by_day(root=ROOT):
    rows = collections.OrderedDict()
    for f in sorted(glob.glob(os.path.join(root, "var", "telemetry", "*.jsonl"))):
        c = collections.Counter()
        for line in io.open(f, encoding="utf-8", errors="replace"):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except (ValueError, TypeError):
                continue
            c[r.get("kind")] += 1
            c["__src__" + str(r.get("source"))] += 1
        rows[os.path.basename(f)[:10]] = c
    return rows


# ── measures ───────────────────────────────────────────────────────────────────────
def cond_entropy(x, k):
    """H(X_t | X_{t-k..t-1}) in bits, plug-in. Only meaningful while 2^k << N."""
    if len(x) <= k:
        return float("nan")
    ctx, joint = collections.Counter(), collections.Counter()
    for i in range(k, len(x)):
        c = tuple(x[i - k:i]) if k else ()
        ctx[c] += 1
        joint[(c, x[i])] += 1
    n = sum(ctx.values())
    return -sum((cnt / n) * math.log2(cnt / ctx[c]) for (c, _v), cnt in joint.items())


def runs_z(x):
    """Wald-Wolfowitz. z < 0 is CLUSTERING (fewer, longer runs than chance)."""
    x = np.asarray(x)
    n1, n0 = int(x.sum()), int(len(x) - x.sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    runs = 1 + int((x[1:] != x[:-1]).sum())
    mu = 1 + 2.0 * n1 * n0 / (n1 + n0)
    var = (2.0 * n1 * n0 * (2.0 * n1 * n0 - n1 - n0)) / ((n1 + n0) ** 2 * (n1 + n0 - 1))
    return (runs - mu) / math.sqrt(var) if var > 0 else float("nan")


def lag1_dep(x):
    """P(1|1) - P(1|0): the one number a per-attempt mechanism moves."""
    x = np.asarray(x)
    a, b = x[:-1], x[1:]
    p11 = b[a == 1].mean() if (a == 1).any() else float("nan")
    p10 = b[a == 0].mean() if (a == 0).any() else float("nan")
    return p11, p10, p11 - p10


def block_shuffle(x, blocks, rng):
    y = np.array(x, dtype=int)
    blocks = np.asarray(blocks)
    for b in set(blocks.tolist()):
        idx = np.flatnonzero(blocks == b)
        if len(idx) > 1:
            y[idx] = rng.permutation(y[idx])
    return y


def surrogate(x, blocks, stat, rng, n, label):
    obs = stat(np.asarray(x))
    null = np.array([stat(block_shuffle(x, blocks, rng)) for _ in range(n)])
    null = null[np.isfinite(null)]
    if not len(null) or not np.isfinite(obs):
        print("   %-32s (not computable)" % label)
        return
    floor = 2.0 / (len(null) + 1)
    p = (1 + min((null >= obs).sum(), (null <= obs).sum())) * 2.0 / (len(null) + 1)
    sd = null.std()
    print("   %-32s obs %+8.4f   null %+8.4f +- %.4f   z %+6.2f   p %s"
          % (label, obs, null.mean(), sd, (obs - null.mean()) / sd if sd > 0 else float("nan"),
             "<%.4f" % floor if p <= floor else "%.4f" % min(1.0, p)))


def screen(v, name, exclude=(0, 1, 2), maxlag=200):
    """A period is a SPIKE with a flat harmonic ladder; smoothness is a monotone decay."""
    v = np.asarray(v, dtype=float)
    if v.size < 30 or v.std() == 0:
        print("   %-26s (too short or constant)" % name)
        return
    v = v - v.mean()
    n, ml = len(v), min(len(v) // 3, maxlag)
    ac = np.nan_to_num(np.array(
        [1.0 if k == 0 else (float(np.corrcoef(v[:-k], v[k:])[0, 1]) if n - k > 3 else 0.0)
         for k in range(ml)]))
    cand = [k for k in range(ml) if k not in exclude]
    best = max(cand, key=lambda k: ac[k])
    nb = [ac[j] for j in range(max(1, best - 3), min(ml, best + 4)) if j != best]
    prom = ac[best] - (max(nb) if nb else 0.0)
    harm = [(m * best, ac[m * best]) for m in (2, 3, 4) if m * best < ml]
    ladder = len(harm) >= 2 and ac[best] > 0.3 and all(a > 0.6 * ac[best] for _, a in harm)
    print("   %-26s %-10s lag %-4d ac %+.3f prom %+.3f  harmonics %s"
          % (name, "PERIODIC" if (ladder and prom > 0.15) else "aperiodic",
             best, ac[best], prom,
             " ".join("%d:%.2f" % (l, a) for l, a in harm) or "-"))


def determinism(v, m=3, tau=1, theiler=8, frac=0.10):
    """Recurrences on diagonal lines >= 2: proximity in state predicting the next step.

    Theiler-corrected, or the measure reads smoothness as determinism. Report it ONLY with
    its null: at these lengths and this recurrence fraction the null sits near 0.86, so the
    measure has very little room, and a bare 0.88 would be a number pretending to be a
    result.
    """
    n = len(v) - (m - 1) * tau
    if n < 40:
        return float("nan")
    emb = np.column_stack([v[i * tau:i * tau + n] for i in range(m)])
    d = np.sqrt(((emb[:, None, :] - emb[None, :, :]) ** 2).sum(-1))
    pos = d[d > 0]
    if not pos.size:
        return float("nan")
    R = d <= np.quantile(pos, frac)
    ii, jj = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    R = R & (np.abs(ii - jj) > theiler)
    tot = R.sum()
    return (2.0 * ((R[:-1, :-1] & R[1:, 1:]).sum()) / tot) if tot else float("nan")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--surrogates", type=int, default=2000)
    ap.add_argument("--era", default="2026-09-02", help="the era split date (YYYY-MM-DD)")
    ap.add_argument("--global-null", action="store_true",
                    help="use a global shuffle instead of the within-day block shuffle")
    ap.add_argument("--seed", type=int, default=20260910)
    a = ap.parse_args(argv)
    rng = np.random.default_rng(a.seed)

    dec = load_decisions()
    mg = load_margins()
    if len(dec) < 100:
        print("only %d decisions in var/memory/speech.jsonl -- nothing to reconstruct" % len(dec))
        return 2

    x = [1 if r["outcome"] == "spoke" else 0 for r in dec]
    day = [r["at"][:10] for r in dec]
    kind = [r.get("kind") for r in dec]
    blocks = (["all"] * len(x)) if a.global_null else day
    if a.global_null:
        print("\n!! --global-null: this destroys the day-to-day rate drift along with the")
        print("!! order, so it reports that drift back as memory. Measured 2026-09-10, it")
        print("!! overstates the lag-1 dependence by more than double. Use it to make that")
        print("!! point, not to draw a conclusion.")

    # ── 0. the presence channel, because a dead lane outranks any statistic ────────
    hdr("0. THE PRESENCE CHANNEL")
    tel = telemetry_by_day()
    if not tel:
        print("   no var/telemetry/*.jsonl at all")
    else:
        keys = ("heart_rate", "accel_rms", "battery", "light", "sleep_confidence")
        print("   %-12s %s   watch-sourced" % ("day", " ".join("%11s" % k[:11] for k in keys)))
        for d, c in tel.items():
            print("   %-12s %s   %d"
                  % (d, " ".join("%11d" % c.get(k, 0) for k in keys), c.get("__src__watch", 0)))
        dead = [d for d, c in tel.items() if c.get("__src__watch", 0) == 0]
        if dead:
            print("\n   WATCH SILENT on %d of %d days, most recently %s -- "
                  "presence cannot be reconstructed over that window"
                  % (len(dead), len(tel), dead[-1]))

    # ── A. screen ─────────────────────────────────────────────────────────────────
    hdr("A. THE APERIODICITY SCREEN  (controls first, at the real length)")
    screen(np.sin(2 * np.pi * np.arange(len(x)) / 11.0)
           + 0.05 * rng.standard_normal(len(x)), "control: period 11")
    screen(rng.standard_normal(len(x)), "control: white noise")
    screen(x, "decisions (spoke=1)")
    if mg:
        screen([r["margin"] for r in mg], "eot_margin, all")

    # ── B. memoryless? ────────────────────────────────────────────────────────────
    hdr("B. IS IT MEMORYLESS?   N=%d   base rate %.3f" % (len(x), float(np.mean(x))))
    for k in range(5):
        print("   H(X | k=%d) = %.4f bits" % (k, cond_entropy(x, k)))
    p11, p10, d = lag1_dep(x)
    print("\n   P(spoke | prev spoke  ) = %.4f" % p11)
    print("   P(spoke | prev dropped) = %.4f" % p10)
    print("   difference              = %+.4f" % d)
    print("\n   vs the %s null, %d surrogates:"
          % ("GLOBAL shuffle" if a.global_null else "within-day block shuffle", a.surrogates))
    surrogate(x, blocks, lambda v: lag1_dep(v)[2], rng, a.surrogates, "P(1|1)-P(1|0)")
    surrogate(x, blocks, lambda v: cond_entropy(list(v), 1), rng, a.surrogates, "H(X|X-1) bits")
    surrogate(x, blocks, runs_z, rng, a.surrogates, "runs z  (<0 = clustering)")

    # ── the plateaus, which are what the dependence actually is ───────────────────
    runs = [(k, len(list(g))) for k, g in itertools.groupby(x)]
    dr = [n for k, n in runs if k == 0]
    long_beats = sum(n for k, n in runs if k == 0 and n >= 5)
    print("\n   drop runs: %d   median %d   max %d" % (len(dr), int(np.median(dr)) if dr else 0,
                                                       max(dr) if dr else 0))
    print("   beats inside runs of >=5: %d  (%.0f%% of the series)"
          % (long_beats, 100.0 * long_beats / len(x)))
    ts = []
    for r in dec:
        try:
            ts.append(dt.datetime.strptime(r["at"], "%Y-%m-%dT%H:%M:%SZ").timestamp())
        except ValueError:
            ts.append(float("nan"))
    gd, gs = [], []
    for i in range(1, len(dec)):
        g = ts[i] - ts[i - 1]
        if not (0 < g < 7200):
            continue
        (gd if (x[i - 1] == 0 and x[i] == 0) else gs).append(g)
    if gd and gs:
        print("   median gap  drop->drop %.0fs   after a spoke %.0fs   (%.0fx faster retry)"
              % (np.median(gd), np.median(gs), np.median(gs) / max(1.0, np.median(gd))))

    # ── the era split: same dependence, different cause = a mechanism ─────────────
    print("\n   THE ERA SPLIT at %s -- if the dependence is a mechanism rather than a" % a.era)
    print("   dynamic, it survives unchanged while its CAUSE changes completely:")
    for lo, hi, lbl in (("0000-00-00", a.era, "before"), (a.era, "9999-99-99", "after")):
        idx = [i for i, dd in enumerate(day) if lo <= dd < hi]
        if len(idx) < 40:
            continue
        xv = [x[i] for i in idx]
        c = collections.Counter()
        for i in idx:
            if x[i]:
                continue
            rr = (dec[i].get("reason") or "").lower()
            # BOTH VOCABULARIES, because the store is append-only (2026-09-11). The
            # `len(t)<2` branch used to answer "she had nothing to add after all" for
            # every empty generation -- a motive she had not chosen -- and 927 rows on
            # disk still carry it and always will. The fix splits the new ones into a
            # HELD turn and a real decline, so the buckets below keep the old label as
            # its own row rather than folding it in: a pre-fix empty is genuinely
            # unattributable, and quietly merging it with either new bucket would put a
            # number on a question the old data cannot answer.
            c["EMPTY: unattributable (pre-fix label)" if "nothing to add" in rr else
              "EMPTY: held, no canon" if "no conversation to speak into" in rr else
              "EMPTY: she chose silence" if "chose silence" in rr else
              "EMPTY: canon unknown" if "no words came back" in rr else
              "EMPTY: one character" if "one character came back" in rr else
              "restatement" if "restatement" in rr else
              "claimed an act" if "claimed" in rr else
              "sidecar" if "sidecar" in rr else
              "solo_worth_saying" if "solo_worth" in rr else "other"] += 1
        nd = max(1, sum(c.values()))
        era_runs = [(kk, len(list(g))) for kk, g in itertools.groupby(xv)]
        longest_drop = max((n for kk, n in era_runs if kk == 0), default=0)
        print("     %-7s n=%-5d rate %.3f  diff %+.3f  longest drop run %-4d | %s"
              % (lbl, len(xv), float(np.mean(xv)), lag1_dep(xv)[2], longest_drop,
                 ", ".join("%s %.0f%%" % (k, 100.0 * v / nd) for k, v in c.most_common(3))))

    # ── C. per lane ───────────────────────────────────────────────────────────────
    hdr("C. PER LANE  (a pooled number hides a dead one)")
    for k in ("check_in", "solo", "muse", "mode_turn", "continue"):
        idx = [i for i, kk in enumerate(kind) if kk == k]
        if len(idx) < 60:
            print("   %-10s n=%-5d too short to test" % (k, len(idx)))
            continue
        xk = [x[i] for i in idx]
        p1, p0, dk = lag1_dep(xk)
        print("\n   %-10s n=%-5d rate %.3f  P(1|1) %.3f  P(1|0) %.3f  diff %+.3f  runs z %+.2f"
              % (k, len(xk), float(np.mean(xk)), p1, p0, dk, runs_z(xk)))
        surrogate(xk, [day[i] for i in idx], lambda v: lag1_dep(v)[2], rng,
                  min(a.surrogates, 1000), "  diff vs null")

    # ── D. eot_margin ─────────────────────────────────────────────────────────────
    hdr("D. eot_margin  (the one genuinely dynamical quantity)")
    if not mg:
        print("   no margin samples in var/gateway.log")
    else:
        ses = collections.Counter(r["session"] for r in mg).most_common(1)[0][0]
        v = np.array([r["margin"] for r in mg if r["session"] == ses], dtype=float)
        print("   longest single session %r: n=%d  mean %+.2f  sd %.2f" % (ses, len(v), v.mean(), v.std()))
        print("   (restricted to ONE session because consecutive samples across sessions can")
        print("    be days apart, and every lag below is a lag in BEATS, not in time)")
        for k in (1, 2, 3, 5, 10):
            if len(v) > k + 3:
                print("     autocorr lag %-3d %+.3f" % (k, float(np.corrcoef(v[:-k], v[k:])[0, 1])))
        det = determinism(v)
        sh = np.array([determinism(rng.permutation(v)) for _ in range(40)])
        sh = sh[np.isfinite(sh)]
        r1 = float(np.corrcoef(v[:-1], v[1:])[0, 1]) if len(v) > 4 else 0.0
        ar = []
        for _ in range(40):
            w = np.zeros(len(v))
            for i in range(1, len(v)):
                w[i] = r1 * w[i - 1] + math.sqrt(max(1e-9, 1 - r1 ** 2)) * rng.standard_normal()
            ar.append(determinism(w * v.std() + v.mean()))
        ar = np.array([q for q in ar if np.isfinite(q)])
        print("\n     determinism (m=3, Theiler 8)   %.3f" % det)
        if sh.size:
            print("     shuffled null                  %.3f +- %.3f   z %+.2f"
                  % (sh.mean(), sh.std(), (det - sh.mean()) / sh.std() if sh.std() else float("nan")))
        if ar.size:
            print("     AR(1) null, lag-1 %+.3f        %.3f +- %.3f   z %+.2f"
                  % (r1, ar.mean(), ar.std(), (det - ar.mean()) / ar.std() if ar.std() else float("nan")))

    # ── E. the clocks ─────────────────────────────────────────────────────────────
    hdr("E. WHERE THE CLOCKS WOULD SHOW, IF THEY SHAPED THIS")
    allg = np.array([g for g in (np.diff(np.array(ts))) if 0 < g < 14400])
    if allg.size:
        print("   n=%d gaps under 4h   median %.0fs   mean %.0fs"
              % (allg.size, np.median(allg), allg.mean()))
        for lo, hi, lbl in ((0, 60, "< 1 min"), (60, 300, "1-5 min"),
                            (300, 700, "5-11.7 min   <- checkin_idle_s 600"),
                            (700, 1500, "11.7-25 min"),
                            (1500, 2100, "25-35 min    <- solo_every_s 1800"),
                            (2100, 14400, "> 35 min")):
            n = int(((allg >= lo) & (allg < hi)).sum())
            print("   %-34s %5d %5.1f%% %s"
                  % (lbl, n, 100.0 * n / allg.size, "#" * int(40.0 * n / allg.size)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
