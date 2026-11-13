"""Crew profile routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from sqlmodel import select

from app.core.database import get_session
from app.models.crew import CrewProfile
from app.schemas.crew import CrewRead, CrewUpdate
from app.services.history_service import get_crew

router = APIRouter(tags=["crew"])


@router.get("/crew", response_model=list[CrewRead])
def list_crew(session: Session = Depends(get_session)) -> list[CrewProfile]:
    """List all crew profiles."""
    return list(session.exec(select(CrewProfile).order_by(CrewProfile.display_name)).all())


@router.get("/crew/{crew_id}", response_model=CrewRead)
def read_crew(crew_id: str, session: Session = Depends(get_session)) -> CrewProfile:
    """Return one crew profile."""
    crew = get_crew(session, crew_id)
    if crew is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    return crew


@router.patch("/crew/{crew_id}", response_model=CrewRead)
def update_crew(
    crew_id: str, payload: CrewUpdate, session: Session = Depends(get_session)
) -> CrewProfile:
    """Update editable crew profile fields."""
    crew = get_crew(session, crew_id)
    if crew is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(crew, field, value)
    session.add(crew)
    session.commit()
    return crew
