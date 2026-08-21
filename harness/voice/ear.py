"""The GNA EAR — live inference wrapper around the PROVEN KAI-3 artifacts.

Pipeline (all constants inherited from the gated KAI-3 lane):
    log-mel [T,64] → OpenVINO IR (POT i16, GNA-legal: pad=0, head padded to 36ch)
    → logits [T', 36] → slice [:V+1=33] → CTC-greedy collapse (blank=32)
    → for each kept frame: softmax(logits[:32]/τ=0.2) @ W_sub → [E=3840]
    → k×E on-manifold residual frames for the daemon's inject_frames channel.

Device ladder: GNA_HW (the silicon, gated 0.877) → GNA_SW → CPU (same IR).
Artifacts (var/voice/): ear IR (pot .xml/.bin) + wsub.npz (W_sub, vsub_ids, tau)
— produced once by tools/voice_export_wsub.py + copied from _xbar/p2b/kai3.
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VOICE_DIR = os.environ.get("SP_VOICE_DIR", os.path.join(_ROOT, "var", "voice"))
# newest ear first: the P1 conversational IR (voice_ctc), else the gated KAI-3 POT IR.
_CANDIDATE_IRS = ("voice_ctc.xml", "audio_ctc_pot_gna.xml")
IR_XML = next((os.path.join(VOICE_DIR, n) for n in _CANDIDATE_IRS
               if os.path.isfile(os.path.join(VOICE_DIR, n))),
              os.path.join(VOICE_DIR, _CANDIDATE_IRS[0]))
WSUB_NPZ = os.path.join(VOICE_DIR, "wsub.npz")

_state: dict = {}


class EarUnavailable(RuntimeError):
    pass


def _load() -> dict:
    if _state:
        return _state
    if not os.path.isfile(WSUB_NPZ):
        raise EarUnavailable(
            f"missing {WSUB_NPZ} — run tools/voice_export_wsub.py once (see ADR-KAI4 P0)")
    z = np.load(WSUB_NPZ)
    _state["wsub"] = z["wsub"].astype(np.float32)        # [V, E] (×√H-scaled embed rows)
    _state["tau"] = float(z["tau"]) if "tau" in z else 0.2
    _state["V"] = int(_state["wsub"].shape[0])
    _state["E"] = int(_state["wsub"].shape[1])

    if not os.path.isfile(IR_XML):
        raise EarUnavailable(
            f"missing {IR_XML} — copy _xbar/p2b/kai3/ov_work/pot/audio_ctc_pot_gna.xml/.bin "
            f"into {VOICE_DIR}")
    try:
        import openvino as ov
    except ImportError as exc:
        raise EarUnavailable(
            "openvino not installed (pip install openvino==2023.3.0 — the GNA-capable LTS)"
        ) from exc
    core = ov.Core()
    devices = core.available_devices
    _state["compiled"] = None
    for dev in ("GNA", "CPU"):  # 'GNA' resolves to GNA_HW when the driver is live
        if any(d.startswith(dev) for d in devices):
            try:
                model = core.read_model(IR_XML)
                _state["compiled"] = core.compile_model(model, dev)
                _state["device"] = dev
                break
            except Exception:
                continue
    if _state["compiled"] is None:
        raise EarUnavailable(f"no usable OV device (available: {devices})")
    inp = _state["compiled"].input(0)
    _state["in_shape"] = list(inp.get_shape())            # static (GNA requirement)
    return _state


def status() -> dict:
    try:
        s = _load()
        return {"ok": True, "device": s["device"], "V": s["V"], "E": s["E"],
                "in_shape": s["in_shape"]}
    except EarUnavailable as exc:
        return {"ok": False, "error": str(exc)}


def hear(mel: np.ndarray) -> np.ndarray:
    """log-mel [T,64] → on-manifold residual frames [k, E] (k=0 when nothing legible)."""
    s = _load()
    compiled, tau, wsub, v = s["compiled"], s["tau"], s["wsub"], s["V"]

    # fit the GNA static input: shapes are [1, Tm, 64] (or [1, 64, Tm]); pad/trim T.
    shape = s["in_shape"]
    t_axis = 1 if shape[-1] == 64 else 2
    tm = shape[t_axis]
    T = mel.shape[0]
    if T < tm:
        mel_fit = np.pad(mel, ((0, tm - T), (0, 0)))
    else:
        mel_fit = mel[:tm]
    x = mel_fit[None, ...] if t_axis == 1 else mel_fit.T[None, ...]

    out = compiled(x.astype(np.float32))
    logits = np.asarray(list(out.values())[0]).squeeze(0)  # [T', 36] or [36, T']
    if logits.shape[0] == 36 or (logits.ndim == 2 and logits.shape[0] < logits.shape[1]
                                 and logits.shape[0] in (33, 36)):
        logits = logits.T
    logits = logits[:, : v + 1]                            # drop the ch÷4 pad → [T', 33]
    valid = min(T, logits.shape[0])
    logits = logits[:valid]

    # CTC-greedy collapse: drop blanks + repeats, keep the frame logits at kept steps.
    ids = logits.argmax(axis=-1)
    kept = []
    prev = -1
    for t, i in enumerate(ids):
        if i != v and i != prev:
            kept.append(t)
        prev = i
    if not kept:
        return np.zeros((0, s["E"]), dtype=np.float32)

    # HARD-SELECT the argmax embed row per kept frame (KAI-4 P1 fix): at V=217 the
    # softmax(τ=0.2) blend is too soft — injecting a blurry mix of embed rows is
    # harder for the 12B to read than the EXACT row it was trained on. os.environ
    # SP_VOICE_SOFT=1 restores the soft blend (KAI-3 V=32 behaviour).
    if os.environ.get("SP_VOICE_SOFT") == "1":
        lg = logits[kept, :v] / tau
        lg -= lg.max(axis=-1, keepdims=True)
        p = np.exp(lg)
        p /= p.sum(axis=-1, keepdims=True)
        return (p @ wsub).astype(np.float32)               # [k, E] soft blend
    sel = logits[kept, :v].argmax(axis=-1)                 # per-frame token index
    return wsub[sel].astype(np.float32)                    # [k, E] exact embed rows
