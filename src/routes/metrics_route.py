"""Prometheus metrics endpoint."""

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from fastapi import APIRouter, Response


router = APIRouter(tags=["Metrics"])


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    """Return Prometheus text exposition for service metrics."""

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
