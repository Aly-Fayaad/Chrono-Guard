r"""Deterministic synthetic scenario fixtures for mission intelligence (Phase 8).

Six reproducible scenarios exercise the mission-intelligence rules end to end:

``normal_sleep``
    Adequate, consistent sleep and ordinary daytime duties. No finding.

``sleep_deprivation``
    Four short nights and a demanding task soon after waking, with a fatigue
    signal of ``monitor``.

``high_workload``
    Four demanding tasks back to back inside one workload window.

``sleep_mission_conflict``
    A demanding night task scheduled inside the inferred sleep opportunity.

``high_fatigue_before_critical``
    An ``elevated_concern`` assessment and a critical EVA. The assessment row is
    clearly marked as synthetic test data and is **not** AI model output.

``recovery_scheduling``
    Two demanding tasks separated by a 10 minute gap. The Phase 8 tests use the
    what-if API to insert a structured recovery period and compare the rules.

Every row is synthetic. The schema has a ``source`` column only on
``SleepRecord`` and ``HealthMeasurement``; those rows use
``MeasurementSource.simulated``. ``Assessment`` and ``MissionTask`` have no
source column, so their text fields carry the explicit marker
``SYNTHETIC TEST DATA (source=simulated) - not AI model output.``.

The crew ids are ``crew-mission-01`` through ``crew-mission-06``. They never
overlap the demo crews ``crew-demo-01`` through ``crew-demo-03``. The seed
function is idempotent and ``--reset`` deletes only those six ids.

Run the CLI from ``backend/``::

    \& ".\.venv\Scripts\python.exe" -m app.mission.scenario_fixtures
    \& ".\.venv\Scripts\python.exe" -m app.mission.scenario_fixtures --reset
    \& ".\.venv\Scripts\python.exe" -m app.mission.scenario_fixtures --scenario normal_sleep
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlmodel import Session, select

from app.core.database import engine, init_db
from app.models import (
    ActionHistory,
    Assessment,
    CheckIn,
    CrewProfile,
    HealthMeasurement,
    MissionTask,
    SleepRecord,
)
from app.models.enums import (
    AssessmentStatus,
    MeasurementSource,
    QualityFlag,
    TaskType,
    WorkloadLevel,
)

UTC = timezone.utc

WINDOW_START = datetime(2026, 11, 13, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 11, 14, 0, 0, tzinfo=UTC)
"""Common evaluation window for every scenario (UTC, half-open day)."""

SYNTHETIC_MARKER = (
    "SYNTHETIC TEST DATA (source=simulated) - not AI model output."
)
"""Marker used where the schema has no ``source`` column."""

FIXTURE_ENGINE_VERSION = "synthetic-scenario-fixture/1.0"
"""Engine version written to synthetic assessments. It is not an AI model id."""

ScenarioKey = Literal[
    "normal_sleep",
    "sleep_deprivation",
    "high_workload",
    "sleep_mission_conflict",
    "high_fatigue_before_critical",
    "recovery_scheduling",
]


@dataclass(frozen=True)
class ScenarioSpec:
    """Static metadata for one deterministic scenario."""

    key: ScenarioKey
    crew_id: str
    display_name: str
    role: str
    sleep_target_hours: float
    assessment_status: AssessmentStatus
    assessment_summary: str
    window_start: datetime = WINDOW_START
    window_end: datetime = WINDOW_END


SCENARIOS: tuple[ScenarioSpec, ...] = (
    ScenarioSpec(
        key="normal_sleep",
        crew_id="crew-mission-01",
        display_name="Mira Sol",
        role="Commander",
        sleep_target_hours=8.0,
        assessment_status=AssessmentStatus.no_flag,
        assessment_summary=(
            f"{SYNTHETIC_MARKER} Normal-sleep baseline; no fatigue flag."
        ),
    ),
    ScenarioSpec(
        key="sleep_deprivation",
        crew_id="crew-mission-02",
        display_name="Tomas Reed",
        role="Mission Specialist",
        sleep_target_hours=8.0,
        assessment_status=AssessmentStatus.monitor,
        assessment_summary=(
            f"{SYNTHETIC_MARKER} Short-sleep pattern; monitoring advisory only."
        ),
    ),
    ScenarioSpec(
        key="high_workload",
        crew_id="crew-mission-03",
        display_name="Anya Novak",
        role="Flight Engineer",
        sleep_target_hours=8.0,
        assessment_status=AssessmentStatus.no_flag,
        assessment_summary=(
            f"{SYNTHETIC_MARKER} High-workload schedule with adequate sleep."
        ),
    ),
    ScenarioSpec(
        key="sleep_mission_conflict",
        crew_id="crew-mission-04",
        display_name="Idris Kane",
        role="Pilot",
        sleep_target_hours=8.0,
        assessment_status=AssessmentStatus.no_flag,
        assessment_summary=(
            f"{SYNTHETIC_MARKER} Night task inside the inferred sleep window."
        ),
    ),
    ScenarioSpec(
        key="high_fatigue_before_critical",
        crew_id="crew-mission-05",
        display_name="Lea Fontaine",
        role="EVA Specialist",
        sleep_target_hours=8.0,
        assessment_status=AssessmentStatus.elevated_concern,
        assessment_summary=(
            f"{SYNTHETIC_MARKER} Elevated-concern fixture for a critical-task "
            "review. This status was chosen for the test and is not produced by "
            "the AI model."
        ),
    ),
    ScenarioSpec(
        key="recovery_scheduling",
        crew_id="crew-mission-06",
        display_name="Noah Brandt",
        role="Science Officer",
        sleep_target_hours=8.0,
        assessment_status=AssessmentStatus.no_flag,
        assessment_summary=(
            f"{SYNTHETIC_MARKER} Two demanding tasks with a short recovery gap."
        ),
    ),
)

SCENARIOS_BY_KEY: dict[str, ScenarioSpec] = {
    spec.key: spec for spec in SCENARIOS
}
SCENARIO_KEYS: tuple[str, ...] = tuple(spec.key for spec in SCENARIOS)
CREW_IDS: tuple[str, ...] = tuple(spec.crew_id for spec in SCENARIOS)
"""Only these six ids are deleted by ``--reset``."""

_DELETE_ORDER = (
    ActionHistory,
    Assessment,
    SleepRecord,
    HealthMeasurement,
    CheckIn,
    MissionTask,
)
"""Dependent rows removed before the crew profile."""


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------


def _sleep(
    crew_id: str,
    *,
    index: int,
    start: datetime,
    end: datetime,
    interruptions: int = 0,
) -> SleepRecord:
    """Build one synthetic, valid sleep record."""
    duration_hours = (end - start).total_seconds() / 3600.0
    return SleepRecord(
        id=f"{crew_id}-sleep-{index:02d}",
        crew_id=crew_id,
        sleep_start=start,
        sleep_end=end,
        duration_hours=round(duration_hours, 3),
        interruptions=interruptions,
        source=MeasurementSource.simulated,
        quality=QualityFlag.valid,
    )


def _regular_sleep(crew_id: str) -> list[SleepRecord]:
    """Return three consistent 22:00-06:00 UTC sleep records.

    The newest record ends on 2026-11-13 at 06:00 UTC, so
    ``infer_planned_sleep`` returns the next habitual window,
    2026-11-13 22:00 to 2026-11-14 06:00 UTC.
    """
    records: list[SleepRecord] = []
    for index, day in enumerate((10, 11, 12), start=1):
        records.append(
            _sleep(
                crew_id,
                index=index,
                start=datetime(2026, 11, day, 22, 0, tzinfo=UTC),
                end=datetime(2026, 11, day + 1, 6, 0, tzinfo=UTC),
            )
        )
    return records


def _short_sleep(crew_id: str) -> list[SleepRecord]:
    """Return four 02:00-06:00 UTC sleep records (four hours each)."""
    records: list[SleepRecord] = []
    for index, day in enumerate((10, 11, 12, 13), start=1):
        records.append(
            _sleep(
                crew_id,
                index=index,
                start=datetime(2026, 11, day, 2, 0, tzinfo=UTC),
                end=datetime(2026, 11, day, 6, 0, tzinfo=UTC),
            )
        )
    return records


def _task(
    crew_id: str,
    *,
    task_id: str,
    title: str,
    task_type: TaskType,
    start: datetime,
    end: datetime,
    workload: WorkloadLevel,
    is_critical: bool = False,
) -> MissionTask:
    """Build one synthetic mission task."""
    return MissionTask(
        id=task_id,
        crew_id=crew_id,
        title=title,
        task_type=task_type,
        start_time=start,
        end_time=end,
        workload_level=workload,
        is_critical=is_critical,
        notes=f"{SYNTHETIC_MARKER} Scenario fixture only.",
    )


def _assessment(spec: ScenarioSpec) -> Assessment:
    """Build the synthetic assessment row for one scenario."""
    return Assessment(
        id=f"{spec.crew_id}-assessment",
        crew_id=spec.crew_id,
        status=spec.assessment_status,
        summary=spec.assessment_summary,
        explanation=(
            f"{SYNTHETIC_MARKER} Seeded by app.mission.scenario_fixtures for "
            "deterministic tests. It is not a model result and must not be read "
            "as a clinical finding."
        ),
        contributing_factors=[
            {
                "source": "simulated",
                "synthetic_test_data": True,
                "model_output": False,
                "scenario": spec.key,
            }
        ],
        engine_version=FIXTURE_ENGINE_VERSION,
        created_at=datetime(2026, 11, 13, 6, 30, tzinfo=UTC),
    )


def _normal_sleep_tasks(crew_id: str) -> list[MissionTask]:
    """Ordinary daytime duties with adequate spacing."""
    return [
        _task(
            crew_id,
            task_id=f"{crew_id}-task-science",
            title="Science sample analysis",
            task_type=TaskType.science,
            start=datetime(2026, 11, 13, 9, 0, tzinfo=UTC),
            end=datetime(2026, 11, 13, 10, 30, tzinfo=UTC),
            workload=WorkloadLevel.medium,
        ),
        _task(
            crew_id,
            task_id=f"{crew_id}-task-exercise",
            title="Resistance exercise",
            task_type=TaskType.exercise,
            start=datetime(2026, 11, 13, 12, 0, tzinfo=UTC),
            end=datetime(2026, 11, 13, 13, 0, tzinfo=UTC),
            workload=WorkloadLevel.medium,
        ),
        _task(
            crew_id,
            task_id=f"{crew_id}-task-maintenance",
            title="Habitat maintenance",
            task_type=TaskType.maintenance,
            start=datetime(2026, 11, 13, 15, 0, tzinfo=UTC),
            end=datetime(2026, 11, 13, 16, 0, tzinfo=UTC),
            workload=WorkloadLevel.low,
        ),
    ]


def _sleep_deprivation_tasks(crew_id: str) -> list[MissionTask]:
    """One demanding task soon after waking, plus an ordinary duty."""
    return [
        _task(
            crew_id,
            task_id=f"{crew_id}-task-early",
            title="Post-wake maintenance",
            task_type=TaskType.maintenance,
            start=datetime(2026, 11, 13, 6, 15, tzinfo=UTC),
            end=datetime(2026, 11, 13, 7, 15, tzinfo=UTC),
            workload=WorkloadLevel.high,
        ),
        _task(
            crew_id,
            task_id=f"{crew_id}-task-day",
            title="Science sample analysis",
            task_type=TaskType.science,
            start=datetime(2026, 11, 13, 11, 0, tzinfo=UTC),
            end=datetime(2026, 11, 13, 12, 0, tzinfo=UTC),
            workload=WorkloadLevel.medium,
        ),
    ]


def _high_workload_tasks(crew_id: str) -> list[MissionTask]:
    """Four back-to-back demanding tasks inside one 24 hour window."""
    tasks: list[MissionTask] = []
    for slot, hour in enumerate((8, 10, 12, 14), start=1):
        tasks.append(
            _task(
                crew_id,
                task_id=f"{crew_id}-task-demand-{slot}",
                title=f"Demanding maintenance block {slot}",
                task_type=TaskType.maintenance,
                start=datetime(2026, 11, 13, hour, 0, tzinfo=UTC),
                end=datetime(2026, 11, 13, hour + 2, 0, tzinfo=UTC),
                workload=WorkloadLevel.high,
            )
        )
    return tasks


def _sleep_mission_conflict_tasks(crew_id: str) -> list[MissionTask]:
    """A daytime duty and a demanding task inside the inferred sleep window."""
    return [
        _task(
            crew_id,
            task_id=f"{crew_id}-task-day",
            title="Science sample analysis",
            task_type=TaskType.science,
            start=datetime(2026, 11, 13, 10, 0, tzinfo=UTC),
            end=datetime(2026, 11, 13, 11, 0, tzinfo=UTC),
            workload=WorkloadLevel.medium,
        ),
        _task(
            crew_id,
            task_id=f"{crew_id}-task-night",
            title="Night maintenance",
            task_type=TaskType.maintenance,
            start=datetime(2026, 11, 13, 23, 0, tzinfo=UTC),
            end=datetime(2026, 11, 14, 0, 0, tzinfo=UTC),
            workload=WorkloadLevel.high,
        ),
    ]


def _high_fatigue_tasks(crew_id: str) -> list[MissionTask]:
    """A critical EVA and a low-workload afternoon duty."""
    return [
        _task(
            crew_id,
            task_id=f"{crew_id}-task-eva",
            title="Critical EVA - solar array inspection",
            task_type=TaskType.eva,
            start=datetime(2026, 11, 13, 9, 0, tzinfo=UTC),
            end=datetime(2026, 11, 13, 13, 0, tzinfo=UTC),
            workload=WorkloadLevel.high,
            is_critical=True,
        ),
        _task(
            crew_id,
            task_id=f"{crew_id}-task-review",
            title="Procedure review",
            task_type=TaskType.other,
            start=datetime(2026, 11, 13, 15, 0, tzinfo=UTC),
            end=datetime(2026, 11, 13, 16, 0, tzinfo=UTC),
            workload=WorkloadLevel.low,
        ),
    ]


def _recovery_scheduling_tasks(crew_id: str) -> list[MissionTask]:
    """Two demanding tasks with a 10 minute recovery gap."""
    return [
        _task(
            crew_id,
            task_id=f"{crew_id}-task-demanding-a",
            title="Demanding maintenance A",
            task_type=TaskType.maintenance,
            start=datetime(2026, 11, 13, 8, 0, tzinfo=UTC),
            end=datetime(2026, 11, 13, 9, 0, tzinfo=UTC),
            workload=WorkloadLevel.high,
        ),
        _task(
            crew_id,
            task_id=f"{crew_id}-task-demanding-b",
            title="Demanding maintenance B",
            task_type=TaskType.maintenance,
            start=datetime(2026, 11, 13, 9, 10, tzinfo=UTC),
            end=datetime(2026, 11, 13, 10, 10, tzinfo=UTC),
            workload=WorkloadLevel.high,
        ),
        _task(
            crew_id,
            task_id=f"{crew_id}-task-day",
            title="Science sample analysis",
            task_type=TaskType.science,
            start=datetime(2026, 11, 13, 13, 0, tzinfo=UTC),
            end=datetime(2026, 11, 13, 14, 0, tzinfo=UTC),
            workload=WorkloadLevel.medium,
        ),
    ]


_BUILDERS = {
    "normal_sleep": _normal_sleep_tasks,
    "sleep_deprivation": _sleep_deprivation_tasks,
    "high_workload": _high_workload_tasks,
    "sleep_mission_conflict": _sleep_mission_conflict_tasks,
    "high_fatigue_before_critical": _high_fatigue_tasks,
    "recovery_scheduling": _recovery_scheduling_tasks,
}


def _rows_for(spec: ScenarioSpec) -> list[object]:
    """Build every row for one scenario in deterministic order."""
    crew = CrewProfile(
        id=spec.crew_id,
        display_name=spec.display_name,
        role=spec.role,
        sleep_target_hours=spec.sleep_target_hours,
    )
    if spec.key == "sleep_deprivation":
        sleep_records = _short_sleep(spec.crew_id)
    else:
        sleep_records = _regular_sleep(spec.crew_id)
    return [
        crew,
        _assessment(spec),
        *sleep_records,
        *_BUILDERS[spec.key](spec.crew_id),
    ]


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def _delete_crew(session: Session, crew_id: str) -> None:
    """Delete one scenario crew and its dependent rows only."""
    for model in _DELETE_ORDER:
        for row in session.exec(
            select(model).where(model.crew_id == crew_id)
        ).all():
            session.delete(row)
    crew = session.get(CrewProfile, crew_id)
    if crew is not None:
        session.delete(crew)
    session.commit()


def reset_scenarios(session: Session) -> list[str]:
    """Delete every Phase 8 scenario crew; return the ids that were removed.

    Crews outside ``CREW_IDS`` are never queried or deleted.
    """
    removed: list[str] = []
    for crew_id in CREW_IDS:
        if session.get(CrewProfile, crew_id) is not None:
            _delete_crew(session, crew_id)
            removed.append(crew_id)
    return removed


def seed_scenario(
    session: Session, scenario: str, *, reset: bool = False
) -> dict[str, object]:
    """Seed one scenario, skipping an existing crew unless ``reset`` is true.

    Args:
        session: Open database session.
        scenario: One of ``SCENARIO_KEYS``.
        reset: Delete and recreate this crew id when it already exists. No other
            crew id is touched.

    Returns:
        ``{"scenario": key, "created": bool, "crew_id": str}``.

    Raises:
        KeyError: if ``scenario`` is not a Phase 8 scenario key.
    """
    spec = SCENARIOS_BY_KEY[scenario]
    if session.get(CrewProfile, spec.crew_id) is not None:
        if not reset:
            return {
                "scenario": spec.key,
                "created": False,
                "crew_id": spec.crew_id,
            }
        _delete_crew(session, spec.crew_id)
    session.add_all(_rows_for(spec))
    session.commit()
    return {"scenario": spec.key, "created": True, "crew_id": spec.crew_id}


def seed_all(session: Session, *, reset: bool = False) -> list[dict[str, object]]:
    """Seed all six scenarios in a stable order."""
    return [
        seed_scenario(session, key, reset=reset)
        for key in SCENARIO_KEYS
    ]


def main() -> None:
    """Seed the Phase 8 scenarios from the command line."""
    parser = argparse.ArgumentParser(
        description=(
            "Seed deterministic synthetic mission scenarios "
            "(crew-mission-01 ... crew-mission-06)."
        )
    )
    parser.add_argument(
        "--scenario",
        choices=SCENARIO_KEYS,
        default=None,
        help="Seed one scenario instead of all six.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Delete and recreate the selected scenario crew id(s). Only the "
            "crew-mission-* ids are touched."
        ),
    )
    args = parser.parse_args()

    init_db()
    with Session(engine, expire_on_commit=False) as session:
        selected = [args.scenario] if args.scenario else list(SCENARIO_KEYS)
        for key in selected:
            result = seed_scenario(session, key, reset=args.reset)
            state = "created" if result["created"] else "skipped"
            print(f"{key}: {state} ({result['crew_id']})")


if __name__ == "__main__":
    main()
