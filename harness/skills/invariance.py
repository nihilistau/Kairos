"""invariance — the ENTRY TEST for invariance maps (Tier 3, INVARIANT-ROADMAP.md §1.1).

The stability family (G-SEM-STABLE) used to be three artisanal theorems. Friedman's
FIN/USE gives the discipline an admissions office: for a FINITE partial self-map f of
[-1,1], "can this invariance be demanded of maximal objects?" is completely
characterized and LOCALLY checkable.

── THE SOURCE, PINNED (2026-07-30) ───────────────────────────────────────────────────
Harvey Friedman, *Invariant Maximality Derivations* (Chapter 3 of *Invariant Maximality,
Finite Constructions, and Games*), 16 October 2025, **§3.6.6** — Downloadable Manuscripts
#127, `u.osu.edu/friedman.8/files/2025/10/TangIncCh3101525.docx`. It is a .docx, not a
PDF, which is why a PDF-only search of the lecture notes finds nothing. Verbatim:

    FIN/USE. Let f::[-1,1] -> [-1,1] be finite. The following are equivalent.
      i.   f is fully usable
      ii.  f is 2-usable
      iii. f is strictly increasing, and: (-1 < f(-1) and f⁻¹(1) < 1) and
           (-1 < f⁻¹(-1) and f(1) < 1) both fail.

    FIN/USE*. A finite f::[-1,1] -> [-1,1] is fully usable if and only if every two
    element restriction is 2-usable.

"Usable" is defined separately at §3.5 Def 3.5.1: f is fully usable iff OC/MAX/f; usable
iff all seven Secondary Templates hold. The necessity of each clause is proved
separately (Thm 3.5.1.1 monotonicity; Lemma 3.5.1.2 and Thm 3.5.1.3 the endpoints).

TRANSCRIPTION NOTE — do not "fix" the form below. Friedman's own text prints clause iii
with a typo TWICE (the chapter intro and the §3.6.6 proof preamble render the second
conjunct as `f(-1) < 1`). The correct `f(1) < 1` appears four times elsewhere — §3.6
preamble, the §3.6.6 statement, FIN/USE/EXPTIME §3.6.7, and Thm 3.9.6.2 — and is the
only form consistent with Thm 3.5.1.3's duality argument. Ours is the correct one.

── THREE THINGS THIS MODULE MUST NOT OVERCLAIM ───────────────────────────────────────
1. DECIDABILITY IS OUR COROLLARY, NOT HIS THEOREM. Friedman never writes "decidable".
   What §3.6.7 proves (in SEFA) is FIN/USE/EXPTIME: the *witnessing invariant maximal
   sets* are EXPTIME. That clause iii is a finite check on fld(f) — and therefore that
   usability of a finite f is decidable — follows trivially, but it is our inference and
   the two claims must not be conflated.
2. THE AXIS IS [-1,1], NOT "a bounded axis". Our time line is unbounded, and we read the
   endpoint conditions as vacuous there. That is an EMBEDDING argument and it is stated
   here rather than assumed: a finite map whose field lies strictly inside the interval
   never instantiates f(-1), f⁻¹(-1), f(1) or f⁻¹(1), so both pathologies are vacuously
   false and clause iii collapses to "strictly increasing". Order-embed the finite field
   into the interior of [-1,1] and FIN/USE applies verbatim.
3. FIN/USE IS AN *IFF* ONLY FOR FINITE f. For an INTERVAL EXTENSION g = f ∪ id(J)
   (§3.9.1) — which is what "identity outside a window, moved inside it" actually is —
   §3.9 says plainly: "We wish to do the same for the interval extensions... We have
   only been partially successful with this aim." Thm 3.9.6.2 proves the same three
   conditions remain NECESSARY; sufficiency is an explicit open CONJECTURE. So this
   module REFUSES to certify an interval extension (see `identity_on`) and offers
   `necessary_conditions()` instead. Refusing is the safe direction: a gate may demand
   silence, never speech.

USE: any transformation proposed for the G-SEM-STABLE family passes through
admissible() BEFORE it becomes a gate. A map this module rejects is not a worse
invariance — it is one the mathematics says CANNOT be consistently demanded of maximal
views at all, and gating it would be pinning a promise that provably cannot hold.

Maps are finite dicts {a: b} of Fractions/floats over an axis [lo, hi]; identity points
may be included or omitted (only the moved points matter to the conditions). Either
bound may be None = unbounded on that side, which makes the matching endpoint condition
vacuous by (2) above.
"""
from fractions import Fraction


def _pairs(f: dict):
    return sorted((Fraction(a).limit_denominator(10**9),
                   Fraction(b).limit_denominator(10**9)) for a, b in f.items())


def _clauses(f: dict, lo=None, hi=None):
    """The three FIN/USE clause-iii checks, with no verdict attached.

    Split out because they mean two DIFFERENT things depending on the shape of the map:
    for a finite f they are necessary AND sufficient (§3.6.6); for an interval extension
    they are necessary only (§3.9.6.2). Same arithmetic, different licence — so the
    arithmetic lives in one place and the licence is decided by the caller."""
    pts = _pairs(f)
    if not pts:
        return True, "empty map (identity): trivially usable"
    # strictly increasing (FIN/USE i->iii, via Thm 3.5.1.1's necessity)
    for i in range(len(pts) - 1):
        (a1, b1), (a2, b2) = pts[i], pts[i + 1]
        if a1 == a2:
            return False, "not a function: %s mapped twice" % a1
        if not (b1 < b2):
            return False, ("not strictly increasing: f(%s)=%s !< f(%s)=%s"
                           % (a1, b1, a2, b2))
    dom = {a for a, _ in pts}
    rng = {b for _, b in pts}
    if lo is not None:
        LO = Fraction(lo)
        if any(x < LO for x in dom | rng):
            return False, "map leaves the declared axis (below lo)"
    if hi is not None:
        HI = Fraction(hi)
        if any(x > HI for x in dom | rng):
            return False, "map leaves the declared axis (above hi)"
    # endpoint pathologies (FIN/USE iii): each needs BOTH conjuncts to hold to be fatal
    def fwd(x):
        d = dict(pts)
        return d.get(x, x)

    def inv(x):
        d = {b: a for a, b in pts}
        return d.get(x, x)

    if lo is not None and hi is not None:
        LO, HI = Fraction(lo), Fraction(hi)
        if LO < fwd(LO) and inv(HI) < HI:
            return False, ("endpoint pathology: f lifts lo while hi is reached from "
                           "strictly inside — FIN/USE says this invariance cannot be "
                           "demanded of maximal objects")
        if LO < inv(LO) and fwd(HI) < HI:
            return False, ("endpoint pathology (dual): f⁻¹ lifts lo while f pulls hi "
                           "strictly inside")
    return True, "strictly increasing, endpoints clean"


def admissible(f: dict, lo=None, hi=None, identity_on=None):
    """(ok, why) — may this invariance be DEMANDED of maximal objects?

    `identity_on=(a, b)` declares the map to be an INTERVAL EXTENSION g = f ∪ id([a,b])
    rather than a finite map. FIN/USE does not reach that case: §3.9.6.2 gives the three
    conditions as NECESSARY and leaves sufficiency an open conjecture, so certifying one
    would be pinning a promise the mathematics has not made. We refuse instead, and the
    refusal names why. `necessary_conditions()` answers the weaker question honestly.
    """
    ok, why = _clauses(f, lo, hi)
    if not ok:
        return False, why
    if identity_on is not None:
        a, b = identity_on
        return False, (
            "necessary conditions hold, but this is an INTERVAL EXTENSION "
            "(identity on [%s, %s]): FIN/USE §3.6.6 is an iff for FINITE f only, and "
            "§3.9.6.2 leaves sufficiency an open conjecture. Refusing to certify — use "
            "necessary_conditions() if the necessary half is what you need." % (a, b))
    return True, why + ": usable (FIN/USE §3.6.6)"


def necessary_conditions(f: dict, lo=None, hi=None):
    """(ok, why) for the three conditions of Thm 3.9.6.2 — NECESSARY for full (or even
    2-) usability, and known sufficient only when the map is finite. Use this when the
    map is an interval extension and the honest answer is "not refuted", not "usable"."""
    ok, why = _clauses(f, lo, hi)
    if not ok:
        return False, why + " — refuted (Thm 3.9.6.2 necessity)"
    return True, why + ": necessary conditions hold (Thm 3.9.6.2); sufficiency OPEN"


def admissible_pairwise(f: dict, lo=None, hi=None):
    """FIN/USE*: the LOCAL form — usable iff every two-element restriction is usable.
    Exists so the gate can assert the locality theorem holds on real batteries (the
    global and pairwise answers must agree; disagreement is a bug in THIS module).

    Finite maps only — FIN/USE* is stated for finite f, and an interval extension has no
    two-element restriction that captures id(J). Callers with an `identity_on` map want
    necessary_conditions(), not this."""
    pts = _pairs(f)
    if len(pts) <= 1:
        return admissible(f, lo, hi)
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            ok, why = admissible(dict([pts[i], pts[j]]), lo, hi)
            if not ok:
                return False, "2-element restriction {%s, %s}: %s" % (
                    pts[i][0], pts[j][0], why)
    return True, "every two-element restriction is usable (FIN/USE*)"
