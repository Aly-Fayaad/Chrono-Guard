"""Fixtures for mission-intelligence tests.

This file intentionally defines its own isolated in-memory database instead of
importing from ``backend/tests/conftest.py``. The mission tests must stay
runnable on their own and must never touch a real database file.
"""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

from app.core.database import build_engine, get_session
from app.main import create_app
from app.mission.followups import reset_follow_ups
from app.models import CrewProfile  # importing the package registers every table


@pytest.fixture()
def engine() -> Iterator[Engine]:
    """Create an isolated in-memory SQLite engine and dispose it afterwards."""
    db_engine = build_engine("sqlite://")
    SQLModel.metadata.create_all(db_engine)
    try:
        yield db_engine
    finally:
        db_engine.dispose()


@pytest.fixture()
def session(engine: Engine) -> Iterator[Session]:
    """Yield a session bound to the isolated test engine."""
    with Session(engine, expire_on_commit=False) as db_session:
        yield db_session


@pytest.fixture()
def session_factory(engine: Engine) -> Iterator[Callable[[], Session]]:
    """Return a session factory and close any session left open at teardown."""
    sessions: list[Session] = []

    def make_session() -> Session:
        db_session = Session(engine, expire_on_commit=False)
        sessions.append(db_session)
        return db_session

    try:
        yield make_session
    finally:
        for db_session in sessions:
            db_session.close()


@pytest.fixture()
def client(
    engine: Engine, session_factory: Callable[[], Session]
) -> Iterator[TestClient]:
    """Create an app with the mission router and a test-engine session."""
    reset_follow_ups()
    app = create_app(engine)

    def override_session() -> Iterator[Session]:
        with session_factory() as db_session:
            yield db_session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        reset_follow_ups()


@pytest.fixture()
def crew_id(session: Session) -> str:
    """Insert and return one crew member used by the mission tests."""
    session.add(
        CrewProfile(
            id="crew-mission",
            display_name="Mission Test Crew",
            role="commander",
            sleep_target_hours=7.5,
        )
    )
    session.commit()
    return "crew-mission"
