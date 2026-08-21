"""MCP client bridge — mount external MCP servers' tools into the harness.

Reads mcp_servers.json (harness root, or SP_MCP_CONFIG) and exposes every
listed server's tools as harness ToolSpecs, so the SERVED MODEL can call any
MCP tool through the normal ```tool_code loop (run_with_tools).

Config format (a subset of the common MCP client config):

    {
      "servers": {
        "kairos": {"command": "python", "args": ["-m", "harness.mcp_server"]},
        "someweb": {"url": "http://127.0.0.1:9000/mcp"}
      }
    }

Design notes:
  * POOLED sessions (pool.py): one kept-open session per server, on a dedicated
    loop thread. It mattered — connect-per-call measured 2.2 s EVERY call with
    24 ms variance, which is a process spawn, not a slow tool. SP_MCP_POOL=0
    falls back to connect-per-call, which is slow and known-good.
  * Name collisions are NAMESPACED, not dropped. A bridged tool whose name a
    native tool already owns becomes `<server>_<name>` — chrome-devtools-mcp ships
    `take_screenshot`, which is also the name of her webcam/screen tool, and the
    old rule silently DISCARDED the browser one. That is capability loss dressed
    up as conflict resolution. Native always keeps the bare name; the bridged one
    is still reachable.
  * `allow` / `deny` per server: a 29-tool server should not flood her tool index
    just because it is connected.
  * Tool listings are cached per process (SP_MCP_REFRESH=1 to bust).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from typing import Any, Dict, List, Optional

_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEF_CONFIG = os.path.join(_HARNESS_ROOT, "mcp_servers.json")

_cache_lock = threading.Lock()
_tool_cache: Optional[List[Dict[str, Any]]] = None  # [{server, name, description, schema}]


def _config_path() -> str:
    return os.environ.get("SP_MCP_CONFIG", _DEF_CONFIG)


def load_config() -> Dict[str, Any]:
    p = _config_path()
    if not os.path.isfile(p):
        return {"servers": {}}
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception as exc:
        print(f"[mcp_bridge] bad config {p}: {exc}", file=sys.stderr)
        return {"servers": {}}


def _client_for(spec: Dict[str, Any]):
    """Build a fastmcp Client for one server spec ({command,args,env} or {url})."""
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    if "url" in spec:
        return Client(spec["url"])
    env = dict(os.environ)
    env.update(spec.get("env", {}))
    transport = StdioTransport(
        command=spec["command"], args=spec.get("args", []),
        env=env, cwd=spec.get("cwd", _HARNESS_ROOT),
    )
    return Client(transport)


def _run(coro, timeout: float = 60.0):
    """Run an async op from sync code, safe whether or not a loop is running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(asyncio.wait_for(coro, timeout))
    # Called from inside an event loop (rare): use a scratch thread.
    box: Dict[str, Any] = {}

    def _worker() -> None:
        try:
            box["v"] = asyncio.run(asyncio.wait_for(coro, timeout))
        except Exception as exc:  # pragma: no cover
            box["e"] = exc

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout + 5)
    if "e" in box:
        raise box["e"]
    return box.get("v")


async def _alist_tools(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    async with _client_for(spec) as c:
        tools = await c.list_tools()
    return [
        {"name": t.name, "description": t.description or "",
         "schema": getattr(t, "inputSchema", None) or {}}
        for t in tools
    ]


def _extract_text(res: Any) -> str:
    """An MCP result -> the text a tool_output should carry.

    Shared with pool.py ON PURPOSE: the pooled and unpooled paths must render a
    result identically, or the pool becomes a second implementation of what a tool
    returns — this repo's signature bug wearing a performance hat."""
    parts = []
    for item in getattr(res, "content", []) or []:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(text)
    return "\n".join(parts) if parts else str(getattr(res, "data", res))


async def _acall_tool(spec: Dict[str, Any], name: str, kwargs: Dict[str, Any]) -> str:
    async with _client_for(spec) as c:
        res = await c.call_tool(name, kwargs)
    return _extract_text(res)


def list_bridged_tools(refresh: bool = False) -> List[Dict[str, Any]]:
    """All tools from all configured servers (cached)."""
    global _tool_cache
    with _cache_lock:
        if _tool_cache is not None and not refresh \
                and os.environ.get("SP_MCP_REFRESH") != "1":
            return _tool_cache
        out: List[Dict[str, Any]] = []
        for sname, spec in load_config().get("servers", {}).items():
            try:
                # POOLED when armed: the listing is the FIRST call, so it is also
                # what opens the session every later tool call reuses. Doing it
                # unpooled would spawn a server, list, close it, and then spawn
                # another for the first real call.
                from harness.mcp_server import pool as _pool
                if _pool.enabled():
                    raw = _pool.list_tools(sname, spec)
                    listed = [{"name": t.name, "description": t.description or "",
                               "schema": getattr(t, "inputSchema", None) or {}}
                              for t in raw]
                else:
                    listed = _run(_alist_tools(spec), timeout=30)
                for t in listed:
                    t["server"] = sname
                    out.append(t)
            except Exception as exc:
                print(f"[mcp_bridge] list_tools failed for '{sname}': {exc}", file=sys.stderr)
        _tool_cache = out
        return out


def mcp_toolspecs(exclude_names: Optional[set] = None) -> List["ToolSpec"]:  # noqa: F821
    """Bridged tools as harness ToolSpecs for run_with_tools.

    exclude_names: native tool names that win on collision (bridged skipped).
    """
    from harness.toolcore.tools import ToolSpec

    servers = load_config().get("servers", {})
    exclude = exclude_names or set()
    specs: List[ToolSpec] = []
    taken = set(exclude)
    for t in list_bridged_tools():
        spec_dict = servers.get(t["server"], {})
        # PER-SERVER FILTERING. `allow` is a whitelist, `deny` a blacklist. A server
        # with 29 tools (chrome-devtools ships lighthouse, tracing and heap
        # snapshots) would otherwise dump all of them into her load-on-demand index,
        # where every entry costs prompt budget whether she ever wants it or not.
        allow = spec_dict.get("allow")
        deny = set(spec_dict.get("deny", []))
        if allow is not None and t["name"] not in allow:
            continue
        if t["name"] in deny:
            continue
        # NAMESPACE ON COLLISION rather than drop. See the module docstring.
        exposed = t["name"]
        if exposed in taken:
            exposed = f"{t['server']}_{t['name']}"
            if exposed in taken:
                continue                      # genuinely nothing left to call it
        taken.add(exposed)
        schema = t.get("schema") or {}
        props = schema.get("properties", {}) or {}
        required = schema.get("required", []) or []

        def _mk(sd: Dict[str, Any], tool_name: str, server_name: str):
            def _call(**kwargs: Any) -> str:
                try:
                    from harness.mcp_server import pool as _pool
                    if _pool.enabled():
                        return _pool.call_tool(server_name, sd, tool_name, kwargs)
                    return _run(_acall_tool(sd, tool_name, kwargs))
                except Exception as exc:
                    return f"[mcp tool error: {exc}]"
            return _call

        specs.append(ToolSpec(
            name=exposed,
            description=(t["description"] or "").strip().split("\n")[0] or f"MCP tool from {t['server']}",
            parameters={"type": "object", "properties": props, "required": required},
            fn=_mk(spec_dict, t["name"], t["server"]),
        ))
    return specs
