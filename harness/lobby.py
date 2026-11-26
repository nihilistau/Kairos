"""THE LOBBY — the launcher as a page, before anything is running (2026-11-26, design §5,
ruling 9.3: "TUI + lobby page").

    kairos.bat lobby            ->  http://127.0.0.1:8799/   (opens in the browser)

The same four choices as the menu — companion, who she talks to, how she runs (her own
engine, an external one, RunPod), and Start / Stop — with what is running on each profile's
port. It serves ONE page and four JSON doors, all through harness/launcher.py, which drives
serve.py and nothing else. When she is up the page links to her room.

Stdlib only; loopback only; a POST is accepted only from this page's own origin (the same
rule the gateway's _guard keeps) — a web page elsewhere cannot start or stop her.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from harness import home as H
from harness import launcher as L

PORT = 8799
ORIGIN = f"http://127.0.0.1:{PORT}"
_JOB = {"running": "", "log": []}

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Kairos · lobby</title>
<style>
:root { color-scheme: dark; --bg:#070a0f; --s:#111824; --hair:rgba(160,190,220,.18); --t1:#e6edf5; --t2:#9fb0c3; --acc:#5fd4e0; --warn:#f59e0b; }
* { box-sizing: border-box; } body { margin:0; background:var(--bg); color:var(--t1); font:14px/1.5 system-ui, sans-serif; }
main { max-width: 760px; margin: 0 auto; padding: 24px 16px; display:flex; flex-direction:column; gap:16px; }
h1 { font-size: 20px; font-weight: 500; margin: 0; } .dim { color: var(--t2); font-size: 13px; }
section { background: var(--s); border: 1px solid var(--hair); border-radius: 10px; padding: 12px 14px; }
h2 { font-size: 11px; letter-spacing: .12em; text-transform: uppercase; margin: 0 0 8px; color: var(--t2); font-weight: 500; }
.opts { display:grid; grid-template-columns: repeat(auto-fill, minmax(200px,1fr)); gap: 8px; }
.opt { text-align:left; background:none; color:var(--t1); border:1px solid var(--hair); border-radius:8px; padding:8px 10px; cursor:pointer; font:inherit; }
.opt.on { border-color: var(--acc); } .opt small { display:block; color: var(--t2); font-size: 12px; }
.row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
button.go { background: var(--acc); color: #04252a; border: 0; border-radius: 8px; padding: 8px 16px; font: inherit; cursor: pointer; }
button.ghost { background: none; color: var(--t1); border: 1px solid var(--hair); border-radius: 8px; padding: 8px 16px; font: inherit; cursor: pointer; }
a { color: var(--acc); } pre { white-space: pre-wrap; font-size: 12px; color: var(--t2); max-height: 200px; overflow:auto; margin:8px 0 0; }
.up { color: #34d399; } .warn { color: var(--warn); }
</style></head><body><main>
<h1>Kairos</h1><div class="dim">Choose who, how, and start her. Everything here is the same as <code>kairos.bat</code>.</div>
<section><h2>Running now</h2><div id="status" class="dim">…</div></section>
<section><h2>Companion</h2><div id="comps" class="opts"></div></section>
<section><h2>Talking to</h2><div id="users" class="opts"></div><div class="dim">Takes effect at the next start. Add people in the room (People).</div></section>
<section><h2>How she runs</h2><div id="profs" class="opts"></div></section>
<section><div class="row"><button class="go" id="start">Start her</button><button class="ghost" id="stop">Stop</button>
<span id="msg" class="dim"></span></div><pre id="log"></pre></section>
</main><script>
let S = {};
const j = (u, b) => fetch(u, b ? {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(b)} : {}).then(r => r.json());
function opt(el, items, cur, onPick, label, sub) {
  el.innerHTML = ''; items.forEach(it => { const b = document.createElement('button'); b.className = 'opt' + (it.id === cur ? ' on' : '');
    b.innerHTML = '<b></b><small></small>'; b.querySelector('b').textContent = label(it); b.querySelector('small').textContent = sub(it) || '';
    b.onclick = () => onPick(it); el.appendChild(b); });
}
async function load() {
  S = await j('/api/state');
  const st = document.getElementById('status');
  st.innerHTML = S.status.filter(s => s.up).map(s => `<span class="up">:${s.port} up</span> — ${s.companion || ''}, talking to ${s.user || '—'} · <a href="http://127.0.0.1:${s.port}/room/">open her room</a>`).join('<br>') || 'nothing is running';
  opt(document.getElementById('comps'), S.companions, S.companion, async it => { await j('/api/choose', {companion: it.id}); load(); }, it => it.name, it => it.id);
  opt(document.getElementById('users'), S.users, (S.users.find(u => u.active) || {}).id, async it => { await j('/api/choose', {user: it.id}); load(); }, it => it.names[0], it => it.handle);
  opt(document.getElementById('profs'), S.profiles, S.profile, async it => { await j('/api/choose', {profile: it.id}); load(); }, it => it.id, it => it.engine);
  document.getElementById('log').textContent = (S.job.log || []).slice(-40).join('\\n');
  document.getElementById('msg').textContent = S.job.running ? S.job.running + '…' : '';
}
document.getElementById('start').onclick = async () => { const r = await j('/api/start', {}); document.getElementById('msg').textContent = r.ok ? 'starting…' : r.error; };
document.getElementById('stop').onclick = async () => { const r = await j('/api/stop', {}); document.getElementById('msg').textContent = r.ok ? 'stopping…' : r.error; };
load(); setInterval(load, 3000);
</script></body></html>"""


def _run(label: str, argv) -> None:
    _JOB.update(running=label, log=[])
    try:
        p = subprocess.Popen(argv, cwd=H.ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace")
        for line in p.stdout:
            _JOB["log"].append(line.rstrip())
            del _JOB["log"][:-200]
        p.wait()
        _JOB["log"].append(f"[{label} finished: exit {p.returncode}]")
    finally:
        _JOB["running"] = ""


def state() -> dict:
    st = L.load_state()
    homes = [h for h in H.list_homes() if not h.get("error")]
    comp = next((h for h in homes if h["id"] == st.get("companion")), homes[0] if homes else None)
    profs = L.profiles()
    prof = st.get("profile") or (next((p["name"] for p in profs if p.get("home") == (comp or {}).get("id")), "")
                                 or (profs[0]["name"] if profs else ""))
    return {"companions": homes, "companion": (comp or {}).get("id", ""),
            "users": L.users_of(comp["dir"]) if comp else [],
            "profiles": [{"id": p["name"], "engine": p["engine"]} for p in profs], "profile": prof,
            "status": L.status(), "job": dict(_JOB)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):                  # quiet: the page shows what matters
        return

    def _send(self, code: int, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        if self.path == "/api/state":
            return self._send(200, state())
        return self._send(404, {"ok": False})

    def do_POST(self):  # noqa: N802
        if self.headers.get("Origin", "") != ORIGIN:
            return self._send(403, {"ok": False, "error": "cross-origin request refused"})
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
        except ValueError:
            return self._send(400, {"ok": False, "error": "bad body"})
        st = L.load_state()
        if self.path == "/api/choose":
            if body.get("companion"):
                st["companion"] = str(body["companion"])
            if body.get("profile"):
                st["profile"] = str(body["profile"])
            if body.get("user") and st.get("companion"):
                try:
                    L.set_user(H.home_dir(st["companion"]), str(body["user"]))
                except Exception as e:           # a refusal is shown, not hidden
                    return self._send(400, {"ok": False, "error": str(e)})
            L.save_state(st)
            return self._send(200, {"ok": True})
        if self.path in ("/api/start", "/api/stop"):
            if _JOB["running"]:
                return self._send(409, {"ok": False, "error": _JOB["running"] + " is still running"})
            prof = st.get("profile") or state()["profile"]
            if self.path == "/api/start":
                if not prof:
                    return self._send(400, {"ok": False, "error": "choose how she runs"})
                st["started_profile"] = prof
                L.save_state(st)
                argv = [sys.executable, "-m", "harness.launcher", "start", "--profile=" + prof] + \
                       (["--companion=" + st["companion"]] if st.get("companion") else [])
                label = "start"
            else:
                argv = [sys.executable, "-m", "harness.launcher", "stop"] + \
                       (["--profile=" + st["started_profile"]] if st.get("started_profile") else [])
                label = "stop"
            threading.Thread(target=_run, args=(label, argv), daemon=True).start()
            return self._send(200, {"ok": True})
        return self._send(404, {"ok": False})


def main(open_browser: bool = True) -> int:
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"  the lobby: {ORIGIN}/   (Ctrl+C to close it; she keeps running)")
    if open_browser:
        webbrowser.open(ORIGIN + "/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
