"""Read helpers shared by routers, Person 3, and Person 4."""

from datetime import datetime, timedelta

from sqlalchemy import func
from sqlmodel import Session
from sqlmodel import select

from app.core.database import to_utc, utcnow
from app.models.assessment import Assessment
from app.models.checkin import HealthMeasurement, SleepRecord
from app.models.crew import CrewProfile
from app.models.enums import MeasurementType, QualityFlag
from app.models.mission import MissionTask


def get_crew(session: Session, crew_id: str) -> CrewProfile | None:
    """Return a crew profile by id."""
    return session.get(CrewProfile, crew_id)


def _measurement_statement(
    crew_id: str,
    types: list[MeasurementType] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    valid_only: bool = False,
):
    """Build the shared measurement filter statement."""
    statement = select(HealthMeasurement).where(HealthMeasurement.crew_id == crew_id)
    if types:
        statement = statement.where(HealthMeasurement.type.in_(types))
    if since is not None:
        statement = statement.where(HealthMeasurement.recorded_at >= to_utc(since))
    if until is not None:
        statement = statement.where(HealthMeasurement.recorded_at <= to_utc(until))
    if valid_only:
        statement = statement.where(HealthMeasurement.quality == QualityFlag.valid)
    return statement


def get_measurements(
    session: Session,
    crew_id: str,
    types: list[MeasurementType] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    valid_only: bool = False,
    limit: int | None = None,
) -> list[HealthMeasurement]:
    """Return measurements newest first, optionally filtered."""
    statement = _measurement_statement(crew_id, types, since, until, valid_only)
    statement = statement.order_by(
        HealthMeasurement.recorded_at.desc(), HealthMeasurement.id.desc()
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.exec(statement).all())


def count_measurements(
    session: Session,
    crew_id: str,
    types: list[MeasurementType] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    valid_only: bool = False,
) -> int:
    """Count measurements matching the same filters as ``get_measurements``."""
    statement = _measurement_statement(crew_id, types, since, until, valid_only)
    count_statement = select(func.count()).select_from(statement.subquery())
    return int(session.exec(count_statement).one())


def _sleep_statement(
    crew_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
    valid_only: bool = False,
):
    """Build the shared sleep filter statement."""
    statement = select(SleepRecord).where(SleepRecord.crew_id == crew_id)
    if since is not None:
        statement = statement.where(SleepRecord.sleep_start >= to_utc(since))
    if until is not None:
        statement = statement.where(SleepRecord.sleep_start <= to_utc(until))
    if valid_only:
        statement = statement.where(SleepRecord.quality == QualityFlag.valid)
    return statement


def get_sleep_records(
    session: Session,
    crew_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
    valid_only: bool = False,
    limit: int | None = None,
) -> list[SleepRecord]:
    """Return sleep records newest first, optionally filtered."""
    statement = _sleep_statement(crew_id, since, until, valid_only)
    statement = statement.order_by(
        SleepRecord.sleep_start.desc(), SleepRecord.id.desc()
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.exec(statement).all())


def count_sleep_records(
    session: Session,
    crew_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
    valid_only: bool = False,
) -> int:
    """Count sleep records matching the same filters as ``get_sleep_records``."""
    statement = _sleep_statement(crew_id, since, until, valid_only)
    count_statement = select(func.count()).select_from(statement.subquery())
    return int(session.exec(count_statement).one())


def get_upcoming_tasks(
    session: Session,
    crew_id: str,
    from_time: datetime | None = None,
    horizon_hours: int = 72,
) -> list[MissionTask]:
    """Return tasks overlapping the upcoming horizon, earliest first.

    The default horizon is 72 hours. The HTTP ``/missions?upcoming=true`` route
    intentionally has different semantics: without ``horizon_hours`` it returns
    all future tasks. Callers that need the 72-hour planning window should use
    this helper (or pass ``horizon_hours`` to the route).
    """
    start = to_utc(from_time) if from_time is not None else utcnow()
    end = start + timedelta(hours=horizon_hours)
    statement = (
        select(MissionTask)
        .where(
            MissionTask.crew_id == crew_id,
            MissionTask.start_time < end,
            MissionTask.end_time > start,
        )
        .order_by(MissionTask.start_time, MissionTask.id)
    )
    return list(session.exec(statement).all())


def get_latest_assessment(session: Session, crew_id: str) -> Assessment | None:
    """Return the most recent assessment for a crew member."""
    statement = (
        select(Assessment)
        .where(Assessment.crew_id == crew_id)
        .order_by(Assessment.created_at.desc(), Assessment.id.desc())
        .limit(1)
    )
    return session.exec(statement).first()


def get_assessment(
    session: Session, crew_id: str, assessment_id: str
) -> Assessment | None:
    """Return one assessment belonging to a crew member."""
    assessment = session.get(Assessment, assessment_id)
    if assessment is None or assessment.crew_id != crew_id:
        return None
    return assessment


def get_assessments(
    session: Session, crew_id: str, limit: int, offset: int
) -> list[Assessment]:
    """Return a crew's assessments, newest first."""
    statement = (
        select(Assessment)
        .where(Assessment.crew_id == crew_id)
        .order_by(Assessment.created_at.desc(), Assessment.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.exec(statement).all())


def count_assessments(session: Session, crew_id: str) -> int:
    """Return the total number of assessments for a crew member."""
    return int(
        session.exec(
            select(func.count())
            .select_from(Assessment)
            .where(Assessment.crew_id == crew_id)
        ).one()
    )
