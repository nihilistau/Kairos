"""G-BOUNCE-FLUSH — a gateway bounce does not throw away what she has not delivered yet.

THE BUG (2026-09-27 04:55, measured live). Thirteen own-time lines were queued
(`pending=13` on /v1/kairos/state). `python serve.py companion --gateway-only` ran, and
afterwards `pending=0` with no "redelivered" line in var/gateway.log. The lines were in
the day transcript (`_ON_SPOKE` writes before the outbox), so the CONTENT survived; the
DELIVERY did not.

Why: every serve.py stop path ends in `kill_by_cmdline`, which on Windows is
`Stop-Process -Force` (TerminateProcess) and on POSIX `pkill` from a process that then
exits. A hard kill runs no atexit and no signal handler, so nothing in the dying gateway
can save its outbox. `shutdown.flush()` already wrote the outbox to undelivered.jsonl, and
`scheduler.reload_undelivered()` already brought it back at boot, but only the room's
shutdown ladder and the watchdog called flush. The three serve.py paths (--gateway-only,
--stop, and the stop() in front of every full boot) called nothing.

The fix: serve.py asks the gateway to flush (POST /v1/shutdown/flush, loopback only,
short timeout, best-effort, logged either way) and then kills it. The route calls
`shutdown.bounce_flush()`, which quiesces first so nothing new is queued between the
flush and the kill.

  §1  the seam: bounce_flush() quiesces, writes every queued line, empties the outbox
  §2  round trip: the next process restores them, and drain() (2026-09-27, _POLLED /
      ORPHAN_AFTER_S / LATE_S) hands them to the tab that is polling, late and silent
  §3  a restored row whose `at` is an ISO string (flush() stamps one when a row had none)
      does not crash drain(), which does float(at)
  §4  the route: loopback peers only, and it calls the seam
  §5  serve.py: stop_gateway_only() POSTs the flush BEFORE the kill, against a fake
      gateway on an ephemeral port; a dead or hung gateway does not block the kill
  §6  every stop path goes through stop_gateway_only, and nothing else kills a gateway

Lane: OFFLINE. No daemon, no GPU, and nothing here touches port 8800: the default port
the launcher falls back to is patched to the fake gateway before the first call.
"""
import ast
import http.server
import json
import os
import socket
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from harness_tests._gate import sandbox, check, finish, utf8_stdout  # noqa: E402

utf8_stdout()
_SB = sandbox("g_bounce_flush")  # FIRST, before any harness. import

import _src  # noqa: E402
from harness.control import shutdown as SD  # noqa: E402
from harness.kairos import scheduler as KS  # noqa: E402

# undelivered_path() is hard-wired to her var/room/ — the sandbox does not cover it.
_UP = os.path.join(_SB, "undelivered.jsonl")
_orig_up = SD.undelivered_path
SD.undelivered_path = lambda: _UP


def _reset():
    SD._reset_for_test()
    with KS._LOCK:
        KS._OUTBOX.clear()
        KS._POLLED.clear()
        KS._PENDING_INSIGHT.clear()
    if os.path.exists(_UP):
        os.remove(_UP)


def _msg(text, age_s):
    return {"text": text, "kind": "solo", "mode": "", "speak": True, "reason": "quiet",
            "margin": 0.0, "notes": [], "at": time.time() - age_s, "oid": "o-" + text}


def _rows():
    if not os.path.exists(_UP):
        return []
    with open(_UP, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


try:
    print("1. THE SEAM: QUIESCE, THEN WRITE EVERYTHING QUEUED")
    _reset()
    KS._OUTBOX["room-closed"].extend([_msg("first", 900), _msg("second", 600)])
    KS._OUTBOX["room-open"].append(_msg("third", 300))
    fn = getattr(SD, "bounce_flush", None)
    check("shutdown.bounce_flush exists", callable(fn), "no seam for the serve.py paths")
    res = fn() if callable(fn) else {}
    rows = [r for r in _rows() if r.get("why") == "undelivered"]
    check("every queued line is written to undelivered.jsonl",
          sorted(r["text"] for r in rows) == ["first", "second", "third"], rows)
    check("...each under its own session",
          {r["text"]: r["session"] for r in rows}
          == {"first": "room-closed", "second": "room-closed", "third": "room-open"}, rows)
    check("...the epoch `at` is kept, not restamped",
          bool(rows) and all(isinstance(r.get("at"), float) for r in rows), rows)
    check("...the receipt counts them", (res or {}).get("flushed") == 3, res)
    check("the outbox is empty after the flush",
          not any(KS._OUTBOX.values()), dict(KS._OUTBOX))
    check("the gateway is quiesced, so nothing new queues before the kill",
          SD.is_shutting_down(), "a line spoken between flush and kill would be lost")

    print("\n2. THE NEXT PROCESS GETS THEM BACK, AND drain() DELIVERS THEM")
    # a new process: fresh flag, fresh queues, nobody has polled yet
    SD._reset_for_test()
    with KS._LOCK:
        KS._OUTBOX.clear()
        KS._POLLED.clear()
    r = KS.reload_undelivered()
    check("reload restores all three", r.get("restored") == 3, r)
    got = KS.drain("room-new")
    check("a tab polling after the bounce receives all three, in the order she spoke",
          [m.get("text") for m in got] == ["first", "second", "third"],
          [m.get("text") for m in got])
    check("...marked redelivered", bool(got) and all(m.get("redelivered") for m in got), got)
    check("...and silent, because they are minutes late (LATE_S)",
          bool(got) and all(m.get("speak") is False and m.get("late") is True for m in got), got)
    check("...and a second reload delivers nothing twice",
          len(got) == 3 and KS.reload_undelivered().get("restored") == 0)

    print("\n3. A RESTORED ROW WITH AN ISO `at` DOES NOT BREAK THE POLL")
    _reset()
    iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 300))
    with open(_UP, "w", encoding="utf-8") as f:
        f.write(json.dumps({"session": "room-gone", "why": "undelivered",
                            "text": "stamped by flush", "at": iso}) + "\n")
    KS.reload_undelivered()
    try:
        got = KS.drain("room-new")
        err = None
    except Exception as exc:          # float("2026-...") inside drain
        got, err = [], exc
    check("drain() does not raise on a restored ISO-stamped row", err is None, repr(err))
    check("...and delivers it", [m.get("text") for m in got] == ["stamped by flush"], got)
    check("...with `at` back in the epoch shape drain() compares",
          got and isinstance(got[0].get("at"), float), got)

    print("\n4. THE ROUTE: LOOPBACK ONLY, AND IT CALLS THE SEAM")
    ok_peer = getattr(SD, "peer_may_flush", None)
    check("shutdown.peer_may_flush exists", callable(ok_peer))
    if callable(ok_peer):
        check("127.0.0.1 may flush", ok_peer("127.0.0.1"))
        check("::1 may flush", ok_peer("::1"))
        check("a LAN peer may not (SP_GATEWAY_BIND can open the gateway)",
              not ok_peer("192.168.1.20"))
        check("garbage may not", not ok_peer("not-an-address") and not ok_peer(""))
    branch = None
    for name in _src.files("harness", "server"):
        tree = ast.parse(_src.text("harness", "server", name))
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and isinstance(node.test, ast.Compare) \
                    and any(isinstance(c, ast.Constant) and c.value == "/v1/shutdown/flush"
                            for c in node.test.comparators):
                branch = ast.unparse(ast.Module(body=node.body, type_ignores=[]))
    check("the gateway has a /v1/shutdown/flush branch", branch is not None)
    b = branch or ""
    check("...which checks the peer with peer_may_flush(client_address)",
          "peer_may_flush(" in b and "client_address" in b, b[:300])
    check("...and calls bounce_flush()", "bounce_flush(" in b, b[:300])
    check("...after the peer check",
          "peer_may_flush(" in b and "bounce_flush(" in b
          and b.index("peer_may_flush(") < b.index("bounce_flush("), b[:300])

    print("\n5. serve.py FLUSHES BEFORE IT KILLS")
    import serve  # noqa: E402

    hits = []
    order = []

    class Fake(http.server.BaseHTTPRequestHandler):
        delay = 0.0

        def do_POST(self):  # noqa: N802
            hits.append(self.path)
            order.append("flush " + self.path)
            if Fake.delay:
                time.sleep(Fake.delay)
            payload = json.dumps({"ok": True, "flushed": 13}).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except OSError:
                pass

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    srv.daemon_threads = True
    port = srv.server_address[1]
    assert port != 8800
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    # NEVER HER GATEWAY: the bare-stop fallback port is pointed at the fake before any call.
    check("serve.py names its default gateway port in one place",
          hasattr(serve, "GATEWAY_PORT_DEFAULT"))
    serve.GATEWAY_PORT_DEFAULT = port
    _orig_kill = serve.kill_by_cmdline
    serve.kill_by_cmdline = lambda pattern: order.append("kill " + pattern)
    try:
        serve.stop_gateway_only(port)
        check("stop_gateway_only POSTs /v1/shutdown/flush",
              hits == ["/v1/shutdown/flush"], hits)
        check("...BEFORE the kill",
              [o.split()[0] for o in order] == ["flush", "kill"], order)
        check("...and the kill is still by port",
              order and ("--gateway-port %d" % port) in order[-1], order)

        hits.clear(); order.clear()
        serve.stop_gateway_only(None)
        check("a bare stop (no profile) flushes the default port too",
              hits == ["/v1/shutdown/flush"] and [o.split()[0] for o in order]
              == ["flush", "kill"], order)

        # a gateway that is not there: the kill must still happen, and promptly
        s = socket.socket(); s.bind(("127.0.0.1", 0)); dead = s.getsockname()[1]; s.close()
        order.clear()
        t0 = time.time()
        serve.stop_gateway_only(dead)
        check("no gateway listening: the kill still runs",
              [o.split()[0] for o in order] == ["kill"], order)
        check("...without waiting", time.time() - t0 < 3.0, time.time() - t0)

        # a gateway that hangs: the flush is bounded, the kill still runs
        hits.clear(); order.clear()
        Fake.delay = 3.0
        _orig_to = getattr(serve, "FLUSH_TIMEOUT_S", None)
        check("the flush timeout is a named constant", _orig_to is not None)
        serve.FLUSH_TIMEOUT_S = 0.5
        t0 = time.time()
        serve.stop_gateway_only(port)
        el = time.time() - t0
        serve.FLUSH_TIMEOUT_S = _orig_to
        Fake.delay = 0.0
        check("a hung gateway does not block the kill",
              order and order[-1].startswith("kill") and el < 2.5, (order, el))
        check("the default timeout is short (<= 10 s)",
              _orig_to is not None and 0 < _orig_to <= 10, _orig_to)

        # stop(c): the full-boot restart and --stop <profile>. engine.launch is faked so
        # nothing real is killed.
        import types
        calls = []
        fake_launch = types.ModuleType("engine.launch")
        fake_launch.stop_daemon = lambda c=None: calls.append("daemon")
        _saved = sys.modules.get("engine.launch")
        sys.modules["engine.launch"] = fake_launch
        hits.clear(); order.clear()
        try:
            serve.stop({"serve": {"gateway_port": port}})
        finally:
            if _saved is None:
                sys.modules.pop("engine.launch", None)
            else:
                sys.modules["engine.launch"] = _saved
        check("stop(c) flushes the gateway before killing it",
              hits == ["/v1/shutdown/flush"] and [o.split()[0] for o in order]
              == ["flush", "kill"], (hits, order))
    finally:
        serve.kill_by_cmdline = _orig_kill
        srv.shutdown()

    print("\n6. EVERY STOP PATH GOES THROUGH stop_gateway_only")

    def _calls(fn):
        tree = ast.parse(_src.body(fn).lstrip())
        out = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                f = n.func
                out.append(f.id if isinstance(f, ast.Name)
                           else f.attr if isinstance(f, ast.Attribute) else "")
        return out

    check("stop() calls stop_gateway_only", "stop_gateway_only" in _calls(serve.stop))
    mc = _calls(serve.main)
    check("main() calls stop_gateway_only (--gateway-only)", "stop_gateway_only" in mc)
    check("main() calls stop() (--stop and the full-boot restart)", "stop" in mc)
    stree = ast.parse(_src.text("serve.py"))
    killers = []
    for fnode in ast.walk(stree):
        if isinstance(fnode, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in ast.walk(fnode):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                        and n.func.id == "kill_by_cmdline":
                    killers.append(fnode.name)
    check("kill_by_cmdline has exactly one caller, stop_gateway_only",
          sorted(set(killers)) == ["stop_gateway_only"], killers)
finally:
    SD.undelivered_path = _orig_up
    SD._reset_for_test()

finish("G-BOUNCE-FLUSH")
