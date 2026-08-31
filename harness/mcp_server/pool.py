"""pool.py — persistent MCP sessions, so a tool call is not a process spawn.

MEASURED, before this existed (2026-07-31, the `kairos` stdio server):

    list_bridged_tools()   3.619 s   cold
    disk_free()            2.200 s
    disk_free()            2.223 s
    disk_free()            2.224 s

Two and a quarter seconds, every call, with a variance of 24 ms — which is the
shape of a fixed cost, not a slow tool. The bridge opened the server, called it,
and closed it again each time: `async with _client_for(spec)`, one Python
interpreter spawned per tool call. The module docstring called that "~1s/call" and
said a pool was "the follow-on if that ever matters".

It matters. She reaches for tools mid-conversation, and 2.2 s of dead air per call
is the difference between a tool feeling like part of her and feeling like a form
submission. This is the thing that would have made her tool use FEEL bad long
before anything about it was wrong.

HOW IT WORKS. One daemon thread owns one asyncio loop; that loop owns every open
session. Sync callers hand coroutines to it via `run_coroutine_threadsafe`. That
arrangement is not incidental — an MCP session is an async context manager bound to
the loop that entered it, so it CANNOT be entered on one loop and used from
another. `asyncio.run()` per call (what the old path did) creates and destroys a
loop each time, which is precisely why nothing could be kept open.

WHAT IT REFUSES TO DO:
  * Never leaves a wedged session in the pool. A call that raises drops its session
    and retries ONCE on a fresh one — a stdio server that died between calls is
    ordinary, not exceptional, and a pool that hands out corpses is worse than no
    pool.
  * Never blocks forever. Every wait is bounded; on timeout the session is dropped
    rather than parked in an unknown state.
  * Never becomes mandatory. SP_MCP_POOL=0 falls straight back to connect-per-call,
    which is slow and known-good. A performance change that can take the tool layer
    down with it is not worth having.
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
from typing import Any, Dict, Optional

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

_ENABLED = os.environ.get("SP_MCP_POOL", "1") != "0"
_CALL_TIMEOUT = float(os.environ.get("SP_MCP_CALL_TIMEOUT", "60"))

_loop: Optional[asyncio.AbstractEventLoop] = None
_thread: Optional[threading.Thread] = None
_start_lock = threading.Lock()

# server name -> {"client": entered client, "spec": spec}
_sessions: Dict[str, Any] = {}
_sess_lock = threading.Lock()

_stats = {"opened": 0, "reused": 0, "reconnects": 0, "closed": 0}


def enabled() -> bool:
    return _ENABLED


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """The one loop that owns every session. Started once, lives for the process."""
    global _loop, _thread
    with _start_lock:
        if _loop is not None and _thread is not None and _thread.is_alive():
            return _loop
        ready = threading.Event()

        def _run() -> None:
            global _loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _loop = loop
            ready.set()
            loop.run_forever()

        _thread = threading.Thread(target=_run, name="mcp-pool", daemon=True)
        _thread.start()
        ready.wait(10)
        if _loop is None:
            raise RuntimeError("mcp pool loop failed to start")
        return _loop


def _submit(coro, timeout: float):
    """Run a coroutine on the pool loop from sync code."""
    loop = _ensure_loop()
    fut = asyncio.run_coroutine_threadsafe(coro, loop)
    return fut.result(timeout)


async def _open(spec: Dict[str, Any]):
    from harness.mcp_server.bridge import _client_for
    client = _client_for(spec)
    await client.__aenter__()
    return client


async def _shut(client) -> None:
    try:
        await client.__aexit__(None, None, None)
    except Exception as _swx:
        _swallowed(_swlog, "_shut", _swx, lane="mcp_server")


def _get_session(server: str, spec: Dict[str, Any]):
    """An open client for `server`, opening one if needed. Caller holds no lock."""
    with _sess_lock:
        s = _sessions.get(server)
        if s is not None and s["spec"] == spec:
            _stats["reused"] += 1
            return s["client"]
    client = _submit(_open(spec), timeout=30)
    with _sess_lock:
        old = _sessions.get(server)
        _sessions[server] = {"client": client, "spec": spec}
    if old is not None:                       # raced; close the loser
        try:
            _submit(_shut(old["client"]), timeout=10)
        except Exception as _swx:
            _swallowed(_swlog, "_get_session", _swx, lane="mcp_server")
    _stats["opened"] += 1
    return client


def drop(server: str) -> None:
    """Forget a session and close it. Safe to call on one that is already gone."""
    with _sess_lock:
        s = _sessions.pop(server, None)
    if s is None:
        return
    _stats["closed"] += 1
    try:
        _submit(_shut(s["client"]), timeout=10)
    except Exception as _swx:
        _swallowed(_swlog, "drop", _swx, lane="mcp_server")


def call_tool(server: str, spec: Dict[str, Any], name: str,
              kwargs: Dict[str, Any]) -> str:
    """One tool call over a kept-open session. Retries ONCE on a fresh session.

    The retry is not optimism — a stdio server that exited between calls is the
    ordinary case, and the failure is indistinguishable from a real tool error
    until you try again on a new connection."""
    from harness.mcp_server.bridge import _extract_text

    async def _do(client):
        return await client.call_tool(name, kwargs)

    for attempt in (1, 2):
        client = _get_session(server, spec)
        try:
            res = _submit(_do(client), timeout=_CALL_TIMEOUT)
            return _extract_text(res)
        except Exception as exc:
            drop(server)                      # never leave a wedged session behind
            if attempt == 2:
                raise
            _stats["reconnects"] += 1
            print(f"[mcp_pool] '{server}' session died ({exc}); reconnecting",
                  file=sys.stderr)
    return ""                                  # unreachable


def list_tools(server: str, spec: Dict[str, Any]) -> list:
    """Tool listing over the kept-open session, with the same retry."""
    async def _do(client):
        return await client.list_tools()

    for attempt in (1, 2):
        client = _get_session(server, spec)
        try:
            return _submit(_do(client), timeout=30)
        except Exception:
            drop(server)
            if attempt == 2:
                raise
            _stats["reconnects"] += 1
    return []


def status() -> dict:
    with _sess_lock:
        open_servers = sorted(_sessions)
    return {"enabled": _ENABLED, "open": open_servers,
            "loop_alive": bool(_thread and _thread.is_alive()), **_stats}


def shutdown(stop_loop: bool = False) -> None:
    """Close every session. For tests and a clean stack stop.

    `stop_loop` also stops the loop thread. Off by default because the pool is
    process-lived and the next call would just start another one; on at true
    process exit it silences fastmcp's "Task was destroyed but it is pending!",
    which is the session runner still parked on a loop nobody is going to run
    again. Cosmetic, but a scary-looking warning on every clean exit trains people
    to ignore warnings."""
    global _loop, _thread
    for name in list(_sessions):
        drop(name)
    if not stop_loop:
        return
    loop, _loop = _loop, None
    thread, _thread = _thread, None
    if loop is not None and loop.is_running():
        for task in asyncio.all_tasks(loop):
            loop.call_soon_threadsafe(task.cancel)
        loop.call_soon_threadsafe(loop.stop)
    if thread is not None:
        thread.join(timeout=5)
