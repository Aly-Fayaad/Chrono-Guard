"""Development-only demo seeding route."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session

from app.core.config import get_settings
from app.core.database import get_session
from app.schemas.crew import SeedResult
from app.seed.demo_data import Scenario, seed_scenario
from app.services import checkin_service
from app.services.analysis import AnalysisEngine
from app.services.history_service import get_latest_assessment

logger = logging.getLogger(__name__)

router = APIRouter(tags=["demo"])


def _analyze_latest(
    session: Session, crew_id: str, engine: AnalysisEngine | None
) -> None:
    """Generate one assessment for seeded data so the console has real output."""
    if engine is None or get_latest_assessment(session, crew_id) is not None:
        return
    checkins = checkin_service.list_checkins(session, crew_id, 1, 0)
    if not checkins:
        return
    try:
        assessment = engine.analyze(session, crew_id, checkins[0].id)
        if assessment is not None:
            session.add(assessment)
            session.commit()
    except Exception:  # noqa: BLE001 - seeding must still succeed
        session.rollback()
        logger.exception("Analysis engine failed while seeding %s", crew_id)


@router.post("/demo/seed", response_model=SeedResult)
def seed_demo(
    request: Request,
    scenario: Scenario = Query(default="normal_routine"),
    reset: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> SeedResult:
    """Seed one synthetic scenario; available only when ENV=dev."""
    if get_settings().ENV != "dev":
        raise HTTPException(status_code=403, detail="Demo seeding is disabled")
    result = seed_scenario(session, scenario, reset=reset)
    engine = getattr(request.app.state, "analysis_engine", None)
    _analyze_latest(session, str(result["crew_id"]), engine)
    return SeedResult(**result)
