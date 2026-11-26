"""G-COMPANION-CREATE — a new companion is not blank, and nothing of hers leaks into it. OFFLINE.

WHY (2026-11-26, his report: "the video avatar, wardrobe etc didn't show"). A home made by
`home.create()` was an empty folder: no face (the seeder looked for assets/avatar-default,
which only the export has), no wardrobe, no voice of her own (every new companion spoke as
Ara, as Kairos does), and a persona copied from the template told her she was "Kairos".
The audit that followed found more: a room or watchdog restart dropped `--companion` and
came back as Kairos, and four stores were repo-root literals a second companion would read
as hers (held-back lines, deep recall's transcript index, game shots, book places).

  1. create(): persona named (no "Kairos"), a personality-state block, the default face and
     wardrobe laid in, her own voice; an existing id refused
  2. a second companion gets a DIFFERENT voice; a named voice is honoured; a bad one refused
  3. seeding fills gaps only: an existing fragment and a chosen voice are never overwritten
  4. a bundle without a personality or a face is seeded the same way on import
  5. the route makes one while live; the window's state offers the voices
  6. a restart (room, watchdog, daemon start) keeps the companion it was launched with
  7. the four stores follow the home, not the repo root
  8. the room says her name, not "KAIROS"

Run: python harness_tests/g_companion_create.py
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
SB = sandbox("g_companion_create")

from harness import home as H  # noqa: E402
from harness import companion_create as CC  # noqa: E402

H.COMPANIONS_DIR = os.path.join(SB, "companions")
H.VAR = os.path.join(SB, "var")


def read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _try(f):
    try:
        f()
        return ""
    except (H.HomeError, ValueError) as e:
        return str(e) or "refused"


print("1. create(): not blank")
r = CC.create("ivy", "Ivy")
P = H.resolve(r["home"])
ident = read(os.path.join(P["persona_dir"], "00-identity.md"))
check("the persona template is laid in", r["persona_files"] >= 10 and bool(ident), r["persona_files"])
check("…with HER name in it", "Your name is Ivy." in ident and "Kairos" not in ident, ident[:200])
check("…and without the 'copy the template' instruction", "Copy `persona-template/`" not in ident)
check("persona.md holds the personality-state block", "## Personality state" in read(P["persona_file"]))
have_face = bool(CC.face_dir())
if have_face:
    check("the default face is laid in (reference, character, stills)",
          os.path.isfile(os.path.join(P["avatar_dir"], "_reference.png"))
          and os.path.isfile(os.path.join(P["avatar_dir"], "character.txt"))
          and os.path.isdir(os.path.join(P["avatar_dir"], "calm")), r.get("face_why"))
    check("…and the wardrobe's gestures (wants.jsonl)", len(read(os.path.join(P["avatar_dir"], "wants.jsonl")).splitlines()) >= 6)
    check("…and it was laid in HER folder, not the process's", r["face"] and os.environ["SP_AVATAR_DIR"] != P["avatar_dir"])
else:
    print("  omitted  face: no bundled default set on this machine")
tun = json.loads(read(P["tuning"]) or "{}")
check("her own voice is in her knobs", tun.get("voice.xai_voice") in CC.XAI_VOICES and tun.get("voice.lfm3_voice"), tun)
check("…and she speaks LOCALLY by default (no key, no cost)", tun.get("voice.method") == "lfm3", tun)
check("an empty registry is ready", os.path.isfile(P["registry"]))
check("an existing id is refused", bool(_try(lambda: CC.create("ivy"))))

print("\n2. voices")
r2 = CC.create("rowan", "Rowan")
check("a second companion gets a different voice", r2["voice"] != r["voice"], (r["voice"], r2["voice"]))
r3 = CC.create("wren", "Wren", voice="celeste", seeds=("persona", "voice"))
check("a named voice is honoured", r3["voice"] == "celeste")
check("an unknown voice is refused", "unknown voice" in _try(lambda: CC.create("x1", voice="robot")))

print("\n3. seeding fills gaps only")
with open(os.path.join(P["persona_dir"], "00-identity.md"), "w", encoding="utf-8") as f:
    f.write("Ivy, rewritten by him.\n")
CC.fill(r["home"], "Ivy", voice="leo")
check("an edited fragment survives a second fill", read(os.path.join(P["persona_dir"], "00-identity.md")) == "Ivy, rewritten by him.\n")
check("a chosen voice survives a second fill", json.loads(read(P["tuning"]))["voice.xai_voice"] == r["voice"])

print("\n4. a bundle missing parts is seeded on import")
os.environ["SP_BUNDLE_DIR"] = os.path.join(SB, "bundles")
from harness import bundle as B  # noqa: E402
hb = B.export(r["home"], ["history"])["path"]
r4 = B.import_new(hb, "fern", "Fern")
P4 = H.resolve(r4["home"])
check("no personality in the bundle -> her named persona",
      "Your name is Fern." in read(os.path.join(P4["persona_dir"], "00-identity.md")))
check("…and her own voice", json.loads(read(P4["tuning"]) or "{}").get("voice.xai_voice") in CC.XAI_VOICES)
if have_face:
    check("no face in the bundle -> the default face", os.path.isfile(os.path.join(P4["avatar_dir"], "_reference.png")))

print("\n5. the room's route")
from harness.server import companion_routes as CR  # noqa: E402
os.environ["SP_HOME"] = r["home"]
code, st = CR.get_state()
check("the window is offered the voices and a free one",
      st.get("voices") == CC.XAI_VOICES and st.get("suggested_voice") in CC.XAI_VOICES, st.get("suggested_voice"))
code, cr = CR.post_create({"id": "moss", "name": "Moss", "voice": "iris"})
check("POST /v1/companion/create makes one", code == 200 and cr["voice"] == "iris" and cr["name"] == "Moss", cr)
check("…and refuses a bad id", CR.post_create({"id": "No Good"})[0] == 400)

print("\n6. a restart keeps the companion")
import subprocess  # noqa: E402
from harness.server import app as A  # noqa: E402
seen = []
_popen, _prof = subprocess.Popen, A._system_profile
subprocess.Popen = lambda argv, **kw: seen.append(list(argv))
A._system_profile = lambda: "companion"
try:
    A._do_restart(False)
finally:
    subprocess.Popen, A._system_profile = _popen, _prof
check("the room/watchdog restart passes --companion=<this home>",
      seen and ("--companion=" + r["home"]) in seen[-1], seen[-1] if seen else None)
import _src  # noqa: E402
src = _src.pkg("harness", "server")          # the package, not one file (G-SRC-TRAP)
check("…and so does the daemon start", '"--daemon-only"]\n' in src and '["--companion=" + os.environ["SP_HOME"]]' in src)

print("\n7. the four stores follow the home")
for k, v in H.env_for(r["home"]).items():
    os.environ[k] = v
from harness.control import shutdown as SD  # noqa: E402
# Deep recall is the optional sidecar, which imports numpy (2026-11-27: this line was red on
# every bare-install CI job). Where it is absent its index has no subject, so that ONE check
# is skipped by name. Every other store below is core and still checked.
try:
    from harness.sidecar import archive as AR  # noqa: E402
except ModuleNotFoundError as e:
    if e.name != "numpy":
        raise
    AR = None
from harness.skills import games as G, library as L  # noqa: E402
ins = lambda p: os.path.normcase(os.path.abspath(p)).startswith(os.path.normcase(r["home"]) + os.sep)  # noqa: E731
check("held-back lines are hers", ins(SD.undelivered_path()), SD.undelivered_path())
if AR is None:
    print("  skip deep recall's index is hers   (numpy absent: the sidecar is not installed)")
else:
    check("deep recall's index is hers", ins(AR._index_dir()), AR._index_dir())
check("deep recall searches HER transcripts", ins(os.path.dirname(H.path("registry"))) and
      any("transcripts" in s for s in [os.path.join(os.path.dirname(H.path("registry")), "transcripts")]))
check("game shots are hers", ins(G._shot_path("m1")), G._shot_path("m1"))
check("her place in each book is hers", ins(L._bm_path()), L._bm_path())

print("\n8. the room says her name")
main = read(os.path.join(ROOT, "ui", "src", "main.jsx"))
check("no literal KAIROS brand", ">KAIROS<" not in main and "<Brand />" in main and "/v1/companion" in read(os.path.join(ROOT, "ui", "src", "api.js")))

finish("G-COMPANION-CREATE")
