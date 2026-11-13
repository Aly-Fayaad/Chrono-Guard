"""Pydantic v2 domain models for the mission-intelligence module.

These are transfer objects only. They do **not** change the database schema and
are deliberately separate from the SQLModel tables. All datetimes are timezone
aware and normalised to UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from app.models.enums import QualityFlag


def _new_id() -> str:
    """Return a fresh string identifier for a transfer object."""
    return uuid4().hex


def _require_utc(value: datetime) -> datetime:
    """Reject naive datetimes and convert aware values to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetimes must be timezone-aware (UTC)")
    return value.astimezone(timezone.utc)


class TaskCategory(str, Enum):
    """Mission task categories, including categories absent from the database enum."""

    eva = "eva"
    maintenance = "maintenance"
    science = "science"
    exercise = "exercise"
    medical = "medical"
    rest = "rest"
    other = "other"
    sleep = "sleep"
    communication = "communication"
    rest_recovery = "rest_recovery"


class Priority(str, Enum):
    """Display priority derived from workload and criticality."""

    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class WorkloadLevel(str, Enum):
    """Relative workload of a mission task."""

    low = "low"
    medium = "medium"
    high = "high"


class TaskStatus(str, Enum):
    """Lifecycle status for a mission task."""

    planned = "planned"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class ConflictType(str, Enum):
    """Category of a detected schedule conflict."""

    task_overlap = "task_overlap"
    sleep_window_conflict = "sleep_window_conflict"
    circadian_low_alertness = "circadian_low_alertness"
    insufficient_recovery_gap = "insufficient_recovery_gap"
    workload_overload = "workload_overload"
    high_fatigue_critical_task = "high_fatigue_critical_task"
    insufficient_data = "insufficient_data"


class Severity(str, Enum):
    """How strongly a conflict or advisory should be surfaced."""

    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class FatigueLevel(str, Enum):
    """Categorical fatigue level. There is intentionally no numeric counterpart."""

    unknown = "unknown"
    no_flag = "no_flag"
    monitor = "monitor"
    elevated_concern = "elevated_concern"


class SuitabilityStatus(str, Enum):
    """Outcome of evaluating one task against one astronaut's current state."""

    suitable = "suitable"
    review = "review"
    not_recommended = "not_recommended"
    insufficient_data = "insufficient_data"


class CrewProfileSummary(BaseModel):
    """Read-only summary of a crew member profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    crew_id: str
    display_name: str
    role: str
    sleep_target_hours: float = Field(ge=0)


class SleepSummary(BaseModel):
    """Read-only summary of one recorded sleep interval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sleep_id: str
    start_time: datetime
    end_time: datetime
    interruptions: int = Field(ge=0)
    quality: QualityFlag

    @field_validator("start_time", "end_time")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def _window(self) -> "SleepSummary":
        if self.end_time <= self.start_time:
            raise ValueError("sleep end_time must be after start_time")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_minutes(self) -> int:
        """Duration of the sleep interval in whole minutes."""
        return int((self.end_time - self.start_time).total_seconds() // 60)


class PlannedSleepWindow(BaseModel):
    """One planned or inferred sleep opportunity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start_time: datetime
    end_time: datetime
    source: str = Field(
        default="inferred_habitual_sleep",
        description="Where the window came from, e.g. inferred_habitual_sleep.",
    )

    @field_validator("start_time", "end_time")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def _window(self) -> "PlannedSleepWindow":
        if self.end_time <= self.start_time:
            raise ValueError("planned sleep end_time must be after start_time")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_minutes(self) -> int:
        """Duration of the planned sleep window in whole minutes."""
        return int((self.end_time - self.start_time).total_seconds() // 60)


class FatigueSignal(BaseModel):
    """Categorical fatigue input with no numeric score.

    ``contributing_factors`` is passed through verbatim from the assessment so
    downstream code cannot mistake an ad-hoc JSON shape for a validated schema.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    level: FatigueLevel
    source: str
    contributing_factors: list[dict] = Field(default_factory=list)


class TaskView(BaseModel):
    """Normalised, read-only view of a mission task."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    astronaut_id: str
    name: str
    category: TaskCategory
    start_time: datetime
    end_time: datetime
    priority: Priority
    workload_level: WorkloadLevel
    required_alertness: int | None = Field(
        default=None,
        # Bounds mirror MIN_ALERTNESS/MAX_ALERTNESS in config.py. They are
        # hardcoded here because config.py imports this module's enums, so
        # importing the config back would create a circular import.
        ge=1,
        le=5,
        description="Required alertness on the project's 1-5 scale, if known.",
    )
    status: TaskStatus
    is_critical: bool

    @field_validator("start_time", "end_time")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def _window(self) -> "TaskView":
        if self.end_time <= self.start_time:
            raise ValueError("task end_time must be after start_time")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_minutes(self) -> int:
        """Task duration in whole minutes."""
        return int((self.end_time - self.start_time).total_seconds() // 60)


class AstronautContext(BaseModel):
    """All mission-intelligence inputs for one astronaut and one time window."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    crew: CrewProfileSummary
    recent_sleep: list[SleepSummary] = Field(default_factory=list)
    fatigue_signal: FatigueSignal
    planned_sleep_windows: list[PlannedSleepWindow] = Field(default_factory=list)
    tasks: list[TaskView] = Field(default_factory=list)


class FreeGap(BaseModel):
    """An unused interval between tasks inside a requested window."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start_time: datetime
    end_time: datetime

    @field_validator("start_time", "end_time")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def _window(self) -> "FreeGap":
        if self.end_time <= self.start_time:
            raise ValueError("free gap end_time must be after start_time")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_minutes(self) -> int:
        """Length of the free gap in whole minutes."""
        return int((self.end_time - self.start_time).total_seconds() // 60)


class SuitabilityResult(BaseModel):
    """Advisory result of evaluating one task for one astronaut.

    ``inputs_used`` records the exact values and thresholds the rules saw, so a
    reviewer can reproduce the decision. It is JSON-like data, never a numeric
    fatigue score.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    astronaut_id: str
    status: SuitabilityStatus
    reasons: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    inputs_used: dict[str, Any] = Field(default_factory=dict)


class Conflict(BaseModel):
    """One explainable schedule conflict.

    Fields follow FR-03 in ``docs/02_requirements.md``: rule id, category,
    severity, affected interval, involved task ids, explanation, cited sources,
    and the configuration keys that were applied. ``suggested_action`` is
    review-oriented advisory wording only.

    ``conflict_id`` is supplied by ``conflicts.py`` as a deterministic hash so a
    repeated evaluation of the same inputs yields the same identifier. The
    factory default exists only so a hand-built DTO remains valid.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    conflict_id: str = Field(default_factory=_new_id)
    rule_id: str
    conflict_type: ConflictType
    severity: Severity
    astronaut_id: str
    task_ids: list[str] = Field(default_factory=list)
    affected_start: datetime
    affected_end: datetime
    explanation: str
    suggested_action: str
    source_ids: list[str] = Field(default_factory=list)
    config_keys: list[str] = Field(default_factory=list)

    @field_validator("affected_start", "affected_end")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def _window(self) -> "Conflict":
        if self.affected_end < self.affected_start:
            raise ValueError("affected_end must not be before affected_start")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def task_id(self) -> str | None:
        """Primary task id (the first entry of ``task_ids``), if any."""
        return self.task_ids[0] if self.task_ids else None


class DataWarning(BaseModel):
    """A note that a rule could not be evaluated because data were missing.

    Warnings never replace a conflict; they record explicitly that no judgement
    was made, which is the missing-data behaviour required by FR-12.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    astronaut_id: str
    task_id: str | None = None
    message: str


class ConflictReport(BaseModel):
    """Result of one conflict-detection pass for one astronaut."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    astronaut_id: str
    rule_set_version: str
    conflicts: list[Conflict] = Field(default_factory=list)
    data_warnings: list[DataWarning] = Field(default_factory=list)
    config_keys: list[str] = Field(default_factory=list)


class RecommendationType(str, Enum):
    """Action family of an advisory recommendation."""

    review_task_timing = "review_task_timing"
    identify_recovery_opportunity = "identify_recovery_opportunity"
    redistribute_demanding_tasks = "redistribute_demanding_tasks"
    review_sleep_schedule = "review_sleep_schedule"
    evaluate_lighting_schedule = "evaluate_lighting_schedule"


class Recommendation(BaseModel):
    """One advisory countermeasure recommendation.

    Fields follow FR-06 in ``docs/02_requirements.md`` and the Phase 5A
    recommendation contract. Recommendations are advisory only, must use
    "may reduce risk under rule X" wording, and must never claim to improve
    fatigue or recommend medication.

    ``recommendation_id`` is a deterministic hash supplied by
    ``recommendations.py``; the factory default exists only so a hand-built DTO
    remains valid. ``requires_medical_review`` is false unless the
    recommendation relies on a health-assessment signal.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    recommendation_id: str = Field(default_factory=_new_id)
    recommendation_type: RecommendationType
    related_conflict_id: str
    astronaut_id: str
    countermeasure_id: str
    countermeasure_name: str
    rule_id: str
    reason: str
    suggested_action: str
    expected_benefit: str
    priority: Priority
    explanation: str
    source_ids: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_mission_approval: bool = False
    requires_medical_review: bool = False
    advisory_text: str


class ConflictTypeMetric(BaseModel):
    """Aggregated conflict count and severity distribution for one type."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    conflict_type: ConflictType
    count: int = Field(ge=0)
    highest_severity: Severity | None = None
    severity_counts: dict[Severity, int] = Field(default_factory=dict)


class WorkloadWindowMetric(BaseModel):
    """One maximal workload window and its demanding-task load.

    The window mirrors the counting window of ``R-WORKLOAD-01``: it starts at a
    demanding task and spans ``WORKLOAD_WINDOW_HOURS``. ``task_ids`` lists the
    demanding tasks that start inside it, in start-time order.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    window_start: datetime
    window_end: datetime
    demanding_task_count: int = Field(ge=0)
    demanding_minutes: int = Field(ge=0)
    exceeds_task_limit: bool
    exceeds_minutes_limit: bool
    task_ids: list[str] = Field(default_factory=list)

    @field_validator("window_start", "window_end")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def _window(self) -> "WorkloadWindowMetric":
        if self.window_end <= self.window_start:
            raise ValueError("workload window end must be after start")
        return self


class ScheduleMetrics(BaseModel):
    """Rule-based metrics for one schedule in a what-if comparison.

    ``fatigue_level`` and ``fatigue_source`` are copied from the original
    context for both schedules; a scenario never re-predicts fatigue.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_start: datetime
    evaluation_end: datetime
    conflicts_by_type: list[ConflictTypeMetric] = Field(default_factory=list)
    total_conflicts: int = Field(ge=0)
    highest_severity: Severity | None = None
    workload_windows: list[WorkloadWindowMetric] = Field(default_factory=list)
    total_free_minutes: int = Field(ge=0)
    total_recovery_minutes: int = Field(ge=0)
    total_recovery_and_free_minutes: int = Field(ge=0)
    longest_recovery_gap_minutes: int = Field(ge=0)
    tasks_inside_sleep_windows: int = Field(ge=0)
    task_ids_inside_sleep_windows: list[str] = Field(default_factory=list)
    fatigue_level: FatigueLevel
    fatigue_source: str
    data_warning_count: int = Field(ge=0)
    data_warning_rule_ids: list[str] = Field(default_factory=list)

    @field_validator("evaluation_start", "evaluation_end")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def _window(self) -> "ScheduleMetrics":
        if self.evaluation_end <= self.evaluation_start:
            raise ValueError("evaluation_end must be after evaluation_start")
        return self


class ScenarioComparison(BaseModel):
    """Deterministic comparison of an original and a proposed schedule.

    The comparison is deliberately limited to rule-based metrics. It never
    claims a physiological effect, and ``note`` states explicitly that fatigue
    was not re-predicted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    original_metrics: ScheduleMetrics
    proposed_metrics: ScheduleMetrics
    conflict_count_delta: int
    resolved_conflicts: list[Conflict] = Field(default_factory=list)
    new_conflicts: list[Conflict] = Field(default_factory=list)
    summary: str
    note: str
    config_keys: list[str] = Field(default_factory=list)
