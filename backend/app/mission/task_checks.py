"""Non-blocking task checks for ``mission_service`` integration.

``mission_service.create_task`` and ``update_task`` are owned by another member
and may only be edited with explicit approval. This module provides the helper
those functions can call **without changing their behaviour**: it evaluates a
candidate task window against the Phase 4 rules and emits log warnings. It never
raises for a conflict, never rejects a task, and never writes to the database.

The candidate task does not exist in the database yet, so it is built as a
``TaskView`` and appended to a read-only context. Existing tasks are loaded over
``PLANNING_HORIZON_HOURS`` before and after the candidate so the recovery,
circadian, sleep-window, and workload rules see the surrounding schedule.

This is decision support only. A logged warning is not a validation failure and
does not change the task's stored state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlmodel import Session

from app.core.database import to_utc
from app.mission.adapters import (
    AssessmentFatigueProvider,
    build_context,
    required_alertness,
)
from app.mission.config import DEFAULT_CONFIG, MissionConfig
from app.mission.conflicts import detect_conflicts
from app.mission.models import (
    Conflict,
    DataWarning,
    TaskCategory,
    TaskStatus,
    TaskView,
)
from app.models.enums import TaskType, WorkloadLevel

LOGGER = logging.getLogger(__name__)

CANDIDATE_TASK_ID = "__candidate_task__"
"""Reserved id used only inside the temporary evaluation context."""


@dataclass(frozen=True)
class TaskCheckResult:
    """Conflicts and data warnings that involve a candidate task.

    ``evaluated`` is false when the crew is unknown or the surrounding context
    cannot be built. In that case the caller must not treat the empty lists as a
    clean result; the normal service validation still applies.
    """

    evaluated: bool
    conflicts: list[Conflict] = field(default_factory=list)
    warnings: list[DataWarning] = field(default_factory=list)


def _candidate_task(
    crew_id: str,
    start_time: datetime,
    end_time: datetime,
    *,
    task_type: TaskType,
    workload_level: WorkloadLevel,
    is_critical: bool,
    title: str,
    config: MissionConfig,
) -> TaskView:
    """Build the transient ``TaskView`` for the candidate window."""
    workload = WorkloadLevel(workload_level.value)
    priority = (
        config.CRITICAL_PRIORITY
        if is_critical
        else config.PRIORITY_BY_WORKLOAD[workload]
    )
    return TaskView(
        task_id=CANDIDATE_TASK_ID,
        astronaut_id=crew_id,
        name=title.strip() or "Candidate mission task",
        category=TaskCategory(task_type.value),
        start_time=to_utc(start_time),
        end_time=to_utc(end_time),
        priority=priority,
        workload_level=workload,
        required_alertness=required_alertness(workload, is_critical, config),
        status=TaskStatus.planned,
        is_critical=is_critical,
    )


def check_candidate_task(
    session: Session,
    crew_id: str,
    start_time: datetime,
    end_time: datetime,
    *,
    task_type: TaskType = TaskType.other,
    workload_level: WorkloadLevel = WorkloadLevel.medium,
    is_critical: bool = False,
    title: str = "Candidate mission task",
    exclude_task_id: str | None = None,
    config: MissionConfig = DEFAULT_CONFIG,
) -> TaskCheckResult:
    """Evaluate a candidate task without persisting or rejecting it.

    Args:
        session: Read-only database session.
        crew_id: Crew member the task would belong to.
        start_time: Candidate start (naive values are treated as UTC by the
            surrounding adapters, matching the existing service behaviour).
        end_time: Candidate end.
        task_type: Database task type.
        workload_level: Database workload level.
        is_critical: Database critical flag.
        title: Task title, used only in advisory explanations.
        exclude_task_id: Existing task id to omit, so an update does not conflict
            with itself.
        config: Immutable threshold set.

    Returns:
        A :class:`TaskCheckResult`. ``evaluated`` is false when the crew or
        context cannot be read; conflicts and warnings are then empty.

    The function never raises for a rule finding. It also never raises for a
    missing crew, because the caller's existing 404 handling remains the source
    of truth.
    """
    try:
        start = to_utc(start_time)
        end = to_utc(end_time)
    except (TypeError, ValueError):
        return TaskCheckResult(evaluated=False)
    if end <= start:
        return TaskCheckResult(evaluated=False)

    horizon = timedelta(hours=config.PLANNING_HORIZON_HOURS)
    try:
        context = build_context(
            session,
            crew_id,
            start - horizon,
            end + horizon,
            AssessmentFatigueProvider(),
            config,
        )
    except (LookupError, ValueError):
        return TaskCheckResult(evaluated=False)

    tasks = [
        task
        for task in context.tasks
        if exclude_task_id is None or task.task_id != exclude_task_id
    ]
    tasks.append(
        _candidate_task(
            crew_id,
            start,
            end,
            task_type=task_type,
            workload_level=workload_level,
            is_critical=is_critical,
            title=title,
            config=config,
        )
    )
    report = detect_conflicts(
        context.model_copy(update={"tasks": tasks}), config
    )
    conflicts = [
        conflict
        for conflict in report.conflicts
        if CANDIDATE_TASK_ID in conflict.task_ids
    ]
    return TaskCheckResult(
        evaluated=True,
        conflicts=conflicts,
        warnings=list(report.data_warnings),
    )


def log_task_warnings(
    session: Session,
    crew_id: str,
    start_time: datetime,
    end_time: datetime,
    *,
    task_type: TaskType = TaskType.other,
    workload_level: WorkloadLevel = WorkloadLevel.medium,
    is_critical: bool = False,
    title: str = "Candidate mission task",
    exclude_task_id: str | None = None,
    config: MissionConfig = DEFAULT_CONFIG,
) -> TaskCheckResult:
    """Check a candidate task and log every finding as a non-blocking warning.

    This is the one-call helper proposed for ``mission_service.create_task`` and
    ``mission_service.update_task``. It returns the result so a future schema
    change could also expose the warnings in an API response, but the current
    proposal only logs them.
    """
    result = check_candidate_task(
        session,
        crew_id,
        start_time,
        end_time,
        task_type=task_type,
        workload_level=workload_level,
        is_critical=is_critical,
        title=title,
        exclude_task_id=exclude_task_id,
        config=config,
    )
    if not result.evaluated:
        return result

    for conflict in result.conflicts:
        LOGGER.warning(
            "Non-blocking mission advisory for crew '%s': rule %s (%s) "
            "affects candidate task '%s'. %s",
            crew_id,
            conflict.rule_id,
            conflict.severity.value,
            title,
            conflict.explanation,
        )
    for warning in result.warnings:
        LOGGER.warning(
            "Non-blocking mission data warning for crew '%s': rule %s. %s",
            crew_id,
            warning.rule_id,
            warning.message,
        )
    return result
