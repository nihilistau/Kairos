"""nsys, decode-dominated, armed kernels — WHERE inside decode the 2.37x lives.

The wall clock says decode is the whole remaining gap against llama.cpp. It does not say what
decode is spending it on, and the last two confident answers to that kind of question were both
wrong, so this is an instrument rather than a theory.

Shape of the run: prefill the same 3,720-token prompt (so decode happens at the depth the gap
was measured at), then generate 512 tokens. At ~16 tok/s that is ~32 s of decode against ~12 s
of prefill, so decode dominates the window — and prefill and decode use DIFFERENT kernels
(`k_attn_from_tiled_v2_T` vs `k_attn_decode_win_tiled_v2_T`), so the summary separates them by
name even where they overlap.

One warm call first: a fresh daemon has a cold expert cache, and a trace of the cold pass would
attribute PCIe stalls to decode.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("BENCH_PROFILE", "sp")   # BENCH_PROFILE=<name> for another
os.environ.setdefault("BENCH_CHARS", "14000")
import bench_ab as B  # noqa: E402

# nsys is not on PATH in a default Windows install; NSYS=<full path> if it is not.
NSYS = os.environ.get("NSYS") or "nsys"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "var", "bench", "decode_trace")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
DECODE_TOKENS = int(os.environ.get("DECODE_TOKENS", "384"))
# The first attempt used --delay=90 --duration=420 and swallowed the model load:
# 420 s of full CUDA tracing produced a stream whose importer sat at 15 GB and was
# still converting 12 minutes later. The window has to be small AND the workload has
# to be inside it deliberately, not hopefully.
DELAY, DURATION = 150, 75

env = dict(B.serve.build_env(B.CFG))
env.update(B.ARMS["on"])                       # the kernels that actually serve
_sr = os.environ.get("SystemRoot") or os.environ.get("windir")
if _sr:
    env.setdefault("SystemRoot", _sr)

cmd = [NSYS, "profile", "--trace=cuda", "--sample=none",
       "--delay=%d" % DELAY, "--duration=%d" % DURATION,
       "--cuda-memory-usage=false", "--force-overwrite=true", "-o", OUT,
       B.EXE, "start", "--model", B.CFG["paths"]["model"],
       "--tokenizer", B.CFG["paths"]["tokenizer"], "--port", str(B.PORT)]

log = open(os.path.join(os.path.dirname(OUT), "decode_daemon.log"),
           "w", encoding="utf-8")
LAUNCH = time.time()
p = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
if not B.wait_up(300):
    print("daemon did not come up")
    B.kill()
    sys.exit(1)
T0 = time.time()
print("  up; warming the expert cache", flush=True)
w = B.oneshot(8)
print("  warm pass: %d ms" % w["ms"], flush=True)
# WAIT FOR THE CAPTURE WINDOW rather than assuming the workload lands in it.
wait = (LAUNCH + DELAY + 2) - time.time()
if wait > 0:
    print("  holding %.0f s until the capture window opens" % wait, flush=True)
    time.sleep(wait)
t0 = time.time()
r = B.oneshot(DECODE_TOKENS)
print("  traced: prompt_tokens=%s  %d tokens  %d ms  (%.2f tok/s over the decode)"
      % (r.get("prompt_tokens"), DECODE_TOKENS, r["ms"],
         DECODE_TOKENS / ((time.time() - t0))), flush=True)

# kill the DAEMON and let nsys finish: killing nsys leaves a corrupt .qdstrm (2026-09-11).
subprocess.run(["taskkill", "/F", "/IM", os.path.basename(B.EXE)], capture_output=True)
try:
    p.wait(timeout=600)
except subprocess.TimeoutExpired:
    print("  nsys still finalising")
print("  report: %s.nsys-rep" % OUT)
