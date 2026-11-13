"""Mission task request and response schemas."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import TaskType, WorkloadLevel


class MissionTaskCreate(BaseModel):
    """Fields required to create a mission task."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    task_type: TaskType = TaskType.other
    start_time: datetime
    end_time: datetime
    workload_level: WorkloadLevel = WorkloadLevel.medium
    is_critical: bool = False
    notes: str | None = None


class MissionTaskUpdate(BaseModel):
    """Editable mission task fields."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1)
    task_type: TaskType | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    workload_level: WorkloadLevel | None = None
    is_critical: bool | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> Self:
        """Reject null values for fields that cannot be cleared."""
        fields = ("title", "task_type", "start_time", "end_time", "workload_level", "is_critical")
        for field in fields:
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class MissionTaskRead(BaseModel):
    """Mission task returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    crew_id: str
    title: str
    task_type: TaskType
    start_time: datetime
    end_time: datetime
    workload_level: WorkloadLevel
    is_critical: bool
    notes: str | None


class MissionDeleteResult(BaseModel):
    """Confirmation of a deleted mission task."""

    deleted: bool
    id: str
