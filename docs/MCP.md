---
type: reference
title: "MCP — the FastMCP server and the bridge"
status: LIVE (sandboxed-first since 2026-08-19; SP_MCP_UNSANDBOXED is a held knob)
---

# Kairos MCP layer (FastMCP)

Added by the 2026-07-10 audit. Two directions, one config.

## 1. The server — Kairos's hands over MCP

```
python -m harness.mcp_server              # stdio transport
python -m harness.mcp_server --http 8765  # streamable-HTTP on 127.0.0.1:8765
```

Exposes the harness's real skills as MCP tools: `list_dir`, `read_file`,
`write_file`, `run_shell`, `run_powershell`, `run_python`, `web_search`,
`web_fetch`, `get_time`, plus the memory tools (`remember`/`forget`/
`list_memories`/…) when `SP_RECALL_REGISTRY` is set, plus everything in
`harness/mcp_server/custom_tools.py`.

Any MCP client (Claude Desktop, Cowork, another agent) can connect and drive
the system. Example Claude Desktop entry:

```json
"kairos": {
  "command": "python",
  "args": ["-m", "harness.mcp_server"],
  "cwd": "<path-to>/kairos-harness"
}
```

### Customizing
Edit `harness/mcp_server/custom_tools.py` — every plain function there becomes
a tool (docstring = description, type hints = schema). No FastMCP knowledge
needed. Restart the server to pick up changes.

## 2. The bridge — the world's MCP tools for the served model

`mcp_servers.json` (harness root, override with `SP_MCP_CONFIG`) lists servers;
with `SP_MCP_TOOLS=1` the gateway mounts every listed server's tools into the
model's tool loop (they land in the load-on-demand index tier, so the ≤6-tool
rule holds). Native harness tool names win on collisions.

```json
{
  "servers": {
    "kairos":  {"command": "python", "args": ["-m", "harness.mcp_server"]},
    "somehttp": {"url": "http://127.0.0.1:9000/mcp"}
  }
}
```

`run_gateway_system.bat` (engine root) sets `SP_MCP_TOOLS=1` along with the
rest of the agentic stack (`SP_SPINE_TOOLSET`, `SP_SPINE_RECALL`,
`SP_PERSONALITY`).

## Gate

`python harness_tests/h_mcp_server.py` — G-MCP-SERVER: (A) in-process server lists +
calls tools, (B) stdio bridge round-trips, (C) `SP_MCP_TOOLS=1` wiring joins
`all_tools()` without duplicates.

---

## Which direction is which (2026-07-31)

This confused everyone including the author, so it is stated once, plainly.

**OUTBOUND — `harness/mcp_server/` is a SERVER.** It exposes her memory, her board
and her skills to *external* MCP clients. That is its whole point and it is
genuinely useful: point Claude Code, LM Studio, or any MCP client at it and they
can read what she knows.

```
python -m harness.mcp_server              # stdio, for an MCP client
python -m harness.mcp_server --http 8765  # streamable-HTTP
```

**INBOUND — `mcp_servers.json` + `harness/mcp_server/bridge.py` is a CLIENT.** It
mounts *other people's* MCP servers as tools she can call.

**AND UNTIL 2026-07-31 THE INBOUND CONFIG POINTED AT THE OUTBOUND SERVER.** A loop.
Every tool it offered was already native, so 9 of 10 were shadowed and skipped, and
the entire net gain of the MCP layer was `disk_free` — an *example* function in a
file whose docstring says "Example:". At 2.2 s a call.

The production config now holds only external servers. `fixtures/mcp/selftest.json`
keeps the self-connection for the gates that need one.

### Per-server keys

| key | meaning |
|---|---|
| `command`/`args`/`env`/`cwd` | stdio server |
| `url` | HTTP/SSE server |
| `allow` | whitelist of tool names to expose (a 29-tool server should not flood her index) |
| `deny` | blacklist |

A bridged tool whose name a native tool already owns is **namespaced** to
`<server>_<name>`, not dropped — `take_screenshot` from the browser server becomes
`browser_take_screenshot`, and her own webcam tool keeps the bare name. Silently
discarding it, which is what the bridge used to do, is capability loss dressed up as
conflict resolution.
