"""Tests for the mission-intelligence transfer objects (``models.py``).

The tests cover UTC handling, window validation, the categorical fatigue
contract (no numeric score), and the field sets required by FR-03 and FR-06 of
``docs/02_requirements.md``.
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.mission.models import (
    AstronautContext,
    Conflict,
    ConflictType,
    CrewProfileSummary,
    FatigueLevel,
    FatigueSignal,
    PlannedSleepWindow,
    Priority,
    Recommendation,
    RecommendationType,
    Severity,
    SleepSummary,
    TaskCategory,
    TaskStatus,
    TaskView,
    WorkloadLevel,
)
from app.models.enums import QualityFlag

UTC = timezone.utc


def _task_view(**overrides: object) -> TaskView:
    """Build a valid ``TaskView`` and apply overrides."""
    values: dict[str, object] = {
        "task_id": "task-1",
        "astronaut_id": "crew-1",
        "name": "Inspect airlock",
        "category": TaskCategory.maintenance,
        "start_time": datetime(2026, 11, 13, 9, 0, tzinfo=UTC),
        "end_time": datetime(2026, 11, 13, 10, 30, tzinfo=UTC),
        "priority": Priority.high,
        "workload_level": WorkloadLevel.medium,
        "required_alertness": 3,
        "status": TaskStatus.planned,
        "is_critical": False,
    }
    values.update(overrides)
    return TaskView.model_validate(values)


def test_task_category_contains_database_and_new_values() -> None:
    """TaskCategory keeps the database values and adds the three new ones."""
    assert {category.value for category in TaskCategory} == {
        "eva",
        "maintenance",
        "science",
        "exercise",
        "medical",
        "rest",
        "other",
        "sleep",
        "communication",
        "rest_recovery",
    }


def test_task_view_computes_duration_and_normalises_to_utc() -> None:
    """A non-UTC aware datetime is converted to UTC, duration is computed."""
    view = _task_view(
        start_time=datetime(2026, 11, 13, 11, 0, tzinfo=timezone(timedelta(hours=2))),
        end_time=datetime(2026, 11, 13, 12, 30, tzinfo=timezone(timedelta(hours=2))),
    )

    assert view.start_time == datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
    assert view.start_time.utcoffset() == timedelta(0)
    assert view.duration_minutes == 90


@pytest.mark.parametrize(
    "field_name",
    ["start_time", "end_time"],
)
def test_task_view_rejects_naive_datetimes(field_name: str) -> None:
    """Naive datetimes are rejected instead of being guessed as local time."""
    with pytest.raises(ValidationError):
        _task_view(**{field_name: datetime(2026, 11, 13, 9, 0)})


def test_task_view_rejects_end_not_after_start() -> None:
    """A task window must have a positive duration."""
    with pytest.raises(ValidationError):
        _task_view(end_time=datetime(2026, 11, 13, 9, 0, tzinfo=UTC))


def test_task_view_rejects_alertness_outside_scale() -> None:
    """Required alertness is bounded to the project's 1-5 scale."""
    with pytest.raises(ValidationError):
        _task_view(required_alertness=0)


def test_task_view_is_frozen() -> None:
    """Transfer objects must not be mutated after construction."""
    view = _task_view()
    with pytest.raises(ValidationError):
        view.name = "changed"  # type: ignore[misc]


def test_sleep_summary_computes_duration_and_rejects_negative_window() -> None:
    """Sleep summaries compute duration and validate the interval."""
    summary = SleepSummary(
        sleep_id="sleep-1",
        start_time=datetime(2026, 11, 12, 22, 0, tzinfo=UTC),
        end_time=datetime(2026, 11, 13, 6, 0, tzinfo=UTC),
        interruptions=1,
        quality=QualityFlag.valid,
    )
    assert summary.duration_minutes == 480

    with pytest.raises(ValidationError):
        SleepSummary(
            sleep_id="sleep-2",
            start_time=datetime(2026, 11, 13, 6, 0, tzinfo=UTC),
            end_time=datetime(2026, 11, 13, 6, 0, tzinfo=UTC),
            interruptions=0,
            quality=QualityFlag.valid,
        )


def test_planned_sleep_window_validates_window_and_source() -> None:
    """Planned windows carry a source and enforce a positive duration."""
    window = PlannedSleepWindow(
        start_time=datetime(2026, 11, 13, 22, 0, tzinfo=UTC),
        end_time=datetime(2026, 11, 14, 6, 0, tzinfo=UTC),
    )
    assert window.duration_minutes == 480
    assert window.source == "inferred_habitual_sleep"

    with pytest.raises(ValidationError):
        PlannedSleepWindow(
            start_time=datetime(2026, 11, 14, 6, 0, tzinfo=UTC),
            end_time=datetime(2026, 11, 13, 22, 0, tzinfo=UTC),
        )


def test_fatigue_signal_has_no_numeric_score() -> None:
    """A fatigue signal is categorical only; there is no score field."""
    assert set(FatigueSignal.model_fields) == {
        "level",
        "source",
        "contributing_factors",
    }
    signal = FatigueSignal(
        level=FatigueLevel.unknown,
        source="assessment:none",
        contributing_factors=[{"key": "sleep_debt", "value": "unknown"}],
    )
    assert signal.level is FatigueLevel.unknown
    assert "score" not in signal.model_dump()

    with pytest.raises(ValidationError):
        FatigueSignal(level=FatigueLevel.unknown, source="x", score=3)  # type: ignore[call-arg]


def test_fatigue_level_has_the_four_categorical_values() -> None:
    """The fatigue scale is categorical and matches the requirements."""
    assert {level.value for level in FatigueLevel} == {
        "unknown",
        "no_flag",
        "monitor",
        "elevated_concern",
    }


def test_conflict_has_the_fr03_fields() -> None:
    """Conflict exposes rule, category, severity, interval, evidence, config."""
    conflict = Conflict(
        rule_id="R-SLEEP-001",
        conflict_type=ConflictType.sleep_window_conflict,
        severity=Severity.high,
        astronaut_id="crew-1",
        task_ids=["task-1"],
        affected_start=datetime(2026, 11, 13, 22, 0, tzinfo=UTC),
        affected_end=datetime(2026, 11, 13, 23, 0, tzinfo=UTC),
        explanation="Task overlaps the protected sleep window.",
        suggested_action="Review moving the task under rule R-SLEEP-001.",
        source_ids=["NASA-HRP-Sleep-Risk"],
        config_keys=["PROTECTED_SLEEP_WINDOW_START_HOUR"],
    )

    assert conflict.conflict_id
    assert conflict.task_id == "task-1"
    assert conflict.task_ids == ["task-1"]
    assert conflict.source_ids == ["NASA-HRP-Sleep-Risk"]
    assert conflict.config_keys == ["PROTECTED_SLEEP_WINDOW_START_HOUR"]


def test_conflict_rejects_naive_datetimes_and_reversed_interval() -> None:
    """Conflicts use UTC-aware datetimes and an ordered interval."""
    base: dict[str, object] = {
        "rule_id": "R-1",
        "conflict_type": ConflictType.task_overlap,
        "severity": Severity.low,
        "astronaut_id": "crew-1",
        "affected_start": datetime(2026, 11, 13, 9, 0, tzinfo=UTC),
        "affected_end": datetime(2026, 11, 13, 10, 0, tzinfo=UTC),
        "explanation": "Overlap.",
    }

    with pytest.raises(ValidationError):
        Conflict.model_validate({**base, "affected_start": datetime(2026, 11, 13, 9, 0)})

    with pytest.raises(ValidationError):
        Conflict.model_validate(
            {
                **base,
                "affected_start": datetime(2026, 11, 13, 10, 0, tzinfo=UTC),
                "affected_end": datetime(2026, 11, 13, 9, 0, tzinfo=UTC),
            }
        )


def _recommendation_values(**overrides: object) -> dict[str, object]:
    """Build a valid ``Recommendation`` payload and apply overrides."""
    values: dict[str, object] = {
        "recommendation_type": RecommendationType.review_task_timing,
        "related_conflict_id": "cf_1234567890abcdef",
        "astronaut_id": "crew-1",
        "countermeasure_id": "CM-01",
        "countermeasure_name": "Protect / Reschedule Sleep Opportunity",
        "rule_id": "R-SLEEP-WINDOW-01",
        "reason": "The task overlaps the planned sleep window.",
        "suggested_action": (
            "Consider moving the task outside the sleep window. Review under "
            "rule R-SLEEP-WINDOW-01; this may reduce risk under rule "
            "R-SLEEP-WINDOW-01."
        ),
        "expected_benefit": (
            "Removes the overlap with the planned sleep window under rule "
            "R-SLEEP-WINDOW-01."
        ),
        "priority": Priority.high,
        "explanation": "Advisory only; no physiological effect is claimed.",
        "source_ids": ["NASA-HRP-Sleep-Risk", "NASA-STD-3001-Vol2"],
        "preconditions": ["Mission planner confirms the task can move."],
        "warnings": ["Advisory only."],
        "requires_mission_approval": True,
        "advisory_text": (
            "Moving this task may reduce risk under rule R-SLEEP-WINDOW-01."
        ),
    }
    values.update(overrides)
    return values


def test_recommendation_has_the_fr06_fields() -> None:
    """Recommendation exposes type, conflict link, advice, and review flags."""
    recommendation = Recommendation.model_validate(_recommendation_values())

    assert recommendation.recommendation_id
    assert recommendation.recommendation_type is RecommendationType.review_task_timing
    assert recommendation.related_conflict_id == "cf_1234567890abcdef"
    assert recommendation.astronaut_id == "crew-1"
    assert recommendation.requires_mission_approval is True
    assert recommendation.requires_medical_review is False
    assert "may reduce risk under rule" in recommendation.advisory_text
    assert recommendation.warnings == ["Advisory only."]


def test_recommendation_type_has_the_five_action_families() -> None:
    """The recommendation contract exposes exactly the five Phase 5A types."""
    assert {item.value for item in RecommendationType} == {
        "review_task_timing",
        "identify_recovery_opportunity",
        "redistribute_demanding_tasks",
        "review_sleep_schedule",
        "evaluate_lighting_schedule",
    }


def test_recommendation_requires_advisory_text() -> None:
    """A recommendation without advisory wording is invalid."""
    values = _recommendation_values()
    values.pop("advisory_text")

    with pytest.raises(ValidationError):
        Recommendation.model_validate(values)


def test_astronaut_context_defaults_to_empty_collections() -> None:
    """Context lists default to empty and accept a nested task view."""
    context = AstronautContext(
        crew=CrewProfileSummary(
            crew_id="crew-1",
            display_name="Crew One",
            role="commander",
            sleep_target_hours=7.5,
        ),
        fatigue_signal=FatigueSignal(level=FatigueLevel.unknown, source="test"),
    )

    assert context.recent_sleep == []
    assert context.planned_sleep_windows == []
    assert context.tasks == []
