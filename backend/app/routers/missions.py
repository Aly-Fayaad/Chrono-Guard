"""Mission task routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session

from app.core.database import get_session
from app.models.enums import TaskType, WorkloadLevel
from app.schemas.mission import (
    MissionDeleteResult,
    MissionTaskCreate,
    MissionTaskRead,
    MissionTaskUpdate,
)
from app.services import mission_service
from app.services.history_service import get_crew

router = APIRouter(tags=["missions"])


@router.post(
    "/crew/{crew_id}/missions", response_model=MissionTaskRead, status_code=status.HTTP_201_CREATED
)
def create_mission(
    crew_id: str, payload: MissionTaskCreate, session: Session = Depends(get_session)
) -> MissionTaskRead:
    """Create a mission task for a crew member."""
    if get_crew(session, crew_id) is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    return mission_service.create_task(session, crew_id, payload)


@router.get("/crew/{crew_id}/missions", response_model=list[MissionTaskRead])
def list_missions(
    crew_id: str,
    response: Response,
    upcoming: bool = False,
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    task_type: TaskType | None = Query(default=None),
    workload_level: WorkloadLevel | None = Query(default=None),
    is_critical: bool | None = Query(default=None),
    horizon_hours: int | None = Query(default=None, ge=1, le=720),
    session: Session = Depends(get_session),
) -> list[MissionTaskRead]:
    """List mission tasks with optional upcoming-window and attribute filters.

    ``upcoming=true`` without ``horizon_hours`` keeps the existing behaviour of
    returning all future tasks. Supplying ``horizon_hours`` restricts that to
    the next N hours. The shared helper
    ``history_service.get_upcoming_tasks`` defaults to 72 hours; this route does
    not, so existing clients are not silently truncated.
    """
    if get_crew(session, crew_id) is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    filters = {
        "upcoming": upcoming,
        "from_time": from_time,
        "to_time": to_time,
        "task_type": task_type,
        "workload_level": workload_level,
        "is_critical": is_critical,
        "horizon_hours": horizon_hours,
    }
    response.headers["X-Total-Count"] = str(
        mission_service.count_tasks(session, crew_id, **filters)
    )
    return mission_service.list_tasks(session, crew_id, **filters)


@router.get("/crew/{crew_id}/missions/{task_id}", response_model=MissionTaskRead)
def read_mission(
    crew_id: str, task_id: str, session: Session = Depends(get_session)
) -> MissionTaskRead:
    """Return one mission task."""
    task = mission_service.get_task(session, crew_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Mission task not found")
    return task


@router.patch("/crew/{crew_id}/missions/{task_id}", response_model=MissionTaskRead)
def update_mission(
    crew_id: str,
    task_id: str,
    payload: MissionTaskUpdate,
    session: Session = Depends(get_session),
) -> MissionTaskRead:
    """Partially update a mission task."""
    task = mission_service.get_task(session, crew_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Mission task not found")
    return mission_service.update_task(session, task, payload)


@router.delete("/crew/{crew_id}/missions/{task_id}", response_model=MissionDeleteResult)
def delete_mission(
    crew_id: str, task_id: str, session: Session = Depends(get_session)
) -> MissionDeleteResult:
    """Delete a mission task."""
    task = mission_service.get_task(session, crew_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Mission task not found")
    mission_service.delete_task(session, task)
    return MissionDeleteResult(deleted=True, id=task_id)
