"""Descriptive dashboard aggregation.

No baselines, thresholds, alerts, or composite scores live here. The endpoint
reports what was stored and simple seven-day statistics so the UI does not have
to re-implement health-data aggregation.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.database import to_utc, utcnow
from app.models.checkin import HealthMeasurement, SleepRecord
from app.models.enums import MeasurementType, QualityFlag
from app.schemas.dashboard import DashboardSummary, MeasurementSummary, SleepSummary
from app.services.validation import unit_for

WINDOW_DAYS = 7


def _latest_measurement(
    session: Session, crew_id: str, measurement_type: MeasurementType
) -> HealthMeasurement | None:
    """Return the newest stored row for one measurement type."""
    return session.exec(
        select(HealthMeasurement)
        .where(
            HealthMeasurement.crew_id == crew_id,
            HealthMeasurement.type == measurement_type,
        )
        .order_by(HealthMeasurement.recorded_at.desc(), HealthMeasurement.id.desc())
        .limit(1)
    ).first()


def _measurement_summaries(
    session: Session, crew_id: str, since: datetime
) -> tuple[list[MeasurementSummary], datetime | None]:
    """Build per-type summaries and the newest measurement timestamp."""
    aggregate_rows = session.exec(
        select(
            HealthMeasurement.type,
            HealthMeasurement.quality,
            func.count(),
            func.avg(HealthMeasurement.value),
        )
        .where(
            HealthMeasurement.crew_id == crew_id,
            HealthMeasurement.recorded_at >= since,
        )
        .group_by(HealthMeasurement.type, HealthMeasurement.quality)
    ).all()

    valid_counts: dict[MeasurementType, int] = {}
    questionable_counts: dict[MeasurementType, int] = {}
    means: dict[MeasurementType, float] = {}
    for measurement_type, quality, count, mean in aggregate_rows:
        if quality == QualityFlag.valid:
            valid_counts[measurement_type] = int(count)
            means[measurement_type] = float(mean) if mean is not None else 0.0
        elif quality == QualityFlag.questionable:
            questionable_counts[measurement_type] = int(count)

    summaries: list[MeasurementSummary] = []
    newest: datetime | None = None
    for measurement_type in MeasurementType:
        latest = _latest_measurement(session, crew_id, measurement_type)
        if latest is not None:
            latest_at = to_utc(latest.recorded_at)
            newest = latest_at if newest is None else max(newest, latest_at)
        summaries.append(
            MeasurementSummary(
                type=measurement_type,
                unit=unit_for(measurement_type),
                latest_value=float(latest.value) if latest is not None else None,
                latest_quality=latest.quality if latest is not None else None,
                latest_recorded_at=to_utc(latest.recorded_at) if latest else None,
                valid_count_7d=valid_counts.get(measurement_type, 0),
                questionable_count_7d=questionable_counts.get(measurement_type, 0),
                mean_7d=round(means[measurement_type], 3)
                if measurement_type in means
                else None,
            )
        )
    return summaries, newest


def _sleep_summary(
    session: Session, crew_id: str, since: datetime
) -> tuple[SleepSummary, datetime | None]:
    """Build the latest-sleep and seven-day valid-night summary."""
    latest = session.exec(
        select(SleepRecord)
        .where(SleepRecord.crew_id == crew_id)
        .order_by(SleepRecord.sleep_end.desc(), SleepRecord.id.desc())
        .limit(1)
    ).first()

    window_rows = list(
        session.exec(
            select(SleepRecord).where(
                SleepRecord.crew_id == crew_id,
                SleepRecord.sleep_end >= since,
            )
        ).all()
    )
    valid = [row for row in window_rows if row.quality == QualityFlag.valid]
    mean = (
        round(sum(float(row.duration_hours) for row in valid) / len(valid), 3)
        if valid
        else None
    )
    summary = SleepSummary(
        last_duration_hours=float(latest.duration_hours) if latest else None,
        last_sleep_end=to_utc(latest.sleep_end) if latest else None,
        last_quality=latest.quality if latest else None,
        mean_duration_7d=mean,
        valid_nights_7d=len(valid),
    )
    return summary, to_utc(latest.sleep_end) if latest else None


def build_dashboard_summary(session: Session, crew_id: str) -> DashboardSummary:
    """Return the descriptive seven-day dashboard payload."""
    now = utcnow()
    since = now - timedelta(days=WINDOW_DAYS)
    measurements, newest_measurement = _measurement_summaries(session, crew_id, since)
    sleep, newest_sleep = _sleep_summary(session, crew_id, since)

    candidates = [value for value in (newest_measurement, newest_sleep) if value]
    freshness = None
    if candidates:
        newest = max(candidates)
        freshness = round(max(0.0, (now - newest).total_seconds() / 3600), 2)

    return DashboardSummary(
        crew_id=crew_id,
        generated_at=now,
        window_days=WINDOW_DAYS,
        measurements=measurements,
        sleep=sleep,
        data_freshness_hours=freshness,
    )
