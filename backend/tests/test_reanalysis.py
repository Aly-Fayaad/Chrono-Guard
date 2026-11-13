"""Historical re-analysis: additive, idempotent, failure-isolated."""

from datetime import datetime, timedelta, timezone

from app.ml.crew_health_engine import CrewHealthEngine
from app.models.assessment import Assessment
from app.models.enums import AssessmentStatus


def _night_payload(end: datetime) -> dict:
    """Check-in payload with one 7.5 h sleep window ending at ``end``."""
    start = end - timedelta(hours=7.5)
    return {
        "recorded_at": end.isoformat(),
        "sleep": {
            "sleep_start": start.isoformat(),
            "sleep_end": end.isoformat(),
            "interruptions": 0,
        },
        "behavioral": {"sleepiness_kss": 5, "mood": 3},
        "cardiovascular": {"heart_rate": 68, "hrv": 58},
        "physical": {"body_temperature": 36.6},
    }


def _post_nights(client, crew_id: str, count: int = 2) -> list[str]:
    """Post ``count`` nightly check-ins with the engine disabled."""
    client.app.state.analysis_engine = None
    now = datetime.now(timezone.utc).replace(microsecond=0)
    ids = []
    for index in range(count - 1, -1, -1):
        end = now - timedelta(hours=2 + 24 * index)
        response = client.post(
            f"/api/v1/crew/{crew_id}/checkins",
            json=_night_payload(end),
        )
        assert response.status_code == 201
        ids.append(response.json()["checkin"]["id"])
    return ids


def test_reanalysis_is_additive_and_idempotent(client, crew_id: str) -> None:
    """First run creates assessments; a retry skips them without duplicates."""
    checkin_ids = _post_nights(client, crew_id, count=2)
    before = client.get(f"/api/v1/crew/{crew_id}/checkins").json()

    client.app.state.analysis_engine = CrewHealthEngine()
    first = client.post(f"/api/v1/crew/{crew_id}/assessments/reanalyze")
    assert first.status_code == 200
    body = first.json()
    assert body["engine_version"].startswith("crew-health")
    assert body["processed"] == 2
    assert body["succeeded"] == 2
    assert body["skipped"] == 0
    assert body["failed"] == 0
    # The first historical check-in had only one prior night available.
    assert body["insufficient"] == 1

    assessments = client.get(f"/api/v1/crew/{crew_id}/assessments").json()
    assert len(assessments) == 2
    assert {row["checkin_id"] for row in assessments} == set(checkin_ids)

    after = client.get(f"/api/v1/crew/{crew_id}/checkins").json()
    assert [row["id"] for row in after] == [row["id"] for row in before]

    retry = client.post(f"/api/v1/crew/{crew_id}/assessments/reanalyze")
    assert retry.status_code == 200
    body = retry.json()
    assert body["processed"] == 2
    assert body["succeeded"] == 0
    assert body["skipped"] == 2
    assert body["failed"] == 0
    assert len(
        client.get(f"/api/v1/crew/{crew_id}/assessments").json()
    ) == 2


def test_reanalysis_preserves_old_assessments(
    client, crew_id: str, session_factory
) -> None:
    """A previous engine version's assessment remains in history."""
    checkin_ids = _post_nights(client, crew_id, count=2)
    with session_factory() as session:
        old = Assessment(
            crew_id=crew_id,
            checkin_id=checkin_ids[0],
            status=AssessmentStatus.monitor,
            summary="Old engine result",
            explanation="Kept for history.",
            contributing_factors=[],
            engine_version="old-engine",
        )
        session.add(old)
        session.commit()
        old_id = old.id

    client.app.state.analysis_engine = CrewHealthEngine()
    response = client.post(f"/api/v1/crew/{crew_id}/assessments/reanalyze")
    assert response.status_code == 200
    assert response.json()["succeeded"] == 2

    assessments = client.get(f"/api/v1/crew/{crew_id}/assessments").json()
    assert old_id in {row["id"] for row in assessments}
    assert len([row for row in assessments if row["checkin_id"] == checkin_ids[0]]) == 2


class _FlakyEngine:
    """Return assessments except for one chosen check-in."""

    version = "flaky-engine-1.0"

    def __init__(self, fail_checkin_id: str) -> None:
        self.fail_checkin_id = fail_checkin_id

    def analyze(self, session, crew_id: str, checkin_id: str | None):
        if checkin_id == self.fail_checkin_id:
            raise RuntimeError("simulated analysis failure")
        return Assessment(
            crew_id=crew_id,
            checkin_id=checkin_id,
            status=AssessmentStatus.no_flag,
            summary="Re-analysed",
            explanation="Test assessment.",
            contributing_factors=[],
            engine_version=self.version,
        )


def test_one_failure_does_not_stop_the_batch(client, crew_id: str) -> None:
    """Failed check-ins are reported and do not block later records."""
    checkin_ids = _post_nights(client, crew_id, count=3)
    client.app.state.analysis_engine = _FlakyEngine(fail_checkin_id=checkin_ids[1])

    response = client.post(f"/api/v1/crew/{crew_id}/assessments/reanalyze")
    assert response.status_code == 200
    body = response.json()
    assert body["processed"] == 3
    assert body["succeeded"] == 2
    assert body["failed"] == 1
    assert body["skipped"] == 0
    failed = [item for item in body["results"] if item["status"] == "failed"]
    assert failed and failed[0]["checkin_id"] == checkin_ids[1]
    assert "simulated analysis failure" in failed[0]["reason"]
    assert len(
        client.get(f"/api/v1/crew/{crew_id}/assessments").json()
    ) == 2
    assert len(client.get(f"/api/v1/crew/{crew_id}/checkins").json()) == 3

    retry = client.post(f"/api/v1/crew/{crew_id}/assessments/reanalyze")
    assert retry.status_code == 200
    body = retry.json()
    assert body["succeeded"] == 0
    assert body["skipped"] == 2
    assert body["failed"] == 1
    assert len(
        client.get(f"/api/v1/crew/{crew_id}/assessments").json()
    ) == 2


def test_reanalysis_unknown_crew_is_404(client) -> None:
    """Unknown crew members cannot trigger re-analysis."""
    response = client.post("/api/v1/crew/missing/assessments/reanalyze")
    assert response.status_code == 404


def test_reanalysis_without_engine_is_503(client, crew_id: str) -> None:
    """A disabled engine is reported explicitly instead of silently succeeding."""
    client.app.state.analysis_engine = None
    response = client.post(f"/api/v1/crew/{crew_id}/assessments/reanalyze")
    assert response.status_code == 503
