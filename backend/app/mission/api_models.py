"""Pydantic request and response models for the mission-intelligence API.

The domain transfer objects (``TaskView``, ``Conflict``, ``Recommendation``,
``ScenarioComparison``, ...) live in ``app/mission/models.py``. This module adds
only the HTTP envelope: request bodies, response wrappers, and the stable
``data_warnings`` shape.

All datetimes are expected to be timezone-aware UTC values. The mission layer
rejects naive datetimes with a 422 response rather than guessing a timezone.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Self, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.mission.models import (
    Conflict,
    CrewProfileSummary,
    FatigueSignal,
    PlannedSleepWindow,
    Recommendation,
    ScenarioComparison,
    SleepSummary,
    SuitabilityResult,
    TaskView,
)
from app.models.enums import ActionStatus


class ScheduleView(str, Enum):
    """Requested schedule granularity."""

    daily = "daily"
    weekly = "weekly"


class ApiDataWarning(BaseModel):
    """A machine-readable warning that accompanies every successful response.

    ``code`` is the stable value clients should branch on. Examples:

    * ``no_assessment_available`` - no ``Assessment`` row exists, so fatigue is
      ``unknown`` and suitability falls back to ``insufficient_data``.
    * ``assessment_insufficient_data`` - an assessment exists but its status is
      ``insufficient_data``.
    * ``no_recent_sleep`` - no recent ``SleepRecord`` is available.
    * ``no_planned_sleep_window`` - the habitual sleep window could not be
      inferred.
    * ``no_tasks_in_window`` - the requested window contains no tasks.
    * ``conflict_data_warning`` - a conflict rule was skipped; ``rule_id`` names
      the rule and ``message`` explains why.

    Warnings never replace an error. They record that a rule made no judgement,
    which is the missing-data behaviour required by FR-12/NFR-09.
    """

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    rule_id: str | None = None
    task_id: str | None = None


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------


class ScheduleResponse(BaseModel):
    """One daily or weekly mission schedule for one crew member."""

    crew_id: str
    view: ScheduleView
    window_start: datetime
    window_end: datetime
    tasks: list[TaskView] = Field(default_factory=list)
    planned_sleep_windows: list[PlannedSleepWindow] = Field(default_factory=list)
    data_warnings: list[ApiDataWarning] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


class HealthSummary(BaseModel):
    """Read-only health inputs used by the mission rules.

    There is intentionally no numeric fatigue score: the only fatigue input is
    the categorical ``Assessment.status`` mapped to ``FatigueSignal.level``.
    """

    fatigue_signal: FatigueSignal
    latest_sleep: SleepSummary | None = None
    recent_sleep: list[SleepSummary] = Field(default_factory=list)
    planned_sleep_windows: list[PlannedSleepWindow] = Field(default_factory=list)


class TaskSuitability(BaseModel):
    """One upcoming task paired with its advisory suitability result."""

    task: TaskView
    suitability: SuitabilityResult


class OverviewResponse(BaseModel):
    """Combined health, upcoming-task, and suitability overview."""

    crew: CrewProfileSummary
    health: HealthSummary
    window_start: datetime
    window_end: datetime
    upcoming_tasks: list[TaskSuitability] = Field(default_factory=list)
    conflict_count: int = Field(ge=0)
    recommendation_count: int = Field(ge=0)
    data_warnings: list[ApiDataWarning] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Conflicts and recommendations
# ---------------------------------------------------------------------------


class ConflictListResponse(BaseModel):
    """The full conflict report for one crew member and one window."""

    crew_id: str
    window_start: datetime
    window_end: datetime
    rule_set_version: str
    conflicts: list[Conflict] = Field(default_factory=list)
    config_keys: list[str] = Field(default_factory=list)
    data_warnings: list[ApiDataWarning] = Field(default_factory=list)


class RecommendationListResponse(BaseModel):
    """Advisory recommendations derived from the conflict report."""

    crew_id: str
    window_start: datetime
    window_end: datetime
    conflict_count: int = Field(ge=0)
    recommendations: list[Recommendation] = Field(default_factory=list)
    data_warnings: list[ApiDataWarning] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# What-if operations
# ---------------------------------------------------------------------------


class DelayTaskOperation(BaseModel):
    """Shift one task later by a positive number of minutes."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["delay_task"]
    task_id: str = Field(min_length=1)
    minutes: int = Field(gt=0)


class MoveTaskOperation(BaseModel):
    """Move one task to a new start time, preserving its duration."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["move_task"]
    task_id: str = Field(min_length=1)
    new_start: datetime


class AddRecoveryPeriodOperation(BaseModel):
    """Insert a structured recovery block into the schedule."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["add_recovery_period"]
    start: datetime
    end: datetime
    shift_following_tasks: bool = True
    task_id: str | None = None
    name: str | None = Field(default=None, min_length=1)


class RedistributeWorkloadOperation(BaseModel):
    """Move one demanding task to a different schedule window."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["redistribute_workload"]
    task_id: str = Field(min_length=1)
    new_start: datetime


class ModifySleepWindowOperation(BaseModel):
    """Replace one planned or inferred sleep window."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["modify_sleep_window"]
    new_start: datetime
    new_end: datetime
    window_index: int = Field(default=0, ge=0)


WhatIfOperation = Annotated[
    Union[
        DelayTaskOperation,
        MoveTaskOperation,
        AddRecoveryPeriodOperation,
        RedistributeWorkloadOperation,
        ModifySleepWindowOperation,
    ],
    Field(discriminator="type"),
]
"""Discriminated union of the five Phase 6 operations."""


class WhatIfRequest(BaseModel):
    """A transient schedule comparison request.

    The base window is used both to build the original context and as the
    comparison's evaluation window. Operations are applied in order and are
    never persisted.
    """

    model_config = ConfigDict(extra="forbid")

    window_start: datetime
    window_end: datetime
    operations: list[WhatIfOperation] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _window(self) -> Self:
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        return self


class AppliedOperation(BaseModel):
    """Echo of one applied operation, for traceability."""

    index: int = Field(ge=0)
    type: str
    task_id: str | None = None


class WhatIfResponse(BaseModel):
    """Result of a what-if comparison."""

    crew_id: str
    window_start: datetime
    window_end: datetime
    applied_operations: list[AppliedOperation] = Field(default_factory=list)
    comparison: ScenarioComparison
    data_warnings: list[ApiDataWarning] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Follow-ups
# ---------------------------------------------------------------------------


class FollowUpAction(str, Enum):
    """The three allowed follow-up transitions."""

    accept = "accept"
    skip = "skip"
    complete = "complete"


class FollowUpCreate(BaseModel):
    """Create a follow-up from a recommendation in the current evaluation.

    ``window_start`` and ``window_end`` must be supplied together. When omitted,
    the default window is now to now + ``PLANNING_HORIZON_HOURS``; clients should
    pass the same window they used to fetch the recommendation so the id remains
    reproducible.
    """

    model_config = ConfigDict(extra="forbid")

    recommendation_id: str = Field(min_length=1)
    window_start: datetime | None = None
    window_end: datetime | None = None
    due_at: datetime | None = None

    @model_validator(mode="after")
    def _window_pair(self) -> Self:
        if (self.window_start is None) != (self.window_end is None):
            raise ValueError("window_start and window_end must be supplied together")
        if (
            self.window_start is not None
            and self.window_end is not None
            and self.window_end <= self.window_start
        ):
            raise ValueError("window_end must be after window_start")
        return self


class FollowUpRead(BaseModel):
    """One advisory follow-up record.

    The record is created from a recommendation and keeps the recommendation's
    countermeasure, rule, and approval flags. It never applies a schedule change.
    """

    follow_up_id: str
    crew_id: str
    recommendation_id: str
    related_conflict_id: str
    countermeasure_id: str
    countermeasure_name: str
    rule_id: str
    status: ActionStatus
    requires_mission_approval: bool
    requires_medical_review: bool
    approved: bool | None = None
    due_at: datetime | None = None
    result: str | None = None
    advisory_text: str
    created_at: datetime
    updated_at: datetime


class FollowUpUpdate(BaseModel):
    """Apply one accept, skip, or complete transition."""

    model_config = ConfigDict(extra="forbid")

    action: FollowUpAction
    approved: bool | None = None
    result: str | None = Field(default=None, max_length=2000)


class FollowUpResponse(BaseModel):
    """A follow-up plus the warnings from the evaluation it came from."""

    follow_up: FollowUpRead
    data_warnings: list[ApiDataWarning] = Field(default_factory=list)
