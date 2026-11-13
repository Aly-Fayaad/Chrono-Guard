"""Check-in routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.checkin import CheckInCreate, CheckInRead, CheckInResponse
from app.services import checkin_service
from app.services.history_service import get_crew

router = APIRouter(tags=["checkins"])


@router.post(
    "/crew/{crew_id}/checkins", response_model=CheckInResponse, status_code=status.HTTP_201_CREATED
)
def create_checkin(
    crew_id: str,
    payload: CheckInCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> CheckInResponse:
    """Validate and save one check-in, then invoke the analysis hook."""
    if get_crew(session, crew_id) is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    engine = getattr(request.app.state, "analysis_engine", None)
    checkin, measurements, sleep_record, assessment = checkin_service.create_checkin(
        session, crew_id, payload, engine
    )
    return CheckInResponse(
        checkin=checkin,
        measurements=measurements,
        sleep_record=sleep_record,
        assessment=assessment,
    )


@router.get("/crew/{crew_id}/checkins", response_model=list[CheckInRead])
def list_checkins(
    crew_id: str,
    limit: int = Query(checkin_service.DEFAULT_CHECKIN_LIMIT, ge=1, le=checkin_service.MAX_CHECKIN_LIMIT),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[CheckInRead]:
    """List a crew member's check-ins, newest first."""
    if get_crew(session, crew_id) is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    return checkin_service.list_checkins(session, crew_id, limit, offset)


@router.get(
    "/crew/{crew_id}/checkins/{checkin_id}", response_model=CheckInResponse
)
def read_checkin(
    crew_id: str, checkin_id: str, session: Session = Depends(get_session)
) -> CheckInResponse:
    """Return one check-in with measurements, sleep, and assessment."""
    detail = checkin_service.get_checkin_detail(session, crew_id, checkin_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Check-in not found")
    checkin, measurements, sleep_record, assessment = detail
    return CheckInResponse(
        checkin=checkin,
        measurements=measurements,
        sleep_record=sleep_record,
        assessment=assessment,
    )
