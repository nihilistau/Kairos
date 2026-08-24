# tools/ — what is here, and whether it is live

| script | purpose | used by |
|---|---|---|
| `sweep.py` | **LIVE, the offline suite's runner** (2026-08-24): reads the OFFLINE rows out of GATE-INDEX and runs them in parallel, on EXIT CODES and never on grepped stdout; `g_backup` is forced serial. `--audit` diffs her real stores around each gate | `gates/GATE-INDEX.md`, every session that says "the gates are green" |
| `gate_sandbox_audit.py` | **LIVE** (2026-08-24): does any gate write into HER stores? Runs each one and diffs her real memory/journal/wardrobe by filename and bytes. Nine gates were named on the day it was written; no gate is trusted to sandbox itself | `sweep.py --audit`, G-JOURNAL-LOOP's own history |
| `w4_note_ab.py` | **LIVE receipt, one question** (2026-08-25): six turns per arm of the `wardrobe.turn_note` knob through the REAL native gateway, deliberation openers counted with stream_processor's own `_ANALYSIS` recogniser; writes `var/w4-note-ab.json` and restores the knob OFF whatever happens. One of the two callers (the other is `g_reseam_live`) that must declare `synthetic` so its turns are quarantined out of her day | the W4b ledger entry, `harness/tuning/registry.py` |
| `avatar_gen.py` | her stills + motion through the xAI API (reference, wants, gestures, loops) | wardrobe generate-now (`harness/server/app.py`), day boundary, `docs/AVATAR-PIPELINE.md` |
| `avatar/` | ONE-OFF migrations, already run (2026-08-23): `rename_outfits.py` (`t0..t3` → mesh-top/sheer-tee/lace-set/bodysuit — the opaque keys that hid "black lace underwear" filed under the mesh top for three days) and `rename_tier_field.py` (`tier` → `outfit`/`made_in`: two things wearing one word) | history; kept as the record of what moved |
| `kairos_export.py` | **LIVE, and the only way the public repo is built** (2026-08-21): a filtered, scrubbed copy with fresh history — never a clone. `--check` is the dry run. This file does not itself ship | AGENTS.md §2, `../kairos-drift/`, the scrub gate |
| `kairos_default_set.py` | builds the DEFAULT AVATAR SET Kairos ships — one outfit's grid, seven faces, six gestures, provenance kept and the prompt prose stripped. Run when the shipped set changes, not per export | `kairos_export.py`, `docs/AVATAR-PIPELINE.md` §5 |
| `disk_bench.py` | **ONE-OFF measurement** (2026-08-23): are the two Optane drives fast enough to be a TIER? Random 2.84 MB reads (the measured expert-slot shape, not a sequential marketing shape), unbuffered through `FILE_FLAG_NO_BUFFERING` or it reports the page cache | the tiering question; no code depends on it |
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
