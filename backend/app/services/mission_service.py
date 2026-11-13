"""Mission task business logic."""

from datetime import datetime

from sqlmodel import Session
from sqlmodel import select

from app.core.database import to_utc, utcnow
from app.mission.task_checks import log_task_warnings
from app.models.mission import MissionTask
from app.schemas.mission import MissionTaskCreate, MissionTaskUpdate
from app.services.validation import ValidationFailure


def create_task(session: Session, crew_id: str, payload: MissionTaskCreate) -> MissionTask:
    """Validate and persist a new mission task."""
    start = to_utc(payload.start_time)
    end = to_utc(payload.end_time)
    if end <= start:
        raise ValidationFailure("end_time must be after start_time")
    task = MissionTask(
        crew_id=crew_id,
        title=payload.title,
        task_type=payload.task_type,
        start_time=start,
        end_time=end,
        workload_level=payload.workload_level,
        is_critical=payload.is_critical,
        notes=payload.notes,
    )
    session.add(task)
    session.commit()
    log_task_warnings(
        session,
        crew_id,
        task.start_time,
        task.end_time,
        task_type=task.task_type,
        workload_level=task.workload_level,
        is_critical=task.is_critical,
        title=task.title,
        exclude_task_id=task.id,
    )
    return task


def list_tasks(
    session: Session,
    crew_id: str,
    upcoming: bool = False,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
) -> list[MissionTask]:
    """Return mission tasks, earliest first, with optional window filters."""
    statement = select(MissionTask).where(MissionTask.crew_id == crew_id)
    if upcoming:
        lower = to_utc(from_time) if from_time is not None else utcnow()
        statement = statement.where(MissionTask.start_time >= lower)
    elif from_time is not None:
        statement = statement.where(MissionTask.start_time >= to_utc(from_time))
    if to_time is not None:
        statement = statement.where(MissionTask.start_time <= to_utc(to_time))
    return list(session.exec(statement.order_by(MissionTask.start_time)).all())


def get_task(session: Session, crew_id: str, task_id: str) -> MissionTask | None:
    """Return one task belonging to a crew member."""
    task = session.get(MissionTask, task_id)
    if task is None or task.crew_id != crew_id:
        return None
    return task


def update_task(
    session: Session, task: MissionTask, payload: MissionTaskUpdate
) -> MissionTask:
    """Apply a partial update after validating the resulting time window."""
    changes = payload.model_dump(exclude_unset=True)
    start = to_utc(changes.get("start_time", task.start_time))
    end = to_utc(changes.get("end_time", task.end_time))
    if end <= start:
        raise ValidationFailure("end_time must be after start_time")
    for field, value in changes.items():
        setattr(task, field, value)
    task.start_time = start
    task.end_time = end
    session.add(task)
    session.commit()
    log_task_warnings(
        session,
        task.crew_id,
        task.start_time,
        task.end_time,
        task_type=task.task_type,
        workload_level=task.workload_level,
        is_critical=task.is_critical,
        title=task.title,
        exclude_task_id=task.id,
    )
    return task


def delete_task(session: Session, task: MissionTask) -> None:
    """Delete a mission task."""
    session.delete(task)
    session.commit()
