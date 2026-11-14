"""Tier-1 API additions: crew lifecycle, analysis, dashboard, and contracts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import select

from app.models.assessment import Assessment
from app.models.checkin import CheckIn, HealthMeasurement, SleepRecord
from app.models.crew import CrewProfile
from app.models.mission import MissionTask
from app.services.analysis import NullEngine


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _payload(
    *,
    recorded_at: datetime | None = None,
    heart_rate: float | None = 70,
    sleep_hours: float | None = 7.0,
    mood: int = 3,
) -> dict:
    at = recorded_at or _now()
    payload: dict = {
        "recorded_at": at.isoformat(),
        "behavioral": {"mood": mood, "sleepiness_kss": 4},
    }
    if heart_rate is not None:
        payload["cardiovascular"] = {"heart_rate": heart_rate, "hrv": 60}
    if sleep_hours is not None:
        payload["sleep"] = {
            "sleep_start": (at - timedelta(hours=sleep_hours)).isoformat(),
            "sleep_end": at.isoformat(),
            "interruptions": 0,
        }
    return payload


def _new_crew(client, slug: str) -> dict:
    response = client.post(
        "/api/v1/crew",
        json={"id": slug, "display_name": slug, "role": "tester"},
    )
    assert response.status_code == 201
    return response.json()


def test_crew_create_duplicate_and_cascade_delete(
    client, session_factory
) -> None:
    """POST /crew works with a slug and DELETE removes every child row."""
    crew = _new_crew(client, "crew-tier1")
    assert crew["id"] == "crew-tier1"
    assert crew["sleep_target_hours"] == 7.5

    duplicate = client.post(
        "/api/v1/crew",
        json={"id": "crew-tier1", "display_name": "Other", "role": "tester"},
    )
    assert duplicate.status_code == 409

    checkin = client.post(
        "/api/v1/crew/crew-tier1/checkins", json=_payload()
    )
    assert checkin.status_code == 201

    mission = client.post(
        "/api/v1/crew/crew-tier1/missions",
        json={
            "title": "Tier-1 task",
            "task_type": "eva",
            "start_time": (_now() + timedelta(hours=2)).isoformat(),
            "end_time": (_now() + timedelta(hours=3)).isoformat(),
            "workload_level": "high",
            "is_critical": True,
        },
    )
    assert mission.status_code == 201

    # Force an assessment so the cascade covers the assessment table too.
    analysis = client.post("/api/v1/crew/crew-tier1/analysis/run")
    assert analysis.status_code == 200
    assert analysis.json()["assessment"] is not None

    deleted = client.delete("/api/v1/crew/crew-tier1")
    assert deleted.status_code == 200
    body = deleted.json()
    assert body["deleted"] is True
    assert body["deleted_rows"]["checkin"] == 1
    assert body["deleted_rows"]["healthmeasurement"] >= 1
    assert body["deleted_rows"]["sleeprecord"] == 1
    assert body["deleted_rows"]["missiontask"] == 1
    assert body["deleted_rows"]["assessment"] >= 1

    assert client.get("/api/v1/crew/crew-tier1").status_code == 404
    with session_factory() as session:
        assert session.exec(
            select(CrewProfile).where(CrewProfile.id == "crew-tier1")
        ).first() is None
        for model in (
            CheckIn,
            HealthMeasurement,
            SleepRecord,
            MissionTask,
            Assessment,
        ):
            assert session.exec(
                select(model).where(model.crew_id == "crew-tier1")
            ).first() is None


def test_crew_without_slug_gets_server_id(client) -> None:
    """Omitting id generates a server-side identifier."""
    response = client.post(
        "/api/v1/crew",
        json={"display_name": "Generated", "role": "specialist"},
    )
    assert response.status_code == 201
    assert response.json()["id"]


def test_crew_accepts_slug_alias(client) -> None:
    """Callers may name the optional stable identifier ``slug``."""
    response = client.post(
        "/api/v1/crew",
        json={
            "slug": "crew-slug-alias",
            "display_name": "Slug Alias",
            "role": "specialist",
        },
    )
    assert response.status_code == 201
    assert response.json()["id"] == "crew-slug-alias"


def test_assessment_detail_is_crew_scoped(client) -> None:
    """Assessment detail is 404 when missing or owned by another crew."""
    _new_crew(client, "crew-a")
    _new_crew(client, "crew-b")
    posted = client.post("/api/v1/crew/crew-a/checkins", json=_payload())
    assert posted.status_code == 201
    assessment_id = posted.json()["assessment"]["id"]

    own = client.get(f"/api/v1/crew/crew-a/assessments/{assessment_id}")
    assert own.status_code == 200
    assert own.json()["id"] == assessment_id

    other = client.get(f"/api/v1/crew/crew-b/assessments/{assessment_id}")
    assert other.status_code == 404

    missing = client.get("/api/v1/crew/crew-a/assessments/not-there")
    assert missing.status_code == 404


def test_analysis_run_uses_latest_or_explicit_checkin(client) -> None:
    """The analysis route targets an explicit check-in or the newest one."""
    _new_crew(client, "crew-analysis")
    first = client.post(
        "/api/v1/crew/crew-analysis/checkins", json=_payload()
    ).json()
    second = client.post(
        "/api/v1/crew/crew-analysis/checkins", json=_payload()
    ).json()

    explicit = client.post(
        "/api/v1/crew/crew-analysis/analysis/run",
        params={"checkin_id": first["checkin"]["id"]},
    )
    assert explicit.status_code == 200
    assert explicit.json()["assessment"]["checkin_id"] == first["checkin"]["id"]

    latest = client.post("/api/v1/crew/crew-analysis/analysis/run")
    assert latest.status_code == 200
    assert latest.json()["assessment"]["checkin_id"] == second["checkin"]["id"]

    other = client.post(
        "/api/v1/crew/crew-analysis/analysis/run",
        params={"checkin_id": "missing-checkin"},
    )
    assert other.status_code == 404


def test_analysis_run_null_engine_and_unconfigured(client) -> None:
    """NullEngine returns null; a missing engine is a 503."""
    _new_crew(client, "crew-null")
    posted = client.post("/api/v1/crew/crew-null/checkins", json=_payload())
    assert posted.status_code == 201

    client.app.state.analysis_engine = NullEngine()
    null_result = client.post("/api/v1/crew/crew-null/analysis/run")
    assert null_result.status_code == 200
    assert null_result.json() == {"assessment": None}

    client.app.state.analysis_engine = None
    missing = client.post("/api/v1/crew/crew-null/analysis/run")
    assert missing.status_code == 503


def test_dashboard_summary_counts_and_freshness(client) -> None:
    """Dashboard reports latest, seven-day counts, valid-only mean, and sleep."""
    _new_crew(client, "crew-dashboard")
    old = _now() - timedelta(days=1)
    latest = _now()
    client.post(
        "/api/v1/crew/crew-dashboard/checkins",
        json=_payload(recorded_at=old, heart_rate=70, sleep_hours=7.0),
    )
    client.post(
        "/api/v1/crew/crew-dashboard/checkins",
        json=_payload(recorded_at=latest, heart_rate=130, sleep_hours=2.0),
    )

    response = client.get("/api/v1/crew/crew-dashboard/dashboard/summary")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "crew_id",
        "generated_at",
        "window_days",
        "measurements",
        "sleep",
        "data_freshness_hours",
    }
    assert body["window_days"] == 7

    by_type = {row["type"]: row for row in body["measurements"]}
    heart = by_type["heart_rate"]
    assert heart["latest_value"] == 130
    assert heart["latest_quality"] == "questionable"
    assert heart["valid_count_7d"] == 1
    assert heart["questionable_count_7d"] == 1
    assert heart["mean_7d"] == 70
    assert heart["unit"] == "bpm"

    sleep = body["sleep"]
    assert sleep["last_duration_hours"] == 2
    assert sleep["mean_duration_7d"] == 7
    assert sleep["valid_nights_7d"] == 1
    assert sleep["last_quality"] == "questionable"
    assert sleep["last_sleep_end"].startswith(latest.date().isoformat())
    assert 0 <= body["data_freshness_hours"] < 1

    # Descriptive only: no baselines, thresholds, alerts, or scores.
    assert not any(
        key in body for key in ("baseline", "threshold", "alert", "score")
    )


def test_unified_validation_error_shape(client) -> None:
    """Every 422 uses the Pydantic loc/msg/type list, including domain errors."""
    missing = client.post("/api/v1/crew", json={"role": "tester"})
    assert missing.status_code == 422
    assert set(missing.json()["detail"][0]) == {"loc", "msg", "type"}

    _new_crew(client, "crew-422")
    domain = client.post(
        "/api/v1/crew/crew-422/checkins",
        json={
            "sleep": {
                "sleep_start": _now().isoformat(),
                "sleep_end": (_now() - timedelta(hours=1)).isoformat(),
            }
        },
    )
    assert domain.status_code == 422
    detail = domain.json()["detail"]
    assert set(detail[0]) == {"loc", "msg", "type"}
    assert detail[0]["type"] == "value_error"

    simulated = client.post(
        "/api/v1/crew/crew-422/checkins",
        json={"source": "simulated", "behavioral": {"mood": 3}},
    )
    assert simulated.status_code == 422
    assert simulated.json()["detail"][0]["loc"] == ["body", "source"]

    bad_query = client.get(
        "/api/v1/crew/crew-422/missions", params={"horizon_hours": 0}
    )
    assert bad_query.status_code == 422
    assert set(bad_query.json()["detail"][0]) == {"loc", "msg", "type"}


def test_list_routes_expose_total_count_header(client) -> None:
    """List routes keep array/envelope bodies and add X-Total-Count."""
    _new_crew(client, "crew-count")
    client.app.state.analysis_engine = NullEngine()
    for _ in range(2):
        assert (
            client.post(
                "/api/v1/crew/crew-count/checkins", json=_payload()
            ).status_code
            == 201
        )
    for index in range(2):
        assert (
            client.post(
                "/api/v1/crew/crew-count/missions",
                json={
                    "title": f"Task {index}",
                    "start_time": (_now() + timedelta(hours=index + 1)).isoformat(),
                    "end_time": (_now() + timedelta(hours=index + 2)).isoformat(),
                },
            ).status_code
            == 201
        )

    checkins = client.get("/api/v1/crew/crew-count/checkins", params={"limit": 1})
    assert checkins.status_code == 200
    assert len(checkins.json()) == 1
    assert checkins.headers["X-Total-Count"] == "2"

    history = client.get(
        "/api/v1/crew/crew-count/history/measurements", params={"limit": 1}
    )
    assert history.status_code == 200
    assert history.headers["X-Total-Count"] == "8"

    sleep = client.get(
        "/api/v1/crew/crew-count/history/sleep", params={"limit": 1}
    )
    assert sleep.status_code == 200
    assert sleep.headers["X-Total-Count"] == "2"

    missions = client.get("/api/v1/crew/crew-count/missions", params={"limit": 1})
    assert missions.status_code == 200
    assert missions.headers["X-Total-Count"] == "2"

    assessments = client.get("/api/v1/crew/crew-count/assessments")
    assert assessments.status_code == 200
    assert assessments.headers["X-Total-Count"] == "0"

    crew = client.get("/api/v1/crew")
    assert crew.status_code == 200
    assert int(crew.headers["X-Total-Count"]) >= 1


def test_history_accepts_repeated_type_filters(client) -> None:
    """Repeated ?type= filters combine; a single value still works."""
    _new_crew(client, "crew-history")
    client.post(
        "/api/v1/crew/crew-history/checkins",
        json={
            "recorded_at": _now().isoformat(),
            "behavioral": {"mood": 4},
            "cardiovascular": {"heart_rate": 72},
        },
    )

    repeated = client.get(
        "/api/v1/crew/crew-history/history/measurements",
        params=[("type", "heart_rate"), ("type", "mood")],
    )
    assert repeated.status_code == 200
    assert {row["type"] for row in repeated.json()["measurements"]} == {
        "heart_rate",
        "mood",
    }

    single = client.get(
        "/api/v1/crew/crew-history/history/measurements",
        params={"type": "heart_rate"},
    )
    assert single.status_code == 200
    assert [row["type"] for row in single.json()["measurements"]] == ["heart_rate"]

    invalid = client.get(
        "/api/v1/crew/crew-history/history/measurements",
        params={"type": "not-a-type"},
    )
    assert invalid.status_code == 422
    assert set(invalid.json()["detail"][0]) == {"loc", "msg", "type"}


def test_mission_filters_and_upcoming_horizon(client) -> None:
    """Attribute filters and the optional upcoming horizon are composable."""
    _new_crew(client, "crew-missions")
    now = _now()
    specs = [
        ("past", "maintenance", "low", False, -2),
        ("soon-eva", "eva", "high", True, 1),
        ("later-eva", "eva", "high", True, 50),
        ("science", "science", "medium", False, 100),
    ]
    for title, task_type, workload, critical, hours in specs:
        response = client.post(
            "/api/v1/crew/crew-missions/missions",
            json={
                "title": title,
                "task_type": task_type,
                "start_time": (now + timedelta(hours=hours)).isoformat(),
                "end_time": (now + timedelta(hours=hours + 1)).isoformat(),
                "workload_level": workload,
                "is_critical": critical,
            },
        )
        assert response.status_code == 201

    all_rows = client.get("/api/v1/crew/crew-missions/missions")
    assert all_rows.status_code == 200
    assert len(all_rows.json()) == 4

    upcoming = client.get(
        "/api/v1/crew/crew-missions/missions", params={"upcoming": "true"}
    )
    assert {row["title"] for row in upcoming.json()} == {
        "soon-eva",
        "later-eva",
        "science",
    }

    horizon = client.get(
        "/api/v1/crew/crew-missions/missions",
        params={"upcoming": "true", "horizon_hours": 48},
    )
    assert [row["title"] for row in horizon.json()] == ["soon-eva"]

    filtered = client.get(
        "/api/v1/crew/crew-missions/missions",
        params={
            "task_type": "eva",
            "workload_level": "high",
            "is_critical": "true",
        },
    )
    assert filtered.status_code == 200
    assert {row["title"] for row in filtered.json()} == {"soon-eva", "later-eva"}
    assert filtered.headers["X-Total-Count"] == "2"


def test_overview_uses_canonical_quality_and_source_names(client) -> None:
    """The overview series exposes the same enums as the rest of the API."""
    _new_crew(client, "crew-overview-enums")
    posted = client.post(
        "/api/v1/crew/crew-overview-enums/checkins",
        json={
            **_payload(heart_rate=130),
            "source": "device_import",
        },
    )
    assert posted.status_code == 201

    overview = client.get("/api/v1/crew/crew-overview-enums/overview")
    assert overview.status_code == 200
    latest = overview.json()["series"]["heart_rate"][-1]
    assert latest["quality"] == "questionable"
    assert latest["source"] == "device_import"


def test_checkin_source_contract(client) -> None:
    """API submissions accept manual/device_import and reject simulated."""
    _new_crew(client, "crew-source")

    device = client.post(
        "/api/v1/crew/crew-source/checkins",
        json={**_payload(), "source": "device_import"},
    )
    assert device.status_code == 201
    assert {row["source"] for row in device.json()["measurements"]} == {
        "device_import"
    }
    assert device.json()["sleep_record"]["source"] == "device_import"

    manual = client.post(
        "/api/v1/crew/crew-source/checkins", json=_payload()
    )
    assert manual.status_code == 201
    assert {row["source"] for row in manual.json()["measurements"]} == {"manual"}

    rejected = client.post(
        "/api/v1/crew/crew-source/checkins",
        json={**_payload(), "source": "simulated"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"][0]["loc"] == ["body", "source"]
