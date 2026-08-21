"""G-ROOM-BUNDLE — the committed room IS the source. OFFLINE (skip 2 without npm).

THE HOLE (2026-08-21 audit): console/room/ is a Vite build of ui/src, committed so the
gateway can serve it with no Node at runtime — and nothing ever verified that the two
agree. A source edit without a rebuild ships silently; `emptyOutDir: true` means a rebuild
also rewrites console/room/index.html. This builds ui/src into a scratch directory and
compares the emitted JS/CSS BYTES with what is committed (names are content-hashed and
may differ only if content differs, so bytes are the honest comparison).

    python harness_tests/g_room_bundle.py
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate import check, finish, skip, utf8_stdout  # noqa: E402

utf8_stdout()
UI = os.path.join(ROOT, "ui")
COMMITTED = os.path.join(ROOT, "console", "room", "assets")
npm = shutil.which("npm") or shutil.which("npm.cmd")
if not npm:
    skip("npm is not on PATH — the bundle cannot be rebuilt here", "G-ROOM-BUNDLE")
if not os.path.isdir(os.path.join(UI, "node_modules")):
    r = subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=UI, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        skip("npm ci failed: %s" % (r.stderr or r.stdout)[-300:], "G-ROOM-BUNDLE")

print("1. A FRESH BUILD OF ui/src MATCHES THE COMMITTED console/room/assets, BYTE FOR BYTE")
out = tempfile.mkdtemp(prefix="g-room-bundle-")
r = subprocess.run([npm, "run", "build", "--", "--outDir", out, "--emptyOutDir"],
                   cwd=UI, capture_output=True, text=True, timeout=600)
check("vite build succeeds", r.returncode == 0, (r.stderr or r.stdout)[-300:])
built = sorted(glob.glob(os.path.join(out, "assets", "*")))
committed = sorted(glob.glob(os.path.join(COMMITTED, "*")))
check("the build emits exactly one js and one css (the gateway serves one subdir deep)",
      len([b for b in built if b.endswith(".js")]) == 1 and len([b for b in built if b.endswith(".css")]) == 1,
      [os.path.basename(b) for b in built])

def _by_ext(paths):
    d = {}
    for p in paths:
        d.setdefault(os.path.splitext(p)[1], []).append(p)
    return d

B, C = _by_ext(built), _by_ext(committed)
for ext in (".js", ".css"):
    bb = open(B[ext][0], "rb").read() if B.get(ext) else b""
    cc = open(C[ext][0], "rb").read() if C.get(ext) else b""
    check("committed %s == built %s (%d bytes)" % (ext, ext, len(bb)), bb == cc and bb,
          "committed=%s built=%s" % ([os.path.basename(x) for x in C.get(ext, [])],
                                     [os.path.basename(x) for x in B.get(ext, [])]))
idx_built = open(os.path.join(out, "index.html"), encoding="utf-8").read() if os.path.exists(os.path.join(out, "index.html")) else ""
idx_comm = open(os.path.join(ROOT, "console", "room", "index.html"), encoding="utf-8").read()
check("console/room/index.html names the committed assets",
      all(os.path.basename(c) in idx_comm for c in committed), [os.path.basename(c) for c in committed])
shutil.rmtree(out, ignore_errors=True)
finish("G-ROOM-BUNDLE")
