"""Operational health endpoint."""

from fastapi import APIRouter


router = APIRouter(tags=["Health"])


@router.get("/health", include_in_schema=False)
def health_check():
    """Return service liveness status."""
    return {"status": "ok", "service": "rfq_chatbot_ms"}

