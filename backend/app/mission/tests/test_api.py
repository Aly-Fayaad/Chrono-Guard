"""End-to-end tests for the Phase 7 mission-intelligence API.

The tests exercise every endpoint through FastAPI's ``TestClient`` with the
mission router mounted under ``/api/v1`` and the database dependency pointed at
the isolated in-memory engine from ``conftest.py``.

Covered behaviour:

* schedule (daily/weekly), overview, conflicts, recommendations;
* the transient what-if comparison and its validation errors;
* the follow-up lifecycle, approval gate, and terminal states;
* the consistent error body for 404/409/422 and request validation;
* ``data_warnings`` on every successful response, including the missing-data
  codes and the process-local follow-up-store warning;
* the deterministic recommendation id contract used by follow-ups.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from app.models import Assessment, CrewProfile, MissionTask, SleepRecord
from app.models.enums import AssessmentStatus, QualityFlag, TaskType, WorkloadLevel

UTC = timezone.utc
CREW_ID = "crew-api"
WINDOW_START = datetime(2026, 11, 13, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 11, 14, 0, 0, tzinfo=UTC)
BASE = "/api/v1/crew"
MISSION_INTEL = f"{BASE}/{CREW_ID}/mission-intel"


def _iso(value: datetime) -> str:
    """Return an ISO-8601 UTC string accepted by the API."""
    return value.isoformat()


def _window_query() -> dict[str, str]:
    """Return the explicit baseline evaluation window as query parameters."""
    return {"window_start": _iso(WINDOW_START), "window_end": _iso(WINDOW_END)}


def _seed_crew_with_data(session_factory: Callable[[], Session]) -> None:
    """Insert a crew member, an elevated assessment, sleep, and conflicting tasks.

    The tasks deliberately place one high-workload task at 03:00 UTC on
    2026-11-13 and seed a matching habitual sleep window, so the Phase 4 rules
    produce circadian, sleep-window, and high-fatigue findings. A second task in
    the morning keeps the schedule realistic and gives the what-if test a
    non-conflicting destination.
    """
    with session_factory() as session:
        session.add(
            CrewProfile(
                id=CREW_ID,
                display_name="API Test Crew",
                role="commander",
                sleep_target_hours=8.0,
            )
        )
        session.add(
            Assessment(
                id="assessment-api",
                crew_id=CREW_ID,
                status=AssessmentStatus.elevated_concern,
                summary="Synthetic elevated-concern result for API tests.",
                explanation="Test fixture only.",
                contributing_factors=[{"factor": "synthetic_test_input"}],
                engine_version="test",
                created_at=datetime(2026, 11, 13, 6, 0, tzinfo=UTC),
            )
        )
        for index in range(3):
            day = 10 + index
            session.add(
                SleepRecord(
                    id=f"sleep-api-{index}",
                    crew_id=CREW_ID,
                    sleep_start=datetime(2026, 11, day, 22, 0, tzinfo=UTC),
                    sleep_end=datetime(2026, 11, day + 1, 6, 0, tzinfo=UTC),
                    duration_hours=8.0,
                    interruptions=0,
                    quality=QualityFlag.valid,
                )
            )
        session.add(
            MissionTask(
                id="task-wake",
                crew_id=CREW_ID,
                title="Night wake",
                task_type=TaskType.maintenance,
                start_time=datetime(2026, 11, 13, 3, 0, tzinfo=UTC),
                end_time=datetime(2026, 11, 13, 4, 0, tzinfo=UTC),
                workload_level=WorkloadLevel.high,
                is_critical=False,
            )
        )
        session.add(
            MissionTask(
                id="task-day",
                crew_id=CREW_ID,
                title="Day maintenance",
                task_type=TaskType.maintenance,
                start_time=datetime(2026, 11, 13, 10, 0, tzinfo=UTC),
                end_time=datetime(2026, 11, 13, 11, 0, tzinfo=UTC),
                workload_level=WorkloadLevel.medium,
                is_critical=False,
            )
        )
        session.commit()


def _seed_empty_crew(session_factory: Callable[[], Session], crew_id: str) -> None:
    """Insert a crew member with no assessment, sleep, or tasks."""
    with session_factory() as session:
        session.add(
            CrewProfile(
                id=crew_id,
                display_name="Empty Crew",
                role="specialist",
                sleep_target_hours=7.5,
            )
        )
        session.commit()


@pytest.fixture()
def seeded(session_factory: Callable[[], Session]) -> str:
    """Seed the shared API fixture data and return the crew id."""
    _seed_crew_with_data(session_factory)
    return CREW_ID


def _warning_codes(payload: dict) -> set[str]:
    """Return the set of warning codes in an API response."""
    return {warning["code"] for warning in payload["data_warnings"]}


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------


def test_schedule_daily(client, seeded) -> None:
    """A daily schedule returns the explicit date's UTC window and tasks."""
    response = client.get(
        f"{MISSION_INTEL}/schedule",
        params={"view": "daily", "date": "2026-11-13"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["crew_id"] == CREW_ID
    assert body["view"] == "daily"
    assert body["window_start"].startswith("2026-11-13T00:00:00")
    assert body["window_end"].startswith("2026-11-14T00:00:00")
    task_ids = [task["task_id"] for task in body["tasks"]]
    assert task_ids == ["task-wake", "task-day"]
    assert body["planned_sleep_windows"]
    assert "data_warnings" in body


def test_schedule_weekly(client, seeded) -> None:
    """A weekly schedule covers seven UTC days from the requested date."""
    response = client.get(
        f"{MISSION_INTEL}/schedule",
        params={"view": "weekly", "date": "2026-11-13"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["view"] == "weekly"
    start = datetime.fromisoformat(body["window_start"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(body["window_end"].replace("Z", "+00:00"))
    assert end - start == timedelta(days=7)
    assert {task["task_id"] for task in body["tasks"]} == {"task-wake", "task-day"}


def test_schedule_unknown_crew_returns_consistent_error(client) -> None:
    """An unknown crew returns 404 with the shared error body."""
    response = client.get(
        f"{BASE}/crew-missing/mission-intel/schedule",
        params={"view": "daily", "date": "2026-11-13"},
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "crew_not_found"
    assert body["error"]["details"] == {"crew_id": "crew-missing"}
    assert body["data_warnings"] == []


def test_schedule_invalid_view_returns_validation_error(client, seeded) -> None:
    """An unsupported schedule view is rendered with the mission error body."""
    response = client.get(
        f"{MISSION_INTEL}/schedule",
        params={"view": "monthly", "date": "2026-11-13"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Request validation failed."
    assert body["error"]["details"]


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


def test_overview_includes_health_tasks_and_counts(client, seeded) -> None:
    """The overview combines health, suitability, and advisory counts."""
    response = client.get(f"{MISSION_INTEL}/overview", params=_window_query())
    assert response.status_code == 200
    body = response.json()
    assert body["crew"]["crew_id"] == CREW_ID
    assert body["health"]["fatigue_signal"]["level"] == "elevated_concern"
    assert body["health"]["latest_sleep"]["sleep_id"] == "sleep-api-2"
    assert body["upcoming_tasks"]
    assert all(item["suitability"]["task_id"] for item in body["upcoming_tasks"])
    assert body["conflict_count"] >= 1
    assert body["recommendation_count"] >= 1
    assert body["data_warnings"] == []


def test_overview_missing_data_warnings(client, session_factory) -> None:
    """A crew with no data gets explicit warnings instead of a silent safe answer."""
    _seed_empty_crew(session_factory, "crew-empty")
    response = client.get(
        f"{BASE}/crew-empty/mission-intel/overview", params=_window_query()
    )
    assert response.status_code == 200
    body = response.json()
    codes = _warning_codes(body)
    assert {
        "no_assessment_available",
        "no_recent_sleep",
        "no_planned_sleep_window",
        "no_tasks_in_window",
    } <= codes
    assert body["health"]["fatigue_signal"]["level"] == "unknown"


def test_overview_insufficient_assessment_warning(client, session_factory) -> None:
    """An insufficient_data assessment is reported distinctly."""
    _seed_empty_crew(session_factory, "crew-insufficient")
    with session_factory() as session:
        session.add(
            Assessment(
                id="assessment-insufficient",
                crew_id="crew-insufficient",
                status=AssessmentStatus.insufficient_data,
                summary="Not enough data.",
                explanation="Test fixture only.",
                contributing_factors=[],
                engine_version="test",
                created_at=datetime(2026, 11, 13, 6, 0, tzinfo=UTC),
            )
        )
        session.commit()
    response = client.get(
        f"{BASE}/crew-insufficient/mission-intel/overview", params=_window_query()
    )
    assert response.status_code == 200
    assert "assessment_insufficient_data" in _warning_codes(response.json())


def test_overview_default_window(client, seeded) -> None:
    """Omitting the window uses the configured default horizon."""
    response = client.get(f"{MISSION_INTEL}/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["window_end"] > body["window_start"]


# ---------------------------------------------------------------------------
# Conflicts and recommendations
# ---------------------------------------------------------------------------


def test_conflicts_are_returned_with_rule_metadata(client, seeded) -> None:
    """The conflict report exposes rule ids, explanations, and config keys."""
    response = client.get(f"{MISSION_INTEL}/conflicts", params=_window_query())
    assert response.status_code == 200
    body = response.json()
    assert body["crew_id"] == CREW_ID
    assert body["rule_set_version"]
    assert body["conflicts"]
    assert body["config_keys"]
    for conflict in body["conflicts"]:
        assert conflict["rule_id"]
        assert conflict["explanation"]
        assert conflict["suggested_action"]
        assert conflict["affected_start"]
    assert "data_warnings" in body


def test_recommendations_are_deterministic(client, seeded) -> None:
    """Repeated evaluation returns identical recommendation ids."""
    first = client.get(
        f"{MISSION_INTEL}/recommendations", params=_window_query()
    )
    second = client.get(
        f"{MISSION_INTEL}/recommendations", params=_window_query()
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body["recommendations"]
    assert first_body["conflict_count"] == second_body["conflict_count"]
    assert [
        item["recommendation_id"] for item in first_body["recommendations"]
    ] == [item["recommendation_id"] for item in second_body["recommendations"]]
    assert all(
        item["requires_mission_approval"] for item in first_body["recommendations"]
    )


def test_recommendations_unknown_crew(client) -> None:
    """Unknown crew is a 404, even for a read-only endpoint."""
    response = client.get(
        f"{BASE}/crew-missing/mission-intel/recommendations",
        params=_window_query(),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "crew_not_found"


# ---------------------------------------------------------------------------
# What-if
# ---------------------------------------------------------------------------


def test_what_if_move_task_compares_rule_metrics(client, seeded) -> None:
    """Moving the night task later resolves conflicts in rule metrics."""
    payload = {
        "window_start": _iso(WINDOW_START),
        "window_end": _iso(WINDOW_END),
        "operations": [
            {
                "type": "move_task",
                "task_id": "task-wake",
                "new_start": _iso(datetime(2026, 11, 13, 12, 0, tzinfo=UTC)),
            }
        ],
    }
    response = client.post(f"{MISSION_INTEL}/what-if", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["applied_operations"] == [
        {"index": 0, "type": "move_task", "task_id": "task-wake"}
    ]
    comparison = body["comparison"]
    assert comparison["conflict_count_delta"] <= 0
    assert comparison["resolved_conflicts"]
    assert comparison["note"] == (
        "Fatigue was not re-predicted; this comparison reflects schedule rules only."
    )
    assert comparison["original_metrics"]["total_conflicts"] >= (
        comparison["proposed_metrics"]["total_conflicts"]
    )
    assert "data_warnings" in body


def test_what_if_delay_task(client, seeded) -> None:
    """A positive delay is a valid operation."""
    payload = {
        "window_start": _iso(WINDOW_START),
        "window_end": _iso(WINDOW_END),
        "operations": [{"type": "delay_task", "task_id": "task-day", "minutes": 60}],
    }
    response = client.post(f"{MISSION_INTEL}/what-if", json=payload)
    assert response.status_code == 200
    assert response.json()["applied_operations"][0]["type"] == "delay_task"


def test_what_if_unknown_task_is_422(client, seeded) -> None:
    """An operation that names an unknown task is a mission validation error."""
    payload = {
        "window_start": _iso(WINDOW_START),
        "window_end": _iso(WINDOW_END),
        "operations": [
            {
                "type": "move_task",
                "task_id": "task-missing",
                "new_start": _iso(datetime(2026, 11, 13, 12, 0, tzinfo=UTC)),
            }
        ],
    }
    response = client.post(f"{MISSION_INTEL}/what-if", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"] == {
        "operation_index": 0,
        "operation_type": "move_task",
    }


def test_what_if_rejects_bad_discriminator(client, seeded) -> None:
    """An unknown operation type is rejected by request validation."""
    payload = {
        "window_start": _iso(WINDOW_START),
        "window_end": _iso(WINDOW_END),
        "operations": [{"type": "teleport_task", "task_id": "task-wake"}],
    }
    response = client.post(f"{MISSION_INTEL}/what-if", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_what_if_rejects_empty_operations(client, seeded) -> None:
    """At least one operation is required."""
    payload = {
        "window_start": _iso(WINDOW_START),
        "window_end": _iso(WINDOW_END),
        "operations": [],
    }
    response = client.post(f"{MISSION_INTEL}/what-if", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_what_if_rejects_naive_window(client, seeded) -> None:
    """Naive datetimes are rejected instead of being silently treated as UTC."""
    payload = {
        "window_start": "2026-11-13T00:00:00",
        "window_end": "2026-11-14T00:00:00",
        "operations": [{"type": "delay_task", "task_id": "task-day", "minutes": 60}],
    }
    response = client.post(f"{MISSION_INTEL}/what-if", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# ---------------------------------------------------------------------------
# Follow-ups
# ---------------------------------------------------------------------------


def _current_recommendation_id(client) -> str:
    """Fetch the first recommendation id for the baseline window."""
    response = client.get(
        f"{MISSION_INTEL}/recommendations", params=_window_query()
    )
    assert response.status_code == 200
    return response.json()["recommendations"][0]["recommendation_id"]


def _create_follow_up(client) -> dict:
    """Create a follow-up from the first current recommendation."""
    payload = {
        "recommendation_id": _current_recommendation_id(client),
        "window_start": _iso(WINDOW_START),
        "window_end": _iso(WINDOW_END),
    }
    response = client.post(f"{MISSION_INTEL}/follow-ups", json=payload)
    assert response.status_code == 201
    return response.json()["follow_up"]


def test_follow_up_accept_then_conflict(client, seeded) -> None:
    """Accepting is allowed once; a second accept is a 409."""
    follow_up = _create_follow_up(client)
    assert follow_up["status"] == "suggested"
    assert follow_up["requires_mission_approval"] is True

    accepted = client.patch(
        f"{MISSION_INTEL}/follow-ups/{follow_up['follow_up_id']}",
        json={"action": "accept"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["follow_up"]["status"] == "accepted"

    repeated = client.patch(
        f"{MISSION_INTEL}/follow-ups/{follow_up['follow_up_id']}",
        json={"action": "accept"},
    )
    assert repeated.status_code == 409
    body = repeated.json()
    assert body["error"]["code"] == "invalid_status_transition"
    assert body["error"]["details"]["current_status"] == "accepted"


def test_follow_up_completion_requires_approval(client, seeded) -> None:
    """Completing an approval-gated follow-up without approval is a 422."""
    follow_up = _create_follow_up(client)
    completed = client.patch(
        f"{MISSION_INTEL}/follow-ups/{follow_up['follow_up_id']}",
        json={"action": "complete"},
    )
    assert completed.status_code == 422
    assert completed.json()["error"]["code"] == "mission_approval_required"


def test_follow_up_complete_with_approval_is_terminal(client, seeded) -> None:
    """Approved completion succeeds and later transitions return 409."""
    follow_up = _create_follow_up(client)
    completed = client.patch(
        f"{MISSION_INTEL}/follow-ups/{follow_up['follow_up_id']}",
        json={"action": "complete", "approved": True, "result": "Reviewed and accepted."},
    )
    assert completed.status_code == 200
    record = completed.json()["follow_up"]
    assert record["status"] == "completed"
    assert record["approved"] is True
    assert record["result"] == "Reviewed and accepted."

    repeated = client.patch(
        f"{MISSION_INTEL}/follow-ups/{follow_up['follow_up_id']}",
        json={"action": "skip"},
    )
    assert repeated.status_code == 409


def test_follow_up_skip_is_terminal(client, seeded) -> None:
    """Skipping a suggested follow-up is allowed, but terminal."""
    follow_up = _create_follow_up(client)
    skipped = client.patch(
        f"{MISSION_INTEL}/follow-ups/{follow_up['follow_up_id']}",
        json={"action": "skip"},
    )
    assert skipped.status_code == 200
    assert skipped.json()["follow_up"]["status"] == "skipped"

    repeated = client.patch(
        f"{MISSION_INTEL}/follow-ups/{follow_up['follow_up_id']}",
        json={"action": "accept"},
    )
    assert repeated.status_code == 409


def test_follow_up_carries_process_local_warning(client, seeded) -> None:
    """Every follow-up response states that storage is process-local."""
    follow_up = _create_follow_up(client)
    created = client.post(
        f"{MISSION_INTEL}/follow-ups",
        json={
            "recommendation_id": follow_up["recommendation_id"],
            "window_start": _iso(WINDOW_START),
            "window_end": _iso(WINDOW_END),
        },
    )
    assert created.status_code == 201
    assert "follow_up_store_is_process_local" in _warning_codes(created.json())

    patched = client.patch(
        f"{MISSION_INTEL}/follow-ups/{follow_up['follow_up_id']}",
        json={"action": "accept"},
    )
    assert "follow_up_store_is_process_local" in _warning_codes(patched.json())


def test_follow_up_unknown_recommendation(client, seeded) -> None:
    """A recommendation id outside the current evaluation is a 404."""
    response = client.post(
        f"{MISSION_INTEL}/follow-ups",
        json={
            "recommendation_id": "rec_missing",
            "window_start": _iso(WINDOW_START),
            "window_end": _iso(WINDOW_END),
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "recommendation_not_found"


def test_follow_up_unknown_crew(client) -> None:
    """Creating a follow-up for an unknown crew is a 404."""
    response = client.post(
        f"{BASE}/crew-missing/mission-intel/follow-ups",
        json={
            "recommendation_id": "rec_missing",
            "window_start": _iso(WINDOW_START),
            "window_end": _iso(WINDOW_END),
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "crew_not_found"


def test_follow_up_patch_unknown_id(client, seeded) -> None:
    """Patching an unknown follow-up id is a 404."""
    response = client.patch(
        f"{MISSION_INTEL}/follow-ups/fu_missing",
        json={"action": "accept"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "follow_up_not_found"


def test_follow_up_requires_window_pair(client, seeded) -> None:
    """Supplying only one half of the window is rejected by validation."""
    response = client.post(
        f"{MISSION_INTEL}/follow-ups",
        json={
            "recommendation_id": _current_recommendation_id(client),
            "window_start": _iso(WINDOW_START),
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_follow_up_invalid_action(client, seeded) -> None:
    """An unknown action is a request-validation error."""
    follow_up = _create_follow_up(client)
    response = client.patch(
        f"{MISSION_INTEL}/follow-ups/{follow_up['follow_up_id']}",
        json={"action": "reopen"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
