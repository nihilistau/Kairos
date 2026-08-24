"""Server — OpenAI-compatible SSE gateway over the Kairos daemon.

(`create_flask_app` left the exports 2026-08-24 — audit D1: a drifted, caller-less
twin of the stdlib server. `run()` is the one door.)"""

from harness.server.app import (
    run,
    stream_completion,
    blocking_completion,
)

__all__ = ["run", "stream_completion", "blocking_completion"]
