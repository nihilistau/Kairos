"""Observability — the Oracle: structured logging + error aggregation."""

from harness.observability.oracle import (
    get_logger,
    get_error_aggregator,
    ensure_initialized,
    diagnose,
    ErrorAggregator,
)

__all__ = [
    "get_logger",
    "get_error_aggregator",
    "ensure_initialized",
    "diagnose",
    "ErrorAggregator",
]
