"""Database engine, UTC datetime handling, and schema bootstrap."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Enum as SAEnum,
    TypeDecorator,
    create_engine,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect, Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

FALLBACK_SQLITE_URL = "sqlite:///./chronoguard.db"


class UTCDateTime(TypeDecorator):
    """Store UTC and return timezone-aware UTC datetimes.

    PostgreSQL uses ``TIMESTAMP WITH TIME ZONE``. SQLite has no native
    timezone-aware type, so it stores naive UTC and the decorator re-attaches
    UTC when reading. This keeps the API contract identical on both backends.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        """Normalise values to UTC before storage."""
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        if dialect.name == "postgresql":
            return value
        # SQLite's DateTime binding is happier with naive UTC.
        return value.replace(tzinfo=None)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        """Attach UTC to naive values read from SQLite."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


#: JSON on SQLite, JSONB on PostgreSQL. The Python contract is identical.
JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def to_utc(value: datetime) -> datetime:
    """Treat naive datetimes as UTC and convert aware datetimes to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def new_id() -> str:
    """Generate a server-side string primary key."""
    return uuid4().hex


def _normalise_url(url: str) -> str:
    """Use psycopg 3 for plain PostgreSQL URLs and ensure default port if omitted."""
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]

    if url.startswith("postgresql+psycopg://"):
        try:
            parsed = urlparse(url)
            if parsed.hostname and not parsed.port:
                user_info = ""
                if parsed.username:
                    user_info = parsed.username
                    if parsed.password:
                        user_info += f":{parsed.password}"
                    user_info += "@"
                new_netloc = f"{user_info}{parsed.hostname}:5432"
                parsed = parsed._replace(netloc=new_netloc)
                url = urlunparse(parsed)
        except Exception:
            pass
    return url


def build_engine(url: str, connect_timeout: int = 10) -> Engine:
    """Create a production-ready engine for SQLite or PostgreSQL."""
    normalised = _normalise_url(url)
    if not normalised.startswith("sqlite"):
        db_engine = create_engine(
            normalised,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_recycle=300,
            connect_args={"connect_timeout": connect_timeout},
        )
        return db_engine

    options: dict[str, object] = {"connect_args": {"check_same_thread": False}}
    if normalised == "sqlite://" or ":memory:" in normalised:
        options["poolclass"] = StaticPool
    db_engine = create_engine(normalised, **options)

    @event.listens_for(db_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        """Enable FK enforcement so SQLite behaves like PostgreSQL."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return db_engine


engine = build_engine(settings.DATABASE_URL)
_active_engine: Engine = engine


def get_engine() -> Engine:
    """Return the currently active engine."""
    return _active_engine


def set_engine(new_engine: Engine) -> None:
    """Set the active engine globally."""
    global _active_engine, engine
    _active_engine = new_engine
    engine = new_engine


def _sync_postgres_enum_values(db_engine: Engine) -> None:
    """Add newly introduced enum members to existing PostgreSQL enum types.

    ``create_all`` creates enum types on a fresh database but never alters an
    existing type. This small additive step keeps old databases compatible when
    an enum gains a member (for example the ``hrv`` measurement type).
    """
    if db_engine.dialect.name != "postgresql":
        return

    specs: dict[str, list[str]] = {}
    for table in SQLModel.metadata.tables.values():
        for column in table.columns:
            column_type = column.type
            if isinstance(column_type, SAEnum) and column_type.name:
                specs[column_type.name] = list(column_type.enums)

    with db_engine.begin() as connection:
        for name, values in specs.items():
            exists = connection.execute(
                text("SELECT 1 FROM pg_type WHERE typname = :name"), {"name": name}
            ).first()
            if not exists:
                continue
            for value in values:
                escaped = value.replace("'", "''")
                connection.execute(
                    text(
                        f'ALTER TYPE "{name}" ADD VALUE IF NOT EXISTS \'{escaped}\''
                    )
                )


def _ensure_default_crew_seeded(db_engine: Engine) -> None:
    """Auto-seed default crew on empty local SQLite so frontend has immediate data."""
    try:
        # Never auto-seed in-memory test databases
        url_str = str(db_engine.url)
        if url_str in ("sqlite://", "sqlite:///:memory:") or ":memory:" in url_str:
            return

        from sqlmodel import select
        from app.models.crew import CrewProfile

        with Session(db_engine) as session:
            has_crew = session.exec(select(CrewProfile)).first() is not None
            if not has_crew:
                from app.seed.demo_data import seed_scenario
                seed_scenario(session, "normal_routine", reset=False)
                logger.info("Auto-seeded demo crew into local database.")
    except Exception as exc:
        logger.debug("Auto-seeding skipped: %s", exc)


def init_db(db_engine: Engine | None = None) -> Engine:
    """Create all registered tables and reconcile enum members.

    Handles connectivity resilience:
    - In dev mode (ENV != 'production'), if connecting to remote PostgreSQL fails
      due to timeout or network issues, seamlessly falls back to local SQLite so
      local development and offline work remain unblocked.
    - In production (ENV == 'production'), retries with backoff and raises detailed
      diagnostics if the database remains unreachable.
    """
    from app import models  # noqa: F401

    active = db_engine or get_engine()
    is_prod = settings.ENV.lower() in {"prod", "production"}

    # For PostgreSQL engines, verify connectivity before running DDL
    if active.dialect.name == "postgresql":
        max_attempts = 3 if is_prod else 1
        connected = False
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                with active.connect() as conn:
                    conn.execute(text("SELECT 1"))
                connected = True
                break
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts:
                    logger.warning(
                        "Database connection attempt %d/%d failed; retrying in %ds...",
                        attempt,
                        max_attempts,
                        attempt * 2,
                    )
                    time.sleep(attempt * 2)

        if not connected:
            if is_prod:
                logger.error(
                    "CRITICAL: Failed to connect to production PostgreSQL database: %s",
                    last_error,
                )
                raise last_error  # type: ignore[misc]

            logger.warning(
                "Could not connect to PostgreSQL database (%s). "
                "Falling back to local SQLite (%s) for development.",
                last_error,
                FALLBACK_SQLITE_URL,
            )
            active = build_engine(FALLBACK_SQLITE_URL)
            set_engine(active)

    try:
        SQLModel.metadata.create_all(active)
        _sync_postgres_enum_values(active)
    except Exception as exc:
        if not is_prod and active.dialect.name == "postgresql":
            logger.warning(
                "Schema creation on PostgreSQL failed (%s). "
                "Falling back to local SQLite (%s) for development.",
                exc,
                FALLBACK_SQLITE_URL,
            )
            active = build_engine(FALLBACK_SQLITE_URL)
            set_engine(active)
            SQLModel.metadata.create_all(active)
        else:
            raise

    if active.dialect.name == "sqlite" and not is_prod:
        _ensure_default_crew_seeded(active)

    return active


def get_session() -> Iterator[Session]:
    """Yield a synchronous database session bound to the active engine."""
    with Session(get_engine(), expire_on_commit=False) as session:
        yield session
