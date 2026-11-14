"""Database engine, UTC datetime handling, and schema bootstrap."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
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

settings = get_settings()


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
    """Use psycopg 3 for plain PostgreSQL URLs."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def build_engine(url: str) -> Engine:
    """Create a production-ready engine for SQLite or PostgreSQL."""
    normalised = _normalise_url(url)
    if not normalised.startswith("sqlite"):
        db_engine = create_engine(
            normalised,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_recycle=1800,
            connect_args={"connect_timeout": 10},
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


def init_db(db_engine: Engine | None = None) -> None:
    """Create all registered tables and reconcile enum members."""
    from app import models  # noqa: F401

    active = db_engine or engine
    SQLModel.metadata.create_all(active)
    _sync_postgres_enum_values(active)


def get_session() -> Iterator[Session]:
    """Yield a synchronous database session."""
    with Session(engine, expire_on_commit=False) as session:
        yield session
