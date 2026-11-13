"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from app.core.config import get_settings
from app.core.database import engine as default_engine
from app.core.database import init_db
from app.routers import ROUTERS
from app.services.analysis import load_engine
from app.services.validation import ValidationFailure


def create_app(db_engine: Engine | None = None) -> FastAPI:
    """Build the application with CORS, schema startup, and all routers."""
    settings = get_settings()
    active_engine = db_engine or default_engine

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db(active_engine)
        app.state.db_engine = active_engine
        app.state.analysis_engine = load_engine(settings.ANALYSIS_ENGINE)
        yield

    app = FastAPI(
        title="Lunar Crew Health Companion",
        version="1.0.0",
        description="Synthetic health check-ins, mission tasks, and read-only assessments.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ValidationFailure)
    async def handle_validation_failure(
        request: Request, exc: ValidationFailure
    ) -> JSONResponse:
        """Return 422 for hard plausibility or cross-field violations."""
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    for router in ROUTERS:
        app.include_router(router, prefix="/api/v1")

    @app.get("/health", response_model=dict[str, str])
    @app.get("/api/v1/health", response_model=dict[str, str])
    def health() -> dict[str, str]:
        """Liveness probe with the active environment."""
        return {"status": "ok", "env": settings.ENV}

    return app


app = create_app()
