"""FastAPI router for mission intelligence (Person 4, Phase 7).

All routes live under ``/crew/{crew_id}/mission-intel``. ``app/main.py`` mounts
this router under ``/api/v1`` once it is registered in
``app/routers/__init__.py``.

Design rules:

* Reads go through ``app/services/history_service.py`` via the Phase 2 adapters.
* No task, assessment, or check-in is written. Follow-ups use the process-local
  store in ``followups.py`` (see that module for why no table is used).
* Unknown crew -> 404; invalid windows, operations, or values -> 422.
* Every successful response carries ``data_warnings``. A missing assessment is
  reported as ``no_assessment_available`` rather than silently treated as safe.
* Wording remains advisory. No response diagnoses, predicts impairment, or
  recommends medication.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.database import get_session, utcnow
from app.mission.adapters import AssessmentFatigueProvider, build_context
from app.mission.api_models import (
    AddRecoveryPeriodOperation,
    ApiDataWarning,
    AppliedOperation,
    ConflictListResponse,
    DelayTaskOperation,
    FollowUpCreate,
    FollowUpResponse,
    FollowUpUpdate,
    HealthSummary,
    ModifySleepWindowOperation,
    MoveTaskOperation,
    OverviewResponse,
    RecommendationListResponse,
    RedistributeWorkloadOperation,
    ScheduleResponse,
    ScheduleView,
    TaskSuitability,
    WhatIfRequest,
    WhatIfResponse,
)
from app.mission.conflicts import RULE_SET_VERSION, detect_conflicts
from app.mission.config import DEFAULT_CONFIG
from app.mission.errors import (
    MissionCrewNotFound,
    MissionRecommendationNotFound,
    MissionRoute,
    MissionValidationError,
)
from app.mission.followups import (
    apply_follow_up_action,
    create_follow_up,
)
from app.mission.integration import evaluate_upcoming
from app.mission.models import (
    AstronautContext,
    ConflictReport,
    FatigueLevel,
    Recommendation,
    SleepSummary,
)
from app.mission.recommendations import generate_recommendations
from app.mission.scenarios import (
    add_recovery_period,
    compare,
    delay_task,
    modify_sleep_window,
    move_task,
    redistribute_workload,
)
from app.mission.schedule import day_bounds, week_bounds
from app.services.history_service import get_crew

router = APIRouter(route_class=MissionRoute, tags=["mission-intel"])

_FOLLOW_UP_STORE_WARNING = ApiDataWarning(
    code="follow_up_store_is_process_local",
    message=(
        "Follow-ups are stored in process memory for this phase; they are cleared "
        "when the API process restarts. No mission task is changed by a follow-up."
    ),
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _resolve_window(
    window_start: datetime | None,
    window_end: datetime | None,
) -> tuple[datetime, datetime]:
    """Return the requested window, or the default planning horizon."""
    if (window_start is None) != (window_end is None):
        raise MissionValidationError(
            "window_start and window_end must be supplied together."
        )
    if window_start is None:
        start = utcnow().replace(microsecond=0)
        end = start + timedelta(hours=DEFAULT_CONFIG.PLANNING_HORIZON_HOURS)
        return start, end
    assert window_end is not None  # guarded by the pair check above
    return window_start, window_end


def _context_or_error(
    session: Session,
    crew_id: str,
    window_start: datetime,
    window_end: datetime,
) -> AstronautContext:
    """Build an astronaut context, mapping expected failures to HTTP errors."""
    try:
        return build_context(
            session,
            crew_id,
            window_start,
            window_end,
            AssessmentFatigueProvider(),
        )
    except LookupError as exc:
        raise MissionCrewNotFound(crew_id) from exc
    except ValueError as exc:
        raise MissionValidationError(str(exc)) from exc


def _latest_sleep(context: AstronautContext) -> SleepSummary | None:
    """Return the most recent recorded sleep summary, if any."""
    return max(
        context.recent_sleep,
        key=lambda summary: (summary.end_time, summary.sleep_id),
        default=None,
    )


def _dedupe(warnings: list[ApiDataWarning]) -> list[ApiDataWarning]:
    """Remove duplicate warnings while preserving order."""
    seen: set[tuple[str, str | None, str | None, str]] = set()
    unique: list[ApiDataWarning] = []
    for warning in warnings:
        key = (warning.code, warning.rule_id, warning.task_id, warning.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(warning)
    return unique


def _context_warnings(
    context: AstronautContext,
    report: ConflictReport | None = None,
) -> list[ApiDataWarning]:
    """Build the stable warning list for a successful response."""
    warnings: list[ApiDataWarning] = []

    if context.fatigue_signal.source == "assessment:none":
        warnings.append(
            ApiDataWarning(
                code="no_assessment_available",
                message=(
                    "No Assessment row is available for this crew member, so the "
                    "fatigue level is 'unknown'. Suitability results that need a "
                    "fatigue signal are reported as insufficient_data."
                ),
            )
        )
    elif context.fatigue_signal.level is FatigueLevel.unknown:
        warnings.append(
            ApiDataWarning(
                code="assessment_insufficient_data",
                message=(
                    "The latest Assessment reports insufficient_data, so the "
                    "fatigue level is 'unknown'."
                ),
            )
        )

    if not context.recent_sleep:
        warnings.append(
            ApiDataWarning(
                code="no_recent_sleep",
                message=(
                    "No recent SleepRecord is available; sleep-shortfall rules "
                    "and sleep history comparisons were not evaluated."
                ),
            )
        )
    if not context.planned_sleep_windows:
        warnings.append(
            ApiDataWarning(
                code="no_planned_sleep_window",
                message=(
                    "No habitual sleep window could be inferred; sleep-window "
                    "overlap rules were not evaluated and the circadian rule used "
                    "the configured fallback window."
                ),
            )
        )
    if not context.tasks:
        warnings.append(
            ApiDataWarning(
                code="no_tasks_in_window",
                message="No mission task starts inside the requested window.",
            )
        )

    if report is not None:
        for warning in report.data_warnings:
            warnings.append(
                ApiDataWarning(
                    code="conflict_data_warning",
                    message=warning.message,
                    rule_id=warning.rule_id,
                    task_id=warning.task_id,
                )
            )
    return _dedupe(warnings)


def _apply_operation(context: AstronautContext, operation) -> AstronautContext:
    """Apply one discriminated what-if operation to a context."""
    if isinstance(operation, DelayTaskOperation):
        return delay_task(context, operation.task_id, operation.minutes)
    if isinstance(operation, MoveTaskOperation):
        return move_task(context, operation.task_id, operation.new_start)
    if isinstance(operation, AddRecoveryPeriodOperation):
        kwargs = {}
        if operation.name is not None:
            kwargs["name"] = operation.name
        return add_recovery_period(
            context,
            operation.start,
            operation.end,
            shift_following_tasks=operation.shift_following_tasks,
            task_id=operation.task_id,
            **kwargs,
        )
    if isinstance(operation, RedistributeWorkloadOperation):
        return redistribute_workload(
            context, operation.task_id, operation.new_start
        )
    if isinstance(operation, ModifySleepWindowOperation):
        return modify_sleep_window(
            context,
            operation.new_start,
            operation.new_end,
            window_index=operation.window_index,
        )
    raise MissionValidationError(
        f"Unsupported what-if operation: {type(operation).__name__}"
    )


def _recommendation_for(
    context: AstronautContext,
    recommendation_id: str,
) -> Recommendation:
    """Return the current recommendation with the given id or raise 404."""
    report = detect_conflicts(context)
    recommendations = generate_recommendations(context, report)
    for recommendation in recommendations:
        if recommendation.recommendation_id == recommendation_id:
            return recommendation
    raise MissionRecommendationNotFound(recommendation_id)


# ---------------------------------------------------------------------------
# GET schedule
# ---------------------------------------------------------------------------


@router.get(
    "/crew/{crew_id}/mission-intel/schedule",
    response_model=ScheduleResponse,
)
def get_schedule(
    crew_id: str,
    view: ScheduleView = Query(default=ScheduleView.daily),
    schedule_date: date | None = Query(
        default=None,
        alias="date",
        description="UTC calendar date. Defaults to today in UTC.",
    ),
    session: Session = Depends(get_session),
) -> ScheduleResponse:
    """Return one daily or weekly schedule for a crew member.

    A day is the half-open UTC interval ``[00:00, next 00:00)``. A week starts at
    the requested date's UTC midnight and lasts seven days; it is not forced to
    Monday.

    Limitation inherited from ``get_upcoming_tasks``: only tasks that *start*
    inside the window are loaded. A task that starts before the window and
    overlaps into it is not returned, even though the local overlap filter would
    accept it.
    """
    selected_date = schedule_date or utcnow().date()
    if view is ScheduleView.daily:
        window_start, window_end = day_bounds(selected_date)
    else:
        window_start, window_end = week_bounds(selected_date)

    context = _context_or_error(session, crew_id, window_start, window_end)
    tasks = sorted(
        (
            task
            for task in context.tasks
            if task.start_time < window_end and task.end_time > window_start
        ),
        key=lambda task: (task.start_time, task.task_id),
    )
    return ScheduleResponse(
        crew_id=crew_id,
        view=view,
        window_start=window_start,
        window_end=window_end,
        tasks=tasks,
        planned_sleep_windows=context.planned_sleep_windows,
        data_warnings=_context_warnings(context),
    )


# ---------------------------------------------------------------------------
# GET overview
# ---------------------------------------------------------------------------


@router.get(
    "/crew/{crew_id}/mission-intel/overview",
    response_model=OverviewResponse,
)
def get_overview(
    crew_id: str,
    window_start: datetime | None = Query(default=None),
    window_end: datetime | None = Query(default=None),
    session: Session = Depends(get_session),
) -> OverviewResponse:
    """Return health, upcoming tasks, suitability, and advisory counts.

    The default window is now to now + ``PLANNING_HORIZON_HOURS``. Suitability
    results are advisory only and may be ``insufficient_data`` when the fatigue
    or sleep inputs are missing.
    """
    start, end = _resolve_window(window_start, window_end)
    context = _context_or_error(session, crew_id, start, end)
    report = detect_conflicts(context)
    recommendations = generate_recommendations(context, report)
    suitability = evaluate_upcoming(context)
    task_by_id = {task.task_id: task for task in context.tasks}
    upcoming = [
        TaskSuitability(task=task_by_id[result.task_id], suitability=result)
        for result in suitability
        if result.task_id in task_by_id
    ]
    return OverviewResponse(
        crew=context.crew,
        health=HealthSummary(
            fatigue_signal=context.fatigue_signal,
            latest_sleep=_latest_sleep(context),
            recent_sleep=context.recent_sleep,
            planned_sleep_windows=context.planned_sleep_windows,
        ),
        window_start=start,
        window_end=end,
        upcoming_tasks=upcoming,
        conflict_count=len(report.conflicts),
        recommendation_count=len(recommendations),
        data_warnings=_context_warnings(context, report),
    )


# ---------------------------------------------------------------------------
# GET conflicts
# ---------------------------------------------------------------------------


@router.get(
    "/crew/{crew_id}/mission-intel/conflicts",
    response_model=ConflictListResponse,
)
def get_conflicts(
    crew_id: str,
    window_start: datetime | None = Query(default=None),
    window_end: datetime | None = Query(default=None),
    session: Session = Depends(get_session),
) -> ConflictListResponse:
    """Return the rule-based conflict report for one crew and window."""
    start, end = _resolve_window(window_start, window_end)
    context = _context_or_error(session, crew_id, start, end)
    report = detect_conflicts(context)
    return ConflictListResponse(
        crew_id=crew_id,
        window_start=start,
        window_end=end,
        rule_set_version=RULE_SET_VERSION,
        conflicts=report.conflicts,
        config_keys=report.config_keys,
        data_warnings=_context_warnings(context, report),
    )


# ---------------------------------------------------------------------------
# GET recommendations
# ---------------------------------------------------------------------------


@router.get(
    "/crew/{crew_id}/mission-intel/recommendations",
    response_model=RecommendationListResponse,
)
def get_recommendations(
    crew_id: str,
    window_start: datetime | None = Query(default=None),
    window_end: datetime | None = Query(default=None),
    session: Session = Depends(get_session),
) -> RecommendationListResponse:
    """Return advisory recommendations derived from the conflict report."""
    start, end = _resolve_window(window_start, window_end)
    context = _context_or_error(session, crew_id, start, end)
    report = detect_conflicts(context)
    recommendations = generate_recommendations(context, report)
    return RecommendationListResponse(
        crew_id=crew_id,
        window_start=start,
        window_end=end,
        conflict_count=len(report.conflicts),
        recommendations=recommendations,
        data_warnings=_context_warnings(context, report),
    )


# ---------------------------------------------------------------------------
# POST what-if
# ---------------------------------------------------------------------------


@router.post(
    "/crew/{crew_id}/mission-intel/what-if",
    response_model=WhatIfResponse,
)
def post_what_if(
    crew_id: str,
    payload: WhatIfRequest,
    session: Session = Depends(get_session),
) -> WhatIfResponse:
    """Compare a transient schedule edit against the original schedule.

    Operations are applied in order to an in-memory copy of the context. Nothing
    is persisted. Malformed or impossible operations return 422. The comparison
    reports rule-based metrics only and never re-predicts fatigue.
    """
    context = _context_or_error(
        session, crew_id, payload.window_start, payload.window_end
    )
    proposed = context
    applied: list[AppliedOperation] = []
    for index, operation in enumerate(payload.operations):
        try:
            proposed = _apply_operation(proposed, operation)
        except MissionValidationError:
            raise
        except ValueError as exc:
            raise MissionValidationError(
                f"Operation {index} ({operation.type}) is invalid: {exc}",
                details={"operation_index": index, "operation_type": operation.type},
            ) from exc
        applied.append(
            AppliedOperation(
                index=index,
                type=operation.type,
                task_id=getattr(operation, "task_id", None),
            )
        )

    try:
        comparison = compare(
            context,
            proposed,
            window_start=payload.window_start,
            window_end=payload.window_end,
        )
    except ValueError as exc:
        raise MissionValidationError(str(exc)) from exc

    original_report = detect_conflicts(context)
    proposed_report = detect_conflicts(proposed)
    warnings = _context_warnings(context, original_report)
    warnings.extend(_context_warnings(proposed, proposed_report))
    return WhatIfResponse(
        crew_id=crew_id,
        window_start=payload.window_start,
        window_end=payload.window_end,
        applied_operations=applied,
        comparison=comparison,
        data_warnings=_dedupe(warnings),
    )


# ---------------------------------------------------------------------------
# POST / PATCH follow-ups
# ---------------------------------------------------------------------------


@router.post(
    "/crew/{crew_id}/mission-intel/follow-ups",
    response_model=FollowUpResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_follow_up(
    crew_id: str,
    payload: FollowUpCreate,
    session: Session = Depends(get_session),
) -> FollowUpResponse:
    """Create an advisory follow-up from a current recommendation.

    The recommendation is regenerated from the same window, so the request can
    only reference a recommendation that the rules currently produce for this
    crew. The follow-up starts in ``suggested`` status and changes nothing.
    """
    start, end = _resolve_window(payload.window_start, payload.window_end)
    context = _context_or_error(session, crew_id, start, end)
    recommendation = _recommendation_for(context, payload.recommendation_id)
    record = create_follow_up(crew_id, recommendation, payload.due_at)
    report = detect_conflicts(context)
    return FollowUpResponse(
        follow_up=record,
        data_warnings=_dedupe(
            _context_warnings(context, report) + [_FOLLOW_UP_STORE_WARNING]
        ),
    )


@router.patch(
    "/crew/{crew_id}/mission-intel/follow-ups/{follow_up_id}",
    response_model=FollowUpResponse,
)
def patch_follow_up(
    crew_id: str,
    follow_up_id: str,
    payload: FollowUpUpdate,
    session: Session = Depends(get_session),
) -> FollowUpResponse:
    """Apply ``accept``, ``skip``, or ``complete`` to a follow-up.

    Completing a follow-up that requires mission approval requires
    ``approved=true``. ``skipped`` and ``completed`` are terminal states and
    return 409 if transitioned again.
    """
    if get_crew(session, crew_id) is None:
        raise MissionCrewNotFound(crew_id)
    record = apply_follow_up_action(
        crew_id,
        follow_up_id,
        payload.action,
        approved=payload.approved,
        result=payload.result,
    )
    return FollowUpResponse(
        follow_up=record,
        data_warnings=[_FOLLOW_UP_STORE_WARNING],
    )
