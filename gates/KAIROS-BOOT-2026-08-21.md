# KAIROS-BOOT receipt — 2026-08-21

The acceptance run for the engine-agnostic stack (plan Phase 4): the exported tree boots
against an OpenAI-compatible endpoint that is not the custom engine, and holds a
conversation with memory and the room.

| | |
|---|---|
| Tree | `<path-to>\Kairos` (export of `Kairos@d1af36b` + the boot-gate key fix) |
| Profile | `profiles/companion.toml` — `[engine] kind="openai"`, `base_url=http://127.0.0.1:1234`, `api_key_file=var/secrets/engine.token`, gateway `:8810` |
| Endpoint | LM Studio local server (auth ON — bearer from the key FILE), model `lfm2.5-1.2b-instruct@q8_0`, CPU only (`lms load ... --gpu off`) so it shared the box with the sp stack on `:8800`/`:3000` |
| Command | `python serve.py companion` run FROM the Kairos dir (its own `var/`, its own persona from `persona-template/`) |
| Gate | `SP_BOOT_GATEWAY=http://127.0.0.1:8810 python harness_tests/g_kairos_boot.py` |
| Verdict | **G-KAIROS-BOOT 12/12** |

```
1. THE STACK IS UP ON AN EXTERNAL ENGINE, AND SAYS SO
  ok   /health is ok and warm (nothing to warm on a foreign endpoint)
  ok   /health names the engine kind and base_url
  ok   /v1/system says the engine is external and a full restart is off the table
  ok   the room serves
2. A TURN STREAMS, AND IS REMEMBERED
  ok   at least one delta streamed and the stream ended
  ok   ...and the engine answered (no error event in the stream — a 401 is not a turn)
  ok   the fact landed in her memory (listed live by /v1/memory)
3. THE REST OF THE ROOM ANSWERS
  ok   the kairos outbox polls without error
  ok   /v1/speak/status answers with the live voice resolution
  ok   /v1/catalog answers
  ok   /v1/tuning answers with the eot_bias knob tagged sp-only
  ok   a full restart is refused politely (external engine)
```

`/health` as served: `{"ok": true, "agent": true, "warm": true, "engine": {"kind": "openai",
"base_url": "http://127.0.0.1:1234", "supports": ["abort", "metrics_tps", "oneshot"], "model": ""},
"daemon": false}`

## What the run found on the way (all fixed before the green, each with a gate)

- `serve.py build_env` read two keys the companion profile lacked (`kv.persist_b4`,
  `memory.l5_tau`) and raised at the door → G-BACKEND-SEAM §7 now calls `build_env(companion)`.
- The gateway bound `8800` regardless of `[serve].gateway_port` — `app.py` read no port, so the
  Kairos gateway sat BESIDE the live one on her port (Windows allows two listeners) → `SP_GATEWAY_PORT`
  is mapped by the door and bound by `app.py`; G-BACKEND-SEAM §7 asserts the mapping.
- The exporter cleared the target's `var/` and `persona/` on re-export (wiped a live token) → local
  dirs survive.
- The boot gate read `/v1/memory` under the wrong key, took a 401 stream as a turn, and treated a
  polite 400 refusal as an exception → all three corrected in the gate.
- The launcher's "engine: NOT answering yet" probe sent no bearer → it sends the key-file token.

## Known, not fixed here

- The user-turn capture stored "and reply in one short sentence: My favourite tea is …" — the
  "remember this" splitter leaves the conjunction behind. Cosmetic; the fact is recalled. Ledgered.
- A 1.2B model makes no tool calls (`calls=0`); memory landed through the per-turn capture, not
  through `remember`. The gate asserts the fact is listed, not how it got there.
- `harness.telemetry` is not in the export; the spine logs one WARNING per turn that its sink is
  unavailable.
