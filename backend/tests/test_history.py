"""History filtering and read-helper contract tests."""

from app.services.history_service import get_measurements, get_sleep_records


def _post(client, crew_id: str, recorded_at: str, measurements: dict, sleep: dict | None = None):
    payload = {"recorded_at": recorded_at, **measurements}
    if sleep is not None:
        payload["sleep"] = sleep
    response = client.post(f"/api/v1/crew/{crew_id}/checkins", json=payload)
    assert response.status_code == 201
    return response.json()


def _sleep(day: str) -> dict:
    return {
        "sleep_start": f"{day}T00:00:00Z",
        "sleep_end": f"{day}T07:00:00Z",
        "interruptions": 0,
    }


def test_measurement_history_filters(client, crew_id: str) -> None:
    """Measurement history supports type, from, to, and limit filters."""
    _post(client, crew_id, "2026-11-01T12:00:00Z", {"cardiovascular": {"heart_rate": 70}}, _sleep("2026-11-01"))
    _post(client, crew_id, "2026-11-03T12:00:00Z", {"behavioral": {"mood": 4}})
    _post(
        client,
        crew_id,
        "2026-11-05T12:00:00Z",
        {"cardiovascular": {"heart_rate": 80}, "physical": {"body_temperature": 38.2}},
        _sleep("2026-11-05"),
    )

    heart = client.get(f"/api/v1/crew/{crew_id}/history/measurements?type=heart_rate").json()
    assert [row["value"] for row in heart["measurements"]] == [80.0, 70.0]

    since = client.get(
        f"/api/v1/crew/{crew_id}/history/measurements?from=2026-11-04T00:00:00Z"
    ).json()["measurements"]
    assert {row["type"] for row in since} == {"heart_rate", "body_temperature"}

    until = client.get(
        f"/api/v1/crew/{crew_id}/history/measurements?to=2026-11-02T00:00:00Z"
    ).json()["measurements"]
    assert [row["value"] for row in until] == [70.0]

    limited = client.get(
        f"/api/v1/crew/{crew_id}/history/measurements?type=heart_rate&limit=1"
    ).json()["measurements"]
    assert [row["value"] for row in limited] == [80.0]


def test_sleep_history_filters(client, crew_id: str) -> None:
    """Sleep history supports from and to filters."""
    _post(client, crew_id, "2026-11-01T12:00:00Z", {"behavioral": {"mood": 4}}, _sleep("2026-11-01"))
    _post(client, crew_id, "2026-11-05T12:00:00Z", {"behavioral": {"mood": 3}}, _sleep("2026-11-05"))

    all_rows = client.get(f"/api/v1/crew/{crew_id}/history/sleep").json()["sleep_records"]
    assert len(all_rows) == 2
    recent = client.get(
        f"/api/v1/crew/{crew_id}/history/sleep?from=2026-11-04T00:00:00Z"
    ).json()["sleep_records"]
    assert len(recent) == 1
    early = client.get(
        f"/api/v1/crew/{crew_id}/history/sleep?to=2026-11-02T00:00:00Z"
    ).json()["sleep_records"]
    assert len(early) == 1


def test_read_helpers_support_valid_only(client, crew_id: str, session_factory) -> None:
    """The P3/P4 data-access helpers can exclude questionable rows."""
    _post(client, crew_id, "2026-11-01T12:00:00Z", {"cardiovascular": {"heart_rate": 70}})
    _post(client, crew_id, "2026-11-02T12:00:00Z", {"cardiovascular": {"heart_rate": 130}})
    with session_factory() as session:
        all_rows = get_measurements(session, crew_id)
        valid_rows = get_measurements(session, crew_id, valid_only=True)
    assert len(all_rows) == 2
    assert len(valid_rows) == 1
    assert valid_rows[0].quality.value == "valid"


def test_history_unknown_crew_returns_404(client) -> None:
    """History routes reject unknown crew ids."""
    assert client.get("/api/v1/crew/missing/history/measurements").status_code == 404
    assert client.get("/api/v1/crew/missing/history/sleep").status_code == 404
