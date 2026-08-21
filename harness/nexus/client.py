"""
NEXUS Client
===========

Knowledge-management client. Two modes behind one interface:

* **embedded** (default): an in-process SQLite store with vector search — the
  harness runs out of the box, no external service.
* **remote**: an HTTP client to a Nexus KMS (e.g. CosySim's KMS on :8700) when
  ``NEXUS_URL`` is set.

Ported (slimmed) from CosySim's NexusClient; the public surface (``search``,
``add_entry``, ``add_qa``, ``ask``) matches so downstream code is unchanged.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.nexus.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)


@dataclass
class NexusEntry:
    id: str
    title: str
    content: str
    content_type: str = "note"
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    created_by: str = "harness"
    score: float = 0.0

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class _EmbeddedStore:
    """SQLite-backed knowledge store with in-memory vector index."""

    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS entries("
            "id TEXT PRIMARY KEY, title TEXT, content TEXT, content_type TEXT, "
            "category TEXT, tags TEXT, created_by TEXT, embedding TEXT, ts REAL)"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS qa(id TEXT PRIMARY KEY, question TEXT, "
            "answer TEXT, category TEXT, embedding TEXT, ts REAL)"
        )
        self._db.commit()
        self._lock = threading.Lock()
        self._embed = get_embedding_service()

    def add_entry(self, entry: NexusEntry) -> str:
        emb = json.dumps(self._embed.embed(f"{entry.title}\n{entry.content}"))
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO entries VALUES(?,?,?,?,?,?,?,?,?)",
                (entry.id, entry.title, entry.content, entry.content_type,
                 entry.category, json.dumps(entry.tags), entry.created_by, emb, time.time()),
            )
            self._db.commit()
        return entry.id

    def add_qa(self, qa_id: str, question: str, answer: str, category: str = "") -> str:
        emb = json.dumps(self._embed.embed(question))
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO qa VALUES(?,?,?,?,?,?)",
                             (qa_id, question, answer, category, emb, time.time()))
            self._db.commit()
        return qa_id

    def search(self, query: str, limit: int = 10) -> List[NexusEntry]:
        qv = self._embed.embed(query)
        rows = self._db.execute(
            "SELECT id,title,content,content_type,category,tags,created_by,embedding FROM entries"
        ).fetchall()
        scored = []
        for r in rows:
            ev = json.loads(r[7]) if r[7] else []
            score = self._embed.similarity(qv, ev) if ev else 0.0
            scored.append(NexusEntry(r[0], r[1], r[2], r[3], r[4],
                                     json.loads(r[5] or "[]"), r[6], score))
        scored.sort(key=lambda e: e.score, reverse=True)
        return scored[:limit]

    def find_qa(self, question: str, limit: int = 3) -> List[Dict[str, Any]]:
        qv = self._embed.embed(question)
        rows = self._db.execute("SELECT question,answer,embedding FROM qa").fetchall()
        scored = []
        for q, a, emb in rows:
            ev = json.loads(emb) if emb else []
            scored.append((self._embed.similarity(qv, ev) if ev else 0.0, q, a))
        scored.sort(reverse=True)
        return [{"question": q, "answer": a, "score": s} for s, q, a in scored[:limit]]


class NexusClient:
    """Public KMS surface. Embedded by default; remote when NEXUS_URL is set."""

    def __init__(self, base_url: str = "", db_path: str = "data/nexus.db") -> None:
        self.base_url = base_url or os.environ.get("NEXUS_URL", "")
        self._http = None
        self._store: Optional[_EmbeddedStore] = None
        if self.base_url:
            try:
                import httpx
                self._http = httpx.Client(timeout=30.0)
            except Exception:
                logger.warning("[NexusClient] httpx missing; falling back to embedded store")
                self.base_url = ""
        if not self.base_url:
            self._store = _EmbeddedStore(db_path)

    def search(self, query: str, limit: int = 10) -> List[NexusEntry]:
        if self._http:
            try:
                r = self._http.get(f"{self.base_url}/search", params={"q": query, "limit": limit})
                return [NexusEntry(**e) for e in r.json().get("results", [])]
            except Exception as exc:
                logger.error("[NexusClient] remote search failed (operation=search): %s", exc)
                return []
        return self._store.search(query, limit)  # type: ignore[union-attr]

    def add_entry(self, title: str, content: str, content_type: str = "note",
                  category: str = "general", tags: Optional[List[str]] = None,
                  created_by: str = "harness") -> Optional[str]:
        import uuid
        entry = NexusEntry(uuid.uuid4().hex[:12], title, content, content_type,
                           category, list(tags or []), created_by)
        if self._http:
            try:
                r = self._http.post(f"{self.base_url}/entries", json=entry.__dict__)
                return r.json().get("id")
            except Exception as exc:
                logger.error("[NexusClient] remote add_entry failed (operation=add): %s", exc)
                return None
        return self._store.add_entry(entry)  # type: ignore[union-attr]

    def add_qa(self, question: str, answer: str, category: str = "") -> Optional[str]:
        import uuid
        qa_id = uuid.uuid4().hex[:12]
        if self._http:
            try:
                self._http.post(f"{self.base_url}/qa",
                                json={"question": question, "answer": answer, "category": category})
                return qa_id
            except Exception:
                return None
        return self._store.add_qa(qa_id, question, answer, category)  # type: ignore[union-attr]

    def find_qa(self, question: str, limit: int = 3) -> List[Dict[str, Any]]:
        if self._http:
            try:
                return self._http.get(f"{self.base_url}/qa",
                                      params={"q": question, "limit": limit}).json().get("results", [])
            except Exception:
                return []
        return self._store.find_qa(question, limit)  # type: ignore[union-attr]


_CLIENT: Optional[NexusClient] = None


def get_nexus_client(base_url: str = "") -> NexusClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = NexusClient(base_url)
    return _CLIENT
