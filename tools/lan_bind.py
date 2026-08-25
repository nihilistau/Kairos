"""lan_bind — scope the gateway's LAN exposure to ONE subnet, and prove it is scoped.

WHY THIS EXISTS. `[serve].bind` widens the gateway off loopback so the watch can reach it
without an adb tunnel. Loopback IS the security model (app.py's `__main__` says why in
full: `_origin_ok` returns True when there is no Origin header, so the origin check
defends against a browser and nothing else), and widening it means anything that can reach
the port can POST /v1/chat — which has shell access and file write through the tool loop.

The bind has to be broad because the room talks to 127.0.0.1 and a single-IP bind would
break it. So the SCOPING is a firewall rule, not a bind address: allow the port from the
one subnet that is his, and block it everywhere else. This machine is also on a guest
network and three virtual switches, and "his network" means exactly one of them.

    python tools/lan_bind.py --status          # is the rule there, and what does it allow
    python tools/lan_bind.py --apply           # create/replace it (needs Administrator)
    python tools/lan_bind.py --remove          # take it away again

NOT AUTOMATIC, and never called from serve.py. A firewall rule is a change to his machine
outside this repo; it is asked for explicitly or it does not happen.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

RULE = "kairos-gateway-lan"
DEFAULT_SUBNET = "10.0.0.0/24"


def _ps(script: str) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                       capture_output=True, text=True)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def port() -> int:
    return int(os.environ.get("SP_GATEWAY_PORT") or 8800)


def status() -> None:
    print("gateway port : %d" % port())
    # NOT os.environ. That is THIS shell's environment, not the gateway's — the gateway
    # got its bind from serve.py's build_env in a different process, and printing my own
    # variable next to a question about hers is exactly the kind of instrument that
    # reports the wrong machine. What is actually listening is the answer, below.
    out = _ps("Get-NetFirewallRule -DisplayName '%s' -ErrorAction SilentlyContinue | "
              "ForEach-Object { $a=$_ | Get-NetFirewallAddressFilter; "
              "$p=$_ | Get-NetFirewallPortFilter; "
              "'{0}|{1}|{2}|{3}' -f $_.Enabled,$_.Action,$p.LocalPort,$a.RemoteAddress }" % RULE)
    if not out:
        print("firewall rule: ABSENT")
        print("")
        print("  The gateway is reachable from EVERY network this machine is on, including")
        print("  any guest connection and the virtual switches. Run --apply (as")
        print("  Administrator) to scope it, or set [serve].bind back to 127.0.0.1.")
        return
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) == 4:
            print("firewall rule: enabled=%s action=%s port=%s from=%s"
                  % (parts[0], parts[1], parts[2], parts[3]))
        else:
            print("firewall rule: %s" % line)
    # AND WHAT IS ACTUALLY LISTENING, because a rule about a port nothing serves is a rule
    # that proves nothing.
    listen = _ps("Get-NetTCPConnection -LocalPort %d -State Listen -ErrorAction "
                 "SilentlyContinue | Select-Object -First 4 -ExpandProperty LocalAddress"
                 % port())
    print("listening on : %s" % (listen.replace("\n", ", ") or "(nothing)"))


def apply(subnet: str) -> int:
    admin = _ps("([Security.Principal.WindowsPrincipal]"
                "[Security.Principal.WindowsIdentity]::GetCurrent())"
                ".IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)")
    if admin.strip().lower() != "true":
        print("!! needs Administrator. Re-run an elevated shell:")
        print("   python tools/lan_bind.py --apply --subnet %s" % subnet)
        return 2
    _ps("Remove-NetFirewallRule -DisplayName '%s' -ErrorAction SilentlyContinue" % RULE)
    out = _ps("New-NetFirewallRule -DisplayName '%s' -Direction Inbound -Action Allow "
              "-Protocol TCP -LocalPort %d -RemoteAddress %s -Profile Any | Out-Null; $?"
              % (RULE, port(), subnet))
    if "True" not in out:
        print("!! rule not created: %s" % out[:300])
        return 1
    print("allowed %s -> TCP %d" % (subnet, port()))
    # THE OTHER HALF: allowing one subnet does not deny the rest on Windows — an existing
    # broad allow rule would still let anything through. Say so rather than imply cover.
    broad = _ps("Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow "
                "-ErrorAction SilentlyContinue | ForEach-Object { $p=$_|"
                "Get-NetFirewallPortFilter; if ($p.LocalPort -eq %d -and "
                "$_.DisplayName -ne '%s') { $_.DisplayName } }" % (port(), RULE))
    if broad.strip():
        print("!! ANOTHER RULE ALSO ALLOWS THIS PORT, so the scoping is not complete:")
        for n in broad.splitlines()[:6]:
            print("     %s" % n.strip())
        print("   Remove or narrow those, or the subnet limit above is decorative.")
    status()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--subnet", default=DEFAULT_SUBNET)
    a = ap.parse_args()
    if a.remove:
        _ps("Remove-NetFirewallRule -DisplayName '%s' -ErrorAction SilentlyContinue" % RULE)
        print("removed %s" % RULE)
        status()
    elif a.apply:
        sys.exit(apply(a.subnet))
    else:
        status()
