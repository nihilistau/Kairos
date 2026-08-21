#!/usr/bin/env python3
"""okf_mem.py - the content-addressed tiered memory tool (MEM-OKF).

One format, two callers:
  * AGENT working memory  - text concepts, addressed by sha256(body)[:16].
  * XBAR/NIGHTSHIFT episodes - latent episodes, addressed by their C2 256-bit
    LSH signature (passed in as --addr); the "full" tier is a blob pointer to
    the Ring-2 / Optane payload.

Three disclosure tiers, all OKF concepts, all linked by the address:
  Tier-0  LUT.md        one row/object: addr | kind | keys | one-line summary | status | ->sum
  Tier-1  sum/<addr>.md the distilled, in-context summary (points down: mem_full)
  Tier-2  full/<addr>.md the complete context (text) OR a blob pointer (episode)

The address is the join key to the PoUW receipt ledger (every write receipted by
hash). Content-addressing gives free dedup + an auditable integrity gate
(G-MEM-OKF-CONFORM via `verify`). No third-party deps.
"""
import argparse, hashlib, os, re, sys, datetime

LUT_NAME = "LUT.md"
SUM_DIR  = "sum"
FULL_DIR = "full"
LUT_HEADER = ("| addr | kind | keys | summary | status | sum |\n"
              "|---|---|---|---|---|---|\n")

# MEM-OKF v2 policy vocabulary — CONSUMED from THE class registry (2026-07-14,
# INVARIANT-ROADMAP.md Tier 1.2). This file used to hold its own copy, and the copy had
# DRIFTED: the 2026-07-12 engine fix (fact -> system: "a remembered thing is CONTEXT,
# not a command") never landed here, so this map still said fact -> recite — the exact
# delivery that made her recite an unrelated memory at "what do you mean?". One
# registry now (harness/skills/memclass.py); G-MEMCLASS convicts any new copy.
# Widening note: the vocabulary now includes the harness writer's classes
# (relationship/identity/event) and self-fact — self-model concepts used to FAIL
# conformance under the old seven-class set.
import sys as _sys
_sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.skills import memclass as _mc  # noqa: E402

MEM_CLASSES    = set(_mc.CLASSES)
MEM_DELIVERIES = set(_mc.DELIVERIES)        # "route:<t>" also allowed (checked by prefix)
MEM_DECLINES   = set(_mc.DECLINES)
# class -> default delivery (the registry's; per-entry field overrides).
CLASS_DEFAULT_DELIVERY = _mc.delivery_map()
# A1: orthogonal trust x freshness axes (Icarus verified x lifecycle; 2606.01444 audit contract).
MEM_VERIFIED  = {"unverified", "verified", "contradicted", "rolled_back"}
MEM_LIFECYCLE = {"active", "superseded"}
# Legal verified-status transitions (an audit-preserving state machine).
LEGAL_VERIFIED = {
    "unverified":   {"unverified", "verified", "contradicted"},
    "verified":     {"verified", "contradicted", "rolled_back"},
    "contradicted": {"contradicted", "rolled_back"},
    "rolled_back":  {"rolled_back"},
}
def legal_transition(frm, to):
    return to in LEGAL_VERIFIED.get(frm, set())

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def norm(body):
    return body.replace("\r\n", "\n").strip() + "\n"

def addr_of(body):
    return hashlib.sha256(norm(body).encode("utf-8")).hexdigest()[:16]

def fm_block(d):
    out = ["---"]
    for k, v in d.items():
        if isinstance(v, list):
            out.append(k + ": [" + ", ".join(str(x) for x in v) + "]")
        else:
            out.append(k + ": " + str(v))
    out.append("---")
    return "\n".join(out) + "\n"

def parse_fm(text):
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, m.group(2)

def ensure_root(root):
    os.makedirs(os.path.join(root, SUM_DIR), exist_ok=True)
    os.makedirs(os.path.join(root, FULL_DIR), exist_ok=True)
    lut = os.path.join(root, LUT_NAME)
    if not os.path.exists(lut):
        with open(lut, "w", encoding="utf-8") as f:
            f.write(fm_block({
                "type": "index", "title": "MEM-OKF LUT (Tier-0, always-loadable)",
                "description": "Keyword -> one-line agent-readable summary -> content address; follow addr to sum/ then full/.",
                "tags": ["mem-okf", "lut", "tier-0", "index"], "timestamp": now_iso(),
                "resource": "tools/okf_mem.py", "sp_status": "ACTIVE",
                "sp_gate": "G-MEM-OKF-CONFORM", "sp_commit": "TBD",
                "sp_repro": "python tools/okf_mem.py verify --root <root>"}))
            f.write("\n# MEM-OKF LUT\n\nLookup before you build. `python tools/okf_mem.py lookup --root <root> <kw>`\n\n")
            f.write(LUT_HEADER)
    idx = os.path.join(root, "index.md")
    if not os.path.exists(idx):
        with open(idx, "w", encoding="utf-8") as f:
            f.write(fm_block({
                "type": "index", "title": "MEM-OKF bundle index",
                "description": "Content-addressed tiered memory. Tier-0 LUT.md, Tier-1 sum/, Tier-2 full/.",
                "tags": ["mem-okf", "index"], "timestamp": now_iso(),
                "resource": "papers/MEMORY-OKF-PROFILE.md", "sp_status": "ACTIVE",
                "sp_gate": "G-MEM-OKF-CONFORM", "sp_commit": "TBD",
                "sp_repro": "python tools/okf_mem.py verify --root <root>"}))
            f.write("\n# MEM-OKF bundle\n\nSee [MEMORY-OKF-PROFILE](../papers/MEMORY-OKF-PROFILE.md). Start at [LUT.md](LUT.md).\n")

def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def lut_rows(root):
    txt = read(os.path.join(root, LUT_NAME))
    rows = []
    for line in txt.split("\n"):
        if line.startswith("|") and not line.startswith("| addr") and not line.startswith("|---"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 6:
                rows.append(cells)
    return rows

def write_lut(root, rows):
    txt = read(os.path.join(root, LUT_NAME))
    head = txt.split(LUT_HEADER)[0]
    body = "".join("| " + " | ".join(r) + " |\n" for r in rows)
    write(os.path.join(root, LUT_NAME), head + LUT_HEADER + body)

def cmd_add(a):
    ensure_root(a.root)
    if a.full_file:
        full_body = read(a.full_file)
    elif a.blob_ref:
        full_body = ("BLOB POINTER (Tier-2 = external payload)\n\nblob: " + a.blob_ref +
                     "\nkind: " + a.kind + "\nFull context is the latent/binary payload at the blob path "
                     "(Ring-2 / Optane). Address = C2 LSH signature / provided id.\n")
    elif not sys.stdin.isatty():
        full_body = sys.stdin.read()
    else:
        print("add: need --full-file, --blob-ref, or piped stdin", file=sys.stderr)
        return 2
    addr = a.addr if a.addr else addr_of(full_body)
    common = {"type": "memory", "title": a.title or a.summary[:60], "description": a.summary,
              "timestamp": now_iso(), "resource": a.commit or "TBD", "sp_status": a.status,
              "sp_gate": a.gate, "sp_commit": a.commit or "TBD", "sp_repro": a.repro or "none",
              "mem_kind": a.kind, "mem_addr": addr}
    # MEM-OKF v2 policy block (additive; OKF-permitted producer keys).
    if a.mem_class:
        delivery = a.delivery or CLASS_DEFAULT_DELIVERY.get(a.mem_class, "recite")
        common["mem_class"] = a.mem_class
        common["mem_delivery"] = delivery
        common["mem_authority"] = a.authority or (
            "private" if a.mem_class == "private-secret"
            else "overrides-prior" if a.mem_class in ("counterfact", "same-template")
            else "supplements")
        if a.retrieval_key:
            common["mem_retrieval_key"] = a.retrieval_key
        elif a.mem_class == "private-secret":
            common["mem_retrieval_key"] = "exact-token"
        # class-default decline: a private-secret is zero-inference-safe by construction.
        decl = a.decline_when or ("zero-inference,attribute-absent" if a.mem_class == "private-secret" else "")
        if decl:
            common["mem_decline_when"] = decl
            common["mem_decline_message"] = a.decline_message or "I have a record for that entity, but it does not include that specific detail."
        if a.confidence is not None:
            common["mem_confidence"] = a.confidence
    # A1: trust x freshness axes. verified starts 'unverified' at capture (cannot be set verified here).
    if getattr(a, "verified", None) == "verified":
        print("add: cannot set verified='verified' at capture; promote via a verify action", file=sys.stderr)
        return 2
    common["mem_verified"] = getattr(a, "verified", None) or "unverified"
    common["mem_lifecycle"] = getattr(a, "lifecycle", None) or "active"
    for _k, _v in (("mem_supersedes", getattr(a, "supersedes", None)),
                   ("mem_superseded_by", getattr(a, "superseded_by", None)),
                   ("mem_contradicted_by", getattr(a, "contradicted_by", None)),
                   ("mem_revises", getattr(a, "revises", None))):
        if _v:
            common[_k] = _v
    full_fm = dict(common); full_fm["tags"] = a.keys.split(",") + [a.kind, "tier-2"]; full_fm["mem_tier"] = "full"
    write(os.path.join(a.root, FULL_DIR, addr + ".md"), fm_block(full_fm) + "\n" + norm(full_body))
    detail = a.detail if a.detail else (read(a.detail_file) if a.detail_file else a.summary)
    sum_fm = dict(common); sum_fm["tags"] = a.keys.split(",") + [a.kind, "tier-1"]
    sum_fm["mem_tier"] = "summary"; sum_fm["mem_full"] = addr
    write(os.path.join(a.root, SUM_DIR, addr + ".md"),
          fm_block(sum_fm) + "\n# " + (a.title or a.summary) + "\n\n" + norm(detail) +
          "\nFull context: [full/" + addr + ".md](../full/" + addr + ".md)\n")
    rows = [r for r in lut_rows(a.root) if r[0] != addr]
    # v2: surface the policy hint at Tier-0 (progressive disclosure of policy, not just content)
    summ = a.summary.replace("|", "/").strip()
    if a.mem_class:
        summ = "[" + a.mem_class + "/" + common["mem_delivery"] + "] " + summ
    rows.append([addr, a.kind, a.keys.replace("|", "/").strip(), summ,
                 a.status, "sum/" + addr + ".md"])
    write_lut(a.root, rows)
    print("added " + addr + "  [" + a.kind + "/" + a.status + "]  " + a.summary)
    return 0

def cmd_lookup(a):
    q = a.query.lower()
    hits = [r for r in lut_rows(a.root) if q in r[2].lower() or q in r[3].lower()]
    if not hits:
        print("(no LUT match for '" + a.query + "')"); return 0
    for r in hits:
        print(r[0] + "  [" + r[1] + "/" + r[4] + "]  " + r[3] + "\n        keys: " + r[2] + "  -> expand " + r[0])
    return 0

def cmd_expand(a):
    sub = FULL_DIR if a.full else SUM_DIR
    p = os.path.join(a.root, sub, a.addr + ".md")
    if not os.path.exists(p):
        print("(no " + sub + "/" + a.addr + ".md)", file=sys.stderr); return 2
    sys.stdout.write(read(p)); return 0

def cmd_verify(a):
    errs, warns, n = [], [], 0
    fulls, sums = set(), set()
    fd = os.path.join(a.root, FULL_DIR)
    if os.path.isdir(fd):
        for fn in os.listdir(fd):
            if not fn.endswith(".md"): continue
            addr = fn[:-3]; fulls.add(addr); n += 1
            fm, body = parse_fm(read(os.path.join(fd, fn)))
            if fm.get("mem_addr") != addr:
                errs.append("full/" + fn + ": mem_addr " + str(fm.get("mem_addr")) + " != " + addr)
            # A1: trust x freshness axis conformance + link-presence for tainted/superseded rows.
            mv, ml = fm.get("mem_verified"), fm.get("mem_lifecycle")
            if mv and mv not in MEM_VERIFIED:
                errs.append("full/" + fn + ": mem_verified '" + str(mv) + "' not in vocab")
            if ml and ml not in MEM_LIFECYCLE:
                errs.append("full/" + fn + ": mem_lifecycle '" + str(ml) + "' not in vocab")
            if ml == "superseded" and not fm.get("mem_superseded_by"):
                errs.append("full/" + fn + ": lifecycle=superseded but no mem_superseded_by link")
            if mv == "contradicted" and not fm.get("mem_contradicted_by"):
                errs.append("full/" + fn + ": verified=contradicted but no mem_contradicted_by link")
            if fm.get("mem_kind") == "agent" and addr_of(body) != addr:
                errs.append("full/" + fn + ": sha256(body)[:16]=" + addr_of(body) + " != " + addr + " (text tampered)")
            # ---- MEM-OKF v2 policy conformance (only for policied entries) ----
            mc = fm.get("mem_class")
            if mc:
                if mc not in MEM_CLASSES:
                    errs.append("full/" + fn + ": mem_class '" + str(mc) + "' not in vocab")
                dv = fm.get("mem_delivery", "")
                if dv and dv not in MEM_DELIVERIES and not dv.startswith("route:"):
                    errs.append("full/" + fn + ": mem_delivery '" + dv + "' not in vocab")
                # safety monotonicity: a secret must never carry a leaky delivery.
                if mc == "private-secret" and dv not in ("attr-gate-strict",):
                    errs.append("full/" + fn + ": private-secret with unsafe delivery '" + dv + "' (must be attr-gate-strict)")
                dw = fm.get("mem_decline_when", "")
                if mc == "private-secret" and "zero-inference" not in dw:
                    errs.append("full/" + fn + ": private-secret missing zero-inference decline")
                if dw:
                    for w in [x.strip() for x in dw.strip("[]").split(",") if x.strip()]:
                        if w not in MEM_DECLINES:
                            errs.append("full/" + fn + ": decline-when '" + w + "' not in vocab")
                    if not fm.get("mem_decline_message"):
                        warns.append("full/" + fn + ": decline-when set but no decline-message")
    sd = os.path.join(a.root, SUM_DIR)
    if os.path.isdir(sd):
        for fn in os.listdir(sd):
            if not fn.endswith(".md"): continue
            addr = fn[:-3]; sums.add(addr)
            fm, _ = parse_fm(read(os.path.join(sd, fn)))
            if fm.get("mem_full") not in fulls:
                errs.append("sum/" + fn + ": mem_full " + str(fm.get("mem_full")) + " unresolved")
    lut_addrs = {r[0] for r in lut_rows(a.root)}
    for r in lut_rows(a.root):
        if r[0] not in fulls: errs.append("LUT " + r[0] + ": no full/")
        if r[0] not in sums:  errs.append("LUT " + r[0] + ": no sum/")
        if not r[2] or not r[3]: errs.append("LUT " + r[0] + ": empty keys/summary")
    for addr in (fulls | sums) - lut_addrs:
        warns.append("orphan " + addr + " (not in LUT)")
    for w in warns: print("  warn:", w)
    for e in errs:  print("  ERROR:", e)
    verdict = "GREEN" if not errs else "RED"
    print("---- G-MEM-OKF-CONFORM: " + str(n) + " objects | " + str(len(errs)) + " errors | " + str(len(warns)) + " warnings ----")
    print("VERDICT: " + verdict)
    return 0 if not errs else 1

# ---- A4: anti-rebuild classifier (Retrieval / Search / Discovery + Kan-obstruction) ----
# Formalizes the binding anti-rebuild pre-flight (MEMORY-OKF-PROFILE §0/§6): every incoming
# knowledge write is classified against the live store. RETRIEVAL = already here (reject/dedup);
# SEARCH = recombination of existing entries (allow, link parents); DISCOVERY = genuinely new
# content or a new type (the Kan obstruction — transport supplies nothing). See
# papers/PPT-LAT-COMPARE-EXTERNAL-SYSTEMS-2026-07.md §4/A4 (source: arXiv 2606.01444).
STOP = set(("the a an of to in on and or is are be as it its for with by from that this than "
            "then so we our you your i at not no can will would could into over under out up "
            "if but which when where who what how all any each per via use used using").split())

def toks(text):
    return set(t for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if t not in STOP)

# SP type vocabulary (mirror of SP-OKF-PROFILE §2 / okf_validate.SP_TYPES). A declared type
# outside this set is a Kan obstruction (a genuinely new kind of concept -> register it first).
SP_TYPES = {"research-paper", "paper-bite", "paper-provenance", "contract", "gate-receipt",
            "roadmap", "project-state", "session-handoff", "abi", "design", "runbook", "lesson",
            "convention", "foundation", "reference", "findings-ledger", "memory", "index", "log"}

def entry_tokens(root):
    """addr -> content token set (frontmatter stripped) for every full/ entry in the store."""
    out = {}
    fd = os.path.join(root, FULL_DIR)
    if os.path.isdir(fd):
        for fn in os.listdir(fd):
            if not fn.endswith(".md"):
                continue
            _, body = parse_fm(read(os.path.join(fd, fn)))
            out[fn[:-3]] = toks(body)
    return out

def classify_body(root, raw, topk=3, hi_cov=0.55, disc_resid=0.5, declared_type=None):
    """Deterministic RETRIEVAL/SEARCH/DISCOVERY verdict for a candidate write vs the store.
    best_cov = max single-entry coverage of the candidate; residual = fraction of candidate
    content tokens covered by NO top-k entry (the Kan-obstruction / new-evidence signal)."""
    fm, body = parse_fm(raw)
    cand = toks(body)
    dtype = declared_type if declared_type is not None else fm.get("type")
    if not cand:
        return {"verdict": "UNKNOWN", "reason": "empty candidate (no content tokens)",
                "exact": False, "best_addr": None, "best_cov": 0.0, "best_jaccard": 0.0,
                "residual": 1.0, "n_entries": 0, "type_novel": False}
    ents = entry_tokens(root)
    exact = addr_of(raw) in ents or addr_of(body) in ents
    scored = []
    for addr, et in ents.items():
        inter = len(cand & et)
        cov = inter / len(cand)
        jac = inter / len(cand | et) if (cand | et) else 0.0
        scored.append((cov, jac, addr))
    scored.sort(reverse=True)
    best_cov, best_jac, best_addr = scored[0] if scored else (0.0, 0.0, None)
    union = set()
    for _cov, _jac, addr in scored[:topk]:
        union |= ents[addr]
    residual = 1.0 - (len(cand & union) / len(cand))
    type_novel = bool(dtype) and dtype not in SP_TYPES
    if exact:
        verdict, reason = "RETRIEVAL", "exact content-address match (duplicate) -> reject"
    elif best_cov >= hi_cov:
        verdict, reason = "RETRIEVAL", ("single existing entry %s covers %.2f of candidate "
                                        "(rebuild) -> reject/dedup" % (best_addr, best_cov))
    elif residual >= disc_resid:
        verdict, reason = "DISCOVERY", ("residual %.2f of candidate absent from store "
                                        "(Kan obstruction) -> allow; needs fresh evidence/receipt" % residual)
    else:
        verdict, reason = "SEARCH", ("covered by union of top-%d entries (residual %.2f), no "
                                     "single dominant source -> allow as derivation, link parents" % (topk, residual))
    if type_novel and verdict != "RETRIEVAL":
        verdict = "DISCOVERY"
        reason = ("declared type '%s' not in SP vocabulary (Kan obstruction) — register in "
                  "SP-OKF-PROFILE first. " % dtype) + reason
    return {"verdict": verdict, "reason": reason, "exact": exact, "best_addr": best_addr,
            "best_cov": round(best_cov, 3), "best_jaccard": round(best_jac, 3),
            "residual": round(residual, 3), "n_entries": len(ents), "type_novel": type_novel}

def cmd_classify(a):
    if a.file:
        raw = read(a.file)
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        print("classify: need --file or piped stdin", file=sys.stderr)
        return 2
    r = classify_body(a.root, raw, topk=a.topk, declared_type=a.declared_type)
    print("VERDICT: " + r["verdict"])
    print("  " + r["reason"])
    print("  best=%s cov=%s jaccard=%s residual(top%d)=%s entries=%d exact=%s type_novel=%s"
          % (r["best_addr"], r["best_cov"], r["best_jaccard"], a.topk, r["residual"],
             r["n_entries"], r["exact"], r["type_novel"]))
    if a.claim and a.claim.upper() == "DISCOVERY" and r["verdict"] != "DISCOVERY":
        print("  WARN: claimed DISCOVERY but classified %s (residual %s) — likely a rebuild/"
              "derivation, not a discovery." % (r["verdict"], r["residual"]))
    if a.strict and r["verdict"] == "RETRIEVAL":
        return 1
    return 0

# ---- A5: human/agent co-edit markers (idempotent generated-block upsert) ----
# An agent re-generating a section edits ONLY the region between its own markers, never
# a human's hand edits. Source: Icarus wiki ICARUS_GENERATED:<key>:START/END pattern.
def _markers(key):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key)
    return ("<!-- SP_GENERATED:%s:START -->" % safe, "<!-- SP_GENERATED:%s:END -->" % safe)

def upsert_block(text, key, content):
    """Replace the region between this key's markers with content (idempotent); append a
    fresh marked block if absent. Everything outside the block is preserved byte-for-byte."""
    start, end = _markers(key)
    block = start + "\n" + content.rstrip("\n") + "\n" + end
    i, j = text.find(start), text.find(end)
    if i != -1 and j != -1 and j > i:
        return text[:i] + block + text[j + len(end):]
    if not text:
        return block + "\n"
    pad = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    return text + pad + block + "\n"

def cmd_upsert(a):
    content = a.content if a.content is not None else (read(a.content_file) if a.content_file else "")
    text = read(a.file) if os.path.exists(a.file) else ""
    write(a.file, upsert_block(text, a.key, content))
    print("upserted block '%s' in %s" % (a.key, a.file))
    return 0

def cmd_transition(a):
    ok = legal_transition(a.frm, a.to)
    print(("LEGAL" if ok else "ILLEGAL") + ": " + a.frm + " -> " + a.to)
    return 0 if ok else 1

def main():
    ap = argparse.ArgumentParser(description="MEM-OKF content-addressed tiered memory")
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--root", default=os.environ.get("MEM_OKF_ROOT", "memory-okf"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add", parents=[parent]); p.set_defaults(fn=cmd_add)
    p.add_argument("--kind", default="agent", choices=["agent", "episode"])
    p.add_argument("--keys", required=True); p.add_argument("--summary", required=True)
    p.add_argument("--title"); p.add_argument("--detail"); p.add_argument("--detail-file")
    p.add_argument("--full-file"); p.add_argument("--blob-ref"); p.add_argument("--addr")
    p.add_argument("--status", default="ACTIVE"); p.add_argument("--gate", default="none")
    p.add_argument("--commit"); p.add_argument("--repro")
    # MEM-OKF v2 policy block
    p.add_argument("--mem-class", dest="mem_class", choices=sorted(MEM_CLASSES),
                   help="v2: sets the default retrieval/delivery/decline policy")
    p.add_argument("--delivery", help="v2: override delivery (systemecho|attr-gate-strict|two-stage|recite|system|route:<t>)")
    p.add_argument("--authority", help="v2: overrides-prior|supplements|private")
    p.add_argument("--retrieval-key", dest="retrieval_key", help="v2: l5-question|exact-token|c2-sig")
    p.add_argument("--decline-when", dest="decline_when", help="v2: comma list (attribute-absent,family-ambiguous,low-margin,zero-inference)")
    p.add_argument("--decline-message", dest="decline_message", help="v2: fixed decline string")
    p.add_argument("--confidence", type=float, default=None)
    # A1: trust x freshness axes
    p.add_argument("--verified", choices=sorted(MEM_VERIFIED))
    p.add_argument("--lifecycle", choices=sorted(MEM_LIFECYCLE))
    p.add_argument("--supersedes"); p.add_argument("--superseded-by", dest="superseded_by")
    p.add_argument("--contradicted-by", dest="contradicted_by"); p.add_argument("--revises")
    p = sub.add_parser("lookup", parents=[parent]); p.set_defaults(fn=cmd_lookup); p.add_argument("query")
    p = sub.add_parser("expand", parents=[parent]); p.set_defaults(fn=cmd_expand)
    p.add_argument("addr"); p.add_argument("--full", action="store_true")
    p = sub.add_parser("verify", parents=[parent]); p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("classify", parents=[parent]); p.set_defaults(fn=cmd_classify)
    p.add_argument("--file", help="candidate write to classify (else read stdin)")
    p.add_argument("--topk", type=int, default=3, help="entries unioned for the residual signal")
    p.add_argument("--strict", action="store_true", help="exit 1 on a RETRIEVAL (rebuild) verdict")
    p.add_argument("--claim", help="the write's claimed class (e.g. discovery) — warns on mismatch")
    p.add_argument("--declared-type", dest="declared_type", help="override the candidate's frontmatter type")
    p = sub.add_parser("upsert-block", parents=[parent]); p.set_defaults(fn=cmd_upsert)
    p.add_argument("--file", required=True); p.add_argument("--key", required=True)
    p.add_argument("--content"); p.add_argument("--content-file", dest="content_file")
    p = sub.add_parser("transition", parents=[parent]); p.set_defaults(fn=cmd_transition)
    p.add_argument("frm"); p.add_argument("to")
    a = ap.parse_args(); sys.exit(a.fn(a))

if __name__ == "__main__":
    main()
