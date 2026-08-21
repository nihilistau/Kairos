"""
Server Controller
=================

Owns the lifecycle of the Kairos ``sp-daemon`` subprocess: launch with
the right backend env, health-poll, and shutdown. The harness analogue of
CosySim's ``ServerController`` / ``LMStudioManager`` — but instead of driving
the ``lms`` CLI it spawns the native daemon binary.

The daemon is a long-lived resident process holding the model + KV cache in
VRAM; the harness owns exactly one per model.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from harness.inference.client import SPDaemonClient

logger = logging.getLogger(__name__)


@dataclass
class DaemonSpec:
    """How to launch one daemon instance."""

    model: str
    tokenizer: str
    port: int = 3000
    host: str = "127.0.0.1"
    binary: str = "sp-daemon"
    backend: str = "cuda"           # cuda | cpu | hex | vulkan
    kvdecode: bool = True           # required for the 12B resident decode
    decode_int8: bool = True        # tied full-vocab head materialization
    recall_registry: str = ""       # SP_RECALL_REGISTRY (autonomous recall)
    wc_head: str = ""               # SP_B3_WC deploy blob
    extra_env: Dict[str, str] = field(default_factory=dict)

    def env(self) -> Dict[str, str]:
        e = dict(os.environ)
        e["SP_DAEMON_BACKEND"] = self.backend
        if self.kvdecode:
            e["SP_DAEMON_KVDECODE"] = "1"
        if self.decode_int8:
            e["SP_CUDA_DECODE_INT8"] = "1"
        if self.recall_registry:
            e["SP_RECALL_REGISTRY"] = self.recall_registry
        if self.wc_head:
            e["SP_B3_WC"] = self.wc_head
        e.update(self.extra_env)
        return e

    def argv(self) -> List[str]:
        return [
            self.binary, "start",
            "--model", self.model,
            "--tokenizer", self.tokenizer,
            "--port", str(self.port),
        ]


class ServerController:
    """Launch / monitor / stop a single sp-daemon.

    CONNECTS: SPDaemonClient
    EMITS: process lifecycle log lines (Oracle format)
    """

    def __init__(self, spec: DaemonSpec) -> None:
        self.spec = spec
        self.proc: Optional[subprocess.Popen] = None
        self.client = SPDaemonClient(f"http://{spec.host}:{spec.port}")

    def available(self) -> bool:
        """True if the daemon binary is resolvable on PATH."""
        return shutil.which(self.spec.binary) is not None or Path(self.spec.binary).exists()

    def start(self, *, wait_ready: float = 120.0) -> bool:
        """Spawn the daemon and block until it is health-ready (or timeout)."""
        if self.client.health():
            logger.info("[ServerController] daemon already live on :%d (operation=start)", self.spec.port)
            return True
        if not self.available():
            logger.error("[ServerController] binary not found (operation=start): %s", self.spec.binary)
            return False
        logger.info("[ServerController] launching daemon (operation=start, backend=%s)", self.spec.backend)
        self.proc = subprocess.Popen(self.spec.argv(), env=self.spec.env())
        deadline = time.time() + wait_ready
        while time.time() < deadline:
            if self.client.health():
                logger.info("[ServerController] daemon ready (operation=start, port=%d)", self.spec.port)
                return True
            if self.proc.poll() is not None:
                logger.error("[ServerController] daemon exited early (operation=start, rc=%s)", self.proc.returncode)
                return False
            time.sleep(1.0)
        logger.error("[ServerController] daemon not ready in %.0fs (operation=start)", wait_ready)
        return False

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            logger.info("[ServerController] stopping daemon (operation=stop)")
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
