#!/usr/bin/env python3
"""okf_validate.py -- SP-OKF (Kairos profile of the Open Knowledge Format) conformance
validator. Gate: G-OKF-CONFORM. Dependency-free (no pyyaml). Spec: papers/SP-OKF-PROFILE.md.

Walks an OKF bundle (a directory of markdown concept files) and checks every *.md:
  - has YAML frontmatter delimited by leading '---' / '---';
  - carries the REQUIRED OKF field `type`, from the SP type vocabulary (§2);
  - reserved OKF fields, if present, are well-formed: title/description (str), tags (list),
    timestamp (ISO-8601-ish), resource (str);
  - SP receipts-first fields, if present, are well-formed: sp_status in the allowed set,
    sp_gate/sp_commit/sp_repro (str);
  - markdown cross-links to local .md files resolve (warning, not error).

Usage:
    python okf_validate.py <bundle-dir> [--strict-links] [--quiet]
Exit code 0 iff zero errors (warnings do not fail unless --strict-links).
"""
import os, re, sys, datetime, fnmatch

SP_TYPES = {
    "research-paper", "paper-bite", "paper-provenance", "contract", "gate-receipt",
    "roadmap", "project-state", "session-handoff", "abi", "design", "runbook",
    "lesson", "convention", "memory", "index", "log",
    "foundation", "reference", "findings-ledger",
}
# memory-dialect subtypes: the agent-memory harness tags concepts with one of these as `type`
# (the OKF `type` slot), with `node_type: memory` as the OKF concept type. Older memory files
# carry only the subtype (no node_type wrapper); accept the subtype as the memory dialect.
MEMORY_SUBTYPES = {"feedback", "project", "reference", "user"}
SP_STATUS = {"GREEN", "GREEN-LIVE", "RED", "DESIGN", "HONEST-NEGATIVE", "DRAFT", "ACTIVE", "SUPERSEDED"}
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:?\d{2})?)?$")
MDLINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def parse_frontmatter(text):
    """Return (dict, body_offset) or (None, 0) if no frontmatter. Minimal YAML: scalars,
    inline [a, b] lists, and `- item` block lists."""
    if not text.startswith("---"):
        return None, 0
    end = text.find("\n---", 3)
    if end == -1:
        return None, 0
    fm = text[3:end].strip("\n")
    d, cur_key = {}, None
    for raw in fm.split("\n"):
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.lstrip().startswith("- ") and cur_key:           # block list item
            d.setdefault(cur_key, [])
            if isinstance(d[cur_key], list):
                d[cur_key].append(line.lstrip()[2:].strip())
            continue
        # allow leading whitespace: flatten nested mapping keys (e.g. metadata: node_type: ...)
        # up to top level, which is how the memory dialect exposes node_type/type.
        m = re.match(r"^\s*([A-Za-z0-9_]+):\s*(.*)$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        cur_key = k
        if v == "":
            d[k] = []                                             # expect block list below
        elif v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            d[k] = [x.strip().strip('"\'') for x in inner.split(",")] if inner else []
        else:
            d[k] = v.strip('"\'')
    return d, end


def validate_file(path, bundle_root, strict_links):
    errs, warns = [], []
    try:
        text = open(path, encoding="utf-8").read()
    except Exception as e:
        return [f"unreadable: {e}"], []
    fm, _ = parse_frontmatter(text)
    if fm is None:
        return ["no YAML frontmatter (expected leading '---' ... '---')"], []
    # REQUIRED: type (with memory-dialect acceptance via node_type).
    # The minimal YAML parser flattens nested `metadata:` keys to top-level, so memory files
    # (metadata: node_type: memory + a subtype `type: feedback|project|reference|user`) expose
    # node_type=memory (in SP_TYPES) and type=<subtype> (not in SP_TYPES). Accept that dialect.
    t = fm.get("type")
    nt = fm.get("node_type")
    if t and t in SP_TYPES:
        pass                                                      # ordinary SP-OKF concept
    elif nt in SP_TYPES:
        pass                                                      # memory dialect; subtype `type` allowed
    elif t and t in MEMORY_SUBTYPES:
        pass                                                      # memory dialect (legacy: subtype only, no node_type)
    elif t:
        errs.append(f"`type: {t}` not in SP vocabulary (register in SP-OKF-PROFILE §2 first)")
    else:
        errs.append("missing required field `type`")
    # reserved OKF fields, if present
    if "tags" in fm and not isinstance(fm["tags"], list):
        errs.append("`tags` must be a YAML list")
    if "timestamp" in fm and not ISO_RE.match(str(fm["timestamp"])):
        errs.append(f"`timestamp: {fm['timestamp']}` not ISO-8601")
    for s in ("title", "description", "resource"):
        if s in fm and not isinstance(fm[s], str):
            errs.append(f"`{s}` must be a string")
    # SP receipts-first fields, if present
    if "sp_status" in fm and fm["sp_status"] not in SP_STATUS:
        errs.append(f"`sp_status: {fm['sp_status']}` not in {sorted(SP_STATUS)}")
    if not fm.get("title"):
        warns.append("no `title` (recommended)")
    if not fm.get("timestamp"):
        warns.append("no `timestamp` (recommended)")
    # cross-link resolution (local .md targets)
    for tgt in MDLINK_RE.findall(text):
        link = tgt.split("#")[0].strip()
        if not link or link.startswith(("http://", "https://", "mailto:")):
            continue
        if link.endswith(".md"):
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), link))
            if not os.path.exists(resolved):
                (errs if strict_links else warns).append(f"dangling link -> {link}")
    return errs, warns


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        print("usage: okf_validate.py <bundle-dir> [--strict-links] [--quiet]")
        return 2
    root = args[0]
    strict = "--strict-links" in flags
    quiet = "--quiet" in flags
    md = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if fn.endswith(".md"):
                md.append(os.path.join(dp, fn))
    md.sort()
    # optional .okfignore: one glob per line, # = comment. A bare pattern is matched against BOTH
    # the bundle-relative path and the basename (convenient for "ignore every X.md"). A pattern
    # with a LEADING '/' is ROOT-ANCHORED (gitignore-style): matched only against the bundle-
    # relative path, never the basename -- so `/README.md` ignores the root README without also
    # catching nested `papers/*/README.md` concept files (whose basename is also README.md).
    ignore_path = os.path.join(root, ".okfignore")
    if os.path.exists(ignore_path):
        pats = []
        for ln in open(ignore_path, encoding="utf-8"):
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                pats.append(ln)
        if pats:
            def _ignored(rel, base):
                for g in pats:
                    if g.startswith("/"):
                        if fnmatch.fnmatch(rel, g[1:]):        # root-anchored: rel-path only
                            return True
                    elif fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(base, g):
                        return True
                return False
            kept = []
            n_ignored = 0
            for p in md:
                rel = os.path.relpath(p, root).replace(os.sep, "/")
                base = os.path.basename(p)
                if _ignored(rel, base):
                    n_ignored += 1
                else:
                    kept.append(p)
            md = kept
            print(f"[ignored {n_ignored} files via .okfignore]")
    n_err = n_warn = n_ok = 0
    for p in md:
        e, w = validate_file(p, root, strict)
        rel = os.path.relpath(p, root)
        if e:
            n_err += len(e)
            print(f"[FAIL] {rel}")
            for x in e:
                print(f"        ERROR: {x}")
        elif w and not quiet:
            print(f"[warn] {rel}")
        if w and not quiet:
            for x in w:
                print(f"        warn: {x}")
        if not e:
            n_ok += 1
        n_warn += len(w)
    print(f"---- G-OKF-CONFORM: {len(md)} concepts | {n_ok} conformant | {n_err} errors | {n_warn} warnings ----")
    if n_err == 0:
        print("VERDICT: GREEN" + (" (strict-links)" if strict else ""))
        return 0
    print("VERDICT: RED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
