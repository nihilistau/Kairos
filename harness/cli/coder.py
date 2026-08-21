"""
CLI Coding Interface
==================

An interactive coding agent driven by the harness: the model runs an ephemeral
tool-calling loop over the built-in ``coder`` skill pack (read/write/search/run
in a sandboxed workspace). This is the harness's analogue of a CLI coding
assistant — built entirely on Kairos inference, no external model API.

Run::

    python -m harness.cli coder            # interactive REPL
    python -m harness.cli coder "task..."  # one-shot task
"""

from __future__ import annotations

import sys
from typing import List, Optional

from harness.inference import InferenceConfig
from harness.toolcore.tools import get_tool_registry, run_with_tools
from harness.observability import get_logger

logger = get_logger(__name__)

_SYSTEM = (
    "You are a coding assistant operating inside a sandboxed workspace. "
    "Use the available tools to inspect and modify files. Think step by step, "
    "make minimal correct edits, and verify your work by reading back or running "
    "commands. When the task is complete, summarize what you changed."
)


def _build_tools():
    reg = get_tool_registry()
    reg.load_from_skills(pack="coder")
    return reg.specs()


def run_task(task: str, *, max_rounds: int = 12, config: Optional[InferenceConfig] = None) -> str:
    """Run one coding task to completion and return the final answer."""
    tools = _build_tools()
    messages = [{"role": "user", "content": task}]
    cfg = config or InferenceConfig(temperature=0.2, max_tokens=1024)

    def _on_tool(name: str, args: dict, result: str) -> None:
        preview = result.replace("\n", " ")[:120]
        print(f"  \033[2m· {name}({args}) -> {preview}\033[0m", file=sys.stderr)

    return run_with_tools(
        [{"role": "system", "content": _SYSTEM}] + messages,
        tools,
        config=cfg,
        max_rounds=max_rounds,
        on_tool=_on_tool,
    )


def repl() -> None:
    """Interactive coding REPL."""
    print("kairos-harness coder — type a task, Ctrl-D to exit.\n")
    while True:
        try:
            task = input("\033[1mcoder>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not task:
            continue
        try:
            answer = run_task(task)
            print(f"\n{answer}\n")
        except Exception as exc:
            logger.error("[coder] task failed (operation=run_task): %s", exc)
            print(f"error: {exc}\n")


def main(argv: List[str]) -> int:
    if argv:
        print(run_task(" ".join(argv)))
    else:
        repl()
    return 0
