"""python -m harness.setup — the setup centre in a terminal, for a fresh install before the
room has an engine (the room's Get set up window is the same steps). Stdlib only."""
from __future__ import annotations

import os
import re
import sys
import time

from harness.setup import installer as I
from harness.setup.net import CatalogueError


def _ask(prompt: str, default: str = "") -> str:
    a = input(f"  {prompt}{' [' + default + ']' if default else ''}: ").strip()
    return a or default


def _choose(title: str, items, label, default_id: str):
    print("\n  " + title)
    for i, it in enumerate(items):
        print("   %s %d. %s" % ("*" if it["id"] == default_id else " ", i + 1, label(it)))
    a = _ask("number", str(1 + next((i for i, it in enumerate(items) if it["id"] == default_id), 0)))
    try:
        return items[int(a) - 1]
    except (ValueError, IndexError):
        return next(it for it in items if it["id"] == default_id)


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    k = I.kits()
    hw = I.hardware()
    sg = I.suggest(hw)
    print("\n  Kairos - get set up")
    print("  this machine: %s; %s GB memory" % (", ".join(f"{g['name']} ({g['vram_gb']} GB)" for g in hw["gpus"]) or "no NVIDIA card", hw["ram_gb"]))
    print("  suggested: " + sg["why"])
    e = _choose("How she runs", k["engines"], lambda x: f"{x['title']} - {x['about']}", sg["engine"])
    m = _choose("Her model", k["models"], lambda x: f"{x['title']}{'  [UNCENSORED]' if x.get('uncensored') else ''} - about {x['approx_gb']} GB",
                sg["model"])
    if m.get("uncensored"):
        print("\n  !! " + k["uncensored_warning"])
        if _ask("continue with it? (yes/no)", "no").lower() not in ("y", "yes"):
            return 1
    dest = _ask("where to put the downloads (a full path)", os.path.join(I.H.ROOT, "data"))
    os.makedirs(dest, exist_ok=True)
    reuse = _ask("folders where you already keep models (';'-separated, blank for none)",
                 os.environ.get("SP_SETUP_REUSE", ""))
    try:
        p = I.plan(m["id"], e["id"], dest, reuse=[d for d in reuse.split(";") if d.strip()])
    except (I.SetupError, CatalogueError) as x:
        print("  !! " + str(x))
        return 1
    for it in p["items"]:
        print("   %-70s %6.1f GB%s" % (it["name"][:70], it["size"] / 2 ** 30, "  (already here)" if it.get("reuse") else ""))
    print("  %.1f GB to download, %.1f GB free" % (p["need_bytes"] / 2 ** 30, p["free_bytes"] / 2 ** 30))
    if not p["fits"]:
        print("  !! not enough room there - choose a folder on a bigger drive")
        return 1
    if _ask(f"accept the licence ({p['licence'].get('name')}, {p['licence'].get('url', '')})? (yes/no)", "no").lower() not in ("y", "yes"):
        return 1
    if p["items"]:
        I.start(p, licence_ok=True)
        while I.status().get("running"):
            st = I.status()
            print("\r  fetching %-50s %.1f GB " % (st.get("current", "")[:50], (st.get("bytes") or 0) / 2 ** 30), end="", flush=True)
            time.sleep(2)
        st = I.status()
        print()
        if st.get("error"):
            print("  !! " + st["error"] + " - run this again to resume")
            return 1
        ap = I.pending_approval(p)
        if ap:
            print(f"\n  approve the engine before it runs: {ap['path']}\n  from {ap['publisher']} release {ap['release']}\n  SHA-256 {ap['sha256']}")
            if _ask("approve it? (yes/no)", "no").lower() not in ("y", "yes"):
                return 1
            I.approve(ap["sha256"])
    # HER, AND YOU (first-time setup = create companion + create user, design §7a): an
    # existing companion, or a new one made the same way the room makes one (named persona,
    # the default face and wardrobe, a local voice); then who you are, as her user1.
    from harness import home as Hm
    from harness import companion_create as CC
    homes = [h for h in Hm.list_homes() if not h.get("error")]
    if homes:
        print("\n  companions here: " + ", ".join(f"{h['name']} ({h['id']})" for h in homes))
    comp = _ask("which companion - an id above, or a NAME for a new one", homes[0]["id"] if homes else "Kairos")
    if not any(h["id"] == comp for h in homes):
        cid = re.sub(r"[^a-z0-9_-]+", "-", comp.lower()).strip("-") or "kairos"
        r = CC.create(cid, comp)
        print(f"  made {r['name']}: a persona in her name, the default face and wardrobe, a local voice"
              "  (shape her later in the room: Character, Persona)")
        comp = cid
    you = _ask("your name (what she calls you; blank to skip)", "")
    pron = _ask("your pronouns (he/him/his, she/her/her, they/them/their)", "they/them/their") if you else ""
    if you:
        saved = os.environ.get("SP_PEOPLE")
        os.environ["SP_PEOPLE"] = Hm.resolve(Hm.home_dir(comp))["people"]
        try:
            from harness import people as PP
            u = next((x for x in PP.users() if you.lower() in [n.lower() for n in x["names"]]), None) \
                or PP.add_user(you, pron)
            PP.set_active(u["id"])
            print(f"  you are her {u['handle']}")
        finally:
            if saved is None:
                os.environ.pop("SP_PEOPLE", None)
            else:
                os.environ["SP_PEOPLE"] = saved
    name = _ask("a name for this profile", "local")
    base = _ask("the engine's address", "http://127.0.0.1:1234") if e.get("external") else ""
    try:
        path = I.write_profile(name, p, companion=comp, base_url=base, user_name=you, user_pronouns=pron)
    except I.SetupError as x:
        print("  !! " + str(x))
        return 1
    print(f"\n  written {path}\n  start her: kairos.bat start --profile={name}" + (f" --companion={comp}" if comp else ""))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(1)
