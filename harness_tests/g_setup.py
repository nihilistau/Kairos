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
      [m["id"] for m in K["models"] if m.get("uncensored")] == ["your model-uncensored", "gemma4-31b-uncensored"]
      and "uncensored" in K["uncensored_warning"].lower())
check("every engine has assets or is external", all(e.get("assets") or e.get("external") for e in K["engines"]))

print("\n2. suggest()")
s = I.suggest({"os": "nt", "gpus": [{"name": "RTX 2060", "vram_gb": 12, "vendor": "nvidia"}], "ram_gb": 32})
check("12 GB NVIDIA: the your model on llama.cpp CUDA", (s["engine"], s["model"]) == ("llamacpp-cuda", "your model"), s)
s = I.suggest({"os": "nt", "gpus": [{"name": "4090", "vram_gb": 24, "vendor": "nvidia"}], "ram_gb": 64})
check("24 GB + 64 GB: the 31B", s["model"] == "gemma4-31b")
check("no card: the CPU build", I.suggest({"os": "nt", "gpus": [], "ram_gb": 32})["engine"] == "llamacpp-cpu")
check("Linux: the Linux build", I.suggest({"os": "posix", "gpus": [], "ram_gb": 32})["engine"] == "llamacpp-linux")

print("\n3. plan()")
FILES = [{"path": "mmproj-X-BF16.gguf", "size": 10, "sha256": "a" * 64},
         {"path": "Gemma4-your model-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf", "size": 1000, "sha256": "b" * 64},
         {"path": "mtp-gemma-4-your model-it.gguf", "size": 5, "sha256": "c" * 64},
         {"path": "README.md", "size": 1, "sha256": None}]
_hf, _rel, _la = I.hf.files, I.github.releases, I.github.latest_asset
I.hf.files = lambda repo, token=None, net=None: FILES
I.github.releases = lambda repo, net=None: [{"tag_name": "b1"}]
def _asset(repo, pattern, net=None, listing=None, prefer_tag_prefix=None):
    name = "cudart-llama-bin-win-cuda-12.4-x64.zip" if "cudart" in pattern else "llama-b1-bin-win-cuda-12.4-x64.zip"
    return {"tag": "b1", "name": name, "size": 50, "url": "https://github.com/x/" + name, "sha256": "d" * 64}


I.github.latest_asset = _asset
p = I.plan("your model-uncensored", "llamacpp-cuda", DEST)
roles = {i["role"]: i["name"] for i in p["items"]}
check("the model file is the model, never the projector or the draft", roles.get("model", "").endswith("Q4_K_M.gguf"), roles)
check("…with the projector and the draft beside it", roles.get("mmproj", "").startswith("mmproj") and roles.get("draft", "").startswith("mtp"))
check("…and the engine release asset", "engine" in [i["role"] for i in p["items"]])
check("every file carries its published hash", all(i["sha256"] for i in p["items"]))
check("sizes against free space (model, projector, draft, engine, runtime)", p["bytes"] == 1115 and p["fits"], (p["bytes"], p["fits"]))
check("the uncensored warning comes with an uncensored model", p["uncensored"] and p["warning"])
p2 = I.plan("your model", "external", DEST)
check("…and not with the standard one", not p2["uncensored"] and not p2["warning"])
check("an external engine downloads no engine", "engine" not in [i["role"] for i in p2["items"]], [i["role"] for i in p2["items"]])

print("\n3b. a file already on this machine")
have = os.path.join(SB, "mymodels", "sub")
os.makedirs(have)
open(os.path.join(have, "Gemma4-your model-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf"), "wb").write(b"m" * 1000)
pr = I.plan("your model-uncensored", "external", DEST, reuse=[os.path.join(SB, "mymodels")])
mi = [i for i in pr["items"] if i["role"] == "model"][0]
check("found by name and size, and not counted as a download", mi.get("reuse") and pr["need_bytes"] == pr["bytes"] - 1000)
pr2 = I.plan("your model-uncensored", "external", DEST, reuse=[])
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
check("no transcoder: refused, and it says what to use instead", "llama.cpp" in _err(lambda: I.convert("m.gguf", "out")))
fake = os.path.join(SB, "sp_transcode.exe")
open(fake, "wb").write(b"MZ transcoder")
check("an unapproved transcoder is refused", "approve" in _err(lambda: I.convert("m.gguf", "out", exe=fake)))
I.shutil.which = _which

print("\n8. the routes")
from harness.server import setup_routes as SR  # noqa: E402
SR._PLAN["p"] = None
check("a relative folder is refused", SR.post_plan({"model": "your model", "engine": "external", "dest": "data"})[0] == 400)
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

I.hf.files, I.github.releases, I.github.latest_asset, I.DL.download = _hf, _rel, _la, _dl
finish("G-SETUP")
