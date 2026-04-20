"""Operational health endpoint."""

from sqlalchemy import text

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.connectors.azure_openai_connector import AzureOpenAIConnector
from src.database import get_engine


router = APIRouter(tags=["Health"])


@router.get("/health", include_in_schema=False)
def health_check():
    """Return service liveness status."""
    return {"status": "ok", "service": "rfq_chatbot_ms"}


@router.get("/ready", include_in_schema=False)
def readiness_check():
    """Return service readiness based on DB and Azure OpenAI configuration checks."""

    db_ready = True
    azure_ready = True

    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        db_ready = False

    try:
        AzureOpenAIConnector().assert_ready()
    except Exception:
        azure_ready = False

    if db_ready and azure_ready:
        return {
            "status": "ready",
            "service": "rfq_chatbot_ms",
            "checks": {"database": "ok", "azure_openai": "ok"},
        }

    return JSONResponse(
        status_code=503,
        content={
            "status": "not_ready",
            "service": "rfq_chatbot_ms",
            "checks": {
                "database": "ok" if db_ready else "error",
                "azure_openai": "ok" if azure_ready else "error",
            },
        },
    )

