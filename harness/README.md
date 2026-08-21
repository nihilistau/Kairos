# harness/ — the Python brain

Everything that is not arithmetic. The engine (`engine/`) decodes tokens; this decides what she
remembers, when she speaks, who she is, and what the room sees. Zero third-party dependencies on
the core path (`pyproject.toml`); numpy/PIL only for vision, voice and games.

| package | owns | engine-bound? |
|---|---|---|
| `server/app.py` | the gateway: SSE chat, every `/v1/*` route the room uses, the day boundary, restart/shutdown | the chat path and warm gate are; the panel routes are not |
| `inference/` | the one client seam to the daemon (`client.py`), `InferenceConfig`, the control-surface stripper | yes (the seam) |
| `skills/` | memory (`memory.py`, `lifecycle.py`, `verdict.py` — the one read seam), notes, search/research/xai, looking, narrative, world | pure (memory's `/v1/capture` mint degrades) |
| `control/` | spine (decide→execute→verify), agency, ledger, wardrobe/catalog/avatar, shutdown, backup, watchdog | pure (watchdog restarts the daemon) |
| `kairos/` | unprompted speech: impulse policy, reasons, the scheduler (injected `generate`) | pure; the `eot_margin` arrives from the engine |
| `personality/` | persona fragments, marks, curator, self-model | pure |
| `tuning/registry.py` | every live knob, declared once; the settings window renders it | pure |
| `voice/` | TTS (xAI Ara + expressive tags; local voxtral fallback), the ear | TTS pure; ear is frame-injected |
| `senses/` | the ambient eye (quiet-guarded), sight, capture | sight is frame-injected |
| `sidecar/` | the LFM CPU helpers over an OpenAI-compatible door | pure |
| `mcp_server/`, `mcp/`, `toolcore/`, `tools/` | her hands: MCP server, tool manifest and calling loop | pure |
| `roleplay/`, `games/`, `maintenance/`, `quality/`, `observability/`, `telemetry/` | the stage, the board, ops, repeat guard, progress, the daemon event bus | telemetry is engine-bound |

Read `docs/MEMORY-AND-RECALL.md` before touching `skills/`; `AGENTS.md` §0 before touching anything twice.
