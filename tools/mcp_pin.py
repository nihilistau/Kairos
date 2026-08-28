"""mcp_pin — see and accept the fingerprints of the MCP tools she is offered.

WHY THIS EXISTS. `harness/mcp_server/bridge.py` fingerprints every bridged tool's name,
description and schema on first sight, and REFUSES the tool if that fingerprint later
changes (the rug-pull shape: same name, new description, and the description IS prompt).
A refusal that has no acceptance door is not a security control, it is an outage — so this
is the other half, and the refusal message names it by the exact command to run.

    python tools/mcp_pin.py                      # what is pinned, and what is live now
    python tools/mcp_pin.py --accept browser take_screenshot
    python tools/mcp_pin.py --accept-all browser
    python tools/mcp_pin.py --forget browser     # drop a server's pins entirely (re-TOFU)

TRUST ON FIRST USE is what this is, said plainly: it cannot vouch for the first listing.
What it guarantees is that what she was offered yesterday is what she is offered today, and
that any change is a decision he made rather than one npm made for him at 3am.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness.mcp_server import bridge as B  # noqa: E402


def _live() -> dict:
    """{server: {tool: TOOL}} as the servers describe themselves RIGHT NOW.

    The whole tool, not just its digest (2026-08-28): `--diff` compares the text a pin was
    taken of against the text on offer now, and a digest cannot be diffed against anything.

    UNFILTERED, and it must be: routing this through check_pins would hide the one row the
    command exists to show — a refused tool would read as "not offered right now" and the
    CHANGED line would be unreachable. And it must not LEARN either: a diagnostic that
    silently pinned whatever it saw would mean the control could be defeated by looking at
    it. So this reads the servers directly and compares against the pins by hand."""
    os.environ["SP_MCP_PIN"] = "0"
    out: dict = {}
    for t in B.list_bridged_tools(refresh=True):
        out.setdefault(t.get("server", ""), {})[t.get("name", "")] = t
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--diff", nargs="+", metavar="SERVER [TOOL]",
                    help="what changed between what a tool said when it was pinned "
                         "and what it says now")
    ap.add_argument("--accept", nargs=2, metavar=("SERVER", "TOOL"))
    ap.add_argument("--accept-all", metavar="SERVER")
    ap.add_argument("--forget", metavar="SERVER")
    a = ap.parse_args()
    pins = B.load_pins()

    if a.forget:
        if pins.pop(a.forget, None) is None:
            print("nothing pinned for %r" % a.forget)
            return 1
        B.save_pins(pins)
        print("dropped every pin for %r — the next listing pins whatever it sees" % a.forget)
        return 0

    if a.diff:
        # THE OTHER HALF OF THE REFUSAL. It says "accept it if the change is legitimate";
        # until 2026-08-28 nothing could show what the change WAS, because a pin stored a
        # digest and the text it was taken of was thrown away. This prints it.
        srv = a.diff[0]
        only = a.diff[1] if len(a.diff) > 1 else ""
        live = _live()
        if srv not in live:
            print("server %r listed no tools — is it configured and reachable?" % srv)
            return 1
        names = [only] if only else sorted(set(pins.get(srv, {})) | set(live[srv]))
        shown = 0
        for n in names:
            entry, tool = (pins.get(srv) or {}).get(n), live[srv].get(n)
            if tool is None:
                print("\n%s/%s  the server does not offer this tool right now" % (srv, n))
                shown += 1
                continue
            if entry is None:
                print("\n%s/%s  unpinned — the next listing pins whatever it sees" % (srv, n))
                shown += 1
                continue
            d = B.pin_diff(entry, tool)
            if d["why"] == "unchanged" and not only:
                continue
            shown += 1
            print("\n%s/%s  %s" % (srv, n, d["why"]))
            print("    %s -> %s" % (B.pin_digest(entry), B._digest(tool)))
            for line in d["description"]:
                print("    desc  %s" % line)
            for line in d["schema"]:
                print("    schema %s" % line)
        if not shown:
            print("%r: every pinned tool still says exactly what it said when it was pinned"
                  % srv)
        else:
            print("\naccept:  python tools/mcp_pin.py --accept %s <tool>" % srv)
        return 0

    if a.accept or a.accept_all:
        # RE-LIST, do not trust the cache: accepting a fingerprint you have not just read
        # from the server is accepting a number, which is not the same thing.
        os.environ["SP_MCP_PIN"] = "0"            # see the refused ones too
        live = _live()
        srv = a.accept[0] if a.accept else a.accept_all
        if srv not in live:
            print("server %r listed no tools — is it configured and reachable?" % srv)
            return 1
        names = [a.accept[1]] if a.accept else sorted(live[srv])
        for n in names:
            if n not in live[srv]:
                print("%r has no tool named %r right now" % (srv, n))
                return 1
            was = (pins.get(srv) or {}).get(n)
            # THE RECORD, not the number: a pin that stores only its digest can never show
            # the next reader what changed, which is how this control ended up asking for a
            # judgement nobody could make. See bridge._pin_record.
            rec = B._pin_record(live[srv][n])
            pins.setdefault(srv, {})[n] = rec
            print("pinned %s/%s  %s -> %s"
                  % (srv, n, B.pin_digest(was) or "(new)", rec["digest"]))
        B.save_pins(pins)
        return 0

    live = _live()
    servers = sorted(set(pins) | set(live))
    if not servers:
        print("no MCP servers configured (see mcp_servers.json)")
        return 0
    for srv in servers:
        print("\n%s" % srv)
        for name in sorted(set(pins.get(srv, {})) | set(live.get(srv, {}))):
            p, lt = pins.get(srv, {}).get(name), live.get(srv, {}).get(name)
            p, l = B.pin_digest(p) if p is not None else None, B._digest(lt) if lt else None
            if p and l and p == l:
                mark, note = "  ok ", p
            elif p and not l:
                # either the server dropped the tool, or the pin refused it and it is not
                # in the allowed listing — both are worth seeing, neither is an error here
                mark, note = "  -- ", "%s (pinned; not offered right now)" % p
            elif l and not p:
                mark, note = "  new", "%s (unpinned — the next listing will pin it)" % l
            else:
                mark, note = "CHANGED", "%s -> %s" % (p, l)
            print("  %-8s %-28s %s" % (mark, name, note))
    print("\naccept a change:  python tools/mcp_pin.py --accept <server> <tool>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
