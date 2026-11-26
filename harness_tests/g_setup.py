"""G-SETUP — the setup centre suggests what fits, fetches only what it planned, runs nothing
unapproved, and writes a profile serve.py can start. OFFLINE (the catalogues are faked at
their owner modules; nothing touches the network). (harness/setup/, design §4)

  1. the kits: every model names a repo, patterns and a known licence; uncensored models are
     flagged and the warning exists; every engine has assets or is external
  2. suggest(): what this card and memory can run
  3. plan(): the model file (never the vision projector or the draft), plus mmproj / draft /
     engine; sizes against free space; the licence; the warning only when uncensored
  4. start(): refused without the licence, without room, and while a job runs; the files land
     where planned; the engine zip is extracted safely
  5. approval: the engine executable is pending until approved BY HASH; a bad hash refused
  6. the profile: refuses an existing name and a bad one; the companion profile with the
     engine set — kind openai, base_url, `[engine] command` naming the approved exe and the
     model — and with a home, no registry; serve.build_env takes it
  7. convert: refused without a transcoder, and with an unapproved one
  8. the routes: a relative folder refused; start needs a plan; the profile needs approval
  9. serve.py: an `[engine] command` whose exe is missing says so and does not start

Run: python harness_tests/g_setup.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import tomllib
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_setup")
os.environ["SP_DAEMON_URL"] = "http://127.0.0.1:9"

from harness.setup import installer as I  # noqa: E402

I.STATE = os.path.join(SB, "setup.json")
DEST = os.path.join(SB, "data")
os.makedirs(DEST)


def _err(f, kind=I.SetupError):
    try:
        f()
        return ""
    except kind as e:
        return str(e) or "refused"


print("1. the kits")
K = I.kits()
check("every model names a repo, model patterns and a known licence",
      all(m["repo"] and m["model"] and m["licence"] in K["licences"] for m in K["models"]))
check("the uncensored ones are flagged, and the warning says so plainly",
      [m["id"] for m in K["models"] if m.get("uncensored")] == ["g4-moe-uncensored", "g4-31b-uncensored"]
      and "uncensored" in K["uncensored_warning"].lower())
check("every engine has assets or is external", all(e.get("assets") or e.get("external") for e in K["engines"]))
# THE EXPORT'S SCRUB GENERALISES HIS MODEL'S NAME AWAY ("26B-A4B" -> "your model"), which
# turned every kit's repo into an invalid id the first time a fresh install ran the wizard.
# The kits ship raw (noscrub) and the ids the code passes around match no scrub rule.
_man = open(os.path.join(ROOT, "kairos-export", "kairos-export.toml"), encoding="utf-8").read() \
    if os.path.exists(os.path.join(ROOT, "kairos-export", "kairos-export.toml")) else ""
if _man:
    import re as _re
    _rules = _re.findall(r'^"([^"]+)"\s*=\s*"[^"]*"', _man.split("[scrub]", 1)[1], _re.M)
    check("the kits ship unscrubbed (their repo ids are the point)", '"harness/setup/kits.json"' in _man.split("noscrub = [", 1)[1].split("]", 1)[0])
    _hit = [(m["id"], r) for m in K["models"] for r in _rules if r in m["id"]]
    _src = open(os.path.join(ROOT, "harness", "setup", "installer.py"), encoding="utf-8").read()
    check("no kit id, and no installer string, matches a scrub rule",
          not _hit and not [r for r in _rules if r in _src and r.lower().startswith(("26b", "gemma4-26", "gemma-4-26"))], _hit)
else:
    print("  omitted  the scrub check: no export manifest in this tree")

print("\n2. suggest()")
s = I.suggest({"os": "nt", "gpus": [{"name": "RTX 2060", "vram_gb": 12, "vendor": "nvidia"}], "ram_gb": 32})
check("12 GB NVIDIA: the mixture-of-experts model on llama.cpp CUDA", (s["engine"], s["model"]) == ("llamacpp-cuda", "g4-moe"), s)
s = I.suggest({"os": "nt", "gpus": [{"name": "4090", "vram_gb": 24, "vendor": "nvidia"}], "ram_gb": 64})
check("24 GB + 64 GB: the 31B", s["model"] == "g4-31b")
check("no card: the CPU build", I.suggest({"os": "nt", "gpus": [], "ram_gb": 32})["engine"] == "llamacpp-cpu")
check("Linux: the Linux build", I.suggest({"os": "posix", "gpus": [], "ram_gb": 32})["engine"] == "llamacpp-linux")

print("\n3. plan()")
FILES = [{"path": "mmproj-X-BF16.gguf", "size": 10, "sha256": "a" * 64},
         {"path": "Gemma4-26B-A4B-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf", "size": 1000, "sha256": "b" * 64},
         {"path": "mtp-gemma-4-26B-A4B-it.gguf", "size": 5, "sha256": "c" * 64},
         {"path": "README.md", "size": 1, "sha256": None}]
_hf, _rel, _la = I.hf.files, I.github.releases, I.github.latest_asset
I.hf.files = lambda repo, token=None, net=None: FILES
I.github.releases = lambda repo, net=None: [{"tag_name": "b1"}]
def _asset(repo, pattern, net=None, listing=None, prefer_tag_prefix=None):
    name = "cudart-llama-bin-win-cuda-12.4-x64.zip" if "cudart" in pattern else "llama-b1-bin-win-cuda-12.4-x64.zip"
    return {"tag": "b1", "name": name, "size": 50, "url": "https://github.com/x/" + name, "sha256": "d" * 64}


I.github.latest_asset = _asset
p = I.plan("g4-moe-uncensored", "llamacpp-cuda", DEST)
roles = {i["role"]: i["name"] for i in p["items"]}
check("the model file is the model, never the projector or the draft", roles.get("model", "").endswith("Q4_K_M.gguf"), roles)
check("…with the projector and the draft beside it", roles.get("mmproj", "").startswith("mmproj") and roles.get("draft", "").startswith("mtp"))
check("…and the engine release asset", "engine" in [i["role"] for i in p["items"]])
check("every file carries its published hash", all(i["sha256"] for i in p["items"]))
check("sizes against free space (model, projector, draft, engine, runtime)", p["bytes"] == 1115 and p["fits"], (p["bytes"], p["fits"]))
check("the uncensored warning comes with an uncensored model", p["uncensored"] and p["warning"])
p2 = I.plan("g4-moe", "external", DEST)
check("…and not with the standard one", not p2["uncensored"] and not p2["warning"])
check("an external engine downloads no engine", "engine" not in [i["role"] for i in p2["items"]], [i["role"] for i in p2["items"]])

print("\n3b. a file already on this machine")
have = os.path.join(SB, "mymodels", "sub")
os.makedirs(have)
open(os.path.join(have, "Gemma4-26B-A4B-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf"), "wb").write(b"m" * 1000)
pr = I.plan("g4-moe-uncensored", "external", DEST, reuse=[os.path.join(SB, "mymodels")])
mi = [i for i in pr["items"] if i["role"] == "model"][0]
check("found by name and size, and not counted as a download", mi.get("reuse") and pr["need_bytes"] == pr["bytes"] - 1000)
pr2 = I.plan("g4-moe-uncensored", "external", DEST, reuse=[])
check("…and without reuse folders, it downloads", not [i for i in pr2["items"] if i.get("reuse")])

print("\n4. start()")
check("refused without the licence", "licence" in _err(lambda: I.start(p)))
check("refused without room", "space" in _err(lambda: I.start(dict(p, fits=False), licence_ok=True)))
EXE = b"MZ fake llama-server"


def fake_download(url, dest, *, size=None, sha256=None, **kw):
    os.makedirs(os.path.dirname(str(dest)), exist_ok=True)
    if str(dest).endswith(".zip"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            if "cudart" in str(dest):
                z.writestr("cudart64_12.dll", b"cuda runtime")
            else:
                z.writestr("llama-server.exe", EXE)
                z.writestr("ggml.dll", b"dll")
        data = buf.getvalue()
    else:
        data = b"x" * int(size or 1)
    with open(dest, "wb") as f:
        f.write(data)
    return dest


_dl = I.DL.download
I.DL.download = fake_download
p = dict(p)
for it in p["items"]:
    if it["role"] == "engine":
        it["size"] = None                # the fake zip's size is its own
I.start(p, licence_ok=True)
I._JOB["thread"].join(10)
st = I.status()
check("every planned file landed", st["finished"] and len(st["done"]) == 5, st.get("error") or st.get("done"))
check("…where the plan said", all(os.path.isfile(i["to"]) for i in p["items"]))
exe = I.engine_exe(p)
check("the engine zip was extracted beside it", exe.endswith("llama-server.exe") and os.path.isfile(exe), exe)
check("…and the CUDA runtime from the second zip sits beside the exe",
      os.path.isfile(os.path.join(os.path.dirname(exe), "cudart64_12.dll")))

print("\n5. approval")
ap = I.pending_approval(p)
check("the engine is pending approval, by hash", ap and len(ap["sha256"]) == 64 and ap["path"] == exe)
check("a bad hash is refused", bool(_err(lambda: I.approve("nope"))))
I.approve(ap["sha256"])
check("approved: nothing pending", I.pending_approval(p) is None and I.approved(exe))
with open(exe, "ab") as f:
    f.write(b"tampered")
check("a different file at that path is NOT approved", not I.approved(exe) and I.pending_approval(p))
with open(exe, "wb") as f:
    f.write(EXE)

print("\n6. the profile")
check("a bad name is refused", bool(_err(lambda: I.write_profile("../x", p))))
path = I.write_profile("local", p, companion="ivy", user_name="Ray", user_pronouns="he/him/his")
check("written to the profiles folder in use", os.path.dirname(path) == os.environ["SP_LAUNCH_PROFILES_DIR"])
check("an existing name is refused", "already exists" in _err(lambda: I.write_profile("local", p)))
with open(path, "rb") as f:
    prof = tomllib.load(f)
eng = prof["engine"]
check("kind openai at the engine's port", eng["kind"] == "openai" and eng["base_url"] == "http://127.0.0.1:8080")
check("[engine] command: the approved exe and the model, projector and draft",
      eng["command"][0] == exe and roles["model"] in " ".join(eng["command"])
      and "--mmproj" in eng["command"] and "-md" in eng["command"], eng["command"][:4])
# An explicit layer count switches off llama.cpp's own fitting (found by the fresh install: a
# 16 GB model forced whole onto a 12 GB card); its defaults, -ngl auto + --fit on, size the split.
check("[engine] command leaves the layer split to llama.cpp's fit (no -ngl, no -ngld)",
      not {"-ngl", "-ngld", "--n-gpu-layers", "--gpu-layers"} & set(eng["command"]), eng["command"])
check("its companion home, and no registry beside it", prof["companion"]["home"] == "ivy" and "registry" not in prof["paths"])
check("its user", prof["user"] == {"name": "Ray", "pronouns": "he/him/his"})
import serve  # noqa: E402
from harness import home as H  # noqa: E402
H.create("ivy", "Ivy")
prof["paths"]["companions_dir"] = os.environ["SP_COMPANIONS_DIR"]
prof["_profile_name"] = "local"
_env = dict(os.environ)
try:
    e = serve.build_env(prof)
    ok = e.get("SP_ENGINE_KIND") == "openai" and e.get("SP_COMPANION_ID") == "ivy"
except SystemExit as x:
    ok, e = False, {"refused": str(x)}
os.environ.clear()
os.environ.update(_env)
check("serve.build_env takes it", ok, {k: e.get(k) for k in ("SP_ENGINE_KIND", "SP_COMPANION_ID", "refused")})

print("\n7. convert")
os.environ.pop("SP_TRANSCODE_EXE", None)
_which = I.shutil.which
I.shutil.which = lambda name: None
_intree, I.IN_TREE_TRANSCODER = I.IN_TREE_TRANSCODER, os.path.join(SB, "no-build", "sp_transcode.exe")
check("no transcoder: refused, and it says what to use instead", "llama.cpp" in _err(lambda: I.convert("m.gguf", "out")))
fake = os.path.join(SB, "sp_transcode.exe")
open(fake, "wb").write(b"MZ transcoder")
check("an unapproved transcoder is refused", "approve" in _err(lambda: I.convert("m.gguf", "out", exe=fake)))
I.shutil.which = _which
I.IN_TREE_TRANSCODER = _intree
# The tool takes <in.gguf> <out.sp-model> <out.sp-tokenizer> (engine/tools/sp_transcode); the
# first wiring passed a STEM, so every native conversion would have died on its usage line.
I.approve(I._sha(fake))
_run, seen = I.subprocess.run, {}


def _tool(argv, **k):
    seen.setdefault("argv", argv)
    for out in argv[2:4]:                       # what the real tool writes: both outputs
        open(out, "w").write("x")
    return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()


I.subprocess.run = _tool
res = I.convert("m.gguf", os.path.join(SB, "her"), exe=fake)
I.subprocess.run = _run
a = seen.get("argv", [])
check("convert passes the tool its model AND tokenizer paths (as .part, renamed on success)",
      a[1:4] == ["m.gguf", os.path.join(SB, "her.sp-model.part"), os.path.join(SB, "her.sp-tokenizer.part")]
      and "--q4b" in a and "--stream" in a, a)
check("…and the finished pair is under the real names", os.path.isfile(os.path.join(SB, "her.sp-model"))
      and not os.path.exists(os.path.join(SB, "her.sp-model.part")))
check("the in-tree build is where the setup centre looks",
      I.IN_TREE_TRANSCODER.replace("\\", "/").endswith("engine/tools/sp_transcode/build/sp_transcode.exe")
      or os.name != "nt")

print("\n8. the routes")
from harness.server import setup_routes as SR  # noqa: E402
SR._PLAN["p"] = None
check("a relative folder is refused", SR.post_plan({"model": "g4-moe", "engine": "external", "dest": "data"})[0] == 400)
_st = I.status
I.status = lambda: {}
check("start needs a plan", SR.post_start({"licence_ok": True})[0] == 400)
I.status = _st
SR._PLAN["p"] = p
with open(exe, "ab") as f:
    f.write(b"changed again")
check("the profile needs the engine approved", "approve" in SR.post_profile({"name": "x2"})[1].get("error", ""))

print("\n9. serve.py")
c = {"engine": {"command": [os.path.join(SB, "missing.exe")]}}
check("a missing engine exe is said, not started", serve.launch_engine_command(c, {}, "http://127.0.0.1:9") is False)

print("\n10. her native engine (kairos-engine), end to end")
# FOUND 2026-11-26: choosing "Kairos engine" wrote an openai profile running sp-daemon.exe with
# llama-server's flags; nothing asked for the transcoder, nothing converted, and serve.py's
# `from engine.launch import …` had no engine/launch.py to import. The whole path, on fakes.
k = I.kits()
check("the kit prefers the release with the CUDA libraries, then the lean one",
      I.kits_engine("kairos-engine")["assets"] == [["kairos-engine-*-win-cuda*-cublas.zip", "kairos-engine-*-win-cuda*.zip"]])
NDEST = os.path.join(SB, "ndata")
_seen_pats = []


def _nasset(repo, pattern, net=None, listing=None, prefer_tag_prefix=None):
    _seen_pats.append(pattern)
    name = "kairos-engine-0.8.0-win-cuda13-cublas.zip"
    return {"tag": "v0.8.0", "name": name, "size": None, "url": "https://github.com/x/" + name, "sha256": "e" * 64}


DAEMON, TRANS = b"MZ fake sp-daemon", b"MZ fake sp_transcode"


def _ndl(url, dest, *, size=None, sha256=None, **kw):
    if str(dest).endswith(".zip"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("sp-daemon.exe", DAEMON)
            z.writestr("sp_transcode.exe", TRANS)
            z.writestr("launch.py", "# the release's launch.py\n")
            z.writestr("cublas64_13.dll", b"nvidia")
        os.makedirs(os.path.dirname(str(dest)), exist_ok=True)
        open(dest, "wb").write(buf.getvalue())
        return dest
    return fake_download(url, dest, size=size, sha256=sha256)


I.github.latest_asset, I.DL.download = _nasset, _ndl
pn = I.plan("g4-moe-uncensored", "kairos-engine", NDEST)
check("…and asks the catalogue for it first", bool(_seen_pats) and "cublas" in _seen_pats[0], _seen_pats[:1])
I.start(pn, licence_ok=True)
I._JOB["thread"].join(10)
check("the engine release downloads and unpacks", I.status().get("finished") and os.path.isfile(I.engine_exe(pn)), I.status().get("error"))
check("it is her native engine, and it needs converting", I.native(pn) and I.needs_convert(pn))
a1 = I.pending_approval(pn)
check("approval 1 of 2: the engine", a1 and a1["what"] == "engine" and a1["path"].endswith("sp-daemon.exe"), a1)
check("converting is refused before anything is approved", "approve" in _err(lambda: I.start_convert(pn)))
I.approve(a1["sha256"])
a2 = I.pending_approval(pn)
check("approval 2 of 2: the transcoder its release ships", a2 and a2["what"] == "transcoder" and a2["path"].endswith("sp_transcode.exe"), a2)
check("the transcoder the setup centre finds is that one", bool(a2) and I.transcoder(pn) == a2["path"])
if a2:
    I.approve(a2["sha256"])
check("then nothing is pending", I.pending_approval(pn) is None)
I.ENGINE_DIR = os.path.join(SB, "kairos-root", "engine")   # never the real tree's engine/
check("the profile is refused before the model is converted",
      "convert" in _err(lambda: I.write_profile("nat0", pn, companion="ivy")))

# a stand-in converter: the tool's argv, writing what the tool writes (or failing half way)
FAKE_T = os.path.join(SB, "fake_transcode.py")
open(FAKE_T, "w").write("import sys\nopen(sys.argv[2],'w').write('M')\nopen(sys.argv[3],'w').write('T')\n"
                        "sys.exit(3 if 'FAIL' in open(sys.argv[1]).read(1000) else 0)\n")
_argv = I.convert_argv
I.convert_argv = lambda exe, g, m, t: [sys.executable, FAKE_T, g, m, t]
gguf, spm, spt = I.sp_paths(pn)
check("the .sp pair goes beside the download, same name",
      spm == gguf[:-5] + ".sp-model" and spt == gguf[:-5] + ".sp-tokenizer", (spm, spt))
open(gguf, "w").write("FAIL")
I.start_convert(pn)
I._JOB["thread"].join(10)
check("a failed conversion leaves nothing under the real names (it would read as done)",
      I.status().get("convert_error") and not os.path.exists(spm) and not os.path.exists(spt), I.status().get("convert_error"))
open(gguf, "w").write("ok")
I.start_convert(pn)
I._JOB["thread"].join(10)
st = I.status()
check("the conversion runs in the background and lands both files",
      st.get("converted") and not st.get("converting") and os.path.isfile(spm) and os.path.isfile(spt), st.get("convert_error"))
check("…and is then not needed", not I.needs_convert(pn))
I.convert_argv = _argv

try:
    path = I.write_profile("nat1", pn, companion="ivy", user_name="Sam", user_pronouns="he/him/his")
    with open(path, "rb") as f:
        np_ = tomllib.load(f)
    _why = ""
except I.SetupError as x:                       # a verdict, not a crash, when an earlier step broke
    path, np_, _why = "", {"engine": {}, "paths": {}, "companion": {}, "user": {}}, str(x)
check("the native profile is written", bool(path), _why)
check("the profile is a NATIVE one (kind sp), from sp.toml", np_["engine"].get("kind") == "sp" and "command" not in np_["engine"], np_["engine"])
check("…its paths are the approved daemon and the converted model",
      tuple(np_["paths"].get(k2) for k2 in ("engine_exe", "model", "tokenizer")) == (I.engine_exe(pn), spm, spt), np_["paths"])
# FOUND BY THE END-TO-END RUN: sp.toml's own [kv]/[decode] gave "exceeds Pmax", then a byte-exact
# path MoE does not have, then garbage. The kit's tested values must reach the profile.
_kp = I.kits_engine("kairos-engine")["profile"]
_bad = [f"{sec}.{k2}" for sec in ("kv", "decode") for k2, v in _kp[sec].items()
        if k2 != "moe_cache_gb" and np_.get(sec, {}).get(k2) != v]
check("…and the kit's tested [kv]/[decode] settings (Pmax 20000, byte-exact off, KV persistence off…)",
      not _bad and np_.get("kv", {}).get("pmax") == 20000 and np_.get("decode", {}).get("byteexact") is False
      and np_.get("kv", {}).get("persist") is False, _bad[:6])
_ns = lambda v: I.native_settings(I.kits_engine("kairos-engine"), {"gpus": [{"vram_gb": v}]})["kv"]["moe_cache_gb"]  # noqa: E731
check("…the expert cache is the tested 6 GB on a 12 GB+ card, and smaller on a smaller one",
      (_ns(12), _ns(24), _ns(8), _ns(6)) == (6.0, 6.0, 2.0, 1.0), (_ns(12), _ns(24), _ns(8), _ns(6)))
check("…with its companion home and you (sp.toml has no [user] to substitute)",
      np_["companion"].get("home") == "ivy" and np_["user"].get("name") == "Sam" and "registry" not in np_["paths"], np_.get("user"))
la = os.path.join(I.ENGINE_DIR, "launch.py")
_rd = lambda f: open(f).read() if os.path.isfile(f) else ""  # noqa: E731
check("engine/launch.py is installed from the release, where serve.py imports it",
      _rd(la) == "# the release's launch.py\n")
os.makedirs(os.path.dirname(la), exist_ok=True)
open(la, "w").write("# a cloned engine's own launch.py\n")
try:
    I.write_profile("nat2", pn)
except I.SetupError:
    pass
check("…and never over one already there", _rd(la) == "# a cloned engine's own launch.py\n")
SR._PLAN["p"] = pn
kit = SR.get_kit()[1]
check("the Setup window sees no conversion pending and a transcoder", not kit["convert"]["needed"] and kit["transcoder"], kit["convert"])
np_["paths"]["companions_dir"] = os.environ["SP_COMPANIONS_DIR"]   # ivy lives in the sandbox (§6)
np_["_profile_name"] = "nat1"
_env = dict(os.environ)
try:
    e = serve.build_env(np_)
    ok = e.get("SP_ENGINE_KIND") == "sp" and os.path.normcase(e.get("SP_MODEL_PATH", "")) == os.path.normcase(spm)
except (SystemExit, Exception) as x:
    ok, e = False, {"refused": str(x)}
os.environ.clear()
os.environ.update(_env)
check("serve.build_env takes the native profile", ok, {k2: e.get(k2) for k2 in ("SP_ENGINE_KIND", "SP_MODEL_PATH", "refused")})

I.hf.files, I.github.releases, I.github.latest_asset, I.DL.download = _hf, _rel, _la, _dl
finish("G-SETUP")
