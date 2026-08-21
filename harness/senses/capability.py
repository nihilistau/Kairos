"""capability.py — WHAT THE SERVED MODEL CAN ACTUALLY RECEIVE.

THE RULING COMES FROM A COMMITTED TABLE (`config/model_capability.json`) AND FROM
NOTHING ELSE. A model that is not in the table has no senses. This is the same
discipline the verdict layer already uses for memory: rulings are lookups in
committed finite tables, never magnitudes and never prose.

THE BUG THIS EXISTS TO PREVENT (found 2026-07-31, live):

    var/voice/embed_audio.npz is [3840, 640], extracted from gemma4-12b.
    The served your model has hidden size 2816 and `audio_config: null` —
    no audio embedder anywhere in the checkpoint.

    harness/voice/native.py:83 produced 3840-wide frames anyway. Nothing caught
    it. native.py never compared E against the served model; the daemon
    (routes.rs:2255) took `e_dim` from `frames[0].len()` and only checked the
    batch was SELF-consistent — its comment says "each must be E floats", but E
    was never checked against the model. A model swap moved the hidden dim and
    the sense carried on with weights belonging to a different network.

So: every encoder in `harness/senses/` asks this module first, and an encoder
whose projection disagrees with `e` REFUSES rather than injects. A sense that is
silently wrong is worse than a sense that is absent, because the absent one gets
noticed. Fail closed.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TABLE = os.environ.get("SP_CAPABILITY_TABLE",
                       os.path.join(_ROOT, "config", "model_capability.json"))

_CACHE: dict[str, "Capability"] = {}


class SenseRefused(RuntimeError):
    """An encoder declined to produce frames. Carries the reason, verbatim, for the
    operator — these are the messages that make an absent sense visible."""


@dataclass(frozen=True)
class Capability:
    """What one model can receive. `audio`/`vision` are None when the model lacks
    that sense entirely — which is a fact about the checkpoint, not a config gap."""
    tag: str
    e: int
    audio: Optional[dict]
    vision: Optional[dict]
    audio_absent_reason: str = ""
    known: bool = True

    # ── the two questions every encoder asks ────────────────────────────────
    def require(self, sense: str) -> dict:
        """Return the sense's spec, or raise with a reason worth reading."""
        if not self.known:
            raise SenseRefused(
                f"model '{self.tag}' is not in {os.path.basename(TABLE)}; senses are "
                f"refused for unlisted models. Add it (with its hidden size and token "
                f"ids read from the model's own config.json) to arm them.")
        spec = getattr(self, sense, None)
        if spec is None:
            why = self.audio_absent_reason if sense == "audio" else ""
            raise SenseRefused(
                f"model '{self.tag}' has no {sense} path." + (f" {why}" if why else ""))
        return spec

    def assert_width(self, sense: str, width: int) -> None:
        """THE CHECK THAT WAS MISSING. A projection whose output width disagrees with
        the served model's hidden size is weights from another network."""
        if width != self.e:
            raise SenseRefused(
                f"{sense} projection produces {width}-wide frames but model "
                f"'{self.tag}' has hidden size {self.e}. These weights belong to a "
                f"different model — refusing to inject. (This is the 2026-07-31 "
                f"defect: a 12B projection surviving a swap to the model.)")


def _load_table() -> dict[str, Any]:
    try:
        with open(TABLE, "r", encoding="utf-8") as f:
            return json.load(f).get("models", {})
    except FileNotFoundError:
        return {}


def model_tag(model_path: str | None = None) -> str:
    """The table's key: the stem of the served model path.
    '.../your model.sp-model' -> 'your model'."""
    p = model_path or os.environ.get("SP_MODEL_PATH", "")
    if not p:
        return ""
    return os.path.splitext(os.path.basename(p))[0]


def for_model(model_path: str | None = None) -> Capability:
    """Capability of the model currently served. Unlisted => known=False, no senses."""
    tag = model_tag(model_path)
    if tag in _CACHE:
        return _CACHE[tag]
    models = _load_table()
    row = models.get(tag)
    # one level of aliasing, so q4b/reason variants of a checkpoint need no duplicate
    seen = {tag}
    while isinstance(row, dict) and "alias_of" in row:
        nxt = row["alias_of"]
        if nxt in seen:           # a cycle is a table bug; treat as unlisted
            row = None
            break
        seen.add(nxt)
        row = models.get(nxt)
    if not isinstance(row, dict):
        cap = Capability(tag=tag or "<unset SP_MODEL_PATH>", e=0, audio=None,
                         vision=None, known=False)
    else:
        cap = Capability(
            tag=tag,
            e=int(row.get("e", 0)),
            audio=row.get("audio"),
            vision=row.get("vision"),
            audio_absent_reason=row.get("audio_absent_reason", ""),
        )
    _CACHE[tag] = cap
    return cap


def status() -> dict:
    """Operator-facing summary — what she can hear and see on THIS model."""
    c = for_model()
    return {
        "model": c.tag,
        "known": c.known,
        "hidden_size": c.e,
        "hearing": bool(c.audio),
        "sight": bool(c.vision),
        "why_no_hearing": c.audio_absent_reason if not c.audio else "",
        "table": TABLE,
    }


def reset_cache() -> None:
    """Tests and knob flips only — the served model does not change mid-process."""
    _CACHE.clear()
