# harness/ — the Python brain

Everything that is not arithmetic. The engine (`engine/`) decodes tokens; this decides what she
remembers, when she speaks, who she is, and what the room sees. Zero third-party dependencies on
the core path (`pyproject.toml`); numpy/PIL only for vision, voice and games.

| package | owns | engine-bound? |
|---|---|---|
| `agent.py` (module, not a package) | her system prefix: `system_bundle()` is the ONE builder — persona, the tool index it assembles for `run_with_tools`, and `voice_coda()` — with `invalidate_system_prefix()` the one door. It replaced the `_SYS_CACHE` that nothing invalidated (2026-08-25, G-PREFIX-REFRESH). That string is KV token 0, so freshness here is SCHEDULED and never continuous: rebuild it per turn and the whole conversation re-prefills | yes (token 0 is the persist cache's floor) |
| `server/app.py` | the HTTP surface: SSE chat, every `/v1/*` route the room uses (incl. `GET /v1/day`, the room's day read-back, and `POST /v1/maintenance/refresh`), the day boundary (`_append_day_turn`), restart/shutdown, the warm gate | the chat path and warm gate are; the panel routes are not |
| `server/turn.py` | **THE TURN EPILOGUE** (2026-09-01): `_settle_turn` is the one list of debts every turn owes — his latch, capture, the day row, her marks, the receipts — paid on every exit and latched so two owners pay once; with `_arm_turn` taking what he typed before the tool loop can touch it, `_on_her_own_words` the unprompted lane's epilogue, and `_arm_self_turn`/`_disarm_self_turn` the author-token contract around her own generations (G-TURN-EPILOGUE §10 asserts it is ONE object) | yes |
| `server/panels.py` | the room's read-only windows, ~35 producers shaped `() -> dict` and almost all NEVER RAISES, because a panel that throws takes the window with it. G-PANELS-SERVE calls every one of them and then asks the live gateway for every route `ui/src/api.js` names | no |
| `server/state.py` | what the gateway knows right now: the warm gate, the canonical per-session transcripts, the generate-now job, the last-turn clock. Reached as `state.X` and never `from state import X` — `LAST_TURN_AT` is rebindable and an import would snapshot it. **None of it is locked** (AGENTS.md §4 trap 8) | n/a |
| `inference/` | the one client seam to the daemon (`client.py`), `InferenceConfig`, `context.prefix_tokens()` (the system prefix measured, not asserted), and BOTH control-surface strippers: the per-delta display one and `strip_for_record()` (`stream_processor.py`), the record lane's whole-turn cleaner held equal to its JS twin by G-STRIP-EQUIVALENCE | yes (the seam) |
| `skills/` | memory (`memory/` — A PACKAGE since 2026-09-01, `__init__.py` is the one door and the siblings are the implementation; `lifecycle.py`, `verdict.py` — the one read seam, `memclass.py` — the class registry that owns `half_life_days` + `salience_weight` per class since 2026-08-25), notes, search/research/xai, looking, narrative, world | pure (memory's `/v1/capture` mint degrades) |
| `control/` | spine (decide→execute→verify), agency, ledger, wardrobe/catalog/avatar, shutdown, backup, watchdog | pure (watchdog restarts the daemon) |
| `kairos/` | unprompted speech: impulse policy, reasons, the scheduler (injected `generate`) | pure; the `eot_margin` arrives from the engine |
| `personality/` | persona fragments, marks, curator, self-model | pure |
| `tuning/registry.py` | every live knob, declared once; the settings window renders it | pure |
| `voice/` | TTS (xAI Ara + expressive tags; local voxtral fallback), the ear | TTS pure; ear is frame-injected |
| `senses/` | the ambient eye (quiet-guarded), sight, capture | sight is frame-injected |
| `sidecar/` | the LFM CPU helpers over an OpenAI-compatible door | pure |
| `mcp_server/`, `mcp/`, `toolcore/`, `tools/` | her hands: MCP server, tool manifest and calling loop | pure |
| `model/` | the model OF HIM — the thing facts are evidence FOR: `person.py` (dispositions, character; a subject of `docs/MEMORY-AND-RECALL.md`, read it first) and `presence.py`, the attention ledger — absence is only information if you can prove you were looking | pure |
| `nexus/` | knowledge store behind one interface — embedded SQLite + vector search by default, a remote KMS when `NEXUS_URL` is set; `skills/builtin/memory.py` and `semindex` are the callers | pure |
| `cli/` | `python -m harness.cli` — ask / coder / serve / daemon / nexus / oracle / skills. A second door onto the same harness; nothing the room does goes through it | the `ask`/`serve`/`daemon` verbs are |
| `roleplay/`, `games/`, `maintenance/`, `quality/`, `observability/`, `telemetry/` | the stage, the board, ops, repeat guard, progress, the daemon event bus | telemetry is engine-bound |

That is every package under `harness/` — the table is the whole list, not a selection; only
`config.py` and the `__init__.py`s are unlisted. A new package gets a row when it lands.

Read `docs/MEMORY-AND-RECALL.md` before touching `skills/`; `AGENTS.md` §0 before touching anything twice.
