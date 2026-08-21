"""
Inference Router
================

Priority-aware front door to inference. Ported (slimmed) from CosySim's
3-tier router. The harness typically serves a single big resident model
(Gemma-4-12B) so tiers collapse to a priority queue + optional draft/small
model affinity, but the seam is kept so additional daemons can be bound later.
"""

from __future__ import annotations

import logging
import queue
import threading
from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Callable, Dict, Optional

from harness.inference.client import SPDaemonClient, get_client
from harness.inference.inference_config import InferenceConfig

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    REALTIME = 0      # interactive turn, user is waiting
    INTERACTIVE = 1
    BACKGROUND = 2    # autonomous / ambient
    BATCH = 3         # analytics, bulk


class Tier(Enum):
    PRIMARY = "primary"     # the big resident model
    DRAFT = "draft"         # speculative / small helper


@dataclass
class InferenceRequest:
    priority: Priority = Priority.INTERACTIVE
    tier: Optional[Tier] = None
    agent_id: str = ""
    prompt: Optional[str] = None
    messages: Optional[list] = None
    config: Optional[InferenceConfig] = None
    on_delta: Optional[Callable[[str], None]] = None
    _seq: int = field(default=0, compare=False)


class InferenceRouter:
    """Single-worker priority queue over one or more daemon clients.

    CONNECTS: SPDaemonClient
    CALLED BY: InferenceOrchestrator
    """

    def __init__(self) -> None:
        self._clients: Dict[Tier, SPDaemonClient] = {}
        self._q: "queue.PriorityQueue" = queue.PriorityQueue()
        self._worker: Optional[threading.Thread] = None
        self._running = False
        self._seq = 0
        self._lock = threading.Lock()

    def bind(self, tier: Tier, client: SPDaemonClient) -> None:
        self._clients[tier] = client

    def _client_for(self, req: InferenceRequest) -> SPDaemonClient:
        tier = req.tier or Tier.PRIMARY
        return self._clients.get(tier) or self._clients.get(Tier.PRIMARY) or get_client()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._loop, daemon=True, name="inference-router")
        self._worker.start()

    def stop(self) -> None:
        self._running = False

    def submit(self, req: InferenceRequest) -> "Future":
        self.start()
        fut: Future = Future()
        with self._lock:
            self._seq += 1
            req._seq = self._seq
        # PriorityQueue orders by (priority, seq) for FIFO within a priority.
        self._q.put((int(req.priority), req._seq, req, fut))
        return fut

    def submit_sync(self, req: InferenceRequest, timeout: float = 120.0) -> Any:
        return self.submit(req).result(timeout=timeout)

    def _loop(self) -> None:
        while self._running:
            try:
                _, _, req, fut = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                client = self._client_for(req)
                gen = client.chat_stream(
                    prompt=req.prompt,
                    messages=req.messages,
                    config=req.config,
                    on_event=None,
                )
                if req.on_delta:
                    parts = []
                    for d in gen:
                        parts.append(d)
                        req.on_delta(d)
                    try:
                        next(gen)
                    except StopIteration as stop:
                        fut.set_result(stop.value)
                else:
                    # drain to completion
                    try:
                        while True:
                            next(gen)
                    except StopIteration as stop:
                        fut.set_result(stop.value)
            except Exception as exc:  # surface to the Future
                logger.error("[InferenceRouter] request failed (operation=submit, agent=%s): %s", req.agent_id, exc)
                fut.set_exception(exc)


_ROUTER: Optional[InferenceRouter] = None


def get_router() -> InferenceRouter:
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = InferenceRouter()
        _ROUTER.bind(Tier.PRIMARY, get_client())
    return _ROUTER
