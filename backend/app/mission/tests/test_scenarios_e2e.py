"""End-to-end API tests for the six Phase 8 deterministic scenarios.

Every test seeds one scenario into the isolated in-memory database and then
exercises the real mission-intelligence router through ``TestClient``. The
assertions cover the expected conflict types, the expected recommendation types,
and (for the recovery scenario) the what-if comparison.

The fixtures are synthetic. Where the schema has no ``source`` column, the
payload carries :data:`SYNTHETIC_MARKER`; ``SleepRecord`` rows use
``MeasurementSource.simulated``. One test verifies that provenance so a fixture
can never be mistaken for an AI model result.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.mission.scenario_fixtures import (
    CREW_IDS,
    FIXTURE_ENGINE_VERSION,
    SCENARIO_KEYS,
    SCENARIOS_BY_KEY,
    SYNTHETIC_MARKER,
    reset_scenarios,
    seed_all,
    seed_scenario,
)
from app.models import (
    Assessment,
    CrewProfile,
    MissionTask,
    SleepRecord,
)
from app.models.enums import MeasurementSource

WINDOW_START = "2026-11-13T00:00:00Z"
WINDOW_END = "2026-11-14T00:00:00Z"
WINDOW = {"window_start": WINDOW_START, "window_end": WINDOW_END}

BASE = "/api/v1/crew/{crew_id}/mission-intel"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def seed(session_factory: Callable[[], Session]) -> Callable[[str], None]:
    """Return a helper that seeds one scenario through its own session."""

    def _seed(key: str) -> None:
        with session_factory() as session:
            result = seed_scenario(session, key, reset=True)
        assert result["created"] is True

    return _seed


def _conflicts(client: TestClient, crew_id: str) -> list[dict]:
    response = client.get(
        BASE.format(crew_id=crew_id) + "/conflicts", params=WINDOW
    )
    assert response.status_code == 200, response.text
    return response.json()["conflicts"]


def _conflict_types(client: TestClient, crew_id: str) -> set[str]:
    return {conflict["conflict_type"] for conflict in _conflicts(client, crew_id)}


def _recommendations(client: TestClient, crew_id: str) -> list[dict]:
    response = client.get(
        BASE.format(crew_id=crew_id) + "/recommendations", params=WINDOW
    )
    assert response.status_code == 200, response.text
    return response.json()["recommendations"]


def _recommendation_types(client: TestClient, crew_id: str) -> set[str]:
    return {
        recommendation["recommendation_type"]
        for recommendation in _recommendations(client, crew_id)
    }


# ---------------------------------------------------------------------------
# One test per scenario
# ---------------------------------------------------------------------------


def test_normal_sleep_has_no_findings(client: TestClient, seed) -> None:
    """Scenario 1: adequate sleep and daytime duties produce no advisory."""
    seed("normal_sleep")
    crew_id = SCENARIOS_BY_KEY["normal_sleep"].crew_id

    assert _conflict_types(client, crew_id) == set()
    assert _recommendations(client, crew_id) == []


def test_sleep_deprivation_findings(client: TestClient, seed) -> None:
    """Scenario 2: short sleep yields recovery, circadian, and fatigue findings."""
    seed("sleep_deprivation")
    crew_id = SCENARIOS_BY_KEY["sleep_deprivation"].crew_id

    assert _conflict_types(client, crew_id) == {
        "insufficient_recovery_gap",
        "high_fatigue_critical_task",
        "circadian_low_alertness",
    }
    recommendations = _recommendations(client, crew_id)
    assert {item["recommendation_type"] for item in recommendations} == {
        "identify_recovery_opportunity",
        "review_task_timing",
        "evaluate_lighting_schedule",
    }
    assert all(item["requires_medical_review"] is False for item in recommendations)


def test_high_workload_findings(client: TestClient, seed) -> None:
    """Scenario 3: four demanding blocks overload one workload window."""
    seed("high_workload")
    crew_id = SCENARIOS_BY_KEY["high_workload"].crew_id

    assert _conflict_types(client, crew_id) == {
        "workload_overload",
        "insufficient_recovery_gap",
    }
    assert _recommendation_types(client, crew_id) == {
        "redistribute_demanding_tasks",
        "identify_recovery_opportunity",
    }


def test_sleep_mission_conflict_findings(client: TestClient, seed) -> None:
    """Scenario 4: a night task overlaps the inferred sleep opportunity."""
    seed("sleep_mission_conflict")
    crew_id = SCENARIOS_BY_KEY["sleep_mission_conflict"].crew_id

    assert _conflict_types(client, crew_id) == {
        "sleep_window_conflict",
        "circadian_low_alertness",
    }
    assert _recommendation_types(client, crew_id) == {
        "review_sleep_schedule",
        "evaluate_lighting_schedule",
    }


def test_high_fatigue_before_critical_findings(client: TestClient, seed) -> None:
    """Scenario 5: elevated concern before a critical EVA requires medical review."""
    seed("high_fatigue_before_critical")
    crew_id = SCENARIOS_BY_KEY["high_fatigue_before_critical"].crew_id

    conflicts = _conflicts(client, crew_id)
    assert {conflict["conflict_type"] for conflict in conflicts} == {
        "high_fatigue_critical_task"
    }
    assert conflicts[0]["severity"] == "critical"

    recommendations = _recommendations(client, crew_id)
    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation["recommendation_type"] == "review_task_timing"
    assert recommendation["rule_id"] == "R-FATIGUE-CRITICAL-01"
    assert recommendation["requires_medical_review"] is True
    assert recommendation["requires_mission_approval"] is True


def test_recovery_scheduling_what_if_resolves_conflict(
    client: TestClient, seed
) -> None:
    """Scenario 6: inserting a recovery block resolves the only conflict."""
    seed("recovery_scheduling")
    crew_id = SCENARIOS_BY_KEY["recovery_scheduling"].crew_id

    assert _conflict_types(client, crew_id) == {"insufficient_recovery_gap"}
    assert _recommendation_types(client, crew_id) == {
        "identify_recovery_opportunity"
    }

    payload = {
        "window_start": WINDOW_START,
        "window_end": WINDOW_END,
        "operations": [
            {
                "type": "add_recovery_period",
                "start": "2026-11-13T09:00:00Z",
                "end": "2026-11-13T09:30:00Z",
                "shift_following_tasks": True,
            }
        ],
    }
    response = client.post(
        BASE.format(crew_id=crew_id) + "/what-if", json=payload
    )
    assert response.status_code == 200, response.text
    body = response.json()
    comparison = body["comparison"]

    assert body["applied_operations"] == [
        {
            "index": 0,
            "type": "add_recovery_period",
            "task_id": None,
        }
    ]
    assert comparison["conflict_count_delta"] == -1
    assert {
        conflict["conflict_type"] for conflict in comparison["resolved_conflicts"]
    } == {"insufficient_recovery_gap"}
    assert comparison["new_conflicts"] == []
    assert comparison["note"] == (
        "Fatigue was not re-predicted; this comparison reflects schedule rules only."
    )


# ---------------------------------------------------------------------------
# Seeding behaviour and provenance
# ---------------------------------------------------------------------------


def test_seed_is_idempotent(
    session_factory: Callable[[], Session],
) -> None:
    """Seeding twice must not create duplicate rows."""
    with session_factory() as session:
        first = seed_all(session)
        second = seed_all(session)
        counts = {
            crew_id: len(
                session.exec(
                    select(MissionTask).where(MissionTask.crew_id == crew_id)
                ).all()
            )
            for crew_id in CREW_IDS
        }

    assert [item["created"] for item in first] == [True] * 6
    assert [item["created"] for item in second] == [False] * 6
    assert counts == {
        spec.crew_id: _expected_task_count(spec.key)
        for spec in SCENARIOS_BY_KEY.values()
    }


def _expected_task_count(key: str) -> int:
    """Return the deterministic number of tasks for one scenario."""
    return {
        "normal_sleep": 3,
        "sleep_deprivation": 2,
        "high_workload": 4,
        "sleep_mission_conflict": 2,
        "high_fatigue_before_critical": 2,
        "recovery_scheduling": 3,
    }[key]


def test_reset_deletes_only_scenario_crews(
    session_factory: Callable[[], Session],
) -> None:
    """``reset_scenarios`` must leave demo crews and their rows untouched."""
    with session_factory() as session:
        session.add(
            CrewProfile(
                id="crew-demo-99",
                display_name="Unrelated Demo Crew",
                role="Demo",
                sleep_target_hours=8.0,
            )
        )
        session.commit()
        seed_all(session)
        removed = reset_scenarios(session)
        remaining_crews = {
            crew.id for crew in session.exec(select(CrewProfile)).all()
        }
        remaining_tasks = {
            task.crew_id for task in session.exec(select(MissionTask)).all()
        }

    assert set(removed) == set(CREW_IDS)
    assert remaining_crews == {"crew-demo-99"}
    assert remaining_tasks == set()


def test_fixtures_are_marked_synthetic(
    session_factory: Callable[[], Session],
) -> None:
    """Fixtures must never look like real records or AI model output."""
    with session_factory() as session:
        seed_all(session)
        sleep_rows = session.exec(select(SleepRecord)).all()
        assessments = session.exec(select(Assessment)).all()
        tasks = session.exec(select(MissionTask)).all()

    assert sleep_rows
    assert {row.source for row in sleep_rows} == {MeasurementSource.simulated}
    assert assessments
    for assessment in assessments:
        assert SYNTHETIC_MARKER in assessment.summary
        assert SYNTHETIC_MARKER in assessment.explanation
        assert assessment.engine_version == FIXTURE_ENGINE_VERSION
        factor = assessment.contributing_factors[0]
        assert factor["source"] == "simulated"
        assert factor["synthetic_test_data"] is True
        assert factor["model_output"] is False
    assert tasks
    for task in tasks:
        assert task.notes is not None
        assert SYNTHETIC_MARKER in task.notes


def test_unknown_scenario_key_is_rejected(
    session_factory: Callable[[], Session],
) -> None:
    """An unknown scenario key raises ``KeyError`` instead of seeding silently."""
    with session_factory() as session, pytest.raises(KeyError):
        seed_scenario(session, "not_a_scenario")
    assert set(SCENARIO_KEYS) == {
        "normal_sleep",
        "sleep_deprivation",
        "high_workload",
        "sleep_mission_conflict",
        "high_fatigue_before_critical",
        "recovery_scheduling",
    }
