from datetime import datetime

from sqlalchemy import JSON, Enum as SAEnum
from sqlalchemy import Index
from sqlmodel import Field, SQLModel

from app.core.database import UTCDateTime, new_id, utcnow
from app.models.enums import ActionStatus, enum_values

ACTION_STATUS = SAEnum(ActionStatus, values_callable=enum_values, name="action_status")


class Countermeasure(SQLModel, table=True):
    """Countermeasure catalogue entry owned by Person 4."""

    id: str = Field(primary_key=True)
    name: str = Field(nullable=False)
    preconditions: list[dict] = Field(default_factory=list, sa_type=JSON, nullable=False)
    evidence_status: str = Field(nullable=False)
    evidence_source: str | None = Field(default=None)
    warnings: str | None = Field(default=None)
    requires_mission_approval: bool = Field(default=False, nullable=False)
    follow_up_instruction: str | None = Field(default=None)


class ActionHistory(SQLModel, table=True):
    """Countermeasure action history owned by Person 4."""

    __table_args__ = (Index("ix_action_crew_created", "crew_id", "created_at"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    crew_id: str = Field(foreign_key="crewprofile.id", nullable=False)
    assessment_id: str | None = Field(default=None, foreign_key="assessment.id")
    countermeasure_id: str = Field(foreign_key="countermeasure.id", nullable=False)
    status: ActionStatus = Field(default=ActionStatus.suggested, sa_type=ACTION_STATUS, nullable=False)
    follow_up_due_at: datetime | None = Field(default=None, sa_type=UTCDateTime)
    follow_up_result: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, sa_type=UTCDateTime, nullable=False)
