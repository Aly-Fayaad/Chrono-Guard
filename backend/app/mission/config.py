"""Central configuration for the mission-intelligence module.

All policy values live here. Per the project rules, every field is labelled in a
comment either as ``evidence-based (source: URL)`` or as a ``configurable
assumption``. The three sources supported by this project are defined in
``docs/01_references.md``; none of them states a numeric threshold, so every
numeric value below is a configurable assumption, even where the underlying
*concept* is evidence-based.

The configuration is frozen: rules must never mutate thresholds at runtime.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.mission.models import Priority, TaskStatus, WorkloadLevel


class MissionConfig(BaseModel):
    """Immutable threshold set for conflict detection and fatigue advisories.

    Each field documents what it controls. The comment above each field records
    the evidence status required by ``AGENTS.md``. Defaults are prototype
    assumptions chosen for a lunar mission, not NASA cut-offs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # ------------------------------------------------------------------
    # Sleep opportunity
    # ------------------------------------------------------------------

    # configurable assumption
    MIN_SLEEP_WINDOW_MINUTES: int = Field(
        default=420,
        ge=0,
        le=1440,
        description=(
            "Minimum uninterrupted sleep opportunity (minutes) that a schedule should "
            "preserve. NASA sources require sufficient sleep opportunity but give no "
            "numeric minimum."
        ),
    )

    # configurable assumption
    PROTECTED_SLEEP_WINDOW_START_HOUR: int = Field(
        default=22,
        ge=0,
        le=23,
        description=(
            "Clock hour (UTC) at which the default protected sleep window starts. "
            "Used only as a fallback when no habitual sleep window can be inferred."
        ),
    )

    # configurable assumption
    PROTECTED_SLEEP_WINDOW_END_HOUR: int = Field(
        default=7,
        ge=0,
        le=23,
        description=(
            "Clock hour (UTC) at which the default protected sleep window ends. "
            "May be earlier than the start hour to represent a window that crosses "
            "midnight."
        ),
    )

    # configurable assumption
    WOCL_START_HOUR: int = Field(
        default=2,
        ge=0,
        le=23,
        description=(
            "Clock hour (UTC) at which the configurable Window of Circadian Low "
            "starts. The WOCL concept is evidence-based, but the clock times are not "
            "stated in the sources."
        ),
    )

    # configurable assumption
    WOCL_END_HOUR: int = Field(
        default=6,
        ge=0,
        le=23,
        description=(
            "Clock hour (UTC) at which the configurable Window of Circadian Low ends."
        ),
    )

    # configurable assumption
    WOCL_TOLERANCE_MINUTES: int = Field(
        default=30,
        ge=0,
        description=(
            "Buffer (minutes) added around the WOCL when deciding whether a task is "
            "too close to the circadian trough."
        ),
    )

    # ------------------------------------------------------------------
    # Recovery and workload
    # ------------------------------------------------------------------

    # configurable assumption
    MIN_RECOVERY_GAP_MINUTES: int = Field(
        default=30,
        ge=0,
        description=(
            "Minimum recovery gap (minutes) required between two demanding tasks. "
            "Recovery gaps are evidence-based as a concept; the duration is not."
        ),
    )

    # configurable assumption
    WORKLOAD_WINDOW_HOURS: int = Field(
        default=24,
        ge=1,
        le=168,
        description=(
            "Length (hours) of the rolling window over which demanding tasks and "
            "task-hours are counted for workload concentration."
        ),
    )

    # configurable assumption
    MAX_DEMANDING_TASKS_PER_WINDOW: int = Field(
        default=3,
        ge=1,
        description=(
            "Maximum number of demanding tasks allowed inside one workload window "
            "before an advisory is raised."
        ),
    )

    # configurable assumption
    MAX_DEMANDING_TASK_HOURS_PER_WINDOW: int = Field(
        default=480,
        ge=1,
        le=168 * 60,
        description=(
            "Maximum cumulative demanding-task time (minutes) allowed inside one "
            "workload window before an advisory is raised."
        ),
    )

    # configurable assumption
    DEMANDING_WORKLOAD_LEVELS: tuple[WorkloadLevel, ...] = Field(
        default=(WorkloadLevel.high,),
        description=(
            "Workload levels treated as demanding when counting workload "
            "concentration and recovery gaps."
        ),
    )

    # ------------------------------------------------------------------
    # Alertness and task mapping
    # ------------------------------------------------------------------

    # configurable assumption
    ALERTNESS_BY_WORKLOAD: dict[WorkloadLevel, int] = Field(
        default_factory=lambda: {
            WorkloadLevel.low: 2,
            WorkloadLevel.medium: 3,
            WorkloadLevel.high: 5,
        },
        description=(
            "Maps a task's workload level to a required-alertness score on the "
            "1-5 scale. The scale and the mapping are project conventions, not a "
            "NASA instrument."
        ),
    )

    # configurable assumption
    CRITICAL_ALERTNESS_BONUS: int = Field(
        default=1,
        ge=0,
        description=(
            "Alertness points added to a critical task's mapped requirement before "
            "the result is capped at MAX_ALERTNESS."
        ),
    )

    # configurable assumption
    CRITICAL_TASK_ALERTNESS_REQUIREMENT: int = Field(
        default=4,
        ge=1,
        le=5,
        description=(
            "Minimum required alertness for any critical task, regardless of its "
            "workload level."
        ),
    )

    # configurable assumption
    MIN_ALERTNESS: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Lower bound of the internal 1-5 required-alertness scale.",
    )

    # configurable assumption
    MAX_ALERTNESS: int = Field(
        default=5,
        ge=1,
        le=5,
        description="Upper bound of the internal 1-5 required-alertness scale.",
    )

    # configurable assumption
    PRIORITY_BY_WORKLOAD: dict[WorkloadLevel, Priority] = Field(
        default_factory=lambda: {
            WorkloadLevel.low: Priority.low,
            WorkloadLevel.medium: Priority.medium,
            WorkloadLevel.high: Priority.high,
        },
        description=(
            "Derives a display priority from the workload level when the database "
            "has no priority field."
        ),
    )

    # configurable assumption
    CRITICAL_PRIORITY: Priority = Field(
        default=Priority.critical,
        description=(
            "Priority assigned to any task whose database row has is_critical=True."
        ),
    )

    # configurable assumption
    DEFAULT_TASK_STATUS: TaskStatus = Field(
        default=TaskStatus.planned,
        description=(
            "Status assigned to every task adapted from the database, because "
            "MissionTask has no status field."
        ),
    )

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    # configurable assumption
    CONFLICT_OVERLAP_TOLERANCE_MINUTES: int = Field(
        default=0,
        ge=0,
        description=(
            "Overlap tolerance (minutes) when comparing two task windows. Zero "
            "means any positive overlap is a conflict."
        ),
    )

    # configurable assumption
    PLANNING_HORIZON_HOURS: int = Field(
        default=72,
        ge=1,
        le=720,
        description=(
            "Default look-ahead horizon (hours) for conflict checks and "
            "recommendations when the caller does not supply an explicit window."
        ),
    )

    # configurable assumption
    MAX_CONTEXT_TASKS: int = Field(
        default=100,
        ge=1,
        description=(
            "Maximum number of task views loaded into one astronaut context, to "
            "keep evaluation bounded."
        ),
    )

    # ------------------------------------------------------------------
    # Schedule and suitability (Phase 3)
    # ------------------------------------------------------------------

    # configurable assumption
    MIN_FREE_GAP_MINUTES: int = Field(
        default=15,
        ge=0,
        le=1440,
        description=(
            "Shortest unused interval (minutes) reported as a free gap between "
            "tasks. Shorter slack is treated as an implicit buffer, not a gap. "
            "No source states a duration."
        ),
    )

    # configurable assumption
    SLEEP_SHORTFALL_NOT_RECOMMENDED_RATIO: float = Field(
        default=0.75,
        gt=0.0,
        le=1.0,
        description=(
            "Last-sleep duration below this fraction of the crew sleep target is "
            "treated as severe. Used by the Phase 3 suitability rules; the "
            "shortfall concept is evidence-based but the fraction is not."
        ),
    )

    # configurable assumption
    SLEEP_SHORTFALL_REVIEW_RATIO: float = Field(
        default=0.90,
        gt=0.0,
        le=1.0,
        description=(
            "Last-sleep duration below this fraction of the crew sleep target "
            "requires review for demanding tasks. Values at or above it are "
            "treated as adequate. Configurable assumption."
        ),
    )

    # ------------------------------------------------------------------
    # Sleep history and inference
    # ------------------------------------------------------------------

    # configurable assumption
    RECENT_SLEEP_LOOKBACK_DAYS: int = Field(
        default=14,
        ge=1,
        description=(
            "How many days before the evaluation window are loaded into the recent "
            "sleep summaries."
        ),
    )

    # configurable assumption
    RECENT_SLEEP_MAX_RECORDS: int = Field(
        default=14,
        ge=1,
        description="Maximum number of recent sleep records kept in the context.",
    )

    # configurable assumption
    HABITUAL_SLEEP_LOOKBACK_DAYS: int = Field(
        default=14,
        ge=1,
        description=(
            "How many days of sleep records are used when inferring the habitual "
            "sleep window."
        ),
    )

    # configurable assumption
    HABITUAL_SLEEP_MIN_RECORDS: int = Field(
        default=3,
        ge=2,
        description=(
            "Minimum number of consistent sleep records required before a habitual "
            "sleep window is inferred. Below this, inference returns no windows."
        ),
    )

    # configurable assumption
    HABITUAL_SLEEP_MATCH_TOLERANCE_MINUTES: int = Field(
        default=90,
        ge=0,
        le=720,
        description=(
            "Maximum circular distance (minutes) from the mean sleep times for a "
            "record to be considered part of the habitual window."
        ),
    )

    # configurable assumption
    SLEEP_DEBT_LOOKBACK_DAYS: int = Field(
        default=7,
        ge=1,
        description=(
            "How many days of sleep history feed the cumulative sleep-debt proxy. "
            "The debt concept is evidence-based; the lookback is not."
        ),
    )

    # configurable assumption
    SLEEP_DEBT_THRESHOLD_MINUTES: int = Field(
        default=300,
        ge=0,
        description=(
            "Sleep deficit (minutes) above which the sleep-debt indicator is "
            "raised."
        ),
    )

    # configurable assumption
    INSUFFICIENT_DATA_MIN_DAYS: int = Field(
        default=3,
        ge=1,
        description=(
            "Minimum days of usable history before risk indicators are reported "
            "instead of an explicit insufficient-data result."
        ),
    )

    # ------------------------------------------------------------------
    # Risk indicator and recommendations (reserved for later phases)
    # ------------------------------------------------------------------

    # configurable assumption
    RISK_WEIGHT_SLEEP: float = Field(
        default=1.0,
        ge=0.0,
        description="Weight of the sleep indicator in a combined risk indicator.",
    )

    # configurable assumption
    RISK_WEIGHT_CIRCADIAN: float = Field(
        default=1.0,
        ge=0.0,
        description="Weight of the circadian-placement indicator.",
    )

    # configurable assumption
    RISK_WEIGHT_WORKLOAD: float = Field(
        default=1.0,
        ge=0.0,
        description="Weight of the workload indicator.",
    )

    # configurable assumption
    RISK_FLAG_THRESHOLD: float = Field(
        default=1.0,
        ge=0.0,
        description=(
            "Combined-indicator value at which an advisory flag is raised."
        ),
    )

    # configurable assumption
    MIN_STRUCTURED_BREAK_MINUTES: int = Field(
        default=15,
        ge=0,
        description="Minimum duration of a structured recovery break.",
    )

    # configurable assumption
    NAP_MIN_MINUTES: int = Field(
        default=10,
        ge=0,
        description="Lower bound of a recommended strategic nap.",
    )

    # configurable assumption
    NAP_MAX_MINUTES: int = Field(
        default=30,
        ge=0,
        description="Upper bound of a recommended strategic nap.",
    )

    # configurable assumption
    MAX_RECOMMENDATIONS_PER_RESPONSE: int = Field(
        default=5,
        ge=1,
        description=(
            "Maximum number of recommendations returned per evaluation so the "
            "output stays reviewable."
        ),
    )

    @model_validator(mode="after")
    def _validate_consistency(self) -> "MissionConfig":
        """Reject configuration combinations that would make rules ambiguous."""
        if self.WOCL_START_HOUR == self.WOCL_END_HOUR:
            raise ValueError("WOCL_START_HOUR and WOCL_END_HOUR must differ")
        if self.PROTECTED_SLEEP_WINDOW_START_HOUR == self.PROTECTED_SLEEP_WINDOW_END_HOUR:
            raise ValueError(
                "PROTECTED_SLEEP_WINDOW_START_HOUR and END_HOUR must differ"
            )
        if self.MIN_ALERTNESS >= self.MAX_ALERTNESS:
            raise ValueError("MIN_ALERTNESS must be lower than MAX_ALERTNESS")
        for workload, score in self.ALERTNESS_BY_WORKLOAD.items():
            if not self.MIN_ALERTNESS <= score <= self.MAX_ALERTNESS:
                raise ValueError(
                    f"ALERTNESS_BY_WORKLOAD[{workload.value}] must be within "
                    f"[{self.MIN_ALERTNESS}, {self.MAX_ALERTNESS}]"
                )
        missing = set(WorkloadLevel) - set(self.ALERTNESS_BY_WORKLOAD)
        if missing:
            raise ValueError(
                "ALERTNESS_BY_WORKLOAD must cover every workload level; missing "
                f"{sorted(level.value for level in missing)}"
            )
        missing_priority = set(WorkloadLevel) - set(self.PRIORITY_BY_WORKLOAD)
        if missing_priority:
            raise ValueError(
                "PRIORITY_BY_WORKLOAD must cover every workload level; missing "
                f"{sorted(level.value for level in missing_priority)}"
            )
        if self.NAP_MIN_MINUTES > self.NAP_MAX_MINUTES:
            raise ValueError("NAP_MIN_MINUTES must not exceed NAP_MAX_MINUTES")
        if not (
            0.0
            < self.SLEEP_SHORTFALL_NOT_RECOMMENDED_RATIO
            < self.SLEEP_SHORTFALL_REVIEW_RATIO
            <= 1.0
        ):
            raise ValueError(
                "SLEEP_SHORTFALL_NOT_RECOMMENDED_RATIO must be lower than "
                "SLEEP_SHORTFALL_REVIEW_RATIO, and both must be in (0, 1]"
            )
        if not self.DEMANDING_WORKLOAD_LEVELS:
            raise ValueError("DEMANDING_WORKLOAD_LEVELS must not be empty")
        return self


DEFAULT_CONFIG = MissionConfig()
"""Process-wide default configuration shared by the mission modules."""
