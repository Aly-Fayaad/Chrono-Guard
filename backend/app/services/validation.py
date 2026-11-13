"""Plausibility validation and server-owned units."""

import math
from datetime import datetime
from typing import TypedDict

from app.models.enums import MeasurementType, QualityFlag


class ValidationFailure(ValueError):
    """Raised when a submitted value violates a hard rule."""


class LimitSpec(TypedDict):
    """Unit and hard/soft bounds for one measurement key."""

    unit: str
    hard: tuple[float, float]
    soft: tuple[float, float] | None


# prototype plausibility ranges, not clinical thresholds
LIMITS: dict[str, LimitSpec] = {
    "heart_rate": {"unit": "bpm", "hard": (20.0, 250.0), "soft": (40.0, 120.0)},
    "systolic_bp": {"unit": "mmHg", "hard": (50.0, 260.0), "soft": (90.0, 140.0)},
    "diastolic_bp": {"unit": "mmHg", "hard": (30.0, 160.0), "soft": (50.0, 90.0)},
    "body_temperature": {"unit": "C", "hard": (30.0, 43.0), "soft": (35.5, 37.8)},
    "mood": {"unit": "score", "hard": (1.0, 5.0), "soft": None},
    "sleepiness_kss": {"unit": "score", "hard": (1.0, 9.0), "soft": None},
    "perceived_stress": {"unit": "score", "hard": (1.0, 5.0), "soft": None},
    "sleep_duration_hours": {"unit": "h", "hard": (0.0, 24.0), "soft": (3.0, 12.0)},
    "interruptions": {"unit": "count", "hard": (0.0, 20.0), "soft": None},
}


def unit_for(measurement_type: MeasurementType) -> str:
    """Return the server-owned unit for a measurement type."""
    return str(LIMITS[measurement_type.value]["unit"])


def _quality(key: str, value: float) -> QualityFlag:
    """Apply hard and soft bounds for one limit key."""
    if not math.isfinite(value):
        raise ValidationFailure(f"{key} must be a finite number")
    low, high = LIMITS[key]["hard"]
    if value < low or value > high:
        raise ValidationFailure(f"{key} must be between {low:g} and {high:g}")
    soft = LIMITS[key]["soft"]
    if soft is not None and not soft[0] <= value <= soft[1]:
        return QualityFlag.questionable
    return QualityFlag.valid


def quality_for(measurement_type: MeasurementType, value: float) -> QualityFlag:
    """Validate a measurement and return its quality flag."""
    return _quality(measurement_type.value, value)


def validate_blood_pressure(systolic: float | None, diastolic: float | None) -> None:
    """Reject systolic values that are not greater than diastolic values."""
    if systolic is not None and diastolic is not None and systolic <= diastolic:
        raise ValidationFailure("systolic_bp must be greater than diastolic_bp")


def validate_sleep(
    sleep_start: datetime, sleep_end: datetime, interruptions: int
) -> tuple[float, QualityFlag]:
    """Validate a sleep interval and return computed duration and quality."""
    if sleep_end <= sleep_start:
        raise ValidationFailure("sleep_end must be after sleep_start")
    raw_duration = (sleep_end - sleep_start).total_seconds() / 3600
    if raw_duration <= 0 or raw_duration > 24:
        raise ValidationFailure("sleep duration must be greater than 0 and at most 24 hours")
    _quality("interruptions", float(interruptions))
    return round(raw_duration, 2), _quality("sleep_duration_hours", raw_duration)
