"""ONE workload, both arms, same process shape — the combined measurement that was owed.

The engine README's 36,573 -> ~13,300 ms was stitched from two traces: the attention work was
measured before the fp16 GEMM existed, and the GEMM work was measured after it. Nobody has ever
run BOTH kernels against BOTH kernels off on one prompt in one sitting, which is what a reader
assumes the table means.

Arms:
    off   attn_tile=0    attn_v2=0  gemm_f16=0     the kernels an adopter gets out of the box
    on    attn_tile=1024 attn_v2=1  gemm_f16=1     what upstream actually runs

The daemon is launched DIRECTLY, not through serve.py, because serve.py maps these from the
profile and this needs them varied without editing her profile. Same binary, same weights, same
prompt, same max_tokens, same greedy sampling; only the three knobs move.

The 2026-09-12 table in the engine README was produced by this file with
`BENCH_PROFILE=companion BENCH_CHARS=14000 BENCH_REPEATS=3`, and the prefill/decode split
beside it by `bench_split.py` with `BENCH_REPEATS=2`. The llama.cpp column is
`llama-bench -m <gguf> -ncmoe 8 -p 3720 -n 128` and `-p 0 -n 128 -d 3720` for the
depth-matched decode row — the default `tg128` runs at depth 0 and is not comparable.
"""
import io
import json
import os
import subprocess
import sys
import time
import tomllib
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
S = os.path.join(ROOT, "var", "bench")
os.makedirs(S, exist_ok=True)

import serve  # noqa: E402

# WHICH PROFILE supplies the paths and the base env. Defaults to the public
# one so this runs in a clone; the operator's own profile is an env away.
PROFILE = os.environ.get("BENCH_PROFILE", "sp")
CFG = tomllib.load(open(os.path.join(ROOT, "profiles", PROFILE + ".toml"), "rb"))
PORT = int(CFG["serve"]["port"])
EXE = CFG["paths"]["engine_exe"].replace("/", "\\")
ARMS = {
    "off": {"SP_G4_ATTN_TILE": "0", "SP_G4_ATTN_V2": "0", "SP_G4_GEMM_F16": "0"},
    "on":  {"SP_G4_ATTN_TILE": "1024", "SP_G4_ATTN_V2": "1", "SP_G4_GEMM_F16": "1"},
}
REPEATS = int(os.environ.get("BENCH_REPEATS", "3"))
TARGET_TOKENS = 3750


def prompt_text():
    """VARIED English at a fixed length, not repeated filler.

    The first cut repeated one sentence. Repetition is the wrong stimulus for a MoE: routing
    is content-dependent, so a prompt that says the same thing 500 times exercises a handful
    of experts and flatters (or punishes) the expert-streaming path in a way no real turn
    does. This reads the repo's own changelog — ordinary varied prose, deterministic, and the
    same bytes for both arms, which is the only property the comparison actually needs.
    """
    _src = os.path.join(ROOT, "docs", "CHANGELOG.md")
    if not os.path.exists(_src):
        _src = os.path.join(ROOT, "CHANGELOG.md")      # the exported layout
    txt = io.open(_src, encoding="utf-8").read()
    txt = " ".join(txt.split())          # collapse layout; keep the words
    return txt[:CHARS]


CHARS = int(os.environ.get("BENCH_CHARS", "14000"))
PROMPT = prompt_text()


def wait_up(timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/v1/metrics" % PORT, timeout=3).read()
            return True
        except Exception:
            time.sleep(2)
    return False


def oneshot(max_tokens=128):
    body = json.dumps({"messages": [{"role": "user", "content": PROMPT}],
                       "max_tokens": max_tokens, "temperature": 0.0,
                       "deadline_s": 900.0}).encode()
    req = urllib.request.Request("http://127.0.0.1:%d/v1/oneshot" % PORT, data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    r = json.loads(urllib.request.urlopen(req, timeout=1200).read())
    r["wall_ms"] = int((time.time() - t0) * 1000)
    return r


def kill():
    subprocess.run(["taskkill", "/F", "/IM", os.path.basename(EXE)], capture_output=True)
    time.sleep(3)


def run_arm(name, nsys_out=None):
    env = dict(serve.build_env(CFG))
    env.update(ARMS[name])
    # CreateProcess needs SystemRoot; build_env strips what the profile does not map.
    _sr = os.environ.get("SystemRoot") or os.environ.get("windir")
    if _sr:
        env.setdefault("SystemRoot", _sr)
    cmd = [EXE, "start", "--model", CFG["paths"]["model"],
           "--tokenizer", CFG["paths"]["tokenizer"], "--port", str(PORT)]
    if nsys_out:
        nsys = (r"C:\Program Files\NVIDIA Corporation\Nsight Systems 2025.6.3"
                r"\target-windows-x64\nsys.exe")
        # delay past model load, exactly as the 09-11 trace did: capturing the load swamps
        # the kernels with H2D and makes the two arms incomparable on anything but total.
        cmd = [nsys, "profile", "--trace=cuda,nvtx", "--sample=none",
               "--delay=95", "--duration=180", "--force-overwrite=true",
               "-o", nsys_out] + cmd
    log = open(os.path.join(S, "daemon_%s.log" % name), "w", encoding="utf-8")
    p = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
    if not wait_up():
        print("  %s: daemon did not come up" % name)
        kill()
        return []
    rows = []
    for i in range(REPEATS):
        r = oneshot()
        rows.append(r)
        print("    %s run %d: prompt_tokens=%s batched=%s engine_ms=%s wall_ms=%s"
              % (name, i + 1, r.get("prompt_tokens"), r.get("batched"),
                 r.get("ms"), r["wall_ms"]), flush=True)
    if nsys_out:
        # nsys must be allowed to finish: killing IT leaves a corrupt .qdstrm (learned 09-11).
        subprocess.run(["taskkill", "/F", "/IM", os.path.basename(EXE)], capture_output=True)
        p.wait(timeout=300)
    else:
        kill()
    time.sleep(3)
    return rows


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "time"
    out = {}
    for arm in ("off", "on"):
        print("  --- arm %s ---" % arm, flush=True)
        out[arm] = run_arm(arm, nsys_out=(os.path.join(S, "trace_" + arm)
                                          if mode == "nsys" else None))
    json.dump(out, open(os.path.join(S, "bench_%s.json" % mode), "w"), indent=1)
    print()
    for arm in ("off", "on"):
        ms = [r["ms"] for r in out.get(arm, []) if "ms" in r]
        if ms:
            print("  %-4s engine_ms  min %d  med %d  max %d   (n=%d, prompt_tokens=%s)"
                  % (arm, min(ms), sorted(ms)[len(ms) // 2], max(ms), len(ms),
                     out[arm][0].get("prompt_tokens")))
    if out.get("off") and out.get("on"):
        a = min(r["ms"] for r in out["off"])
        b = min(r["ms"] for r in out["on"])
        print("  speedup (min/min): %.2fx" % (a / b))
