from datetime import datetime

from sqlalchemy import JSON, Enum as SAEnum
from sqlalchemy import Index
from sqlmodel import Field, SQLModel

from app.core.database import UTCDateTime, new_id, utcnow
from app.models.enums import AssessmentStatus, enum_values

ASSESSMENT_STATUS = SAEnum(AssessmentStatus, values_callable=enum_values, name="assessment_status")


class Assessment(SQLModel, table=True):
    """Analysis output written by the AI engine (read-only for clients)."""

    __table_args__ = (Index("ix_assessment_crew_created", "crew_id", "created_at"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    crew_id: str = Field(foreign_key="crewprofile.id", nullable=False)
    checkin_id: str | None = Field(default=None, foreign_key="checkin.id")
    status: AssessmentStatus = Field(sa_type=ASSESSMENT_STATUS, nullable=False)
    summary: str = Field(nullable=False)
    explanation: str = Field(nullable=False)
    contributing_factors: list[dict] = Field(default_factory=list, sa_type=JSON, nullable=False)
    engine_version: str = Field(nullable=False)
    created_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime, nullable=False)
