"""Shared pytest fixtures with an isolated in-memory SQLite database."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from app.core.database import build_engine, get_session
from app.main import create_app
from app.models import CrewProfile


@pytest.fixture()
def engine():
    """Create an isolated in-memory database engine."""
    db_engine = build_engine("sqlite://")
    SQLModel.metadata.create_all(db_engine)
    return db_engine


@pytest.fixture()
def session_factory(engine) -> Callable[[], Session]:
    """Return a factory for sessions bound to the test engine."""

    def make_session() -> Session:
        return Session(engine, expire_on_commit=False)

    return make_session


@pytest.fixture()
def crew_id(session_factory: Callable[[], Session]) -> str:
    """Insert one test crew member."""
    with session_factory() as session:
        session.add(
            CrewProfile(id="crew-test", display_name="Test Crew", role="commander")
        )
        session.commit()
    return "crew-test"


@pytest.fixture()
def client(engine, session_factory: Callable[[], Session]) -> Iterator[TestClient]:
    """Create an app with the database dependency pointed at the test engine."""
    app = create_app(engine)

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
