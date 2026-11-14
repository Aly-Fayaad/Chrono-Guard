"""Explicit analysis-run route.

P3 supplies the engine; this router owns the HTTP trigger and reuses the same
persist-and-fail-safe path as check-in submission.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.analysis import AnalysisRunResponse
from app.services import checkin_service
from app.services.history_service import get_crew

router = APIRouter(tags=["analysis"])


@router.post("/crew/{crew_id}/analysis/run", response_model=AnalysisRunResponse)
def run_analysis(
    crew_id: str,
    request: Request,
    checkin_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> AnalysisRunResponse:
    """Run the configured engine on a given or latest check-in.

    The check-in must belong to the crew. The response is
    ``{"assessment": null}`` for a no-op engine (``NullEngine``) or when the
    engine fails safely. An unconfigured engine returns ``503``.
    """
    if get_crew(session, crew_id) is None:
        raise HTTPException(status_code=404, detail="Crew member not found")

    if checkin_id is not None:
        detail = checkin_service.get_checkin_detail(session, crew_id, checkin_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Check-in not found")
        target_id = checkin_id
    else:
        latest = checkin_service.get_latest_checkin(session, crew_id)
        if latest is None:
            raise HTTPException(status_code=404, detail="Check-in not found")
        target_id = latest.id

    engine = getattr(request.app.state, "analysis_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Analysis engine is not configured")

    assessment = checkin_service.run_analysis(session, crew_id, target_id, engine)
    return AnalysisRunResponse(assessment=assessment)
