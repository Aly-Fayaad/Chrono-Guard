"""Check-in validation, atomicity, and analysis hook tests."""

from datetime import datetime, timedelta, timezone

from app.models.assessment import Assessment
from app.models.enums import AssessmentStatus


def _full_payload(start: datetime) -> dict:
    end = start + timedelta(hours=7.5)
    return {
        "recorded_at": start.isoformat(),
        "sleep": {
            "sleep_start": (start - timedelta(hours=8)).isoformat(),
            "sleep_end": (start - timedelta(hours=0.5)).isoformat(),
            "interruptions": 1,
        },
        "behavioral": {"mood": 3, "sleepiness_kss": 6, "perceived_stress": 2},
        "cardiovascular": {"heart_rate": 72, "systolic_bp": 118, "diastolic_bp": 76},
        "physical": {"body_temperature": 36.7},
    }


def _post_checkin(client, crew_id: str, payload: dict):
    return client.post(f"/api/v1/crew/{crew_id}/checkins", json=payload)


def test_checkin_saves_measurements_and_sleep(client, crew_id: str) -> None:
    """A valid check-in persists measurements, sleep, and computed duration."""
    response = _post_checkin(client, crew_id, _full_payload(datetime.now(timezone.utc)))
    assert response.status_code == 201
    body = response.json()
    assert len(body["measurements"]) == 7
    assert {row["unit"] for row in body["measurements"]} == {"score", "bpm", "mmHg", "C"}
    assert all(row["source"] == "manual" for row in body["measurements"])
    assert body["sleep_record"]["duration_hours"] == 7.5
    assert body["sleep_record"]["quality"] == "valid"
    assert body["assessment"] is None

    listed = client.get(f"/api/v1/crew/{crew_id}/checkins").json()
    assert len(listed) == 1
    detail = client.get(f"/api/v1/crew/{crew_id}/checkins/{body['checkin']['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["measurements"]) == 7


def test_hard_violation_rejects_and_saves_nothing(client, crew_id: str) -> None:
    """A hard-bound violation returns 422 and rolls back the whole check-in."""
    payload = _full_payload(datetime.now(timezone.utc))
    payload["cardiovascular"]["heart_rate"] = 300
    response = _post_checkin(client, crew_id, payload)
    assert response.status_code == 422
    assert client.get(f"/api/v1/crew/{crew_id}/checkins").json() == []
    assert client.get(f"/api/v1/crew/{crew_id}/history/measurements").json()["measurements"] == []
    assert client.get(f"/api/v1/crew/{crew_id}/history/sleep").json()["sleep_records"] == []


def test_soft_violation_is_saved_as_questionable(client, crew_id: str) -> None:
    """Soft-bound violations are stored with quality='questionable'."""
    payload = _full_payload(datetime.now(timezone.utc))
    payload["cardiovascular"]["heart_rate"] = 130
    payload["physical"]["body_temperature"] = 38.2
    response = _post_checkin(client, crew_id, payload)
    assert response.status_code == 201
    quality = {
        row["type"]: row["quality"] for row in response.json()["measurements"]
    }
    assert quality["heart_rate"] == "questionable"
    assert quality["body_temperature"] == "questionable"
    assert quality["mood"] == "valid"


def test_systolic_must_exceed_diastolic(client, crew_id: str) -> None:
    """Cross-field blood pressure validation rejects invalid pairs."""
    payload = {"cardiovascular": {"systolic_bp": 110, "diastolic_bp": 110}}
    assert _post_checkin(client, crew_id, payload).status_code == 422
    assert client.get(f"/api/v1/crew/{crew_id}/checkins").json() == []


def test_empty_checkin_is_rejected(client, crew_id: str) -> None:
    """At least one health or sleep value is required."""
    assert _post_checkin(client, crew_id, {"notes": "nothing to report"}).status_code == 422


def test_unknown_crew_returns_404(client) -> None:
    """Check-in routes reject unknown crew ids."""
    assert _post_checkin(client, "missing", {"cardiovascular": {"heart_rate": 70}}).status_code == 404
    assert client.get("/api/v1/crew/missing/checkins").status_code == 404


class _BoomEngine:
    """Engine that always fails."""

    def analyze(self, session, crew_id: str, checkin_id: str | None):
        raise RuntimeError("engine boom")


class _FakeEngine:
    """Engine that returns a deterministic assessment."""

    def analyze(self, session, crew_id: str, checkin_id: str | None) -> Assessment:
        return Assessment(
            crew_id=crew_id,
            checkin_id=checkin_id,
            status=AssessmentStatus.monitor,
            summary="Elevated sleepiness",
            explanation="KSS is above the crew baseline.",
            contributing_factors=[
                {
                    "indicator": "sleepiness_kss",
                    "observed": 6,
                    "reference": "1-9",
                    "note": "self reported",
                }
            ],
            engine_version="fake-1.0",
        )


def test_engine_exception_does_not_lose_checkin(client, crew_id: str) -> None:
    """An analysis failure leaves the committed check-in intact."""
    client.app.state.analysis_engine = _BoomEngine()
    response = _post_checkin(client, crew_id, {"cardiovascular": {"heart_rate": 70}})
    assert response.status_code == 201
    assert response.json()["assessment"] is None
    assert len(client.get(f"/api/v1/crew/{crew_id}/checkins").json()) == 1


def test_fake_engine_assessment_is_persisted(client, crew_id: str) -> None:
    """A returned assessment is persisted and exposed through read routes."""
    client.app.state.analysis_engine = _FakeEngine()
    response = _post_checkin(client, crew_id, {"behavioral": {"sleepiness_kss": 6}})
    assert response.status_code == 201
    assessment = response.json()["assessment"]
    assert assessment["status"] == "monitor"
    assert assessment["engine_version"] == "fake-1.0"

    latest = client.get(f"/api/v1/crew/{crew_id}/assessments/latest")
    assert latest.status_code == 200
    assert latest.json()["id"] == assessment["id"]
    listed = client.get(f"/api/v1/crew/{crew_id}/assessments").json()
    assert len(listed) == 1
