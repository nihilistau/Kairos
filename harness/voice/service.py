"""/v1/voice — the P0 voice turn (ADR-KAI4).

Browser sends one VAD-segmented utterance (PCM16 mono 16k, base64) + session_id.
We: guard-VAD → log-mel → GNA ear → [k×E] frames → daemon /v1/chat with
inject_frames (audio placeholder 258881) → stream the reply deltas back (the
console speaks them via its v0 TTS). The canonical session transcript records
the voice turn so the conversation stays coherent across modalities.

P0 honesty notes:
  * inject_frames turns bypass persist-KV in the daemon (B5 seam exclusion) —
    a voice turn costs a fresh prefill; persist∘inject composition is a P1 item.
  * The ear's legible vocabulary is the trained V_sub — P0 gates PLUMBING
    (G-VOICE-0); free speech arrives with the P1 vocab scale-up.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, Iterator

import numpy as np

from harness.voice import dsp, ear, native

import logging
from harness.loud import swallowed as _swallowed
_swlog = logging.getLogger(__name__)

VOICE_PH = 258881          # the gemma-4 audio placeholder (KAI-3 constant)
VAD_RMS = float(os.environ.get("SP_VOICE_VAD_RMS", "0.010"))
MAX_SECONDS = 30


def voice_status() -> Dict[str, Any]:
    return {"ear": ear.status(), "vad_rms": VAD_RMS, "inject_ph": VOICE_PH}


def voice_turn(body: Dict[str, Any], transcript: list) -> Iterator[bytes]:
    """SSE generator: {'voice':...} header event, then daemon deltas, then [DONE]."""
    def ev(obj: Dict[str, Any]) -> bytes:
        return ("data: " + json.dumps(obj) + "\n\n").encode()

    try:
        pcm = dsp.pcm16_to_f32(base64.b64decode(body.get("audio_b64", "")))
    except Exception as exc:
        yield ev({"error": f"bad audio_b64: {exc}"})
        yield b"data: [DONE]\n\n"
        return
    if pcm.size == 0 or pcm.size > MAX_SECONDS * dsp.SR:
        yield ev({"error": f"utterance empty or >{MAX_SECONDS}s"})
        yield b"data: [DONE]\n\n"
        return

    energy = dsp.rms_energy(pcm)
    if energy.size == 0 or float(energy.max()) < VAD_RMS:
        yield ev({"voice": {"skip": "silence", "rms": float(energy.max() if energy.size else 0)}})
        yield b"data: [DONE]\n\n"
        return

    # ── NATIVE encoder-free audio path (THE POINT: raw audio -> the model's own
    #    embed_audio.embedding_projection -> inject at audio token 258881). The CTC
    #    "ear" was a transcription substitute; the native path is what Gemma was
    #    trained to interpret as sound. SP_VOICE_EAR=1 forces the legacy CTC path. ──
    use_native = native.available() and os.environ.get("SP_VOICE_EAR") != "1"
    if use_native:
        frames = native.encode(pcm)
        path = f"native (embed_audio {native.status().get('E')}d)"
    else:
        try:
            frames = ear.hear(dsp.logmel(pcm))
        except ear.EarUnavailable as exc:
            yield ev({"error": f"ear unavailable: {exc}"})
            yield b"data: [DONE]\n\n"
            return
        path = f"ctc-ear ({ear.status().get('device')})"

    n_fr = int(frames.shape[0])
    yield ev({"voice": {"frames": n_fr, "path": path,
                        "seconds": round(pcm.size / dsp.SR, 2)}})
    if n_fr == 0:
        yield ev({"delta": "(I heard sound but couldn't extract audio frames.)"})
        yield b"data: [DONE]\n\n"
        return

    # NATIVE audio: the daemon appends the injected frames right AFTER the full
    # prompt (each minted as the <|audio|> token 258881 — HF masked_scatter parity).
    # So the LAST message's text must be the instruction that immediately precedes
    # the audio, and it must NOT mention "frames"/counts or add <|audio> boa/eoa
    # markers — doing so makes the model ECHO the text or double-count the audio
    # (proven: a clean "listen and reply" prompt transcribes real speech; adding
    # frame-count text or boa/eoa breaks it). The audio itself IS the user turn.
    instr = os.environ.get(
        "SP_VOICE_PROMPT",
        "The user just spoke to you out loud. First understand exactly what they "
        "said, then reply directly and briefly to their actual words — do not "
        "invent content you did not hear:")
    # ── SHE IS TOLD ON THIS MOUTH TOO (2026-08-29 audit). The anon staple lived only
    # on the native chat path, so on a voice turn she could promise to remember a
    # private utterance: the writers refused and she was never told why — the exact
    # lie-by-omission the staple exists to prevent. Same one sentence, same source.
    try:
        from harness.control import anon as _anon_v
        _an = _anon_v.note()
        if _an:
            instr = instr + "\n\n" + _an
    except Exception as _swx:
        _swallowed(_swlog, "voice_turn", _swx, lane="voice")
    turn = list(transcript)
    turn.append({"role": "user", "content": instr})
    transcript.append({"role": "user", "content": "[voice message]"})

    from harness.inference.client import get_client
    client = get_client()
    if "inject_frames" not in getattr(client, "supports", {"inject_frames"}):
        # VOICE-IN IS RESIDUAL AUDIO FRAMES and a foreign endpoint has no door for them
        # (2026-08-21). Said once, as a reply, not as a crash. ASR-then-text is the
        # engine-agnostic path and is an OFF-BY-DEFAULT row until it is built.
        yield ev({"delta": "[voice-in is not available on this engine — speak to me in text]"})
        yield b"data: [DONE]\n\n"
        return
    # ── THROUGH THE ONE DOOR (2026-08-29 audit, D20-D23). This lane hand-built its
    # request and posted it raw, which made it a SECOND DOOR in five separate ways:
    # no system prefix (she was not herself on voice — no persona, no coda — and the
    # prompt shared nothing with the committed KV, evicting his conversation both
    # ways); no context.fit() (a long transcript walked into pmax and got the empty
    # 200); no byteexact resolution (the daemon default REFUSES on this MoE); a third
    # eot_bias literal; and no stripper but four regex literals, so [MOOD:] and
    # thought markers reached the screen and the TTS verbatim. sight.py was fixed for
    # exactly this class; this was the lane the fix did not reach. Now: one prefix
    # (system_bundle), one seam (to_sp_chat via chat_stream + extra), one ceiling
    # (fit inside chat_stream), one speech kernel (speech_delta) with _clean kept for
    # the audio-specific artifacts on top.
    try:
        from harness.agent import system_bundle
        _sysc, _ = system_bundle()
        msgs = [{"role": "system", "content": _sysc}] + turn
    except Exception:
        msgs = turn                        # a missing bundle must not cost the turn
    from harness.inference.inference_config import InferenceConfig
    cfg = InferenceConfig(
        temperature=float(body.get("temperature", 0.3)),
        repetition_penalty=1.15,
        # P1.5: double the ceiling — voice replies were truncating mid-sentence.
        max_tokens=int(body.get("max_tokens", 256)))
    _extra = {"inject_frames": [f.tolist() for f in frames], "inject_ph": VOICE_PH}
    if "eot_bias" in body:                 # an explicit caller value still wins
        _extra["eot_bias"] = float(body["eot_bias"])
    from harness.inference import stream_processor as _sp
    _pend: dict = {"buf": ""}          # the kernel's held-tail seed, as app.py seeds it
    reply_parts: list = []
    try:
        # speech_delta passes COMPLETE marks through on purpose (the room draws
        # chips from them); this client SPEAKS its deltas, so marks are stripped
        # here too — safe per-delta because the kernel already holds partial ones.
        for delta in client.chat_stream(messages=msgs, config=cfg, extra=_extra):
            reply_parts.append(delta)
            vis = _sp.speech_delta(_pend, delta)
            if vis:
                vis = _clean(_sp.strip_tags(vis))
                if vis.strip():
                    yield ev({"delta": vis})
        vis = _sp.speech_delta(_pend, "", flush=True)
        if vis:
            vis = _clean(_sp.strip_tags(vis))
            if vis.strip():
                yield ev({"delta": vis})
    except Exception as exc:
        yield ev({"delta": f"[voice turn error: {exc}]"})
    # strip_for_record, not just control surfaces: the session transcript is a
    # RECORD, and a [MOOD:] mark recorded as her words comes back as an example
    # of her own voice (the record-lane rule, applied to the third mouth).
    final = _clean(_sp.strip_for_record("".join(reply_parts))).strip()
    if final:
        transcript.append({"role": "assistant", "content": final})
    yield b"data: [DONE]\n\n"


_CTRL = None


def _clean(s: str) -> str:
    """Strip control-token artifacts that leak on the injected-frame path
    (<0x0D> CR bytes, stray fences, [audio] placeholders)."""
    global _CTRL
    if _CTRL is None:
        import re
        _CTRL = re.compile(r"<0x0[0-9A-Fa-f]>|```+|\[audio\]|<\|?audio\|?>")
    return _CTRL.sub("", s)


# (_raw_stream deleted 2026-08-29: chat_stream_raw never existed anywhere, so this
# urllib fallback WAS the lane — the hand-built second door D20 describes. The one
# client carries inject_frames via chat_stream(extra=...) now.)

