"""`python -m harness.skills.graph build [--registry PATH] [--rules a,b]` prints the summary."""
from __future__ import annotations

import argparse
import json
import sys

from harness.skills import graph


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m harness.skills.graph")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="rebuild the graph from the registry and transcripts")
    b.add_argument("--registry", default="")
    b.add_argument("--rules", default="", help="comma-separated; default is all four")
    a = ap.parse_args(argv)
    try:
        s = graph.build(a.registry, [r for r in a.rules.split(",") if r] or None)
    except (ValueError, OSError) as e:
        print("graph build failed: %s" % e, file=sys.stderr)
        return 1
    print(json.dumps(s, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
