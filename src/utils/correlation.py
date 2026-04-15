"""
utils/correlation.py
Request correlation ID infrastructure using contextvars.

Provides a ContextVar that holds the current request's correlation ID,
accessible from any point in the call stack without threading issues.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

# Holds the correlation ID for the current request context
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="no-request")


def get_correlation_id() -> str:
    """Return the correlation ID for the current async/thread context."""
    return _correlation_id.get()


def set_correlation_id(value: str) -> None:
    """Set the correlation ID for the current async/thread context."""
    _correlation_id.set(value)


def generate_correlation_id() -> str:
    """Generate a new UUID4 correlation ID."""
    return uuid.uuid4().hex[:12]
