"""Unified crew overview: mission clock, series, detections, tasks, assessment.

One read-only endpoint feeds the whole console so the frontend never has to
re-assemble mission time, health analysis, or assessment state locally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.assessment import AssessmentRead
from app.schemas.mission import MissionTaskRead

MetricKey = Literal["heart_rate", "hrv", "temperature", "sleep_hours"]
DetectionStatus = Literal[
    "normal", "anomaly", "insufficient_baseline", "data_quality"
]


class MissionClockRead(BaseModel):
    """Operational mission clock at the server's current instant."""

    as_of: datetime
    epoch: datetime
    mission_day_hours: float
    met_hours: float
    mission_day_index: int
    mission_local_time_hours: float
    local_time: str
    met_label: str


class OverviewMeasurement(BaseModel):
    """One point in a metric series, shaped for the console."""

    id: str
    crew_id: str
    type: MetricKey
    value: float
    unit: str
    recorded_at: datetime
    source: Literal["manual", "simulated", "device_import"]
    quality: Literal["valid", "questionable", "missing"]


class OverviewDetection(BaseModel):
    """Server-computed personal-baseline detection for one metric."""

    metric: MetricKey
    status: DetectionStatus
    z_score: float | None = None
    reason: str | None = None
    event: dict[str, str] | None = None


class CrewOverview(BaseModel):
    """Everything the console needs for one crew member."""

    crew_id: str
    server_time: datetime
    analysis_engine: str
    mission: MissionClockRead
    series: dict[MetricKey, list[OverviewMeasurement]]
    detections: list[OverviewDetection]
    assessment: AssessmentRead | None
    tasks: list[MissionTaskRead]
    wake: datetime | None
    last_check_in: datetime | None
