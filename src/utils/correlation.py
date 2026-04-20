"""Request-scoped correlation id utilities."""

from __future__ import annotations

import re
from contextvars import ContextVar
from uuid import uuid4


correlation_id_context: ContextVar[str] = ContextVar("correlation_id", default="-")

_VALID_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def get_correlation_id() -> str:
    """Return the current request correlation id from context storage."""

    return correlation_id_context.get()


def resolve_correlation_id(
    incoming_correlation_id: str | None,
    incoming_request_id: str | None,
) -> str:
    """Resolve a safe correlation id from incoming headers or generate one."""

    candidate = (incoming_correlation_id or "").strip() or (incoming_request_id or "").strip()
    if candidate and _VALID_CORRELATION_ID.match(candidate):
        return candidate
    return str(uuid4())
