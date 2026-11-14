"""Adapters between the existing database and the mission-intelligence DTOs.

The database is treated as read-only. Every read goes through
``app.services.history_service``; no SQLModel query is written here.

Mapping notes (all configurable assumptions, because the database has no such
fields for mission tasks):

* ``priority`` - critical tasks map to ``CRITICAL_PRIORITY``; otherwise the
  workload level is mapped through ``PRIORITY_BY_WORKLOAD``.
* ``required_alertness`` - derived from the workload level through
  ``ALERTNESS_BY_WORKLOAD``; critical tasks are raised to at least
  ``CRITICAL_TASK_ALERTNESS_REQUIREMENT`` and capped at ``MAX_ALERTNESS``.
* ``status`` - every adapted task gets ``DEFAULT_TASK_STATUS`` because
  ``MissionTask`` has no status column.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Protocol, Sequence

from sqlmodel import Session

from app.core.database import to_utc
from app.mission.config import DEFAULT_CONFIG, MissionConfig
from app.mission.models import (
    AstronautContext,
    CrewProfileSummary,
    FatigueLevel,
    FatigueSignal,
    PlannedSleepWindow,
    Priority,
    SleepSummary,
    TaskCategory,
    TaskView,
    WorkloadLevel,
)
from app.models.assessment import Assessment
from app.models.enums import AssessmentStatus
from app.models.mission import MissionTask
from app.models.checkin import SleepRecord
from app.services.history_service import (
    get_crew,
    get_latest_assessment,
    get_sleep_records,
    get_upcoming_tasks,
)

_MINUTES_PER_DAY = 24 * 60


def _as_utc(value: datetime, label: str) -> datetime:
    """Require an aware datetime and normalise it to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware (UTC)")
    return value.astimezone(timezone.utc)


def required_alertness(
    workload: WorkloadLevel, is_critical: bool, config: MissionConfig = DEFAULT_CONFIG
) -> int:
    """Derive a 1-5 required-alertness score from workload and criticality.

    This is a configurable assumption: neither the scale nor the mapping exists
    in the database or in the reference sources.
    """
    value = config.ALERTNESS_BY_WORKLOAD[workload]
    if is_critical:
        value = max(
            value + config.CRITICAL_ALERTNESS_BONUS,
            config.CRITICAL_TASK_ALERTNESS_REQUIREMENT,
        )
    return max(config.MIN_ALERTNESS, min(config.MAX_ALERTNESS, value))


def task_from_db(
    task: MissionTask, config: MissionConfig = DEFAULT_CONFIG
) -> TaskView:
    """Adapt a ``MissionTask`` row into a ``TaskView``.

    Missing database fields are filled with documented configurable assumptions
    (see the module docstring). Datetimes are normalised to UTC.
    """
    workload = WorkloadLevel(task.workload_level.value)
    priority = (
        config.CRITICAL_PRIORITY
        if task.is_critical
        else config.PRIORITY_BY_WORKLOAD[workload]
    )
    return TaskView(
        task_id=task.id,
        astronaut_id=task.crew_id,
        name=task.title,
        category=TaskCategory(task.task_type.value),
        start_time=to_utc(task.start_time),
        end_time=to_utc(task.end_time),
        priority=priority,
        workload_level=workload,
        required_alertness=required_alertness(workload, task.is_critical, config),
        status=config.DEFAULT_TASK_STATUS,
        is_critical=task.is_critical,
    )


class FatigueSignalProvider(Protocol):
    """Source of a categorical fatigue signal for one astronaut."""

    def get_fatigue_signal(self, session: Session, crew_id: str) -> FatigueSignal:
        """Return the current fatigue signal for ``crew_id``."""
        ...


class AssessmentFatigueProvider:
    """Read the latest ``Assessment`` and expose it as a categorical signal.

    There is no numeric conversion: the assessment's ``contributing_factors``
    are passed through as raw JSON objects, and an absent or insufficient
    assessment yields ``FatigueLevel.unknown``.
    """

    def get_fatigue_signal(self, session: Session, crew_id: str) -> FatigueSignal:
        """Read the latest assessment through ``history_service``."""
        assessment = get_latest_assessment(session, crew_id)
        if assessment is None:
            return FatigueSignal(
                level=FatigueLevel.unknown,
                source="assessment:none",
                contributing_factors=[],
            )
        level = self._level_from_assessment(assessment)
        factors = assessment.contributing_factors
        if not isinstance(factors, list):
            factors = []
        return FatigueSignal(
            level=level,
            source=f"assessment:{assessment.id}",
            contributing_factors=[item for item in factors if isinstance(item, dict)],
        )

    @staticmethod
    def _level_from_assessment(assessment: Assessment) -> FatigueLevel:
        """Map the assessment status to a categorical fatigue level."""
        mapping = {
            AssessmentStatus.insufficient_data: FatigueLevel.unknown,
            AssessmentStatus.no_flag: FatigueLevel.no_flag,
            AssessmentStatus.monitor: FatigueLevel.monitor,
            AssessmentStatus.elevated_concern: FatigueLevel.elevated_concern,
        }
        return mapping.get(assessment.status, FatigueLevel.unknown)


class StaticFatigueProvider:
    """Return a fixed signal. Intended for tests and deterministic fixtures."""

    def __init__(self, signal: FatigueSignal) -> None:
        self._signal = signal

    def get_fatigue_signal(self, session: Session, crew_id: str) -> FatigueSignal:
        """Return the configured signal without touching the database."""
        return self._signal


def _circular_mean_minutes(values: Sequence[float]) -> float:
    """Return the circular mean of minute-of-day values in ``[0, 1440)``."""
    angles = [2.0 * math.pi * value / _MINUTES_PER_DAY for value in values]
    sin_sum = sum(math.sin(angle) for angle in angles)
    cos_sum = sum(math.cos(angle) for angle in angles)
    if abs(sin_sum) < 1e-12 and abs(cos_sum) < 1e-12:
        return values[0] % _MINUTES_PER_DAY
    angle = math.atan2(sin_sum, cos_sum)
    return (angle * _MINUTES_PER_DAY / (2.0 * math.pi)) % _MINUTES_PER_DAY


def _circular_distance(first: float, second: float) -> float:
    """Return the shortest circular distance between two minute-of-day values."""
    forward = (first - second) % _MINUTES_PER_DAY
    backward = (second - first) % _MINUTES_PER_DAY
    return min(forward, backward)


def _minute_of_day(value: datetime) -> float:
    """Return the UTC minute-of-day for an aware datetime."""
    utc_value = to_utc(value)
    return (
        utc_value.hour * 60
        + utc_value.minute
        + utc_value.second / 60.0
        + utc_value.microsecond / 60_000_000.0
    )


def infer_planned_sleep(
    sleep_records: Sequence[SleepRecord], config: MissionConfig = DEFAULT_CONFIG
) -> list[PlannedSleepWindow]:
    """Infer the next habitual sleep window from recent ``SleepRecord`` rows.

    Returns an empty list when there are fewer than
    ``HABITUAL_SLEEP_MIN_RECORDS`` consistent records. Consistency is measured
    with a circular tolerance, so sleep that crosses midnight is handled.

    The result is the **next occurrence** of the inferred window after the most
    recent recorded sleep, as UTC datetimes. This is proposed system logic; the
    sources describe sleep opportunity but do not define how to infer it.
    """
    if not sleep_records:
        return []

    records = list(sleep_records)
    newest_end = max(to_utc(record.sleep_end) for record in records)
    cutoff = newest_end - timedelta(days=config.HABITUAL_SLEEP_LOOKBACK_DAYS)
    recent = [
        record for record in records if to_utc(record.sleep_end) >= cutoff
    ]
    if len(recent) < config.HABITUAL_SLEEP_MIN_RECORDS:
        return []

    starts = [_minute_of_day(record.sleep_start) for record in recent]
    ends = [_minute_of_day(record.sleep_end) for record in recent]
    mean_start = _circular_mean_minutes(starts)
    mean_end = _circular_mean_minutes(ends)
    tolerance = config.HABITUAL_SLEEP_MATCH_TOLERANCE_MINUTES

    consistent = [
        record
        for record, start, end in zip(recent, starts, ends)
        if _circular_distance(start, mean_start) <= tolerance
        and _circular_distance(end, mean_end) <= tolerance
    ]
    if len(consistent) < config.HABITUAL_SLEEP_MIN_RECORDS:
        return []

    mean_start = round(
        _circular_mean_minutes(
            [_minute_of_day(record.sleep_start) for record in consistent]
        )
    ) % _MINUTES_PER_DAY
    mean_end = round(
        _circular_mean_minutes(
            [_minute_of_day(record.sleep_end) for record in consistent]
        )
    ) % _MINUTES_PER_DAY
    duration = (mean_end - mean_start) % _MINUTES_PER_DAY
    if duration <= 0:
        return []

    anchor = newest_end.replace(hour=0, minute=0, second=0, microsecond=0)
    start_time = anchor + timedelta(minutes=mean_start)
    if start_time < newest_end:
        start_time += timedelta(days=1)
    end_time = start_time + timedelta(minutes=duration)
    return [
        PlannedSleepWindow(
            start_time=start_time,
            end_time=end_time,
            source="inferred_habitual_sleep",
        )
    ]


def build_context(
    session: Session,
    crew_id: str,
    window_start: datetime,
    window_end: datetime,
    provider: FatigueSignalProvider,
    config: MissionConfig = DEFAULT_CONFIG,
) -> AstronautContext:
    """Assemble the mission-intelligence context for one astronaut.

    Reads only through ``app.services.history_service`` helpers. Raises
    ``LookupError`` for an unknown crew and ``ValueError`` for an invalid or
    naive time window.

    Tasks are selected by interval overlap, so an activity already in progress
    at ``window_start`` remains visible to safety and conflict rules.
    """
    start = _as_utc(window_start, "window_start")
    end = _as_utc(window_end, "window_end")
    if end <= start:
        raise ValueError("window_end must be after window_start")

    crew = get_crew(session, crew_id)
    if crew is None:
        raise LookupError(f"crew member not found: {crew_id}")

    lookback_start = start - timedelta(days=config.RECENT_SLEEP_LOOKBACK_DAYS)
    sleep_records = get_sleep_records(
        session,
        crew_id,
        since=lookback_start,
        until=end,
        valid_only=True,
    )
    planned_windows = infer_planned_sleep(sleep_records, config)
    fatigue_signal = provider.get_fatigue_signal(session, crew_id)

    horizon_hours = max(1, math.ceil((end - start).total_seconds() / 3600))
    db_tasks = get_upcoming_tasks(
        session,
        crew_id,
        from_time=start,
        horizon_hours=horizon_hours,
    )
    task_views: list[TaskView] = []
    for task in db_tasks:
        if to_utc(task.start_time) >= end:
            continue
        task_views.append(task_from_db(task, config))
        if len(task_views) >= config.MAX_CONTEXT_TASKS:
            break

    recent_records = sorted(
        sleep_records, key=lambda record: to_utc(record.sleep_start), reverse=True
    )[: config.RECENT_SLEEP_MAX_RECORDS]
    recent_sleep = [
        SleepSummary(
            sleep_id=record.id,
            start_time=to_utc(record.sleep_start),
            end_time=to_utc(record.sleep_end),
            interruptions=record.interruptions,
            quality=record.quality,
        )
        for record in recent_records
    ]

    return AstronautContext(
        crew=CrewProfileSummary(
            crew_id=crew.id,
            display_name=crew.display_name,
            role=crew.role,
            sleep_target_hours=crew.sleep_target_hours,
        ),
        recent_sleep=recent_sleep,
        fatigue_signal=fatigue_signal,
        planned_sleep_windows=planned_windows,
        tasks=task_views,
    )
