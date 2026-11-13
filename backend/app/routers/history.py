"""Health and sleep history routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.core.database import get_session
from app.models.enums import MeasurementType
from app.schemas.history import MeasurementHistory, SleepHistory
from app.services.history_service import (
    get_crew,
    get_measurements,
    get_sleep_records,
)

router = APIRouter(tags=["history"])

DEFAULT_HISTORY_LIMIT = 200
MAX_HISTORY_LIMIT = 1000


@router.get(
    "/crew/{crew_id}/history/measurements", response_model=MeasurementHistory
)
def measurement_history(
    crew_id: str,
    measurement_type: MeasurementType | None = Query(default=None, alias="type"),
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=DEFAULT_HISTORY_LIMIT, ge=1, le=MAX_HISTORY_LIMIT),
    session: Session = Depends(get_session),
) -> MeasurementHistory:
    """Return measurement history, newest first, with optional filters."""
    if get_crew(session, crew_id) is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    types = [measurement_type] if measurement_type is not None else None
    rows = get_measurements(
        session, crew_id, types=types, since=from_time, until=to_time, limit=limit
    )
    return MeasurementHistory(measurements=rows)


@router.get("/crew/{crew_id}/history/sleep", response_model=SleepHistory)
def sleep_history(
    crew_id: str,
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=DEFAULT_HISTORY_LIMIT, ge=1, le=MAX_HISTORY_LIMIT),
    session: Session = Depends(get_session),
) -> SleepHistory:
    """Return sleep history, newest first, with optional date filters."""
    if get_crew(session, crew_id) is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    rows = get_sleep_records(session, crew_id, since=from_time, until=to_time)[:limit]
    return SleepHistory(sleep_records=rows)
