"""G-KAIROS-SCRUB — the public tree carries no one's name, paths, secrets or stores. OFFLINE.

Ships in the Kairos export and runs there; in the source repo it runs against the export
target (KAIROS_TARGET, default ../Kairos) and skips when there is none. The rule it holds
(memory: "scrub before pushing public"): the operator's handle and his companion's inferences
about him come out; everyday facts may stay; nothing under var/, persona/, memory-okf*,
no key files, no absolute machine paths, no source-only profiles.

    python harness_tests/g_kairos_scrub.py
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _gate import check, finish, skip, utf8_stdout  # noqa: E402

utf8_stdout()
ROOT = os.path.dirname(HERE)
# In the source repo this file lives beside the exporter; the TREE under test is the target.
if os.path.exists(os.path.join(ROOT, "kairos-export", "kairos-export.toml")):
    ROOT = os.environ.get("KAIROS_TARGET") or os.path.normpath(os.path.join(ROOT, "..", "Kairos"))
    if not os.path.isdir(ROOT):
        skip("no export target at %s — run tools/kairos_export.py first" % ROOT, "G-KAIROS-SCRUB")

# ── TWO HAND-KEPT COPIES OF ONE TRUTH, AND THAT IS WHY THIS GATE PASSED (2026-08-26) ──
# These were literals. The MANIFEST has a `forbidden` list and the EXPORTER has a TEXT_EXT
# set, and this gate carried its own copy of both — so the thing being checked and the check
# could drift apart, and did:
#
#   * `.java` / `.xml` reached the manifest with the watch agent. Neither list had them, so
#     the exporter copied them RAW and this gate never opened them. The operator's LAN
#     address shipped inside AgentService.java and the verdict was CLEAN.
#   * Two new `forbidden` tokens were added to the manifest the same day and this gate would
#     not have looked for either of them.
#
# So both are READ FROM THE SOURCE OF TRUTH when it is reachable. The literals survive only
# as the fallback for running INSIDE the export, where neither file ships — and the gate
# asserts the two agree whenever it can see both, because a fallback that silently differs
# is the same bug with a longer fuse.
_SRC_ROOT = os.path.dirname(HERE)
_MANIFEST = os.path.join(_SRC_ROOT, "kairos-export", "kairos-export.toml")
_EXPORTER = os.path.join(_SRC_ROOT, "tools", "kairos_export.py")

# ── THE GATE MAY NOT PUBLISH WHAT IT FORBIDS (2026-08-27) ────────────────────────────
# This was a list of LITERALS, and this file is copied RAW into the export
# (`kairos_export.py`: `shutil.copy2` after the scrub, so the rewrite rules never touch
# it). So the one artefact whose job is to keep the operator's handle out of a public repo
# was the artefact publishing it — his handle AND the local-part of his email, on line 48
# of a file anyone can read. Found by cloning the pushed repo and grepping it, which is the
# only check that answers "what is actually public" rather than "what did we intend".
#
# The needles are SHA-256 now. The gate still finds them because it hashes WINDOWS of the
# text rather than searching for a string: for each needle length, hash every window of
# that length beginning at a token boundary and compare digests. That is the same
# detection as `tok in txt` for anything that starts at a word/path boundary — which every
# one of these does — and it names nothing.
#
# A hit reports the needle's INDEX, never its value. If the token really is in a shipped
# file the operator can see which file and line; he does not need this gate to spell it out
# for the reader who got there first.
#
# WHAT THIS DOES NOT CLAIM: a 5-character handle does not survive a determined offline
# attack on its digest, and it is not meant to. The threat is a public file that GitHub
# search, a crawler, or a casual reader indexes in cleartext. That is now closed.
_FALLBACK_H = (
    (5,  "4e38adb6f60ebe297c84fb0b37db558f9639a0f220a55211bcb98583de0d3328"),
    (11, "b094ba63b14c26c1d8063ce290ca9790d221b5bd309dd7d9c615cb6a4f422632"),
    (5,  "3a2edd19fc19ace507806c80db4c02a510e8244e3097f478cb3b99f2aad3e180"),
    (5,  "faf8bc67a416cfe6fa0f297eca4449cb0514ba1afb1d8e9978761cd930c4af41"),
    (9,  "efda066af97a14bd74920d4162c3f6a8dd7d9a6a79a5d06d07aeebd453435201"),
    (10, "3522e4ecde35c9bb08a9814f0bb158ef24e70bb45ed0324e942c913001f87571"),
)
_FALLBACK_FORBIDDEN = []          # kept as a name; the literals are gone on purpose


def _hashed_hits(txt: str) -> list:
    """[(needle_index, line_no)] for every hashed needle present in `txt`.

    Anchored at token starts — a window counts only where the preceding character is not
    alphanumeric — so this is one hash per boundary per distinct needle length rather than
    one per character. Every needle here begins at such a boundary.
    """
    import hashlib
    by_len = {}
    for i, (ln, h) in enumerate(_FALLBACK_H):
        by_len.setdefault(ln, {})[h] = i
    starts = [0] + [i + 1 for i, c in enumerate(txt) if not (c.isalnum() or c == "_")]
    out = []
    for ln, wanted in by_len.items():
        for s in starts:
            if s + ln > len(txt):
                continue
            h = hashlib.sha256(txt[s:s + ln].encode("utf-8")).hexdigest()
            idx = wanted.get(h)
            if idx is not None:
                out.append((idx, txt.count("\n", 0, s) + 1))
    return out
# MIRRORS the exporter's TEXT_EXT, and must: this is what the gate uses when it runs
# INSIDE the export, where neither the manifest nor the exporter ships. A fallback
# that lags is a check that is strictest exactly where nobody can fix it.
_FALLBACK_TEXT = (".bat", ".c", ".cfg", ".cjs", ".conf", ".css", ".csv", ".cu", ".cuh",
                  ".env", ".gitignore", ".gradle", ".h", ".html", ".ini", ".java", ".js",
                  ".json", ".jsonl", ".jsx", ".kt", ".md", ".mjs", ".mts", ".pro",
                  ".properties", ".py", ".rs", ".service", ".sh", ".sql", ".svg", ".toml",
                  ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml")

FORBIDDEN = list(_FALLBACK_FORBIDDEN)
TEXT = tuple(_FALLBACK_TEXT)
_from_source = False
if os.path.exists(_MANIFEST) and os.path.exists(_EXPORTER):
    import io as _io_src
    import re as _re_src
    import tomllib as _toml_src
    _man = _toml_src.load(open(_MANIFEST, "rb"))
    _f = list((_man.get("scrub", {}) or {}).get("forbidden")
              or _man.get("forbidden") or [])
    _m = _re_src.search(r"TEXT_EXT\s*=\s*\{(.*?)\}",
                        _io_src.open(_EXPORTER, encoding="utf-8").read(), _re_src.S)
    _t = sorted(set(_re_src.findall(r'"(\.[a-z0-9]+)"', _m.group(1)))) if _m else []
    if _f and _t:
        # THE MANIFEST IS THE AUTHORITY. Union with the fallback so a token this gate has
        # always looked for cannot be lost by an edit to the manifest.
        FORBIDDEN = sorted(set(_f) | set(_FALLBACK_FORBIDDEN))
        TEXT = tuple(sorted(set(_t) | set(_FALLBACK_TEXT)))
        _from_source = True

print("1. NO FORBIDDEN TOKEN SURVIVES IN ANY TEXT FILE")
hits = []
n_files = 0
for dp, dns, fns in os.walk(ROOT):
    # var/ and persona/ are the tree's LOCAL state (gitignored there; never exported) — the
    # running companion's token and registry live in them by design
    dns[:] = [d for d in dns if d not in (".git", "node_modules", "__pycache__", "var", "persona")]
    for fn in fns:
        if not fn.endswith(TEXT) and fn != ".gitignore":
            continue
        p = os.path.join(dp, fn)
        n_files += 1
        try:
            txt = open(p, encoding="utf-8").read()
        except UnicodeDecodeError:
            continue
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        if rel == "harness_tests/g_kairos_scrub.py":
            continue                                  # this file names the tokens it forbids
        for tok in FORBIDDEN:
            if tok in txt:
                ln = next((i for i, l in enumerate(txt.splitlines(), 1) if tok in l), 0)
                hits.append("%s:%d  %s" % (rel, ln, tok))
        # ...and the hashed needles, which are the only ones available inside the export.
        # Reported by INDEX: a gate that prints the token it caught re-publishes it in CI
        # logs, which is the same leak one layer out.
        for idx, ln in _hashed_hits(txt):
            hits.append("%s:%d  <identity needle #%d>" % (rel, ln, idx))
check("%d text files scanned, zero forbidden tokens" % n_files, not hits, hits[:12])

print("\n2. NOTHING OF HERS OR HIS IS IN THE TREE")
# "in the export" means TRACKED (or present, when the tree has no git yet): a running companion
# makes its own var/ and persona/ beside the code, and those are gitignored there by design.
def _tracked():
    try:
        import subprocess
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True)
        if out.returncode == 0 and os.path.isdir(os.path.join(ROOT, ".git")):
            return {p.decode("utf-8", "replace") for p in out.stdout.split(b"\x00") if p}
    except Exception:
        pass
    return None
_T = _tracked()
for d in ("var", "persona", "memory-okf", "memory-okf-personality", "_task_state", "engine", "core", "papers"):
    if _T is not None:
        check("no %s/ in the export (tracked)" % d, not any(p.startswith(d + "/") for p in _T))
    else:
        check("no %s/ in the export" % d, not os.path.isdir(os.path.join(ROOT, d)))
bad_profiles = [f for f in os.listdir(os.path.join(ROOT, "profiles")) if f.startswith("agent")] \
    if os.path.isdir(os.path.join(ROOT, "profiles")) else []
check("no source-only profiles (agent*.toml)", not bad_profiles, bad_profiles)
check("profiles/companion.toml ships", os.path.exists(os.path.join(ROOT, "profiles", "companion.toml")))
keyish = []
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if d not in (".git", "node_modules", "var", "persona")]
    for fn in fns:
        if fn.endswith((".py", ".md", ".jsx", ".js")):
            continue                                  # code and docs may be ABOUT secrets
        if re.search(r"(secret|token|\.env$|api[_-]?key|\.pem$|\.key$)", fn, re.I):
            keyish.append(os.path.relpath(os.path.join(dp, fn), ROOT))
check("no key/secret-shaped files", not keyish, keyish)
check("persona-template/ ships and persona/ is gitignored",
      os.path.isdir(os.path.join(ROOT, "persona-template"))
      and "persona/" in open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read())
check("KAIROS-SOURCE.txt names the source commit",
      os.path.exists(os.path.join(ROOT, "KAIROS-SOURCE.txt"))
      and "exported from" in open(os.path.join(ROOT, "KAIROS-SOURCE.txt"), encoding="utf-8").read())
check("LICENSE and README ship", os.path.exists(os.path.join(ROOT, "LICENSE")) and os.path.exists(os.path.join(ROOT, "README.md")))
if _T is not None:
    # The first fresh clone (2026-08-21) had NO harness/**/__init__.py and no harness_tests/_gate.py:
    # the overlay .gitignore carried an unanchored `_*.py`. A tree that imports by accident
    # (namespace packages) is one refactor away from not importing at all.
    _inits = [p for p in _T if p.startswith("harness/") and p.endswith("/__init__.py")]
    check("harness/**/__init__.py are TRACKED (%d)" % len(_inits), len(_inits) >= 10, len(_inits))
    check("harness_tests/_gate.py is TRACKED", "harness_tests/_gate.py" in _T)

# ── THE CHECK THAT WOULD HAVE CAUGHT IT ─────────────────────────────────────────────
# Not "is the output clean" — that was already asserted and was already passing over bytes
# nobody read. This asserts COVERAGE: the lists this gate uses come from the files that
# actually drive the export, and every text extension in the shipped tree is one of them.
check("the forbidden list and the text extensions come from the SOURCE OF TRUTH, "
      "not a second copy", _from_source or not os.path.exists(_MANIFEST),
      "manifest=%s exporter=%s" % (os.path.exists(_MANIFEST), os.path.exists(_EXPORTER)))
_BINARY = {".png", ".jpg", ".jpeg", ".webp", ".webm", ".mp4", ".ico", ".ttf", ".woff",
           ".woff2", ".gguf", ".bin", ".npz", ".pyc", ".keystore", ".apk", ".dex", ".jar",
           ".lock", ".gz", ".zip", ".pdf", ".wav", ".mp3", ".onnx", ".safetensors", ".map"}
_unscanned = set()
for _b2, _d2, _f2 in os.walk(ROOT):
    # THE WIPE SPARES .git / var / persona / node_modules -- those are the TARGET's own
    # local state, not bytes this export shipped. Walking them reported the target's own
    # gateway.log and engine.token as export problems: the check pointing at the wrong
    # tree, which is the class of mistake it was written to catch.
    if any((os.sep + x) in _b2 or _b2.endswith(os.sep + x)
           for x in (".git", "var", "persona", "node_modules", "__pycache__")):
        continue
    for _n2 in _f2:
        _e2 = os.path.splitext(_n2)[1].lower()
        if _e2 and _e2 not in TEXT and _e2 not in _BINARY:
            _unscanned.add(_e2)
check("every text extension IN THE SHIPPED TREE is one this scan opens",
      not _unscanned, sorted(_unscanned)[:12])

finish("G-KAIROS-SCRUB")
