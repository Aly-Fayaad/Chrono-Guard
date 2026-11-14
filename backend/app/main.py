"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import Engine
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.database import engine as default_engine
from app.core.database import init_db
from app.core.errors import (
    domain_validation_response,
    request_validation_response,
    validation_response,
)
from app.routers import ROUTERS
from app.services.analysis import load_engine
from app.services.validation import ValidationFailure

logger = logging.getLogger(__name__)


def create_app(db_engine: Engine | None = None) -> FastAPI:
    """Build the application with CORS, schema startup, and all routers."""
    settings = get_settings()
    active_engine = db_engine or default_engine

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        active_db_engine = init_db(active_engine)
        app.state.db_engine = active_db_engine
        app.state.analysis_engine = load_engine(settings.ANALYSIS_ENGINE)
        yield

    app = FastAPI(
        title="Lunar Crew Health Companion",
        version="1.1.0",
        description="Synthetic health check-ins, mission tasks, and read-only assessments.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        # The API currently uses no browser cookies. Keeping credentials off
        # avoids needlessly broad cross-origin authority.
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Total-Count", "X-Request-ID"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        """Attach a request id so frontend and backend logs can be correlated."""
        supplied_request_id = request.headers.get("X-Request-ID")
        request_id = supplied_request_id if supplied_request_id and len(supplied_request_id) <= 128 else uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """Log internal failures without exposing implementation details to clients."""
        logger.exception("Unhandled request failure", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.exception_handler(ValidationFailure)
    async def handle_validation_failure(
        request: Request, exc: ValidationFailure
    ) -> JSONResponse:
        """Return the unified 422 shape for domain validation failures."""
        return domain_validation_response(str(exc))

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Return only the stable loc/msg/type fields for Pydantic errors."""
        return request_validation_response(exc)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Keep 422 responses in the unified shape and preserve other errors."""
        if exc.status_code == 422:
            if isinstance(exc.detail, list):
                return validation_response(exc.detail)
            return domain_validation_response(str(exc.detail))
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    for router in ROUTERS:
        app.include_router(router, prefix="/api/v1")

    @app.get("/health", response_model=dict[str, str])
    @app.get("/api/v1/health", response_model=dict[str, str])
    def health() -> dict[str, str]:
        """Liveness probe with the active environment."""
        return {"status": "ok", "env": settings.ENV}

    @app.get("/health/ready", response_model=dict[str, str])
    @app.get("/api/v1/health/ready", response_model=dict[str, str])
    def readiness() -> JSONResponse:
        """Readiness probe that verifies the database connection."""
        curr_engine = getattr(app.state, "db_engine", None) or active_engine
        try:
            with curr_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 - report readiness, never crash the probe
            logger.exception("Database readiness check failed")
            return JSONResponse(
                status_code=503,
                content={"status": "error", "database": "unavailable", "env": settings.ENV},
            )
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "database": "ok",
                "dialect": curr_engine.dialect.name,
                "env": settings.ENV,
            },
        )

    return app


app = create_app()
