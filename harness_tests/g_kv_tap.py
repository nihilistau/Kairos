"""G-KV-TAP — the two K/V residual taps stay off, and stay honest about alignment.

`SP_DUMP_KV` (prefill) and `SP_DUMP_KV_DECODE` (the resident decode step) write raw residual
rows out of `cuda_forward.cu`. They are diagnostics: unarmed they must cost nothing and change
nothing, and armed they must not hand back rows a reader can silently misalign.

WHY A GATE RATHER THAN TRUST. The two defects these guard both already happened in this tree,
on these taps, within one day:

  DEFAULT-OFF MUST BE STRUCTURAL. `g_hidden_tap` exists because a tap was armed and wrote
  nothing while reporting success. The same shape applies here in reverse: the getenv has to
  sit BEFORE the D2H and the fopen, or an unarmed build pays a full stream sync per layer per
  token. On the decode path that is once per generated token, thirty times over.

  ROW i IS NOT POSITION i. The prefill tap is REFUSED unless P == 0, because persist-KV
  reseams and a suffix dump compared row-for-row produces a smooth-looking error curve that is
  entirely an artefact -- a reading that was published and withdrawn twice (see
  docs/LOGIT-LENS-CALIBRATION-2026-09-18.md). The decode tap cannot refuse, because every
  generated token has a real position, so it APPENDS and writes an int32 `.pos` sidecar in
  lockstep instead. Either the refusal or the sidecar going missing turns a careful measurement
  back into the defect it was built to avoid.

Source-shaped and offline: the live check needs a GPU and a 26B checkpoint. Comments are
stripped first -- this file and cuda_forward.cu both describe the taps at length and a prose
mention would satisfy a naive grep (the trap this tree keeps stepping on).
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
    skip("engine/src/backends/cuda/cuda_forward.cu absent (engine not cloned)", "G-KV-TAP")

src = open(CU, encoding="utf-8", errors="replace").read()
code = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
code = re.sub(r"//[^\n]*", " ", code)


def body_of(sig, src_text=code):
    """The brace-balanced body following a signature, so a leg cannot match another function.

    SKIPS FORWARD DECLARATIONS. `g4_kv_step` appears twice -- a prototype (`...);`) and the
    definition -- and taking the first match walked past the prototype's semicolon to some
    unrelated later brace, which made section 5 fail on correct code. A gate that cannot find
    the function it guards reports a defect that is its own."""
    i, j = -1, -1
    start = 0
    while True:
        i = src_text.find(sig, start)
        if i < 0:
            return ""
        j = src_text.find("{", i)
        semi = src_text.find(";", i)
        if j >= 0 and (semi < 0 or j < semi):
            break                       # a real body, not `...);`
        start = i + len(sig)
    if j < 0:
        return ""
    depth, k = 0, j
    while k < len(src_text):
        if src_text[k] == "{":
            depth += 1
        elif src_text[k] == "}":
            depth -= 1
            if depth == 0:
                return src_text[j:k + 1]
        k += 1
    return src_text[j:]


tap = body_of("static void g4_dump_kv_tap_at(")

print("1. THE TAP EXISTS AND IS ONE WRITER")
check("g4_dump_kv_tap_at is present", tap != "",
      "the shared writer was renamed or removed; this gate is measuring nothing")
check("the prefill entry point delegates rather than copying the writer",
      "g4_dump_kv_tap_at(" in body_of("static void g4_dump_kv_tap("),
      "two fopen/D2H/fwrite implementations would drift on what a row means (AGENTS.md sec 0)")

print("\n2. UNARMED COSTS NOTHING: THE ENV CHECK PRECEDES EVERY EXPENSIVE CALL")
gate_at = tap.find('getenv("SP_DUMP_KV")')
check("the base-path getenv is present", gate_at >= 0)
for expensive, why in ((("cudaMemcpy", "cudaStreamSynchronize"), "a device sync/copy"),
                       (("fopen",), "a file open"),
                       (("malloc",), "a host allocation")):
    firsts = [tap.find(e) for e in expensive if tap.find(e) >= 0]
    check("%s happens only after the env check" % why,
          gate_at >= 0 and all(f > gate_at for f in firsts),
          "an unarmed build would pay it once per layer per token")

print("\n3. THE PREFILL TAP REFUSES A RESEAM; THE DECODE TAP CARRIES POSITIONS")
check("a non-zero start position is refused when not appending",
      re.search(r"if\s*\(\s*!append\s*&&\s*pos\s*!=\s*0\s*\)", tap) is not None,
      "without this, a persist-KV suffix dump is compared row-for-row against a full one and "
      "the artefact looks like an error that grows with position")
check("the appending mode writes a .pos sidecar", '".pos"' in tap or ".pos" in tap,
      "one row per generated token with no position map is only alignable by guessing")
check("the sidecar is int32, matching what readers unpack", "int32_t" in tap,
      "tools read it with struct '<i'; a width change here silently shifts every position")
check("append picks the file mode", re.search(r'append\s*\?\s*"ab"\s*:\s*"wb"', tap) is not None,
      "a truncating decode tap would keep only the last token; an appending prefill tap would "
      "concatenate runs into one file that looks like a longer single run")

print("\n4. EVERY KNOB IS DEFAULT-OFF")
for env, shape in (("SP_DUMP_KV", "base path unset => return"),
                   ("SP_DUMP_KV_DECODE", "decode tap unset => no call"),
                   ("SP_PROBE_KV_F16", "probe fp16 round unset => no-op")):
    check("%s is read via getenv and defaults off (%s)" % (env, shape),
          ('getenv("%s")' % env) in code,
          "an unmapped or always-on knob changes the null floor")
check("SP_PROBE_KV_F16 arms only on an explicit 1",
      re.search(r'getenv\("SP_PROBE_KV_F16"\)\s*;\s*\w+\s*=\s*\(\w+\s*&&\s*\*\w+\s*==\s*.1.\)',
                code) is not None
      or re.search(r"SP_PROBE_KV_F16[^;]*;[^;]*==\s*'1'", code) is not None,
      "a bare presence test would arm it for SP_PROBE_KV_F16=0")

print("\n5. THE DECODE TAP IS ON THE RESIDENT STEP, NOT A SECOND FORWARD")
step = body_of("static int g4_kv_step(sp_g4_kv *s, int do_head)")
check("g4_kv_step calls the tap", "g4_dump_kv_tap_at(" in step,
      "the whole point of this tap is that it reads the forward that answers /v1/chat; on any "
      "other path the probe-vs-served error this tree measured at ~1.21x per layer applies")
check("it passes the step's own position, not a row index",
      re.search(r'g4_dump_kv_tap_at\("decode"[^;]*s->dpos_host', step) is not None,
      "a row index would be wrong the moment a reseam skipped a position")

finish("G-KV-TAP")
