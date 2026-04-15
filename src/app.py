"""FastAPI application bootstrap for rfq_chatbot_ms."""

import logging

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config.settings import get_settings
from src.utils.errors import AppError


logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = get_settings()

    app = FastAPI(
        title="rfq_chatbot_ms",
        version="0.1.0",
        description="RFQ chatbot service with the Phase 4 typed retrieval baseline.",
    )

    origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        error_msgs = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err["loc"])
            error_msgs.append(f"{loc}: {err['msg']}")
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation failed: " + " | ".join(error_msgs)},
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception during request", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    from src.routes.health_route import router as health_router
    from src.routes.chat_routes import router as chat_router
    from src.routes.session_routes import router as session_router
    from src.routes.smoke_route import router as smoke_router

    app.include_router(health_router)

    v1 = APIRouter(prefix="/rfq-chatbot/v1")
    v1.include_router(smoke_router)
    v1.include_router(session_router)
    v1.include_router(chat_router)
    app.include_router(v1)

    return app


app = create_app()
