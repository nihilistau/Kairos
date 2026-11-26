"""G-BUNDLE — export, import, reset and undo move a companion as a unit, and delete nothing.
OFFLINE. (design docs/DESIGN-2026-11-26-homes-people-setup.md §3; harness/bundle.py)

  1. export: the chosen parts, every file checksummed, episodes and face left out by default
  2. inspect refuses what it cannot trust (not a zip, no manifest, an escaping name, a
     tampered file, an unknown store)
  3. import as a NEW companion: everything lands in the new home; no personality -> template
  4. reset history: a before-bundle, the old moved to archive/<ts>, a blank registry, the
     personality and the episodes untouched
  5. undo puts it back exactly; the blank goes to archive/<ts>-undo
  6. load a personality from another companion's bundle; history untouched
  7. a LIVE home is never changed: refused, scheduled, kept while live, applied when not
  8. NOTHING IS DELETED: every file content that ever existed in the home is still on disk
  9. her adopted home: a reset would never take her episodes, face, or another part's store

Run: python harness_tests/g_bundle.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_bundle")
os.environ["SP_BUNDLE_DIR"] = os.path.join(SB, "bundles")

from harness import bundle as B  # noqa: E402
from harness import home as H  # noqa: E402

H.COMPANIONS_DIR = os.path.join(SB, "companions")
H.VAR = os.path.join(SB, "var")


def _try(f):
    try:
        f()
        return ""
    except (B.BundleError, H.HomeError) as e:
        return str(e) or "refused"


def write(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def read(p):
    """'' for a missing file, so a store that VANISHED fails its check by name instead of
    taking the gate down with a traceback (the delete-instead-of-move mutant did exactly that)."""
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def contents(root):
    out = set()
    for dp, dn, fn in os.walk(root):
        for f in fn:
            with open(os.path.join(dp, f), "rb") as fh:
                out.add(hashlib.sha256(fh.read()).hexdigest())
    return out


ivy = H.create("ivy", "Ivy")
P = H.resolve(ivy)
write(P["persona_file"], "Ivy is wry.\n\n## Personality state\nmood: calm\n")
write(os.path.join(P["persona_dir"], "00-identity.md"), "I am Ivy.\n")
write(P["registry"], '{"name":"a","text":"Robin likes tea"}\n')
write(os.path.join(os.path.dirname(P["registry"]), "speech.jsonl"), '{"said":"hello"}\n')
write(os.path.join(P["personality_okf"], "full", "j.md"), "a journal line\n")
write(P["tuning"], '{"voice.enabled": true}\n')
write(os.path.join(P["eps_dir"], "ep1", "k.bin"), "kv")
write(os.path.join(P["avatar_dir"], "look.png"), "png")
seen = contents(ivy)

print("1. export")
r = B.export(ivy)
check("a bundle is written to the bundle folder", os.path.isfile(r["path"])
      and r["path"].startswith(os.environ["SP_BUNDLE_DIR"]) and r["name"].endswith(".kairos"), r)
man = B.inspect(r["path"])
arcs = set(man["files"])
check("personality and history by default", man["parts"] == ["personality", "history"], man["parts"])
check("the persona, registry, speech, journal and knobs are in it",
      {"files/persona_file/persona.md", "files/registry/registry.jsonl", "files/registry/speech.jsonl",
       "files/personality_okf/full/j.md", "files/tuning/tuning.json",
       "files/persona_dir/00-identity.md"} <= arcs, sorted(arcs))
check("the episodes and the face are not", not any("ep1" in a or "look.png" in a for a in arcs))
check("every file carries a sha256", all(len(v) == 64 for v in man["files"].values()))
check("the companion is named", man["companion"] == {"id": "ivy", "name": "Ivy"})
check("no part chosen is refused", bool(_try(lambda: B.export(ivy, []))))
# --out into a folder that does not exist yet (found 2026-11-26 bundling her into a fresh
# install: the .part file's open() died on the missing folder)
_new = os.path.join(SB, "not-yet", "made", "x.kairos")
try:
    B.export(ivy, ["personality"], out=_new)
    _err = ""
except Exception as e:      # the defect was an OSError, which _try does not catch
    _err = repr(e)
check("export --out makes its folder", not _err and os.path.isfile(_new), _err)

print("\n2. inspect refuses what it cannot trust")
bad = os.path.join(SB, "bad.kairos")
write(bad, "not a zip")
check("not a zip", "not a zip" in _try(lambda: B.inspect(bad)))
with zipfile.ZipFile(bad, "w") as z:
    z.writestr("files/registry/registry.jsonl", "x")
check("no manifest", "manifest" in _try(lambda: B.inspect(bad)))
for entry, why in (("files/registry/../../evil.txt", "an escaping name"),
                   ("files/nosuchstore/a.txt", "an unknown store"),
                   ("/abs.txt", "an absolute name")):
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr(entry, "x")
        z.writestr(B.MANIFEST, json.dumps({"kairos_bundle": 1, "parts": ["history"], "units": {},
                                           "files": {entry: hashlib.sha256(b"x").hexdigest()},
                                           "companion": {"id": "x", "name": "x"}, "created": ""}))
    check("refused: " + why, "unsafe" in _try(lambda: B.inspect(bad)))
tam = os.path.join(SB, "tampered.kairos")
with zipfile.ZipFile(r["path"]) as zi, zipfile.ZipFile(tam, "w") as zo:
    for n in zi.namelist():
        zo.writestr(n, b"changed" if n == "files/registry/registry.jsonl" else zi.read(n))
check("a tampered file fails its checksum", "checksum" in _try(lambda: B.inspect(tam)))

print("\n3. import as a new companion")
res = B.import_new(r["path"], "ivy2", "Ivy Two")
P2 = H.resolve(res["home"])
check("the registry landed in the new home", read(P2["registry"]) == read(P["registry"]))
check("…and the speech log beside it", os.path.isfile(os.path.join(os.path.dirname(P2["registry"]), "speech.jsonl")))
check("…and the persona and journal", read(P2["persona_file"]) == read(P["persona_file"])
      and os.path.isfile(os.path.join(P2["personality_okf"], "full", "j.md")))
check("it is called what you said", H.read(res["home"])["companion"]["name"] == "Ivy Two")
check("an existing id is refused (never overwritten)", bool(_try(lambda: B.import_new(r["path"], "ivy"))))
hist_only = B.export(ivy, ["history"])["path"]
r3 = B.import_new(hist_only, "ivy3")
check("a history-only bundle gets the persona template, so she has a voice",
      len(os.listdir(H.resolve(r3["home"])["persona_dir"])) > 0 or not B._template(),
      os.listdir(H.resolve(r3["home"])["persona_dir"]))

print("\n4. reset history")
reg_before = read(P["registry"])
rr = B.reset(ivy, ["history"])
check("a before-bundle was written", os.path.isfile(os.path.join(os.environ["SP_BUNDLE_DIR"], rr["before"])), rr)
check("the old registry is in archive/<ts>", read(os.path.join(ivy, "archive", rr["ts"], "registry",
                                                                 "registry.jsonl")) == reg_before)
check("a blank registry is in place", os.path.isfile(P["registry"]) and read(P["registry"]) == "")
check("the personality is untouched", read(P["persona_file"]).startswith("Ivy is wry")
      and os.path.isfile(os.path.join(P["personality_okf"], "full", "j.md")))
check("the episodes are untouched", os.path.isfile(os.path.join(P["eps_dir"], "ep1", "k.bin")))
check("the journal records it", B.history(ivy)[-1]["op"] == "reset")

print("\n5. undo")
write(P["registry"], '{"name":"b","text":"after the reset"}\n')
ru = B.undo(ivy)
check("the registry is back, byte for byte", read(P["registry"]) == reg_before)
check("what was there since went to archive/<ts>-undo",
      "after the reset" in read(os.path.join(ivy, "archive", ru["ts"] + "-undo", "registry", "registry.jsonl")))
check("a second undo has nothing to undo", "nothing to undo" in _try(lambda: B.undo(ivy)))

print("\n6. load a personality from another companion")
other = H.create("rowan", "Rowan")
PO = H.resolve(other)
write(PO["persona_file"], "Rowan is earnest.\n")
ob = B.export(other, ["personality"])["path"]
rl = B.replace(ivy, ob, ["personality"])
check("her persona is now Rowan's", read(P["persona_file"]).startswith("Rowan is earnest"))
check("her own is in the archive", read(os.path.join(ivy, "archive", rl["ts"], "persona_file",
                                                     "persona.md")).startswith("Ivy is wry"))
check("her history is untouched", read(P["registry"]) == reg_before)
check("a part the bundle lacks is refused", "no history" in _try(lambda: B.replace(ivy, ob, ["history"])))

print("\n7. a LIVE home is never changed")
H.claim_live(ivy)
check("the marker says live (this process)", H.is_live(ivy))
check("reset is refused while live", "running" in _try(lambda: B.reset(ivy, ["history"])))
B.schedule(ivy, "reset", ["history"])
check("…so the room schedules it", B.pending(ivy)["op"] == "reset")
kept = B.apply_pending(ivy)
check("apply while still live keeps it pending, not failed", kept and kept.get("kept") and B.pending(ivy))
os.remove(os.path.join(ivy, H.LIVE))
done = B.apply_pending(ivy)
check("…and applies it once she is down", done and done.get("ok") and B.pending(ivy) is None, done)
with open(os.path.join(ivy, H.LIVE), "w") as f:
    json.dump({"pid": 999999}, f)
check("a stale marker (dead pid) is not live", not H.is_live(ivy))
B.schedule(ivy, "load", ["history"], bundle=ob)          # rowan's bundle has no history
fail = B.apply_pending(ivy)
check("a failing scheduled op is reported and kept as pending.failed",
      fail and not fail.get("ok") and any(f.startswith("pending.failed-") for f in os.listdir(ivy)), fail)
check("schedule refuses a bundle path outside the folder", bool(_try(lambda: B.resolve_name("../x.kairos"))))

print("\n8. NOTHING IS DELETED")
now = contents(ivy)
check("every file content the home ever had is still on disk", seen <= now, len(seen - now))

print("\n9. her adopted home: what a reset would take")
her = H.home_dir("kairos")
if os.path.isfile(os.path.join(ROOT, "companions", "kairos", "companion.toml")):
    H.COMPANIONS_DIR = os.path.join(ROOT, "companions")
    hp = H.resolve(H.home_dir("kairos"))
    us = B.units(hp, ["personality", "history"])
    taken = [p for _k, _pt, _kd, p in us]
    check("never her episodes", not any(os.path.normcase(p).startswith(os.path.normcase(hp["eps_dir"])) for p in taken))
    check("never her face", not any(os.path.normcase(p) == os.path.normcase(hp["avatar_dir"]) for p in taken))
    prot = B._protected(hp, ["personality", "history"])
    check("her episodes and face are protected inside any folder a reset walks",
          os.path.normcase(os.path.normpath(hp["eps_dir"])) in prot
          and os.path.normcase(os.path.normpath(hp["avatar_dir"])) in prot)
    check("the registry's folder is the history unit (speech, transcripts, journal travel with it)",
          os.path.normcase(os.path.dirname(hp["registry"])) in [os.path.normcase(p) for p in taken])
else:
    print("  omitted  §9: her home is not in this tree (the public export)")

print("\n10. the room's routes (harness/server/companion_routes.py)")
H.COMPANIONS_DIR = os.path.join(SB, "companions")
from harness.server import companion_routes as CR  # noqa: E402
os.environ["SP_HOME"] = ivy
for k, v in H.env_for(ivy).items():
    os.environ[k] = v
H.claim_live(ivy)                                        # as the gateway does
code, st = CR.get_state()
check("GET names the companion and lists it as this one",
      st["current"]["id"] == "ivy" and any(h["current"] for h in st["homes"]), st["current"])
code, ex = CR.post_export({"parts": ["personality"]})
check("export runs live (it only reads)", code == 200 and ex["parts"] == ["personality"], ex)
write(P["registry"], '{"name":"c","text":"live row"}\n')
_live_reg = read(P["registry"])
code, sc = CR.post_schedule({"op": "reset", "parts": ["history"]})
check("reset from the room is SCHEDULED, never run on the live home",
      code == 200 and B.pending(ivy)["op"] == "reset", sc)
check("…and the registry is untouched until then", read(P["registry"]) == _live_reg)
CR.post_cancel({})
check("cancel keeps the request on disk", B.pending(ivy) is None
      and any(f.startswith("pending.cancelled-") for f in os.listdir(ivy)))
code, sc = CR.post_schedule({"op": "load", "bundle": "../../etc/passwd.kairos", "parts": ["history"]})
check("a bundle path outside the bundle folder is refused", code == 400, sc)
code, dl = 0, CR.bundle_path("..\\x.kairos")
check("the download refuses a path, not a name", dl == "")
check("…and serves a bundle it holds", CR.bundle_path(ex["name"]) == ex["path"])
junk = b"not a bundle"
code, up = CR.upload("junk.kairos", len(junk), __import__("io").BytesIO(junk).read)
check("an upload that is not a bundle is refused and kept as .rejected",
      code == 400 and os.path.isfile(os.path.join(os.environ["SP_BUNDLE_DIR"], "junk.kairos.rejected")), up)
with open(ex["path"], "rb") as f:
    good = f.read()
code, up = CR.upload("copy.kairos", len(good), __import__("io").BytesIO(good).read)
check("a real bundle uploads and is checked", code == 200 and up["parts"] == ["personality"], up)
code, nw = CR.post_new({"bundle": "copy.kairos", "id": "fern", "name": "Fern"})
check("a new companion from the room, while live", code == 200 and nw["id"] == "fern", nw)
code, nw = CR.post_new({"bundle": "copy.kairos", "id": "Bad Id"})
check("…with a bad id refused", code == 400)
os.remove(os.path.join(ivy, H.LIVE))

finish("G-BUNDLE")
