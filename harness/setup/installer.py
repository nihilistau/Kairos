"""THE SETUP CENTRE'S WORK (2026-11-26, design §4): look at the machine, suggest, plan, fetch,
approve, convert, and write the profile.

    hardware()                 GPU and VRAM (nvidia-smi), RAM, free disk — what to suggest
    suggest(hw)                an engine and a model that fit
    plan(model, engine, dest)  every file, its size and hash, resolved LIVE from Hugging Face
                               and GitHub; against the destination's free space
    start(plan) / status()     the downloads, one at a time in a background thread, resumable,
                               each verified against its published hash before it counts
    approve(sha256)            an executable from a downloaded zip runs only after you
                               approve it, recorded by hash (a different file at that path
                               is not approved)
    convert(gguf) / start_convert(plan)
                               GGUF -> .sp for her native engine, with the sp_transcode its
                               release ships (approved like the engine), in the background
    write_profile(name, ...)   profiles/<name>.toml — the companion profile with the engine
                               set: base_url, and `[engine] command` so serve.py starts it

The wizard (Setup window, `python -m harness.setup`) is these calls in order. Nothing is ever
run that was not approved; nothing is downloaded from a host off the allowlist (net.py).
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from harness import home as H
from harness.setup import download as DL
from harness.setup import extract as EX
from harness.setup import github, hf
from harness.setup.net import CatalogueError

KITS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kits.json")
STATE = os.path.join(H.VAR, "setup.json")
_LOCK = threading.Lock()
_JOB: Dict[str, object] = {"thread": None, "cancel": None}


class SetupError(ValueError):
    pass


def kits() -> dict:
    with open(KITS, encoding="utf-8") as f:
        return json.load(f)


def _state() -> dict:
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(s: dict) -> None:
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)
    from harness.store_io import replace_atomic
    replace_atomic(tmp, STATE)


# ── the machine ────────────────────────────────────────────────────────────────────────
def hardware(dest: str = "") -> dict:
    gpus = []
    exe = shutil.which("nvidia-smi")
    if exe:
        try:
            out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=10).stdout
            for line in out.strip().splitlines():
                name, mem = [x.strip() for x in line.split(",", 1)]
                gpus.append({"name": name, "vram_gb": round(int(mem) / 1024, 1), "vendor": "nvidia"})
        except (OSError, ValueError, subprocess.SubprocessError):
            gpus = []
    ram = 0.0
    try:
        if os.name == "nt":
            import ctypes

            class _M(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = _M()
            m.dwLength = ctypes.sizeof(_M)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            ram = m.ullTotalPhys / 2 ** 30
        else:
            ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
    except (OSError, ValueError, AttributeError):
        ram = 0.0
    d = dest or H.ROOT
    free = shutil.disk_usage(d if os.path.isdir(d) else os.path.dirname(d) or ".").free / 2 ** 30
    return {"os": os.name, "gpus": gpus, "ram_gb": round(ram, 1), "free_gb": round(free, 1), "dest": d}


def suggest(hw: dict) -> dict:
    """An engine and a model that fit this machine, and why."""
    vram = max([g["vram_gb"] for g in hw.get("gpus", [])] or [0])
    if hw.get("os") != "nt":
        engine = "llamacpp-linux"
    elif any(g.get("vendor") == "nvidia" for g in hw.get("gpus", [])):
        engine = "llamacpp-cuda"
    else:
        engine = "llamacpp-cpu"
    model = "g4-31b" if vram >= 24 and hw.get("ram_gb", 0) >= 32 else "g4-moe"
    why = (f"{vram:.0f} GB on the graphics card and {hw.get('ram_gb', 0):.0f} GB of memory: "
           + ("the dense 31B fits." if model == "g4-31b" else
              "the mixture-of-experts model fits — it keeps part of itself in system memory and stays quick."))
    return {"engine": engine, "model": model, "why": why}


# ── what to fetch ──────────────────────────────────────────────────────────────────────
def _first(files: List[dict], patterns: List[str], exclude: List[str] = ()) -> Optional[dict]:
    for pat in patterns:
        for f in files:
            n = f["path"].rsplit("/", 1)[-1]
            if fnmatch.fnmatch(n, pat) and not any(fnmatch.fnmatch(n, x) for x in exclude):
                return f
    return None


def _by_id(items: List[dict], iid: str, what: str) -> dict:
    for it in items:
        if it["id"] == iid:
            return it
    raise SetupError(f"no {what} {iid!r}")


def find_existing(name: str, size: int, dirs) -> str:
    """A file already on this machine with the same NAME and SIZE (Primer's "existing files
    count"), in `dirs` (SP_SETUP_REUSE, ';'-separated, or the wizard's). Not trusted on
    that alone: start() checks its SHA-256 before it is used."""
    for d in dirs or []:
        if not d or not os.path.isdir(d):
            continue
        for dp, dn, fn in os.walk(d):
            if dp.count(os.sep) - d.count(os.sep) > 3:
                dn[:] = []
                continue
            if name in fn:
                p = os.path.join(dp, name)
                try:
                    if os.path.getsize(p) == size:
                        return p
                except OSError:
                    continue
    return ""


def reuse_dirs() -> List[str]:
    return [d for d in (os.environ.get("SP_SETUP_REUSE") or "").split(";") if d.strip()]


def plan(model_id: str, engine_id: str, dest: str, *, token: str = "", net=None, reuse=None) -> dict:
    """Every file to fetch: [{role, name, url, size, sha256, to}] + total and free space.
    A file already on this machine (`reuse` folders) is marked `reuse` and not downloaded."""
    k = kits()
    m = _by_id(k["models"], model_id, "model")
    e = _by_id(k["engines"], engine_id, "engine")
    items = []
    files = hf.files(m["repo"], token=token or None, net=net)
    excl = ["mmproj*", "*mtp*", "*MTP*"]
    main = _first(files, m["model"], exclude=excl)
    if not main:
        raise SetupError(f"no model file in {m['repo']} matches {m['model']}")
    mdir = os.path.join(dest, "models", *m["repo"].split("/"))
    for role, pats, ex in (("model", None, None), ("mmproj", m.get("mmproj"), None), ("draft", m.get("draft"), None)):
        f = main if role == "model" else (_first(files, pats) if pats else None)
        if not f:
            continue
        items.append({"role": role, "name": f["path"].rsplit("/", 1)[-1], "size": f["size"],
                      "sha256": f["sha256"],
                      "url": f"https://huggingface.co/{m['repo']}/resolve/main/{f['path']}",
                      "to": os.path.join(mdir, f["path"].rsplit("/", 1)[-1])})
    if not e.get("external"):
        listing = github.releases(e["github"], net=net)
        for alts in e["assets"]:
            a = None
            for pat in alts:
                try:
                    a = github.latest_asset(e["github"], fnmatch.translate(pat), net=net, listing=listing)
                    break
                except CatalogueError:
                    continue
            if not a:
                raise SetupError(f"{e['github']} has no release asset matching {alts[0]}"
                                 + (" — the Kairos engine release is not published yet; choose llama.cpp"
                                    if e.get("native") else ""))
            items.append({"role": "engine", "name": a["name"], "size": a["size"], "sha256": a["sha256"],
                          "url": a["url"], "tag": a["tag"],
                          "to": os.path.join(dest, "engines", e["id"], a["tag"], a["name"])})
    for it in items:
        if it["role"] != "engine" and it["size"]:
            found = find_existing(it["name"], it["size"], reuse if reuse is not None else reuse_dirs())
            if found and os.path.normcase(found) != os.path.normcase(it["to"]):
                it["reuse"] = found
    total = sum(int(i["size"] or 0) for i in items)
    have = sum(int(i["size"] or 0) for i in items
               if i.get("reuse") or (os.path.isfile(i["to"]) and os.path.getsize(i["to"]) == i["size"]))
    free = shutil.disk_usage(dest if os.path.isdir(dest) else os.path.dirname(dest) or ".").free
    return {"model": model_id, "engine": engine_id, "dest": dest, "items": items, "bytes": total,
            "need_bytes": total - have, "free_bytes": free, "fits": free > (total - have) * 1.05 + 2 ** 30,
            "licence": k["licences"].get(m["licence"], {"name": m["licence"]}), "licence_id": m["licence"],
            "uncensored": bool(m.get("uncensored")),
            "warning": k["uncensored_warning"] if m.get("uncensored") else ""}


# ── fetching ───────────────────────────────────────────────────────────────────────────
def status() -> dict:
    s = _state()
    t = _JOB.get("thread")
    s["running"] = bool(t and t.is_alive())
    return s


def start(p: dict, *, licence_ok: bool = False, token: str = "", transport=None, resolve=None) -> dict:
    """Begin the downloads in the background. Refuses without the licence acknowledged, without
    room on the disk, or while a job runs."""
    if not licence_ok:
        raise SetupError(f"acknowledge the model's licence first ({p['licence'].get('name')})")
    if not p.get("fits"):
        raise SetupError("not enough free space at the destination")
    with _LOCK:
        t = _JOB.get("thread")
        if t and t.is_alive():
            raise SetupError("a download is already running")
        cancel = threading.Event()
        st = {"plan": p, "done": [], "current": "", "bytes": 0, "error": "", "finished": False,
              "approved": _state().get("approved", []), "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
        _save(st)

        def run():
            for it in p["items"]:
                if cancel.is_set():
                    break
                st["current"] = it["name"]
                _save(st)
                try:
                    if it.get("reuse") and not os.path.isfile(it["to"]):
                        # ALREADY ON THIS MACHINE: checked by its published hash, then hard-linked
                        # (no second copy) or, across drives, copied.
                        st["current"] = it["name"] + " (checking the copy already here)"
                        _save(st)
                        if it.get("sha256") and _sha(it["reuse"]) != it["sha256"]:
                            raise CatalogueError("the copy already here does not match the published hash")
                        os.makedirs(os.path.dirname(it["to"]), exist_ok=True)
                        try:
                            os.link(it["reuse"], it["to"])
                        except OSError:
                            shutil.copy2(it["reuse"], it["to"])
                    if not (os.path.isfile(it["to"]) and os.path.getsize(it["to"]) == it["size"]):
                        os.makedirs(os.path.dirname(it["to"]), exist_ok=True)

                        def prog(done, total=None, **_k):
                            # SAVED, throttled: status() reads the file, so an unsaved count
                            # showed 0.0 GB for a whole download (found by the fresh install).
                            st["bytes"] = done
                            if time.time() - st.get("_saved_at", 0) > 1.5:
                                st["_saved_at"] = time.time()
                                _save(st)
                        DL.download(it["url"], Path(it["to"]), size=it["size"], sha256=it["sha256"],
                                    progress=prog, cancel=cancel, transport=transport, resolve=resolve,
                                    token=token or None)
                    if it["role"] == "engine" and it["to"].endswith(".zip"):
                        # EACH ZIP INTO ITS OWN FOLDER: the extractor refuses a folder that is
                        # not empty (it never overwrites), and llama.cpp's CUDA build is two
                        # zips — the engine and its CUDA runtime. _merge_runtime puts them
                        # together afterwards, copying, never replacing.
                        into = Path(it["to"][:-4])
                        if not (into.is_dir() and any(into.iterdir())):
                            EX.extract_zip(Path(it["to"]), into)
                    st["done"].append(it["name"])
                except (CatalogueError, EX.ExtractError, OSError) as e:
                    st["error"] = f"{it['name']}: {e}"
                    break
                finally:
                    _save(st)
            if not st["error"] and not cancel.is_set():
                _merge_runtime(p)
            st["finished"] = not st["error"] and not cancel.is_set()
            st["current"] = ""
            _save(st)

        th = threading.Thread(target=run, name="kairos-setup", daemon=True)
        _JOB.update(thread=th, cancel=cancel)
        th.start()
    return {"ok": True, "started": True}


def _merge_runtime(p: dict) -> None:
    """The runtime DLLs (cudart) beside the engine executable, which loads them from its own
    folder. Copies; an existing file is never replaced."""
    exe = engine_exe(p)
    if not exe:
        return
    there = os.path.dirname(exe)
    for it in p["items"]:
        d = it["to"][:-4] if it["role"] == "engine" and it["to"].endswith(".zip") else ""
        if not d or os.path.normcase(os.path.abspath(d)) == os.path.normcase(os.path.abspath(there)) \
                or not os.path.isdir(d):
            continue
        for dp, _dn, fn in os.walk(d):
            for f in fn:
                if f.lower().endswith(".dll") and not os.path.exists(os.path.join(there, f)):
                    shutil.copy2(os.path.join(dp, f), os.path.join(there, f))


def cancel() -> dict:
    c = _JOB.get("cancel")
    if c:
        c.set()
    return {"ok": True}


# ── approving what will run ────────────────────────────────────────────────────────────
def _sha(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _in_engine(p: dict, name: str) -> str:
    """A file inside the plan's downloaded engine (its zip's folder), or ""."""
    if not name:
        return ""
    for it in p.get("items") or []:
        if it["role"] == "engine":
            root = it["to"][:-4] if it["to"].endswith(".zip") else os.path.dirname(it["to"])
            for dp, _dn, fn in os.walk(root):
                if name in fn:
                    return os.path.join(dp, name)
    return ""


def engine_exe(p: dict) -> str:
    e = kits_engine(p["engine"])
    return "" if e.get("external") else _in_engine(p, e["exe"])


def native(p: Optional[dict]) -> bool:
    """Her own engine (kairos-engine): kind "sp", a converted model, engine/launch.py."""
    try:
        e = kits_engine((p or {}).get("engine") or "")
    except SetupError:
        return False
    return bool(e.get("native") and e.get("transcoder") and not e.get("external"))


def bundled_transcoder(p: Optional[dict]) -> str:
    """sp_transcode as the engine release ships it, beside sp-daemon."""
    return _in_engine(p, kits_engine(p["engine"]).get("transcoder", "")) if native(p) else ""


def pending_approval(p: dict) -> Optional[dict]:
    """The next executable from this plan that will run and is not yet approved: the engine,
    then — for her native engine — the transcoder its release ships (2026-11-26: it was never
    asked for, so the conversion could not have run). One at a time; approve and ask again."""
    tag = next((it.get("tag") for it in p.get("items") or [] if it["role"] == "engine"), "")
    for what, exe in (("engine", engine_exe(p)), ("transcoder", bundled_transcoder(p))):
        if not exe or not os.path.isfile(exe):
            continue
        sha = _sha(exe)
        if sha in _state().get("approved", []):
            continue
        return {"what": what, "path": exe, "sha256": sha,
                "publisher": kits_engine(p["engine"]).get("github"), "release": tag}
    return None


def kits_engine(eid: str) -> dict:
    return _by_id(kits()["engines"], eid, "engine")


def approve(sha256: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", sha256 or ""):
        raise SetupError("approve a SHA-256")
    s = _state()
    s.setdefault("approved", [])
    if sha256 not in s["approved"]:
        s["approved"].append(sha256)
    _save(s)
    return {"ok": True, "approved": sha256}


def approved(path: str) -> bool:
    return os.path.isfile(path) and _sha(path) in _state().get("approved", [])


# ── converting for her native engine ───────────────────────────────────────────────────
# Built in this tree by engine/build-transcode.bat (engine/tools/sp_transcode, 2026-11-26).
IN_TREE_TRANSCODER = os.path.join(H.ROOT, "engine", "tools", "sp_transcode", "build",
                                  "sp_transcode.exe" if os.name == "nt" else "sp_transcode")


def transcoder(p: Optional[dict] = None) -> str:
    """sp_transcode: SP_TRANSCODE_EXE, the one the plan's engine release ships, the in-tree
    build, then PATH."""
    for c in (os.environ.get("SP_TRANSCODE_EXE", ""), bundled_transcoder(p) if p else "",
              IN_TREE_TRANSCODER, shutil.which("sp_transcode") or "", shutil.which("sp_transcode.exe") or ""):
        if c and os.path.isfile(c):
            return c
    return ""


def convert_argv(exe: str, gguf: str, model: str, tok: str) -> List[str]:
    """The tool takes the model AND tokenizer paths (not a stem); --stream keeps peak memory at
    about one tensor, so a 26B fits a 32 GB machine, and its output is byte-identical."""
    return [exe, gguf, model, tok, "--q4b", "--stream", "--verify"]


def convert(gguf: str, out_stem: str, *, exe: str = "") -> dict:
    exe = exe or transcoder()
    if not exe:
        raise SetupError("sp_transcode is not on this machine — build it with "
                         "engine/build-transcode.bat, or use llama.cpp, which needs no conversion")
    if not approved(exe):
        raise SetupError("approve the transcoder first (its SHA-256 is shown in Setup)")
    model, tok = out_stem + ".sp-model", out_stem + ".sp-tokenizer"
    if os.path.isfile(model) and os.path.isfile(tok):
        return {"ok": True, "model": model, "tokenizer": tok, "skipped": True}
    # INTO .part NAMES, RENAMED ONLY ON SUCCESS: "both files exist" is what skips a conversion,
    # so an interrupted 14 GB write left under the real name would have counted as done.
    r = subprocess.run(convert_argv(exe, gguf, model + ".part", tok + ".part"), capture_output=True, text=True)
    if r.returncode != 0 or not (os.path.isfile(model + ".part") and os.path.isfile(tok + ".part")):
        raise SetupError("conversion failed: " + ((r.stderr or r.stdout) or "no output")[-400:])
    from harness.store_io import replace_atomic
    replace_atomic(tok + ".part", tok)
    replace_atomic(model + ".part", model)
    return {"ok": True, "model": model, "tokenizer": tok}


def sp_paths(p: dict) -> tuple:
    """The .sp pair the plan's model converts to: beside the GGUF, same name."""
    g = next((it["to"] for it in p.get("items") or [] if it["role"] == "model"), "")
    stem = g[:-5] if g.lower().endswith(".gguf") else g
    return g, stem + ".sp-model", stem + ".sp-tokenizer"


def needs_convert(p: Optional[dict]) -> bool:
    if not native(p):
        return False
    _g, m, t = sp_paths(p)
    return not (os.path.isfile(m) and os.path.isfile(t))


def start_convert(p: dict) -> dict:
    """GGUF -> .sp in the background (a 26B takes minutes), as the downloads do: status()
    carries `converting`, then `converted` or `convert_error`."""
    if not native(p):
        raise SetupError("only her native engine needs a converted model")
    if pending_approval(p):
        raise SetupError("approve the engine and its transcoder first")
    exe = transcoder(p)
    gguf, _m, _t = sp_paths(p)
    if not os.path.isfile(gguf):
        raise SetupError("the model is not downloaded yet")
    with _LOCK:
        t = _JOB.get("thread")
        if t and t.is_alive():
            raise SetupError("a download or conversion is already running")
        st = _state()
        st.update(converting=True, convert_error="", converted=False,
                  convert_started=time.strftime("%Y-%m-%dT%H:%M:%S"))
        _save(st)

        def run():
            try:
                convert(gguf, sp_paths(p)[1][:-len(".sp-model")], exe=exe)
                st["converted"] = True
            except (SetupError, OSError) as e:
                st["convert_error"] = str(e)
            finally:
                st["converting"] = False
                _save(st)

        th = threading.Thread(target=run, name="kairos-convert", daemon=True)
        _JOB.update(thread=th, cancel=None)
        th.start()
    return {"ok": True, "started": True}


ENGINE_DIR = os.path.join(H.ROOT, "engine")     # where serve.py imports engine.launch from


def install_launcher(p: dict) -> str:
    """engine/launch.py, from the engine release, where serve.py imports it (`from engine.launch
    import launch_daemon`). Never over one already there — that is a cloned engine repo's own."""
    dst = os.path.join(ENGINE_DIR, "launch.py")
    if os.path.isfile(dst):
        return dst
    src = _in_engine(p, "launch.py")
    if not src:
        raise SetupError("this engine release has no launch.py — use kairos-engine 0.8.0 or later")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return dst


# ── the profile ────────────────────────────────────────────────────────────────────────
def engine_command(p: dict, *, ctx: int = 0, port: int = 0) -> List[str]:
    """llama-server and its flags for this plan (the model, vision, draft, context, port).

    NO LAYER COUNT (2026-11-26, found by the fresh install). This passed `-ngl 99`, and llama.cpp
    answered "failed to fit params to free device memory: n_gpu_layers already set by user" — an
    explicit count switches off its own fitting, so a 16 GB model was forced whole onto a 12 GB
    card. Left unset, llama.cpp's defaults (`-ngl auto`, `--fit on`) size the GPU/CPU split to
    the card, MoE experts included. The draft's layers likewise."""
    d = kits()["defaults"]
    exe = engine_exe(p)
    get = {it["role"]: it["to"] for it in p["items"]}
    cmd = [exe, "-m", get["model"], "-c", str(ctx or d["ctx"]),
           "--host", "127.0.0.1", "--port", str(port or d["port"]), "--jinja"]
    if get.get("mmproj"):
        cmd += ["--mmproj", get["mmproj"]]
    if get.get("draft"):
        cmd += ["-md", get["draft"], "--spec-type", "draft-mtp"]
    return cmd


def _q(s: str) -> str:
    return "'" + str(s).replace("'", "") + "'"


def write_profile(name: str, p: dict, *, companion: str = "", user_name: str = "",
                  user_pronouns: str = "", base_url: str = "", ctx: int = 0) -> str:
    """profiles/<name>.toml: the shipped `companion` profile with its [engine] (and, given,
    its [companion] home and [user]) set. Refuses to overwrite an existing profile."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name or ""):
        raise SetupError("a profile name is letters, digits, - and _")
    # The profiles folder the Launch window writes (SP_LAUNCH_PROFILES_DIR, sandboxed in every
    # gate), else profiles/ beside serve.py. The TEMPLATE is always the shipped companion.toml.
    pdir = os.environ.get("SP_LAUNCH_PROFILES_DIR") or os.path.join(H.ROOT, "profiles")
    dst = os.path.join(pdir, name + ".toml")
    if os.path.exists(dst):
        raise SetupError(f"profiles/{name}.toml already exists — pick another name")
    e = kits_engine(p["engine"]) if p.get("engine") else {"external": True}
    port = kits()["defaults"]["port"]
    if native(p):
        # HER NATIVE ENGINE (2026-11-26). This branch did not exist: the profile came out as
        # kind "openai" with llama-server's flags on sp-daemon.exe. The template is the shipped
        # sp.toml (kind "sp"); its [paths] get the approved daemon and the CONVERTED model, and
        # engine/launch.py — serve.py's way to start it — comes from the release.
        if pending_approval(p):
            raise SetupError("approve the engine and its transcoder first")
        if needs_convert(p):
            raise SetupError("convert the model for her engine first")
        install_launcher(p)
        _g, spm, spt = sp_paths(p)
        with open(os.path.join(H.ROOT, "profiles", "sp.toml"), encoding="utf-8") as f:
            text = f.read()
        sec = re.search(r"(?ms)^\[paths\]\n.*?(?=^\[)", text)
        body = sec.group(0)
        for key, val in (("engine_exe", engine_exe(p)), ("model", spm), ("tokenizer", spt)):
            body = re.sub(r"(?m)^%s\s*=.*$" % key, lambda _m, k=key, v=val: "%s = %s" % (k, _q(v)), body, count=1)
        text = text[:sec.start()] + body + text[sec.end():]
        # THE SETTINGS THIS MODEL RUNS WITH (2026-11-26, found by the end-to-end run): sp.toml
        # alone gave "exceeds Pmax" (4096 is shorter than a companion's system prompt), then a
        # byte-exact path not implemented for MoE experts, then garbage. The kit carries the
        # values her own stack runs this model with on a 12 GB card.
        for sect, vals in native_settings(e).items():
            for key, val in vals.items():
                text = _toml_set(text, sect, key, val)
        return _finish_profile(dst, name, text, companion, user_name, user_pronouns)
    with open(os.path.join(H.ROOT, "profiles", "companion.toml"), encoding="utf-8") as f:
        text = f.read()
    if e.get("external"):
        eng = "[engine]\nkind = \"openai\"\nbase_url = %s\nmodel = \"\"\n" % _q(base_url or "http://127.0.0.1:1234")
    else:
        cmd = engine_command(p, ctx=ctx, port=port)
        eng = ("[engine]\n# written by the setup centre (harness/setup) on %s — serve.py starts this engine\n"
               "kind = \"openai\"\nbase_url = %s\nmodel = \"\"\ncommand = [%s]\nready_s = 600\n"
               % (time.strftime("%Y-%m-%d"), _q("http://127.0.0.1:%d" % port), ", ".join(_q(x) for x in cmd)))
    # function replacements: a Windows path in the text would be read as a regex escape
    text = re.sub(r"(?ms)^\[engine\]\n.*?(?=^\[)", lambda _m: eng + "\n", text, count=1)
    return _finish_profile(dst, name, text, companion, user_name, user_pronouns)


def native_settings(e: dict, hw: Optional[dict] = None) -> dict:
    """The kit's [kv]/[decode] values for her native engine, with the expert cache scaled to
    the card: 6 GB is what a 12 GB card was tested with; below that, VRAM minus 6 (min 1)."""
    prof = json.loads(json.dumps(e.get("profile") or {}))
    kv = prof.get("kv") or {}
    if "moe_cache_gb" in kv:
        try:
            hw = hw if hw is not None else hardware()
            vram = max((g.get("vram_gb") or 0) for g in hw.get("gpus") or [{}])
        except Exception as x:   # no nvidia-smi: keep the tested value, and say so in the log
            import logging
            from harness.loud import swallowed as _sw
            _sw(logging.getLogger(__name__), "setup.native_settings", x)
            vram = 0
        if vram and vram < 12:
            kv["moe_cache_gb"] = float(max(1, int(vram) - 6))
    return prof


def _toml_val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return _q(str(v))


def _toml_set(text: str, sect: str, key: str, val) -> str:
    """`key = val` in [sect]: the line replaced where it exists, else added under the header."""
    m = re.search(r"(?ms)^\[%s\]\n.*?(?=^\[|\Z)" % re.escape(sect), text)
    line = "%s = %s" % (key, _toml_val(val))
    if not m:
        return text.rstrip("\n") + "\n\n[%s]\n%s\n" % (sect, line)
    body = m.group(0)
    if re.search(r"(?m)^%s\s*=" % re.escape(key), body):
        body = re.sub(r"(?m)^%s\s*=.*$" % re.escape(key), lambda _m: line, body, count=1)
    else:
        body = body.replace("[%s]\n" % sect, "[%s]\n%s\n" % (sect, line), 1)
    return text[:m.start()] + body + text[m.end():]


def _finish_profile(dst: str, name: str, text: str, companion: str, user_name: str,
                    user_pronouns: str) -> str:
    """[user] and [companion] for either template, then the file."""
    if user_name:
        _u = "[user]\nname = %s\npronouns = %s\n\n" % (_q(user_name), _q(user_pronouns))
        if re.search(r"(?m)^\[user\]\s*$", text):
            text = re.sub(r"(?ms)^\[user\]\n.*?(?=^\[|\Z)", lambda _m: _u, text, count=1)
        else:   # sp.toml has no [user] section: a substitution alone would silently drop you
            text = text.rstrip("\n") + "\n\n" + _u
    if companion:
        text = "[companion]\nhome = %s\n\n" % _q(companion) + text
        # with a home, the profile must not name a registry (serve.apply_home refuses two sources)
        text = re.sub(r"(?m)^registry\s*=.*$", "# registry: in the companion's home", text)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write("# %s — written by the setup centre (harness/setup) %s\n" % (name, time.strftime("%Y-%m-%d")) + text)
    return dst
