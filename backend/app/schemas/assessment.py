"""Assessment response schemas (read-only for clients)."""

from datetime import datetime
from typing import Any, Literal

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


class ReanalysisItem(BaseModel):
    """Outcome of one check-in in a historical re-analysis run."""

    checkin_id: str
    status: Literal["succeeded", "skipped", "failed"]
    assessment_id: str | None = None
    assessment_status: AssessmentStatus | None = None
    reason: str | None = None


class ReanalysisResult(BaseModel):
    """Summary of a crew member's historical re-analysis run."""

    crew_id: str
    engine_version: str
    processed: int
    succeeded: int
    skipped: int
    failed: int
    insufficient: int
    results: list[ReanalysisItem]
