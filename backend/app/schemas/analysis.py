"""Analysis-run response schema."""

from pydantic import BaseModel

from app.schemas.assessment import AssessmentRead


class AnalysisRunResponse(BaseModel):
    """Result of an explicit analysis run.

    ``assessment`` is null when the configured engine is a no-op, when no
    analysis is available, or when the engine failed safely after the check-in
    was already stored.
    """

    assessment: AssessmentRead | None = None
