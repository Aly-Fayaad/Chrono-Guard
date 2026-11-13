"""Check-in orchestration: validate, persist atomically, then analyse."""

import logging
from datetime import datetime

from sqlmodel import Session
from sqlmodel import select

from app.core.database import to_utc, utcnow
from app.models.assessment import Assessment
from app.models.checkin import CheckIn, HealthMeasurement, SleepRecord
from app.models.enums import MeasurementSource, MeasurementType
from app.schemas.checkin import CheckInCreate
from app.services.analysis import AnalysisEngine
from app.services.validation import (
    ValidationFailure,
    quality_for,
    unit_for,
    validate_blood_pressure,
    validate_sleep,
)

logger = logging.getLogger(__name__)

DEFAULT_CHECKIN_LIMIT = 50
MAX_CHECKIN_LIMIT = 200
_MEASUREMENT_FIELDS = (
    ("behavioral", MeasurementType.mood, "mood"),
    ("behavioral", MeasurementType.sleepiness_kss, "sleepiness_kss"),
    ("behavioral", MeasurementType.perceived_stress, "perceived_stress"),
    ("cardiovascular", MeasurementType.heart_rate, "heart_rate"),
    ("cardiovascular", MeasurementType.hrv, "hrv"),
    ("cardiovascular", MeasurementType.systolic_bp, "systolic_bp"),
    ("cardiovascular", MeasurementType.diastolic_bp, "diastolic_bp"),
    ("physical", MeasurementType.body_temperature, "body_temperature"),
)


def _build_rows(
    crew_id: str, payload: CheckInCreate, recorded_at: datetime
) -> tuple[list[HealthMeasurement], SleepRecord | None]:
    """Validate a payload and build unsaved measurement and sleep rows."""
    rows: list[HealthMeasurement] = []
    for section_name, measurement_type, field_name in _MEASUREMENT_FIELDS:
        section = getattr(payload, section_name)
        if section is None:
            continue
        value = getattr(section, field_name)
        if value is None:
            continue
        quality = quality_for(measurement_type, float(value))
        rows.append(
            HealthMeasurement(
                crew_id=crew_id,
                type=measurement_type,
                value=float(value),
                unit=unit_for(measurement_type),
                recorded_at=recorded_at,
                source=MeasurementSource.manual,
                quality=quality,
            )
        )
    sleep_record = _build_sleep(crew_id, payload)
    if not rows and sleep_record is None:
        raise ValidationFailure("at least one health or sleep value is required")
    return rows, sleep_record


def _build_sleep(crew_id: str, payload: CheckInCreate) -> SleepRecord | None:
    """Build and validate an optional sleep row."""
    if payload.sleep is None:
        return None
    start = to_utc(payload.sleep.sleep_start)
    end = to_utc(payload.sleep.sleep_end)
    duration, quality = validate_sleep(start, end, payload.sleep.interruptions)
    return SleepRecord(
        crew_id=crew_id,
        sleep_start=start,
        sleep_end=end,
        duration_hours=duration,
        interruptions=payload.sleep.interruptions,
        source=MeasurementSource.manual,
        quality=quality,
    )


def _run_engine(
    engine: AnalysisEngine | None, session: Session, crew_id: str, checkin_id: str
) -> Assessment | None:
    """Run the analysis hook without risking the committed check-in."""
    if engine is None:
        return None
    try:
        assessment = engine.analyze(session, crew_id, checkin_id)
        if assessment is None:
            return None
        session.add(assessment)
        session.commit()
        return assessment
    except Exception:  # noqa: BLE001 - extension hook must never break check-ins
        session.rollback()
        logger.exception("Analysis engine failed for check-in %s", checkin_id)
        return None


def create_checkin(
    session: Session, crew_id: str, payload: CheckInCreate, engine: AnalysisEngine | None
) -> tuple[CheckIn, list[HealthMeasurement], SleepRecord | None, Assessment | None]:
    """Validate, save one check-in atomically, then call the analysis hook."""
    recorded_at = to_utc(payload.recorded_at) if payload.recorded_at else utcnow()
    if payload.cardiovascular is not None:
        validate_blood_pressure(
            payload.cardiovascular.systolic_bp, payload.cardiovascular.diastolic_bp
        )
    rows, sleep_record = _build_rows(crew_id, payload, recorded_at)
    checkin = CheckIn(crew_id=crew_id, submitted_at=utcnow(), notes=payload.notes)
    for row in rows:
        row.checkin_id = checkin.id
    if sleep_record is not None:
        sleep_record.checkin_id = checkin.id
    try:
        session.add(checkin)
        session.add_all(rows)
        if sleep_record is not None:
            session.add(sleep_record)
        session.commit()
    except Exception:
        session.rollback()
        raise
    assessment = _run_engine(engine, session, crew_id, checkin.id)
    return checkin, rows, sleep_record, assessment


def list_checkins(session: Session, crew_id: str, limit: int, offset: int) -> list[CheckIn]:
    """Return a crew's check-ins, newest first."""
    statement = (
        select(CheckIn)
        .where(CheckIn.crew_id == crew_id)
        .order_by(CheckIn.submitted_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.exec(statement).all())


def list_all_checkins(session: Session, crew_id: str) -> list[CheckIn]:
    """Return every check-in for a crew member, oldest first."""
    statement = (
        select(CheckIn)
        .where(CheckIn.crew_id == crew_id)
        .order_by(CheckIn.submitted_at)
    )
    return list(session.exec(statement).all())


def get_checkin_detail(
    session: Session, crew_id: str, checkin_id: str
) -> tuple[CheckIn, list[HealthMeasurement], SleepRecord | None, Assessment | None] | None:
    """Return one check-in with its measurements, sleep record, and assessment."""
    checkin = session.get(CheckIn, checkin_id)
    if checkin is None or checkin.crew_id != crew_id:
        return None
    measurements = list(
        session.exec(
            select(HealthMeasurement)
            .where(HealthMeasurement.checkin_id == checkin_id)
            .order_by(HealthMeasurement.recorded_at)
        ).all()
    )
    sleep_record = session.exec(
        select(SleepRecord).where(SleepRecord.checkin_id == checkin_id)
    ).first()
    assessment = session.exec(
        select(Assessment)
        .where(Assessment.checkin_id == checkin_id)
        .order_by(Assessment.created_at.desc())
    ).first()
    return checkin, measurements, sleep_record, assessment
