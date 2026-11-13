"""Assessment response schemas (read-only for clients)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import AssessmentStatus


class AssessmentRead(BaseModel):
    """Analysis output returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    crew_id: str
    checkin_id: str | None
    status: AssessmentStatus
    summary: str
    explanation: str
    contributing_factors: list[dict[str, Any]]
    engine_version: str
    created_at: datetime
