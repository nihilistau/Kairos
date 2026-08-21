"""
MCP Framework
============

The root state tree of the harness. A single :class:`MCPFramework` singleton
owns sessions, agents and a typed event bus. Ported (slimmed for general agent
use) from CosySim's MCPFramework — scene/character nodes generalize to
``AgentNode`` and ``SessionNode``.

All mutable harness state syncs here, so interceptors, skills and the server
share one consistent view.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class FrameworkEvent:
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = "framework"
    ts: float = field(default_factory=time.time)


class AgentNode:
    """Per-agent state: identity, current session, scratch state, inbox."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.current_session: Optional[str] = None
        self._state: Dict[str, Any] = {}
        self._inbox: List[Dict[str, Any]] = []

    def update_state(self, data: Dict[str, Any]) -> None:
        self._state.update(data)

    def get_state(self) -> Dict[str, Any]:
        return dict(self._state)

    def receive(self, message: Dict[str, Any]) -> None:
        self._inbox.append(message)

    def drain_inbox(self) -> List[Dict[str, Any]]:
        msgs, self._inbox = self._inbox, []
        return msgs

    def brief(self) -> str:
        return f"{self.agent_id} @ {self.current_session or '-'} ({len(self._inbox)} msgs)"


class SessionNode:
    """Per-session state: participants, turn log, arbitrary state, subscribers."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._present: set[str] = set()
        self._log: List[Dict[str, Any]] = []
        self._state: Dict[str, Any] = {}
        self._subscribers: List[Callable[[str, Dict[str, Any]], None]] = []

    def enter(self, agent_id: str) -> None:
        self._present.add(agent_id)

    def leave(self, agent_id: str) -> None:
        self._present.discard(agent_id)

    def present(self) -> List[str]:
        return sorted(self._present)

    def update_state(self, data: Dict[str, Any]) -> None:
        self._state.update(data)

    def get_state(self) -> Dict[str, Any]:
        return dict(self._state)

    def emit(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self._log.append({"type": event_type, "payload": payload or {}, "ts": time.time()})
        for cb in list(self._subscribers):
            try:
                cb(event_type, payload or {})
            except Exception:
                pass

    def subscribe(self, cb: Callable[[str, Dict[str, Any]], None]) -> None:
        self._subscribers.append(cb)

    def log(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._log[-limit:]


class MCPFramework:
    """Root singleton: agents, sessions, event bus, persistence.

    EMITS: FrameworkEvent to typed subscribers.
    """

    def __init__(self) -> None:
        self._agents: Dict[str, AgentNode] = {}
        self._sessions: Dict[str, SessionNode] = {}
        self._handlers: Dict[str, List[Callable[[FrameworkEvent], None]]] = {}
        self._turn = 0
        self._ready = False
        self._lock = threading.RLock()

    # ---- nodes ----------------------------------------------------------
    def get_agent(self, agent_id: str) -> AgentNode:
        with self._lock:
            if agent_id not in self._agents:
                self._agents[agent_id] = AgentNode(agent_id)
            return self._agents[agent_id]

    def get_session(self, session_id: str) -> SessionNode:
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionNode(session_id)
            return self._sessions[session_id]

    def send(self, to_agent: str, message: str, *, from_agent: str = "system",
             meta: Optional[Dict[str, Any]] = None) -> None:
        self.get_agent(to_agent).receive(
            {"from": from_agent, "message": message, "meta": meta or {}, "ts": time.time()})

    # ---- events ---------------------------------------------------------
    def on(self, event_type: str, cb: Callable[[FrameworkEvent], None]) -> None:
        self._handlers.setdefault(event_type, []).append(cb)

    def off(self, event_type: str, cb: Callable[[FrameworkEvent], None]) -> None:
        if event_type in self._handlers and cb in self._handlers[event_type]:
            self._handlers[event_type].remove(cb)

    def emit_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None,
                   source: str = "framework") -> FrameworkEvent:
        evt = FrameworkEvent(event_type, payload or {}, source)
        for cb in list(self._handlers.get(event_type, [])):
            try:
                cb(evt)
            except Exception:
                pass
        return evt

    def tick(self) -> int:
        with self._lock:
            self._turn += 1
        self.emit_event("tick", {"turn": self._turn})
        return self._turn

    def mark_ready(self) -> None:
        self._ready = True
        self.emit_event("framework_ready")

    # ---- persistence ----------------------------------------------------
    def save_state(self, path: str) -> str:
        data = {
            "turn": self._turn,
            "agents": {a: n.get_state() for a, n in self._agents.items()},
            "sessions": {s: n.get_state() for s, n in self._sessions.items()},
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        return path

    def load_state(self, path: str) -> bool:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return False
        self._turn = data.get("turn", 0)
        for a, st in data.get("agents", {}).items():
            self.get_agent(a).update_state(st)
        for s, st in data.get("sessions", {}).items():
            self.get_session(s).update_state(st)
        return True


_FRAMEWORK: Optional[MCPFramework] = None
_FW_LOCK = threading.Lock()


def get_framework() -> MCPFramework:
    global _FRAMEWORK
    if _FRAMEWORK is None:
        with _FW_LOCK:
            if _FRAMEWORK is None:
                _FRAMEWORK = MCPFramework()
    return _FRAMEWORK
