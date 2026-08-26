"""harness.senses — what she can take in: sound, sight, the screen.

One rule organises this package, and it is the lesson of 2026-07-31:

    A SENSE ANSWERS TO THE MODEL THAT IS ACTUALLY SERVED.

`capability.py` rules from a committed table on what the live checkpoint can
receive, and every encoder asks it before producing a single frame. An encoder
whose projection is the wrong width for the served model REFUSES. That is not
defensive coding; it is the fix for a real defect in which a retired model's audio
projection survived a swap to a 26B that has no audio path at all, and neither
the harness nor the daemon noticed, because each checked only that the frames
agreed with THEMSELVES.

Fail closed, always. No sense is better than a false one — the absent sense gets
noticed and the false one gets believed.

    capability.py  what the served model can receive (the committed table)
    gguf.py        minimal read-only GGUF reader, numpy only
    vision.py      the model's own ViT, in numpy (UNARMED — see G-SIGHT)
    capture.py     webcam, screen, files (no hard dependencies)
"""
from __future__ import annotations

from harness.senses.capability import Capability, SenseRefused, for_model, status

__all__ = ["Capability", "SenseRefused", "for_model", "status"]
