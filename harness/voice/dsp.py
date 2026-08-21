"""Log-mel front-end — numpy-only, LIFTED VERBATIM from the KAI-3 trainer
(engine tools/audio_port/gen_audio_frames.py) so live features bit-match the
features the GNA ear was trained on. Do not "improve" the filterbank: the
bin-floor triangles and the n_fft//2 center padding are the trained contract.

    16 kHz mono f32 → pad n_fft//2 both sides → frames n_fft=1024, hop=640
    (40 ms = the EAR stride), Hann → |rfft|^2 → fb(64 mels, fmin=20, fmax=8k,
    HTK mel, bin-index triangles) → log(. + 1e-6)
"""
from __future__ import annotations

import numpy as np

SR = 16_000
N_FFT = 1024
HOP = 640          # 40 ms @ 16 kHz — the EAR frame stride
N_MELS = 64


def mel_filterbank(sr: int = SR, n_fft: int = N_FFT, n_mels: int = N_MELS,
                   fmin: float = 20.0, fmax: float | None = None) -> np.ndarray:
    # VERBATIM from gen_audio_frames.py (KAI-3 trained contract).
    fmax = fmax or sr / 2
    hz2mel = lambda f: 2595.0 * np.log10(1 + f / 700.0)   # noqa: E731
    mel2hz = lambda m: 700.0 * (10 ** (m / 2595.0) - 1)   # noqa: E731
    m = np.linspace(hz2mel(fmin), hz2mel(fmax), n_mels + 2)
    bins = np.floor((n_fft + 1) * mel2hz(m) / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1), np.float32)
    for i in range(1, n_mels + 1):
        l, c, r = bins[i - 1], bins[i], bins[i + 1]
        if c == l:
            c = l + 1
        if r == c:
            r = c + 1
        fb[i - 1, l:c] = (np.arange(l, c) - l) / max(c - l, 1)
        fb[i - 1, c:r] = (r - np.arange(c, r)) / max(r - c, 1)
    return fb


_fb_cache: np.ndarray | None = None


def logmel(x: np.ndarray, sr: int = SR, hop: int = HOP, n_fft: int = N_FFT,
           n_mels: int = N_MELS) -> np.ndarray:
    """f32 mono 16k [-1,1] → log-mel [T, n_mels]. VERBATIM trainer math."""
    global _fb_cache
    x = np.asarray(x, dtype=np.float32)
    win = np.hanning(n_fft).astype(np.float32)
    if _fb_cache is None:
        _fb_cache = mel_filterbank(sr, n_fft, n_mels)
    fb = _fb_cache
    pad = n_fft // 2
    xp = np.pad(x, (pad, pad))
    frames = 1 + (len(xp) - n_fft) // hop
    out = np.empty((max(frames, 0), n_mels), np.float32)
    for t in range(frames):
        seg = xp[t * hop: t * hop + n_fft] * win
        spec = np.abs(np.fft.rfft(seg)) ** 2
        out[t] = np.log(fb @ spec + 1e-6)
    return out


def pcm16_to_f32(raw: bytes) -> np.ndarray:
    """little-endian int16 PCM → f32 [-1,1]."""
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def rms_energy(pcm: np.ndarray, win: int = HOP) -> np.ndarray:
    """per-40ms-frame RMS — the server-side VAD guard (client VADs too)."""
    n = pcm.size // win
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    return np.sqrt((pcm[: n * win].reshape(n, win) ** 2).mean(axis=1))
