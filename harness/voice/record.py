"""record.py — save REAL microphone training samples (ADR-KAI4 P1.6).

The console capture panel POSTs {text, audio_b64 (PCM16 mono 16k)} per spoken
sentence; we save a 16k wav under var/voice/real/ and append a manifest line.
tools/voice_frames_real.py then folds these REAL samples (heavily upweighted)
into the CTC bake so the ear learns the operator's actual voice/mic/room — the
true fix for the SAPI->real domain gap.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import wave

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REAL_DIR = os.path.join(_ROOT, "var", "voice", "real")
MANIFEST = os.path.join(REAL_DIR, "manifest.jsonl")


def save_recording(text: str, audio_b64: str) -> dict:
    text = (text or "").strip().lower()
    if not text:
        return {"ok": False, "error": "empty text"}
    try:
        pcm = base64.b64decode(audio_b64)
    except Exception as exc:
        return {"ok": False, "error": f"bad audio_b64: {exc}"}
    if len(pcm) < 3200:                       # < 0.1s @16k16bit
        return {"ok": False, "error": "utterance too short"}
    os.makedirs(REAL_DIR, exist_ok=True)
    h = hashlib.sha1((text + str(time.time())).encode()).hexdigest()[:12]
    name = f"r_{h}.wav"
    path = os.path.join(REAL_DIR, name)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)
    with open(MANIFEST, "a", encoding="utf-8") as f:
        f.write(json.dumps({"wav": name, "text": text,
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ")}) + "\n")
    n = sum(1 for _ in open(MANIFEST, encoding="utf-8"))
    return {"ok": True, "saved": name, "total": n, "seconds": round(len(pcm) / 32000, 2)}


def record_status() -> dict:
    if not os.path.isfile(MANIFEST):
        return {"total": 0, "dir": REAL_DIR}
    rows = [json.loads(l) for l in open(MANIFEST, encoding="utf-8") if l.strip()]
    from collections import Counter
    return {"total": len(rows), "distinct_sentences": len({r["text"] for r in rows}),
            "dir": REAL_DIR}
