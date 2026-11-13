"""Tests for the non-blocking candidate-task helper (``task_checks.py``).

``task_checks`` exists so ``mission_service.create_task`` / ``update_task`` can
log advisory warnings without changing their behaviour. The tests confirm that
the helper never raises for a rule finding, never rejects a task, excludes the
task being updated from its own overlap check, and fails open for unknown crews
or invalid windows.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

import pytest

from app.mission.task_checks import (
    CANDIDATE_TASK_ID,
    check_candidate_task,
    log_task_warnings,
)
from app.models import CrewProfile, MissionTask
from app.models.enums import TaskType, WorkloadLevel

UTC = timezone.utc
CREW_ID = "crew-checks"


def _seed(session_factory: Callable[[], Session]) -> None:
    """Insert one crew member and two ordinary tasks."""
    with session_factory() as session:
        session.add(
            CrewProfile(
                id=CREW_ID,
                display_name="Task Check Crew",
                role="pilot",
                sleep_target_hours=8.0,
            )
        )
        session.add(
            MissionTask(
                id="existing-task",
                crew_id=CREW_ID,
                title="Existing task",
                task_type=TaskType.maintenance,
                start_time=datetime(2026, 11, 13, 12, 0, tzinfo=UTC),
                end_time=datetime(2026, 11, 13, 13, 0, tzinfo=UTC),
                workload_level=WorkloadLevel.high,
                is_critical=False,
            )
        )
        session.add(
            MissionTask(
                id="night-task",
                crew_id=CREW_ID,
                title="Night task",
                task_type=TaskType.maintenance,
                start_time=datetime(2026, 11, 13, 3, 0, tzinfo=UTC),
                end_time=datetime(2026, 11, 13, 4, 0, tzinfo=UTC),
                workload_level=WorkloadLevel.high,
                is_critical=False,
            )
        )
        session.commit()


def test_candidate_in_wocl_produces_conflict(session_factory: Callable[[], Session]) -> None:
    """A candidate at 03:00 UTC is flagged without raising."""
    _seed(session_factory)
    with session_factory() as session:
        result = check_candidate_task(
            session,
            CREW_ID,
            datetime(2026, 11, 13, 3, 0, tzinfo=UTC),
            datetime(2026, 11, 13, 4, 0, tzinfo=UTC),
            task_type=TaskType.maintenance,
            workload_level=WorkloadLevel.high,
            title="Candidate night task",
        )
    assert result.evaluated is True
    assert result.conflicts
    assert all(CANDIDATE_TASK_ID in conflict.task_ids for conflict in result.conflicts)


def test_candidate_short_recovery_gap_is_detected(
    session_factory: Callable[[], Session],
) -> None:
    """A demanding candidate shortly after another demanding task is flagged."""
    _seed(session_factory)
    with session_factory() as session:
        result = check_candidate_task(
            session,
            CREW_ID,
            datetime(2026, 11, 13, 13, 10, tzinfo=UTC),
            datetime(2026, 11, 13, 14, 10, tzinfo=UTC),
            workload_level=WorkloadLevel.high,
            title="Candidate recovery gap",
        )
    recovery = [
        conflict
        for conflict in result.conflicts
        if conflict.conflict_type.value == "insufficient_recovery_gap"
    ]
    assert recovery
    assert any(
        "existing-task" in conflict.task_ids
        and CANDIDATE_TASK_ID in conflict.task_ids
        for conflict in recovery
    )


def test_exclude_task_id_removes_self_overlap(
    session_factory: Callable[[], Session],
) -> None:
    """An update must not compare the candidate with the row it replaces."""
    _seed(session_factory)
    with session_factory() as session:
        result = check_candidate_task(
            session,
            CREW_ID,
            datetime(2026, 11, 13, 13, 10, tzinfo=UTC),
            datetime(2026, 11, 13, 14, 10, tzinfo=UTC),
            workload_level=WorkloadLevel.high,
            title="Updated task",
            exclude_task_id="existing-task",
        )
    assert result.evaluated is True
    assert not any(
        "existing-task" in conflict.task_ids for conflict in result.conflicts
    )


def test_unknown_crew_fails_open(session_factory: Callable[[], Session]) -> None:
    """An unknown crew is left to the service's existing 404 handling."""
    _seed(session_factory)
    with session_factory() as session:
        result = check_candidate_task(
            session,
            "crew-missing",
            datetime(2026, 11, 13, 3, 0, tzinfo=UTC),
            datetime(2026, 11, 13, 4, 0, tzinfo=UTC),
        )
    assert result.evaluated is False
    assert result.conflicts == []
    assert result.warnings == []


def test_invalid_window_fails_open(session_factory: Callable[[], Session]) -> None:
    """A reversed window is not evaluated instead of raising."""
    _seed(session_factory)
    with session_factory() as session:
        result = check_candidate_task(
            session,
            CREW_ID,
            datetime(2026, 11, 13, 4, 0, tzinfo=UTC),
            datetime(2026, 11, 13, 3, 0, tzinfo=UTC),
        )
    assert result.evaluated is False


def test_log_task_warnings_never_raises_and_logs(
    session_factory: Callable[[], Session], caplog: pytest.LogCaptureFixture
) -> None:
    """The service helper logs findings at WARNING and returns the result."""
    _seed(session_factory)
    with session_factory() as session, caplog.at_level(
        logging.WARNING, logger="app.mission.task_checks"
    ):
        result = log_task_warnings(
            session,
            CREW_ID,
            datetime(2026, 11, 13, 3, 0, tzinfo=UTC),
            datetime(2026, 11, 13, 4, 0, tzinfo=UTC),
            task_type=TaskType.maintenance,
            workload_level=WorkloadLevel.high,
            title="Candidate night task",
        )
    assert result.evaluated is True
    messages = [record.getMessage() for record in caplog.records]
    assert any("Non-blocking mission advisory" in message for message in messages)
    assert all("crew-checks" in message for message in messages)


def test_log_task_warnings_invalid_window_does_not_log(
    session_factory: Callable[[], Session], caplog: pytest.LogCaptureFixture
) -> None:
    """A window that cannot be evaluated produces no advisory log."""
    _seed(session_factory)
    with session_factory() as session, caplog.at_level(
        logging.WARNING, logger="app.mission.task_checks"
    ):
        result = log_task_warnings(
            session,
            "crew-missing",
            datetime(2026, 11, 13, 3, 0, tzinfo=UTC),
            datetime(2026, 11, 13, 4, 0, tzinfo=UTC),
        )
    assert result.evaluated is False
    assert not caplog.records
