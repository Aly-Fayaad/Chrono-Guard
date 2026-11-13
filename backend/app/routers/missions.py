"""Mission task routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.core.database import get_session
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
    upcoming: bool = False,
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    session: Session = Depends(get_session),
) -> list[MissionTaskRead]:
    """List mission tasks, optionally restricted to an upcoming window."""
    if get_crew(session, crew_id) is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    return mission_service.list_tasks(session, crew_id, upcoming, from_time, to_time)


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
