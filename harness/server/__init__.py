"""Server — OpenAI-compatible SSE gateway over the Kairos daemon."""

from harness.server.app import (
    run,
    create_flask_app,
    stream_completion,
    blocking_completion,
)

__all__ = ["run", "create_flask_app", "stream_completion", "blocking_completion"]
