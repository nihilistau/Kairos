"""companion — list, export, import, reset and undo companions from a terminal.

    python tools/companion.py list
    python tools/companion.py create  ivy --name "Ivy" [--voice eve]   # a NEW companion, not blank
    python tools/companion.py export  kairos [--parts personality,history] [--out FILE]
    python tools/companion.py inspect FILE
    python tools/companion.py new     FILE  <id> [--name "Name"]        # import as a NEW companion
    python tools/companion.py load    kairos FILE --parts personality --yes
    python tools/companion.py reset   kairos --parts history --yes
    python tools/companion.py undo    kairos --yes
    python tools/companion.py history kairos

load / reset / undo refuse while she is running on that home (stop her, or use the room,
which schedules the change for her next start). Nothing is ever deleted: the old contents
move to companions/<id>/archive/<ts>/ and a bundle of them goes to var/bundles first.
See harness/bundle.py.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from harness import bundle as B  # noqa: E402
from harness import home as H  # noqa: E402


def _mb(n: int) -> str:
    return "%.1f MB" % (n / 1e6)


def _parts(s: str):
    ps = [p.strip() for p in (s or "").split(",") if p.strip()]
    bad = [p for p in ps if p not in B.PARTS]
    if bad:
        raise SystemExit(f"unknown part(s) {bad}; parts are {', '.join(B.PARTS)}")
    return ps


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="companion", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list")
    p = sub.add_parser("create"); p.add_argument("id"); p.add_argument("--name", default=""); p.add_argument("--voice", default="")
    p = sub.add_parser("export"); p.add_argument("id"); p.add_argument("--parts", default="personality,history"); p.add_argument("--out", default="")
    p = sub.add_parser("inspect"); p.add_argument("file")
    p = sub.add_parser("new"); p.add_argument("file"); p.add_argument("id"); p.add_argument("--name", default="")
    p = sub.add_parser("load"); p.add_argument("id"); p.add_argument("file"); p.add_argument("--parts", required=True); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("reset"); p.add_argument("id"); p.add_argument("--parts", required=True); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("undo"); p.add_argument("id"); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("history"); p.add_argument("id")
    a = ap.parse_args(argv)
    try:
        if a.cmd in (None, "list"):
            for h in H.list_homes():
                live = " (running)" if not h.get("error") and H.is_live(h["dir"]) else ""
                print(f"  {h['id']:<16} {h['name']:<20} {h['dir']}{live}" + (f"  !! {h['error']}" if h.get("error") else ""))
            for b in B.listing()[:10]:
                print(f"  bundle  {b['name']}  {_mb(b['size'])}  {','.join(b.get('parts', []))}")
            return 0
        if a.cmd == "create":
            from harness import companion_create as CC
            r = CC.create(a.id, a.name, voice=a.voice)
            print(f"made {r['name']} ({r['id']}) at {r['home']}")
            print(f"  persona: {r['persona_files']} file(s), named; face: {r['face'] or r['face_why']}; voice: {r['voice']}")
            print(f"  start her with: python serve.py <profile> --companion={r['id']}")
            return 0
        if a.cmd == "export":
            r = B.export(H.home_dir(a.id), _parts(a.parts), out=a.out)
            print(f"exported {', '.join(r['parts'])}: {r['files']} files, {_mb(r['bytes'])} -> {r['path']}")
            return 0
        if a.cmd == "inspect":
            m = B.inspect(a.file)
            print(f"{m['name']}: {m['companion']['name']} ({m['companion']['id']}), made {m['created']}")
            for k, u in m["units"].items():
                print(f"  {u['part']:<12} {k:<16} {u['files']} file(s)")
            print("  every checksum verified")
            return 0
        if a.cmd == "new":
            r = B.import_new(a.file, a.id, a.name)
            print(f"new companion {r['id']} at {r['home']} ({', '.join(r['parts'])})")
            print(f"  start her with: python serve.py <profile> --companion={r['id']}")
            return 0
        if a.cmd == "history":
            for r in B.history(H.home_dir(a.id)):
                print(f"  {r['ts']}  {r['op']:<8} {','.join(r.get('parts', []))}  {r.get('before') or r.get('undoes') or r.get('from') or ''}")
            return 0
        home = H.home_dir(a.id)
        if not a.yes:
            what = {"load": f"replace {a.parts} of {a.id} with {getattr(a, 'file', '')}",
                    "reset": f"reset {a.parts} of {a.id} to a blank slate",
                    "undo": f"undo the last change to {a.id}"}[a.cmd]
            print(f"would {what}. Nothing is deleted (old contents -> {home}{os.sep}archive). "
                  "Run again with --yes.")
            return 2
        r = {"load": lambda: B.replace(home, a.file, _parts(a.parts)),
             "reset": lambda: B.reset(home, _parts(a.parts)),
             "undo": lambda: B.undo(home)}[a.cmd]()
        print(f"{r['op']} done ({', '.join(r['parts'])}). Old contents: {home}{os.sep}archive{os.sep}{r.get('undoes') or r['ts']}"
              + (f"; bundle {r['before']}" if r.get("before") else ""))
        return 0
    except (B.BundleError, H.HomeError) as e:
        print(f"!! {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
