"""TUNABLES — one declarative registry for every knob, so the UI never needs new code.

The operator's ask: "expose these things to the UI so that I can easily tune them later
if i need to. eg max_chain and eot_margin etc and anything else like that that has been
added or we will be adding."

The last clause is the design constraint. A hand-built settings page rots the moment a
knob is added — and this system's whole failure mode, four times over today, is a
capability that exists but is not REACHABLE. So: knobs are DECLARED here, once, and the
operator UI renders whatever it finds. Add a Knob to this list and it appears in the
panel, with its bounds, its help text, and its provenance. No UI edit. No endpoint edit.

PROVENANCE MATTERS. Every knob says where its default came from — measured, or chosen.
A number that was calibrated against the live model (kairos.continue_margin) is a very
different animal from one somebody felt was about right, and the operator deserves to see
which is which before he drags a slider.

Values live in var/tuning.json (operator overrides only; an unset knob keeps its default),
and are read live — no restart.
"""
from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# ── SP_TUNING_FILE (2026-08-24) ───────────────────────────────────────────────────────
# This was a bare constant with no override, so it was the ONE store a gate could not be
# pointed away from — and several gates call `set_many()`. Two consequences, both live:
#
#   * `g_presence_modes` raced HER RUNNING STACK over this file mid-sweep and died with
#     WinError 5 on the os.replace. A red that depends on whether she is up is a red
#     nobody can act on.
#   * Worse and quieter: a gate that sets a knob and does not put it back has changed
#     what she DOES. Her presence mode, her kairos chances and her voice all live here.
#
# `_gate.sandbox()` now sets this, and G-GATE-SANDBOX greps for store roots the sandbox
# does not cover — which is why the variable has to exist to be found.
STORE = os.environ.get("SP_TUNING_FILE") or os.path.join(ROOT, "var", "tuning.json")

_LOCK = threading.RLock()
_CACHE: Optional[dict] = None


@dataclass
class Knob:
    key: str                     # "kairos.continue_margin"
    group: str                   # UI section
    label: str
    type: str                    # "float" | "int" | "bool" | "enum"
    default: Any
    help: str
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    choices: list = field(default_factory=list)
    # WHERE the default came from. "measured" = calibrated against the live model and
    # backed by a receipt; "chosen" = a judgement call. The UI shows this.
    provenance: str = "chosen"
    receipt: str = ""            # the gate/receipt that justifies a measured default
    danger: str = ""             # shown as a warning when the operator moves it
    # ── WHO ACTUALLY OWNS THIS VALUE (2026-07-30) ─────────────────────────────────────
    # This file's own docstring warns about "a capability that exists but is not
    # REACHABLE — that is how knobs go dead", and four knobs here had gone exactly that
    # way: `decode.eot_bias`, `decode.no_repeat_ngram`, `memory.admit_personal` and
    # `memory.recall_tau` are DECLARED here and read by NOTHING. Every consumer
    # (`tune.get(...)`) reads only the kairos / reflect / roleplay keys.
    #
    # So the panel was serving `End-of-turn bias 4.00` under a header promising "the next
    # turn reads the new value", while the value that actually reached the sampler came
    # from SP_EOT_BIAS — and 4.00 is a retired model's tune, which on this MoE makes the first
    # sampled token a stop and the turn come back EMPTY. A control that displays a stale
    # number and changes nothing is worse than no control.
    #
    #   "live"    read through tune.get() on the live path — the override works
    #   "profile" owned by profiles/<name>.toml via serve.py; `env` names the variable
    #             that carries it, the panel shows THAT value read-only, and set_many
    #             REFUSES the write with the remedy.
    scope: str = "live"
    env: str = ""                # for scope="profile": the SP_ var that actually carries it
    # WHICH ENGINE CAN HONOUR IT (2026-08-21, the engine-agnostic seam). "" = any backend;
    # "sp" = the Rust sp-daemon only — the room shows the chip and the knob is moot under a
    # foreign endpoint (eot_bias has no wire field there; see InferenceConfig.SP_ONLY).
    engine: str = ""
    # DYNAMIC CHOICES (2026-08-22, the aux model pickers): a callable returning the live
    # list (what the door serves right now); schema() resolves it and falls back to `choices`.
    choices_fn: Any = None

KNOBS: list[Knob] = [
    # ── KAIROS: when she speaks unprompted ────────────────────────────────────────
    # ARMED BY DEFAULT (2026-07-12, operator's call). It stayed off while the chain was
    # unproven and, later, while it was still invisible — she could speak but nothing
    # rendered it. Both are gated now (G-KAIROS-LIVE 8/8, G-KAIROS-TICK 8/8,
    # G-KAIROS-CONSOLE 7/7 end-to-end through the console's own session key), so the
    # default flips. Turning it off is one click on the operator panel.
    #
    # What "on" actually costs: nothing on an ordinary turn. The impulse is the raw
    # stop-vs-continue margin the forward already computed, the policy is SILENT by
    # default, and every bound (chain limit, cooldown, hourly cap, never-after-a-question)
    # is checked before she is even consulted. She speaks when she was CUT OFF mid-thought,
    # and — after 600s of quiet, on a 35% roll — when the room has gone still.
    Knob("kairos.enabled", "Kairos — speaking unprompted", "Enabled", "bool", True,
         "Master switch. Off = she only ever speaks when spoken to. On = she may finish a "
         "thought she was cut off in, and may check in after a long silence — bounded by "
         "the knobs below, and she stays silent almost always."),
    Knob("kairos.continue_margin", "Kairos — speaking unprompted",
         "Continue margin (logits)", "float", -18.50,
         "How reluctantly she must have stopped before she picks the thread back up. "
         "This is the RAW stop-vs-continue logit gap from the forward itself. "
         "THE SCALE IS PER-MODEL and it moves a long way: on a smaller retired model (eot_bias 4.0) "
         "finished turns sat around +2.8 and guillotined ones around -14.1; on "
         "your model (eot_bias 0.0) they sit at +13.10 and -28.43. Same signal, "
         "different scale — which is exactly why this number is re-measured per model "
         "and not carried over. Raise it toward 0 and she talks more (and starts talking "
         "over finished thoughts). Lower it and she is quieter.",
         min=-40.0, max=5.0, step=0.25,
         provenance="measured",
         receipt="tools/kairos/calibrate.py on your model (2026-07-30): FINISHED median "
                 "+13.10 (min +8.96), CUT OFF median -28.43 (max -18.54), gap 41.5 -> "
                 "0/6 finished turns interrupted, 6/6 genuine cut-offs resumed. The retired reference model's "
                 "-11.75 was calibrated at eot_bias 4.0 and does not transfer. Re-run after "
                 "ANY change to eot_bias, sampler, or model.",
         danger="Model-specific. Carrying a value across a model swap silently mis-classifies "
                "finished turns as cut-offs — re-run calibrate.py instead of guessing."),
    Knob("kairos.max_chain", "Kairos — speaking unprompted", "Max unprompted in a row", "int", 1,
         "How many times she may speak unprompted before she MUST wait for you. 1 = she "
         "can continue a cut-off thought once, then it is your turn. This is the main "
         "guard against her talking forever.",
         min=1, max=3, step=1,
         danger="Above 1 she can monologue. Raise this only if you want that."),
    Knob("kairos.cooldown_s", "Kairos — speaking unprompted", "Cooldown (s)", "float", 45.0,
         "After speaking unprompted, she stays quiet at least this long.",
         min=0.0, max=600.0, step=5.0),
    Knob("kairos.max_per_hour", "Kairos — speaking unprompted", "Hard cap per hour", "int", 6,
         "Absolute ceiling on unprompted messages per hour, whatever else says.",
         min=0, max=60, step=1),
    Knob("kairos.checkin_idle_s", "Kairos — speaking unprompted", "Check-in after idle (s)",
         "float", 600.0,
         "How long the room must be quiet before she may say something unprompted "
         "out of the blue (10 min by default, 2026-08-22 — the operator's ask; as opposed to "
         "finishing a cut-off thought).",
         min=30.0, max=3600.0, step=30.0),
    Knob("kairos.checkin_chance", "Kairos — speaking unprompted", "Check-in chance", "float", 0.35,
         "Even once it has gone quiet, she usually still says nothing. 0 = never check in.",
         min=0.0, max=1.0, step=0.05),
    # ── HIS QUIET IS THE CLOCK (2026-08-20, operator) ────────────────────────────
    # "the spoke up and continuation should be set to 5 minutes after I last say
    # anything." checkin_idle_s measures the SESSION's quiet, which includes hers —
    # she could speak, wait out her own cooldown, and speak again with him gone the
    # whole time. This one measures HIM, globally across sessions, and it gates
    # every discretionary speak-up (check_in / continue / expand / muse). Reminders
    # and her own time are untouched. 0 = off (the shipped default; arming is his
    # call — set 300 for his five minutes).
    Knob("kairos.quiet_after_him_s", "Kairos — speaking unprompted", "Quiet after HIM (s)",
         "float", 0.0,
         "No unprompted word (check-in, continuation, follow-on, musing) until at "
         "least this long since HE last said anything, in any session. 0 = off.",
         min=0.0, max=3600.0, step=30.0),
    # "she shouldn't act first at bounce/restart like before." seed() exists to let
    # her speak first after a restart; this makes that a CHOICE. Off = a fresh boot
    # waits for him.
    Knob("kairos.seed_on_boot", "Kairos — speaking unprompted", "Speak first after a restart",
         "bool", False,
         "After a stack restart, may she open the conversation from the day's "
         "transcript, or does she wait until he speaks first?"),
    # ── THE FOLLOW-ON, FOR DEPTH (2026-08-04) ────────────────────────────────────
    # CONTINUE resumes a sentence the forward says was CUT OFF. EXPAND is the other
    # thing people do: finish the message, then send the bit you thought of afterwards.
    # The band between a guillotined turn and a finished one was never read by anything,
    # and it is exactly where that lives. (This comment quoted -14.8 / +2.0 when it was
    # written a few hours earlier — a retired model's medians, on a knob for the model. The live
    # numbers are in the receipt below, and they are measured from her own log rather
    # than from a calibration that has since drifted.)
    Knob("kairos.expand_margin", "Kairos — speaking unprompted", "Follow-on band (below)",
         "float", -12.0,
         "She finished, but not decisively — margin under this and she may send ONE more "
         "short message: the thing she thought of after. Sits between the cut-off "
         "threshold and a confident ending. Lower = rarer, and the curve is STEEP: on "
         "1,892 measured turns the band -18.5..-12 holds 4.7% of them, -18.5..-4 holds "
         "15%, and -18.5..0 holds 29.5%.",
         min=-25.0, max=9.0, step=0.5,
         provenance="measured",
         receipt="THE RATE is measured; the SEMANTICS are not. 1,892 eot_margin values from "
                 "var/daemon.log on your model (2026-08-04): min -31.22, p25 -2.07, "
                 "median +2.85, p75 +6.66, max +14.85. -12.0 puts 4.7% of turns in the band; "
                 "at expand_chance 0.30 that is a follow-on on ~1.4% of turns, roughly one "
                 "in seventy. NOTE this distribution sits far BELOW the 2026-07-30 "
                 "calibration receipt for continue_margin (+13.10 finished / -28.43 cut off) "
                 "— the live signal has drifted and continue_margin is due a re-run of "
                 "tools/kairos/calibrate.py.",
         danger="The RATE is measured, the MEANING is not: nobody has labelled 'finished but "
                "had more', so this threshold is calibrated to how OFTEN she follows on, not "
                "to whether she should. The first value tried, 0.0, was reasoned from the "
                "receipt rather than the data and put 29.5% of turns in the band — a "
                "follow-on on ~9% of all turns, which is the 'will not shut up' failure this "
                "whole module exists to prevent. If she adds to thoughts that were plainly "
                "done, lower it further."),
    Knob("kairos.expand_chance", "Kairos — speaking unprompted", "Follow-on chance",
         "float", 0.30,
         "Even in the band she usually just stops. 0 = never follow on.",
         min=0.0, max=1.0, step=0.05),
    # ── WHETHER HE IS EVEN THERE (2026-08-04) ────────────────────────────────────
    # Every silence looked identical to her: the four minutes while he makes tea and the
    # eight hours while he sleeps. So she said the same thing into both, three times in
    # eleven minutes on the evening this was written.
    Knob("kairos.away_after", "Kairos — speaking unprompted", "Unanswered before she stops",
         "int", 2,
         "She speaks up, he does not answer. After this many she concludes he is away and "
         "stops asking — not sulking, just what a person does when a room does not answer. "
         "Any turn of his resets it.", min=1, max=10, step=1),
    Knob("kairos.backoff_mult", "Kairos — speaking unprompted", "Back-off per unanswered",
         "float", 1.0,
         "Each unanswered remark multiplies the quiet she needs before the next one: at "
         "1.0 the wait goes 4 min, 8, 12 rather than four minutes forever.",
         min=0.0, max=4.0, step=0.25),
    # ── AND WHAT SHE DOES INSTEAD ────────────────────────────────────────────────
    # Until now "he is not here" produced silence and nothing else, so her entire
    # unprompted repertoire was tapping the glass — and once that was rate-limited she
    # stopped existing between his visits.
    Knob("kairos.solo_enabled", "Kairos — her own time", "She does things of her own",
         "bool", True,
         "When she has concluded he is away, she takes turns for HERSELF — reads, looks "
         "something up, follows a thought — instead of only waiting. Shown as an action, "
         "not as a message to him."),
    Knob("kairos.solo_every_s", "Kairos — her own time", "At most one of her own every",
         "float", 1800.0,
         "Seconds between her own turns (30 min by default, 2026-08-22 — the operator's ask). She is "
         "living, not grinding the GPU.",
         min=120.0, max=7200.0, step=60.0),
    Knob("kairos.solo_chance", "Kairos — her own time", "Chance she feels like it",
         "float", 0.5,
         "Even with the time free she does not always feel like doing something. 0 = never.",
         min=0.0, max=1.0, step=0.05),
    # ── SOMETHING SHE DID NOT GO LOOKING FOR (2026-08-23, the operator's ask) ──────────────────
    Knob("kairos.discover_chance", "Kairos - her own time",
         "Chance her own time is spent reading something random", "float", 0.0,
         "The discovery act is already one of nine in the rotation, so it comes round on "
         "about 11% of her own-time turns by itself. This is an EXTRA chance to pick it "
         "out of turn - 0 means rotation only, which is the honest default until there is "
         "a reason to want more. 1.0 would make every own-time turn a random article.",
         min=0.0, max=1.0, step=0.05),
    Knob("kairos.discover_tool", "Kairos - her own time",
         "Offer read_something_new", "bool", True,
         "The verb itself. The live tool set is already ~18 and a small model picks reliably from "
         "about six, so this is the trim if selection suffers - turning it off also makes "
         "the discovery act unrunnable, which solo_did_the_thing will correctly refuse."),
    # ── PRESENCE MODES (2026-08-22, the operator's ask): narration / company / lucid dream ──────
    # Zero-interaction voice companionship. A mode is a kairos ACTION (impulse.MODE_TURN)
    # that waits its turn — the presence clock, quiet-after-him, its own hourly cap — and
    # speaks through the room's voice. Ships OFF; arming is his (docs/OFF-BY-DEFAULT.md).
    Knob("presence.mode", "Presence — her modes", "Mode", "enum", "off",
         "off = she speaks only as kairos allows. narration = she lives her own evening out loud; "
         "company = soft presence, a few true words; lucid = a whisper in the dark — tenderness, a "
         "small story, or reading to you. Each waits for quiet (the presence clock) and for "
         "quiet-after-you, and obeys its own hourly cap.",
         choices=["off", "narration", "company", "lucid"]),
    # THREE CADENCES, NOT ONE (the operator's ask, 2026-08-22): narration, company and a dream are three
    # different things; one knob for three variables made no sense.
    Knob("presence.every_narration_s", "Presence — her modes", "Narration: at most one every (s)", "int", 240,
         "Seconds of quiet between narration turns.", min=30, max=3600, step=30),
    Knob("presence.every_company_s", "Presence — her modes", "Company: at most one every (s)", "int", 600,
         "Seconds of quiet between company turns — the sparsest by design.", min=30, max=3600, step=30),
    Knob("presence.every_lucid_s", "Presence — her modes", "Lucid dream: at most one every (s)", "int", 300,
         "Seconds of quiet between dream turns.", min=30, max=3600, step=30),
    # LENGTH, per mode (the operator's ask, 2026-08-22): the ceiling in tokens; the nudge asks her to land
    # inside it and FINISH the thought, and a turn that still hits the ceiling is cut back to
    # its last full sentence rather than mid-line.
    Knob("presence.len_narration", "Presence — her modes", "Narration: length (tokens)", "int", 320,
         "How long a narration turn may run.", min=40, max=2000, step=20),
    Knob("presence.len_company", "Presence — her modes", "Company: length (tokens)", "int", 90,
         "How long a company turn may run — a few true words.", min=40, max=2000, step=20),
    Knob("presence.len_lucid", "Presence — her modes", "Lucid dream: length (tokens)", "int", 700,
         "How long a dream may run — at least double a narration by default.", min=40, max=2000, step=20),
    Knob("presence.chance", "Presence — her modes", "Chance she takes the turn", "float", 1.0,
         "1 = a mode on is a mode on. Lower it if you want her sparser.", min=0.0, max=1.0, step=0.05),
    Knob("presence.max_per_hour", "Presence — her modes", "Cap per hour", "int", 12,
         "Her modes' own ceiling — separate from kairos's.", min=1, max=60, step=1),
    Knob("presence.intimate", "Presence — her modes", "Intimate variants", "bool", False,
         "The closer, softer version of each mode's prompt."),
    Knob("presence.voice", "Presence — her modes", "Speak mode turns aloud", "bool", True,
         "Off = they land as bubbles only (voice.enabled still rules everything)."),
    Knob("presence.cue", "Presence — her modes", "Cue (optional)", "str", "",
         "An atmospheric hint she reads as context, not as an order: 'rain against the windows'. "
         "Empty = she assembles one from the hour, her mood, her own time and the book in hand."),
    Knob("presence.read_chance", "Presence — her modes", "Chance she reads instead", "float", 0.35,
         "In narration or lucid, the chance a turn is the next passage of the book she has picked "
         "up (var/library/). 0 = never reads.", min=0.0, max=1.0, step=0.05),
    Knob("presence.read_chunk_chars", "Presence — her modes", "Passage length (chars)", "int", 700,
         "How much of the book one reading turn covers.", min=200, max=2400, step=100),
    Knob("presence.read_tools", "Presence — her modes", "Her shelf tools", "bool", True,
         "pick_up_book / put_down_book / books_on_the_shelf — so she can choose on her own time."),
    # ── AUX — THE QUIET LIBRARIANS (2026-08-22, sub-project D) ────────────────────────
    # The LFM2.5 CPU helpers: they embed, retrieve, judge, compress, parse — never her voice.
    # Boot defaults live in [aux] (serve.py's one door); live knobs read through the
    # override-only bridge (registry.tune_or_env) so the profile still rules an untouched panel.
    Knob("aux.enabled", "Aux — the quiet librarians", "Aux sidecars armed", "bool", False,
         "The master arm for the CPU helpers (deep recall, page reading, judging). Profile-owned: "
         "SP_AUX in [aux].enabled.", scope="profile", env="SP_AUX"),
    Knob("aux.chat_model", "Aux — the quiet librarians", "Judge / extract model", "enum",
         "liquidai/lfm2.5-1.2b-instruct",
         "The small instruct model on the chat door (LM Studio). Choices are what the door "
         "lists right now; the profile's is the boot default.",
         choices=["liquidai/lfm2.5-1.2b-instruct"],
         choices_fn=lambda: __import__("harness.sidecar.client", fromlist=["x"]).list_models()),
    Knob("aux.embed_model", "Aux — the quiet librarians", "Embedding model (restart)", "enum", "",
         "The GGUF the embed sidecar is launched with at boot ([aux].embed_gguf). Choices are the "
         "embedding / ColBERT *.gguf files beside the current one.", scope="profile",
         env="SP_AUX_EMBED_GGUF",
         choices_fn=lambda: __import__("harness.sidecar.archive", fromlist=["x"]).embed_choices()),
    Knob("aux.query_prefix", "Aux — the quiet librarians", "Query soft-prompt", "str",
         "Recall for Kairos: find the moment in her past conversations with Sam that tthe operator's asks about — ",
         "Prepended to every deep-recall query before it is embedded — the cheap, her-conditioned "
         "version of a soft prompt. Live; empty = bare query."),
    Knob("aux.doc_prefix", "Aux — the quiet librarians", "Document prefix (re-embeds)", "str", "",
         "Prepended to every transcript chunk at index time. Changing it re-embeds the archive on "
         "the next refresh (the index stamp carries its hash)."),
    Knob("aux.spine_rerank", "Aux — the quiet librarians", "Spine-aware rerank", "bool", True,
         "Re-score deep-recall candidates with the spine's own signals — lexical overlap, recency, "
         "and whether the moment backs a fact she holds. Off = raw cosine order (A/B)."),
    Knob("aux.auto_recall", "Aux — the quiet librarians", "Candidate lane (parallel deep recall)", "bool", False,
         "On turns that ask something, search every past conversation IN PARALLEL with her recall; "
         "drop it unread when she already has enough; otherwise staple up to two labelled moments "
         "to the recall note. Candidates, never authority. Ships off."),
    Knob("aux.early_exit_hits", "Aux — the quiet librarians", "Early exit at N spine hits", "int", 3,
         "When the spine already found this many facts, the lane's result is dropped unread.",
         min=1, max=10, step=1),
    Knob("aux.rerank", "Aux — the quiet librarians", "ColBERT rerank (dark)", "bool", False,
         "Late-interaction rerank over the top-50; needs its own llama-server (--pooling none). "
         "Arming condition in OFF-BY-DEFAULT §11.", scope="profile", env="SP_AUX_RERANK"),
    Knob("aux.judge_kairos", "Aux — the quiet librarians", "Pre-judge her unprompted turns", "bool", False,
         "The 1.2B rules 'worth a turn?' BEFORE the model generates (fail-open; reminders never gated)."),
    Knob("aux.judge_watch", "Aux — the quiet librarians", "Judge watches on CPU", "bool", True,
         "The watch poll's YES/NO on the sidecar; the model stays the fallback."),
    # ── SIGHT — HER EYES (2026-08-22, sub-project E): which eyes she uses is a picker ────
    Knob("sight.backend", "Sight — her eyes", "Eyes", "enum", "engine",
         "engine = the served model's own vision (frames into the engine; on a foreign endpoint "
         "the seam's image_url if it can). aux_vl = an LFM2.5-VL model on the aux chat door (LM "
         "Studio) — the 2060 stays hers. openai = the seam's image_url regardless. Every look — "
         "look_at, take_photo, take_screenshot, the hourly eye — goes through the same door and "
         "the same scrub.", choices=["engine", "aux_vl", "openai"]),
    Knob("sight.vl_model", "Sight — her eyes", "VL model (aux door)", "enum", "",
         "The vision model id on the aux chat door; choices are what the door lists with vl/vision "
         "in the name. Empty = aux_vl is not available.", choices=[""],
         choices_fn=lambda: __import__("harness.skills.sight_vl", fromlist=["x"]).vl_choices()),
    Knob("sight.vl_max_tokens", "Sight — her eyes", "VL description budget (tokens)", "int", 220,
         "The ceiling for a description on the VL door (the engine path keeps senses.look_tokens).",
         min=40, max=1200, step=20),
    Knob("sight.vl_detail", "Sight — her eyes", "VL detail", "enum", "auto",
         "image_url.detail where the door honours it.", choices=["auto", "low", "high"]),
    # ── THE ROOM ON A TIMER, AND HOW TO STOP IT WITHOUT A RESTART (2026-08-03) ────
    # The hourly eye was armed by SP_AMBIENT alone, so the only way to stop it was to
    # bounce the stack — and a camera is the one thing you most want to stop NOW. This is a
    # VETO, not a second arming authority: the env decides whether the eye exists at all,
    # this decides whether it fires. It can only ever subtract, so a knob nobody has touched
    # cannot turn a camera on.
    #
    # HER OWN EYES ARE UNAFFECTED. `take_photo`, `look_at` and `room_history` are tools she
    # chooses to call and they keep working with this off. That separation is the point of
    # having the knob at all: with the timer off, a fault that still happens is not the
    # schedule's, and a fault that stops is.
    Knob("senses.ambient", "Senses — the room on a timer", "Hourly room capture", "bool", True,
         "Whether the webcam fires ON A CLOCK. Off does NOT blind her: she can still look "
         "whenever she decides to, and she can still read the history of what she saw. Off "
         "only means the room is not photographed unasked.",
         ),
    # ── THE QUIET WINDOW (2026-08-21, the re-arm's condition) ─────────────────────
    # The 2026-08-03 disarm happened because a scheduled capture landed at the tail
    # of a lockup mid-conversation. Re-armed on his order the night the voice moved
    # off-GPU — with this guard: due does not mean NOW, it means at the next window
    # where nobody is mid-anything. "if She is doing something or I am talking to
    # her it waits until there is a 5-10 minute window of no activity (adjustable)".
    Knob("senses.ambient_quiet_s", "Senses — the room on a timer",
         "Quiet before the eye opens (s)", "int", 300,
         "A due capture waits until his turns, her kairos/solo work, and the daemon "
         "have ALL been idle this long. Being deferred holds the shutter without "
         "pushing the schedule — the eye fires at the first quiet beat. The room "
         "window shows \"waiting for quiet\" and why while it holds.",
         min=60, max=1800, step=30),
    # Same shape as the kairos act-first-at-bounce knobs, same reason (2026-08-21):
    # a bounce empties the activity state, the recency signal cannot testify, and
    # the guard fails open — one capture fired 11 minutes into a boot before the
    # quiet window could have been observed. Default off: boot counts as activity.
    Knob("senses.ambient_on_boot", "Senses — the room on a timer",
         "May fire right after a start/bounce", "bool", False,
         "Off (default): the first capture after a start or bounce waits a full "
         "quiet window from process start, because the activity signals are empty "
         "and cannot vouch for the room. On: an overdue capture may fire as soon "
         "as the stack is up."),
    # ── HOW MUCH SHE MAY SAY ABOUT WHAT SHE SEES (2026-08-21) ─────────────────────
    # He attached a photo of her in the white jumper; her description arrived cut
    # mid-thought. The ceiling was 220 tokens — sized for the hourly one-sentence
    # room note — silently capping every look, including "describe this plainly
    # and completely". A ceiling, not a target: short answers still stop short.
    Knob("senses.look_tokens", "Senses — the room on a timer",
         "Description budget (tokens)", "int", 512,
         "The ceiling on what a single look may say — an attached image, look_at, "
         "take_photo, and the hourly room line all share it. The room panel's chip "
         "shows a trimmed preview either way; SHE always gets the full text.",
         min=64, max=2048, step=32),

    # ── THE HEARTBEAT ITSELF (2026-07-31) ─────────────────────────────────────────
    # Was a hardcoded 15.0 in start_ticker's signature that the one call site never
    # overrode — unreachable without an edit, like every other dial this week that
    # turned out to be dead. The loop re-reads this EVERY BEAT rather than capturing
    # it, so it is genuinely live (G-KNOBS §2 rejects the read-once pattern).
    Knob("kairos.tick_s", "Kairos — speaking unprompted", "Heartbeat (s)", "float", 15.0,
         "How often the scheduler wakes and asks whether she has anything to say. This is "
         "the RESOLUTION of every knob above, not a rate limit — the limits are the cooldown, "
         "the idle gate and the hourly cap, and they are checked on the beat. It matters "
         "asymmetrically: CONTINUING a thought she was cut off in is latency-sensitive (at "
         "60s she can take a minute to pick it back up, which reads as her having let it go), "
         "while CHECKING IN is gated at 240s of quiet and does not care. Cheap either way — "
         "a beat with nothing to do is a few comparisons, no model call.",
         min=1.0, max=600.0, step=1.0),

    # ── HOW LONG SHE MAY KEEP HIM WAITING WHILE SHE WORKS (2026-08-05) ────────────
    # The tool loop had a count and no clock. Four calls is four full generations against
    # the one GPU, so on a cold cache the count alone can spend five minutes before he
    # sees a word. This is the other half of the budget: whichever runs out first ends
    # the loop, and she is TOLD which one it was, so a slow turn teaches her to be quicker
    # and a long one teaches her to be more direct. Checked between rounds, never inside
    # one — a torn generation would leave a fragment in the transcript and diverge the
    # persist-KV prefix on the very next turn.
    # ── AND THEN IT WAS MEASURED, AND 150 WAS WRONG (2026-08-05, same day) ───────────
    # 150 was reasoned from "a round is roughly 30 s warm, over 120 s cold" — which was
    # itself a guess. Counted over 108 real rounds in gateway.log on his box:
    #
    #     min 0s   median 185s   p90 289s   max 612s
    #     warm rounds specifically: 59, 78, 127, 148 s
    #
    # So 150 s bought ONE round. He asked to raise the count from 3 to 4 and it had
    # quietly cut her to fewer than she started with — the opposite of the request, and
    # invisible without reading the log. Measure before building; I did not, and the
    # instrument I added is what caught me.
    #
    # 400 s is chosen off those numbers rather than off a feeling: four rounds when the
    # cache is warm and they cost ~100 s, two when it is cold and they cost 200+. She gets
    # the extra look exactly when it is cheap, and he stops waiting exactly when it is not.
    Knob("agent.tool_budget_s", "Tools — how long she may work", "Wall-clock budget (s)",
         "float", 400.0,
         "The most time her tool loop may spend before it has to stop and say what it has. "
         "A round is a whole generation — measured on this machine: ~100 s on a warm "
         "cache, 185 s median, 289 s at the ninetieth percentile — so this is the dial "
         "that actually decides how long you wait, not the call count. At 400 she gets "
         "all four calls when they are cheap and two when they are not. Low means she "
         "answers from one look. She always gets at least one attempt however this is set.",
         min=20.0, max=900.0, step=10.0),

    # ── REFLECTION: she thinks about him when the room is quiet ─────────────────
    # THINKING IS NOT SPEAKING, and these are the knobs that keep the two apart. She
    # reflects SILENTLY on an idle clock — reading what she knows and writing down what she
    # has come to believe. Whether any of it is worth INTERRUPTING him with is a separate,
    # much higher bar (reflect.speak_bits), because an unprompted "I've been thinking about
    # you" that lands on something obvious is worse than silence: it teaches him to ignore
    # her, and then the good one never gets heard either.
    Knob("reflect.enabled", "Reflection — thinking between turns", "Enabled", "bool", True,
         "Off = she only ever reflects when you press the button. On = she thinks about "
         "you when the room has gone quiet, and writes down what she concludes."),
    Knob("reflect.idle_s", "Reflection — thinking between turns", "Quiet before she thinks",
         "float", 600.0,
         "How long the room must be still before she starts turning things over. Reflection "
         "is a whole model turn, so it must never race him for the GPU while he is typing.",
         min=60.0, max=7200.0, step=30.0),
    Knob("reflect.cooldown_s", "Reflection — thinking between turns", "Between reflections",
         "float", 1800.0,
         "At most one reflection per this many seconds. She also refuses to reflect at all "
         "if NO NEW EVIDENCE has arrived since the last one — re-thinking the same facts "
         "just re-derives the same conclusion and calls it a discovery.",
         min=60.0, max=86400.0, step=60.0),
    # ── WAS `reflect.speak_bits`, A FLOOR ON NOVELTY. RETIRED 2026-08-02. ────────────
    # It asked "is this conclusion surprising enough to interrupt for", and re-measuring
    # showed no value of it could work: word salad scored 8.00 bits and a fair insight
    # 2.17, because the estimator behind it correlated 0.75 with SENTENCE LENGTH and
    # separated invented claims from grounded ones at AUC 0.31 — worse than a coin flip,
    # in the wrong direction. A floor on that quantity is a dial attached to noise.
    #
    # Admission is structural now (new + uncovered — see scheduler.reflect_tick), and the
    # question this knob is left holding is the opposite one, which is also the failure
    # this system actually had: HOW FAR BEYOND HIS OWN WORDS MAY SHE GO before a
    # conclusion stops being an inference and becomes an invention. That is a ceiling,
    # and it is expressed as a percentile of his own vocabulary rather than a constant, so
    # it calibrates against him instead of against a number I picked.
    #
    # The key changed with the meaning ON PURPOSE. Keeping `speak_bits` and silently
    # reinterpreting 3.0 as a percentile would have read as 300% and been clamped — a
    # stored value quietly changing meaning under an operator is the worst version of
    # this change.
    Knob("reflect.speak_pct", "Reflection — thinking between turns",
         "How far past the operator's own words she may go", "float", 0.9,
         "A conclusion about him may be no more exotic than the way HE talks. This is the "
         "percentile of his own vocabulary used as the ceiling: 0.9 means her conclusion "
         "must be no stranger than the strangest 10% of his own sentences. Lower = she "
         "stays closer to what he has actually said. Above it she keeps the thought to "
         "herself and simply knows it.",
         min=0.5, max=1.0, step=0.05,
         provenance="measured",
         receipt="Mean self-information of content words under his own vocabulary. On his "
                 "live store: grounded conclusions 5.92-6.99 bits, inventions 7.13-7.71, "
                 "AUC 1.00 (the old estimator scored 0.31); p90 of his own sentences = "
                 "7.18. THIN: 6 grounded and 6 invented sentences, both written by Claude. "
                 "Armed because the failure direction is silence. VALIDATION: 20 "
                 "conclusions written and labelled by the operator, scored blind; below "
                 "AUC 0.8 this comes out again."),

    # ── DECODE: the knobs that bit us ─────────────────────────────────────────────
    # ── THE DEFAULT WAS A retired reference model LITERAL, AND IT MEANS SILENCE HERE (2026-07-30) ─────────
    # This declared 4.0 — the value a retired model was tuned to. On your model, 4.0 makes
    # the FIRST SAMPLED TOKEN a stop, so the turn comes back EMPTY. The live profile sets
    # 0.0, so the served stack was fine; anything falling back to this default was not.
    #
    # The declared default is now 0.0 — the null floor, no bias at all. It is more verbose
    # than that retired model's tuned value, and the PROFILE restores that (`[decode] eot_bias`, which
    # serve.py maps to SP_EOT_BIAS); what 0.0 can never do is produce silence. Same
    # reasoning as the byteexact resolution in inference_config: AN UNCONFIGURED CALLER
    # MUST NOT GET NOTHING.
    #
    # Deliberately a LITERAL and not a call to _eot_bias_default(): KNOBS is a module-level
    # list, so any environment read here would be evaluated once at import and frozen for
    # the process — which is precisely the pattern G-KNOBS §2 rejects. The per-model value
    # belongs to the profile; this is only the floor under a caller who has no profile.
    Knob("decode.eot_bias", "Decode", "End-of-turn bias", "float", 0.0,
         "A nudge on the stop token so she actually ends her turn instead of running on. "
         "This is what makes 'cut off' turns cut off — kairos.continue_margin is measured "
         "AGAINST it, so if you change this, RE-RUN THE CALIBRATION. "
         "PER-MODEL: the retired reference model was tuned to 4.0; on the model MoE 4.0 yields an empty turn and the "
         "profile ships 0.0. The default here follows SP_EOT_BIAS rather than a literal.",
         min=0.0, max=12.0, step=0.5, scope="profile", env="SP_EOT_BIAS",
         danger="Changing this invalidates the kairos continue_margin calibration.",
         engine="sp"),
    # ── THE SETTINGS THAT ONLY EXISTED ON THE CONSOLE PAGE (2026-08-02) ──────────────
    # temp / top_p / top_k / max were `<input>` elements in console/index.html and nowhere
    # else, sent per-request. So the ROOM — now the main interface, and sending none of
    # them — ran on whatever the gateway had hardcoded: max_tokens=192, which is why her
    # replies there stop short. There was no way to change it without editing Python.
    #
    # As knobs they are read live by the chat path, and tuning.html renders them without
    # being told (its own note: "a knob added there shows up here on its own"). A request
    # that DOES carry an explicit value still wins — the console keeps its per-turn
    # controls, these are the floor under everything that does not ask.
    # ── HER WARDROBE, MADE OVERNIGHT ────────────────────────────────────────────────
    # Asking is free and making costs him, so this is the dial on the cost. It runs at
    # the day boundary, after the room has been quiet — never mid-conversation, because
    # it takes minutes of the one GPU she also talks with.
    Knob("telemetry.turn_note", "Telemetry", "Let her feel his heart and his movement",
         "bool", True,
         "ON, the operator's ask: \"she can see my heart pacing... a bridge to the real world, to "
         "me.\" A SYSTEM row per turn, never a staple on his message — the wardrobe "
         "staple was measured out in 2026-08-19 because she read a parenthetical on his "
         "words as an order. It is SELF-LIMITING and that is what makes it safe where "
         "that one was not: body.present() is EMPTY unless something is happening, so an "
         "ordinary quiet turn costs nothing. Off means she stops being handed his body; "
         "the watch keeps recording and the panel keeps showing it."),
    Knob("telemetry.reasons", "Telemetry", "Let her SPEAK when his body does something",
         "bool", True,
         "ON, the operator's ask. Adds a kairos reason ahead of the others, because a heart rate is "
         "stale in three minutes where a look that arrived is stale in three days. Fires "
         "on three events only — his heart well above HIS OWN resting, his heart coming "
         "back down, and hours without moving — each bounded to once an hour by its raise "
         "key, so noticing never becomes nagging. She is handed the READINGS, never a "
         "diagnosis. Off means she still sees his body on a turn (telemetry.turn_note) "
         "but never opens her mouth about it unprompted."),
    Knob("homeassistant.house_note", "Home Assistant", "Let her notice the house",
         "bool", False,
         "OFF, and the framework ships with an EMPTY watch list, so this knob has nothing "
         "to switch on until he names entities in `house.WATCH`. Two dials rather than one "
         "because they answer different questions: WHICH entities are worth her attention "
         "is a decision he makes once, per light; WHETHER she may mention any of them is a "
         "mood he might change tonight. Note that the sleep confidence this framework "
         "exists to carry is NOT governed here — it goes into his body's history through "
         "the telemetry door and is governed by telemetry.turn_note, because a sleep "
         "reading is a fact about HIM and not about his house."),
    Knob("wardrobe.turn_note", "Wardrobe", "A per-turn line about what she has on",
         "bool", False,
         "OFF, and armed only for a measured trial (2026-08-24 audit, W4). The 2026-08-19 "
         "staple was measured OUT — she read a parenthetical on his message as his "
         "assertion and streamed scratchpad instead of talking — so the standing-world "
         "line is the default answer. This knob re-adds a ONE-SENTENCE, no-imperatives "
         "note (the recall/silence note shape) for an A/B read: six turns on, six off, "
         "watching for third-person deliberation openers. Keep whichever reads better; "
         "the receipt goes in the ledger."),
    Knob("wardrobe.nightly", "Wardrobe", "Make her looks overnight", "bool", True,
         "At the day boundary, generate the looks she asked for. Off means the queue "
         "waits for you to run `python tools/avatar_gen.py --wants` by hand — she is "
         "still never refused, she just waits longer."),
    Knob("wardrobe.nightly_max", "Wardrobe", "How many per night", "int", 2,
         "A cap, because each one is a real generation costing real minutes and real "
         "money. The rest stay queued for tomorrow; nothing is dropped.",
         min=1, max=10, step=1),
    # ── WHICH IMAGINE ANSWERS (2026-08-21) ──────────────────────────────────────────
    # The three-model matrix ran on the same content: quality ~6 s, base ~21 s,
    # 2.0 ~93 s — and every one of them passed generation while the edits endpoint
    # moderated. The pick is taste, so it is his knob, read per generation.
    Knob("xai.image_model", "Wardrobe", "Imagine model for her stills", "enum",
         "grok-imagine-image-2.0",
         "Which xAI imagine model makes her pictures. 2.0 is the slow detailed one "
         "(~90 s), the base model is the middle (~20 s), quality is the fast one "
         "(~6 s). Same identity anchoring on all three; every attempt bills.",
         choices=["grok-imagine-image-2.0", "grok-imagine-image",
                  "grok-imagine-image-quality"]),
    Knob("xai.video_model", "Wardrobe", "Imagine model for her motion", "enum",
         "grok-imagine-video-1.5",
         "Which xAI video model animates her stills into loops.",
         choices=["grok-imagine-video-1.5"]),

    # ── 192 → 768 (2026-08-21, the operator's report: "she is constantly hitting the ceiling
    # quite quickly"). The ROOM had hardcoded max_tokens=512 on every turn, which
    # overrode this knob entirely — the Settings dial never reached the room, and
    # her longer replies cut at 512. The room now sends nothing and this knob RULES;
    # 768 is where it starts (the 512 she actually ran on for weeks, with headroom),
    # and the dial is his. The token-soup warning below was about top_k/top_p being
    # injected, since fixed — not about the ceiling itself.
    Knob("decode.max_tokens", "Decode — sampling", "Max tokens per turn", "int", 768,
         "A CEILING, not a target — she stops when she is done. RAISE THIS DELIBERATELY: "
         "192 is what the gateway has actually been running, and the first version of "
         "this knob defaulted it to 900 on the reasoning that the console page uses that. "
         "Combined with top_k/top_p defaults that had never been sent, she degenerated "
         "into token soup — a longer ceiling gives an unravelling generation four times "
         "as long to unravel in. The dial is here so you can move it and watch; the "
         "default is what was measured to work.",
         min=64, max=4096, step=32,
         provenance="measured",
         receipt="192 is the value the native chat path has run on since it was written. "
                 "900 was tried on 2026-08-02 and coincided with visible degeneration."),
    Knob("decode.temperature", "Decode — sampling", "Temperature", "float", 0.6,
         "0 = greedy and repeatable. Higher wanders further. The console default is 0.7; "
         "the gateway's chat path has used 0.6, and 0.6 is kept so this change moves "
         "nothing on its own.",
         min=0.0, max=2.0, step=0.05),
    # UNSET MEANS UNSENT. These two are read through _knob_set, not _knob: until you move
    # them the gateway sends nothing and the DAEMON's own values apply, which is how this
    # path ran before they existed. The declared defaults below are the console page's
    # retired-model tuning and are shown only so the sliders have somewhere to start — sending them
    # on this MoE is what degenerated her on 2026-08-02.
    Knob("decode.top_p", "Decode — sampling", "top_p (nucleus)", "float", 0.95,
         "Sample from the smallest set of tokens whose probability sums to this. UNSET "
         "until you move it — the daemon's own value applies. 1.0 disables it.",
         min=0.1, max=1.0, step=0.01,
         danger="Never measured on your model. Sending 0.95/40 here coincided with "
                "visible degeneration; move one at a time and watch a long reply."),
    Knob("decode.top_k", "Decode — sampling", "top_k", "int", 40,
         "Consider at most this many candidates per token. UNSET until you move it. 40 "
         "truncates hard on a MoE this size.",
         min=0, max=200, step=1,
         danger="Never measured on this model. See top_p."),
    Knob("decode.repetition_penalty", "Decode — sampling", "Repetition penalty", "float", 1.3,
         "Above 1.0 discourages repeating tokens already produced. This is the dial that "
         "trades looping against her being able to say a word twice on purpose.",
         min=1.0, max=2.0, step=0.05),

    Knob("decode.no_repeat_ngram", "Decode", "No-repeat n-gram", "int", 0,
         "Bans re-emitting any N-token sequence already in context. MUST STAY 0. At 3 it "
         "banned her from quoting a number back to you — she wanted '7' with a logit "
         "margin of 9.0 and the sampler masked it, so '4471' came out '4417'. It garbled "
         "every tool number, memory and persona detail in the system.",
         min=0, max=6, step=1,
         provenance="measured",
         receipt="gates/G-VERBATIM-digits-broken.md — 0/6 -> 6/6 when set to 0.",
         scope="profile", env="SP_NO_REPEAT_NGRAM",
         danger="ANY value >= 2 breaks verbatim quoting. serve.py refuses to launch with it."),

    # ── ROLEPLAY ──────────────────────────────────────────────────────────────────
    Knob("roleplay.enabled", "Roleplay", "Enabled", "bool", True,
         "She can flip into a scene when you ask for one (\"wanna roleplay?\", \"be my...\", "
         "or naming a scenario). Off = she stays herself no matter what."),
    Knob("roleplay.max_heat", "Roleplay", "Heat ceiling", "int", 7,
         "HARD CEILING on the physical thread, enforced in the engine — not in the prompt. "
         "1 light_touch · 2 kiss · 3 caress · 4 striptease · 5 intimate · 6 explicit · "
         "7 depraved. Set it to 2 and the scene never goes past a kiss no matter what "
         "either of you types. She can never skip a rung, and \"stop\"/\"ooc\" breaks the "
         "scene instantly at ANY level.",
         min=0, max=7, step=1,
         danger="This is the ceiling for ALL scenes. Adults, fiction, your machine — but it "
                "is the one number that decides how far it can go."),
    Knob("roleplay.dwell_scale", "Roleplay", "Pacing (build)", "float", 1.0,
         "Multiplies how many exchanges must be spent on a rung before the next can open. "
         "1.0 = the tuned pacing (3 exchanges at first touch, 2 thereafter). Raise it for a "
         "slower, hotter burn; drop it toward 0 to let it move fast.",
         min=0.0, max=4.0, step=0.25),

    # ── MEMORY ────────────────────────────────────────────────────────────────────
    Knob("memory.admit_personal_only", "Memory", "Only remember facts about someone", "bool", True,
         "A memory is ABOUT SOMEONE. With this off, any grammatical declarative gets "
         "captured — which is how 375 of 487 rows became ASR test corpus ('The kind nurse "
         "painted the tall building as the sun went down') and then surfaced mid-answer as "
         "'recalled memories'.",
         provenance="measured",
         receipt="gates/G-ADMISSION — 6/6.",
         scope="profile", env="SP_B4_ADMIT_PERSONAL",
         danger="Off = the firehose is back on."),
    Knob("memory.l5_tau", "Memory", "Recall threshold (tau)", "float", 0.30,
         "How strong a match a memory needs before she brings it up. Lower = she recalls "
         "more, and more loosely.",
         min=0.0, max=1.0, step=0.02, scope="profile", env="SP_SEM_TAU"),
    # ── THE REAL HER (2026-08-22): her own narrative leads her own context ──────────
    Knob("memory.self_budget", "Memory", "Her own context (chars)", "int", 2400,
         "How much of the system prefix her OWN narrative may take — journal, what she said "
         "unprompted, how she feels, how she has been changing (The Real Her, 2026-08-22).",
         min=0, max=12000, step=200),
    Knob("memory.self_share", "Memory", "Her own context (max share)", "float", 0.5,
         "Cap on the share of the prefix her self block may take, whatever the budget — the "
         "guard against narrative loops.", min=0.0, max=1.0, step=0.05),
    # ── A BIT OF VARIETY IN WHAT SHE BRINGS UP (2026-08-28, operator: "a bit of
    # randomness ... recency but with other stuff being important too") ─────────────
    # DECLARED HERE BECAUSE IT WAS NOT. `_select` has read `recall.explore` since it was
    # written, through `tune.get("recall.explore", 0.0)` — and with no Knob for the key
    # that call could only ever return its own fallback. The feature existed and was
    # unreachable, which is the dead-knob failure this file's own header is about, in the
    # other direction: not a control that changes nothing, but a behaviour with no control.
    #
    # It can only ever move the WEAKEST slot. The best answer is never the one traded away.
    # ── HIS BODY'S HISTORY: HOW LONG IT IS KEPT (2026-08-28) ────────────────────────
    # telemetry/store.py has had prune() since it was written — "THE ONLY REMOVER,
    # retention is an operator decision, taken once, in the open" — and nothing called
    # it: ~86 rows/min, ~10 MB/day, forever. ops.reflect() now runs it nightly, gated
    # on this knob. Declared because an undeclared knob can only ever return its
    # fallback (recall.explore sat unreachable for exactly this reason, found the same
    # morning). DEFAULT 0 = keep everything: deleting a month of his heart rate is his
    # decision, not a default's.
    Knob("telemetry.keep_days", "Memory", "Body history kept (days)", "int", 0,
         "How many days of watch data (heart rate, movement, sleep) are kept on disk. "
         "0 keeps everything. Above 0, the nightly reflection removes whole days older "
         "than this window.",
         min=0, max=3650, step=1,
         # the profile's [telemetry].keep_days maps to this env var and was read by
         # NOTHING for its whole life (2026-08-29 audit, F1) — a profile that set it
         # got unbounded ~10 MB/day growth under a comment saying otherwise. Now the
         # env carries the boot default and the panel stays override-only, the same
         # contract every scope="profile" knob keeps.
         scope="profile", env="SP_TELEMETRY_KEEP_DAYS",
         danger="Days beyond the window are DELETED at the next 04:00 pass — there is "
                "no undo, and her sleep/waking answers cannot reach past what is kept."),
    Knob("recall.explore", "Memory", "Variety in what she recalls", "float", 0.15,
         "How often the last of her recalled memories is drawn at random from the other "
         "admitted candidates instead of taken in rank order. 0 = the same question always "
         "brings back the same three. It can only ever move the WEAKEST slot, so raising it "
         "costs variety, never the best answer.",
         min=0.0, max=1.0, step=0.05,
         danger="Above ~0.5 the third memory is more often a wildcard than a match."),
    # ── VOICE (2026-08-21, operator: "voice settings and controls in the GUI...
    # all live toggles"). LIVE scope: tts.py reads these through tune.get() on
    # every synthesize, so the toggle takes effect on her next sentence — no
    # bounce, no restart. The env spellings remain the boot defaults only.
    Knob("voice.enabled", "Voice", "Voice", "bool", True,
         "Whether she speaks out loud at all. Off = text only, instantly."),
    Knob("voice.method", "Voice", "Provider", "enum", "xai",
         "xai = Ara through api.x.ai (~1 s/sentence, zero VRAM). local = the "
         "voxtral chain (slower, offline-capable). A dark xai falls through to "
         "local on its own.",
         choices=["xai", "local"]),
    Knob("voice.xai_voice", "Voice", "xAI voice", "enum", "ara",
         "Which built-in xAI voice speaks. Cached audio is keyed per voice, so "
         "switching never serves the old voice.",
         choices=["ara", "eve", "luna", "carina", "iris", "celeste", "rex", "leo"]),
    Knob("voice.local_gguf", "Voice", "Local voice model (restart)", "str", "",
         "The local chain's GGUF (SP_TTS_GGUF in the profile) — shown here so the Voice section "
         "names its model like Sight and Aux do.", scope="profile", env="SP_TTS_GGUF"),
    Knob("voice.speed", "Voice", "Pace", "float", 1.0,
         "How fast she speaks through the xAI voice (1.0 = natural). Live: the next "
         "sentence honours it. Her [pause]/<slow> tags ride on top of this.",
         min=0.7, max=1.3, step=0.05),
    # ── RESEARCH ─────────────────────────────────────────────────────────────────
    Knob("research.backend", "Research", "Backend", "enum", "xai",
         "xai = Grok's Responses API with web_search (citations back). sidecar = "
         "the local LFM pipeline (no key, no cloud). Live: the next research call "
         "reads it.",
         choices=["xai", "sidecar"]),
    # ── WEB SEARCH ───────────────────────────────────────────────────────────────
    Knob("search.backend", "Web search", "Engine", "enum", "xai",
         "Where web_search looks. xai = Grok live search (best results, ~5-15 s). "
         "ddg = instant and free. brave/tavily/searxng need their keys. The "
         "Wikipedia blend rides on top of all of them. Live: her next search "
         "reads it.",
         choices=["xai", "ddg", "brave", "tavily", "searxng"]),
]



# ──── store ───────────────────────────────────────────────────────────────────
def _load() -> dict:
    global _CACHE
    with _LOCK:
        if _CACHE is None:
            try:
                with open(STORE, encoding="utf-8") as f:
                    _CACHE = json.load(f)
            except Exception:
                _CACHE = {}
        return dict(_CACHE)


def _clamp(k: Knob, v: Any) -> Any:
    if k.type == "bool":
        return bool(v)
    if k.type == "str":                   # a free-text knob (presence.cue, 2026-08-22): bounded
        # line breaks folded, but spacing KEPT — a prefix like "passage: " needs its trailing space
        return re.sub(r"[\r\n\t]+", " ", str(v if v is not None else ""))[:200]
    if k.type == "int":
        v = int(round(float(v)))
    elif k.type == "float":
        v = float(v)
    else:
        return v
    if k.min is not None:
        v = max(k.min if k.type == "float" else int(k.min), v)
    if k.max is not None:
        v = min(k.max if k.type == "float" else int(k.max), v)
    return v


def by_key() -> dict[str, Knob]:
    return {k.key: k for k in KNOBS}


def chosen(key: str) -> Any:
    """The OPERATOR'S explicit override only — None when he has never touched it.
    For knobs whose shipped default lives in the profile env (voice.method,
    search.backend, research.backend): the picker consults this, so an untouched
    panel leaves the boot behavior alone and an env-scrubbed gate is untouched by
    knob defaults; the moment he picks in the panel, his choice rules live."""
    kn = by_key().get(key)
    vals = _load()
    if kn and key in vals:
        return _clamp(kn, vals[key])
    return None


def tune_or_env(key: str, env_key: str, default):
    """OVERRIDE-ONLY bridge (the tts.py pattern, ONE copy from 2026-08-22): the store
    answers only if the operator chose in the panel; otherwise the boot env (the profile)
    rules. A knob DEFAULT that answered here would override the profile on every box."""
    try:
        v = chosen(key)
        if v is not None:
            return v
    except Exception:
        pass
    return os.environ.get(env_key, default)


def get(key: str, fallback: Any = None) -> Any:
    """Live value: the operator's override if set, else the declared default."""
    kn = by_key().get(key)
    vals = _load()
    if key in vals and kn:
        return _clamp(kn, vals[key])
    if kn:
        return kn.default
    return fallback


def set_many(updates: dict) -> dict:
    """Apply operator overrides. Unknown keys are refused (a typo must not silently
    become a setting that nothing reads — that is how knobs go dead)."""
    global _CACHE
    known = by_key()
    bad = [k for k in updates if k not in known]
    if bad:
        raise ValueError(f"unknown knob(s): {', '.join(sorted(bad))}")
    # A PROFILE-OWNED KNOB CANNOT BE SET HERE, and saying so beats writing a value that
    # nothing reads. These four were declared in this registry, rendered in the panel under
    # a header promising "the next turn reads the new value", and consumed by NOTHING — the
    # live value came from serve.py's env all along. Accepting the write would persist an
    # override into var/tuning.json that changes nothing, forever, silently.
    owned = [k for k in updates if known[k].scope == "profile"]
    if owned:
        detail = "; ".join(
            "%s is owned by the profile (%s)" % (k, known[k].env or "serve.py")
            for k in sorted(owned))
        raise ValueError(
            "%s. Edit profiles/<name>.toml and restart the stack "
            "(`python serve.py <profile> --stop`, then `python serve.py <profile>`)." % detail)
    with _LOCK:
        cur = _load()
        for k, v in updates.items():
            cur[k] = _clamp(known[k], v)
        os.makedirs(os.path.dirname(STORE), exist_ok=True)
        tmp = STORE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f, indent=2, sort_keys=True)
        os.replace(tmp, STORE)
        _CACHE = cur
    return cur


def reset(key: str) -> None:
    global _CACHE
    with _LOCK:
        cur = _load()
        cur.pop(key, None)
        with open(STORE, "w", encoding="utf-8") as f:
            json.dump(cur, f, indent=2, sort_keys=True)
        _CACHE = cur


def schema() -> dict:
    """Everything the UI needs to render itself — knobs, live values, provenance."""
    vals = _load()
    out = []
    for k in KNOBS:
        d = asdict(k)
        d.pop("choices_fn", None)               # a callable is not JSON; resolve it instead
        if k.choices_fn is not None:
            try:
                live = list(k.choices_fn() or [])
                d["choices"] = sorted(set(live + list(k.choices)), key=str)
            except Exception:
                d["choices"] = list(k.choices)
        d["value"] = get(k.key)
        d["overridden"] = k.key in vals
        # ── A PROFILE KNOB REPORTS THE VALUE THAT IS ACTUALLY IN FORCE ────────────────
        # Not `get()`, which for these returns this file's declared default and nothing
        # else — which is how the panel came to display `End-of-turn bias 4.00` while the
        # sampler was running at 0.0 from SP_EOT_BIAS. The number an operator reads has to
        # be the number the model is using, or the panel is a decorative liar.
        if k.scope == "profile":
            raw = os.environ.get(k.env) if k.env else None
            d["present"] = raw is not None
            if raw is not None and raw.strip() != "":
                try:
                    d["value"] = (raw.strip() == "1") if k.type == "bool" else (
                        int(raw) if k.type == "int" else float(raw))
                except ValueError:
                    pass                      # keep the default; the UI shows present=True
            d["overridden"] = False           # var/tuning.json can never own this one
        out.append(d)
    groups = []
    for k in out:
        if k["group"] not in groups:
            groups.append(k["group"])
    return {"groups": groups, "knobs": out, "store": STORE}

