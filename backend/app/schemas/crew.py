"""Crew request and response schemas."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CrewRead(BaseModel):
    """Crew profile returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    role: str
    sleep_target_hours: float
    created_at: datetime


class CrewUpdate(BaseModel):
    """Editable crew profile fields."""

    display_name: str | None = Field(default=None, min_length=1)
    role: str | None = Field(default=None, min_length=1)
    sleep_target_hours: float | None = Field(default=None, gt=0, le=24)

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> Self:
        """Reject null values for fields that cannot be cleared."""
        for field in ("display_name", "role", "sleep_target_hours"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class SeedResult(BaseModel):
    """Result of a demo seed operation."""

    scenario: str
    created: bool
    crew_id: str
