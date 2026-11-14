"""Dashboard summary schemas.

The summary is descriptive only. It intentionally contains no baselines,
thresholds, alerts, or composite scores; those belong to the analysis layer.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.enums import MeasurementType, QualityFlag


class MeasurementSummary(BaseModel):
    """Latest reading plus seven-day counts and valid-only mean."""

    type: MeasurementType
    unit: str
    latest_value: float | None = None
    latest_quality: QualityFlag | None = None
    latest_recorded_at: datetime | None = None
    valid_count_7d: int = 0
    questionable_count_7d: int = 0
    mean_7d: float | None = None


class SleepSummary(BaseModel):
    """Latest sleep window plus seven-day valid-night statistics."""

    last_duration_hours: float | None = None
    last_sleep_end: datetime | None = None
    last_quality: QualityFlag | None = None
    mean_duration_7d: float | None = None
    valid_nights_7d: int = 0


class DashboardSummary(BaseModel):
    """Everything the dashboard needs without recomputing health logic."""

    crew_id: str
    generated_at: datetime
    window_days: int = 7
    measurements: list[MeasurementSummary]
    sleep: SleepSummary
    data_freshness_hours: float | None = None
