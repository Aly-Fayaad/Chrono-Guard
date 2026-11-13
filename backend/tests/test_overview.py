"""Unified overview endpoint: mission clock, series, detections, assessment."""

from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.ml.crew_health_engine import _recent_persistent
from crew_health.pipeline import analyze as analyze_payload

METRICS = {"heart_rate", "hrv", "temperature", "sleep_hours"}


def _night_checkin(day: datetime, *, kss: int = 6) -> dict:
    """A check-in with one 7.5 h sleep window ending at 07:00 UTC."""
    sleep_end = day.replace(hour=7, minute=0, second=0, microsecond=0)
    sleep_start = sleep_end - timedelta(hours=7.5)
    return {
        "recorded_at": day.isoformat(),
        "sleep": {
            "sleep_start": sleep_start.isoformat(),
            "sleep_end": sleep_end.isoformat(),
            "interruptions": 0,
        },
        "behavioral": {"sleepiness_kss": kss, "mood": 3},
        "cardiovascular": {"heart_rate": 70, "hrv": 60},
        "physical": {"body_temperature": 36.6},
    }


def test_overview_unknown_crew_is_404(client) -> None:
    """Unknown crew members cannot read an overview."""
    assert client.get("/api/v1/crew/missing/overview").status_code == 404


def test_overview_empty_crew_has_all_metric_keys(client, crew_id: str) -> None:
    """An empty crew still gets a complete, well-formed envelope."""
    response = client.get(f"/api/v1/crew/{crew_id}/overview")
    assert response.status_code == 200
    body = response.json()

    assert body["crew_id"] == crew_id
    assert set(body["series"]) == METRICS
    assert all(body["series"][metric] == [] for metric in METRICS)
    assert {row["metric"] for row in body["detections"]} == METRICS
    assert all(row["status"] == "insufficient_baseline" for row in body["detections"])
    assert body["assessment"] is None
    assert body["last_check_in"] is None
    assert body["wake"] is None
    assert body["mission"]["met_label"].startswith("D+")


def test_overview_mission_clock_is_server_configured(
    client, crew_id: str, monkeypatch
) -> None:
    """Day length comes from backend settings, not a frontend constant."""
    settings = get_settings()
    epoch = datetime.now(timezone.utc) - timedelta(hours=30)
    monkeypatch.setattr(settings, "MISSION_EPOCH", epoch.isoformat())
    monkeypatch.setattr(settings, "MISSION_DAY_HOURS", 24.65)

    mission = client.get(f"/api/v1/crew/{crew_id}/overview").json()["mission"]
    assert mission["mission_day_hours"] == 24.65
    assert mission["mission_day_index"] == 1
    assert mission["met_label"].startswith("D+001")
    assert 0 <= mission["mission_local_time_hours"] < 24.65


def test_default_mission_day_is_the_martian_sol(client, crew_id: str) -> None:
    """The operational default is 24.65 h, not an Earth 24 h day."""
    assert get_settings().MISSION_DAY_HOURS == 24.65
    mission = client.get(f"/api/v1/crew/{crew_id}/overview").json()["mission"]
    assert mission["mission_day_hours"] == 24.65


def test_mission_clock_does_not_roll_over_at_24_hours(
    client, crew_id: str, monkeypatch
) -> None:
    """24.4 h of MET is still D+000 on a 24.65 h operational day."""
    settings = get_settings()
    epoch = datetime.now(timezone.utc) - timedelta(hours=24.4)
    monkeypatch.setattr(settings, "MISSION_EPOCH", epoch.isoformat())
    monkeypatch.setattr(settings, "MISSION_DAY_HOURS", 24.65)

    mission = client.get(f"/api/v1/crew/{crew_id}/overview").json()["mission"]
    assert mission["mission_day_index"] == 0
    assert 24.0 < mission["mission_local_time_hours"] < 24.65
    assert mission["met_label"].startswith("D+000")


def test_mission_day_length_keeps_published_circadian_equations() -> None:
    """The 24.65 h mission clock must not stretch the 24 h TPM equations."""
    as_of = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
    result = analyze_payload(
        {
            "subject_id": "crew-test",
            "as_of": as_of.isoformat(),
            "timezone": "UTC",
            "nightly_records": [
                {
                    "date": "2026-11-02",
                    "sleep_start": "2026-11-01T23:00:00Z",
                    "sleep_end": "2026-11-02T07:00:00Z",
                    "awakenings": 0,
                    "sleep_duration_hours": 8.0,
                },
                {
                    "date": "2026-11-03",
                    "sleep_start": "2026-11-02T23:00:00Z",
                    "sleep_end": "2026-11-03T07:00:00Z",
                    "awakenings": 0,
                    "sleep_duration_hours": 8.0,
                },
            ],
            "upcoming_tasks": [],
            "mission": {
                "mission_day_hours": 24.65,
                "epoch": "2026-10-30T07:00:00Z",
                "records_on_mission_clock": False,
            },
        }
    )

    mission = result["mission_time"]
    assert mission["mission_day_hours"] == 24.65
    assert mission["circadian_period_hours"] == 24.0
    assert mission["ultradian_period_hours"] == 12.0
    assert mission["published_circadian_equations_unchanged"] is True


def test_stale_persistent_runs_are_not_reported() -> None:
    """Only a run reaching the latest completed night is currently relevant."""
    stale = {"feature": "tst_min", "end_index": 0}
    recent = {"feature": "tst_min", "end_index": 2}
    assert _recent_persistent([stale, recent], history_nights=3) == [recent]
    assert _recent_persistent([stale], history_nights=3) == []


def test_hrv_is_accepted_and_returned(client, crew_id: str) -> None:
    """HRV is a first-class measurement with a server-owned unit."""
    response = client.post(
        f"/api/v1/crew/{crew_id}/checkins",
        json={"cardiovascular": {"hrv": 61}},
    )
    assert response.status_code == 201
    hrv = [row for row in response.json()["measurements"] if row["type"] == "hrv"]
    assert hrv and hrv[0]["unit"] == "ms" and hrv[0]["value"] == 61.0

    series = client.get(f"/api/v1/crew/{crew_id}/overview").json()["series"]["hrv"]
    assert [row["value"] for row in series] == [61.0]


def test_kss_outside_instrument_range_is_rejected(client, crew_id: str) -> None:
    """The self-report uses the 1-9 KSS range, not the old 1-5 scale."""
    response = client.post(
        f"/api/v1/crew/{crew_id}/checkins",
        json={"behavioral": {"sleepiness_kss": 10}},
    )
    assert response.status_code == 422


def test_two_nights_produce_a_backend_assessment(client, crew_id: str) -> None:
    """Check-ins run CrewHealthEngine and the overview exposes its output."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    first = client.post(
        f"/api/v1/crew/{crew_id}/checkins", json=_night_checkin(now - timedelta(days=1))
    )
    assert first.status_code == 201

    second = client.post(f"/api/v1/crew/{crew_id}/checkins", json=_night_checkin(now))
    assert second.status_code == 201
    created = second.json()["assessment"]
    assert created is not None
    assert created["status"] in {"no_flag", "monitor", "elevated_concern"}
    assert created["engine_version"].startswith("crew-health")

    overview = client.get(f"/api/v1/crew/{crew_id}/overview").json()
    assert overview["assessment"]["id"] == created["id"]
    assert overview["assessment"]["status"] == created["status"]
    assert overview["assessment"]["contributing_factors"]
    status_rule = next(
        factor
        for factor in overview["assessment"]["contributing_factors"]
        if factor["indicator"] == "status_rule"
    )
    assert "provisional" in status_rule["note"]
    assert "not a validated impairment indicator" in status_rule["note"]
    assert len(overview["series"]["heart_rate"]) == 2
    assert len(overview["series"]["sleep_hours"]) == 2
    assert len(overview["detections"]) == 4
    assert overview["wake"] is not None
    assert overview["last_check_in"] is not None


def test_demo_seed_generates_an_assessment(client) -> None:
    """Loading demo data also runs the analysis engine."""
    seeded = client.post("/api/v1/demo/seed?scenario=normal_routine")
    assert seeded.status_code == 200
    assert seeded.json()["created"] is True

    overview = client.get("/api/v1/crew/crew-demo-01/overview").json()
    assert overview["assessment"] is not None
    assert overview["analysis_engine"].endswith("CrewHealthEngine")
    assert len(overview["series"]["sleep_hours"]) == 7
    assert len(overview["series"]["hrv"]) == 7
    assert overview["tasks"]
