"""
Built-in Memory Skills
=====================

Thin skills that bridge the model to NEXUS knowledge management: search stored
knowledge and record new facts. These delegate to the Nexus client so the same
tools work whether Nexus is local-embedded or a remote KMS.
"""

from __future__ import annotations

from harness.skills.skill import skill, SkillCategory


@skill(pack="memory", category=SkillCategory.MEMORY,
       description="Search stored knowledge / memories for relevant entries.")
def search_memory(query: str, top_k: int = 5) -> str:
    """Semantic + keyword search over NEXUS."""
    from harness.nexus import get_query_router
    result = get_query_router().query(query)
    if not result.answer:
        return "(no relevant memory)"
    return f"[{result.source} @ {result.confidence:.2f}] {result.answer}"


@skill(pack="memory", category=SkillCategory.MEMORY,
       description="Store a new fact / note into NEXUS knowledge for later recall.")
def remember(title: str, content: str, category: str = "note") -> str:
    """Ingest a knowledge entry."""
    from harness.nexus import get_knowledge_pipeline
    res = get_knowledge_pipeline().ingest(title=title, content=content, category=category)
    if res.was_duplicate:
        return f"(already known: {title})"
    return f"stored '{title}' (id={res.entry_id}, quality={res.quality_score:.2f})"
