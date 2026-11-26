"""THE LAUNCHER — choose who, how, and start her (2026-11-26, design §5).

    kairos.bat                     the menu (Windows; `python -m harness.launcher` anywhere)
    kairos.bat start [--companion=ivy] [--profile=companion]
    kairos.bat stop | status | list | lobby      (lobby: the same, as a page on :8799)

One menu, the same choices the room makes: which COMPANION (her home), which USER she is
talking to (the home's people), which PROFILE (how she runs: her own engine, an external
one, RunPod), then Start / Stop / Status / Back up / Open the room. It drives serve.py — the
one door — and nothing else; it holds no state of its own beyond the last choices
(var/launcher.json), so a choice made here and one made in the room never disagree for long.

Stdlib only, so it runs on a fresh clone before anything is installed, and over SSH.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
import urllib.request
import webbrowser
from typing import List, Optional

from harness import home as H

ROOT = H.ROOT
STATE = os.path.join(H.VAR, "launcher.json")


# ── what there is ──────────────────────────────────────────────────────────────────────
def profiles() -> List[dict]:
    out = []
    d = os.path.join(ROOT, "profiles")
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not f.endswith(".toml"):
            continue
        p = os.path.join(d, f)
        about = ""
        try:
            with open(p, encoding="utf-8") as fh:
                first = fh.readline().strip()
            about = first.lstrip("# ").strip()[:90]
            with open(p, "rb") as fh:
                c = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError) as e:
            out.append({"name": f[:-5], "about": f"!! unreadable: {e}", "port": 0, "engine": "?"})
            continue
        eng = (c.get("engine") or {}).get("kind") or "sp"
        out.append({"name": f[:-5], "about": about, "port": int((c.get("serve") or {}).get("gateway_port") or 8800),
                    "engine": "RunPod (the model on a rented pod)" if c.get("runpod") else
                              {"sp": "her own engine", "openai": "an external engine"}.get(eng, eng),
                    "base_url": (c.get("engine") or {}).get("base_url", ""),
                    "home": (c.get("companion") or {}).get("home", "")})
    return out


def users_of(home: str) -> List[dict]:
    pp = H.resolve(home).get("people", "")
    saved = os.environ.get("SP_PEOPLE")
    os.environ["SP_PEOPLE"] = pp
    try:
        from harness import people as PP
        return PP.users()
    finally:
        if saved is None:
            os.environ.pop("SP_PEOPLE", None)
        else:
            os.environ["SP_PEOPLE"] = saved


def set_user(home: str, pid: str) -> dict:
    pp = H.resolve(home).get("people", "")
    saved = os.environ.get("SP_PEOPLE")
    os.environ["SP_PEOPLE"] = pp
    try:
        from harness import people as PP
        return PP.set_active(pid)
    finally:
        if saved is None:
            os.environ.pop("SP_PEOPLE", None)
        else:
            os.environ["SP_PEOPLE"] = saved


def load_state() -> dict:
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(s: dict) -> None:
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)
    from harness.store_io import replace_atomic
    replace_atomic(tmp, STATE)


def _get(url: str, timeout: float = 2.0) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except Exception as _swx:                  # nothing listening is the common, quiet case
        from harness.loud import swallowed as _swallowed
        import logging
        _swallowed(logging.getLogger(__name__), "_get", _swx, lane="launcher")
        return None


def status() -> List[dict]:
    """Every profile's gateway port, asked: up? which companion? which user?"""
    out, seen = [], set()
    for p in profiles():
        if not p["port"] or p["port"] in seen:
            continue
        seen.add(p["port"])
        h = _get(f"http://127.0.0.1:{p['port']}/health")
        row = {"port": p["port"], "up": bool(h and h.get("ok")), "warm": bool(h and h.get("warm"))}
        if row["up"]:
            c = _get(f"http://127.0.0.1:{p['port']}/v1/companion") or {}
            u = _get(f"http://127.0.0.1:{p['port']}/v1/people") or {}
            row["companion"] = ((c.get("current") or {}).get("name")) or "(no home)"
            row["user"] = ((u.get("active") or {}).get("names") or ["?"])[0] if u.get("active") else ""
        out.append(row)
    return out


# ── doing it ───────────────────────────────────────────────────────────────────────────
def _profile(name: str) -> dict:
    try:
        with open(os.path.join(ROOT, "profiles", name + ".toml"), "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


RUNPOD = os.path.join(ROOT, "tools", "runpod", "runpod.ps1")


def runpod_argv(action: str, profile: str, c: dict) -> List[str]:
    """tools/runpod/runpod.ps1 <action> with the profile's [runpod] table as its arguments —
    the pod's details live in the profile, never in the script (P6, design §5)."""
    r = c.get("runpod") or {}
    port = int((c.get("serve") or {}).get("gateway_port") or 8800)
    argv = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", RUNPOD, action,
            "-Profile", profile, "-Port", str(port)]
    if action == "up":
        for flag, key in (("-VolumeId", "volume_id"), ("-ModelDir", "model_dir"), ("-Model", "model"),
                          ("-Mmproj", "mmproj"), ("-Draft", "draft"), ("-Image", "image"),
                          ("-MaxPrice", "max_price"), ("-MinGb", "min_gb"), ("-Ctx", "ctx"), ("-PodName", "pod_name")):
            if r.get(key) not in (None, ""):
                argv += [flag, str(r[key])]
    elif r.get("pod_name"):
        argv += ["-PodName", str(r["pod_name"])]
    return argv


def start(profile: str, companion: str = "") -> int:
    c = _profile(profile)
    if c.get("runpod"):
        # THE MODEL ON A POD (P6): rent it and point the profile at it first; serve.py after.
        print("  renting the pod for " + profile + " (it bills until you stop)")
        rc = subprocess.call(runpod_argv("up", profile, c), cwd=ROOT)
        if rc != 0:
            return rc
    argv = [sys.executable, os.path.join(ROOT, "serve.py"), profile]
    if companion:
        argv.append("--companion=" + companion)
    print("  running: " + " ".join(argv[1:]))
    return subprocess.call(argv, cwd=ROOT)


def stop(profile: str = "") -> int:
    """serve.py --stop; and for a RunPod profile, her day pass on the pod, then the pod
    TERMINATED (runpod.ps1 down stops her too) — so a stop never leaves a pod billing."""
    c = _profile(profile) if profile else {}
    if c.get("runpod"):
        return subprocess.call(runpod_argv("down", profile, c), cwd=ROOT)
    # THE PROFILE GOES WITH THE STOP (2026-11-26, found by the fresh install): a bare --stop looked
    # for a gateway on :8800 and left the profile's own engine running — the setup centre's
    # llama-server ([engine] command) and a gateway on another port are only known from it.
    return subprocess.call([sys.executable, os.path.join(ROOT, "serve.py")] + ([profile] if profile else [])
                           + ["--stop"], cwd=ROOT)


def backup(companion: str) -> str:
    from harness import bundle as B
    r = B.export(H.home_dir(companion))
    return r["path"]


# ── the menu ───────────────────────────────────────────────────────────────────────────
def _pick(title: str, items: List[str], current: int = -1) -> Optional[int]:
    print("\n  " + title)
    for i, it in enumerate(items):
        print("   %s %d. %s" % ("*" if i == current else " ", i + 1, it))
    ans = input("  number (Enter to keep%s): " % ("" if current >= 0 else ", none chosen")).strip()
    if not ans:
        return current if current >= 0 else None
    try:
        n = int(ans) - 1
        return n if 0 <= n < len(items) else None
    except ValueError:
        return None


def menu() -> int:
    st = load_state()
    while True:
        homes = [h for h in H.list_homes() if not h.get("error")]
        profs = profiles()
        comp = next((h for h in homes if h["id"] == st.get("companion")), homes[0] if homes else None)
        prof = next((p for p in profs if p["name"] == st.get("profile")), None)
        if prof is None and comp:
            prof = next((p for p in profs if p.get("home") == comp["id"]), profs[0] if profs else None)
        users = users_of(comp["dir"]) if comp else []
        act = next((u for u in users if u.get("active")), None)
        print("\n  -- Kairos ----------------------------------------------")
        print("   companion : %s" % (f"{comp['name']} ({comp['id']})" if comp else "none yet - make one in the room (Character)"))
        print("   talking to: %s" % (f"{act['names'][0]} ({act['handle']})" if act else "-"))
        print("   runs on   : %s" % (f"{prof['name']} - {prof['engine']}" if prof else "no profiles/ found"))
        for s in status():
            if s["up"]:
                print("   RUNNING   : :%d %s, talking to %s%s" % (s["port"], s.get("companion", ""), s.get("user") or "-",
                                                               "" if s["warm"] else " (warming up)"))
        print("\n   1 start   2 stop   3 status   4 companion   5 user   6 profile   7 back up   8 open the room   9 get set up   q quit")
        c = input("  > ").strip().lower()
        if c in ("q", "quit", "exit"):
            return 0
        if c == "1" and prof:
            st["started_profile"] = prof["name"]
            save_state(st)
            start(prof["name"], comp["id"] if comp else "")
        elif c == "2":
            stop(st.get("started_profile") or (prof["name"] if prof else ""))
        elif c == "3":
            for s in status():
                print("   :%d %s" % (s["port"], ("up, " + s.get("companion", "") + ", " + (s.get("user") or "-")) if s["up"] else "down"))
        elif c == "4" and homes:
            i = _pick("Companion", [f"{h['name']} ({h['id']})" for h in homes], homes.index(comp) if comp in homes else -1)
            if i is not None:
                st["companion"] = homes[i]["id"]
        elif c == "5" and users:
            i = _pick("Who is talking to her (takes effect at the next start)",
                      [f"{u['names'][0]} ({u['handle']})" for u in users], users.index(act) if act in users else -1)
            if i is not None:
                set_user(comp["dir"], users[i]["id"])
        elif c == "6" and profs:
            i = _pick("How she runs", [f"{p['name']} - {p['engine']}  {p['about']}" for p in profs],
                      profs.index(prof) if prof in profs else -1)
            if i is not None:
                st["profile"] = profs[i]["name"]
        elif c == "7" and comp:
            print("  saved " + backup(comp["id"]))
        elif c == "9":
            subprocess.call([sys.executable, "-m", "harness.setup"], cwd=ROOT)
        elif c == "8" and prof:
            webbrowser.open(f"http://127.0.0.1:{prof['port']}/room/")
        save_state(st)


def main(argv=None) -> int:
    # A console that cannot show a character must not stop the launcher (cp1252 on Windows).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {a.split("=", 1)[0][2:]: a.split("=", 1)[1] for a in argv if a.startswith("--") and "=" in a}
    cmd = next((a for a in argv if not a.startswith("--")), "")
    if not cmd:
        try:
            return menu()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0
    st = load_state()
    if cmd == "start":
        prof = opts.get("profile") or st.get("profile")
        comp = opts.get("companion") or st.get("companion") or ""
        if not prof:
            print("name a profile: kairos.bat start --profile=<name>   (profiles/*.toml)")
            return 2
        st.update(profile=prof, companion=comp, started_profile=prof)
        save_state(st)
        return start(prof, comp)
    if cmd == "stop":
        return stop(opts.get("profile") or st.get("started_profile") or "")
    if cmd == "status":
        for s in status():
            print(":%d %s" % (s["port"], ("up, " + s.get("companion", "") + ", talking to " + (s.get("user") or "-")) if s["up"] else "down"))
        return 0
    if cmd == "lobby":
        from harness import lobby
        return lobby.main()
    if cmd == "list":
        for h in H.list_homes():
            print("companion  %-14s %s" % (h["id"], h.get("error") or h["name"]))
        for p in profiles():
            print("profile    %-14s %s - %s" % (p["name"], p["engine"], p["about"]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
