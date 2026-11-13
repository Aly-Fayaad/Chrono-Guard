"""Tests for the database adapters (``adapters.py``).

These tests exercise the documented mapping assumptions for fields that do not
exist in ``MissionTask``, the categorical fatigue providers, habitual-sleep
inference, and the ``build_context`` data-access contract.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from app.mission.adapters import (
    AssessmentFatigueProvider,
    StaticFatigueProvider,
    build_context,
    infer_planned_sleep,
    task_from_db,
)
from app.mission.config import DEFAULT_CONFIG
from app.mission.models import (
    FatigueLevel,
    FatigueSignal,
    Priority,
    TaskCategory,
    TaskStatus,
    WorkloadLevel,
)
from app.models.assessment import Assessment
from app.models.checkin import SleepRecord
from app.models.enums import AssessmentStatus, QualityFlag, TaskType, WorkloadLevel as DbWorkloadLevel
from app.models.mission import MissionTask

UTC = timezone.utc
WINDOW_START = datetime(2026, 11, 13, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 11, 14, 0, 0, tzinfo=UTC)


def _add_task(
    session: Session,
    crew_id: str,
    *,
    task_id: str,
    start: datetime,
    end: datetime,
    title: str = "Scheduled task",
    task_type: TaskType = TaskType.maintenance,
    workload: DbWorkloadLevel = DbWorkloadLevel.medium,
    is_critical: bool = False,
) -> MissionTask:
    """Insert one ``MissionTask`` and return the persisted instance."""
    task = MissionTask(
        id=task_id,
        crew_id=crew_id,
        title=title,
        task_type=task_type,
        start_time=start,
        end_time=end,
        workload_level=workload,
        is_critical=is_critical,
    )
    session.add(task)
    session.commit()
    return task


def _add_sleep(
    session: Session,
    crew_id: str,
    *,
    sleep_id: str,
    start: datetime,
    end: datetime,
    quality: QualityFlag = QualityFlag.valid,
    interruptions: int = 0,
) -> SleepRecord:
    """Insert one ``SleepRecord`` and return the persisted instance."""
    record = SleepRecord(
        id=sleep_id,
        crew_id=crew_id,
        sleep_start=start,
        sleep_end=end,
        duration_hours=(end - start).total_seconds() / 3600,
        interruptions=interruptions,
        quality=quality,
    )
    session.add(record)
    session.commit()
    return record


def _sleep_row(
    start: datetime, end: datetime, sleep_id: str = "sleep-x"
) -> SleepRecord:
    """Build an unpersisted ``SleepRecord`` for pure-function tests."""
    return SleepRecord(
        id=sleep_id,
        crew_id="crew-mission",
        sleep_start=start,
        sleep_end=end,
        duration_hours=(end - start).total_seconds() / 3600,
        interruptions=0,
        quality=QualityFlag.valid,
    )


def _add_assessment(
    session: Session,
    crew_id: str,
    *,
    assessment_id: str,
    status: AssessmentStatus,
    created_at: datetime,
    contributing_factors: list | None = None,
) -> Assessment:
    """Insert one ``Assessment`` and return the persisted instance."""
    assessment = Assessment(
        id=assessment_id,
        crew_id=crew_id,
        status=status,
        summary="Test summary",
        explanation="Test explanation",
        contributing_factors=contributing_factors or [],
        engine_version="test-1",
        created_at=created_at,
    )
    session.add(assessment)
    session.commit()
    return assessment


# ---------------------------------------------------------------------------
# task_from_db
# ---------------------------------------------------------------------------


def test_task_from_db_maps_database_fields_and_defaults(
    session: Session, crew_id: str
) -> None:
    """Database columns map across; missing fields use documented defaults."""
    row = _add_task(
        session,
        crew_id,
        task_id="task-1",
        start=datetime(2026, 11, 13, 9, 0, tzinfo=UTC),
        end=datetime(2026, 11, 13, 10, 30, tzinfo=UTC),
        title="Inspect airlock",
        task_type=TaskType.maintenance,
        workload=DbWorkloadLevel.medium,
        is_critical=False,
    )

    view = task_from_db(row)

    assert view.task_id == "task-1"
    assert view.astronaut_id == crew_id
    assert view.name == "Inspect airlock"
    assert view.category is TaskCategory.maintenance
    assert view.start_time == datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
    assert view.duration_minutes == 90
    assert view.priority is Priority.medium
    assert view.workload_level is WorkloadLevel.medium
    assert view.required_alertness == DEFAULT_CONFIG.ALERTNESS_BY_WORKLOAD[WorkloadLevel.medium]
    assert view.status is TaskStatus.planned
    assert view.is_critical is False


def test_task_from_db_critical_low_workload_raises_alertness(
    session: Session, crew_id: str
) -> None:
    """Critical tasks get critical priority and at least the critical alertness."""
    row = _add_task(
        session,
        crew_id,
        task_id="task-2",
        start=datetime(2026, 11, 13, 9, 0, tzinfo=UTC),
        end=datetime(2026, 11, 13, 10, 0, tzinfo=UTC),
        workload=DbWorkloadLevel.low,
        is_critical=True,
    )

    view = task_from_db(row)

    assert view.priority is DEFAULT_CONFIG.CRITICAL_PRIORITY
    assert view.required_alertness == DEFAULT_CONFIG.CRITICAL_TASK_ALERTNESS_REQUIREMENT


def test_task_from_db_critical_high_workload_is_capped(
    session: Session, crew_id: str
) -> None:
    """Critical high-workload alertness never exceeds the 1-5 scale."""
    row = _add_task(
        session,
        crew_id,
        task_id="task-3",
        start=datetime(2026, 11, 13, 9, 0, tzinfo=UTC),
        end=datetime(2026, 11, 13, 10, 0, tzinfo=UTC),
        workload=DbWorkloadLevel.high,
        is_critical=True,
    )

    view = task_from_db(row)

    assert view.required_alertness == DEFAULT_CONFIG.MAX_ALERTNESS


def test_task_from_db_normalises_non_utc_datetimes(
    session: Session, crew_id: str
) -> None:
    """Aware non-UTC task times are converted to UTC."""
    offset = timezone(timedelta(hours=2))
    row = _add_task(
        session,
        crew_id,
        task_id="task-4",
        start=datetime(2026, 11, 13, 11, 0, tzinfo=offset),
        end=datetime(2026, 11, 13, 12, 0, tzinfo=offset),
    )

    view = task_from_db(row)

    assert view.start_time == datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
    assert view.start_time.utcoffset() == timedelta(0)


# ---------------------------------------------------------------------------
# Fatigue providers
# ---------------------------------------------------------------------------


def test_assessment_provider_without_assessment_is_unknown(
    session: Session, crew_id: str
) -> None:
    """No assessment yields an explicit unknown signal, not a number."""
    signal = AssessmentFatigueProvider().get_fatigue_signal(session, crew_id)

    assert signal.level is FatigueLevel.unknown
    assert signal.source == "assessment:none"
    assert signal.contributing_factors == []


def test_assessment_provider_maps_insufficient_data_to_unknown(
    session: Session, crew_id: str
) -> None:
    """``insufficient_data`` maps to unknown rather than to a fabricated level."""
    _add_assessment(
        session,
        crew_id,
        assessment_id="assessment-insufficient",
        status=AssessmentStatus.insufficient_data,
        created_at=datetime(2026, 11, 13, 8, 0, tzinfo=UTC),
        contributing_factors=[{"sleep_hours": 5.5}],
    )

    signal = AssessmentFatigueProvider().get_fatigue_signal(session, crew_id)

    assert signal.level is FatigueLevel.unknown
    assert signal.source == "assessment:assessment-insufficient"


def test_assessment_provider_maps_monitor_and_keeps_raw_factors(
    session: Session, crew_id: str
) -> None:
    """Assessment status maps directly; factors pass through without typing."""
    _add_assessment(
        session,
        crew_id,
        assessment_id="assessment-monitor",
        status=AssessmentStatus.monitor,
        created_at=datetime(2026, 11, 13, 8, 0, tzinfo=UTC),
        contributing_factors=[
            {"factor": "reported_sleepiness", "level": "moderate"},
            "loose-text-factor",
            42,
        ],
    )

    signal = AssessmentFatigueProvider().get_fatigue_signal(session, crew_id)

    assert signal.level is FatigueLevel.monitor
    assert signal.contributing_factors == [
        {"factor": "reported_sleepiness", "level": "moderate"}
    ]


def test_assessment_provider_uses_latest_assessment(
    session: Session, crew_id: str
) -> None:
    """The newest assessment by ``created_at`` supplies the signal."""
    _add_assessment(
        session,
        crew_id,
        assessment_id="assessment-old",
        status=AssessmentStatus.elevated_concern,
        created_at=datetime(2026, 11, 12, 8, 0, tzinfo=UTC),
    )
    _add_assessment(
        session,
        crew_id,
        assessment_id="assessment-new",
        status=AssessmentStatus.no_flag,
        created_at=datetime(2026, 11, 13, 8, 0, tzinfo=UTC),
    )

    signal = AssessmentFatigueProvider().get_fatigue_signal(session, crew_id)

    assert signal.level is FatigueLevel.no_flag
    assert signal.source == "assessment:assessment-new"


def test_static_provider_returns_configured_signal(
    session: Session, crew_id: str
) -> None:
    """The static provider never reads the database."""
    configured = FatigueSignal(level=FatigueLevel.elevated_concern, source="test")
    provider = StaticFatigueProvider(configured)

    assert provider.get_fatigue_signal(session, crew_id) is configured


# ---------------------------------------------------------------------------
# infer_planned_sleep
# ---------------------------------------------------------------------------


def test_infer_planned_sleep_without_records_returns_nothing() -> None:
    """No sleep history cannot produce a window."""
    assert infer_planned_sleep([]) == []


def test_infer_planned_sleep_with_too_few_records_returns_nothing() -> None:
    """Fewer records than the configured minimum cannot produce a window."""
    records = [
        _sleep_row(
            datetime(2026, 11, 11, 22, 0, tzinfo=UTC),
            datetime(2026, 11, 12, 6, 0, tzinfo=UTC),
        ),
        _sleep_row(
            datetime(2026, 11, 12, 22, 0, tzinfo=UTC),
            datetime(2026, 11, 13, 6, 0, tzinfo=UTC),
        ),
    ]

    assert infer_planned_sleep(records) == []


def test_infer_planned_sleep_returns_habitual_window_across_midnight() -> None:
    """Consistent records produce the next occurrence of the same window."""
    records = [
        _sleep_row(
            datetime(2026, 11, 10, 21, 50, tzinfo=UTC),
            datetime(2026, 11, 11, 5, 50, tzinfo=UTC),
            sleep_id="sleep-1",
        ),
        _sleep_row(
            datetime(2026, 11, 11, 22, 0, tzinfo=UTC),
            datetime(2026, 11, 12, 6, 0, tzinfo=UTC),
            sleep_id="sleep-2",
        ),
        _sleep_row(
            datetime(2026, 11, 12, 22, 10, tzinfo=UTC),
            datetime(2026, 11, 13, 6, 10, tzinfo=UTC),
            sleep_id="sleep-3",
        ),
    ]

    windows = infer_planned_sleep(records)

    assert len(windows) == 1
    window = windows[0]
    assert window.source == "inferred_habitual_sleep"
    assert window.start_time == datetime(2026, 11, 13, 22, 0, tzinfo=UTC)
    assert window.end_time == datetime(2026, 11, 14, 6, 0, tzinfo=UTC)
    assert window.duration_minutes == 480


def test_infer_planned_sleep_returns_nothing_when_records_disagree() -> None:
    """Inconsistent sleep timing must not be presented as a habitual window."""
    records = [
        _sleep_row(
            datetime(2026, 11, 10, 22, 0, tzinfo=UTC),
            datetime(2026, 11, 11, 6, 0, tzinfo=UTC),
            sleep_id="sleep-1",
        ),
        _sleep_row(
            datetime(2026, 11, 11, 2, 0, tzinfo=UTC),
            datetime(2026, 11, 11, 10, 0, tzinfo=UTC),
            sleep_id="sleep-2",
        ),
        _sleep_row(
            datetime(2026, 11, 12, 10, 0, tzinfo=UTC),
            datetime(2026, 11, 12, 18, 0, tzinfo=UTC),
            sleep_id="sleep-3",
        ),
    ]

    assert infer_planned_sleep(records) == []


# ---------------------------------------------------------------------------
# build_context
# ---------------------------------------------------------------------------


def test_build_context_rejects_unknown_crew(session: Session) -> None:
    """An unknown crew id is an explicit lookup error, not empty data."""
    with pytest.raises(LookupError):
        build_context(
            session,
            "crew-missing",
            WINDOW_START,
            WINDOW_END,
            StaticFatigueProvider(FatigueSignal(level=FatigueLevel.unknown, source="t")),
        )


def test_build_context_rejects_naive_window(
    session: Session, crew_id: str
) -> None:
    """Naive evaluation windows are rejected."""
    with pytest.raises(ValueError):
        build_context(
            session,
            crew_id,
            datetime(2026, 11, 13, 0, 0),
            WINDOW_END,
            StaticFatigueProvider(FatigueSignal(level=FatigueLevel.unknown, source="t")),
        )


def test_build_context_rejects_empty_or_reversed_window(
    session: Session, crew_id: str
) -> None:
    """The evaluation window must have a positive duration."""
    provider = StaticFatigueProvider(
        FatigueSignal(level=FatigueLevel.unknown, source="t")
    )
    with pytest.raises(ValueError):
        build_context(session, crew_id, WINDOW_END, WINDOW_START, provider)
    with pytest.raises(ValueError):
        build_context(session, crew_id, WINDOW_START, WINDOW_START, provider)


def test_build_context_assembles_only_valid_and_in_window_data(
    session: Session, crew_id: str
) -> None:
    """Context contains valid sleep, in-window tasks, and the inferred window."""
    _add_sleep(
        session,
        crew_id,
        sleep_id="sleep-valid-1",
        start=datetime(2026, 11, 10, 22, 0, tzinfo=UTC),
        end=datetime(2026, 11, 11, 6, 0, tzinfo=UTC),
    )
    _add_sleep(
        session,
        crew_id,
        sleep_id="sleep-valid-2",
        start=datetime(2026, 11, 11, 22, 10, tzinfo=UTC),
        end=datetime(2026, 11, 12, 6, 10, tzinfo=UTC),
    )
    _add_sleep(
        session,
        crew_id,
        sleep_id="sleep-valid-3",
        start=datetime(2026, 11, 12, 21, 50, tzinfo=UTC),
        end=datetime(2026, 11, 13, 5, 50, tzinfo=UTC),
    )
    _add_sleep(
        session,
        crew_id,
        sleep_id="sleep-questionable",
        start=datetime(2026, 11, 12, 23, 0, tzinfo=UTC),
        end=datetime(2026, 11, 13, 7, 0, tzinfo=UTC),
        quality=QualityFlag.questionable,
    )

    _add_task(
        session,
        crew_id,
        task_id="task-in-1",
        start=datetime(2026, 11, 13, 9, 0, tzinfo=UTC),
        end=datetime(2026, 11, 13, 10, 30, tzinfo=UTC),
        is_critical=True,
    )
    _add_task(
        session,
        crew_id,
        task_id="task-in-2",
        start=datetime(2026, 11, 13, 23, 30, tzinfo=UTC),
        end=datetime(2026, 11, 14, 0, 30, tzinfo=UTC),
    )
    _add_task(
        session,
        crew_id,
        task_id="task-at-end",
        start=datetime(2026, 11, 14, 0, 0, tzinfo=UTC),
        end=datetime(2026, 11, 14, 1, 0, tzinfo=UTC),
    )
    _add_task(
        session,
        crew_id,
        task_id="task-before-window",
        start=datetime(2026, 11, 12, 23, 0, tzinfo=UTC),
        end=datetime(2026, 11, 12, 23, 30, tzinfo=UTC),
    )

    provider = StaticFatigueProvider(
        FatigueSignal(level=FatigueLevel.monitor, source="test")
    )
    context = build_context(session, crew_id, WINDOW_START, WINDOW_END, provider)

    assert context.crew.crew_id == crew_id
    assert context.crew.display_name == "Mission Test Crew"
    assert context.crew.sleep_target_hours == 7.5

    assert [summary.sleep_id for summary in context.recent_sleep] == [
        "sleep-valid-3",
        "sleep-valid-2",
        "sleep-valid-1",
    ]
    assert all(
        summary.quality is QualityFlag.valid for summary in context.recent_sleep
    )

    assert [task.task_id for task in context.tasks] == ["task-in-1", "task-in-2"]
    assert context.tasks[0].priority is DEFAULT_CONFIG.CRITICAL_PRIORITY
    assert context.tasks[1].priority is Priority.medium

    assert len(context.planned_sleep_windows) == 1
    assert context.planned_sleep_windows[0].start_time == datetime(
        2026, 11, 13, 22, 0, tzinfo=UTC
    )
    assert context.planned_sleep_windows[0].duration_minutes == 480

    assert context.fatigue_signal.level is FatigueLevel.monitor


def test_build_context_without_history_degrades_to_empty_lists(
    session: Session, crew_id: str
) -> None:
    """Missing sleep and task data produces empty lists, not invented values."""
    provider = StaticFatigueProvider(
        FatigueSignal(level=FatigueLevel.unknown, source="test")
    )

    context = build_context(session, crew_id, WINDOW_START, WINDOW_END, provider)

    assert context.recent_sleep == []
    assert context.planned_sleep_windows == []
    assert context.tasks == []
    assert context.fatigue_signal.level is FatigueLevel.unknown


# ---------------------------------------------------------------------------
# Unknown fatigue must never become a number
# ---------------------------------------------------------------------------


def test_unknown_fatigue_is_never_converted_to_a_number(
    session: Session, crew_id: str
) -> None:
    """An unknown signal stays categorical even when factors contain numbers."""
    _add_assessment(
        session,
        crew_id,
        assessment_id="assessment-insufficient",
        status=AssessmentStatus.insufficient_data,
        created_at=datetime(2026, 11, 13, 8, 0, tzinfo=UTC),
        contributing_factors=[{"sleep_hours": 5.5, "confidence": 0.2}],
    )

    signal = AssessmentFatigueProvider().get_fatigue_signal(session, crew_id)

    assert signal.level is FatigueLevel.unknown
    assert signal.level.value == "unknown"
    assert "score" not in signal.model_dump()
    assert set(FatigueSignal.model_fields) == {
        "level",
        "source",
        "contributing_factors",
    }
    top_level_values = [
        value
        for key, value in signal.model_dump().items()
        if key != "contributing_factors"
    ]
    assert not any(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in top_level_values
    )

    provider = StaticFatigueProvider(signal)
    context = build_context(session, crew_id, WINDOW_START, WINDOW_END, provider)

    assert context.fatigue_signal.level is FatigueLevel.unknown
    assert set(context.model_dump()["fatigue_signal"]) == {
        "level",
        "source",
        "contributing_factors",
    }
