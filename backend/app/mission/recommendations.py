"""Advisory recommendation generation for mission intelligence.

The generator turns each detected ``Conflict`` into at most one
``Recommendation``. Recommendations are decision support only: they never
diagnose, never mention medication, and never claim that a schedule change
improves fatigue. Every suggestion uses review-oriented wording and, where a
risk reduction is mentioned, the phrase "may reduce risk under rule X".

Countermeasures are restricted to CM-01 ... CM-07 from
``docs/02_requirements.md``. No recommendation is auto-applied:
``requires_mission_approval`` is always true, and ``requires_medical_review`` is
true only when the recommendation depends on the highest categorical fatigue
signal (``elevated_concern``) from the health assessment.

Every numeric policy value comes from ``MissionConfig``. All times are UTC.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timedelta

from app.mission.config import DEFAULT_CONFIG, MissionConfig
from app.mission.models import (
    AstronautContext,
    Conflict,
    ConflictReport,
    ConflictType,
    FatigueLevel,
    FreeGap,
    PlannedSleepWindow,
    Priority,
    Recommendation,
    RecommendationType,
    Severity,
    SleepSummary,
    TaskStatus,
    TaskView,
)
from app.mission.schedule import free_gaps

_CLOSED_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.completed, TaskStatus.cancelled}
)
"""Tasks that no longer reserve schedule time."""

_PRIORITY_BY_SEVERITY: dict[Severity, Priority] = {
    Severity.low: Priority.low,
    Severity.medium: Priority.medium,
    Severity.high: Priority.high,
    Severity.critical: Priority.critical,
}

_PRIORITY_RANK: dict[Priority, int] = {
    Priority.critical: 4,
    Priority.high: 3,
    Priority.medium: 2,
    Priority.low: 1,
}

# Countermeasure ids and names are fixed by docs/02_requirements.md, Section 3.
_CM_01 = ("CM-01", "Protect / Reschedule Sleep Opportunity")
_CM_02 = (
    "CM-02",
    "Align High-Criticality Tasks with Peak Alertness Windows / Avoid Circadian Trough",
)
_CM_03 = ("CM-03", "Insert Structured Recovery / Rest Break Between Demanding Tasks")
_CM_04 = ("CM-04", "Redistribute High-Workload Tasks Across Schedule Windows")
_CM_05 = ("CM-05", "Adjust Lighting Exposure Schedule for Circadian Alignment")

_COUNTERMEASURE_SOURCES: dict[str, tuple[str, ...]] = {
    "CM-01": ("NASA-HRP-Sleep-Risk", "NASA-STD-3001-Vol2"),
    "CM-02": ("NASA-HRP-Sleep-Risk", "NASA-TM-Fatigue-Countermeasures"),
    "CM-03": ("NASA-TM-Fatigue-Countermeasures", "NASA-STD-3001-Vol2"),
    "CM-04": ("NASA-HRP-Sleep-Risk", "NASA-STD-3001-Vol2"),
    "CM-05": ("NASA-HRP-Sleep-Risk", "NASA-STD-3001-Vol2"),
}

RecommendationBuilder = Callable[
    [AstronautContext, Conflict, MissionConfig], Recommendation
]


# ---------------------------------------------------------------------------
# Shared formatting and lookup helpers
# ---------------------------------------------------------------------------


def _fmt_dt(value: datetime) -> str:
    """Render an aware UTC datetime for human-readable advisory text."""
    return value.strftime("%Y-%m-%d %H:%M UTC")


def _clock(value: datetime) -> str:
    """Render the UTC clock time of a datetime."""
    return value.strftime("%H:%M")


def _interval_minutes(start: datetime, end: datetime) -> int:
    """Return the whole-minute length of an interval (never negative)."""
    return max(0, int((end - start).total_seconds() // 60))


def _overlap_minutes(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> int:
    """Return the whole-minute overlap of two intervals (0 when disjoint)."""
    return _interval_minutes(
        max(first_start, second_start), min(first_end, second_end)
    )


def _target_minutes(context: AstronautContext) -> int:
    """Return the astronaut's own sleep target in whole minutes."""
    return int(round(context.crew.sleep_target_hours * 60))


def _target_text(minutes: int) -> str:
    """Render a sleep target for advisory text."""
    if minutes <= 0:
        return "no positive sleep target"
    return f"{minutes / 60:.1f} h ({minutes} min)"


def _latest_sleep(context: AstronautContext) -> SleepSummary | None:
    """Return the most recent recorded sleep summary, if any."""
    return max(
        context.recent_sleep,
        key=lambda summary: (summary.end_time, summary.sleep_id),
        default=None,
    )


def _latest_sleep_text(context: AstronautContext) -> str:
    """Describe the latest sleep relative to this astronaut's own target."""
    latest = _latest_sleep(context)
    target = _target_minutes(context)
    if latest is None:
        return (
            "No recent sleep record is available for this astronaut, so the "
            "comparison uses the configured target only."
        )
    if target <= 0:
        return (
            f"The latest recorded sleep is {latest.duration_minutes} min; no "
            "positive sleep target is available for comparison."
        )
    ratio = latest.duration_minutes / target
    return (
        f"The latest recorded sleep is {latest.duration_minutes} min, "
        f"{ratio * 100:.0f}% of the {target} min target."
    )


def _task_map(context: AstronautContext) -> dict[str, TaskView]:
    """Index the context's task views by id."""
    return {task.task_id: task for task in context.tasks}


def _tasks_for(context: AstronautContext, conflict: Conflict) -> list[TaskView]:
    """Return the conflict's tasks that are present in the context."""
    by_id = _task_map(context)
    return [by_id[task_id] for task_id in conflict.task_ids if task_id in by_id]


def _first_task(context: AstronautContext, conflict: Conflict) -> TaskView | None:
    """Return the first conflict task available in the context, if any."""
    tasks = _tasks_for(context, conflict)
    return tasks[0] if tasks else None


def _task_phrase(task: TaskView) -> str:
    """Render one task with its id, name, and current UTC schedule.

    The interval is explicitly labelled as the task's current schedule so an
    advisory that suggests moving the task cannot be read as proposing a new
    interval.
    """
    return (
        f"task '{task.task_id}' ({task.name}, currently scheduled "
        f"{_fmt_dt(task.start_time)} to {_fmt_dt(task.end_time)})"
    )


def _window_phrase(window: PlannedSleepWindow) -> str:
    """Render a planned or inferred sleep window."""
    return (
        f"planned sleep window {_clock(window.start_time)}-{_clock(window.end_time)} "
        f"UTC (source '{window.source}', {window.duration_minutes} min)"
    )


def _fallback_window_phrase(config: MissionConfig) -> str:
    """Render the configurable fallback sleep window."""
    return (
        f"configured protected sleep window "
        f"{config.PROTECTED_SLEEP_WINDOW_START_HOUR:02d}:00-"
        f"{config.PROTECTED_SLEEP_WINDOW_END_HOUR:02d}:00 UTC (fallback)"
    )


_HABITUAL_SLEEP_CONFIG_KEYS = frozenset(
    {"HABITUAL_SLEEP_MIN_RECORDS", "HABITUAL_SLEEP_MATCH_TOLERANCE_MINUTES"}
)
_FALLBACK_SLEEP_CONFIG_KEYS = frozenset(
    {"PROTECTED_SLEEP_WINDOW_START_HOUR", "PROTECTED_SLEEP_WINDOW_END_HOUR"}
)
_WOCL_CONFIG_KEYS = frozenset(
    {"WOCL_START_HOUR", "WOCL_END_HOUR", "WOCL_TOLERANCE_MINUTES"}
)


def _circadian_trigger_terms(conflict: Conflict) -> list[str]:
    """Name only the clock criteria that actually produced a circadian finding.

    The rule records which criteria matched in ``conflict.config_keys``. Older
    or hand-built conflicts may omit those keys, so the explanation is used as a
    fallback. The WOCL is never named when it did not contribute to the finding.
    """
    keys = set(conflict.config_keys)
    terms: list[str] = []
    if keys & _HABITUAL_SLEEP_CONFIG_KEYS:
        terms.append("the habitual sleep period")
    if keys & _FALLBACK_SLEEP_CONFIG_KEYS:
        terms.append("the configured protected sleep window")
    if keys & _WOCL_CONFIG_KEYS:
        terms.append("the configured WOCL")
    if terms:
        return terms

    text = conflict.explanation.lower()
    if "habitual sleep period" in text:
        terms.append("the habitual sleep period")
    if "protected sleep window" in text:
        terms.append("the configured protected sleep window")
    if "wocl" in text:
        terms.append("the configured WOCL")
    return terms or ["the flagged clock placement"]


def _join_terms(terms: Sequence[str]) -> str:
    """Join two or three advisory phrases without ambiguity."""
    if len(terms) == 1:
        return terms[0]
    if len(terms) == 2:
        return f"{terms[0]} and {terms[1]}"
    return f"{', '.join(terms[:-1])}, and {terms[-1]}"


def _best_window(
    context: AstronautContext, conflict: Conflict
) -> PlannedSleepWindow | None:
    """Return the sleep window with the largest overlap with the conflict."""
    windows = context.planned_sleep_windows
    if not windows:
        return None
    return max(
        windows,
        key=lambda window: (
            _overlap_minutes(
                conflict.affected_start,
                conflict.affected_end,
                window.start_time,
                window.end_time,
            ),
            window.start_time,
            window.end_time,
        ),
    )


def _gap_phrase(gap: FreeGap) -> str:
    """Render a free interval with both endpoints and its duration."""
    return (
        f"{_fmt_dt(gap.start_time)} to {_fmt_dt(gap.end_time)} "
        f"({gap.duration_minutes} min)"
    )


def _free_gaps_after(
    context: AstronautContext,
    moment: datetime,
    config: MissionConfig,
    min_minutes: int,
) -> list[FreeGap]:
    """Find free schedule intervals after ``moment`` within the horizon.

    Planned sleep windows are excluded so the generator never proposes a
    recovery break or a moved task inside a protected sleep opportunity.
    """
    start = moment
    end = start + timedelta(hours=config.PLANNING_HORIZON_HOURS)
    open_tasks = [
        task for task in context.tasks if task.status not in _CLOSED_STATUSES
    ]
    gaps = free_gaps(
        open_tasks,
        start,
        end,
        config,
        min_minutes=max(1, min_minutes),
    )
    return [
        gap
        for gap in gaps
        if not any(
            gap.start_time < window.end_time and gap.end_time > window.start_time
            for window in context.planned_sleep_windows
        )
    ]


def _source_ids(conflict: Conflict, countermeasure_id: str) -> list[str]:
    """Union the conflict's sources with the countermeasure's sources."""
    return sorted(
        set(conflict.source_ids) | set(_COUNTERMEASURE_SOURCES[countermeasure_id])
    )


def _recommendation_id(
    *,
    context: AstronautContext,
    conflict: Conflict,
    recommendation_type: RecommendationType,
    countermeasure_id: str,
) -> str:
    """Build a deterministic recommendation id from stable inputs.

    The hash covers the astronaut, the related conflict id, the recommendation
    type, the countermeasure id, and the rule id. Re-evaluating the same context
    therefore produces the same id, while a different conflict or action family
    produces a different one. Time is never used as a random source.
    """
    payload = "|".join(
        (
            context.crew.crew_id,
            conflict.conflict_id,
            recommendation_type.value,
            countermeasure_id,
            conflict.rule_id,
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"rc_{digest}"


def _advisory_text(suggested_action: str) -> str:
    """Append the human-in-the-loop statement required by FR-06."""
    return (
        f"{suggested_action.rstrip()} This is advisory decision support only; "
        "decisions remain with the crew, mission control, and medical staff."
    )


def _build(
    *,
    context: AstronautContext,
    conflict: Conflict,
    recommendation_type: RecommendationType,
    countermeasure: tuple[str, str],
    reason: str,
    suggested_action: str,
    expected_benefit: str,
    explanation: str,
    preconditions: Sequence[str],
    warnings: Sequence[str],
    requires_medical_review: bool,
) -> Recommendation:
    """Assemble one recommendation with deterministic id and priority."""
    countermeasure_id, countermeasure_name = countermeasure
    return Recommendation(
        recommendation_id=_recommendation_id(
            context=context,
            conflict=conflict,
            recommendation_type=recommendation_type,
            countermeasure_id=countermeasure_id,
        ),
        recommendation_type=recommendation_type,
        related_conflict_id=conflict.conflict_id,
        astronaut_id=context.crew.crew_id,
        countermeasure_id=countermeasure_id,
        countermeasure_name=countermeasure_name,
        rule_id=conflict.rule_id,
        reason=reason,
        suggested_action=suggested_action,
        expected_benefit=expected_benefit,
        priority=_PRIORITY_BY_SEVERITY[conflict.severity],
        explanation=explanation,
        source_ids=_source_ids(conflict, countermeasure_id),
        preconditions=list(preconditions),
        warnings=list(warnings),
        requires_mission_approval=True,
        requires_medical_review=requires_medical_review,
        advisory_text=_advisory_text(suggested_action),
    )


# ---------------------------------------------------------------------------
# Per-conflict builders
# ---------------------------------------------------------------------------


def _task_overlap_recommendation(
    context: AstronautContext,
    conflict: Conflict,
    config: MissionConfig,
) -> Recommendation:
    """Recommend reviewing the timing of two overlapping tasks (CM-04)."""
    tasks = _tasks_for(context, conflict)
    if tasks:
        task_text = "; ".join(_task_phrase(task) for task in tasks)
        needed = max(task.duration_minutes for task in tasks)
    else:
        task_text = ", ".join(conflict.task_ids) or "the affected tasks"
        needed = config.MIN_STRUCTURED_BREAK_MINUTES

    overlap = _interval_minutes(conflict.affected_start, conflict.affected_end)
    gaps = _free_gaps_after(context, conflict.affected_start, config, needed)
    if gaps:
        gap = gaps[0]
        schedule_text = (
            f"A free interval of {gap.duration_minutes} min starts at "
            f"{_fmt_dt(gap.start_time)}."
        )
        action = (
            f"Consider moving one of the overlapping tasks ({task_text}) into the "
            f"free interval starting {_fmt_dt(gap.start_time)} or another unused "
            f"schedule window. Review under rule {conflict.rule_id}; this may "
            f"reduce risk under rule {conflict.rule_id}."
        )
        preconditions = [
            f"The free interval at {_fmt_dt(gap.start_time)} remains available or "
            "an equivalent interval is created."
        ]
        warnings: list[str] = []
    else:
        schedule_text = (
            f"No free interval of at least {needed} min was found within the "
            f"{config.PLANNING_HORIZON_HOURS} h planning horizon."
        )
        action = (
            f"Consider moving one of the overlapping tasks ({task_text}) to "
            f"another schedule window. Review under rule {conflict.rule_id}; this "
            f"may reduce risk under rule {conflict.rule_id}."
        )
        preconditions = [
            "Mission planner confirms that one of the overlapping tasks can move."
        ]
        warnings = [
            "No suitable free interval was found; the recommendation is limited "
            "to schedule review."
        ]

    reason = (
        f"Rule {conflict.rule_id} reports a {overlap} min overlap between "
        f"{task_text}."
    )
    benefit = (
        f"Removes the {overlap} min overlap between the tasks under rule "
        f"{conflict.rule_id}; no physiological effect is claimed."
    )
    explanation = (
        f"{schedule_text} The recommendation reviews task placement only and "
        "does not claim a performance effect."
    )
    return _build(
        context=context,
        conflict=conflict,
        recommendation_type=RecommendationType.review_task_timing,
        countermeasure=_CM_04,
        reason=reason,
        suggested_action=action,
        expected_benefit=benefit,
        explanation=explanation,
        preconditions=preconditions,
        warnings=warnings,
        requires_medical_review=False,
    )


def _sleep_window_recommendation(
    context: AstronautContext,
    conflict: Conflict,
    config: MissionConfig,
) -> Recommendation:
    """Recommend reviewing the sleep schedule or the task that intrudes (CM-01)."""
    task = _first_task(context, conflict)
    task_text = (
        _task_phrase(task)
        if task is not None
        else (
            f"the interval {_fmt_dt(conflict.affected_start)} to "
            f"{_fmt_dt(conflict.affected_end)}"
        )
    )
    window = _best_window(context, conflict)
    window_text = (
        _window_phrase(window) if window is not None else _fallback_window_phrase(config)
    )
    target = _target_minutes(context)
    target_text = _target_text(target)
    overlap = _interval_minutes(conflict.affected_start, conflict.affected_end)
    source_text = window.source if window is not None else "configured_fallback"

    reason = (
        f"Rule {conflict.rule_id} reports a {overlap} min overlap between "
        f"{task_text} and {window_text}. This astronaut's sleep target is "
        f"{target_text}."
    )
    action = (
        f"Consider moving {task_text} outside {window_text} or reviewing the "
        f"sleep window so the crew keeps the {target_text} target. Review under "
        f"rule {conflict.rule_id}; this may reduce risk under rule "
        f"{conflict.rule_id}."
    )
    benefit = (
        f"Restores the planned sleep opportunity by removing the {overlap} min "
        f"overlap under rule {conflict.rule_id}; no physiological effect is "
        "claimed."
    )
    explanation = (
        f"{_latest_sleep_text(context)} The window source is '{source_text}'. "
        "The overlap is measured against the planned opportunity, not against "
        "recorded sleep."
    )
    warnings: list[str] = []
    if target <= 0:
        warnings.append(
            "The crew sleep target is not positive, so the target comparison is "
            "limited."
        )
    return _build(
        context=context,
        conflict=conflict,
        recommendation_type=RecommendationType.review_sleep_schedule,
        countermeasure=_CM_01,
        reason=reason,
        suggested_action=action,
        expected_benefit=benefit,
        explanation=explanation,
        preconditions=[
            "Mission planner confirms that either the task or the sleep window "
            "can be adjusted."
        ],
        warnings=warnings,
        requires_medical_review=False,
    )


def _recovery_recommendation(
    context: AstronautContext,
    conflict: Conflict,
    config: MissionConfig,
) -> Recommendation:
    """Recommend a recovery opportunity, using this astronaut's free gaps (CM-03)."""
    tasks = _tasks_for(context, conflict)
    task_text = (
        "; ".join(_task_phrase(task) for task in tasks)
        if tasks
        else (", ".join(conflict.task_ids) or "the affected tasks")
    )
    gap_minutes = _interval_minutes(conflict.affected_start, conflict.affected_end)
    required = config.MIN_RECOVERY_GAP_MINUTES
    minimum_break = max(1, config.MIN_STRUCTURED_BREAK_MINUTES)
    latest = _latest_sleep(context)
    target = _target_minutes(context)
    fatigue = context.fatigue_signal.level.value

    gaps = _free_gaps_after(
        context, conflict.affected_start, config, minimum_break
    )
    # Show at most two candidates so the advisory text stays reviewable.
    candidates = gaps[:2]
    if candidates:
        nearest = candidates[0]
        schedule_text = (
            f"Free intervals on this astronaut's schedule within the "
            f"{config.PLANNING_HORIZON_HOURS} h horizon include "
            f"{'; '.join(_gap_phrase(gap) for gap in candidates)}."
        )
        action = (
            f"Consider placing a structured recovery break of at least "
            f"{minimum_break} min in the free interval starting "
            f"{_fmt_dt(nearest.start_time)} ({nearest.duration_minutes} min "
            f"available). Review under rule {conflict.rule_id}; this may reduce "
            f"risk under rule {conflict.rule_id}."
        )
        preconditions = [
            f"The free interval at {_fmt_dt(nearest.start_time)} remains "
            "available or an equivalent interval is created."
        ]
        warnings: list[str] = []
    else:
        schedule_text = (
            f"No free interval of at least {minimum_break} min was found within "
            f"the {config.PLANNING_HORIZON_HOURS} h planning horizon."
        )
        action = (
            f"Consider reviewing the schedule for a structured recovery break of "
            f"at least {minimum_break} min between the demanding tasks. Review "
            f"under rule {conflict.rule_id}; this may reduce risk under rule "
            f"{conflict.rule_id}."
        )
        preconditions = [
            "Mission planner identifies or creates a free recovery interval."
        ]
        warnings = [
            "No free interval was found; the recommendation is limited to "
            "schedule review."
        ]

    reason = (
        f"Rule {conflict.rule_id} reports {gap_minutes} free min around "
        f"{task_text}; the configured minimum recovery gap is {required} min. "
        f"The recorded fatigue level is '{fatigue}'."
    )
    benefit = (
        f"Brings the free time around the demanding task to at least {required} "
        f"min under rule {conflict.rule_id} once a free interval is used; no "
        "physiological effect is claimed."
    )
    explanation = (
        f"{schedule_text} "
        f"{_latest_sleep_text(context)} The recommendation is a schedule review, "
        "not a rest prescription."
    )
    return _build(
        context=context,
        conflict=conflict,
        recommendation_type=RecommendationType.identify_recovery_opportunity,
        countermeasure=_CM_03,
        reason=reason,
        suggested_action=action,
        expected_benefit=benefit,
        explanation=explanation,
        preconditions=preconditions,
        warnings=warnings,
        requires_medical_review=False,
    )


def _workload_recommendation(
    context: AstronautContext,
    conflict: Conflict,
    config: MissionConfig,
) -> Recommendation:
    """Recommend redistributing demanding tasks across windows (CM-04)."""
    tasks = _tasks_for(context, conflict)
    if tasks:
        task_text = "; ".join(_task_phrase(task) for task in tasks)
        count = len(tasks)
        total_minutes: int | None = sum(task.duration_minutes for task in tasks)
        details = (
            f"The {count} tasks account for {total_minutes} demanding minutes in "
            "the context."
        )
    else:
        task_text = ", ".join(conflict.task_ids) or "the affected tasks"
        count = len(conflict.task_ids)
        total_minutes = None
        details = "Task details were not available in the context."

    window_text = (
        f"{_fmt_dt(conflict.affected_start)} to {_fmt_dt(conflict.affected_end)}"
    )
    reason = (
        f"Rule {conflict.rule_id} reports {count} demanding task(s) inside the "
        f"workload window {window_text}. The configured maximum is "
        f"{config.MAX_DEMANDING_TASKS_PER_WINDOW} task(s) and "
        f"{config.MAX_DEMANDING_TASK_HOURS_PER_WINDOW} demanding minutes. "
        f"{details}"
    )
    action = (
        f"Consider redistributing one or more of {task_text} into a different "
        f"schedule window so the count is at or below "
        f"{config.MAX_DEMANDING_TASKS_PER_WINDOW} and cumulative demanding time "
        f"is at or below {config.MAX_DEMANDING_TASK_HOURS_PER_WINDOW} min. Review "
        f"under rule {conflict.rule_id}; this may reduce risk under rule "
        f"{conflict.rule_id}."
    )
    benefit = (
        f"Brings the workload window to at or below the configured "
        f"{config.MAX_DEMANDING_TASKS_PER_WINDOW} task(s) and "
        f"{config.MAX_DEMANDING_TASK_HOURS_PER_WINDOW} demanding minutes under "
        f"rule {conflict.rule_id}; no physiological effect is claimed."
    )
    explanation = (
        f"{details} The recommendation reviews task distribution only and does "
        "not assume that any task can move without mission approval."
    )
    warnings = (
        []
        if tasks
        else [
            "Task details were not available in the context; task ids come from "
            "the conflict."
        ]
    )
    return _build(
        context=context,
        conflict=conflict,
        recommendation_type=RecommendationType.redistribute_demanding_tasks,
        countermeasure=_CM_04,
        reason=reason,
        suggested_action=action,
        expected_benefit=benefit,
        explanation=explanation,
        preconditions=[
            "Mission planner confirms that at least one demanding task can move "
            "to another window."
        ],
        warnings=warnings,
        requires_medical_review=False,
    )


def _high_fatigue_recommendation(
    context: AstronautContext,
    conflict: Conflict,
    config: MissionConfig,
) -> Recommendation:
    """Recommend reviewing critical-task timing under a fatigue signal (CM-02)."""
    task = _first_task(context, conflict)
    if task is not None:
        task_text = _task_phrase(task)
        alertness = (
            "unknown"
            if task.required_alertness is None
            else str(task.required_alertness)
        )
    else:
        task_text = f"the task(s) {', '.join(conflict.task_ids)}"
        alertness = "unknown"

    level = context.fatigue_signal.level
    medical_review = level is FatigueLevel.elevated_concern
    reason = (
        f"Rule {conflict.rule_id} reports fatigue level '{level.value}' (source "
        f"'{context.fatigue_signal.source}') before {task_text}. The task "
        f"requires alertness {alertness} on the project scale."
    )
    action = (
        "Consider moving the critical task to a different schedule window or "
        "inserting a recovery opportunity before it. Review under rule "
        f"{conflict.rule_id}; this may reduce risk under rule {conflict.rule_id}."
    )
    benefit = (
        f"Removes the co-occurrence of a '{level.value}' fatigue signal with a "
        f"critical task under rule {conflict.rule_id}; no physiological effect is "
        "claimed."
    )
    explanation = (
        "The fatigue input is a categorical assessment signal, not a measurement "
        "of impairment. The recommendation reviews timing only and does not "
        "propose any clinical action."
    )
    warnings: list[str] = []
    if medical_review:
        warnings.append(
            "The recorded fatigue level is 'elevated_concern'; a medical review "
            "is flagged for this advisory."
        )
    return _build(
        context=context,
        conflict=conflict,
        recommendation_type=RecommendationType.review_task_timing,
        countermeasure=_CM_02,
        reason=reason,
        suggested_action=action,
        expected_benefit=benefit,
        explanation=explanation,
        preconditions=[
            "Mission planner and, when flagged, medical staff review the task "
            "timing."
        ],
        warnings=warnings,
        requires_medical_review=medical_review,
    )


def _circadian_recommendation(
    context: AstronautContext,
    conflict: Conflict,
    config: MissionConfig,
) -> Recommendation:
    """Recommend timing and lighting review when circadian placement is flagged."""
    task = _first_task(context, conflict)
    task_text = (
        _task_phrase(task)
        if task is not None
        else f"the task(s) {', '.join(conflict.task_ids)}"
    )
    window = (
        context.planned_sleep_windows[0]
        if context.planned_sleep_windows
        else None
    )
    window_text = (
        _window_phrase(window) if window is not None else _fallback_window_phrase(config)
    )
    wocl_text = (
        f"{config.WOCL_START_HOUR:02d}:00-{config.WOCL_END_HOUR:02d}:00 UTC with "
        f"{config.WOCL_TOLERANCE_MINUTES} min tolerance"
    )
    trigger_terms = _circadian_trigger_terms(conflict)
    trigger_text = _join_terms(trigger_terms)
    wocl_triggered = any("WOCL" in term for term in trigger_terms)
    sleep_triggered = any(
        "sleep period" in term or "sleep window" in term for term in trigger_terms
    )

    reason = (
        f"{conflict.explanation} This astronaut's habitual sleep reference is "
        f"{window_text}."
    )
    if wocl_triggered:
        reason = f"{reason} The configured WOCL is {wocl_text}."
    action = (
        f"Consider moving {task_text} outside {trigger_text}. Also review the "
        "lighting exposure schedule so light exposure matches this astronaut's "
        f"sleep-wake pattern. Review under rule {conflict.rule_id}; this may "
        f"reduce risk under rule {conflict.rule_id}."
    )
    benefit = (
        f"Moves the task outside {trigger_text} or aligns the lighting schedule "
        f"with the crew sleep-wake pattern under rule {conflict.rule_id}; the "
        "system cannot control spacecraft lighting and no physiological effect is "
        "claimed."
    )
    if wocl_triggered and sleep_triggered:
        explanation = (
            "The sleep-period reference and the WOCL are configurable clock "
            "models, not measurements of circadian phase. The recommendation is "
            "limited to task timing and lighting review."
        )
    elif wocl_triggered:
        explanation = (
            "The WOCL is a configurable clock model, not a measurement of "
            "circadian phase. The recommendation is limited to task timing and "
            "lighting review."
        )
    else:
        explanation = (
            "The referenced sleep period is a configurable schedule model, not a "
            "measurement of circadian phase. The recommendation is limited to "
            "task timing and lighting review."
        )
    return _build(
        context=context,
        conflict=conflict,
        recommendation_type=RecommendationType.evaluate_lighting_schedule,
        countermeasure=_CM_05,
        reason=reason,
        suggested_action=action,
        expected_benefit=benefit,
        explanation=explanation,
        preconditions=[
            "Mission planner or habitat lighting owner reviews the lighting "
            "schedule."
        ],
        warnings=[],
        requires_medical_review=False,
    )


_BUILDERS: dict[ConflictType, RecommendationBuilder] = {
    ConflictType.task_overlap: _task_overlap_recommendation,
    ConflictType.sleep_window_conflict: _sleep_window_recommendation,
    ConflictType.circadian_low_alertness: _circadian_recommendation,
    ConflictType.insufficient_recovery_gap: _recovery_recommendation,
    ConflictType.workload_overload: _workload_recommendation,
    ConflictType.high_fatigue_critical_task: _high_fatigue_recommendation,
}
"""Mapped conflict types. ``insufficient_data`` is intentionally absent: the
generator reviews only conflicts and never invents a recommendation for a
missing-data finding."""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def generate_recommendations(
    context: AstronautContext,
    conflicts: ConflictReport | Iterable[Conflict],
    config: MissionConfig = DEFAULT_CONFIG,
) -> list[Recommendation]:
    """Turn conflicts into deterministic, personalised advisory recommendations.

    Args:
        context: The single-crew astronaut context the conflicts were computed
            from. It supplies the sleep target, habitual sleep windows, task
            schedule, free gaps, and fatigue signal used for personalisation.
        conflicts: A ``ConflictReport`` or an iterable of ``Conflict`` objects.
        config: Immutable threshold set.

    Returns:
        At most ``config.MAX_RECOMMENDATIONS_PER_RESPONSE`` recommendations,
        ordered by priority (highest first), then related conflict id, then
        recommendation id. A conflict of type ``insufficient_data`` produces no
        recommendation.

    Raises:
        ValueError: if a conflict belongs to another astronaut; a context is
            single-crew by contract.
    """
    conflict_list = (
        list(conflicts.conflicts)
        if isinstance(conflicts, ConflictReport)
        else list(conflicts)
    )
    for conflict in conflict_list:
        if conflict.astronaut_id != context.crew.crew_id:
            raise ValueError(
                "conflicts contains a finding for another astronaut: "
                f"{conflict.conflict_id!r} belongs to {conflict.astronaut_id!r}, "
                f"not {context.crew.crew_id!r}"
            )

    recommendations: list[Recommendation] = []
    for conflict in conflict_list:
        builder = _BUILDERS.get(conflict.conflict_type)
        if builder is None:
            continue
        recommendations.append(builder(context, conflict, config))

    recommendations.sort(
        key=lambda recommendation: (
            -_PRIORITY_RANK[recommendation.priority],
            recommendation.related_conflict_id,
            recommendation.recommendation_id,
        )
    )
    return recommendations[: config.MAX_RECOMMENDATIONS_PER_RESPONSE]
