"""Process-local follow-up records for the mission-intelligence API.

Why this is not in the database
-------------------------------
The project forbids database schema changes in this phase, and the existing
``ActionHistory`` table cannot store the recommendation linkage that the Phase 7
contract exposes: it has no ``recommendation_id`` or ``rule_id`` column, and its
``countermeasure_id`` is a foreign key to the ``Countermeasure`` catalogue, which
the demo seed does not populate. Writing ``ActionHistory`` rows would therefore
either lose the recommendation link or require creating catalogue rows at
request time.

This module keeps follow-ups in a module-level, lock-protected dictionary. The
records survive for the lifetime of the process only; a restart clears them.
That limitation is documented in ``docs/05_api_contracts.md``. A persistent
implementation can replace this module without changing the HTTP contract once
a storage decision is approved.

Follow-ups are advisory bookkeeping only. Accepting, skipping, or completing one
never edits a mission task or applies a countermeasure.
"""

from __future__ import annotations

import threading
from datetime import datetime
from uuid import uuid4

from app.core.database import utcnow
from app.mission.api_models import FollowUpAction, FollowUpRead
from app.mission.errors import (
    MissionApprovalRequired,
    MissionFollowUpNotFound,
    MissionStatusConflict,
)
from app.mission.models import Recommendation
from app.models.enums import ActionStatus

_STORE: dict[str, FollowUpRead] = {}
"""Follow-up records keyed by id. Guarded by ``_LOCK``."""

_LOCK = threading.RLock()

_TARGET_STATUS: dict[FollowUpAction, ActionStatus] = {
    FollowUpAction.accept: ActionStatus.accepted,
    FollowUpAction.skip: ActionStatus.skipped,
    FollowUpAction.complete: ActionStatus.completed,
}

_ALLOWED_TRANSITIONS: dict[ActionStatus, frozenset[ActionStatus]] = {
    ActionStatus.suggested: frozenset(
        {ActionStatus.accepted, ActionStatus.skipped, ActionStatus.completed}
    ),
    ActionStatus.accepted: frozenset(
        {ActionStatus.skipped, ActionStatus.completed}
    ),
    ActionStatus.skipped: frozenset(),
    ActionStatus.completed: frozenset(),
}
"""Allowed lifecycle transitions. Skipped and completed are terminal."""


def reset_follow_ups() -> None:
    """Clear the store. Intended for tests and development only."""
    with _LOCK:
        _STORE.clear()


def create_follow_up(
    crew_id: str,
    recommendation: Recommendation,
    due_at: datetime | None = None,
) -> FollowUpRead:
    """Create a ``suggested`` follow-up from a recommendation.

    The recommendation is copied into the record so later changes to the
    deterministic recommendation text cannot rewrite the history.
    """
    now = utcnow()
    record = FollowUpRead(
        follow_up_id=f"fu_{uuid4().hex}",
        crew_id=crew_id,
        recommendation_id=recommendation.recommendation_id,
        related_conflict_id=recommendation.related_conflict_id,
        countermeasure_id=recommendation.countermeasure_id,
        countermeasure_name=recommendation.countermeasure_name,
        rule_id=recommendation.rule_id,
        status=ActionStatus.suggested,
        requires_mission_approval=recommendation.requires_mission_approval,
        requires_medical_review=recommendation.requires_medical_review,
        approved=None,
        due_at=due_at,
        result=None,
        advisory_text=recommendation.advisory_text,
        created_at=now,
        updated_at=now,
    )
    with _LOCK:
        _STORE[record.follow_up_id] = record
    return record


def get_follow_up(crew_id: str, follow_up_id: str) -> FollowUpRead:
    """Return one follow-up for ``crew_id`` or raise a 404 ``MissionError``."""
    with _LOCK:
        record = _STORE.get(follow_up_id)
    if record is None or record.crew_id != crew_id:
        raise MissionFollowUpNotFound(follow_up_id)
    return record


def apply_follow_up_action(
    crew_id: str,
    follow_up_id: str,
    action: FollowUpAction,
    *,
    approved: bool | None = None,
    result: str | None = None,
) -> FollowUpRead:
    """Apply one transition and return the updated record.

    Rules:

    * ``suggested`` may become ``accepted``, ``skipped``, or ``completed``.
    * ``accepted`` may become ``skipped`` or ``completed``.
    * ``skipped`` and ``completed`` are terminal.
    * Completing a follow-up whose recommendation requires mission approval
      requires ``approved=True`` either on this request or on an earlier one.
    """
    with _LOCK:
        record = get_follow_up(crew_id, follow_up_id)
        target = _TARGET_STATUS[action]
        if target not in _ALLOWED_TRANSITIONS[record.status]:
            raise MissionStatusConflict(
                f"Cannot change follow-up '{follow_up_id}' from "
                f"'{record.status.value}' to '{target.value}'.",
                details={
                    "follow_up_id": follow_up_id,
                    "current_status": record.status.value,
                    "requested_status": target.value,
                },
            )

        resolved_approval = record.approved if approved is None else approved
        if (
            target is ActionStatus.completed
            and record.requires_mission_approval
            and not resolved_approval
        ):
            raise MissionApprovalRequired(
                "This follow-up requires mission approval before it can be "
                "completed; send approved=true with the completion request.",
                details={
                    "follow_up_id": follow_up_id,
                    "requires_mission_approval": True,
                },
            )

        updated = record.model_copy(
            update={
                "status": target,
                "approved": resolved_approval,
                "result": result if result is not None else record.result,
                "updated_at": utcnow(),
            }
        )
        _STORE[follow_up_id] = updated
        return updated
