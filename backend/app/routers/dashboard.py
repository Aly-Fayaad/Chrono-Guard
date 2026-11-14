"""Dashboard summary route."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.database import get_session
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard_service import build_dashboard_summary
from app.services.history_service import get_crew

router = APIRouter(tags=["dashboard"])


@router.get("/crew/{crew_id}/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    crew_id: str, session: Session = Depends(get_session)
) -> DashboardSummary:
    """Return descriptive per-metric and sleep summaries for the dashboard."""
    if get_crew(session, crew_id) is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    return build_dashboard_summary(session, crew_id)
