"""G-PROFILE-KEYS — every profile key has a reader, or a recorded reason. OFFLINE.

THE CLAIM (2026-08-24 audit, S3 — the SP_AVATAR_DEFAULTS shape, made structural).
`serve.py` is THE one door: a knob not mapped in `build_env` does not exist. G-ONEDOOR
holds that at the ENV-VARIABLE layer — and nothing held the PROFILE-KEY layer, so a key
could sit in a profiles/*.toml looking exactly like configuration while serve.py never
read it. Found live, all in `companion.toml` — the PUBLIC framework's profile, the one
a newcomer edits first: `agent.tool_budget_s = 400` (inert; the tuning registry owned
the real budget) and the three decode dials `temperature` / `max_tokens` /
`repetition_penalty` (inert; the registry owns decode defaults per turn). A profile key
nothing reads is a promise the file cannot keep.

THE RULE: every leaf key in every profiles/*.toml appears as a quoted string in
serve.py (the explicit table means every consumed key is spelled there), OR carries a
row in INERT_ALLOWED below with a dated reason — a recorded decision, not a drift, the
OFF-BY-DEFAULT doctrine applied to schema.

Mutant (in-gate): the scanner is fed a synthetic profile with a bogus key and must
convict it — a conservation gate that cannot see a planted violation is scanning
nothing.
"""
from __future__ import annotations

import glob
import io
import os
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Keys that exist in profiles and are DELIBERATELY unread, each with its reason.
# Adding a key here is a decision with a date; adding one to a profile without a
# reader and without a row here is a red.
INERT_ALLOWED = {
    # Every profile names the tokenizer beside the model; the engine derives it from
    # SP_MODEL_PATH and serve.py never mapped this. Kept as documentation of which
    # tokenizer a profile pairs with — recorded 2026-08-24 rather than deleted from
    # fifteen files in one sweep; delete profile-by-profile as each is next touched.
    "paths.tokenizer",
    # The MTP/speculative-drafter flag predates the SP_EAGLE_* knobs that actually
    # gate that machinery (OFF-BY-DEFAULT §8: measured-against). Same recording,
    # same deletion plan as paths.tokenizer.
    "decode.mtp",
}


def leaf_keys(cfg: dict) -> list:
    out = []
    for sect, tbl in cfg.items():
        if not isinstance(tbl, dict):
            out.append(sect)
            continue
        for k, v in tbl.items():
            if isinstance(v, dict):
                out.extend("%s.%s.%s" % (sect, k, k2) for k2 in v)
            else:
                out.append("%s.%s" % (sect, k))
    return out


def unread(cfg: dict, serve_src: str) -> list:
    bad = []
    for dotted in leaf_keys(cfg):
        if dotted in INERT_ALLOWED:
            continue
        k = dotted.rsplit(".", 1)[-1]
        if ('"%s"' % k) not in serve_src and ("'%s'" % k) not in serve_src:
            bad.append(dotted)
    return bad


serve_src = io.open(os.path.join(ROOT, "serve.py"), encoding="utf-8").read()

profiles = sorted(glob.glob(os.path.join(ROOT, "profiles", "*.toml")))
# ONE PROFILE IS A TREE TOO (2026-08-25). This read `>= 10` — true of the source tree's
# fifteen and false of the Kairos export, which ships exactly one (`companion.toml`, the
# very file whose four inert keys this gate was written for). Found by running the suite
# inside the export. The claim is per-profile; the count only has to be non-zero.
check("there are profiles to hold", len(profiles) >= 1, profiles)
for p in profiles:
    with open(p, "rb") as f:
        cfg = tomllib.load(f)
    bad = unread(cfg, serve_src)
    check("%s: every key has a reader or a recorded reason" % os.path.basename(p),
          not bad, bad)

# ...and the same lesson on the allowlist: it names keys of the ENGINE profiles, which
# the export does not carry. A row with no key anywhere is drift HERE; in a tree that
# ships one profile it is simply not that tree's business.
_live = {a for a in INERT_ALLOWED
         if any(a in leaf_keys(tomllib.load(open(p, "rb"))) for p in profiles)}
_orphans = sorted(INERT_ALLOWED - _live) if len(profiles) > 1 else []
check("the allowlist only names keys that still exist (a row outliving its key is "
      "the drift in the other direction)", not _orphans, _orphans)

# ── §mutant: the scanner convicts a planted violation ──────────────────────────────
planted = unread({"agent": {"a_key_serve_never_read": 1}}, serve_src)
check("mutant(planted key): the scan convicts it by dotted name",
      planted == ["agent.a_key_serve_never_read"], planted)

finish("G-PROFILE-KEYS")
