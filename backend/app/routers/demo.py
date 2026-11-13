"""Development-only demo seeding route."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.core.config import get_settings
from app.core.database import get_session
from app.schemas.crew import SeedResult
from app.seed.demo_data import Scenario, seed_scenario

router = APIRouter(tags=["demo"])


@router.post("/demo/seed", response_model=SeedResult)
def seed_demo(
    scenario: Scenario = Query(default="normal_routine"),
    reset: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> SeedResult:
    """Seed one synthetic scenario; available only when ENV=dev."""
    if get_settings().ENV != "dev":
        raise HTTPException(status_code=403, detail="Demo seeding is disabled")
    result = seed_scenario(session, scenario, reset=reset)
    return SeedResult(**result)
