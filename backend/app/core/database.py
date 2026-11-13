from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, TypeDecorator, create_engine
from sqlalchemy.engine import Dialect, Engine
from sqlmodel import Session
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.core.config import get_settings

settings = get_settings()


class UTCDateTime(TypeDecorator):
    """Persist naive UTC and return timezone-aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """Normalise values to naive UTC for storage."""
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """Attach UTC to datetimes read from the database."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


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


def build_engine(url: str) -> Engine:
    """Create an engine, using a shared in-memory pool for SQLite test URLs."""
    if not url.startswith("sqlite"):
        return create_engine(url)
    options: dict[str, object] = {"connect_args": {"check_same_thread": False}}
    if url == "sqlite://" or ":memory:" in url:
        options["poolclass"] = StaticPool
    return create_engine(url, **options)


engine = build_engine(settings.DATABASE_URL)


def init_db(db_engine: Engine | None = None) -> None:
    """Create all tables registered on SQLModel metadata."""
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(db_engine or engine)


def get_session() -> Iterator[Session]:
    """Yield a synchronous database session."""
    with Session(engine, expire_on_commit=False) as session:
        yield session
