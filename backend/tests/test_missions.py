"""Mission task CRUD and scheduling-rule tests."""

from datetime import datetime, timedelta, timezone

BASE = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def _task_payload(**overrides) -> dict:
    payload = {
        "title": "EVA preparation",
        "task_type": "eva",
        "start_time": (BASE + timedelta(days=1)).isoformat(),
        "end_time": (BASE + timedelta(days=1, hours=2)).isoformat(),
        "workload_level": "high",
        "is_critical": True,
        "notes": "Check suit",
    }
    payload.update(overrides)
    return payload


def test_mission_crud(client, crew_id: str) -> None:
    """Create, list, read, update, and delete a mission task."""
    created = client.post(f"/api/v1/crew/{crew_id}/missions", json=_task_payload())
    assert created.status_code == 201
    task = created.json()
    assert task["is_critical"] is True

    listed = client.get(f"/api/v1/crew/{crew_id}/missions").json()
    assert [row["id"] for row in listed] == [task["id"]]

    read = client.get(f"/api/v1/crew/{crew_id}/missions/{task['id']}")
    assert read.status_code == 200

    new_end = (BASE + timedelta(days=1, hours=3)).isoformat()
    updated = client.patch(
        f"/api/v1/crew/{crew_id}/missions/{task['id']}",
        json={"title": "EVA rehearsal", "end_time": new_end},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "EVA rehearsal"

    deleted = client.delete(f"/api/v1/crew/{crew_id}/missions/{task['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": task["id"]}
    assert client.get(f"/api/v1/crew/{crew_id}/missions/{task['id']}").status_code == 404


def test_end_time_must_be_after_start(client, crew_id: str) -> None:
    """Invalid task windows are rejected on create and update."""
    start = (BASE + timedelta(days=1)).isoformat()
    payload = _task_payload(start_time=start, end_time=start)
    assert client.post(f"/api/v1/crew/{crew_id}/missions", json=payload).status_code == 422

    task = client.post(f"/api/v1/crew/{crew_id}/missions", json=_task_payload()).json()
    response = client.patch(
        f"/api/v1/crew/{crew_id}/missions/{task['id']}", json={"end_time": start}
    )
    assert response.status_code == 422
    unchanged = client.get(f"/api/v1/crew/{crew_id}/missions/{task['id']}").json()
    assert unchanged["end_time"] == task["end_time"]


def test_upcoming_filter(client, crew_id: str) -> None:
    """The upcoming flag excludes past tasks and honours the from bound."""
    now = datetime.now(timezone.utc)
    past = _task_payload(
        title="Past maintenance",
        task_type="maintenance",
        start_time=(now - timedelta(days=2)).isoformat(),
        end_time=(now - timedelta(days=1)).isoformat(),
    )
    future = _task_payload(
        title="Future science",
        task_type="science",
        start_time=(now + timedelta(days=1)).isoformat(),
        end_time=(now + timedelta(days=1, hours=1)).isoformat(),
    )
    assert client.post(f"/api/v1/crew/{crew_id}/missions", json=past).status_code == 201
    assert client.post(f"/api/v1/crew/{crew_id}/missions", json=future).status_code == 201

    everything = client.get(f"/api/v1/crew/{crew_id}/missions").json()
    assert len(everything) == 2
    upcoming = client.get(f"/api/v1/crew/{crew_id}/missions?upcoming=true").json()
    assert [row["title"] for row in upcoming] == ["Future science"]

    horizon = (now + timedelta(days=2)).isoformat()
    bounded = client.get(
        f"/api/v1/crew/{crew_id}/missions?upcoming=true&to={horizon}"
    ).json()
    assert len(bounded) == 1


def test_unknown_crew_and_task_return_404(client, crew_id: str) -> None:
    """Mission routes reject unknown crew members and tasks."""
    assert client.get("/api/v1/crew/missing/missions").status_code == 404
    assert (
        client.post("/api/v1/crew/missing/missions", json=_task_payload()).status_code == 404
    )
    assert client.get(f"/api/v1/crew/{crew_id}/missions/nope").status_code == 404
