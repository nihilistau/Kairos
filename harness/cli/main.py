"""
Unified CLI
==========

``harness <command> [args]`` — the single entry point. Mirrors CosySim's
``cli.py`` dispatch pattern.

Commands:
    ask "<prompt>"     One-shot generation via the daemon.
    coder ["<task>"]   Interactive / one-shot coding agent (ephemeral tools).
    serve              Start the OpenAI-compatible SSE gateway.
    daemon             Launch / health-check the sp-daemon.
    nexus <sub>        Knowledge: search / add / ask.
    oracle             Print observability diagnostics.
    skills             List registered skills.
"""

from __future__ import annotations

import argparse
import sys
from typing import List

from harness.observability import ensure_initialized


def _cmd_ask(args: List[str]) -> int:
    from harness.inference import get_client, InferenceConfig
    prompt = " ".join(args) or sys.stdin.read()
    client = get_client()
    for delta in client.chat_stream(prompt=prompt, config=InferenceConfig(max_tokens=512)):
        sys.stdout.write(delta)
        sys.stdout.flush()
    print()
    return 0


def _cmd_coder(args: List[str]) -> int:
    from harness.cli import coder
    return coder.main(args)


def _cmd_serve(args: List[str]) -> int:
    from harness.server import run
    from harness.control import get_port
    p = argparse.ArgumentParser(prog="harness serve")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=get_port("gateway"))
    ns = p.parse_args(args)
    run(host=ns.host, port=ns.port)
    return 0


def _cmd_daemon(args: List[str]) -> int:
    from harness.inference import ServerController, DaemonSpec
    p = argparse.ArgumentParser(prog="harness daemon")
    p.add_argument("--model", required=False, default="")
    p.add_argument("--tokenizer", required=False, default="")
    p.add_argument("--port", type=int, default=3000)
    p.add_argument("--health", action="store_true", help="only health-check")
    ns = p.parse_args(args)
    spec = DaemonSpec(model=ns.model, tokenizer=ns.tokenizer, port=ns.port)
    ctrl = ServerController(spec)
    if ns.health:
        print("daemon healthy" if ctrl.client.health() else "daemon DOWN")
        return 0 if ctrl.client.health() else 1
    return 0 if ctrl.start() else 1


def _cmd_nexus(args: List[str]) -> int:
    from harness.nexus import get_nexus_client, get_knowledge_pipeline, get_query_router
    if not args:
        print("usage: harness nexus {search|add|ask} ...")
        return 2
    sub, rest = args[0], args[1:]
    if sub == "search":
        for e in get_nexus_client().search(" ".join(rest)):
            print(f"[{e.score:.2f}] {e.title}: {e.content[:80]}")
    elif sub == "add":
        title = rest[0] if rest else "untitled"
        content = " ".join(rest[1:])
        res = get_knowledge_pipeline().ingest(title=title, content=content)
        print(f"stored id={res.entry_id} dup={res.was_duplicate}")
    elif sub == "ask":
        res = get_query_router().query(" ".join(rest))
        print(f"[{res.source} @ {res.confidence:.2f}] {res.answer or '(no answer)'}")
    else:
        print(f"unknown nexus subcommand: {sub}")
        return 2
    return 0


def _cmd_oracle(args: List[str]) -> int:
    from harness.observability import diagnose
    diagnose()
    return 0


def _cmd_skills(args: List[str]) -> int:
    from harness.skills import get_skill_registry
    for pack, metas in get_skill_registry().describe().items():
        print(f"\n# {pack}")
        for m in metas:
            print(f"  {m['name']:<16} {m['description']}")
    return 0


_COMMANDS = {
    "ask": _cmd_ask,
    "coder": _cmd_coder,
    "serve": _cmd_serve,
    "daemon": _cmd_daemon,
    "nexus": _cmd_nexus,
    "oracle": _cmd_oracle,
    "skills": _cmd_skills,
}


def main(argv: List[str] | None = None) -> int:
    ensure_initialized()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    fn = _COMMANDS.get(cmd)
    if fn is None:
        print(f"unknown command: {cmd}\n{__doc__}")
        return 2
    return fn(rest)


if __name__ == "__main__":
    sys.exit(main())
