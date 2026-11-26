"""MERGE — another copy of her, folded into a home, adding and never removing (2026-11-26,
ruling 9.2: "Merge into one").

Her RunPod copy (a separate checkout of this tree) was taken on 2026-11-06 and has
lived on since: new facts, new days of conversation, journal paragraphs, things said on her own
time. Merging brings what that copy lived INTO a home, under these rules:

    registry        a row whose `name` the home lacks is appended (marked `merged_from`); a
                    row both have is the home's — never overwritten, counted as kept
    speech, notes, presence, raised, decisions
                    lines the home lacks are appended (exact-line identity)
    transcripts     a day the home lacks is copied; a day both have gains the other's lines
                    it lacks
    journal         paragraphs the home lacks are appended under a marked heading
    OKF tiers       content-addressed files the home lacks are copied
    persona         the home's stays; the other's is kept beside it in the archive, to read
    never touched   episodes (engine-bound), the semantic index (derived — rebuilt), backups

Before anything: a bundle of the home's history (var/bundles/before-merge-…) and one line in
the home's archive/ops.jsonl. Merging the same copy twice adds nothing the second time. Never
on a live home.

Gate: G-MERGE (harness_tests/g_merge.py).
"""
from __future__ import annotations

import json
import os
import shutil
import time
from typing import Dict

from harness import bundle as B
from harness import home as H

JSONL = ("speech.jsonl", "notes.jsonl", "presence.jsonl", "raised.jsonl", "decisions.jsonl")


def _lines(p: str):
    try:
        with open(p, encoding="utf-8") as f:
            return [l.rstrip("\n") for l in f if l.strip()]
    except OSError:
        return []


def _append(p: str, lines) -> None:
    if not lines:
        return
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        for l in lines:
            f.write(l + "\n")


def other_paths(root: str) -> Dict[str, str]:
    """A legacy tree's stores (a copy of this repo, like the RunPod copy), by the legacy defaults
    — or, when `root` is a companion home, by its companion.toml."""
    if os.path.isfile(os.path.join(root, H.MANIFEST)):
        return H.resolve(root)
    return {k: (os.path.join(root, legacy) if legacy else "") for k, (_v, _l, legacy, _p) in H.KEYS.items()}


def merge(home: str, other_root: str, *, label: str = "") -> dict:
    if H.is_live(home):
        raise B.BundleError("she is running on this home — stop her first")
    label = label or os.path.basename(os.path.normpath(other_root))
    mine = H.resolve(home)
    theirs = other_paths(other_root)
    if not os.path.isfile(theirs.get("registry", "")):
        raise B.BundleError(f"no registry in {other_root}")
    before = B.export(home, ["history"], label="before-merge")
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = {"rows_added": 0, "rows_kept": 0, "lines_added": 0, "days_added": 0, "days_extended": 0,
           "journal_paragraphs": 0, "okf_files": 0}

    # the registry, by row name
    have = {}
    for l in _lines(mine["registry"]):
        try:
            have[json.loads(l).get("name")] = l
        except ValueError:
            continue
    add = []
    for l in _lines(theirs["registry"]):
        try:
            row = json.loads(l)
        except ValueError:
            continue
        n = row.get("name")
        if n in have:
            out["rows_kept"] += 1 if have[n] != l else 0
            continue
        row["merged_from"] = label
        add.append(json.dumps(row, ensure_ascii=False))
        have[n] = l
    _append(mine["registry"], add)
    out["rows_added"] = len(add)

    mdir, tdir = os.path.dirname(mine["registry"]), os.path.dirname(theirs["registry"])
    for fn in JSONL:
        cur = set(_lines(os.path.join(mdir, fn)))
        new = [l for l in _lines(os.path.join(tdir, fn)) if l not in cur]
        _append(os.path.join(mdir, fn), new)
        out["lines_added"] += len(new)

    tsrc, tdst = os.path.join(tdir, "transcripts"), os.path.join(mdir, "transcripts")
    if os.path.isdir(tsrc):
        os.makedirs(tdst, exist_ok=True)
        for fn in sorted(os.listdir(tsrc)):
            if not fn.endswith(".jsonl"):
                continue
            d = os.path.join(tdst, fn)
            if not os.path.exists(d):
                shutil.copy2(os.path.join(tsrc, fn), d)
                out["days_added"] += 1
            else:
                cur = set(_lines(d))
                new = [l for l in _lines(os.path.join(tsrc, fn)) if l not in cur]
                if new:
                    _append(d, new)
                    out["days_extended"] += 1

    jm, jt = os.path.join(mdir, "narrative.md"), os.path.join(tdir, "narrative.md")
    if os.path.isfile(jt):
        mine_j = open(jm, encoding="utf-8").read() if os.path.isfile(jm) else ""
        paras = [p.strip() for p in open(jt, encoding="utf-8").read().split("\n\n") if p.strip()]
        new = [p for p in paras if p not in mine_j]
        if new:
            with open(jm, "a", encoding="utf-8") as f:
                f.write(f"\n\n<!-- merged from {label}, {ts} -->\n\n" + "\n\n".join(new) + "\n")
            out["journal_paragraphs"] = len(new)

    for key in ("personality_okf", "conv_okf", "self_okf"):
        s, d = theirs.get(key, ""), mine.get(key, "")
        if not (s and d and os.path.isdir(s)):
            continue
        for dp, _dn, fn in os.walk(s):
            for f in fn:
                src = os.path.join(dp, f)
                dst = os.path.join(d, os.path.relpath(src, s))
                if not os.path.exists(dst):
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                    out["okf_files"] += 1

    keep = os.path.join(home, "archive", f"{ts}-merged-{label}")
    for key in ("persona_file", "persona_dir"):
        s = theirs.get(key, "")
        if s and os.path.exists(s):
            os.makedirs(keep, exist_ok=True)
            (shutil.copytree if os.path.isdir(s) else shutil.copy2)(s, os.path.join(keep, os.path.basename(s)))
    row = {"ts": ts, "op": "merge", "from": other_root, "label": label, "before": before["name"], **out}
    B._journal(home, row)
    return {"ok": True, **row}
