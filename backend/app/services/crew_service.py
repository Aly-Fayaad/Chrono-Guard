"""Crew lifecycle business logic."""

from __future__ import annotations

from sqlalchemy import delete, func
from sqlmodel import Session, select

from app.core.database import new_id
from app.models.assessment import Assessment
from app.models.checkin import CheckIn, HealthMeasurement, SleepRecord
from app.models.crew import CrewProfile
from app.models.guidance import ActionHistory
from app.models.mission import MissionTask
from app.schemas.crew import CrewCreate


class CrewAlreadyExists(ValueError):
    """Raised when a requested crew slug is already in use."""


def create_crew(session: Session, payload: CrewCreate) -> CrewProfile:
    """Create a crew member, optionally with a caller-supplied slug."""
    crew_id = payload.id or new_id()
    if session.get(CrewProfile, crew_id) is not None:
        raise CrewAlreadyExists(f"crew id '{crew_id}' already exists")
    crew = CrewProfile(
        id=crew_id,
        display_name=payload.display_name,
        role=payload.role,
        sleep_target_hours=payload.sleep_target_hours,
    )
    session.add(crew)
    session.commit()
    session.refresh(crew)
    return crew


def delete_crew(session: Session, crew_id: str) -> dict[str, int] | None:
    """Delete a crew member and every dependent row in one transaction.

    The explicit child-first order works on SQLite (where historical schemas
    did not declare cascades) and on PostgreSQL. The whole operation commits
    once, so a failure leaves the crew and its data untouched.
    """
    crew = session.get(CrewProfile, crew_id)
    if crew is None:
        return None

    counts: dict[str, int] = {}
    # Child-first order. Action history references assessments; assessments
    # and measurements reference check-ins.
    for model in (
        ActionHistory,
        Assessment,
        SleepRecord,
        HealthMeasurement,
        CheckIn,
        MissionTask,
    ):
        table = model.__tablename__
        counts[table] = int(
            session.exec(
                select(func.count()).select_from(model).where(model.crew_id == crew_id)
            ).one()
        )
        session.execute(delete(model).where(model.crew_id == crew_id))

    session.delete(crew)
    session.commit()
    return counts
