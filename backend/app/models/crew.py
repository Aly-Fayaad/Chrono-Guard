from datetime import datetime

from sqlmodel import Field, SQLModel

from app.core.database import UTCDateTime, new_id, utcnow


class CrewProfile(SQLModel, table=True):
    """Crew member profile."""

    id: str = Field(default_factory=new_id, primary_key=True)
    display_name: str = Field(nullable=False)
    role: str = Field(nullable=False)
    sleep_target_hours: float = Field(default=7.5, nullable=False)
    created_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime, nullable=False)
