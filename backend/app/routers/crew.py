"""Crew profile routes."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session
from sqlmodel import select

from app.core.database import get_session
from app.models.crew import CrewProfile
from app.schemas.crew import CrewCreate, CrewDeleteResult, CrewRead, CrewUpdate
from app.services import crew_service
from app.services.history_service import get_crew

router = APIRouter(tags=["crew"])


@router.post("/crew", response_model=CrewRead, status_code=status.HTTP_201_CREATED)
def create_crew(payload: CrewCreate, session: Session = Depends(get_session)) -> CrewProfile:
    """Create a crew profile, optionally with a caller-supplied slug."""
    try:
        return crew_service.create_crew(session, payload)
    except crew_service.CrewAlreadyExists as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/crew", response_model=list[CrewRead])
def list_crew(
    response: Response, session: Session = Depends(get_session)
) -> list[CrewProfile]:
    """List all crew profiles."""
    rows = list(session.exec(select(CrewProfile).order_by(CrewProfile.display_name)).all())
    response.headers["X-Total-Count"] = str(len(rows))
    return rows


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
    session.refresh(crew)
    return crew


@router.delete("/crew/{crew_id}", response_model=CrewDeleteResult)
def delete_crew(crew_id: str, session: Session = Depends(get_session)) -> CrewDeleteResult:
    """Delete a crew member and every dependent row in one transaction."""
    counts = crew_service.delete_crew(session, crew_id)
    if counts is None:
        raise HTTPException(status_code=404, detail="Crew member not found")
    return CrewDeleteResult(deleted=True, id=crew_id, deleted_rows=counts)
