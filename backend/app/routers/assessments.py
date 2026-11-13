"""Read-only assessment routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.assessment import AssessmentRead
from app.services.history_service import (
    get_assessments,
    get_crew,
    get_latest_assessment,
)

router = APIRouter(tags=["assessments"])

DEFAULT_ASSESSMENT_LIMIT = 50
MAX_ASSESSMENT_LIMIT = 200


@router.get("/crew/{crew_id}/assessments", response_model=list[AssessmentRead])
def list_assessments(
    crew_id: str,
    limit: int = Query(default=DEFAULT_ASSESSMENT_LIMIT, ge=1, le=MAX_ASSESSMENT_LIMIT),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[AssessmentRead]:
    """List assessments for a crew member, newest first."""
    if get_crew(session, crew_id) is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    return get_assessments(session, crew_id, limit, offset)


@router.get("/crew/{crew_id}/assessments/latest", response_model=AssessmentRead)
def read_latest_assessment(
    crew_id: str, session: Session = Depends(get_session)
) -> AssessmentRead:
    """Return the most recent assessment for a crew member."""
    if get_crew(session, crew_id) is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    assessment = get_latest_assessment(session, crew_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment
