"""G-FLAT-ATTN — no native profile can ask for the attention kernel that cannot launch. OFFLINE.

2026-11-26. `profiles/sp.toml`'s own settings made sp-daemon answer "17 plus 73421 is 42" on
the Gemma 4 your model. Flipping its knobs one at a time from the tested kit settings found ONE:
`attn_tile = 0`. That selects the flat decode-attention kernel, which asks for Pmax*4 bytes of
dynamic shared memory; CUDA refuses more than 48 KB (static shared included) without an opt-in
the engine does not make, so above Pmax 12096 every decode-step launch fails (12288, exactly
48 KB of scores, was measured failing: `attn_shm=49152`) and the daemon serves stale attention. Its
own log said so, once: `FLOAT ATTN LAUNCH FAILED: cudaErrorInvalidValue (... attn_shm=80000)`.

The control at the bound found a SECOND defect: at Pmax 12096 the flat kernels answer correctly
with seg_graph off and "[laugh] [laugh] [laugh]" with it on. With a ring, the SWA layers take the
flat ring kernel, whose context length is a HOST launch argument, so a segment graph replays one
token's context forever. The door refuses that pair too.

  §1 the door: build_env REFUSES kind sp + attn_tile 0 + pmax above the bound, naming the knob;
     accepts the flat kernel AT the bound, and the tiled kernel at any pmax
     ...and REFUSES attn_tile 0 + seg_graph + a ring; accepts either one alone
  §2 every tracked native profile (sp.toml first) obeys both rules as written on disk
  §3 the bound is the engine's: Pmax*4 plus the kernel's static shared stays under 48 KB, the
     flat kernel still sizes its shared memory by Pmax, and nothing opts it into more (skipped where engine/ is not in the tree)
  §4 the engine holds it too (the next engine release): a flat call site that cannot fit gets the tiled
     kernel (g4_attn_tile_for, its ceiling agreeing with the door's), and segment graphs refuse
     the flat ring kernel. The door stays for binaries released before that.

    python harness_tests/g_flat_attn.py
"""
import copy
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from harness_tests._gate import sandbox, check, finish, omit, utf8_stdout  # noqa: E402

utf8_stdout()
SB = sandbox("g_flat_attn")  # FIRST, before any harness. import

try:
    import tomllib
except ImportError:                                   # pragma: no cover
    import tomli as tomllib  # type: ignore
import serve  # noqa: E402

BOUND = serve.FLAT_ATTN_PMAX_MAX


def _env(tile, pmax, kind="sp", seg=False, ring_w=2048):
    c = copy.deepcopy(serve.load_profile("sp"))
    c.setdefault("engine", {})["kind"] = kind
    c["decode"]["attn_tile"] = tile
    c["decode"]["seg_graph"] = seg
    c["kv"]["pmax"] = pmax
    c["kv"]["ring_w"] = ring_w
    try:
        serve.build_env(c)
        return None
    except SystemExit as ex:
        return str(ex)


print("§1 the door")
why = _env(0, 20000)
check("attn_tile 0 at pmax 20000 is REFUSED (the measured garbage)", why is not None, why)
check("...and the refusal names the knob and the way out",
      bool(why) and "attn_tile" in why and "1024" in why and str(BOUND) in why, why)
why = _env(0, BOUND + 1)
check("one position over the bound is refused", why is not None and "attn_tile" in why, why)
why = _env(0, BOUND)
check("the flat kernel AT the bound is allowed (12096: measured coherent)",
      why is None or "attn_tile" not in why, why)
why = _env(1024, 20000)
check("the tiled kernel at pmax 20000 is allowed", why is None or "attn_tile" not in why, why)
why = _env(0, 20000, kind="openai")
check("an external engine is not held to a kernel it does not run",
      why is None or "attn_tile" not in why, why)
why = _env(0, BOUND, seg=True)
check("flat kernel + seg_graph + ring is REFUSED (the measured [laugh] loop)",
      why is not None and "seg_graph" in why and "1024" in why, why)
why = _env(1024, 20000, seg=True)
check("the tiled kernel with seg_graph is allowed (her stack runs it)",
      why is None or "seg_graph" not in why, why)
why = _env(0, BOUND, seg=True, ring_w=0)
check("flat + seg_graph without a ring is allowed (no flat RING kernel to bake)",
      why is None or "seg_graph" not in why, why)

print("§2 every tracked native profile")
_seen = []
for p in sorted(glob.glob(os.path.join(ROOT, "profiles", "*.toml"))):
    with open(p, "rb") as f:
        d = tomllib.load(f)
    if str(d.get("engine", {}).get("kind") or "sp") != "sp":
        continue
    _seen.append(os.path.basename(p))
    tile = int(d.get("decode", {}).get("attn_tile", 0) or 0)
    pmax = int(d.get("kv", {}).get("pmax", 0) or 0)
    seg = bool(d.get("decode", {}).get("seg_graph", False))
    ring = int(d.get("kv", {}).get("ring_w", 0) or 0)
    check("%s: attn_tile %d, pmax %d -> the kernel can launch" % (os.path.basename(p), tile, pmax),
          tile > 0 or pmax <= BOUND, (tile, pmax))
    check("%s: no flat ring kernel under segment graphs" % os.path.basename(p),
          tile > 0 or not seg or ring == 0, (tile, seg, ring))
check("sp.toml is among them (the public engine door)", "sp.toml" in _seen, _seen)
with open(os.path.join(ROOT, "profiles", "sp.toml"), "rb") as f:
    _sp = tomllib.load(f)
check("sp.toml ships the tiled kernel", int(_sp["decode"].get("attn_tile", 0) or 0) > 0,
      _sp["decode"].get("attn_tile"))
check("sp.toml's pmax holds a companion's system prompt (~7.5k tokens)",
      int(_sp["kv"].get("pmax", 0)) >= 8192, _sp["kv"].get("pmax"))
check("sp.toml asks for certified-float turns (byte-exact is refused on a MoE)",
      _sp["decode"].get("byteexact") is False, _sp["decode"].get("byteexact"))

print("§3 the bound is the engine's")
check("FLAT_ATTN_PMAX_MAX leaves room under 48 KB for the static g_sum (12288 measured failing)",
      0 < BOUND and BOUND * 4 + 4 <= 48 * 1024, BOUND)
cu = os.path.join(ROOT, "engine", "src", "backends", "cuda", "cuda_forward.cu")
if not os.path.exists(cu):
    omit("engine source", "engine/ is not in this tree (the public export ships without it)")
else:
    with open(cu, encoding="utf-8", errors="replace") as f:
        src = f.read()
    # comments out first: the engine's own prose names the kernel and the 64 KB figure
    code = re.sub(r"(?s)/\*.*?\*/", "", re.sub(r"//[^\n]*", "", src))
    check("the flat decode kernel is still launched with attn_shm shared bytes",
          re.search(r"k_attn_decode_win_dyn_T<KV><<<\s*nh\s*,\s*bd\s*,\s*attn_shm", code) is not None)
    check("...and attn_shm is still Pmax * sizeof(float)",
          re.search(r"attn_shm\s*=\s*\(size_t\)s->Pmax\s*\*\s*sizeof\(float\)", code) is not None)
    check("the flat ring kernel still takes its context from the host (the graph hazard)",
          re.search(r"const int ctx\s*=\s*s->dpos_host\s*\+\s*1;.{0,1500}?k_attn_decode_ring_T<KV><<<[^;]*ctx", code, re.S)
          is not None)
    check("nothing opts it into more than 48 KB (if this goes red, the bound moved: re-measure)",
          "cudaFuncAttributeMaxDynamicSharedMemorySize" not in code
          or re.search(r"cudaFuncSetAttribute\([^;]*k_attn_decode_win_dyn", code) is None)
    # §4 THE ENGINE HOLDS IT TOO (2026-11-27). The door above protects released binaries that
    # predate the engine fix; the engine now falls back on its own, and these hold that fix.
    print("§4 the engine falls back instead of serving a failed launch")
    _m = re.search(r"#define\s+G4_FLAT_SHM_MAX\s+\(\(size_t\)(\d+)u\s*\*\s*sizeof\(float\)\)", code)
    check("G4_FLAT_SHM_MAX is a position count under 48 KB with room for the static shared",
          _m is not None and int(_m.group(1)) * 4 + 4 <= 48 * 1024, _m.group(0) if _m else None)
    check("...and it is the door's bound (the two agree on where the flat kernel runs)",
          _m is not None and int(_m.group(1)) == BOUND, (_m.group(1) if _m else None, BOUND))
    _f = re.search(r"static int g4_attn_tile_for\(size_t flat_shm\)\s*\{(.*?)\n\}", code, re.S)
    check("g4_attn_tile_for returns the tiled width when the flat kernel cannot fit",
          _f is not None and re.search(r"flat_shm\s*<=\s*G4_FLAT_SHM_MAX\)\s*return t;", _f.group(1))
          and re.search(r"return 1024;", _f.group(1)) is not None)
    _bare = re.findall(r"const int (?:TL|PT|PT2)\s*=\s*(?:s->bx_on \? 0 : )?g4_attn_tile\(\)", code)
    check("no flat call site picks its kernel without asking g4_attn_tile_for", not _bare, _bare)
    check("the serving decode dispatch asks with the linear layers' attn_shm",
          re.search(r"const int TL = s->bx_on \? 0 : g4_attn_tile_for\(ring \? 0 : attn_shm\);", code) is not None)
    check("segment graphs refuse the flat ring kernel (ring + attn_tile 0 -> per-step)",
          re.search(r"if \(s->ring_W > 0 && g4_attn_tile\(\) == 0\)\s*\{.{0,600}?s->seg_mode = 2;\s*return 0;",
                    code, re.S) is not None)

finish("G-FLAT-ATTN")
