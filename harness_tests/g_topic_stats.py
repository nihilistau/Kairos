"""G-TOPIC-STATS — the topic battery's statistics cannot silently become wrong. OFFLINE.

WHY (2026-09-19). `tools/jlens_topic.py` produced the numbers in the larger-battery section of
docs/TUNED-LENS-2026-09-19.md, and every one of them is a comparison against a null or a
control. Each has a plausible-looking simplification that changes the answer and NOTHING a
reader would notice: the p-value still prints, the AUC still prints, the run still exits 0. A
measurement tool's failure mode is not a crash, it is a confident number.

  §1 THE PERMUTATION UNIT MUST BE THE ITEM. Pairs are not independent — each of 86 turns
     appears in 85 of them — so the exchangeable unit is the turn, and the pair labels have to
     be rebuilt from a shuffled item assignment. This leg is STRUCTURAL and says so, because
     the honest finding is that it makes almost no numerical difference: on the receipt's own
     data the two nulls' 95th percentiles are 0.548 and 0.551, and across six synthetic
     fixtures the ratio ranges 0.92 to 1.22 with no consistent direction. AUC is a rank
     statistic over thousands of pairs and both permutations preserve the positive count and
     the marginal ranks, so the dependency barely moves it. **That is the argument FOR gating
     it rather than against**: a revert would be invisible in every printed number, which is
     precisely the class of error a green suite cannot catch (AGENTS.md §0). The first draft of
     this gate asserted a measurable width difference, failed, and was corrected here rather
     than tuned until it passed.
  §2 THE FAST AUC MUST EQUAL THE SLOW ONE. `auc_ranked` exists so a permutation draw is a
     masked sum instead of a pos-by-neg comparison table — the control battery went from hours
     to 22 seconds. A rank identity that is subtly wrong shifts the observed statistic and the
     null TOGETHER, so nothing looks broken.
  §3 THE POSITION GUARD MUST READ THE `.pos` SIDECAR. persist-KV reseams, so a captured row
     count below the prompt length is NORMAL. A guard written as `r1 - r0 >= len(ids)` looks
     equivalent, passes constantly, and pools whatever rows sit at those offsets.
  §4 `--max-ids` MUST STAY UNDER THE BATCHED-PREFILL LINE. Measured 2026-09-19: the batched
     prefill takes over between 62 and 70 ids, and past it NO prompt position reaches the
     decode tap. That is exactly how the first real run read AUC 0.526 — it pooled her
     boilerplate continuation and reported a null about the model. Raising this default
     re-creates that failure and reports it as a finding.
  §5/§6 POOLING NORMALISES AND SCORING CENTRES. At L17 two UNRELATED sentences already sit at
     cosine 0.805. Without centring the AUC reads the anisotropy of the layer; without
     normalising the cosine is a dot product and reads vector length.

SOURCE LEGS MATCH WHITESPACE-INSENSITIVELY over a comment-and-docstring-stripped token stream.
The stripper joins tokens with spaces, so `np.ix_` arrives as `np . ix_` and a leg written
against the source spelling fails on its own subject — which is how the first run of this gate
went red on §1 and §3 for no reason at all.

MUTANTS ARE TEXT SWAPS ON AN IN-MEMORY COPY, never on disk and never a monkeypatch. A
monkeypatch binds to the module attribute the gate imported, so moving the function later would
leave the patch succeeding and reaching nothing. Exec'ing (or re-tokenizing) a mutated source
has no such alias. Each mutant names the leg it must turn red, and OMITs itself if the line it
swaps is gone, because an absent substitution is an unarmed mutant.

    python harness_tests/g_topic_stats.py
"""
from __future__ import annotations

import io
import os
import sys
import tokenize as _tok

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _gate  # noqa: E402
from _gate import check, finish, omit, sandbox, skip, utf8_stdout  # noqa: E402

utf8_stdout()
sandbox("g_topic_stats")

TOOL = os.path.join(ROOT, "tools", "jlens_topic.py")
if not os.path.exists(TOOL):
    skip("tools/jlens_topic.py is absent (the Kairos export's tools list is explicit)",
         "G-TOPIC-STATS")

try:
    import numpy as np
except Exception:
    skip("numpy is unavailable", "G-TOPIC-STATS")


def code_only(text):
    """Source with comments AND docstrings removed, string literals KEPT.

    A leg that greps raw text convicts the prose explaining the fix — this gate's own §3
    paragraph contains the phrase §3 forbids. Docstrings are identified as a STRING token whose
    predecessor is a layout token, so `prev` is updated on EVERY token including layout;
    skipping layout to "ignore it" is what let docstrings survive the first time this helper
    was written (g_jlens_probe.py carries the same note)."""
    starts = (_tok.INDENT, _tok.DEDENT, _tok.NEWLINE, _tok.NL, _tok.ENCODING)
    out, prev = [], _tok.ENCODING
    rl = io.BytesIO(text.encode("utf-8")).readline
    for t in _tok.tokenize(rl):
        if t.type == _tok.COMMENT:
            continue                          # prev unchanged: a comment is not a token
        if t.type == _tok.STRING and prev in starts:
            prev = t.type
            continue
        prev = t.type
        out.append(t.string)
    return " ".join(out)


def flat(s):
    """Whitespace removed, so a leg can be written the way the source spells it."""
    return "".join(s.split())


SRC = io.open(TOOL, encoding="utf-8").read()
CODE = flat(code_only(SRC))


def load(src=None):
    """Exec a copy of the tool. No import, so a mutant cannot leak into the real module."""
    ns = {"__name__": "jlens_topic_probe", "__file__": TOOL}
    exec(compile(src if src is not None else SRC, TOOL, "exec"), ns)
    return ns


M = load()
for fn in ("perm_null", "auc", "auc_ranked", "rank_of", "cos_pairs", "pool", "pair_index",
           "run_real_prompt", "run_controls", "report_real", "main"):
    if fn not in M:
        skip("tools/jlens_topic.py has no %s(); this gate's subject has moved" % fn,
             "G-TOPIC-STATS")


def body(code, start, end):
    return code.split(start)[1].split(end)[0] if start in code and end in code else ""


PERM = body(CODE, "defperm_null", "defreport_real")
REALP = body(CODE, "defrun_real_prompt", "defreport_real")

# ── §1 the permutation unit ───────────────────────────────────────────────────────────────
check("§1 perm_null shuffles the ITEM axis", "rng.permutation(S.shape[0])" in PERM,
      "the exchangeable unit is the turn, not the pair")
check("§1 and rebuilds the pair labels from the shuffled assignment",
      "S[np.ix_(p,p)][I,J]" in PERM,
      "indexing S on both axes is what keeps each turn's memberships intact")
check("§1 it never shuffles a pair-label vector directly",
      "rng.permutation(same)" not in PERM and "rng.permutation(len(" not in PERM,
      "a pair shuffle is the wrong unit even where it happens to give the same number")

# ── §2 the fast AUC equals the slow one ───────────────────────────────────────────────────
rng = np.random.default_rng(11)
worst = 0.0
for _ in range(25):
    c = rng.normal(size=600)
    m = rng.random(600) < rng.uniform(0.05, 0.4)
    if m.all() or not m.any():
        continue
    worst = max(worst, abs(M["auc"](c, m) - M["auc_ranked"](M["rank_of"](c), m)))
check("§2 auc_ranked equals the pos-by-neg comparison form", worst < 1e-12,
      "worst disagreement over 25 random draws: %.3e" % worst)

# and it has to actually be used, or the observed statistic and the null part company
def est_ok(code):
    """BOTH reporting paths, not one. `run_controls` and `report_real` each compute the
    observed AUC and the line is identical in both, so a leg written as `in` passes while one
    of them has been reverted — which is exactly what the first run of this mutant did."""
    f = flat(code_only(code))
    return f.count("auc_ranked(RK[L],same)") >= 2 and "auc(C[L],same)" not in f


check("§2 the reported statistic uses the same estimator as the null, on BOTH paths",
      est_ok(SRC) and "auc_ranked(R[L],sp)" in PERM,
      "observed via one estimator and null via another is a comparison of two things")

# ── §3 the position guard ─────────────────────────────────────────────────────────────────
check("§3 the guard reads the .pos sidecar", '".pos"' in CODE and "pos.index(p)" in REALP,
      "persist-KV reseams: a short row count is normal and says nothing about WHICH positions")
check("§3 every pooled position must be present before the turn is used",
      "ifnotall(pinposforwinwant.values()forpinw)" in REALP,
      "the check is over the positions actually being pooled, not over a count")
check("§3 a turn that cannot prove it is skipped and counted",
      "n_gap+=1" in REALP and "continue" in REALP,
      "the turn must be refused rather than pooled from whatever is at those offsets")

# ── §4 the batched-prefill line ───────────────────────────────────────────────────────────
import argparse as _ap  # noqa: E402

_real_parse = _ap.ArgumentParser.parse_args
_seen = {}


def _capture(self, *a, **k):
    _seen.update({x.dest: x.default for x in self._actions})
    raise SystemExit(0)


_ap.ArgumentParser.parse_args = _capture
try:
    try:
        M["main"]()
    except SystemExit:
        pass
finally:
    _ap.ArgumentParser.parse_args = _real_parse

check("§4 --max-ids defaults under the measured batched-prefill line",
      isinstance(_seen.get("max_ids"), int) and _seen["max_ids"] <= 58,
      "measured 2026-09-19: batched prefill takes over between 62 and 70 ids, and past it no "
      "prompt position reaches the decode tap (default seen: %r)" % (_seen.get("max_ids"),))
check("§4 the default is enforced, not merely declared",
      "iflen(ids)>a.max_ids:" in REALP and "n_long+=1" in REALP,
      "a default with no refusal beside it is a suggestion")

# ── §5 / §6 pooling and scoring ───────────────────────────────────────────────────────────
rng = np.random.default_rng(3)
X = rng.normal(size=(40, 24))
I, J = M["pair_index"](40)

v = M["pool"](np.array([[3.0, 4.0]] * 4), 4)
check("§5 pool() returns a unit vector", abs(float(np.linalg.norm(v)) - 1.0) < 1e-12,
      "norm %.6f — an unnormalised pool makes the cosine a dot product" % np.linalg.norm(v))
check("§6 cos_pairs centres, so a constant offset changes nothing",
      float(np.abs(M["cos_pairs"](X + 50.0, I, J) - M["cos_pairs"](X, I, J)).max()) < 1e-9,
      "at L17 two unrelated sentences sit at cosine 0.805; uncentred scoring reads that")

# ── MUTANTS ───────────────────────────────────────────────────────────────────────────────
def src_leg(code, needle, absent=False):
    f = flat(code_only(code))
    return (needle not in f) if absent else (needle in f)


MUTANTS = [
    ("§1", "perm_null goes back to shuffling the pair vector",
     "        sp = S[np.ix_(p, p)][I, J] >= thr",
     "        sp = rng.permutation(S[I, J] >= thr)",
     lambda code, mod: src_leg(code, "S[np.ix_(p,p)][I,J]")
                       and src_leg(code, "rng.permutation(same)", absent=True)),
    ("§2", "the observed statistic drifts off the null's estimator",
     "            obs = np.array([auc_ranked(RK[L], same) for L in range(30)])",
     "            obs = np.array([auc(C[L], same) for L in range(30)])",
     lambda code, mod: est_ok(code)),
    ("§3", "the guard becomes a row count",
     "        if not all(p in pos for w in want.values() for p in w):",
     "        if (r1 - r0) < n_id:",
     lambda code, mod: src_leg(code, "ifnotall(pinposforwinwant.values()forpinw)")),
    ("§4", "--max-ids is raised past the batched-prefill line",
     '    ap.add_argument("--max-ids", type=int, default=58,',
     '    ap.add_argument("--max-ids", type=int, default=128,',
     lambda code, mod: _default_of(mod, "max_ids") <= 58),
    ("§5", "pool() stops normalising",
     "    return v / n if n > 0 else v",
     "    return v",
     lambda code, mod: abs(float(np.linalg.norm(
         mod["pool"](np.array([[3.0, 4.0]] * 4), 4))) - 1.0) < 1e-12),
    ("§6", "cos_pairs stops centring",
     "    M = M - M.mean(0)",
     "    M = M",
     lambda code, mod: float(np.abs(mod["cos_pairs"](X + 50.0, I, J)
                                    - mod["cos_pairs"](X, I, J)).max()) < 1e-9),
]


def _default_of(mod, dest):
    seen = {}

    def cap(self, *a, **k):
        seen.update({x.dest: x.default for x in self._actions})
        raise SystemExit(0)

    real = _ap.ArgumentParser.parse_args
    _ap.ArgumentParser.parse_args = cap
    try:
        try:
            mod["main"]()
        except SystemExit:
            pass
    finally:
        _ap.ArgumentParser.parse_args = real
    return seen.get(dest, -1)


for leg, what, old, new, still_passes in MUTANTS:
    if SRC.count(old) != 1:
        omit("MUTANT %s %s" % (leg, what),
             "the line it swaps appears %d times in tools/jlens_topic.py, not once"
             % SRC.count(old))
        continue
    mcode = SRC.replace(old, new, 1)
    try:
        mmod = load(mcode)
    except Exception as e:                      # a mutant that will not load proves nothing
        omit("MUTANT %s %s" % (leg, what), "the mutated copy does not load: %s" % e)
        continue
    try:
        passed = bool(still_passes(mcode, mmod))
    except Exception as e:
        passed = False
        _ = e
    check("MUTANT %s %s turns %s red" % (leg, what, leg), not passed,
          "the leg still passed with the fix removed, so it was not testing it")

finish("G-TOPIC-STATS")
