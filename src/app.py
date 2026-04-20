"""FastAPI application bootstrap for rfq_chatbot_ms."""

import logging
import time

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config.settings import get_settings
from src.utils.correlation import (
    correlation_id_context,
    get_correlation_id,
    resolve_correlation_id,
)
from src.utils.errors import AppError
from src.utils.logging import configure_json_logging


logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = get_settings()
    configure_json_logging()

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

    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        correlation_id = resolve_correlation_id(
            request.headers.get("X-Correlation-ID"),
            request.headers.get("X-Request-ID"),
        )
        request.state.correlation_id = correlation_id
        token = correlation_id_context.set(correlation_id)
        started_at = time.perf_counter()
        response = None
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "request_complete method=%s path=%s status_code=%s duration_ms=%.2f",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            correlation_id_context.reset(token)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        error_msgs = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err["loc"])
            error_msgs.append(f"{loc}: {err['msg']}")
        correlation_id = getattr(request.state, "correlation_id", get_correlation_id())
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation failed: " + " | ".join(error_msgs)},
            headers={"X-Correlation-ID": correlation_id},
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        correlation_id = getattr(request.state, "correlation_id", get_correlation_id())
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
            headers={"X-Correlation-ID": correlation_id},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception during request", exc_info=exc)
        correlation_id = getattr(request.state, "correlation_id", get_correlation_id())
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
            headers={"X-Correlation-ID": correlation_id},
        )

    from src.routes.health_route import router as health_router
    from src.routes.metrics_route import router as metrics_router
    from src.routes.chat_routes import router as chat_router
    from src.routes.session_routes import router as session_router
    from src.routes.smoke_route import router as smoke_router

    app.include_router(health_router)
    app.include_router(metrics_router)

    v1 = APIRouter(prefix="/rfq-chatbot/v1")
    v1.include_router(smoke_router)
    v1.include_router(session_router)
    v1.include_router(chat_router)
    app.include_router(v1)

    return app


app = create_app()
