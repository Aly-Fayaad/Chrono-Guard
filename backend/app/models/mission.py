from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index
from sqlmodel import Field, SQLModel

from app.core.database import UTCDateTime, new_id
from app.models.enums import TaskType, WorkloadLevel, enum_values

TASK_TYPE = SAEnum(TaskType, values_callable=enum_values, name="task_type")
WORKLOAD_LEVEL = SAEnum(WorkloadLevel, values_callable=enum_values, name="workload_level")


class MissionTask(SQLModel, table=True):
    """Scheduled mission task linked to a crew member."""

    __table_args__ = (Index("ix_mission_crew_start", "crew_id", "start_time"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    crew_id: str = Field(foreign_key="crewprofile.id", nullable=False)
    title: str = Field(nullable=False)
    task_type: TaskType = Field(default=TaskType.other, sa_type=TASK_TYPE, nullable=False)
    start_time: datetime = Field(sa_type=UTCDateTime, nullable=False)
    end_time: datetime = Field(sa_type=UTCDateTime, nullable=False)
    workload_level: WorkloadLevel = Field(
        default=WorkloadLevel.medium, sa_type=WORKLOAD_LEVEL, nullable=False
    )
    is_critical: bool = Field(default=False, nullable=False)
    notes: str | None = Field(default=None)
