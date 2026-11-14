"""Unified crew overview route."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.config import get_settings
from app.core.database import get_session, to_utc, utcnow
from app.models.checkin import HealthMeasurement, SleepRecord
from app.models.enums import MeasurementSource, MeasurementType, QualityFlag
from app.models.mission import MissionTask
from app.schemas.mission import MissionTaskRead
from app.schemas.overview import (
    CrewOverview,
    MetricKey,
    MissionClockRead,
    OverviewDetection,
    OverviewMeasurement,
)
from app.services import checkin_service, mission_service
from app.services.history_service import (
    get_crew,
    get_latest_assessment,
    get_measurements,
    get_sleep_records,
)
from app.services.mission_clock import compute_mission_clock
from app.services.vitals_service import VitalPoint, detect

router = APIRouter(tags=["overview"])

HISTORY_DAYS = 30
TASK_PAST_DAYS = 7
TASK_FUTURE_DAYS = 14

METRIC_ORDER: tuple[MetricKey, ...] = (
    "heart_rate",
    "hrv",
    "temperature",
    "sleep_hours",
)

_QUALITY = {
    QualityFlag.valid: "valid",
    QualityFlag.questionable: "questionable",
    QualityFlag.missing: "missing",
}
_SOURCE = {
    MeasurementSource.manual: "manual",
    MeasurementSource.simulated: "simulated",
    MeasurementSource.device_import: "device_import",
}
_MEASUREMENT_METRIC = {
    MeasurementType.heart_rate: "heart_rate",
    MeasurementType.hrv: "hrv",
    MeasurementType.body_temperature: "temperature",
}


def _measurement(row: HealthMeasurement) -> OverviewMeasurement | None:
    metric = _MEASUREMENT_METRIC.get(row.type)
    if metric is None:
        return None
    return OverviewMeasurement(
        id=row.id,
        crew_id=row.crew_id,
        type=metric,
        value=float(row.value),
        unit=row.unit,
        recorded_at=to_utc(row.recorded_at),
        source=_SOURCE[row.source],
        quality=_QUALITY[row.quality],
    )


def _sleep_point(row: SleepRecord) -> OverviewMeasurement:
    return OverviewMeasurement(
        id=row.id,
        crew_id=row.crew_id,
        type="sleep_hours",
        value=float(row.duration_hours),
        unit="h",
        recorded_at=to_utc(row.sleep_end),
        source=_SOURCE[row.source],
        quality=_QUALITY[row.quality],
    )


def _points(rows: list[OverviewMeasurement]) -> list[VitalPoint]:
    return [
        VitalPoint(
            value=row.value,
            quality=row.quality,
            recorded_at=row.recorded_at,
        )
        for row in rows
    ]


def _task(row: MissionTask) -> MissionTaskRead:
    return MissionTaskRead.model_validate(row, from_attributes=True)


@router.get("/crew/{crew_id}/overview", response_model=CrewOverview)
def crew_overview(
    crew_id: str, session: Session = Depends(get_session)
) -> CrewOverview:
    """Return the backend's complete view of one crew member."""
    if get_crew(session, crew_id) is None:
        raise HTTPException(status_code=404, detail="Crew member not found")

    now = utcnow()
    window_start = now - timedelta(days=HISTORY_DAYS)
    clock = compute_mission_clock(now)

    series: dict[MetricKey, list[OverviewMeasurement]] = {
        metric: [] for metric in METRIC_ORDER
    }
    for row in get_measurements(session, crew_id, since=window_start):
        item = _measurement(row)
        if item is not None:
            series[item.type].append(item)
    for row in get_sleep_records(session, crew_id, since=window_start):
        series["sleep_hours"].append(_sleep_point(row))
    for metric in METRIC_ORDER:
        series[metric].sort(key=lambda item: item.recorded_at)

    detections = [
        OverviewDetection(**detect(metric, _points(series[metric])))
        for metric in METRIC_ORDER
    ]

    task_start = now - timedelta(days=TASK_PAST_DAYS)
    task_end = now + timedelta(days=TASK_FUTURE_DAYS)
    tasks = mission_service.list_tasks(
        session, crew_id, from_time=task_start, to_time=task_end
    )

    sleep_rows = get_sleep_records(session, crew_id, since=window_start)
    wake = next(
        (to_utc(row.sleep_end) for row in sleep_rows if to_utc(row.sleep_end) <= now),
        None,
    )
    checkins = checkin_service.list_checkins(session, crew_id, 1, 0)
    assessment = get_latest_assessment(session, crew_id)

    return CrewOverview(
        crew_id=crew_id,
        server_time=now,
        analysis_engine=get_settings().ANALYSIS_ENGINE,
        mission=MissionClockRead(**clock.to_dict()),
        series=series,
        detections=detections,
        assessment=assessment,
        tasks=[_task(row) for row in tasks],
        wake=wake,
        last_check_in=to_utc(checkins[0].submitted_at) if checkins else None,
    )
