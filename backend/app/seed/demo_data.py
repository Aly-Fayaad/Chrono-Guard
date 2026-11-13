"""Deterministic synthetic demo scenarios and CLI."""

import argparse
import random
from datetime import datetime, timedelta
from typing import Literal

from sqlmodel import Session
from sqlmodel import select

from app.core.database import engine, init_db, utcnow
from app.models import (
    ActionHistory,
    Assessment,
    CheckIn,
    CrewProfile,
    HealthMeasurement,
    MissionTask,
    SleepRecord,
)
from app.models.enums import MeasurementSource, MeasurementType, TaskType, WorkloadLevel
from app.services.validation import quality_for, unit_for, validate_sleep

Scenario = Literal["normal_routine", "reduced_recovery", "incomplete_records"]
SEED_SCENARIOS: tuple[Scenario, ...] = ("normal_routine", "reduced_recovery", "incomplete_records")
SEED = 42

CREW_IDS: dict[Scenario, str] = {
    "normal_routine": "crew-demo-01",
    "reduced_recovery": "crew-demo-02",
    "incomplete_records": "crew-demo-03",
}
PROFILES: dict[Scenario, tuple[str, str, float]] = {
    "normal_routine": ("Luna Park", "Flight Engineer", 8.0),
    "reduced_recovery": ("Ivan Volkov", "Mission Specialist", 7.5),
    "incomplete_records": ("Aria Chen", "Commander", 7.5),
}


def _at(now: datetime, days_ago: int, hour: int) -> datetime:
    """Return a past timestamp on a relative day."""
    value = (now - timedelta(days=days_ago)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    return min(value, now - timedelta(minutes=5))


def _add_checkin(
    session: Session,
    crew_id: str,
    at: datetime,
    values: dict[MeasurementType, float],
    sleep: tuple[datetime, datetime, int] | None = None,
    notes: str | None = None,
) -> None:
    """Add one simulated check-in with measurements and optional sleep."""
    checkin = CheckIn(crew_id=crew_id, submitted_at=at, notes=notes)
    session.add(checkin)
    for measurement_type, value in values.items():
        session.add(
            HealthMeasurement(
                crew_id=crew_id,
                checkin_id=checkin.id,
                type=measurement_type,
                value=float(value),
                unit=unit_for(measurement_type),
                recorded_at=at,
                source=MeasurementSource.simulated,
                quality=quality_for(measurement_type, float(value)),
            )
        )
    if sleep is not None:
        start, end, interruptions = sleep
        duration, quality = validate_sleep(start, end, interruptions)
        session.add(
            SleepRecord(
                crew_id=crew_id,
                checkin_id=checkin.id,
                sleep_start=start,
                sleep_end=end,
                duration_hours=duration,
                interruptions=interruptions,
                source=MeasurementSource.simulated,
                quality=quality,
            )
        )


def _add_task(
    session: Session,
    crew_id: str,
    title: str,
    task_type: TaskType,
    start: datetime,
    hours: float,
    workload: WorkloadLevel,
    critical: bool = False,
) -> None:
    """Add one simulated mission task."""
    session.add(
        MissionTask(
            crew_id=crew_id,
            title=title,
            task_type=task_type,
            start_time=start,
            end_time=start + timedelta(hours=hours),
            workload_level=workload,
            is_critical=critical,
        )
    )


def _sleep_window(end: datetime, duration: float) -> tuple[datetime, datetime, int]:
    """Build a sleep tuple ending at the given morning timestamp."""
    return end - timedelta(hours=duration + 0.5), end, 0


def _normal(session: Session, crew_id: str, now: datetime, rng: random.Random) -> None:
    """Consistent sleep and regular duties."""
    for days_ago in range(6, -1, -1):
        morning = _at(now, days_ago, 7)
        duration = rng.uniform(7.2, 8.2)
        values = {
            MeasurementType.heart_rate: rng.uniform(58, 70),
            MeasurementType.hrv: rng.uniform(55, 68),
            MeasurementType.systolic_bp: rng.uniform(112, 124),
            MeasurementType.diastolic_bp: rng.uniform(70, 80),
            MeasurementType.body_temperature: rng.uniform(36.3, 36.8),
            MeasurementType.mood: rng.randint(4, 5),
            MeasurementType.sleepiness_kss: rng.randint(1, 3),
            MeasurementType.perceived_stress: rng.randint(1, 2),
        }
        _add_checkin(session, crew_id, morning, values, _sleep_window(morning, duration))
        _add_task(session, crew_id, "Science sample analysis", TaskType.science, _at(now, days_ago, 9), 2, WorkloadLevel.low)
        _add_task(session, crew_id, "Resistance exercise", TaskType.exercise, _at(now, days_ago, 16), 1, WorkloadLevel.medium)


def _reduced(session: Session, crew_id: str, now: datetime, rng: random.Random) -> None:
    """Repeated short sleep and rising workload with a critical EVA tomorrow."""
    for days_ago in range(6, -1, -1):
        morning = _at(now, days_ago, 7)
        duration = 2.8 if days_ago == 3 else rng.uniform(4.0, 5.5)
        values = {
            MeasurementType.heart_rate: rng.uniform(72, 86),
            MeasurementType.hrv: rng.uniform(40, 54),
            MeasurementType.systolic_bp: rng.uniform(118, 132),
            MeasurementType.diastolic_bp: rng.uniform(76, 86),
            MeasurementType.body_temperature: rng.uniform(36.4, 37.2),
            MeasurementType.mood: rng.randint(2, 3),
            MeasurementType.sleepiness_kss: rng.randint(5, 8),
            MeasurementType.perceived_stress: rng.randint(3, 4),
        }
        _add_checkin(session, crew_id, morning, values, _sleep_window(morning, duration))
        workload = (
            WorkloadLevel.high if days_ago <= 1
            else WorkloadLevel.medium if days_ago <= 3
            else WorkloadLevel.low
        )
        _add_task(session, crew_id, "Maintenance rotation", TaskType.maintenance, _at(now, days_ago, 9), 4, workload)
    tomorrow = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    _add_task(session, crew_id, "Critical EVA - regolith survey", TaskType.eva, tomorrow, 4, WorkloadLevel.high, True)


def _incomplete(session: Session, crew_id: str, now: datetime, rng: random.Random) -> None:
    """Missing days and questionable values."""
    day_six = _at(now, 6, 8)
    _add_checkin(
        session,
        crew_id,
        day_six,
        {MeasurementType.heart_rate: rng.uniform(64, 72)},
        notes="Partial entry",
    )
    day_four = _at(now, 4, 21)
    _add_checkin(
        session,
        crew_id,
        day_four,
        {MeasurementType.heart_rate: 125, MeasurementType.hrv: 46, MeasurementType.body_temperature: 38.3},
        _sleep_window(day_four, 5.0),
    )
    day_one = _at(now, 1, 7)
    _add_checkin(
        session,
        crew_id,
        day_one,
        {MeasurementType.mood: 3, MeasurementType.sleepiness_kss: 7},
        notes="No device sync",
    )
    _add_task(session, crew_id, "Medical check", TaskType.medical, _at(now, 2, 10), 1, WorkloadLevel.low)
    _add_task(session, crew_id, "Rest period", TaskType.rest, _at(now, 0, 13), 2, WorkloadLevel.low)


BUILDERS = {"normal_routine": _normal, "reduced_recovery": _reduced, "incomplete_records": _incomplete}
DELETE_ORDER = (ActionHistory, Assessment, SleepRecord, HealthMeasurement, CheckIn, MissionTask)


def _reset_crew(session: Session, crew_id: str) -> None:
    """Delete a demo crew and all of its dependent rows."""
    for model in DELETE_ORDER:
        for row in session.exec(select(model).where(model.crew_id == crew_id)).all():
            session.delete(row)
    crew = session.get(CrewProfile, crew_id)
    if crew is not None:
        session.delete(crew)
    session.commit()


def seed_scenario(session: Session, scenario: Scenario, reset: bool = False) -> dict[str, object]:
    """Seed one scenario, skipping an existing crew unless reset is requested."""
    crew_id = CREW_IDS[scenario]
    if session.get(CrewProfile, crew_id) is not None:
        if not reset:
            return {"scenario": scenario, "created": False, "crew_id": crew_id}
        _reset_crew(session, crew_id)
    display_name, role, sleep_target = PROFILES[scenario]
    session.add(
        CrewProfile(
            id=crew_id,
            display_name=display_name,
            role=role,
            sleep_target_hours=sleep_target,
        )
    )
    BUILDERS[scenario](session, crew_id, utcnow().replace(microsecond=0), random.Random(f"{SEED}:{scenario}"))
    session.commit()
    return {"scenario": scenario, "created": True, "crew_id": crew_id}


def main() -> None:
    """Run the demo seed CLI."""
    parser = argparse.ArgumentParser(description="Seed synthetic ChronoGuard demo data.")
    parser.add_argument("--scenario", choices=SEED_SCENARIOS, default=None)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    init_db()
    with Session(engine, expire_on_commit=False) as session:
        selected = [args.scenario] if args.scenario else list(SEED_SCENARIOS)
        for name in selected:
            result = seed_scenario(session, name, reset=args.reset)
            state = "created" if result["created"] else "skipped"
            print(f"{name}: {state} ({result['crew_id']})")


if __name__ == "__main__":
    main()
