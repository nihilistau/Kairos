"""KAI-4 LATENT VOICE (ADR-KAI4, P0).

The sovereign voice pipeline: mic PCM → log-mel → the PROVEN GNA ear (KAI-3 CTC
encoder, POT i16, gated on physical GNA 2.0 silicon) → on-manifold [k×E] residual
frames → the daemon's inject_frames voice channel (audio placeholder 258881).

Modules:
  dsp.py      — log-mel front-end, numpy-only, BIT-MATCHED to gen_audio_frames.py
                (n_fft=1024, hop=640 = 40ms @16k, n_mels=64, fmin=20, fmax=8k)
  ear.py      — the ear: OpenVINO IR (GNA_HW → GNA_SW → CPU fallback) or numpy
                fallback; CTC-greedy collapse + softmax(τ)·W_sub projection
  service.py  — the /v1/voice glue used by the gateway

One-time artifact export (WSL, torch): tools/voice_export_wsub.py → var/voice/wsub.npz
IR artifacts: copied from _xbar/p2b/kai3/ov_work/pot/ → var/voice/ (frozen, POT i16).
"""
