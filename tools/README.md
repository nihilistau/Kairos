# tools/ — what is here, and whether it is live

| script | purpose | used by |
|---|---|---|
| `avatar_gen.py` | her stills + motion through the xAI API (reference, wants, gestures, loops) | wardrobe generate-now (`harness/server/app.py`), day boundary, `docs/AVATAR-PIPELINE.md` |
| `okf_mem.py`, `okf_validate.py` | the MEM-OKF knowledge store tooling (write/validate) | AGENTS.md §2, the OKF gates |
| `roll_report.py` | the evening's roll in one screen | serve.py usage notes |
| `sem_dash.py` | the SEM stack dashboard | `docs/SEMANTICS.md` |
| `extract_audio_projection.py` | pulls `embed_audio.projection` from the checkpoint for the native ear | ADR-KAI4 |
| `voice_corpus.py`, `voice_frames.py`, `voice_export_wsub.py` | the ear corpus / frame tooling (ADR-KAI4) | `harness/voice/`, the voice gates |
| `voice_render_sapi.ps1` | SAPI renderer for the ear corpus | voice_corpus |
| `drafter/` | EAGLE drafter data + training (engine lane, dark — see OFF-BY-DEFAULT) | engine |
| `kairos/calibrate.py` | recalibrates the kairos continue margin per model | `harness/tuning/registry.py` receipt |
| `memory/` | registry maintenance scripts (salience backfill, identity repair, triage) | MEMORY-AND-RECALL.md |
| `model/` | checkpoint repack (`repack_q4b.py`) + xxh64 | engine lane |
| `reference/` | HF reference parity scripts (embed/tokenizer/head precision) | engine gates |

Removed 2026-08-21 (zero references; history has them at tag `pre-cleanup-2026-08-21`):
`telepathy_audio/` (1,031 files, the KAI-5 PoC corpus), `kairos_report.py`, `voice_export_ir.py`,
`voice_p1_corpus.py`, `voice_pot_gna.py`, `voice_render_voxtral.{py,ps1}`, `voice_wake.py`,
`voice_train.py` + `voice_bake.bat` (the ear bake; its page `console/voice_train.html` went too).
