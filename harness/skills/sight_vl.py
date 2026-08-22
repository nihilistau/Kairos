"""sight_vl — her eyes through the librarians' door (2026-08-22, sub-project E).

An LFM2.5-VL GGUF served by LM Studio on the aux chat door takes an `image_url` part and
answers in words. This module is the transport for `sight.backend == "aux_vl"`: it never
post-processes — `sight._scrub` does, the same for every backend — and it never arms itself:
`sight._describe` decides the route, `sight.sight_tools()` decides the arming.
"""
from __future__ import annotations

import base64
import io
from typing import Optional


def vl_model() -> str:
    from harness.tuning import registry as _tr
    return str(_tr.tune_or_env("sight.vl_model", "SP_AUX_VL_MODEL", "") or "")


def vl_max_tokens() -> int:
    try:
        from harness.tuning import registry as _tr
        return int(_tr.get("sight.vl_max_tokens", 220) or 220)
    except Exception:
        return 220


def vl_detail() -> str:
    try:
        from harness.tuning import registry as _tr
        return str(_tr.get("sight.vl_detail", "auto") or "auto")
    except Exception:
        return "auto"


def door_up() -> bool:
    try:
        from harness.sidecar import client
        return client.available() and client.reachable("chat")
    except Exception:
        return False


def armed() -> bool:
    """A VL door makes her sighted on a model that is not: backend chosen, model chosen, door armed."""
    try:
        from harness.tuning import registry as _tr
        from harness.sidecar import client
        return (str(_tr.get("sight.backend", "engine")) == "aux_vl" and bool(vl_model())
                and client.available())
    except Exception:
        return False


def vl_choices() -> list:
    """The picker's choices: the door's VL/vision model ids, plus the profile default."""
    try:
        from harness.sidecar import client
        ids = [m for m in client.list_models() if "vl" in m.lower() or "vision" in m.lower()]
    except Exception:
        ids = []
    cur = vl_model()
    return sorted(set(ids + ([cur] if cur else [])))


def _data_url(img) -> str:
    from PIL import Image as _PIL
    buf = io.BytesIO()
    _PIL.fromarray(img).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def describe(img, question: str, model: str = "", max_tokens: Optional[int] = None,
             detail: str = "auto") -> str:
    """pixels + a question -> the VL door's words, RAW ('' when dark). sight._scrub follows."""
    from harness.sidecar import client
    part = {"type": "image_url", "image_url": {"url": _data_url(img)}}
    if detail and detail != "auto":
        part["image_url"]["detail"] = detail
    msgs = [{"role": "user", "content": [{"type": "text", "text": question}, part]}]
    return client.chat(msgs, max_tokens=int(max_tokens or vl_max_tokens()), temperature=0.3,
                       model=model or vl_model())


def eyes_status() -> dict:
    """For the senses window and its chip."""
    try:
        from harness.tuning import registry as _tr
        backend = str(_tr.get("sight.backend", "engine") or "engine")
    except Exception:
        backend = "engine"
    return {"backend": backend, "vl_model": vl_model(),
            "door_up": door_up() if backend == "aux_vl" else None, "vl_armed": armed()}
