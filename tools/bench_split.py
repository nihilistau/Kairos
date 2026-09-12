"""Split the engine's oneshot into PREFILL and DECODE so it can be put beside llama-bench.

`/v1/oneshot` returns one number for the whole call. llama-bench reports pp and tg separately,
so comparing them directly compares a sum against two parts and invites exactly the stitched
arithmetic this whole exercise is correcting.

Two calls on the same loaded daemon, same prompt:
    max_tokens = 1     -> prefill + 1 token
    max_tokens = 128   -> prefill + 128 tokens
The difference is 127 decode steps; the first is prefill plus one step. Same process, same
weights, same cache state within the arm, so the subtraction is legitimate.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench_ab as B  # noqa: E402

ARM = os.environ.get("BENCH_ARM", "on")
REPEATS = int(os.environ.get("BENCH_REPEATS", "2"))


def run():
    import subprocess
    import time
    env = dict(B.serve.build_env(B.CFG))
    env.update(B.ARMS[ARM])
    # CreateProcess needs SystemRoot; build_env strips what the profile does not map.
    _sr = os.environ.get("SystemRoot") or os.environ.get("windir")
    if _sr:
        env.setdefault("SystemRoot", _sr)
    log = open(os.path.join(B.S, "daemon_split_%s.log" % ARM), "w", encoding="utf-8")
    subprocess.Popen([B.EXE, "start", "--model", B.CFG["paths"]["model"],
                      "--tokenizer", B.CFG["paths"]["tokenizer"], "--port", str(B.PORT)],
                     env=env, stdout=log, stderr=subprocess.STDOUT)
    if not B.wait_up():
        print("daemon did not come up")
        return
    out = {"arm": ARM, "short": [], "long": []}
    # one warm pass first: run 1 in a fresh daemon pays a cold expert cache, and mixing that
    # into the subtraction would attribute cache misses to decode.
    B.oneshot(8)
    for _ in range(REPEATS):
        a = B.oneshot(1)
        b = B.oneshot(128)
        out["short"].append(a["ms"])
        out["long"].append(b["ms"])
        print("  %s: prefill+1 = %6d ms   prefill+128 = %6d ms   -> 127 decode = %6d ms"
              % (ARM, a["ms"], b["ms"], b["ms"] - a["ms"]), flush=True)
    B.kill()
    time.sleep(2)
    s, l = min(out["short"]), min(out["long"])
    dec = l - s
    pt = 3720
    print()
    print("  prompt_tokens        : %d" % pt)
    print("  prefill (+1 tok)     : %6d ms   -> %.1f tok/s" % (s, pt / (s / 1000.0)))
    print("  127 decode steps     : %6d ms   -> %.2f tok/s" % (dec, 127 / (dec / 1000.0)))
    out["prefill_ms"], out["decode127_ms"] = s, dec
    json.dump(out, open(os.path.join(B.S, "split_%s.json" % ARM), "w"), indent=1)


if __name__ == "__main__":
    run()
