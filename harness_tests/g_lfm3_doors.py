"""G-LFM3-DOORS — serve.py starts her two LFM3 sidecars on the CPU, or says why it did not.

WHAT THIS HOLDS (2026-10-29, LFM3 plan Task 2). `launch_lfm3_audio` (ears + voice: ONE resident
llama-server on the LFM3-Audio GGUF + --mmproj, ASR on /v1/chat/completions, speech on /tts) and
`launch_lfm3_chat` (the optional LFM3-1.7B librarian door) are modelled on `launch_aux_embed`:
off when disarmed, adopt a server already answering /health, name the missing file, otherwise
Popen a detached CPU llama-server. CPU is the point: the 2026-07-31 tts-server sat on the 2060
beside the model and faulted the daemon, so NO -ngl above 0 may ever appear in either argv.

Popen and wait_http are stubbed — this gate never starts a real server and never touches :8811.
"""
from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _gate import check, finish, sandbox, utf8_stdout  # noqa: E402

utf8_stdout()
sandbox("g_lfm3_doors")
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import serve  # noqa: E402

tmp = tempfile.mkdtemp(prefix="g_lfm3_doors_")
os.makedirs(os.path.join(tmp, "aux"), exist_ok=True)
serve.VAR = tmp                      # logs + pidfiles land here, not in her var/


class _P:
    pid = 4242


calls: list = []
live = {"up": False}


def _popen(argv, **kw):
    calls.append(list(argv))
    return _P()


serve.subprocess.Popen = _popen
serve.wait_http = lambda url, secs=1: live["up"]

exe = os.path.join(tmp, "llama-server.exe")
files = {k: os.path.join(tmp, k + ".gguf") for k in ("audio", "mmproj", "chat")}
for p in [exe, *files.values()]:
    open(p, "w").close()


def prof(**over):
    d = {"enabled": True, "llama_dir": tmp.replace("\\", "/"),
         "audio_gguf": files["audio"], "audio_mmproj": files["mmproj"], "chat_gguf": files["chat"],
         "audio_url": "http://127.0.0.1:8813", "chat_url": "http://127.0.0.1:8814",
         "threads": 8, "voice": "female", "lang": "en"}
    d.update(over)
    return {"lfm3": d}


def flat(argv):
    return " ".join(argv)


print("1. DISARMED")
calls.clear(); live["up"] = False
a, ch = serve.launch_lfm3_audio(prof(enabled=False), {}), serve.launch_lfm3_chat(prof(enabled=False), {})
check("off when disabled", a["state"] == "off" and ch["state"] == "off" and not calls, (a, ch, calls))
a = serve.launch_lfm3_audio({}, {})
check("off when the [lfm3] table is absent", a["state"] == "off" and not calls, a)

print("2. ADOPT")
calls.clear(); live["up"] = True
a, ch = serve.launch_lfm3_audio(prof(), {}), serve.launch_lfm3_chat(prof(), {})
check("adopts a live server", a["state"] == "adopted" and ch["state"] == "adopted" and not calls, (a, ch, calls))

print("3. MISSING FILES ARE NAMED")
import io, contextlib  # noqa: E402
calls.clear(); live["up"] = False
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    a = serve.launch_lfm3_audio(prof(audio_gguf=os.path.join(tmp, "nope.gguf")), {})
check("missing file is named", a["state"] == "missing" and "nope.gguf" in buf.getvalue() and not calls,
      (a, buf.getvalue()))
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ch = serve.launch_lfm3_chat(prof(llama_dir=os.path.join(tmp, "nodir")), {})
check("missing llama-server is named", ch["state"] == "missing" and "llama-server" in buf.getvalue(),
      (ch, buf.getvalue()))

print("4. THE ARGV")
calls.clear(); live["up"] = False
a = serve.launch_lfm3_audio(prof(), {})
av = calls[0] if calls else []


def gpu_layers(argv):
    """True when argv offloads anything: a -ngl/--n-gpu-layers value above 0 (or 'all'/'auto')."""
    for i, t in enumerate(argv):
        if t in ("-ngl", "--n-gpu-layers", "--gpu-layers") and i + 1 < len(argv):
            v = argv[i + 1]
            if not v.isdigit() or int(v) > 0:
                return True
    return False


bad_ngl = gpu_layers(av)
check("starts on CPU with mmproj",
      a["state"] == "starting" and "--mmproj" in av and av[av.index("--mmproj") + 1] == files["mmproj"]
      and "--port" in av and av[av.index("--port") + 1] == "8813"
      and "--threads" in av and av[av.index("--threads") + 1] == "8" and not bad_ngl, (a, av))
check("audio door is a log+pidfile child of nobody",
      os.path.isfile(os.path.join(tmp, "lfm3-audio.log"))
      and os.path.isfile(os.path.join(tmp, "aux", "lfm3-audio.pid")), os.listdir(tmp))
calls.clear()
ch = serve.launch_lfm3_chat(prof(), {})
cv = calls[0] if calls else []
check("chat door uses suggested sampling",
      ch["state"] == "starting" and "--temp" in cv and cv[cv.index("--temp") + 1] == "0.1"
      and cv[cv.index("--top-k") + 1] == "50" and cv[cv.index("--repeat-penalty") + 1] == "1.1"
      and cv[cv.index("--port") + 1] == "8814" and "--mmproj" not in cv
      and not gpu_layers(cv), (ch, cv))

# NOTHING SHE SAYS IN THE DOOR'S LOG (2026-10-29, off the record speaks through lfm3). At the
# info threshold (3) llama-server logs timings and token counts and no request text — read off
# var/lfm3-audio.log after a day of /tts and ASR calls. Above it (4 trace, 5 debug, -v) it logs
# request bodies, and LLAMA_ARG_LOG_VERBOSITY can raise it from the environment. The pin is on
# the command line, which wins over the env; --log-prompts-dir must never appear.


def _lv(argv):
    return argv[argv.index("--log-verbosity") + 1] if "--log-verbosity" in argv else None


_loud = ("-v", "--verbose", "--log-verbose", "--log-prompts-dir", "--slot-save-path")
check("both doors pin the log at info (3): no request text in var/lfm3-*.log, env cannot raise it",
      _lv(av) == "3" and _lv(cv) == "3"
      and not any(t in av or t in cv for t in _loud), (_lv(av), _lv(cv)))

# NO HOST PROMPT CACHE ON THE AUDIO DOOR (review round 1): llama-server keeps finished prompts
# in a RAM cache (8 GiB by default) — her sentences and his recordings must not outlive their
# request there. The slot's own KV of the last request remains (ANON-MODE.md, a known limit).
check("the audio door starts with no host prompt cache (--cache-ram 0, --no-cache-prompt)",
      "--cache-ram" in av and av[av.index("--cache-ram") + 1] == "0" and "--no-cache-prompt" in av, av)

print("5. ENV ROWS")
# A SYNTHETIC [lfm3] TABLE, NOT HERS (2026-10-29, the export): reading her live profile made
# this leg red inside Kairos, which ships no companion — and red here the day he disarms the
# doors. The leg is about build_env's mapping, so it feeds build_env a table it controls.
import copy as _copy  # noqa: E402
_prof = _copy.deepcopy(serve.load_profile("companion"))
_prof["lfm3"] = {"enabled": True, "llama_dir": "llama-cpp", "audio_gguf": "models/a.gguf",
                 "audio_mmproj": "models/mm.gguf", "chat_gguf": "models/c.gguf",
                 "audio_url": "http://127.0.0.1:8813", "chat_url": "http://127.0.0.1:8814",
                 "threads": 8, "voice": "female", "lang": "en"}
env = serve.build_env(_prof)
keys = ["SP_LFM3", "SP_LFM3_DIR", "SP_LFM3_AUDIO_GGUF", "SP_LFM3_AUDIO_MMPROJ", "SP_LFM3_CHAT_GGUF",
        "SP_LFM3_AUDIO_URL", "SP_LFM3_CHAT_URL", "SP_LFM3_THREADS", "SP_LFM3_VOICE", "SP_LFM3_LANG"]
check("env rows exist", all(k in env for k in keys), [k for k in keys if k not in env])
check("env carries the profile's doors", env.get("SP_LFM3_AUDIO_URL") == "http://127.0.0.1:8813"
      and env.get("SP_LFM3_CHAT_URL") == "http://127.0.0.1:8814" and env.get("SP_LFM3") == "1",
      {k: env.get(k) for k in keys})

print("6. WHICH LOCAL VOICE A PROFILE WITHOUT LFM3 GETS")
# (final review, 2026-10-29) SP_TTS_LOCAL defaulted to lfm3 for EVERY profile, so sp and
# companion — no [lfm3] table — tried a door nobody started on every sentence (a hop and a
# log line each) before reaching voxtral. The default follows [lfm3].enabled; an explicit
# [tts].local still wins.
import copy  # noqa: E402
_base = serve.load_profile("companion")


def _local(lfm3=None, tts_local=None):
    c = copy.deepcopy(_base)
    c.pop("lfm3", None)
    if lfm3 is not None:
        c["lfm3"] = lfm3
    c.setdefault("tts", {}).pop("local", None)
    if tts_local is not None:
        c["tts"]["local"] = tts_local
    return serve.build_env(c).get("SP_TTS_LOCAL")


_got = {"absent": _local(), "disabled": _local({"enabled": False}), "enabled": _local({"enabled": True}),
        "explicit": _local(None, "lfm3"), "explicit_vox": _local({"enabled": True}, "voxtral")}
check("no [lfm3] (or a disabled one) means the local voice is voxtral",
      _got["absent"] == "voxtral" and _got["disabled"] == "voxtral", _got)
check("[lfm3] enabled means lfm3, and an explicit [tts].local wins either way",
      _got["enabled"] == "lfm3" and _got["explicit"] == "lfm3" and _got["explicit_vox"] == "voxtral", _got)

finish("G-LFM3-DOORS")
