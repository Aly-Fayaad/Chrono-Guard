"""Crew request and response schemas."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CrewCreate(BaseModel):
    """Fields required to create a crew member.

    ``id`` is optional. When omitted the server generates a UUID-style string;
    callers that need a stable demo slug may supply one as ``id`` or ``slug``.
    """

    model_config = ConfigDict(extra="forbid")

    id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Optional slug. Generated server-side when omitted.",
    )
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Alias for id; omitted from responses.",
    )
    display_name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=200)
    sleep_target_hours: float = Field(default=7.5, gt=0, le=24)

    @model_validator(mode="after")
    def _merge_slug(self) -> Self:
        """Use ``slug`` as the id when ``id`` was not supplied."""
        if self.slug is not None:
            if self.id is not None and self.id != self.slug:
                raise ValueError("id and slug must match when both are provided")
            self.id = self.slug
        return self


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


class CrewDeleteResult(BaseModel):
    """Confirmation of a crew deletion and its dependent-row cleanup."""

    deleted: bool
    id: str
    deleted_rows: dict[str, int]


class SeedResult(BaseModel):
    """Result of a demo seed operation."""

    scenario: str
    created: bool
    crew_id: str
