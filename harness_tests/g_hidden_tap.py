"""G-HIDDEN-TAP — the forensics tap must exist on EVERY prefill path, not just the slow one.

WHAT WENT WRONG (2026-09-09). `SP_HIDDEN_DUMP` opens the dump file inside
`gemma4_kv_prefill`, and `g4_kv_step` streams the decode steps through the handle that
opens. That was correct when it was written and quietly stopped being reachable: the daemon
learned to batch (`gemma4_kv_prefill_batched_from`, 24 ms/tok against 141 per-token), the
batched extern had no tap, and so BOTH `/v1/chat` and `/v1/oneshot` produced an empty dump.

The instrument did not fail loudly. It produced a file, and the only capture in the tree was
a July prefill that turned out to be 97% one 11-token loop from a different model — measured
as participation ratio 3.39 and "88% of variance in 10 dimensions", which read as a
confirmation of a 10-dimensional-attractor claim until the period was found.
Receipt: docs/PHASE-SPACE-2026-09-09.md.

WHY THIS GATE IS A SOURCE GATE, STATED PLAINLY. The subject is CUDA that needs an RTX 2060,
a 14 GB model and a five-minute prefill; there is no offline way to drive it. So this asserts
the SHAPE — that every extern which commits prefill positions also carries the tap, and that
the decode hand-off exists on each. That is weaker than driving it, and the honest
verification is in the receipt: `[g4-kv] hidden dump (batched): 102 positions at P=0` beside
`BATCH-PREFILL: 102 tokens batched` at 24 ms/tok, and the two paths agreeing on the same
prompt (PR 58.7 per-token vs 54.7 batched, var@10 33.4% vs 34.7%).

What this gate CAN do that a human re-reading cannot: fail the day a THIRD prefill entry is
added without a tap. That is the whole failure mode.

Lane: OFFLINE (reads the engine source; no GPU, no model).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness_tests._gate import sandbox, check, finish, skip  # noqa: E402

sandbox()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CU = os.path.join(ROOT, "engine", "src", "backends", "cuda", "cuda_forward.cu")

if not os.path.exists(CU):
    # engine/ is a nested clone and is not in the public tree (kairos-export ships no
    # engine/), so a Kairos checkout legitimately has nothing to check here.
    skip("engine/src/backends/cuda/cuda_forward.cu absent (engine not cloned)", "G-HIDDEN-TAP")

src = open(CU, encoding="utf-8", errors="replace").read()
# Comments are stripped before any counting: this file DESCRIBES the tap at length, and a
# prose mention would satisfy a naive grep. The trap this repo keeps stepping on.
code = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
code = re.sub(r"//[^\n]*", " ", code)


def body_of(sig):
    """The source of one extern, by brace depth."""
    i = code.find(sig)
    if i < 0:
        return ""
    d, j = 0, i
    while j < len(code):
        if code[j] == "{":
            d += 1
        elif code[j] == "}":
            d -= 1
            if d == 0:
                return code[i:j + 1]
        j += 1
    return code[i:]


print("1. EVERY PREFILL ENTRY THAT COMMITS POSITIONS CARRIES THE TAP")
# The entries that advance dpos over n prompt positions. `gemma4_kv_prefill_batched` is
# excluded deliberately: it is a chunking wrapper that calls _from, which is tapped.
ENTRIES = ('extern "C" int gemma4_kv_prefill(',
           'extern "C" int gemma4_kv_prefill_batched_from(')
for sig in ENTRIES:
    nm = sig.split()[-1].rstrip("(")
    b = body_of(sig)
    check("%-34s exists" % nm, bool(b))
    check("%-34s opens the dump on SP_HIDDEN_DUMP" % nm, 'getenv("SP_HIDDEN_DUMP")' in b,
          "an untapped prefill path is an instrument that returns an empty file")
    check("%-34s hands off to the decode stream" % nm,
          'getenv("SP_HIDDEN_DUMP_DECODE")' in b and "g_hd_stream" in b,
          "without the hand-off the tap captures prefill and drops every decode step")

print("\n2. THE CHUNKING WRAPPER DELEGATES RATHER THAN DUPLICATING")
w = body_of('extern "C" int gemma4_kv_prefill_batched(')
check("gemma4_kv_prefill_batched calls _from", "gemma4_kv_prefill_batched_from" in w)
check("...and does NOT carry its own copy of the tap",
      'getenv("SP_HIDDEN_DUMP")' not in w,
      "two copies of the open/truncate rule is the bug this tree is named for")

print("\n3. THE DECODE WRITER'S PRECONDITIONS ARE SATISFIABLE FROM BOTH PATHS")
# g4_kv_step guards on `g_hd_f && g_hd_dev` and streams out of g_hd_host. A path that opens
# the file but never allocates those two captures the prefill and silently drops the decode
# steps -- which is exactly half-wiring the instrument again, one layer down.
for sig in ENTRIES:
    nm = sig.split()[-1].rstrip("(")
    b = body_of(sig)
    check("%-34s allocates g_hd_dev" % nm, "cudaMalloc(&g_hd_dev" in b)
    check("%-34s allocates g_hd_host" % nm, "g_hd_host = (float *)malloc" in b)
step = body_of("static int g4_kv_step(") or body_of("int g4_kv_step(")
check("g4_kv_step guards on the buffers it uses",
      "g_hd_f" in step and "g_hd_dev" in step and "g_hd_host" in step, "the decode writer")

print("\n4. DEFAULT-OFF IS STRUCTURAL, NOT A PROMISE")
# Every tap site must sit behind the getenv, so an unset env is byte-identical.
for sig in ENTRIES:
    nm = sig.split()[-1].rstrip("(")
    b = body_of(sig)
    at = b.find('getenv("SP_HIDDEN_DUMP")')
    wr = b.find("fwrite(g_hd_host")
    check("%-34s writes only after the env check" % nm, at >= 0 and wr > at,
          "a write outside the guard would change a default run's bytes")

print("\n5. AND THE BATCHED PATH TRUNCATES ONCE, NOT PER CHUNK")
b = body_of('extern "C" int gemma4_kv_prefill_batched_from(')
check("truncates on P==0 and appends otherwise",
      re.search(r"P\s*==\s*0", b) is not None and '"ab"' in b and '"wb"' in b,
      "chunked prefill truncating per call would leave only the final chunk on disk")

finish("G-HIDDEN-TAP")
