"""Namespaced smoke endpoint used for baseline bootstrap verification."""

from fastapi import APIRouter, Depends

from src.app_context import get_smoke_payload


router = APIRouter(prefix="/smoke", tags=["Smoke"])


@router.get("")
def get_smoke_status(payload: dict[str, str] = Depends(get_smoke_payload)):
    """Return a minimal payload proving the v1 routing stack is wired."""
    return payload
