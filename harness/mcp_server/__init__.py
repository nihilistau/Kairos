"""Kairos MCP layer (FastMCP).

Two directions:
  * server.py  — exposes the harness's system capabilities (web, filesystem,
    PowerShell, Python, time, memory) as a standard MCP server so ANY MCP
    client (Claude, Cowork, other agents) can drive Kairos's hands.
  * bridge.py  — an MCP CLIENT bridge that mounts tools from any configured
    MCP server (mcp_servers.json) into the harness's ephemeral tool-calling
    loop, so the SERVED MODEL can call them like native tools.

Customize by editing custom_tools.py (drop plain functions there) and
mcp_servers.json (add external servers). See MCP-README.md.
"""
