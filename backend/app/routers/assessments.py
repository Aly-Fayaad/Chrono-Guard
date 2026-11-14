"""Read-only assessment routes plus safe historical re-analysis."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.assessment import AssessmentRead, ReanalysisResult
from app.services.history_service import (
    count_assessments,
    get_assessment,
    get_assessments,
    get_crew,
    get_latest_assessment,
)
from app.services.reanalysis_service import reanalyze_crew

router = APIRouter(tags=["assessments"])

DEFAULT_ASSESSMENT_LIMIT = 50
MAX_ASSESSMENT_LIMIT = 200


@router.get("/crew/{crew_id}/assessments", response_model=list[AssessmentRead])
def list_assessments(
    crew_id: str,
    response: Response,
    limit: int = Query(default=DEFAULT_ASSESSMENT_LIMIT, ge=1, le=MAX_ASSESSMENT_LIMIT),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[AssessmentRead]:
    """List assessments for a crew member, newest first."""
    if get_crew(session, crew_id) is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    response.headers["X-Total-Count"] = str(count_assessments(session, crew_id))
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


@router.get(
    "/crew/{crew_id}/assessments/{assessment_id}", response_model=AssessmentRead
)
def read_assessment(
    crew_id: str, assessment_id: str, session: Session = Depends(get_session)
) -> AssessmentRead:
    """Return one assessment, or 404 when missing or owned by another crew."""
    if get_crew(session, crew_id) is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    assessment = get_assessment(session, crew_id, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment


@router.post(
    "/crew/{crew_id}/assessments/reanalyze",
    response_model=ReanalysisResult,
)
def reanalyze_assessments(
    crew_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> ReanalysisResult:
    """Re-analyse stored check-ins without modifying the original records."""
    if get_crew(session, crew_id) is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    engine = getattr(request.app.state, "analysis_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Analysis engine is not configured")
    return reanalyze_crew(session, crew_id, engine)
