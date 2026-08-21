"""restore — list, verify and extract the hourly backups.

    python restore.py                      # list every backup, newest first
    python restore.py list --full          # …with what each one excluded
    python restore.py verify <name|latest> # CRC every member; ok means RESTORABLE
    python restore.py show <name|latest>   # the manifest
    python restore.py peek <name> <path>   # print one file out of a backup
    python restore.py extract <name> --to <dir>     # unpack somewhere safe
    python restore.py now                  # take one right now
    python restore.py restore <name> --path persona.md --yes   # put ONE file back

EXTRACT IS THE DEFAULT AND `restore` IS THE NARROW ONE, deliberately. The failure
this system exists for is a single file being clobbered — persona.md, the registry —
not the tree being lost. Unpacking to a directory and looking before you copy is the
right move nearly every time; a one-shot "restore everything over the top" is how a
bad backup destroys a good present. So `restore` takes ONE path, requires --yes, and
writes a .before-restore copy of whatever it replaces.

Sits beside serve.py rather than under harness/cli/ because you reach for it when
something is wrong, and that is the worst moment to go looking for where it lives.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from harness.control import backup as B  # noqa: E402


def _human(n) -> str:
    if not isinstance(n, (int, float)):
        return "-"
    for u in ("B", "K", "M", "G"):
        if n < 1024:
            return f"{n:.0f}{u}" if u == "B" else f"{n:.1f}{u}"
        n /= 1024.0
    return f"{n:.1f}T"


def _pick(name: str) -> str:
    """`latest` resolves to the newest archive — the name you want when something
    has just gone wrong and you do not want to read a timestamp."""
    rows = B.listing()
    if not rows:
        print("no backups yet")
        raise SystemExit(1)
    if name in ("", "latest", None):
        return rows[0]["name"]
    if name in {r["name"] for r in rows}:
        return name
    hits = [r["name"] for r in rows if name in r["name"]]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        print(f"no backup matching {name!r}")
        raise SystemExit(1)
    print(f"{name!r} matches {len(hits)}: " + ", ".join(hits[:6]))
    raise SystemExit(1)


def cmd_list(args) -> int:
    rows = B.listing()
    if not rows:
        print(f"no backups in {B.DIR}")
        return 0
    st = B.status()
    print(f"{len(rows)} backups in {B.DIR}  ({_human(st['total_bytes'])} total, "
          f"keep {st['keep_hourly']} hourly + {st['keep_daily']} daily)")
    print(f"{'NAME':<34}{'WHEN':<18}{'SIZE':>8}{'FILES':>8}  REASON")
    for r in rows:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["mtime"]))
        flag = "" if not r.get("error") else "  !! " + r["error"]
        print(f"{r['name']:<34}{when:<18}{_human(r['size']):>8}"
              f"{str(r.get('files', '-')):>8}  {r.get('reason', '-')}{flag}")
        if args.full and r.get("excluded"):
            for e in r["excluded"]:
                print(f"      excluded: {e}")
    if not args.full and rows and rows[0].get("excluded"):
        print("\n(--full shows what each backup deliberately excluded)")
    return 0


def cmd_verify(args) -> int:
    name = _pick(args.name)
    res = B.verify(name)
    print(json.dumps(res, indent=2))
    if res.get("ok"):
        print(f"\n{name} is RESTORABLE — every member CRCs clean.")
    return 0 if res.get("ok") else 1


def cmd_show(args) -> int:
    name = _pick(args.name)
    with zipfile.ZipFile(os.path.join(B.DIR, name)) as z:
        print(z.read("MANIFEST.json").decode("utf-8"))
    return 0


def cmd_peek(args) -> int:
    name = _pick(args.name)
    with zipfile.ZipFile(os.path.join(B.DIR, name)) as z:
        members = z.namelist()
        if args.path not in members:
            hits = [m for m in members if args.path in m]
            if len(hits) != 1:
                print(f"{args.path!r} not in {name}"
                      + (f" — did you mean:\n  " + "\n  ".join(hits[:8]) if hits else ""))
                return 1
            args.path = hits[0]
        sys.stdout.write(z.read(args.path).decode("utf-8", "replace"))
    return 0


def cmd_extract(args) -> int:
    name = _pick(args.name)
    dest = os.path.abspath(args.to)
    # NEVER over the live tree by accident. Extract is for looking; `restore` is
    # for putting back, and it takes one path at a time.
    if os.path.realpath(dest) == os.path.realpath(ROOT):
        print("refusing to extract over the repo root — use --to a scratch dir, "
              "then `restore <name> --path <file>` for the one file you want back")
        return 1
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(os.path.join(B.DIR, name)) as z:
        z.extractall(dest)
        n = len(z.namelist())
    print(f"extracted {n} members of {name} -> {dest}")
    return 0


def cmd_restore(args) -> int:
    name = _pick(args.name)
    rel = args.path.replace("\\", "/")
    with zipfile.ZipFile(os.path.join(B.DIR, name)) as z:
        if rel not in z.namelist():
            hits = [m for m in z.namelist() if rel in m]
            print(f"{rel!r} not in {name}"
                  + (f" — did you mean:\n  " + "\n  ".join(hits[:8]) if hits else ""))
            return 1
        data = z.read(rel)
    target = os.path.join(ROOT, rel)
    if not args.yes:
        print(f"would restore {rel}  ({_human(len(data))}) from {name}")
        print(f"          to  {target}")
        if os.path.exists(target):
            print(f"  existing file is {_human(os.path.getsize(target))} — it would be "
                  f"copied to {rel}.before-restore first")
        print("\nre-run with --yes to do it")
        return 0
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    if os.path.exists(target):
        # The present is also data. A restore that destroys what is there is just a
        # different kind of loss.
        shutil.copy2(target, target + ".before-restore")
    with open(target, "wb") as f:
        f.write(data)
    print(f"restored {rel} from {name}")
    if os.path.exists(target + ".before-restore"):
        print(f"previous contents kept at {rel}.before-restore")
    return 0


def cmd_now(args) -> int:
    rec = B.run_once("manual")
    print(json.dumps({k: v for k, v in rec.items() if k != "excluded"}, indent=2))
    return 0 if rec.get("ok") else 1


def cmd_status(args) -> int:
    print(json.dumps(B.status(), indent=2, default=str))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="restore", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("list", help="list backups (default)")
    p.add_argument("--full", action="store_true", help="show exclusions")
    p.set_defaults(fn=cmd_list)

    for nm, fn, hlp in (("verify", cmd_verify, "CRC every member"),
                        ("show", cmd_show, "print the manifest")):
        p = sub.add_parser(nm, help=hlp)
        p.add_argument("name", nargs="?", default="latest")
        p.set_defaults(fn=fn)

    p = sub.add_parser("peek", help="print one file out of a backup")
    p.add_argument("name"); p.add_argument("path")
    p.set_defaults(fn=cmd_peek)

    p = sub.add_parser("extract", help="unpack to a directory")
    p.add_argument("name", nargs="?", default="latest")
    p.add_argument("--to", required=True)
    p.set_defaults(fn=cmd_extract)

    p = sub.add_parser("restore", help="put ONE file back into the repo")
    p.add_argument("name", nargs="?", default="latest")
    p.add_argument("--path", required=True)
    p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_restore)

    sub.add_parser("now", help="take a backup now").set_defaults(fn=cmd_now)
    sub.add_parser("status", help="the backup system's state").set_defaults(fn=cmd_status)

    args = ap.parse_args()
    if not getattr(args, "fn", None):
        args.full = False
        return cmd_list(args)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
