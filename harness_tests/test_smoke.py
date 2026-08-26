"""
Smoke tests — import surface + offline functional paths.

These run with zero third-party deps and without a live sp-daemon. They cover:
the skill registry, the governor (bare — the interceptor pipeline was deleted
2026-08-25, see the note below), the NEXUS embedded store, ephemeral tool-call
parsing, the SSE gateway formatting, and stream-tag extraction.
"""

from __future__ import annotations

import os
import tempfile

import pytest


def test_top_level_imports():
    import harness
    from harness import (
        get_framework, get_governor, skill, get_skill_registry, run_with_tools,
        get_client, get_nexus_client,
    )
    assert harness.__version__


def test_skill_registry_has_builtins():
    from harness.skills import get_skill_registry
    reg = get_skill_registry()
    assert "coder" in reg.all_packs()
    assert "memory" in reg.all_packs()
    assert reg.get_skill("read_file") is not None
    assert len(reg.schemas()) >= 5


def test_skill_schema_shape():
    from harness.skills import get_skill_registry
    schemas = get_skill_registry().schemas(names=["write_file"])
    assert schemas[0]["function"]["name"] == "write_file"
    props = schemas[0]["function"]["parameters"]["properties"]
    assert "path" in props and "content" in props


def test_nexus_embedded_ingest_and_search(tmp_path):
    os.environ["HARNESS_WORKSPACE"] = str(tmp_path)
    from harness.nexus import get_knowledge_pipeline, get_nexus_client
    res = get_knowledge_pipeline().ingest(
        title="Byte-exact forward",
        content="The exact-integer islands make the gemma4 forward bit-deterministic across machines.",
    )
    assert res.success and res.embedded and res.entry_id
    hits = get_nexus_client().search("deterministic forward")
    assert hits and hits[0].title == "Byte-exact forward"


# test_interceptor_pipeline_shapes_reply WAS HERE — DELETED WITH ITS SUBJECT (2026-08-25).
# harness/interceptors/ (build_pipeline + the four CosySim-ported stages, including
# PersonalityStateInterceptor, a complete second authority over persona.md) had NO live
# consumer: this test was the only caller of build_pipeline in the tree, so it was a
# green suite over code no live path could reach — AGENTS.md §0's quiet sibling. The
# live authorities the stages duplicated: persona tags persist through
# spine.py::persona_shift -> apply_personality_tags (gate: h_personality_tags), reply
# stripping through inference/stream_processor. git history keeps the pipeline; the
# OFF-BY-DEFAULT §10 row records the deletion and what would justify a rebuild.


def test_governor_reply_passthrough():
    """The governor itself (toolcore) is still importable and replies with an EMPTY
    pipeline — what remains after the dead interceptor package was removed."""
    from harness.toolcore import get_governor

    class FakeAgent:
        agent_id = "t"
        name = "T"
        system_prompt = "base"

        def reply(self, msg, system_prompt="", messages=None):
            return "Answer."

    gov = get_governor(FakeAgent())
    assert gov.reply("hi") == "Answer."


def test_ephemeral_tool_call_parsing():
    from harness.toolcore.tools import _TOOL_RE
    text = 'ok <tool name="search">{"pattern": "TODO"}</tool>'
    calls = _TOOL_RE.findall(text)
    assert calls == [("search", '{"pattern": "TODO"}')]


def test_sse_gateway_chunk_format():
    from harness.server.app import _chunk
    chunk = _chunk("hello", "legacy-ref-b1")
    assert chunk.startswith("data: ")
    assert "chat.completion.chunk" in chunk


def test_stream_processor_tag_extraction():
    from harness.inference import StreamProcessor

    def gen():
        yield "Hi "
        yield "[MOOD:calm]"
        yield "there"
        yield "[STAT:trust+3]"

    pr = StreamProcessor.process_generator(gen())
    assert pr.clean_text == "Hi there"
    assert pr.mood_tags == ["calm"]
    assert pr.stat_deltas[0].stat == "trust" and pr.stat_deltas[0].delta == 3.0


def test_inference_config_to_sp_chat():
    from harness.inference import InferenceConfig
    cfg = InferenceConfig(temperature=0.7, max_tokens=128, byteexact=True)
    body = cfg.to_sp_chat(prompt="hello")
    assert body["prompt"] == "hello"
    assert body["temperature"] == 0.7
    assert body["max_tokens"] == 128
    assert body["byteexact"] is True


def test_control_plane_targets():
    from harness.control import autostart_targets, get_port
    names = [t.name for t in autostart_targets()]
    assert "sp_daemon" in names
    assert get_port("gateway") == 8800
